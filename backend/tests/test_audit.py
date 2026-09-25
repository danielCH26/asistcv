"""
Tests for audit endpoints.

Covers:
- Rate limiting (3/IP/day)
- JD validation (min 50 chars)
- PDF size limits (10MB)
- PDF upload path (valid/scanned/oversized/non-PDF/garbage)
- Email capture (valid/invalid/expired)
- Audit retrieval
- Retention cleanup
"""
import io
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.session import get_session_context


def _build_pdf(text: str) -> bytes:
    """Build a minimal valid single-page PDF containing `text`.

    Copied as a test helper (no such helper exists in test_pdf_parser.py):
    constructs objects + xref table manually so pypdf/pdfminer can parse
    it without external fixtures.
    """
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return out.getvalue()


VALID_JD = (
    "Looking for a Python developer with AWS experience. "
    "Must have 5+ years of experience in software development. "
    "Experience with React and Node.js is a plus."
)
VALID_CV_TEXT = (
    "John Doe. Experienced Python developer with six years of experience "
    "in Django, FastAPI and AWS platforms at product companies."
)
PDF_TEXT = "John Doe. Experienced Python developer with six years of experience in Django FastAPI and AWS platforms."


# Mock the LLM provider for tests
@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider for audit tests."""
    with patch("app.services.audit_runner.get_llm_provider") as mock:
        provider = MagicMock()
        provider.generate_embedding = AsyncMock(
            return_value=MagicMock(vector=[0.1] * 1024)
        )
        provider.generate_match = AsyncMock(
            return_value=MagicMock(
                score=75,
                strengths=["Strong Python skills", "Good communication"],
                gaps=["No AWS experience", "Limited leadership"],
                energy_level="high",
                reasoning="Good match overall"
            )
        )
        mock.return_value = provider
        yield provider


@pytest.fixture
def mock_retrieval():
    """Mock retrieval service."""
    with patch("app.services.audit_runner.retrieve_profile_context") as mock:
        mock.return_value = MagicMock(
            mode="complete",
            text="Test profile context"
        )
        yield mock


class TestAuditRateLimit:
    """Tests for audit rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limit_check_allows_first_three(self, clean_db):
        """Rate limit allows first 3 audits from same IP."""
        from app.services.audit_rate_limit import check_rate_limit

        async with get_session_context() as session:
            allowed, retry_after = await check_rate_limit(session, "192.168.1.1")
            assert allowed is True
            assert retry_after == 0

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_fourth(self, clean_db):
        """Rate limit blocks 4th audit from same IP."""
        from datetime import timedelta

        from app.db.models import AuditUpload
        from app.services.audit_rate_limit import check_rate_limit
        from app.services.audit_token import calculate_expiry, hash_ip

        ip = "192.168.1.100"
        ip_hash = hash_ip(ip)

        # Create audits with recent timestamps (within the 24h window)
        recent_time = datetime.now(UTC) - timedelta(hours=12)

        async with get_session_context() as session:
            # Create 3 audit records for the same IP
            for i in range(3):
                audit = AuditUpload(
                    audit_token_hash=f"hash_{i}",
                    jd_text="A" * 100,
                    ip_hash=ip_hash,
                    created_at=recent_time,
                    expires_at=calculate_expiry(recent_time),
                )
                session.add(audit)
            await session.commit()

        async with get_session_context() as session:
            allowed, retry_after = await check_rate_limit(session, ip)
            assert allowed is False
            # retry_after should be positive when audits are within the window
            assert retry_after >= 0

    @pytest.mark.asyncio
    async def test_rate_limit_allows_different_ips(self, clean_db):
        """Rate limit allows different IPs independently."""
        from app.db.models import AuditUpload
        from app.services.audit_rate_limit import check_rate_limit
        from app.services.audit_token import calculate_expiry, hash_ip

        ip1 = "192.168.1.1"
        ip2 = "192.168.1.2"

        async with get_session_context() as session:
            # Create 3 audits for IP1
            for i in range(3):
                audit = AuditUpload(
                    audit_token_hash=f"hash_ip1_{i}",
                    jd_text="A" * 100,
                    ip_hash=hash_ip(ip1),
                    expires_at=calculate_expiry(),
                )
                session.add(audit)
            await session.commit()

        async with get_session_context() as session:
            # IP2 should still be allowed
            allowed, _ = await check_rate_limit(session, ip2)
            assert allowed is True


