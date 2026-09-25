"""
Tests for CV storage service.

Tests:
- Store and read CV files
- Delete CV files
- File hash calculation
- Size limits
"""
import os
import tempfile

import pytest

from app.services import cv_storage


class TestCVStorage:
    """Tests for CV file storage."""

    @pytest.fixture(autouse=True)
    def temp_storage(self, monkeypatch):
        """Use temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setenv("CV_STORAGE_DIR", tmpdir)
            yield tmpdir

    def test_store_and_read(self):
        """Store and read CV file."""
        content = b"test pdf content"
        path = cv_storage.store_cv(user_id=1, filename="test.pdf", file_content=content)

        read_content = cv_storage.read_cv(path)
        assert read_content == content

    def test_store_creates_user_directory(self):
        """Store creates user subdirectory."""
        content = b"test"
        path = cv_storage.store_cv(user_id=42, filename="cv.pdf", file_content=content)

        assert "/42/" in path
        assert os.path.exists(os.path.dirname(path))

    def test_delete_existing(self):
        """Delete removes file."""
        content = b"test"
        path = cv_storage.store_cv(user_id=1, filename="test.pdf", file_content=content)

        result = cv_storage.delete_cv(path)
        assert result is True
        assert not os.path.exists(path)

    def test_delete_nonexistent(self):
        """Delete returns False for non-existent file."""
        result = cv_storage.delete_cv("/nonexistent/file.pdf")
        assert result is False

    def test_file_too_large(self):
        """Store rejects file over 10MB."""
        large_content = b"x" * (11 * 1024 * 1024)

        with pytest.raises(ValueError, match="File too large"):
            cv_storage.store_cv(user_id=1, filename="large.pdf", file_content=large_content)


class TestCalculateHash:
    """Tests for file hash calculation."""

    def test_calculates_sha256(self):
        """Returns SHA256 hash of content."""
        content = b"test content"
        hash1 = cv_storage.calculate_file_hash(content)

        # Should be consistent
        hash2 = cv_storage.calculate_file_hash(content)
        assert hash1 == hash2

        # Should be 64 chars (SHA256 hex)
        assert len(hash1) == 64

    def test_different_content_different_hash(self):
        """Different content produces different hash."""
        hash1 = cv_storage.calculate_file_hash(b"content 1")
        hash2 = cv_storage.calculate_file_hash(b"content 2")

        assert hash1 != hash2
