"""
Adaptation cache (Slice A, sprint-adapt-cv-outreach, PR2).

Cache key
---------
``(parent_cv_id, content_version, jd_text_hash)``

- ``parent_cv_id``: id of the source CV in ``users_cvs``.
- ``content_version``: monotonic counter on the source CV, bumped in
  ``PATCH /v1/cvs/{id}``. We compare the cached row's snapshot
  against the CV's *current* value (see ``get_cached``) so an edit
  that bumps ``content_version`` invalidates the cache atomically.
- ``jd_text_hash``: ``sha256(jd_text[:500].encode()).hexdigest()``. Same
  first 500 chars of the JD = same hash. This is intentionally fuzzy on
  the tail because JDs often have boilerplate appended (company
  footers, EEO statements) that doesn't change the adaptation target.

TTL
---
24 hours, enforced by the SQL filter on ``created_at``. We deliberately
don't add a separate cleanup job — a stale row is never returned to the
client because the WHERE clause excludes it, and the row naturally
ages out of any index scans as the partition of recent rows shifts.

Why no Redis
------------
For MVP this lookup runs at most a few times per minute per user; the
``cv_adaptations`` table has a covering index on
``(parent_cv_id, jd_text_hash)`` and the count of completed rows per
user is tiny (≤5–20/month). Premature Redis would add a deployment
surface (Redis URL, eviction policy, observability) that the user base
doesn't justify yet.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

# TTL for cached adaptations. The cache is opportunistic: a stale row
# is never returned to the client because ``get_cached`` filters on
# ``created_at >= now - TTL``.
CACHE_TTL = timedelta(hours=24)

# Number of chars of the JD we hash. Tail of long JDs (EEO statements,
# company footer, related-links lists) doesn't change the adaptation
# target so we deliberately ignore it.
_HASH_PREFIX_LEN = 500


def compute_jd_text_hash(jd_text: str) -> str:
    """Compute the cache hash for a JD text.

    Args:
        jd_text: Free-text job description.

    Returns:
        Hex SHA256 digest of the first 500 chars of the JD. Length is
        always 64 (sha256 hex output).
    """
    head = jd_text[:_HASH_PREFIX_LEN] if jd_text else ""
    return hashlib.sha256(head.encode("utf-8")).hexdigest()


async def get_cached(
    session: AsyncSession,
    cv_id: int,
    content_version: int,
    jd_text_hash: str,
) -> SQLModel | None:
    """Look up a valid cached adaptation for the given triple key.

    A cached row is valid when ALL of the following hold:
    - ``parent_cv_id`` matches ``cv_id``
    - ``jd_text_hash`` matches the supplied hash
    - ``status`` is ``completed`` (we never serve pending/failed rows)
    - ``created_at`` is within ``CACHE_TTL`` (24 h)
    - the parent CV's current ``users_cvs.content_version`` still
      equals the supplied ``content_version`` — when the source CV was
      edited between cache write and cache read, we miss on purpose so
      the runner rebuilds against the new version.

    Args:
        session: Async DB session (RLS context must already be bound
            by the caller; ``cv_adaptations`` and ``users_cvs`` are both
            RLS-protected).
        cv_id: Source CV id (``parent_cv_id``).
        content_version: Expected ``users_cvs.content_version`` of the
            source CV at read time.
        jd_text_hash: Pre-computed hash of the JD head (see
            ``compute_jd_text_hash``).

    Returns:
        The most recent matching ``CVAdaptation`` row, or ``None`` when
        no valid cache hit exists.
    """
    # Imported lazily to avoid circular import at module load (models
    # import services indirectly via session in some call paths).
    from app.db.models import CVAdaptation, UserCV

    threshold = datetime.now(UTC) - CACHE_TTL

    result = await session.execute(
        select(CVAdaptation)
        .where(
            and_(
                CVAdaptation.parent_cv_id == cv_id,
                CVAdaptation.jd_text_hash == jd_text_hash,
                CVAdaptation.status == "completed",
                CVAdaptation.created_at >= threshold,
            )
        )
        .order_by(CVAdaptation.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None

    # Defensive content_version check: if the source CV's CURRENT
    # version differs from what the caller supplied, the CV was edited
    # since this cache row was written. Treat as a miss so the runner
    # rebuilds against the new version.
    cv_row = await session.execute(
        select(UserCV).where(UserCV.id == cv_id)
    )
    cv_obj = cv_row.scalar_one_or_none()
    if cv_obj is None:
        return None
    if cv_obj.content_version != content_version:
        return None

    return row
