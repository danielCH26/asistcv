"""
Tests for offer_prefs — helpers over User.offer_preferences JSONB.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.services.offer_prefs import OfferPrefs, get_offer_prefs, is_stale


class TestOfferPrefs:
    """Defaults defined in the dataclass."""

    def test_default_frequency_hours(self):
        prefs = OfferPrefs()
        assert prefs.frequency_hours == 24

    def test_default_top_n(self):
        prefs = OfferPrefs()
        assert prefs.top_n == 5

    def test_default_email_frequency(self):
        prefs = OfferPrefs()
        assert prefs.email_frequency == "none"


class TestGetOfferPrefs:
    """get_offer_prefs extracts fields from the JSONB, applying defaults."""

    def test_null_preferences_returns_defaults(self):
        """Null offer_preferences dict yields defaults."""
        user = _make_user(offer_preferences=None)
        prefs = get_offer_prefs(user)
        assert prefs.frequency_hours == 24
        assert prefs.top_n == 5
        assert prefs.email_frequency == "none"

    def test_partial_preferences_fills_rest_with_defaults(self):
        """Only some keys present — rest filled from defaults."""
        user = _make_user(offer_preferences={"frequency_hours": 12})
        prefs = get_offer_prefs(user)
        assert prefs.frequency_hours == 12
        assert prefs.top_n == 5
        assert prefs.email_frequency == "none"

    def test_malformed_not_a_dict(self):
        """Non-dict value falls back to defaults entirely."""
        user = _make_user(offer_preferences="not a dict")
        prefs = get_offer_prefs(user)
        assert prefs.frequency_hours == 24
        assert prefs.top_n == 5

    def test_malformed_wrong_types(self):
        """Non-int frequency_hours uses default."""
        user = _make_user(offer_preferences={"frequency_hours": "twelve"})
        prefs = get_offer_prefs(user)
        assert prefs.frequency_hours == 24

    def test_all_fields_set(self):
        """Full preferences dict — values returned as-is."""
        user = _make_user(
            offer_preferences={
                "frequency_hours": 48,
                "top_n": 10,
                "email_frequency": "daily",
                "filters": {"remote_only": True},
            }
        )
        prefs = get_offer_prefs(user)
        assert prefs.frequency_hours == 48
        assert prefs.top_n == 10
        assert prefs.email_frequency == "daily"

    def test_empty_dict_returns_defaults(self):
        """Empty dict is valid but all defaults apply."""
        user = _make_user(offer_preferences={})
        prefs = get_offer_prefs(user)
        assert prefs.frequency_hours == 24
        assert prefs.top_n == 5


class TestIsStale:
    """is_stale checks last_offer_run_at vs frequency_hours."""

    def test_no_last_run_is_stale(self):
        """last_offer_run_at absent → stale."""
        prefs = OfferPrefs(frequency_hours=24)
        user = _make_user(offer_preferences={"frequency_hours": 24})  # no last_offer_run_at
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert is_stale(user, prefs, now) is True

    def test_null_last_run_is_stale(self):
        """Explicit null last_offer_run_at → stale."""
        prefs = OfferPrefs(frequency_hours=24)
        user = _make_user(
            offer_preferences={"frequency_hours": 24, "last_offer_run_at": None}
        )
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert is_stale(user, prefs, now) is True

    def test_within_frequency_not_stale(self):
        """Last run was 1 hour ago, frequency is 24h → not stale."""
        prefs = OfferPrefs(frequency_hours=24)
        last_run = datetime(2025, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
        user = _make_user(
            offer_preferences={
                "frequency_hours": 24,
                "last_offer_run_at": last_run.isoformat(),
            }
        )
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert is_stale(user, prefs, now) is False

    def test_past_frequency_is_stale(self):
        """Last run was 25 hours ago, frequency is 24h → stale."""
        prefs = OfferPrefs(frequency_hours=24)
        last_run = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        user = _make_user(
            offer_preferences={
                "frequency_hours": 24,
                "last_offer_run_at": last_run.isoformat(),
            }
        )
        now = datetime(2025, 1, 2, 1, 0, 0, tzinfo=timezone.utc)  # 25h later
        assert is_stale(user, prefs, now) is True

    def test_exactly_at_boundary_not_stale(self):
        """Last run exactly 24h ago → not stale."""
        prefs = OfferPrefs(frequency_hours=24)
        last_run = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        user = _make_user(
            offer_preferences={
                "frequency_hours": 24,
                "last_offer_run_at": last_run.isoformat(),
            }
        )
        now = datetime(2025, 1, 2, 12, 0, 0, tzinfo=timezone.utc)  # exactly 24h later
        assert is_stale(user, prefs, now) is False

    def test_custom_frequency_hours_respected(self):
        """frequency=48h with 47h elapsed → not stale."""
        prefs = OfferPrefs(frequency_hours=48)
        last_run = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        user = _make_user(
            offer_preferences={
                "frequency_hours": 48,
                "last_offer_run_at": last_run.isoformat(),
            }
        )
        now = datetime(2025, 1, 3, 11, 0, 0, tzinfo=timezone.utc)  # 47h later
        assert is_stale(user, prefs, now) is False

    def test_invalid_timestamp_not_stale(self):
        """Unparseable timestamp → stale (defensive: better safe than skip)."""
        prefs = OfferPrefs(frequency_hours=24)
        user = _make_user(
            offer_preferences={
                "frequency_hours": 24,
                "last_offer_run_at": "not-a-timestamp",
            }
        )
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert is_stale(user, prefs, now) is True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _MockUser:
    offer_preferences: dict | str | None


def _make_user(offer_preferences: dict | str | None = None) -> _MockUser:
    return _MockUser(offer_preferences=offer_preferences)
