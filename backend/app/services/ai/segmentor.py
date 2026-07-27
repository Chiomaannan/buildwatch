"""
segmentor.py — Mask R-CNN instance segmentation service.

Uses torchvision's pre-trained MaskRCNN-ResNet50-FPN-v2 model
(trained on MS-COCO) for pixel-level instance segmentation.

After fine-tuning on a labelled construction dataset, replace the
model loading logic with your custom checkpoint path.

Output per detected instance:
  {
      class_id:    int,
      class_name:  str,
      construction_label: str,
      score:       float,
      bbox:        [x1, y1, x2, y2],
      mask_area:   int,          # pixel count inside mask
      polygon:     [[x, y], ...]  # simplified contour
  }
"""

import logging
from functools import lru_cache
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# COCO class names (91 classes, index 0 = background)
COCO_CLASSES = [
    "__background__", "person", "bicycle", "car", "motorcycle", "airplane",
    "bus", "train", "truck", "boat", "traffic light", "fire hydrant", "N/A",
    "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse",
    "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "N/A", "backpack",
    "umbrella", "N/A", "N/A", "handbag", "tie", "suitcase", "frisbee", "skis",
    "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "N/A", "wine glass",
    "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich",
    "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake",
    "chair", "couch", "potted plant", "bed", "N/A", "dining table", "N/A",
    "N/A", "toilet", "N/A", "tv", "laptop", "mouse", "remote", "keyboard",
    "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator",
    "N/A", "book", "clock", "vase", "scissors", "teddy bear", "hair drier",
    "toothbrush",
]

CONSTRUCTION_ALIASES: dict[str, str] = {
    "person":        "worker",
    "truck":         "truck",
    "car":           "vehicle",
    "bench":         "beam",
    "chair":         "scaffolding",
    "dining table":  "slab",
    "bottle":        "column",
}

SCORE_THRESHOLD = 0.60          # minimum mask confidence
MAX_MASKS = 30                   # cap for annotation performance


@lru_cache(maxsize=1)
def _load_model():
    """Load and cache the Mask R-CNN model."""
    import torch
    from torchvision.models.detection import (
        MaskRCNN_ResNet50_FPN_V2_Weights,
        maskrcnn_resnet50_fpn_v2,
    )

    logger.info("Loading Mask R-CNN (ResNet50-FPN-v2) …")
    weights = MaskRCNN_ResNet50_FPN_V2_Weights.DEFAULT
    model = maskrcnn_resnet50_fpn_v2(weights=weights)
    model.eval()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    logger.info(f"Mask R-CNN loaded on {device}")
    return model, device


def segment(
    image_bgr: np.ndarray,
    annotated_base: np.ndarray | None = None,
) -> tuple[list[dict[str, Any]], np.ndarray]:
    """
    Run Mask R-CNN on a BGR image.

    Args:
        image_bgr:      Input image (H x W x 3, BGR).
        annotated_base: If provided, masks are drawn on top of this image
                        (e.g., already has YOLO boxes from detector.py).
                        Defaults to a copy of image_bgr.

    Returns:
        results:    List of per-instance segmentation dicts.
        annotated:  BGR image with coloured mask overlays drawn.
    """
    import torch
    from torchvision.transforms.functional import to_tensor

    model, device = _load_model()

    # Convert BGR → RGB tensor [1, 3, H, W] normalised to [0, 1]
    image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    img_tensor = to_tensor(image_rgb).unsqueeze(0).to(device)

    with torch.no_grad():
        predictions = model(img_tensor)[0]

    scores = predictions["scores"].cpu().numpy()
    labels = predictions["labels"].cpu().numpy()
    masks = predictions["masks"].cpu().numpy()     # [N, 1, H, W], float32
    boxes = predictions["boxes"].cpu().numpy()

    canvas = (annotated_base if annotated_base is not None else image_bgr).copy()
    results: list[dict[str, Any]] = []

    count = 0
    for score, label, mask, box in zip(scores, labels, masks, boxes):
        if score < SCORE_THRESHOLD:
            continue
        if count >= MAX_MASKS:
            break
        count += 1

        class_name = COCO_CLASSES[label] if label < len(COCO_CLASSES) else str(label)
        construction_label = CONSTRUCTION_ALIASES.get(class_name, class_name)
        binary_mask = (mask[0] > 0.5).astype(np.uint8)   # H x W
        mask_area = int(binary_mask.sum())

        # Simplified polygon contour
        contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        polygon: list[list[int]] = []
        if contours:
            epsilon = 0.01 * cv2.arcLength(contours[0], True)
            approx = cv2.approxPolyDP(contours[0], epsilon, True)
            polygon = approx.reshape(-1, 2).tolist()

        results.append(
            {
                "class_id": int(label),
                "class_name": class_name,
                "construction_label": construction_label,
                "score": round(float(score), 3),
                "bbox": [int(v) for v in box],
                "mask_area": mask_area,
                "polygon": polygon,
            }
        )

        # Draw semi-transparent coloured mask
        color_rgb = _instance_color(count)
        color_bgr = (color_rgb[2], color_rgb[1], color_rgb[0])
        overlay = canvas.copy()
        overlay[binary_mask == 1] = color_bgr
        cv2.addWeighted(overlay, 0.45, canvas, 0.55, 0, canvas)

        # Contour outline
        cv2.drawContours(canvas, contours, -1, color_bgr, 1)

    logger.info(f"Mask R-CNN segmented {len(results)} instance(s)")
    return results, canvas


def _instance_color(idx: int) -> tuple[int, int, int]:
    """Return a distinct RGB colour for each instance index."""
    colors = [
        (230, 25,  75),  (60,  180, 75),  (255, 225, 25),
        (0,   130, 200), (245, 130, 48),  (145, 30,  180),
        (70,  240, 240), (240, 50,  230), (210, 245, 60),
        (250, 190, 212), (0,   128, 128), (220, 190, 255),
        (170, 110, 40),  (255, 250, 200), (128, 0,   0),
        (170, 255, 195), (128, 128, 0),   (255, 215, 180),
        (0,   0,   128), (128, 128, 128),
    ]
    return colors[idx % len(colors)]
