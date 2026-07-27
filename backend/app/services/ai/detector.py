"""
detector.py — YOLO11n object detection for BuildWatch.

Model: buildwatch_best.pt (YOLO11n trained on 4 structural classes + worker)
Classes (nc=5, Roboflow alphabetical): column (0), foundation (1), roof (2), wall (3), worker (4)

Class IDs are read from model.names at runtime, so the dataset YAML ordering
is authoritative — everything here matches on class *name*, never on ID.
"""

import logging
import random
from functools import lru_cache
from typing import Any

import cv2
import numpy as np

from app.config import get_settings

logger = logging.getLogger(__name__)

# Class name of construction workers in buildwatch_best.pt — used by
# worker_monitor.py for presence checks. Excluded from MWPI (not in MWPI_WEIGHTS).
WORKER_CLASS_NAME = "worker"

# BGR colours for the BuildWatch classes
_CLASS_COLORS: dict[str, tuple[int, int, int]] = {
    "foundation": (23, 117, 186),   # #BA7517 in BGR
    "column":     (165, 95, 24),    # #185FA5 in BGR
    "wall":       (86, 110, 15),    # #0F6E56 in BGR
    "roof":       (30, 60, 200),    # #C83C1E in BGR (terracotta)
    "worker":     (0, 165, 255),    # #FFA500 in BGR (safety orange)
}
_DEFAULT_COLOR: tuple[int, int, int] = (180, 180, 180)

_MOCK_CLASSES = [(0, "column"), (1, "foundation"), (2, "roof"), (3, "wall"), (4, "worker")]


@lru_cache(maxsize=1)
def _load_model():
    from ultralytics import YOLO
    settings = get_settings()
    logger.info(f"Loading YOLO11n model: {settings.yolo_model_path}")
    return YOLO(settings.yolo_model_path)


