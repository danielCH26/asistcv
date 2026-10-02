"""
Internal cleanup endpoint for the ``users_refresh_tokens`` sweeper.

Called by the ``refresh-token-sweeper.yml`` GitHub Actions cron job daily.
The endpoint deletes rows that can no longer authenticate anything:

1. ``consumed_at`` older than the retention window — tokens already
   rotated away. They are pure audit evidence of the rotation chain.
2. ``revoked_at`` older than the retention window — tokens killed by
   logout or by reuse detection. Same: evidence, not state.

Both predicates are anchored on the *terminal* timestamp, not
``created_at``: a row created 200 days ago and rotated yesterday is still
useful evidence and is kept.

Active rows (never consumed, never revoked) are never deleted. They are
the only rows that can still be exchanged at ``POST /v1/auth/refresh``,
so this sweep can never shorten a live session.

Retention window
----------------
``REFRESH_TOKEN_RETENTION_DAYS`` (default 90). The table is evidence, not
active state, so the window is sized for incident response — a full
quarter — not for storage. Widening it is always safe: it only defers
deletion.

Auth
----
The endpoint expects ``X-Backend-API-Key: <token>``, compared with
``hmac.compare_digest`` against ``settings.backend_api_key``. It fails
closed when the key is unset: an unconfigured environment gets 401, not
an open door.

Response
--------
``{"deleted": N}`` — number of rows removed in this sweep. N=0 is a
successful sweep, not an error.

Wiring
------
Mounted at ``/internal/auth/refresh-tokens/cleanup`` (no ``/v1`` prefix).
The router prefix in ``app.main`` is ``/internal``.
"""
from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import and_, delete, or_

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import RefreshToken
from app.db.session import get_session_context
from app.services.rls_context import set_rls_service

logger = get_logger("app.api.internal.refresh_tokens")

router = APIRouter(tags=["refresh-tokens-internal"])

API_KEY_HEADER = "X-Backend-API-Key"


def _verify_api_key(provided: str | None) -> bool:
    """Constant-time compare against the configured ``BACKEND_API_KEY``.

    Returns ``False`` when the key isn't configured: the sweeper only
    fires from the GitHub Actions cron, and failing closed means a
    misconfigured production environment refuses the sweep instead of
    exposing a destructive DELETE to anyone who finds the path.
    """
    settings = get_settings()
    expected = settings.backend_api_key
    if not expected:
        logger.warning("internal_cleanup_no_api_key_configured")
        return False
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


@router.post("/auth/refresh-tokens/cleanup")
async def cleanup_refresh_tokens(
    x_backend_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
) -> dict[str, int]:
    """Delete consumed/revoked refresh tokens older than the retention window.

    Returns:
        ``{"deleted": N}`` with N = consumed + revoked rows removed in
        this sweep. Active tokens are never counted.
    """
    if not _verify_api_key(x_backend_api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="UNAUTHORIZED",
        )

    settings = get_settings()
    threshold = datetime.now(UTC) - timedelta(days=settings.refresh_token_retention_days)

    async with get_session_context() as session:
        # Service context: the DELETE spans every user, and a future
        # migration that puts users_refresh_tokens under RLS would make
        # the cron unreachable without the bypass (migration 016).
        await set_rls_service(session)

        # One DELETE, one transaction. ``consumed_at`` / ``revoked_at``
        # are ``datetime | None`` in the model; each branch's
        # ``IS NOT NULL`` predicate narrows it at the SQL level but mypy
        # can't see through SQLAlchemy column expressions, so we cast.
        result = await session.execute(
            delete(RefreshToken).where(
                or_(
                    and_(
                        RefreshToken.consumed_at.is_not(None),
                        RefreshToken.consumed_at < threshold,  # type: ignore[operator]
                    ),
                    and_(
                        RefreshToken.revoked_at.is_not(None),
                        RefreshToken.revoked_at < threshold,  # type: ignore[operator]
                    ),
                )
            )
        )
        await session.commit()

        deleted = result.rowcount or 0

    logger.info(
        "refresh_token_cleanup_swept",
        deleted=deleted,
        retention_days=settings.refresh_token_retention_days,
    )
    return {"deleted": deleted}
