"""
Roundtrip tests for the ``AuthEmailCode`` model (migration 030).

Requires the disposable test database (uses the ``clean_db`` fixture).
"""

from datetime import UTC, datetime, timedelta

from sqlmodel import select

from app.core.security import hash_token
from app.db.models import AuthEmailCode


async def test_auth_email_code_roundtrip(clean_db) -> None:
    """Insert + re-read an AuthEmailCode with all defaults in place."""
    async with clean_db.session_factory() as session:
        code = AuthEmailCode(
            email="user@example.com",
            code_hash=hash_token("123456"),
            purpose="login",
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        session.add(code)
        await session.commit()
        await session.refresh(code)

        assert code.id is not None
        assert code.email == "user@example.com"
        assert code.purpose == "login"
        assert code.attempts == 0
        assert code.used_at is None
        assert len(code.code_hash) == 64  # SHA256 hex


async def test_auth_email_code_lookup_by_email(clean_db) -> None:
    """The email index supports the 'latest live code for this email' query."""
    now = datetime.now(UTC)
    async with clean_db.session_factory() as session:
        for i, (addr, code) in enumerate(
            [
                ("a@example.com", "111111"),
                ("a@example.com", "222222"),
                ("b@example.com", "333333"),
            ]
        ):
            session.add(
                AuthEmailCode(
                    email=addr,
                    code_hash=hash_token(code),
                    expires_at=now + timedelta(minutes=10 + i),
                )
            )
        await session.commit()

        result = await session.execute(
            select(AuthEmailCode)
            .where(AuthEmailCode.email == "a@example.com")
            .order_by(AuthEmailCode.created_at.desc(), AuthEmailCode.id.desc())
        )
        rows = result.scalars().all()

    assert len(rows) == 2
    assert {r.code_hash for r in rows} == {hash_token("111111"), hash_token("222222")}
