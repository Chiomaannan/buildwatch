"""
config.py — Centralised settings loaded from environment variables.
Uses pydantic-settings so every value is type-validated at startup.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Database ──────────────────────────────────────────────────────
    database_url: str = "postgresql://aic_user:aic_password@localhost:5432/aic_db"

    # ── Redis / Celery ────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── MinIO ─────────────────────────────────────────────────────────
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"
    minio_raw_bucket: str = "raw-images"
    minio_annotated_bucket: str = "annotated-images"
    minio_secure: bool = False

    # Host used when *signing* presigned URLs returned to the dashboard.
    # minio_endpoint (e.g. "minio:9000") only resolves inside the Docker
    # network; browsers need the host-mapped address instead.
    minio_public_endpoint: str = "localhost:9000"

    # ── App ───────────────────────────────────────────────────────────
    secret_key: str = "change-me"
    debug: bool = False

    # ── AI Models ─────────────────────────────────────────────────────
    # Path to the YOLO11n BuildWatch weights file.
    yolo_model_path: str = "buildwatch_best.pt"

    # Raw detection confidence threshold — set low; MWPI applies its own 0.4 threshold.
    yolo_confidence: float = 0.25

    # Segmentation is disabled — BuildWatch uses YOLO11n detection only.
    enable_segmentation: bool = False

    # When true, detector.detect() returns plausible fake detections instead of
    # running YOLO11n — lets the full pipeline run without torch/ultralytics
    # installed. Flip to false once stable internet is available for the real
    # model wheels (see backend/Dockerfile ARG MOCK_INFERENCE).
    mock_inference: bool = False

    # ── Anthropic API (plan analysis) ─────────────────────────────────
    # Used by plan_analyzer.py to extract structural weights and expected
    # element counts from uploaded building plan images.
    # Leave empty to fall back to YOLO area analysis or hard defaults.
    anthropic_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
