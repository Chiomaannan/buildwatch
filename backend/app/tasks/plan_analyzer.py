"""
plan_analyzer.py — Celery task: analyze a building plan image to derive
site-specific MWPI weights and expected structural element counts.

Strategy (in priority order):
  1. Claude vision API  — best for rendered images, elevation drawings, floor plans
  2. YOLO on plan image — fallback when no API key; uses bounding box areas as proxies
  3. Hard defaults      — last resort (MOCK_INFERENCE=true, no key, YOLO fails)

Output stored on ProjectPlan:
  plan_weights    — {"foundation": 0.15, "column": 0.25, "wall": 0.40, "roof": 0.20}
  expected_counts — {"foundation": 2, "column": 8, "wall": 20, "roof": 1}

Plan weights cover STRUCTURAL classes only (a building plan shows structure,
not finish state). The fixed finishing weights (plastering/painting, 0.20 of
total mass) are injected at scoring time by progress.ensure_v2_weights, which
scales these structural weights by 0.80. Plans analyzed before roof support
are normalized the same way.
"""

import base64
import json
import logging
import re
from datetime import datetime, timezone

import cv2
import numpy as np

from app.config import get_settings
from app.database import SessionLocal
from app.models.plan import ProjectPlan
from app.services.minio_client import download_to_bytes
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()

_CLASSES = ["foundation", "column", "wall", "roof"]
_DEFAULT_WEIGHTS = {"foundation": 0.15, "column": 0.25, "wall": 0.40, "roof": 0.20}
_DEFAULT_COUNTS  = {"foundation": 2,    "column": 8,    "wall": 16,   "roof": 1}


# ── Claude vision analysis ────────────────────────────────────────────────────

