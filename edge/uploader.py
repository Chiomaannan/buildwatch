"""
uploader.py — Upload images from the local buffer to the backend API.

Features:
  - Multipart POST with image + metadata JSON
  - Exponential back-off on connection errors
  - Drains the entire buffer queue on each call
  - Deletes local image file after confirmed upload (optional)
"""

import json
import logging
import os
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from buffer import get_pending, mark_failed, mark_success, queue_size

logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
UPLOAD_ENDPOINT = f"{BACKEND_URL}/api/v1/upload"
API_KEY = os.getenv("API_KEY", "")          # optional bearer token
DELETE_AFTER_UPLOAD = os.getenv("DELETE_AFTER_UPLOAD", "true").lower() == "true"
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))   # seconds


def _build_session() -> requests.Session:
    """Build a requests session with retry on transient HTTP errors."""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    if API_KEY:
        session.headers.update({"Authorization": f"Bearer {API_KEY}"})
    return session


def upload_pending() -> dict:
    """
    Upload all queued images to the backend.

    Returns a summary dict: {attempted, succeeded, failed}.
    """
    pending = get_pending(limit=20)
    if not pending:
        logger.debug("Upload queue is empty")
        return {"attempted": 0, "succeeded": 0, "failed": 0}

    logger.info(f"Starting upload run — {len(pending)} item(s) in queue")
    session = _build_session()
    stats = {"attempted": 0, "succeeded": 0, "failed": 0}

    for record in pending:
        stats["attempted"] += 1
        row_id = record["id"]
        filepath = record["filepath"]

        if not Path(filepath).exists():
            logger.warning(f"File missing, removing record {row_id}: {filepath}")
            mark_success(row_id)   # treat as done to clear the stale entry
            continue

        try:
            with open(filepath, "rb") as img_file:
                files = {"image": (Path(filepath).name, img_file, "image/jpeg")}
                data = {
                    "project_id": record["project_id"],
                    "device_id": record["device_id"],
                    "captured_at": record["captured_at"],
                    "metadata": record.get("metadata") or "{}",
                }
                resp = session.post(
                    UPLOAD_ENDPOINT,
                    files=files,
                    data=data,
                    timeout=REQUEST_TIMEOUT,
                )

            if resp.status_code in (200, 201):
                mark_success(row_id)
                stats["succeeded"] += 1
                logger.info(
                    f"Uploaded record {row_id} → {resp.json().get('image_id', '?')}"
                )
                if DELETE_AFTER_UPLOAD:
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
            else:
                mark_failed(row_id)
                stats["failed"] += 1
                logger.error(
                    f"Upload rejected for record {row_id}: "
                    f"HTTP {resp.status_code} — {resp.text[:200]}"
                )

        except requests.exceptions.ConnectionError:
            mark_failed(row_id)
            stats["failed"] += 1
            logger.warning(f"No connection — record {row_id} deferred")
            break  # stop trying if the network is down

        except Exception as exc:
            mark_failed(row_id)
            stats["failed"] += 1
            logger.error(f"Unexpected error uploading record {row_id}: {exc}")

    remaining = queue_size()
    logger.info(
        f"Upload run complete — attempted={stats['attempted']} "
        f"succeeded={stats['succeeded']} failed={stats['failed']} "
        f"remaining_in_queue={remaining}"
    )
    return stats