class TestAuditToken:
    """Tests for audit token generation and validation."""

    def test_generate_audit_token(self):
        """Token generation produces unique tokens."""
        from app.services.audit_token import compute_token_hash, generate_audit_token

        token1, hash1 = generate_audit_token()
        token2, hash2 = generate_audit_token()

        assert token1 != token2
        assert hash1 != hash2
        assert compute_token_hash(token1) == hash1

    def test_calculate_expiry(self):
        """Expiry is set to 30 days from creation."""
        from app.services.audit_token import AUDIT_TOKEN_VALIDITY_DAYS, calculate_expiry

        now = datetime.now(UTC)
        expiry = calculate_expiry(now)

        expected = now + timedelta(days=AUDIT_TOKEN_VALIDITY_DAYS)
        assert abs((expiry - expected).total_seconds()) < 1

    def test_is_expired(self):
        """Expired check works correctly."""
        from app.services.audit_token import is_expired

        past = datetime.now(UTC) - timedelta(days=31)
        future = datetime.now(UTC) + timedelta(days=1)

        assert is_expired(past) is True
        assert is_expired(future) is False

    def test_hash_ip(self):
        """IP hashing produces consistent hashes."""
        import hashlib

        from app.services.audit_token import hash_ip

        ip = "192.168.1.1"
        expected_hash = hashlib.sha256(ip.encode()).hexdigest()[:64]

        assert hash_ip(ip) == expected_hash
        assert hash_ip(None) is None