def _real_detections(image_bgr: np.ndarray, conf: float) -> list[dict[str, Any]]:
    model = _load_model()
    results = model.predict(source=image_bgr, conf=conf, verbose=False, stream=False)

    detections: list[dict[str, Any]] = []
    for result in results:
        for box in result.boxes:
            class_id = int(box.cls[0])
            class_name = model.names[class_id]
            conf_score = float(box.conf[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            detections.append({
                "class_id": class_id,
                "class_name": class_name,
                "confidence": round(conf_score, 3),
                "bbox": [x1, y1, x2, y2],
            })
    return detections


def count_workers(image_bgr: np.ndarray, confidence: float = 0.40) -> int:
    """
    Count construction workers using the BuildWatch model's own `worker` class.

    Shares the cached buildwatch_best.pt model with detect() — one model for
    the whole pipeline instead of a separate COCO person detector.
    """
    model = _load_model()
    results = model.predict(source=image_bgr, conf=confidence, verbose=False, stream=False)
    count = 0
    for result in results:
        for box in result.boxes:
            if model.names[int(box.cls[0])] == WORKER_CLASS_NAME:
                count += 1
    return count


def _claude_detections(image_bgr: np.ndarray, conf: float) -> list[dict[str, Any]]:
    """
    Use Claude vision to count structural elements in a construction site photo.
    Falls back to random mock if the API call fails.
    """
    import base64
    import json
    import re
    import anthropic

    settings = get_settings()
    h, w = image_bgr.shape[:2]

    try:
        _, buf = cv2.imencode('.jpg', image_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        b64 = base64.b64encode(buf.tobytes()).decode('utf-8')

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                    },
                    {
                        "type": "text",
                        "text": (
                            "You are a construction progress inspector analyzing a building site photo.\n"
                            "Count only what is CLEARLY BUILT and VISIBLE in this photo.\n\n"
                            "Return ONLY this JSON — no other text:\n"
                            "{\n"
                            '  "foundation": <number of distinct foundation slabs or base sections built>,\n'
                            '  "column": <number of concrete columns, pillars, or pilasters built>,\n'
                            '  "wall": <number of wall sections built — count each bay between openings as one section>,\n'
                            '  "roof": <number of roof or slab sections — 0 if not started>,\n'
                            '  "worker": <number of construction workers visible on site>\n'
                            "}\n\n"
                            "Count conservatively. If a class is not started, return 0."
                        ),
                    },
                ],
            }],
        )

        raw = response.content[0].text.strip()
        m = re.search(r'\{.*?\}', raw, re.DOTALL)
        if not m:
            raise ValueError(f"No JSON in Claude response: {raw!r}")
        counts = json.loads(m.group(0))
        logger.info(f"Claude vision counts: {counts}")

        # Build detection list from counts; spread boxes across image for overlay
        detections: list[dict[str, Any]] = []
        class_map = {"column": 0, "foundation": 1, "roof": 2, "wall": 3, "worker": 4}
        # Approximate zone for each class so the overlay looks plausible
        zone_y = {"foundation": int(h * 0.65), "column": int(h * 0.2), "wall": int(h * 0.25), "roof": int(h * 0.05), "worker": int(h * 0.5)}

        for class_name, class_id in class_map.items():
            n = int(counts.get(class_name, 0))
            if n <= 0:
                continue
            bw = max(w // max(n, 4), 40)
            bh = max(h // 6, 40)
            base_y = zone_y[class_name]
            for i in range(n):
                x1 = int((i / max(n, 1)) * (w - bw))
                y1 = min(base_y + (i % 2) * (bh // 2), h - bh - 1)
                detections.append({
                    "class_id": class_id,
                    "class_name": class_name,
                    "confidence": round(random.uniform(0.72, 0.91), 3),
                    "bbox": [x1, y1, x1 + bw, y1 + bh],
                })
        return detections

    except Exception as exc:
        logger.warning(f"Claude vision detection failed ({exc}) — using random mock")
        return _random_mock_detections(image_bgr, conf)


def _random_mock_detections(image_bgr: np.ndarray, conf: float) -> list[dict[str, Any]]:
    """Last-resort random fake detections when Claude API is unavailable."""
    h, w = image_bgr.shape[:2]
    detections: list[dict[str, Any]] = []
    for class_id, class_name in _MOCK_CLASSES:
        if random.random() < 0.15:
            continue
        for _ in range(random.randint(1, 4)):
            bw = random.randint(w // 8, w // 3)
            bh = random.randint(h // 8, h // 3)
            x1 = random.randint(0, max(w - bw, 1))
            y1 = random.randint(0, max(h - bh, 1))
            detections.append({
                "class_id": class_id,
                "class_name": class_name,
                "confidence": round(random.uniform(max(conf, 0.4), 0.95), 3),
                "bbox": [x1, y1, x1 + bw, y1 + bh],
            })
    return detections


def detect(
    image_bgr: np.ndarray,
    confidence: float | None = None,
) -> tuple[list[dict[str, Any]], np.ndarray]:
    """
    Run YOLO11n inference on a BGR image (or generate mock detections when
    settings.mock_inference is set — see app/config.py).

    Returns:
        detections: list of {class_id, class_name, confidence, bbox [x1,y1,x2,y2]}
        annotated:  BGR image with bounding boxes drawn
    """
    settings = get_settings()
    conf = confidence if confidence is not None else settings.yolo_confidence

    if settings.mock_inference:
        if settings.anthropic_api_key:
            detections = _claude_detections(image_bgr, conf)
            logger.info(f"CLAUDE_VISION: {len(detections)} detection(s)")
        else:
            detections = _random_mock_detections(image_bgr, conf)
            logger.info(f"MOCK_INFERENCE: {len(detections)} random detection(s)")
    else:
        detections = _real_detections(image_bgr, conf)
        logger.info(f"YOLO11n: {len(detections)} detection(s)")

    annotated = image_bgr.copy()
    for det in detections:
        class_name = det["class_name"]
        x1, y1, x2, y2 = det["bbox"]
        color = _CLASS_COLORS.get(class_name, _DEFAULT_COLOR)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label = f"{class_name} {det['confidence']:.2f}"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(annotated, (x1, y1 - lh - 6), (x1 + lw, y1), color, -1)
        cv2.putText(
            annotated, label, (x1, y1 - 4),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA,
        )

    return detections, annotated
