"""
Helpers over ``User.offer_preferences`` JSONB.

Defines a stable ``OfferPrefs`` dataclass with well-known defaults so
every caller avoids repeating them. All functions are tolerant of
malformed input: they fall back to defaults rather than raising.
"""
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.models import User

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OfferPrefs:
    """Normalised job-offer notification preferences.

    Default values are the application-level defaults; callers that
    bypass this module (e.g. direct ``User.offer_preferences`` reads in
    endpoints) MUST replicate these values to stay in sync.
    """

    frequency_hours: int = 24
    """How often the cron pipeline may run for this user."""
    top_n: int = 5
    """Maximum number of offers to surface in one run."""
    email_frequency: str = "none"
    """When to email: ``none``, ``daily``, ``weekly``."""
    filters: dict[str, Any] | None = None
    """Arbitrary offer filters (e.g. ``{"remote_only": True}``)."""


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def get_offer_prefs(user: User) -> OfferPrefs:
    """Return ``OfferPrefs`` from ``User.offer_preferences``.

    ``user.offer_preferences`` may be:
    - A valid dict → fields extracted as-is, missing keys filled from defaults.
    - ``None`` or any non-dict value (string, int, list…) → all defaults.
    - A dict with wrong types (e.g. ``frequency_hours="twelve"``) →
      the offending key uses its default.

    Returns:
        Fully-resolved ``OfferPrefs`` with no ``None`` fields.
    """
    raw = user.offer_preferences

    if not isinstance(raw, dict):
        return OfferPrefs()

    def _int(value: Any, default: int) -> int:
        if isinstance(value, int) and value > 0:
            return value
        return default

    def _str(value: Any, default: str) -> str:
        if isinstance(value, str):
            return value
        return default

    return OfferPrefs(
        frequency_hours=_int(raw.get("frequency_hours"), 24),
        top_n=_int(raw.get("top_n"), 5),
        email_frequency=_str(raw.get("email_frequency"), "none"),
        filters=raw.get("filters") if isinstance(raw.get("filters"), dict) else None,
    )


# ---------------------------------------------------------------------------
# Staleness check
# ---------------------------------------------------------------------------


def is_stale(user: User, prefs: OfferPrefs, now: datetime) -> bool:
    """Return ``True`` when the pipeline should run for this user.

    A run is due when ``last_offer_run_at`` is absent or older than
    ``prefs.frequency_hours`` hours from ``now``.  Any parsing error in
    the timestamp is treated as *stale* (better an extra search than a
    missed one).

    Args:
        user: The user whose ``offer_preferences`` may carry
            ``last_offer_run_at``.
        prefs: Resolved preferences (carries ``frequency_hours``).
        now: The reference "now" timestamp (UTC-aware).

    Returns:
        ``True`` when the user should be processed; ``False`` when the
        most recent run was recent enough.
    """
    raw = user.offer_preferences
    if not isinstance(raw, dict):
        return True

    raw_ts = raw.get("last_offer_run_at")
    if raw_ts is None:
        return True

    try:
        last_run: datetime
        if isinstance(raw_ts, datetime):
            last_run = raw_ts
        else:
            last_run = datetime.fromisoformat(str(raw_ts))
    except (ValueError, TypeError):
        # Unparseable → treat as stale (defensive).
        return True

    # Normalise to UTC-aware for comparison.
    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=UTC)

    threshold = last_run + timedelta(hours=prefs.frequency_hours)
    return now > threshold
