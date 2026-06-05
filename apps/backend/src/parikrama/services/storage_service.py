"""
Storage service — MinIO file upload/download/delete wrapper.

All document files (PDFs, TXTs) are stored in MinIO object storage.
The Postgres ``documents`` table only keeps metadata + the MinIO object key.
"""
from __future__ import annotations

import io
import uuid
from pathlib import Path

import structlog
from minio import Minio
from minio.error import S3Error

from parikrama.config import settings

logger = structlog.get_logger(__name__)

BUCKET_NAME = "parikrama-documents"

# Allowed content types for document uploads
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "application/octet-stream",  # generic fallback
}

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def _get_client() -> Minio:
    """Build a MinIO client from settings."""
    return Minio(
        endpoint=settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )


def ensure_bucket() -> None:
    """Create the documents bucket if it doesn't exist. Safe to call multiple times."""
    client = _get_client()
    try:
        if not client.bucket_exists(BUCKET_NAME):
            client.make_bucket(BUCKET_NAME)
            logger.info("minio_bucket_created", bucket=BUCKET_NAME)
    except S3Error as exc:
        logger.error("minio_bucket_create_failed", bucket=BUCKET_NAME, error=str(exc))
        raise


def upload_file(
    file_data: bytes,
    filename: str,
    content_type: str,
    user_id: str,
) -> tuple[str, int]:
    """Upload a file to MinIO and return (object_key, size_bytes).

    The object key format: ``{user_id}/{uuid4}/{filename}``
    This ensures uniqueness while preserving human-readable filenames.

    Args:
        file_data: Raw file bytes.
        filename: Original filename (used as suffix in the key).
        content_type: MIME type, e.g. ``application/pdf``.
        user_id: Uploading user's UUID (used as key prefix for namespacing).

    Returns:
        Tuple of (minio_key, file_size_bytes).

    Raises:
        ValueError: If file is empty, too large, or content type not allowed.
        S3Error: If MinIO operation fails.
    """
    size = len(file_data)
    if size == 0:
        raise ValueError("Uploaded file is empty.")
    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File too large: {size} bytes (max {MAX_FILE_SIZE_BYTES}).")
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError(f"Content type not allowed: {content_type!r}.")

    ensure_bucket()

    # Build unique key
    safe_name = Path(filename).name  # strip path traversal attempts
    object_key = f"{user_id}/{uuid.uuid4()}/{safe_name}"

    client = _get_client()
    client.put_object(
        bucket_name=BUCKET_NAME,
        object_name=object_key,
        data=io.BytesIO(file_data),
        length=size,
        content_type=content_type,
    )

    logger.info(
        "file_uploaded_to_minio",
        key=object_key,
        size_bytes=size,
        content_type=content_type,
    )
    return object_key, size


def download_file(object_key: str) -> bytes:
    """Download a file from MinIO by its object key.

    Args:
        object_key: The MinIO key (from ``documents.minio_key``).

    Returns:
        Raw file bytes.

    Raises:
        S3Error: If the object doesn't exist or MinIO is unreachable.
    """
    client = _get_client()
    response = client.get_object(BUCKET_NAME, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def delete_file(object_key: str) -> None:
    """Delete a file from MinIO.

    Silently succeeds if the object doesn't exist (idempotent).

    Args:
        object_key: The MinIO key to delete.
    """
    client = _get_client()
    try:
        client.remove_object(BUCKET_NAME, object_key)
        logger.info("file_deleted_from_minio", key=object_key)
    except S3Error as exc:
        # NoSuchKey is acceptable — object may have already been deleted.
        if "NoSuchKey" in str(exc) or "NoSuchBucket" in str(exc):
            logger.warning("minio_delete_object_not_found", key=object_key)
        else:
            logger.error("minio_delete_failed", key=object_key, error=str(exc))
            raise


def get_presigned_url(object_key: str, expires_seconds: int = 3600) -> str:
    """Generate a presigned download URL for a MinIO object.

    Args:
        object_key: MinIO object key.
        expires_seconds: URL expiry duration in seconds (default 1 hour).

    Returns:
        Presigned HTTPS/HTTP URL string.
    """
    from datetime import timedelta
    client = _get_client()
    url = client.presigned_get_object(
        BUCKET_NAME,
        object_key,
        expires=timedelta(seconds=expires_seconds),
    )
    return url
