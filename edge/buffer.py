"""
buffer.py — SQLite-backed offline queue.

When the cellular link is unavailable, images are queued here and
retried automatically on the next upload attempt.

Schema:
  pending_uploads(
      id           INTEGER PRIMARY KEY,
      filepath     TEXT NOT NULL,
      project_id   TEXT NOT NULL,
      device_id    TEXT NOT NULL,
      captured_at  TEXT NOT NULL,
      metadata     TEXT,          -- JSON blob
      attempts     INTEGER DEFAULT 0,
      last_attempt TEXT,
      created_at   TEXT NOT NULL
  )
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

logger = logging.getLogger(__name__)

DB_PATH = Path("./aic_buffer.sqlite3")
MAX_ATTEMPTS = 10  # drop record after this many failed uploads


@contextmanager
def _conn() -> Generator[sqlite3.Connection, None, None]:
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db() -> None:
    """Create the buffer table if it doesn't exist."""
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS pending_uploads (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                filepath     TEXT    NOT NULL,
                project_id   TEXT    NOT NULL,
                device_id    TEXT    NOT NULL,
                captured_at  TEXT    NOT NULL,
                metadata     TEXT,
                attempts     INTEGER NOT NULL DEFAULT 0,
                last_attempt TEXT,
                created_at   TEXT    NOT NULL
            )
        """)
    logger.debug("Buffer DB initialised")


def enqueue(
    filepath: str,
    project_id: str,
    device_id: str,
    captured_at: str,
    metadata: dict | None = None,
) -> int:
    """Add a captured image to the upload queue. Returns the row id."""
    with _conn() as con:
        cur = con.execute(
            """
            INSERT INTO pending_uploads
                (filepath, project_id, device_id, captured_at, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                filepath,
                project_id,
                device_id,
                captured_at,
                json.dumps(metadata or {}),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        row_id = cur.lastrowid
    logger.info(f"Queued image for upload: id={row_id} file={filepath}")
    return row_id


def get_pending(limit: int = 10) -> list[dict]:
    """Return up to `limit` items that haven't exceeded MAX_ATTEMPTS."""
    with _conn() as con:
        rows = con.execute(
            """
            SELECT * FROM pending_uploads
            WHERE attempts < ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (MAX_ATTEMPTS, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_success(row_id: int) -> None:
    """Remove a successfully uploaded record from the queue."""
    with _conn() as con:
        con.execute("DELETE FROM pending_uploads WHERE id = ?", (row_id,))
    logger.debug(f"Buffer record {row_id} removed after successful upload")


def mark_failed(row_id: int) -> None:
    """Increment attempt counter and update last_attempt timestamp."""
    with _conn() as con:
        con.execute(
            """
            UPDATE pending_uploads
            SET attempts     = attempts + 1,
                last_attempt = ?
            WHERE id = ?
            """,
            (datetime.now(timezone.utc).isoformat(), row_id),
        )
    logger.warning(f"Upload attempt failed for buffer record {row_id}")


def queue_size() -> int:
    """Return number of pending records."""
    with _conn() as con:
        row = con.execute(
            "SELECT COUNT(*) FROM pending_uploads WHERE attempts < ?",
            (MAX_ATTEMPTS,),
        ).fetchone()
    return row[0]
