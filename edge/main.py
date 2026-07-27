"""
main.py — Edge agent entry point.

Runs three scheduled jobs:
  1. presence_check_job : Captures a presence-check image every PRESENCE_INTERVAL seconds.
                          Sent with capture_type=presence_check — used for worker headcounts,
                          hidden from Gallery and the Overview slider.
  2. progress_job       : Captures a progress image every PROGRESS_INTERVAL seconds.
                          Sent with capture_type=progress — used for MWPI calculation,
                          appears in Gallery and feeds the comparison slider.
  3. upload_job         : Drains the upload buffer every UPLOAD_INTERVAL seconds.
                          Retries automatically when the network comes back.

Environment variables (set in .env):
  CAPTURE_BACKEND       = rpi | webcam | test
  PRESENCE_INTERVAL     = seconds between presence-check captures (default 600 = 10 min)
  PROGRESS_INTERVAL     = seconds between progress captures (default 3600 = 1 hour)
  UPLOAD_INTERVAL       = seconds between upload attempts (default 60)
  CAPTURE_SAVE_DIR      = local directory for raw captures (default /tmp/aic_captures)
  PROJECT_ID            = backend project UUID
  DEVICE_ID             = unique identifier for this edge device
  BACKEND_URL           = http://... backend base URL
"""

import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import schedule
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("edge_agent.log"),
    ],
)
logger = logging.getLogger("edge.main")

from buffer import enqueue, init_db, queue_size  # noqa: E402
from capture import capture_image  # noqa: E402
from preprocessor import preprocess  # noqa: E402
from uploader import upload_pending  # noqa: E402

# ── Configuration ──────────────────────────────────────────────────────
PRESENCE_INTERVAL = int(os.getenv("PRESENCE_INTERVAL", "600"))   # 10 min
PROGRESS_INTERVAL = int(os.getenv("PROGRESS_INTERVAL", "3600"))  # 1 hour
UPLOAD_INTERVAL   = int(os.getenv("UPLOAD_INTERVAL",   "60"))
CAPTURE_SAVE_DIR  = os.getenv("CAPTURE_SAVE_DIR", "/tmp/aic_captures")
PROJECT_ID        = os.getenv("PROJECT_ID", "")
DEVICE_ID         = os.getenv("DEVICE_ID", "edge-device-001")


def _capture_and_enqueue(capture_type: str) -> None:
    """
    Shared pipeline: capture → preprocess → enqueue with capture_type tag.

    capture_type is injected into the image metadata before upload so the
    backend can route presence_check images to the worker monitor task and
    progress images to the MWPI inference task.
    """
    if not PROJECT_ID:
        logger.error("PROJECT_ID is not set — skipping capture")
        return

    raw_path = capture_image(save_dir=CAPTURE_SAVE_DIR)
    if raw_path is None:
        logger.warning(f"[{capture_type}] Capture failed — skipping this cycle")
        return

    result = preprocess(raw_path)
    if not result.accepted:
        logger.warning(f"[{capture_type}] Image rejected: {result.rejection_reason}")
        Path(raw_path).unlink(missing_ok=True)
        return

    metadata = result.metadata
    metadata["capture_type"] = capture_type

    captured_at = metadata.get("captured_at", datetime.now(timezone.utc).isoformat())
    row_id = enqueue(
        filepath=result.output_path,
        project_id=PROJECT_ID,
        device_id=DEVICE_ID,
        captured_at=captured_at,
        metadata=metadata,
    )
    logger.info(
        f"[{capture_type}] Queued id={row_id} | "
        f"blur={result.blur_score:.1f} brightness={result.brightness:.1f} "
        f"size={result.file_size_bytes // 1024} KB | queue depth={queue_size()}"
    )


def presence_check_job() -> None:
    """Capture a presence-check image for worker headcount monitoring."""
    logger.info("=== Presence-check capture ===")
    _capture_and_enqueue("presence_check")


def progress_job() -> None:
    """Capture a progress image for MWPI calculation."""
    logger.info("=== Progress capture ===")
    _capture_and_enqueue("progress")


def upload_job() -> None:
    """Drain the upload buffer — retries any images that failed previously."""
    logger.debug("=== Upload job ===")
    stats = upload_pending()
    if stats["attempted"] > 0:
        logger.info(
            f"Upload: {stats['succeeded']}/{stats['attempted']} sent, "
            f"{stats['failed']} deferred"
        )


def main() -> None:
    logger.info("=== BuildWatch Edge Agent starting ===")
    logger.info(f"  device_id          = {DEVICE_ID}")
    logger.info(f"  project_id         = {PROJECT_ID or '*** NOT SET ***'}")
    logger.info(f"  presence_interval  = {PRESENCE_INTERVAL}s ({PRESENCE_INTERVAL // 60} min)")
    logger.info(f"  progress_interval  = {PROGRESS_INTERVAL}s ({PROGRESS_INTERVAL // 60} min)")
    logger.info(f"  upload_interval    = {UPLOAD_INTERVAL}s")
    logger.info(f"  capture_backend    = {os.getenv('CAPTURE_BACKEND', 'webcam')}")

    init_db()

    # Run once immediately on start so there's data right away
    progress_job()
    presence_check_job()
    upload_job()

    # Schedule recurring jobs
    schedule.every(PRESENCE_INTERVAL).seconds.do(presence_check_job)
    schedule.every(PROGRESS_INTERVAL).seconds.do(progress_job)
    schedule.every(UPLOAD_INTERVAL).seconds.do(upload_job)

    logger.info("Scheduler running. Press Ctrl+C to stop.")
    try:
        while True:
            schedule.run_pending()
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Edge agent stopped.")


if __name__ == "__main__":
    main()
