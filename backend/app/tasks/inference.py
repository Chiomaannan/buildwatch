"""
inference.py — Celery task: YOLO11n inference + MWPI computation.

Pipeline:
  1. Download raw image from MinIO
  2. Decode to NumPy BGR array
  3. Run YOLO11n detection (detector.detect)
  4. Compute MWPI score (progress.compute_mwpi)
  5. Draw annotated overlay (bounding boxes + MWPI HUD)
  6. Upload annotated image to MinIO
  7. Persist InferenceResult to PostgreSQL
  8. Update Image.status → completed / failed
  9. Publish WebSocket event via Redis pub/sub
"""

import json
import logging
import time
from datetime import date, datetime, timezone

import cv2
import numpy as np
import redis

from app.config import get_settings
from app.database import SessionLocal
from app.models.image import Image, InferenceResult
from app.models.plan import ProjectPlan
from app.models.project import Project
from app.models.schedule import ScheduleMilestone
from app.services.explanation_generator import generate_explanation
from app.services.ai import detector, progress, stage_assessor
from app.services.minio_client import (
    download_to_bytes,
    get_presigned_url,
    upload_bytes,
)
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(
    name="app.tasks.inference.run_inference",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def run_inference(self, image_id: str) -> dict:
    """
    Main inference task. Triggered immediately after an image is uploaded.

    Args:
        image_id: UUID string of the Image record.
    """
    start_ms = int(time.time() * 1000)
    db = SessionLocal()

    try:
        # ── 1. Load image record ──────────────────────────────────────
        image: Image | None = db.query(Image).filter(Image.id == image_id).first()
        if image is None:
            logger.error(f"Image {image_id} not found in DB")
            return {"status": "error", "reason": "image not found"}

        image.status = "processing"
        db.commit()

        # ── 1b. Load plan analysis for plan-informed MWPI ─────────────
        # ProjectPlan (uploaded building plan) provides site-specific weights
        # and expected element counts. Falls back to fixed weights + binary
        # detection if no plan has been uploaded and analyzed yet.
        expected_components: dict[str, int] | None = None
        plan_weights: dict[str, float] | None = None

        project = db.query(Project).filter(Project.id == image.project_id).first()

        active_plan = (
            db.query(ProjectPlan)
            .filter(
                ProjectPlan.project_id == image.project_id,
                ProjectPlan.analysis_status == "completed",
            )
            .order_by(ProjectPlan.created_at.desc())
            .first()
        )
        plan_image_bytes: bytes | None = None
        if active_plan:
            plan_weights        = active_plan.plan_weights or None
            expected_components = active_plan.expected_counts or None
            logger.info(
                f"Plan-informed MWPI — weights={plan_weights} "
                f"expected={expected_components}"
            )
            # The plan image grounds the stage assessor ("grade against the
            # finished design"). Missing/corrupt plan image degrades to
            # rubric-only grading — never fails the frame.
            try:
                plan_image_bytes = download_to_bytes(
                    bucket=settings.minio_raw_bucket,
                    object_name=active_plan.plan_image_path,
                )
            except Exception as exc:
                logger.warning(f"Plan image unavailable for assessor: {exc}")
        elif project and project.bim_config:
            # Legacy fallback: check project.bim_config
            expected_components = project.bim_config.get("expected_components") or None

        # ── 1c. MWPI ratchet inputs ───────────────────────────────────
        # prior_ratios: latched per-class ratios (monotonicity — occlusion of
        # earlier elements must not lower the score). ratio_history: recent raw
        # ratios feeding the median filter that rejects one-frame false positives.
        prior_ratios: dict[str, float] | None = None
        reset_at: str | None = None
        if project and project.mwpi_state:
            prior_ratios = project.mwpi_state.get("latched_ratios") or None
            reset_at = project.mwpi_state.get("reset_at")

        history_query = (
            db.query(InferenceResult.class_ratios_raw, InferenceResult.processed_at)
            .filter(
                InferenceResult.project_id == image.project_id,
                InferenceResult.class_ratios_raw.isnot(None),
            )
        )
        if reset_at:
            # Frames before a manual ratchet reset must not feed the median
            # filter, or they would re-latch the values the reset cleared.
            history_query = history_query.filter(
                InferenceResult.processed_at > datetime.fromisoformat(reset_at)
            )
        history_rows = (
            history_query.order_by(InferenceResult.processed_at.desc())
            .limit(progress.MWPI_SMOOTH_WINDOW - 1)
            .all()
        )
        ratio_history = [row[0] for row in reversed(history_rows)]

        # ── 2. Download raw image from MinIO ──────────────────────────
        raw_bytes = download_to_bytes(
            bucket=settings.minio_raw_bucket,
            object_name=image.raw_storage_path,
        )
        img_array = np.frombuffer(raw_bytes, dtype=np.uint8)
        img_bgr = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if img_bgr is None:
            raise ValueError("Could not decode image bytes from MinIO")

        # ── 3. YOLO11n detection ──────────────────────────────────────
        finish_fractions: dict[str, float] | None = None
        stage_fractions: dict[str, float] | None = None
        if settings.mock_inference and settings.anthropic_api_key:
            # Mock detections already bake completion fractions into their
            # synthesized counts — grading them again would double-penalize,
            # so stage_fractions stays None (multiplier 1.0).
            detections, annotated_bgr, finish_fractions = _claude_site_inference(
                img_bgr, expected_components, plan_weights
            )
        else:
            detections, annotated_bgr = detector.detect(img_bgr)

        # ── 3b. Stage assessment (completion grading + wall surface state) ──
        # Real detections only. No API key → both None (multiplier-1.0 v2
        # behaviour, offline deployments keep scoring). Key configured but
        # the call failed → {} so structural raws go to 0 this frame and the
        # ratchet holds — a transient outage must not latch full credit for
        # a half-built element.
        if not settings.mock_inference and settings.anthropic_api_key:
            assessment = stage_assessor.assess_stages(
                img_bgr, detections, plan_image=plan_image_bytes
            )
            if assessment:
                stage_fractions = assessment.completion
                finish_fractions = assessment.finish_fractions
            else:
                stage_fractions = {}

        # ── 4. MWPI computation (plan-informed, confidence-weighted, monotonic) ──
        mwpi = progress.compute_mwpi(
            detections,
            expected_components=expected_components,
            plan_weights=plan_weights,
            prior_ratios=prior_ratios,
            ratio_history=ratio_history,
            finish_fractions=finish_fractions,
            stage_fractions=stage_fractions,
        )
        mwpi_score          = mwpi.score
        detected_classes    = mwpi.detected_classes
        class_contributions = mwpi.class_contributions
        detected_counts     = mwpi.detected_counts
        avg_conf = progress.avg_confidence(detections)
        if mwpi.held_classes:
            logger.info(f"Ratchet holding occluded classes: {mwpi.held_classes}")

        # ── 5. Draw MWPI overlay on annotated image ───────────────────
        annotated_bgr = _draw_mwpi_overlay(
            annotated_bgr, mwpi_score, detected_classes,
            class_contributions, detected_counts, expected_components,
            plan_weights=plan_weights,
            held_classes=mwpi.held_classes,
        )

        # ── 6. Upload annotated image to MinIO ────────────────────────
        _, encoded = cv2.imencode(".jpg", annotated_bgr, [cv2.IMWRITE_JPEG_QUALITY, 88])
        annotated_bytes = encoded.tobytes()
        annotated_path = f"annotated/{image_id}.jpg"
        upload_bytes(
            bucket=settings.minio_annotated_bucket,
            object_name=annotated_path,
            data=annotated_bytes,
        )

        # ── 7. Generate plain-English explanation via Claude ──────────────
        schedule_ctx = _get_schedule_context(db, image.project_id, mwpi_score)
        project_name = project.name if project else "Unknown Project"
        effective_weights = (
            progress.ensure_v2_weights(plan_weights)
            if plan_weights else progress.MWPI_WEIGHTS
        )

        explanation = generate_explanation(
            mwpi_score=mwpi_score,
            component_contributions=class_contributions,
            plan_weights=effective_weights,
            expected_counts=expected_components or {},
            detected_counts=dict(detected_counts),
            class_ratios=mwpi.ratios,
            held_classes=mwpi.held_classes,
            avg_confidence=avg_conf,
            planned_mwpi=schedule_ctx.get("expected_mwpi") if schedule_ctx else None,
            schedule_deviation=schedule_ctx.get("deviation") if schedule_ctx else None,
            schedule_status=schedule_ctx.get("status") if schedule_ctx else None,
            week_number=schedule_ctx.get("current_week") if schedule_ctx else None,
            project_name=project_name,
        )

        # ── 8. Persist InferenceResult ────────────────────────────────
        elapsed_ms = int(time.time() * 1000) - start_ms

        # component_counts: threshold-filtered counts that fed the MWPI score
        component_counts = dict(detected_counts)

        # component_progress: actual plan-informed contribution per class (%)
        component_progress = {
            cls: round(contrib * 100, 2)
            for cls, contrib in class_contributions.items()
        }

        result = InferenceResult(
            image_id=image_id,
            project_id=image.project_id,
            annotated_image_path=annotated_path,
            yolo_detections=detections,
            segmentation_results=[],
            component_counts=component_counts,
            progress_percentage=round(mwpi_score * 100, 2),
            component_progress=component_progress,
            mwpi_score=mwpi_score,
            detected_classes=detected_classes,
            class_ratios_raw=mwpi.raw_ratios,
            class_ratios=mwpi.ratios,
            explanation=explanation,
            processed_at=datetime.now(timezone.utc),
            processing_time_ms=elapsed_ms,
        )
        db.add(result)
        image.status = "completed"

        # Advance the project ratchet in the same transaction. Row lock + max-
        # merge means a concurrent worker can never regress a latched ratio.
        locked_project = (
            db.query(Project)
            .filter(Project.id == image.project_id)
            .with_for_update()
            .first()
        )
        if locked_project:
            state = locked_project.mwpi_state or {}
            locked_project.mwpi_state = {
                **state,
                "latched_ratios": progress.merge_latched_ratios(
                    state.get("latched_ratios"), mwpi.ratios
                ),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        db.commit()

        logger.info(
            f"Inference done — image={image_id} MWPI={mwpi_score} "
            f"classes={detected_classes} elapsed={elapsed_ms}ms"
        )

        # ── 9. Broadcast WebSocket event via Redis ────────────────────
        try:
            annotated_url = get_presigned_url(settings.minio_annotated_bucket, annotated_path)
        except Exception:
            annotated_url = None

        _publish_event(
            image.project_id,
            {
                "event": "new_inference",
                "project_id": image.project_id,
                "image_id": image_id,
                "mwpi_score": mwpi_score,
                "detected_classes": detected_classes,
                "avg_confidence": avg_conf,
                "explanation": explanation,
                "annotated_image_url": annotated_url,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return {
            "status": "completed",
            "image_id": image_id,
            "mwpi_score": mwpi_score,
            "detected_classes": detected_classes,
            "elapsed_ms": elapsed_ms,
        }

    except Exception as exc:
        logger.exception(f"Inference failed for image {image_id}: {exc}")
        try:
            image = db.query(Image).filter(Image.id == image_id).first()
            if image:
                image.status = "failed"
                result = InferenceResult(
                    image_id=image_id,
                    project_id=image.project_id,
                    error_message=str(exc),
                    processed_at=datetime.now(timezone.utc),
                    processing_time_ms=int(time.time() * 1000) - start_ms,
                )
                db.add(result)
                db.commit()
        except Exception:
            pass
        raise self.retry(exc=exc)

    finally:
        db.close()


def _claude_site_inference(
    img_bgr: np.ndarray,
    expected_components: dict[str, int] | None,
    plan_weights: dict[str, float] | None,
) -> tuple[list[dict], np.ndarray, dict[str, float] | None]:
    """
    When MOCK_INFERENCE=true and Anthropic key is available, use Claude vision
    to estimate what fraction of each structural class is built, then synthesise
    detections proportional to expected counts so compute_mwpi gets accurate
    input. Also returns finishing fractions (plastering/painting as fractions
    of the visible walls) from the same estimate, replacing the crop-based
    surface classifier that only makes sense on real detections.
    Falls back to detector.detect() (random mock, no finish data) on any error.
    """
    import base64
    import json
    import random
    import re
    import anthropic

    try:
        _, buf = cv2.imencode('.jpg', img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        b64 = base64.b64encode(buf.tobytes()).decode('utf-8')

        # Build context string from plan so Claude knows the scale
        weights = plan_weights or progress.MWPI_WEIGHTS
        plan_ctx = ""
        if expected_components:
            lines = [f"  - {cls}: {n} planned" for cls, n in expected_components.items()]
            plan_ctx = "Building plan calls for:\n" + "\n".join(lines) + "\n\n"

        prompt = (
            "You are a construction progress inspector reviewing a site photo.\n\n"
            + plan_ctx
            + "Estimate what fraction of each structural element is VISIBLY BUILT "
            "in this photo (0.0 = nothing started, 1.0 = fully complete).\n\n"
            "Rules:\n"
            "- foundation: ground slabs, footings, or base complete → 1.0 if done\n"
            "- column: concrete columns/pilasters/piers — count ALL visible including "
            "those embedded at wall edges and window/door jambs\n"
            "- wall: blockwork/masonry walls — estimate overall percentage of perimeter "
            "walls built to full height\n"
            "- roof: slabs or roof cover — 0.0 if not started\n"
            "- plastering: fraction of the VISIBLE walls that are rendered smooth "
            "(no block joints showing) — includes painted walls\n"
            "- painting: fraction of the VISIBLE walls carrying a paint/finish coat\n\n"
            "Return ONLY this JSON, no other text:\n"
            '{"foundation": <0.0-1.0>, "column": <0.0-1.0>, "wall": <0.0-1.0>, '
            '"roof": <0.0-1.0>, "plastering": <0.0-1.0>, "painting": <0.0-1.0>}'
        )

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=128,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )

        raw = response.content[0].text.strip()
        m = re.search(r'\{.*?\}', raw, re.DOTALL)
        if not m:
            raise ValueError(f"No JSON: {raw!r}")
        ratios: dict[str, float] = json.loads(m.group(0))
        logger.info(f"Claude site completion ratios: {ratios}")

        finish_fractions = {
            cls: max(0.0, min(1.0, float(ratios.get(cls, 0.0))))
            for cls in progress.FINISHING_CLASSES
        }

        # Synthesise detections: n = ceil(ratio × expected), min 1 if any progress
        h, w = img_bgr.shape[:2]
        class_map = {"foundation": 0, "column": 1, "wall": 2, "roof": 3}
        zone_y   = {"foundation": int(h * 0.7), "column": int(h * 0.2), "wall": int(h * 0.3), "roof": int(h * 0.05)}
        detections: list[dict] = []

        for cls, class_id in class_map.items():
            ratio = max(0.0, min(1.0, float(ratios.get(cls, 0.0))))
            if ratio <= 0:
                continue
            expected = (expected_components or {}).get(cls, 2)
            n = max(1, round(ratio * expected))
            bw = max(w // max(n, 4), 40)
            bh = max(h // 5, 40)
            base_y = zone_y[cls]
            for i in range(n):
                x1 = int((i / max(n, 1)) * (w - bw))
                y1 = min(base_y + (i % 2) * (bh // 3), h - bh - 1)
                detections.append({
                    "class_id": class_id,
                    "class_name": cls,
                    "confidence": round(random.uniform(0.72, 0.93), 3),
                    "bbox": [x1, y1, x1 + bw, y1 + bh],
                })

        # Draw bounding boxes on a copy of the image
        annotated = img_bgr.copy()
        cls_colors = {"foundation": (23, 117, 186), "column": (165, 95, 24), "wall": (86, 110, 15), "roof": (30, 60, 200)}
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            color = cls_colors.get(det["class_name"], (180, 180, 180))
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            label = f"{det['class_name']} {det['confidence']:.2f}"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            cv2.rectangle(annotated, (x1, y1 - lh - 4), (x1 + lw, y1), color, -1)
            cv2.putText(annotated, label, (x1, y1 - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)

        return detections, annotated, finish_fractions

    except Exception as exc:
        logger.warning(f"Claude site inference failed ({exc}) — using random mock")
        mock_detections, mock_annotated = detector.detect(img_bgr)
        return mock_detections, mock_annotated, None


def _publish_event(project_id: str, event: dict) -> None:
    """Publish inference completion event to Redis pub/sub channel."""
    try:
        r = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        r.publish(f"project:{project_id}:events", json.dumps(event))
        r.close()
    except Exception as exc:
        logger.warning(f"Redis publish failed (non-fatal): {exc}")


def _get_schedule_context(db, project_id: str, mwpi_score: float) -> dict | None:
    """
    Return schedule comparison data for the current week, or None if no schedule set.
    Finds the latest milestone whose planned_date has passed; falls back to the first
    upcoming milestone if none have passed yet.
    """
    milestones = (
        db.query(ScheduleMilestone)
        .filter(ScheduleMilestone.project_id == project_id)
        .order_by(ScheduleMilestone.week_number)
        .all()
    )
    if not milestones:
        return None

    today = date.today().isoformat()
    current = None
    for m in milestones:
        if m.planned_date <= today:
            current = m
        else:
            break

    if current is None:
        current = milestones[0]

    deviation = round(mwpi_score - current.planned_mwpi, 4)
    if deviation >= 0.0:
        status = "ON_SCHEDULE"
    elif deviation >= -0.10:
        status = "SLIGHTLY_BEHIND"
    else:
        status = "DELAYED"

    return {
        "expected_mwpi": current.planned_mwpi,
        "deviation": deviation,
        "status": status,
        "current_week": current.week_number,
    }


def _draw_mwpi_overlay(
    img: np.ndarray,
    mwpi_score: float,
    detected_classes: list[str],
    class_contributions: dict[str, float],
    detected_counts: dict[str, int],
    expected_components: dict[str, int] | None = None,
    plan_weights: dict[str, float] | None = None,
    held_classes: list[str] | None = None,
) -> np.ndarray:
    """Render a plan-informed MWPI HUD in the top-left corner of the annotated image.

    Each class line shows:
      - With BIM plan:  "column  10/20  +0.15"  (detected/expected, actual contribution)
      - Without plan:   "column  +0.30"          (binary fallback, full weight)
      - Held classes:   "foundation  0/2  +0.20 held"  (latched by the ratchet
        while occluded by later construction)
    """
    overlay = img.copy()
    h, w = img.shape[:2]
    # Wider box when plan data is shown (extra "10/20" token per line)
    has_plan = bool(expected_components)
    box_w = min(300 if has_plan else 280, w - 20)
    n_classes = max(len(detected_classes), 1)
    box_h = min(50 + n_classes * 18, h - 20)

    cv2.rectangle(overlay, (10, 10), (10 + box_w, 10 + box_h), (15, 15, 15), -1)
    cv2.addWeighted(overlay, 0.70, img, 0.30, 0, img)

    # Title
    cv2.putText(img, "BuildWatch - MWPI", (18, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.52, (200, 200, 200), 1, cv2.LINE_AA)

    # MWPI score bar
    pct = mwpi_score * 100
    bar_x, bar_y, bar_w, bar_h = 18, 38, box_w - 20, 14
    cv2.rectangle(img, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (50, 50, 50), -1)
    filled = int(bar_w * mwpi_score)
    bar_color = (0, 200, 60) if mwpi_score >= 0.7 else (0, 160, 255) if mwpi_score >= 0.4 else (60, 80, 220)
    cv2.rectangle(img, (bar_x, bar_y), (bar_x + filled, bar_y + bar_h), bar_color, -1)
    cv2.putText(img, f"MWPI: {mwpi_score:.2f}  ({pct:.0f}%)",
                (bar_x + bar_w + 6, bar_y + 11),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1, cv2.LINE_AA)

    # Per-class breakdown
    y = 68
    class_colors = {
        "foundation": (23, 117, 186), "column": (165, 95, 24),
        "wall": (86, 110, 15), "roof": (30, 60, 200),
        "plastering": (234, 51, 147), "painting": (119, 39, 219),
    }
    for cls in detected_classes:
        col        = class_colors.get(cls, (180, 180, 180))
        contrib    = class_contributions.get(cls, progress.MWPI_WEIGHTS.get(cls, 0))
        detected_n = detected_counts.get(cls, 0)
        expected_n = (expected_components or {}).get(cls)

        if expected_n:
            label = f"{cls}  {detected_n}/{expected_n}  +{contrib:.2f}"
        else:
            label = f"{cls}  +{contrib:.2f}"
        if cls in (held_classes or []):
            label += " held"

        cv2.circle(img, (22, y - 3), 4, col, -1)
        cv2.putText(img, label, (30, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (200, 200, 200), 1, cv2.LINE_AA)
        y += 18

    if not detected_classes:
        cv2.putText(img, "No milestones detected", (18, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, (120, 120, 120), 1, cv2.LINE_AA)

    return img
