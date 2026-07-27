"""
stage_assessor.py — per-class completion grading + wall surface state,
in one Claude vision call per capture.

Detection answers "is there a roof?"; the score needs "how much roof?" — a
bare truss frame and a fully covered roof both detect as `roof` at high
confidence. This module grades the completion of each structural class 0–1
and classifies wall surface state (plastering/painting), sending:

  1. The project's building plan image (architectural plan / elevation / 3D
     render), when one has been uploaded — completion is graded RELATIVE to
     the finished design instead of generic rules alone.
  2. The full site frame (downscaled) — context for structural grading.
  3. Up to MAX_WALL_CROPS wall crops — surface-state labels:
        unplastered — exposed blockwork, visible block joints
        plastered   — smooth render, no finish coat
        painted     — a paint/finish coat over the render

Grading is of the completion state of VISIBLE elements, not building-wide
extent — extent is already captured by detection ratios / expected counts in
progress.compute_mwpi, and grading extent here would double-penalize.

Consumed by progress.compute_mwpi: `completion` multiplies into structural
raw ratios (stage_fractions), `finish_fractions` feeds the finishing classes.
"""

import base64
import json
import logging
import re
from dataclasses import dataclass

import cv2
import numpy as np

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Same fast vision model used for mock site inference — grading against a
# rubric doesn't need a larger model, and this runs on every capture.
ASSESSOR_MODEL = "claude-haiku-4-5-20251001"

# Ignore wall detections below this confidence (matches MWPI_CONF_FLOOR).
WALL_CONF_FLOOR = 0.25
# Cost/latency bound: classify at most this many wall crops (the full frame
# already provides context, so fewer crops than the old finish classifier).
MAX_WALL_CROPS = 4
# Pad crops by this fraction of the bbox so surface texture context survives
# tight YOLO boxes.
CROP_PAD = 0.08
# Long-edge cap for the full frame and plan image sent to Claude.
FRAME_LONG_EDGE = 1024

STRUCTURAL_CLASSES = ("foundation", "column", "wall", "roof")
_VALID_STATES = ("unplastered", "plastered", "painted")


@dataclass
class StageAssessment:
    """One frame's completion grading and wall surface classification."""

    completion: dict[str, float]        # {structural class: 0–1 completion}
    finish_fractions: dict[str, float]  # {"plastering": frac, "painting": frac}
    wall_states: list[str]              # per-crop label, detection order


def assess_stages(
    img_bgr: np.ndarray,
    detections: list[dict],
    plan_image: bytes | None = None,
) -> StageAssessment | None:
    """
    Grade the completion of each structural class and the surface state of
    detected walls. Returns None when no API key is configured or the call
    fails — callers decide whether that means "hold" or "v2 behaviour".
    """
    if not settings.anthropic_api_key:
        return None

    walls = sorted(
        (
            d for d in detections
            if d.get("class_name", "").lower() == "wall"
            and d.get("confidence", 0.0) >= WALL_CONF_FLOOR
        ),
        key=lambda d: d.get("confidence", 0.0),
        reverse=True,
    )[:MAX_WALL_CROPS]
    crops = [c for c in (_encode_crop(img_bgr, d["bbox"]) for d in walls) if c]

    detected = sorted({
        d.get("class_name", "").lower()
        for d in detections
        if d.get("class_name", "").lower() in STRUCTURAL_CLASSES
    })

    parsed = _assess_with_claude(
        frame_b64=_encode_frame(img_bgr),
        crops_b64=crops,
        detected_classes=detected,
        plan_image=plan_image,
    )
    if parsed is None:
        return None

    completion = {
        cls: max(0.0, min(1.0, float(parsed.get("completion", {}).get(cls, 0.0))))
        for cls in STRUCTURAL_CLASSES
    }

    states = [s for s in parsed.get("walls", []) if s in _VALID_STATES]
    if crops and len(states) != len(crops):
        logger.warning(
            f"Stage assessor returned {len(states)} wall labels for "
            f"{len(crops)} crops — ignoring surface states this frame"
        )
        states = []
    n = len(states)
    if n:
        plastered = sum(1 for s in states if s in ("plastered", "painted"))
        painted = sum(1 for s in states if s == "painted")
        finish = {
            "plastering": round(plastered / n, 4),
            "painting": round(painted / n, 4),
        }
    else:
        finish = {"plastering": 0.0, "painting": 0.0}

    result = StageAssessment(
        completion=completion, finish_fractions=finish, wall_states=states
    )
    logger.info(
        f"Stage assessment — completion={completion} walls={states} "
        f"finish={finish} plan_image={'yes' if plan_image else 'no'}"
    )
    return result


