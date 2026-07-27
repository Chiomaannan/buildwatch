"""
preprocessor.py — Edge image preprocessing pipeline.

Steps applied before upload:
  1. Load image
  2. Blur detection (discard if too blurry)
  3. Brightness check (discard if too dark / over-exposed)
  4. Resize to max dimension (reduce bandwidth)
  5. JPEG compression
  6. Metadata tagging (EXIF-like dict stored alongside image)
  7. Return result with quality verdict
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Thresholds — adjust per deployment environment
BLUR_THRESHOLD = float(os.getenv("BLUR_THRESHOLD", "80.0"))       # Laplacian variance
MIN_BRIGHTNESS = float(os.getenv("MIN_BRIGHTNESS", "40.0"))        # 0-255
MAX_BRIGHTNESS = float(os.getenv("MAX_BRIGHTNESS", "230.0"))       # 0-255
MAX_DIMENSION = int(os.getenv("MAX_DIMENSION", "1280"))            # px
JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "82"))                # 0-100


@dataclass
class PreprocessResult:
    accepted: bool
    output_path: str = ""
    rejection_reason: str = ""
    metadata: dict = field(default_factory=dict)
    original_size: tuple[int, int] = (0, 0)
    processed_size: tuple[int, int] = (0, 0)
    blur_score: float = 0.0
    brightness: float = 0.0
    file_size_bytes: int = 0


def preprocess(image_path: str, output_path: str | None = None) -> PreprocessResult:
    """
    Run the full preprocessing pipeline on a single image.

    Args:
        image_path:  Path to the raw captured image.
        output_path: Where to write the processed image.
                     Defaults to overwriting the input file.

    Returns:
        PreprocessResult with quality verdict and metadata.
    """
    if output_path is None:
        output_path = image_path

    # ── Load ──────────────────────────────────────────────────────────
    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        return PreprocessResult(accepted=False, rejection_reason="Cannot read image file")

    original_h, original_w = img_bgr.shape[:2]
    result = PreprocessResult(accepted=True, original_size=(original_w, original_h))

    # ── Blur detection ────────────────────────────────────────────────
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()
    result.blur_score = round(blur_score, 2)

    if blur_score < BLUR_THRESHOLD:
        return PreprocessResult(
            accepted=False,
            rejection_reason=f"Too blurry (score={blur_score:.1f} < {BLUR_THRESHOLD})",
            blur_score=blur_score,
        )

    # ── Brightness check ──────────────────────────────────────────────
    brightness = float(np.mean(gray))
    result.brightness = round(brightness, 2)

    if brightness < MIN_BRIGHTNESS:
        return PreprocessResult(
            accepted=False,
            rejection_reason=f"Too dark (brightness={brightness:.1f})",
            blur_score=blur_score,
            brightness=brightness,
        )
    if brightness > MAX_BRIGHTNESS:
        return PreprocessResult(
            accepted=False,
            rejection_reason=f"Over-exposed (brightness={brightness:.1f})",
            blur_score=blur_score,
            brightness=brightness,
        )

    # ── Auto brightness/contrast normalisation (CLAHE) ───────────────
    lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
    l_ch, a_ch, b_ch = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l_ch = clahe.apply(l_ch)
    img_bgr = cv2.cvtColor(cv2.merge([l_ch, a_ch, b_ch]), cv2.COLOR_LAB2BGR)

    # ── Resize (keep aspect ratio) ────────────────────────────────────
    h, w = img_bgr.shape[:2]
    if max(h, w) > MAX_DIMENSION:
        scale = MAX_DIMENSION / max(h, w)
        new_w, new_h = int(w * scale), int(h * scale)
        img_bgr = cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

    processed_h, processed_w = img_bgr.shape[:2]
    result.processed_size = (processed_w, processed_h)

    # ── Save compressed JPEG ──────────────────────────────────────────
    cv2.imwrite(output_path, img_bgr, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    result.output_path = output_path
    result.file_size_bytes = os.path.getsize(output_path)

    # ── Build metadata dict (attached to upload payload) ─────────────
    result.metadata = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "blur_score": result.blur_score,
        "brightness": result.brightness,
        "original_width": original_w,
        "original_height": original_h,
        "processed_width": processed_w,
        "processed_height": processed_h,
        "jpeg_quality": JPEG_QUALITY,
        "file_size_bytes": result.file_size_bytes,
    }

    logger.info(
        f"Preprocessed {os.path.basename(image_path)} | "
        f"blur={blur_score:.1f} brightness={brightness:.1f} "
        f"size={processed_w}x{processed_h} ({result.file_size_bytes // 1024} KB)"
    )
    return result
