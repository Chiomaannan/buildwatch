"""
minio_client.py — MinIO / S3-compatible storage helpers.

Provides:
  - upload_file()        : store bytes or a file path
  - download_to_bytes()  : retrieve object as bytes
  - get_presigned_url()  : time-limited public URL for dashboard display
  - delete_object()      : remove an object
"""

import io
import logging
from functools import lru_cache

from minio import Minio
from minio.error import S3Error

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_minio_client() -> Minio:
    """Return a cached MinIO client instance for internal (in-network) operations."""
    settings = get_settings()
    return Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


@lru_cache
def _get_public_minio_client() -> Minio:
    """
    Client signed against minio_public_endpoint — used only for presigned URLs.
    Region is fixed explicitly so the SDK skips its bucket-location lookup,
    which would otherwise try (and fail) to reach minio_public_endpoint
    directly — it isn't network-reachable from inside the container.
    """
    settings = get_settings()
    return Minio(
        endpoint=settings.minio_public_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
        region="us-east-1",
    )


def upload_bytes(
    bucket: str,
    object_name: str,
    data: bytes,
    content_type: str = "image/jpeg",
) -> str:
    """
    Upload raw bytes to MinIO.

    Returns the object_name (storage path) on success.
    Raises S3Error on failure.
    """
    client = get_minio_client()
    client.put_object(
        bucket_name=bucket,
        object_name=object_name,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    logger.info(f"Uploaded {len(data)} bytes → {bucket}/{object_name}")
    return object_name


def upload_file(bucket: str, object_name: str, file_path: str) -> str:
    """
    Upload a local file to MinIO.

    Returns the object_name on success.
    """
    client = get_minio_client()
    client.fput_object(bucket_name=bucket, object_name=object_name, file_path=file_path)
    logger.info(f"Uploaded file {file_path} → {bucket}/{object_name}")
    return object_name


def download_to_bytes(bucket: str, object_name: str) -> bytes:
    """Retrieve an object and return its content as bytes."""
    client = get_minio_client()
    response = client.get_object(bucket_name=bucket, object_name=object_name)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def get_presigned_url(bucket: str, object_name: str, expires_hours: int = 24) -> str:
    """
    Generate a pre-signed GET URL valid for `expires_hours` hours.
    Used by the dashboard to serve images without making buckets fully public.
    """
    from datetime import timedelta

    client = _get_public_minio_client()
    url = client.presigned_get_object(
        bucket_name=bucket,
        object_name=object_name,
        expires=timedelta(hours=expires_hours),
    )
    return url


def delete_object(bucket: str, object_name: str) -> None:
    """Delete an object from MinIO."""
    client = get_minio_client()
    try:
        client.remove_object(bucket_name=bucket, object_name=object_name)
        logger.info(f"Deleted {bucket}/{object_name}")
    except S3Error as exc:
        logger.warning(f"Could not delete {bucket}/{object_name}: {exc}")
