"""
RLS context helpers for PostgreSQL Row-Level Security (migration 011).

Binds the ``app.current_user_id`` / ``app.current_role`` GUCs for the
CURRENT TRANSACTION via ``SET LOCAL``. With pooled connections you must
not use session-level ``SET``; ``SET LOCAL`` reverts automatically at
COMMIT/ROLLBACK, so re-bind after every commit that is followed by more
statements.

Contexts:
- user:      ``set_rls_user(session, user_id, role)`` — JWT principals.
- service:   ``set_rls_service(session)`` — GUC '0' (RLS bypass policy):
             MCP/API-key requests, internal cron cleanup, Stripe webhook.
- anonymous: ``set_rls_anonymous(session)`` — free-audit funnel; the
             audit_uploads policies accept 'anonymous' for unlinked rows.
- ``bind_rls_context`` picks user vs service from a principal id
  (0 = service per ``app.api.deps`` convention).

Values are inlined after strict validation (``SET`` does not accept bind
parameters in the PostgreSQL grammar): user ids go through ``int()``,
roles are whitelisted, and the anonymous marker is a constant literal.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

GUC_USER_ID = "app.current_user_id"
# NOTE: "current_role" is a reserved PostgreSQL keyword and cannot be used
# as a custom GUC suffix, so the role GUC is named app.user_role.
GUC_ROLE = "app.user_role"

SERVICE_USER_ID = 0
ANONYMOUS_USER = "anonymous"

_ALLOWED_ROLES = frozenset({"job_seeker", "recruiter", "service"})


async def set_rls_service(session: AsyncSession) -> None:
    """Bind the service context (id '0'): RLS bypass policies grant access."""
    await session.execute(text(f"SET LOCAL {GUC_USER_ID} = '{SERVICE_USER_ID}'"))
    await session.execute(text(f"SET LOCAL {GUC_ROLE} = 'service'"))


async def set_rls_anonymous(session: AsyncSession) -> None:
    """Bind the anonymous context: unlinked audit_uploads rows only."""
    await session.execute(text(f"SET LOCAL {GUC_USER_ID} = '{ANONYMOUS_USER}'"))


async def set_rls_user(
    session: AsyncSession, user_id: int, role: str | None = None
) -> None:
    """Bind the context of an authenticated user.

    The id is cast through ``int()`` before inlining (injection guard);
    unknown roles are ignored rather than echoed into the GUC.
    """
    uid = int(user_id)
    await session.execute(text(f"SET LOCAL {GUC_USER_ID} = '{uid}'"))
    if role in _ALLOWED_ROLES:
        await session.execute(text(f"SET LOCAL {GUC_ROLE} = '{role}'"))


async def bind_rls_context(
    session: AsyncSession, user_id: int, role: str | None = None
) -> None:
    """Bind by principal id: 0 → service context, anything else → that user.

    Mirrors the ``app.api.deps`` convention where API-key/service
    authentication yields ``CurrentUser(id=0)``.
    """
    if user_id == SERVICE_USER_ID:
        await set_rls_service(session)
    else:
        await set_rls_user(session, user_id, role)