def _analyze_with_claude(image_bytes: bytes) -> dict:
    """
    Send the plan image to Claude and extract structural weights + counts.
    Returns {"weights": {...}, "expected_counts": {...}}.
    Raises on any failure so the caller can fall back.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    # Detect mime type from magic bytes
    mime = "image/jpeg"
    if image_bytes[:4] == b'\x89PNG':
        mime = "image/png"
    elif image_bytes[:4] in (b'GIF8', b'GIF9'):
        mime = "image/gif"

    system = (
        "You are a structural analysis assistant for a construction monitoring system. "
        "Your role is to examine building plan images and output precise JSON describing "
        "the structural composition. You must always return valid JSON only — no prose, "
        "no markdown, no explanation. If you are uncertain, return the default values "
        "specified in the user prompt."
    )

    prompt = (
        "You are analyzing a building plan, architectural rendering, or photograph "
        "of a completed or planned residential/commercial building.\n\n"
        "Your job is to help a construction monitoring AI understand the structural "
        "composition of this building so it can track construction progress accurately.\n\n"
        "Examine the image and estimate TWO things:\n\n"
        "1. WEIGHTS — What proportion of the total structural work does each element type represent?\n"
        "   Consider the visual area, complexity, and quantity of each:\n"
        "   - foundation: base foundations, footings, ground-level structural base\n"
        "   - column: vertical structural columns, pillars, posts\n"
        "   - wall: load-bearing or infill walls (masonry, block, concrete walls)\n"
        "   - roof: roof structure and cover — the terminal structural milestone "
        "(weathertight/lockup stage)\n\n"
        "2. EXPECTED_COUNTS — How many of each element would a single fixed camera, "
        "mounted on one side of the site, realistically see as construction progresses? "
        "Exclude elements hidden behind completed walls or on the far side of the building.\n"
        "   - foundation: visible sections of foundation from one angle (usually 1–2)\n"
        "   - column: columns visible on the near face and side face only\n"
        "   - wall: wall spans visible from the camera's approximate viewpoint\n"
        "   - roof: roof sections visible from one angle (usually 1)\n\n"
        "Return ONLY valid JSON with no explanation:\n"
        '{"weights": {"foundation": 0.XX, "column": 0.XX, "wall": 0.XX, "roof": 0.XX}, '
        '"expected_counts": {"foundation": N, "column": N, "wall": N, "roof": N}}\n\n'
        "Rules:\n"
        "- weights must sum to exactly 1.0, minimum 0.05 per class\n"
        "- expected_counts must be positive integers\n"
        "- if the image is unclear, use: "
        '{"weights":{"foundation":0.15,"column":0.25,"wall":0.40,"roof":0.20},'
        '"expected_counts":{"foundation":2,"column":8,"wall":16,"roof":1}}'
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=system,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    )

    raw = message.content[0].text.strip()
    logger.info(f"Claude plan analysis raw response: {raw}")

    # Extract JSON robustly (sometimes Claude adds a sentence before the JSON)
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if not match:
        raise ValueError(f"Claude returned no JSON: {raw}")

    parsed = json.loads(match.group())

    weights = parsed.get("weights", {})
    counts  = parsed.get("expected_counts", {})

    # Validate weights
    for cls in _CLASSES:
        weights.setdefault(cls, 0.05)
    total = sum(weights.values()) or 1.0
    weights = {k: round(weights[k] / total, 4) for k in _CLASSES}

    # Validate counts
    for cls in _CLASSES:
        counts[cls] = max(1, int(counts.get(cls, _DEFAULT_COUNTS[cls])))

    return {"weights": weights, "expected_counts": counts}


# ── YOLO area-based fallback ──────────────────────────────────────────────────

def _analyze_with_yolo(img_bgr: np.ndarray) -> dict:
    """
    Run the existing BuildWatch YOLO model on the plan image.
    Compute per-class bounding-box area as a fraction of image area,
    then derive weights and use detection counts as expected_counts.
    """
    from app.services.ai.detector import detect

    h, w = img_bgr.shape[:2]
    img_area = h * w

    detections, _ = detect(img_bgr)

    class_areas: dict[str, float] = {c: 0.0 for c in _CLASSES}
    class_counts: dict[str, int]  = {c: 0   for c in _CLASSES}

    for d in detections:
        cls = d.get("class_name", "").lower()
        if cls not in _CLASSES:
            continue
        x1, y1, x2, y2 = d.get("bbox", [0, 0, 0, 0])
        area = max(0, (x2 - x1) * (y2 - y1))
        class_areas[cls]  += area / img_area  # normalized
        class_counts[cls] += 1

    total_area = sum(class_areas.values())

    if total_area < 0.001:
        logger.warning("YOLO found no structural elements in plan image — using defaults")
        return {"weights": _DEFAULT_WEIGHTS, "expected_counts": _DEFAULT_COUNTS}

    weights = {cls: round(class_areas[cls] / total_area, 4) for cls in _CLASSES}

    # Ensure minimum weight per class
    for cls in _CLASSES:
        if weights[cls] < 0.05:
            weights[cls] = 0.05
    total = sum(weights.values())
    weights = {cls: round(weights[cls] / total, 4) for cls in _CLASSES}

    counts = {cls: max(1, class_counts[cls]) for cls in _CLASSES}

    return {"weights": weights, "expected_counts": counts}


# ── Celery task ───────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.tasks.plan_analyzer.analyze_plan",
    bind=True,
    max_retries=2,
    default_retry_delay=15,
    acks_late=True,
)
def analyze_plan(self, plan_id: str) -> dict:
    """
    Analyze a building plan image to derive site-specific MWPI weights
    and expected structural element counts.

    Updates ProjectPlan.plan_weights, .expected_counts, .analysis_status.
    """
    db = SessionLocal()
    try:
        plan: ProjectPlan | None = db.query(ProjectPlan).filter(
            ProjectPlan.id == plan_id
        ).first()
        if plan is None:
            logger.error(f"ProjectPlan {plan_id} not found")
            return {"status": "error", "reason": "plan not found"}

        plan.analysis_status = "analyzing"
        plan.updated_at = datetime.now(timezone.utc)
        db.commit()

        # ── Download plan image ────────────────────────────────────────
        raw_bytes = download_to_bytes(
            bucket=settings.minio_raw_bucket,
            object_name=plan.plan_image_path,
        )

        result: dict | None = None
        method_used = "unknown"

        # ── 1. Try Claude vision API ───────────────────────────────────
        if settings.anthropic_api_key:
            try:
                result = _analyze_with_claude(raw_bytes)
                method_used = "claude"
                logger.info(f"Plan {plan_id} analyzed via Claude: {result}")
            except Exception as exc:
                logger.warning(f"Claude analysis failed, falling back to YOLO: {exc}")

        # ── 2. Try YOLO area analysis ──────────────────────────────────
        if result is None and not settings.mock_inference:
            try:
                img_array = np.frombuffer(raw_bytes, dtype=np.uint8)
                img_bgr   = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                if img_bgr is not None:
                    result = _analyze_with_yolo(img_bgr)
                    method_used = "yolo"
                    logger.info(f"Plan {plan_id} analyzed via YOLO: {result}")
            except Exception as exc:
                logger.warning(f"YOLO analysis failed, using defaults: {exc}")

        # ── 3. Hard defaults ───────────────────────────────────────────
        if result is None:
            result = {"weights": _DEFAULT_WEIGHTS, "expected_counts": _DEFAULT_COUNTS}
            method_used = "defaults"
            logger.info(f"Plan {plan_id} using default weights (no analysis available)")

        plan.plan_weights     = result["weights"]
        plan.expected_counts  = result["expected_counts"]
        plan.analysis_status  = "completed"
        plan.analysis_notes   = (
            f"Analyzed via {method_used}. "
            f"Weights: {result['weights']}. "
            f"Expected counts: {result['expected_counts']}."
        )
        plan.updated_at = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            f"Plan analysis complete — plan={plan_id} method={method_used} "
            f"weights={result['weights']} counts={result['expected_counts']}"
        )
        return {"status": "completed", "plan_id": plan_id, "method": method_used, **result}

    except Exception as exc:
        logger.exception(f"Plan analysis failed for {plan_id}: {exc}")
        try:
            p = db.query(ProjectPlan).filter(ProjectPlan.id == plan_id).first()
            if p:
                p.analysis_status = "failed"
                p.analysis_notes  = str(exc)
                p.updated_at = datetime.now(timezone.utc)
                db.commit()
        except Exception:
            pass
        raise self.retry(exc=exc)

    finally:
        db.close()