def _encode_frame(img_bgr: np.ndarray) -> str:
    """Downscale the full frame to FRAME_LONG_EDGE and return base64 JPEG."""
    h, w = img_bgr.shape[:2]
    scale = FRAME_LONG_EDGE / max(h, w)
    if scale < 1.0:
        img_bgr = cv2.resize(img_bgr, (int(w * scale), int(h * scale)))
    _, buf = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def _encode_plan(plan_image: bytes) -> tuple[str, str] | None:
    """Decode, downscale, and re-encode the plan image. None if unreadable."""
    arr = np.frombuffer(plan_image, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    return _encode_frame(img), "image/jpeg"


def _encode_crop(img_bgr: np.ndarray, bbox: list) -> str | None:
    """Crop a padded bbox and return it as base64 JPEG, or None if degenerate."""
    h, w = img_bgr.shape[:2]
    x1, y1, x2, y2 = (int(v) for v in bbox)
    pad_x = int((x2 - x1) * CROP_PAD)
    pad_y = int((y2 - y1) * CROP_PAD)
    x1, y1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
    x2, y2 = min(w, x2 + pad_x), min(h, y2 + pad_y)
    if x2 - x1 < 16 or y2 - y1 < 16:
        return None
    crop = img_bgr[y1:y2, x1:x2]
    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        return None
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def _img_block(b64: str, media_type: str = "image/jpeg") -> dict:
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": b64},
    }


def _assess_with_claude(
    frame_b64: str,
    crops_b64: list[str],
    detected_classes: list[str],
    plan_image: bytes | None,
) -> dict | None:
    """One vision request grading completion + labelling wall crops."""
    import anthropic

    content: list[dict] = []

    plan_note = ""
    if plan_image:
        encoded = _encode_plan(plan_image)
        if encoded:
            content.append({
                "type": "text",
                "text": "TARGET DESIGN — the finished building (architectural "
                        "plan, elevation, or 3D render):",
            })
            content.append(_img_block(*encoded))
            plan_note = (
                "Grade completion RELATIVE to the TARGET DESIGN above: compare "
                "the roof shape/coverage, wall extents and heights, and storeys "
                "the design calls for against what has actually been built.\n"
            )

    content.append({"type": "text", "text": "SITE PHOTO — the building today:"})
    content.append(_img_block(frame_b64))

    for i, b64 in enumerate(crops_b64):
        content.append({"type": "text", "text": f"Wall crop {i + 1}:"})
        content.append(_img_block(b64))

    n = len(crops_b64)
    walls_line = (
        f'"walls": [{n} labels in crop order, each one of '
        '"unplastered"|"plastered"|"painted"]'
        if n else '"walls": []'
    )
    detected_note = (
        f"The site detector found these element types: {', '.join(detected_classes)}.\n"
        if detected_classes else ""
    )

    content.append({
        "type": "text",
        "text": (
            "You are grading construction progress on a residential site in "
            "Ghana.\n\n"
            + plan_note
            + detected_note
            + "For each element type, grade how COMPLETE the visible elements "
            "are (0.0–1.0). Grade the state of what is visible, NOT how much "
            "of the whole building exists — element counts are measured "
            "separately.\n"
            "- foundation: footings/base slab state (1.0 = complete or built "
            "over)\n"
            "- column: visible columns cast to full height → 1.0; partial "
            "lifts → fraction of height\n"
            "- wall: blockwork height relative to wall-plate/roof level — "
            "use door/window lintels and block courses as the datum. Window "
            "and door OPENINGS are NOT incompleteness (frames and glazing "
            "are finishing work), and unfilled gables are not deductions. "
            "RULE: if roofing has STARTED in any form (wall plate, trusses, "
            "or cover visible on the walls), the blockwork must already be "
            "complete — grade wall exactly 1.0, never 0.8 or 0.9. Grade "
            "below 1.0 only when there is NO roofing yet and blockwork is "
            "still visibly rising (e.g. half-height courses ≈ 0.5)\n"
            "- roof: 0.0 none · 0.2 ring beam/wall plate only · 0.5 trusses/"
            "frame erected, no cover · 0.8 partially sheeted · 1.0 fully "
            "covered\n"
            "Use 0.0 for element types that are absent or not visible.\n\n"
            "Also classify the surface state of each wall crop:\n"
            '- "unplastered": bare blockwork — block joints/mortar lines '
            "visible\n"
            '- "plastered": rendered smooth, no finish coat\n'
            '- "painted": paint/finish coat over the render\n'
            "If a wall is partially finished, choose the state covering the "
            "majority of its surface.\n\n"
            "Return ONLY this JSON, no other text:\n"
            '{"completion": {"foundation": <0-1>, "column": <0-1>, '
            '"wall": <0-1>, "roof": <0-1>}, ' + walls_line + "}"
        ),
    })

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=ASSESSOR_MODEL,
            max_tokens=384,
            messages=[{"role": "user", "content": content}],
        )
        raw = response.content[0].text.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            raise ValueError(f"No JSON in response: {raw!r}")
        return json.loads(m.group(0))
    except Exception as exc:
        logger.warning(f"Stage assessment failed (non-fatal): {exc}")
        return None