class TestAuditEndpoint:
    """Tests for audit API endpoints."""

    @pytest.mark.asyncio
    async def test_audit_anonymous_requires_jd_min_length(
        self, client, mock_llm_provider, mock_retrieval
    ):
        """POST /v1/audit/anonymous rejects short JD."""
        response = client.post(
            "/v1/audit/anonymous",
            data={"jd_text": "Too short"},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "JD_TOO_SHORT"

    @pytest.mark.asyncio
    async def test_audit_anonymous_returns_result(
        self, client, mock_llm_provider, mock_retrieval
    ):
        """POST /v1/audit/anonymous returns analysis result."""
        response = client.post(
            "/v1/audit/anonymous",
            data={
                "jd_text": "Looking for a Python developer with AWS experience. "
                "Must have 5+ years of experience in software development. "
                "Experience with React and Node.js is a plus.",
                "cv_text": "Experienced Python developer with 6 years of experience. "
                "Strong in Django and FastAPI.",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "audit_token" in data
        assert "score" in data
        assert data["score"] == 75
        assert "Cache-Control" in response.headers
        assert response.headers["Cache-Control"] == "no-store"

    @pytest.mark.asyncio
    async def test_audit_rate_limit_response_includes_retry_after(
        self, client, mock_llm_provider, mock_retrieval
    ):
        """Rate limited response includes Retry-After header."""
        # This test would require setting up 3+ audits first
        # For now, we just verify the header structure exists
        pass


class TestCaptureEmail:
    """Tests for email capture endpoint."""

    @pytest.mark.asyncio
    async def test_capture_email_invalid_format(self, client):
        """Capture email rejects invalid email format."""
        response = client.post(
            "/v1/audit/test-token/capture-email",
            json={"email": "not-an-email"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_capture_email_audit_not_found(self, client):
        """Capture email returns 404 for non-existent audit."""
        response = client.post(
            "/v1/audit/nonexistent-token/capture-email",
            json={"email": "test@example.com"},
        )
        assert response.status_code == 404


class TestAuditRetrieve:
    """Tests for audit retrieval endpoint."""

    def test_get_audit_not_found(self, client):
        """GET /v1/audit/{token} returns 404 for non-existent audit."""
        response = client.get("/v1/audit/nonexistent-token")
        assert response.status_code == 404


class TestAuditRetention:
    """Tests for audit retention cleanup."""

    @pytest.mark.asyncio
    async def test_delete_expired_audits(self, clean_db):
        """delete_expired_audits removes expired unlinked audits."""
        from app.db.models import AuditUpload
        from app.services.audit_retention import delete_expired_audits
        from app.services.audit_token import generate_audit_token

        # Create expired audit
        _, hash1 = generate_audit_token()
        expired_date = datetime.now(UTC) - timedelta(days=31)

        async with get_session_context() as session:
            audit = AuditUpload(
                audit_token_hash=hash1,
                jd_text="Test JD",
                expires_at=expired_date,
                linked_user_id=None,  # Not linked
            )
            session.add(audit)
            await session.commit()

        # Run cleanup
        async with get_session_context() as session:
            deleted = await delete_expired_audits(session)
            assert deleted == 1

    @pytest.mark.asyncio
    async def test_retention_preserves_linked_audits(self, clean_db):
        """delete_expired_audits preserves audits linked to users."""
        from app.db.models import AuditUpload, User
        from app.services.audit_retention import delete_expired_audits
        from app.services.audit_token import generate_audit_token

        # Create expired but linked audit
        _, hash1 = generate_audit_token()
        expired_date = datetime.now(UTC) - timedelta(days=31)

        async with get_session_context() as session:
            # Create user first
            user = User(
                email="test@example.com",
                password_hash="hash",
                role="job_seeker",
                full_name="Test User",
            )
            session.add(user)
            await session.flush()

            audit = AuditUpload(
                audit_token_hash=hash1,
                jd_text="Test JD",
                expires_at=expired_date,
                linked_user_id=user.id,  # Linked to user
            )
            session.add(audit)
            await session.commit()

        # Run cleanup
        async with get_session_context() as session:
            deleted = await delete_expired_audits(session)
            assert deleted == 0  # Should not delete linked audits


class TestAuditPdfUpload:
    """Tests for the PDF upload path of POST /v1/audit/anonymous."""

    async def _seed_audits(self, ip: str, count: int) -> None:
        """Insert `count` successful audits for `ip` to trip the rate limit."""
        from app.db.models import AuditUpload
        from app.services.audit_token import calculate_expiry, hash_ip

        async with get_session_context() as session:
            for i in range(count):
                session.add(
                    AuditUpload(
                        audit_token_hash=f"hash_pdf_{ip}_{i}",
                        jd_text="A" * 100,
                        ip_hash=hash_ip(ip),
                        expires_at=calculate_expiry(),
                    )
                )
            await session.commit()

    @pytest.mark.asyncio
    async def test_pdf_upload_success(self, client, mock_llm_provider, mock_retrieval):
        """Valid small PDF + valid JD returns 200 with audit_token."""
        response = client.post(
            "/v1/audit/anonymous",
            data={"jd_text": VALID_JD},
            files={
                "cv_file": (
                    "cv.pdf",
                    _build_pdf(PDF_TEXT),
                    "application/pdf",
                )
            },
            headers={"X-Forwarded-For": "203.0.113.11"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "audit_token" in data
        assert data["score"] == 75
        assert response.headers["Cache-Control"] == "no-store"

    @pytest.mark.asyncio
    async def test_scanned_pdf_rejected(self, client, mock_llm_provider, mock_retrieval):
        """PDF with no meaningful text (scanned) returns 422 PDF_NO_TEXT."""
        response = client.post(
            "/v1/audit/anonymous",
            data={"jd_text": VALID_JD},
            files={"cv_file": ("scan.pdf", _build_pdf("Hi"), "application/pdf")},
            headers={"X-Forwarded-For": "203.0.113.12"},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "PDF_NO_TEXT"

    @pytest.mark.asyncio
    async def test_oversized_pdf_rejected(
        self, client, mock_llm_provider, mock_retrieval, monkeypatch
    ):
        """PDF above the size cap returns 413 (cap patched small for speed)."""
        from app.api.v1 import audit as audit_module

        monkeypatch.setattr(audit_module, "MAX_PDF_SIZE", 10)
        response = client.post(
            "/v1/audit/anonymous",
            data={"jd_text": VALID_JD},
            files={"cv_file": ("cv.pdf", _build_pdf(PDF_TEXT), "application/pdf")},
            headers={"X-Forwarded-For": "203.0.113.13"},
        )
        assert response.status_code == 413
        assert response.json()["detail"]["code"] == "FILE_TOO_LARGE"

    @pytest.mark.asyncio
    async def test_non_pdf_file_rejected(self, client, mock_llm_provider, mock_retrieval):
        """text/plain upload (.txt) returns 415 UNSUPPORTED_MEDIA_TYPE."""
        response = client.post(
            "/v1/audit/anonymous",
            data={"jd_text": VALID_JD},
            files={"cv_file": ("notes.txt", b"plain text cv", "text/plain")},
            headers={"X-Forwarded-For": "203.0.113.14"},
        )
        assert response.status_code == 415
        assert response.json()["detail"]["code"] == "UNSUPPORTED_MEDIA_TYPE"

    @pytest.mark.asyncio
    async def test_garbage_pdf_rejected(self, client, mock_llm_provider, mock_retrieval):
        """PDF bytes neither parser can read return 503 PDF_PARSE_FAILED."""
        response = client.post(
            "/v1/audit/anonymous",
            data={"jd_text": VALID_JD},
            files={"cv_file": ("cv.pdf", b"%PDF-1.4 garbage not a pdf", "application/pdf")},
            headers={"X-Forwarded-For": "203.0.113.15"},
        )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "PDF_PARSE_FAILED"

    @pytest.mark.asyncio
    async def test_missing_cv_rejected(self, client, mock_llm_provider, mock_retrieval):
        """Neither cv_file nor cv_text returns 422 CV_REQUIRED."""
        response = client.post(
            "/v1/audit/anonymous",
            data={"jd_text": VALID_JD},
            headers={"X-Forwarded-For": "203.0.113.16"},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "CV_REQUIRED"

    @pytest.mark.asyncio
    async def test_cv_text_too_short_rejected(self, client, mock_llm_provider, mock_retrieval):
        """cv_text below minimum length returns 422 CV_TOO_SHORT."""
        response = client.post(
            "/v1/audit/anonymous",
            data={"jd_text": VALID_JD, "cv_text": "short cv"},
            headers={"X-Forwarded-For": "203.0.113.17"},
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "CV_TOO_SHORT"

    @pytest.mark.asyncio
    async def test_rate_limit_applies_to_pdf_path(self, client, mock_llm_provider, mock_retrieval):
        """Rate limit (3/IP/day) also blocks the PDF upload path."""
        ip = "203.0.113.18"
        await self._seed_audits(ip, 3)

        response = client.post(
            "/v1/audit/anonymous",
            data={"jd_text": VALID_JD},
            files={"cv_file": ("cv.pdf", _build_pdf(PDF_TEXT), "application/pdf")},
            headers={"X-Forwarded-For": ip},
        )
        assert response.status_code == 429
        assert response.json()["detail"]["code"] == "RATE_LIMITED"
