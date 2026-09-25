"""
CV storage service - handles file storage for PDFs.

For MVP: stores files on local disk.
Can be extended to S3 or other storage backends.
"""
import hashlib
import os
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)

# Storage configuration
STORAGE_DIR = os.environ.get("CV_STORAGE_DIR", "/tmp/asistcv_cvs")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


def _get_storage_path(user_id: int, filename: str) -> Path:
    """Get storage path for a CV file."""
    # Create user directory if it doesn't exist
    user_dir = Path(STORAGE_DIR) / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    # Use hash of filename to avoid collisions
    safe_name = hashlib.sha256(filename.encode()).hexdigest()[:16]
    return user_dir / f"{safe_name}.pdf"


def store_cv(user_id: int, filename: str, file_content: bytes) -> str:
    """Store CV file on disk.

    Args:
        user_id: ID of the user storing the CV
        filename: Original filename
        file_content: PDF binary content

    Returns:
        File path relative to storage root
    """
    if len(file_content) > MAX_FILE_SIZE:
        raise ValueError(f"File too large: {len(file_content)} bytes (max {MAX_FILE_SIZE})")

    storage_path = _get_storage_path(user_id, filename)

    with open(storage_path, "wb") as f:
        f.write(file_content)

    logger.info("cv_stored", user_id=user_id, filename=filename, size=len(file_content))

    return str(storage_path)


def read_cv(storage_path: str) -> bytes:
    """Read CV file from storage.

    Args:
        storage_path: Path to the stored file

    Returns:
        PDF binary content
    """
    with open(storage_path, "rb") as f:
        return f.read()


def delete_cv(storage_path: str) -> bool:
    """Delete CV file from storage.

    Args:
        storage_path: Path to the stored file

    Returns:
        True if deleted, False if file didn't exist
    """
    try:
        os.remove(storage_path)
        logger.info("cv_deleted", path=storage_path)
        return True
    except FileNotFoundError:
        return False


def calculate_file_hash(file_content: bytes) -> str:
    """Calculate SHA256 hash of file content.

    Args:
        file_content: Binary content

    Returns:
        Hex string of SHA256 hash
    """
    return hashlib.sha256(file_content).hexdigest()
