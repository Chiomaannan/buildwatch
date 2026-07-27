"""
capture.py — Image capture abstraction.

Supports three backends:
  - 'rpi'     : Raspberry Pi camera via picamera2 (on-device only)
  - 'webcam'  : USB / built-in webcam via OpenCV
  - 'test'    : Reads images from a local test directory (development)

Set CAPTURE_BACKEND in .env to choose.
"""

import os
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2

logger = logging.getLogger(__name__)

CAPTURE_BACKEND = os.getenv("CAPTURE_BACKEND", "webcam")  # rpi | webcam | test
TEST_IMAGE_DIR = os.getenv("TEST_IMAGE_DIR", "./test_images")


def capture_image(save_dir: str = "/tmp/aic_captures") -> str | None:
    """
    Capture one image and save it to `save_dir`.

    Returns the file path on success, None on failure.
    """
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"capture_{timestamp}.jpg"
    filepath = os.path.join(save_dir, filename)

    backend = CAPTURE_BACKEND.lower()

    if backend == "rpi":
        return _capture_rpi(filepath)
    elif backend == "webcam":
        return _capture_webcam(filepath)
    elif backend == "test":
        return _capture_test(filepath)
    else:
        logger.error(f"Unknown CAPTURE_BACKEND: {backend}")
        return None


def _capture_rpi(filepath: str) -> str | None:
    """Capture using Raspberry Pi camera module via picamera2."""
    try:
        from picamera2 import Picamera2  # type: ignore

        cam = Picamera2()
        config = cam.create_still_configuration(
            main={"size": (1920, 1080)},
            lores={"size": (640, 480)},
            display="lores",
        )
        cam.configure(config)
        cam.start()
        time.sleep(2)  # warm-up
        cam.capture_file(filepath)
        cam.stop()
        cam.close()
        logger.info(f"RPi capture saved: {filepath}")
        return filepath
    except Exception as exc:
        logger.error(f"RPi capture failed: {exc}")
        return None


def _capture_webcam(filepath: str, device_index: int = 0) -> str | None:
    """Capture a single frame from a USB/built-in webcam."""
    cap = cv2.VideoCapture(device_index)
    if not cap.isOpened():
        logger.error(f"Cannot open webcam device {device_index}")
        return None

    # Allow auto-exposure to settle
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    for _ in range(5):
        cap.read()

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        logger.error("Failed to read frame from webcam")
        return None

    cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    logger.info(f"Webcam capture saved: {filepath}")
    return filepath


def _capture_test(filepath: str) -> str | None:
    """
    Pull the next image from TEST_IMAGE_DIR in round-robin order.
    Useful for development without a physical camera.
    """
    test_dir = Path(TEST_IMAGE_DIR)
    if not test_dir.exists():
        logger.error(f"Test image directory not found: {test_dir}")
        return None

    images = sorted(test_dir.glob("*.jpg")) + sorted(test_dir.glob("*.png"))
    if not images:
        logger.error(f"No images found in {test_dir}")
        return None

    # Use a simple index file to cycle through images
    idx_file = test_dir / ".capture_index"
    idx = int(idx_file.read_text()) if idx_file.exists() else 0
    source = images[idx % len(images)]
    idx_file.write_text(str(idx + 1))

    import shutil
    shutil.copy(str(source), filepath)
    logger.info(f"Test capture copied from {source.name} → {filepath}")
    return filepath
