"""
Adaptation cache (Slice A, sprint-adapt-cv-outreach, PR2).

Cache key
---------
``(parent_cv_id, content_version_snapshot, jd_text_hash)``

- ``parent_cv_id``: id of the source CV in ``users_cvs``.
- ``content_version_snapshot``: the source CV's ``content_version`` AT
  THE MOMENT the cached row was written (migration 022 stamps it onto
  ``cv_adaptations.content_version``). On read we compare the row's
  snapshot against the source CV's CURRENT ``content_version`` — equal
  is a hit, different is a miss. The CV edit path (``PATCH /v1/cvs/{id}``)
  bumps ``users_cvs.content_version`` (migration 014), so the snapshot
  becomes stale on edit and the cache miss is automatic.
- ``jd_text_hash``: ``sha256(jd_text[:500].encode()).hexdigest()``. Same
  first 500 chars of the JD = same hash. This is intentionally fuzzy on
  the tail because JDs often have boilerplate appended (company
  footers, EEO statements) that doesn't change the adaptation target.

Why the snapshot, not the caller's value
----------------------------------------
The previous shape (``content_version: int`` passed in by the caller)
read the source CV's ``content_version`` in the same request and
passed it back in. The cache's "defensive" check then compared
``cv_obj.content_version != content_version`` — a tautology (``x != x``).
The caller did not know what value the source CV had been at when the
row was originally written, and had no way to find out: that is
precisely what the snapshot on the row records. Reading it is what
makes the comparison meaningful: the row says "I was generated when
the CV was at v=N"; the current CV says "I am at v=M"; mismatch → miss.

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
    jd_text_hash: str,
) -> SQLModel | None:
    """Look up a valid cached adaptation for the given (cv, jd) key.

    A cached row is valid when ALL of the following hold:
    - ``parent_cv_id`` matches ``cv_id``
    - ``jd_text_hash`` matches the supplied hash
    - ``status`` is ``completed`` (we never serve pending/failed rows)
    - ``created_at`` is within ``CACHE_TTL`` (24 h)
    - the row's stored snapshot of ``users_cvs.content_version``
      (``cv_adaptations.content_version``) still equals the source CV's
      current ``users_cvs.content_version``. When the source CV was
      edited between cache write and cache read, ``PATCH /v1/cvs/{id}``
      bumped ``users_cvs.content_version`` and the snapshot no longer
      matches — we miss on purpose so the runner rebuilds against the
      new CV.

    Args:
        session: Async DB session (RLS context must already be bound
            by the caller; ``cv_adaptations`` and ``users_cvs`` are both
            RLS-protected).
        cv_id: Source CV id (``parent_cv_id``).
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

    # Snapshot-vs-current check (migration 022). The row's
    # ``content_version`` is the source CV's value at write time;
    # the source CV's CURRENT value is whatever ``users_cvs`` says now.
    # When they differ, the CV was edited since the cache row was
    # written — a miss, so the runner rebuilds against the new CV.
    # The previous API let the caller pass the value back in, which
    # was a tautology because the caller had read it from the same
    # ``users_cvs`` row in the same request; the row is the only source
    # of truth that survives across requests.
    cv_row = await session.execute(
        select(UserCV).where(UserCV.id == cv_id)
    )
    cv_obj = cv_row.scalar_one_or_none()
    if cv_obj is None:
        return None
    if row.content_version != cv_obj.content_version:
        return None

    return row
