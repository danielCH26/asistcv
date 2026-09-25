"""
Tests for recruiter roster functionality.

These tests cover:
- Consent gate (403 for recruiters without consent)
- Re-consent endpoint
- Candidate CRUD operations
- Candidate ranking
"""
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.api.v1.recruiter_candidates as recruiter_candidates_module
from app.core.security import create_access_token
from app.db.models import RecruiterCandidate, RecruiterConsent, Subscription, User
from app.services.candidate_ranking import (
    calculate_effective_score,
    calculate_recency_decay,
)
from app.services.consent_gate import check_recruiter_consent


class TestConsentGate:
    """Tests for the consent gate dependency."""

    @pytest.mark.asyncio
    async def test_recruiter_without_consent_returns_403(self, test_db):
        """Recruiters without consent should get 403 CONSENT_REQUIRED."""
        from fastapi import HTTPException

        async with test_db.session_factory() as session:
            # Create a recruiter without consent
            user = User(
                email="recruiter@test.com",
                password_hash="hashed",
                role="recruiter",
                full_name="Test Recruiter",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            # Create CurrentUser for recruiter
            from app.api.deps import CurrentUser
            current_user = CurrentUser(id=user.id, name=user.full_name, role="recruiter", auth_method="jwt")

            # Mock session.execute to return no consent
            with patch.object(session, "execute", new_callable=AsyncMock) as mock_execute:
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = None
                mock_execute.return_value = mock_result

                with pytest.raises(HTTPException) as exc_info:
                    await check_recruiter_consent(current_user, session)

                assert exc_info.value.status_code == 403
                assert exc_info.value.detail == "CONSENT_REQUIRED"

    @pytest.mark.asyncio
    async def test_recruiter_with_consent_passes(self, test_db):
        """Recruiters with consent should pass."""
        from app.api.deps import CurrentUser

        async with test_db.session_factory() as session:
            # Create a recruiter with consent
            user = User(
                email="recruiter_with_consent@test.com",
                password_hash="hashed",
                role="recruiter",
                full_name="Test Recruiter",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            # Use timezone-aware datetime
            consent = RecruiterConsent(
                user_id=user.id,
                accepted_at=datetime.now(UTC).replace(tzinfo=None),  # Make naive for DB
                tos_version="v1.2",
            )
            session.add(consent)
            await session.commit()

            current_user = CurrentUser(id=user.id, name=user.full_name, role="recruiter", auth_method="jwt")

            # Mock session.execute to return consent
            with patch.object(session, "execute", new_callable=AsyncMock) as mock_execute:
                mock_result = MagicMock()
                mock_result.scalar_one_or_none.return_value = consent
                mock_execute.return_value = mock_result

                result = await check_recruiter_consent(current_user, session)
                assert result.id == user.id
                assert result.role == "recruiter"

    @pytest.mark.asyncio
    async def test_non_recruiter_passes_always(self, test_db):
        """Non-recruiters should always pass (no consent check)."""
        from app.api.deps import CurrentUser

        async with test_db.session_factory() as session:
            current_user = CurrentUser(id=1, name="Test User", role="job_seeker", auth_method="jwt")

            # Should pass without checking consent
            result = await check_recruiter_consent(current_user, session)
            assert result.role == "job_seeker"


class TestCandidateRanking:
    """Tests for the candidate ranking algorithm."""

    def test_calculate_recency_decay_never_analysed(self):
        """Candidates never analysed have no decay (1.0)."""
        decay = calculate_recency_decay(None)
        assert decay == 1.0

    def test_calculate_recency_decay_recent_analysis(self):
        """Recently analysed candidates have high decay (close to 1.0)."""
        recent = datetime.now(UTC) - timedelta(days=1)
        decay = calculate_recency_decay(recent)
        assert 0.9 < decay <= 1.0

    def test_calculate_recency_decay_old_analysis(self):
        """Old analyses have significant decay."""
        old = datetime.now(UTC) - timedelta(days=30)
        decay = calculate_recency_decay(old)
        assert 0.3 < decay < 0.4

    def test_calculate_effective_score_basic(self):
        """Basic effective score calculation."""
        score = calculate_effective_score(0.8, datetime.now(UTC) - timedelta(days=1))
        assert 0.7 < score < 0.8

    def test_calculate_effective_score_floor_rule_applied(self):
        """Floor rule should apply when match_score >= 0.7."""
        # Old analysis that would normally decay below floor
        old = datetime.now(UTC) - timedelta(days=60)
        score = calculate_effective_score(0.9, old, apply_floor=True)

        # With floor: floor = 0.5 * 0.9 = 0.45
        # Without floor: 0.9 * exp(-60/30) = 0.9 * 0.135 = 0.1215
        # Should be capped at floor: >= 0.45
        assert score >= 0.45

    def test_calculate_effective_score_floor_not_applied_for_low_scores(self):
        """Floor rule should NOT apply when match_score < 0.7."""
        old = datetime.now(UTC) - timedelta(days=60)
        score = calculate_effective_score(0.5, old, apply_floor=True)

        # Without floor: 0.5 * exp(-60/30) = 0.5 * 0.135 = 0.0675
        # Floor would be 0.5 * 0.5 = 0.25 but shouldn't apply
        assert score < 0.15


class TestRecruiterConsentModel:
    """Tests for RecruiterConsent model."""

    @pytest.mark.asyncio
    async def test_create_consent(self, test_db):
        """Creating a consent record should work."""
        async with test_db.session_factory() as session:
            user = User(
                email="consent_test@test.com",
                password_hash="hashed",
                role="recruiter",
                full_name="Consent Test",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            # Use timezone-naive datetime for DB
            consent = RecruiterConsent(
                user_id=user.id,
                accepted_at=datetime.now(UTC).replace(tzinfo=None),
                tos_version="v1.2",
                ip="127.0.0.1",
                user_agent="Test/1.0",
            )
            session.add(consent)
            await session.commit()

            assert consent.id is not None
            assert consent.user_id == user.id
            assert consent.tos_version == "v1.2"


class TestCandidateModel:
    """Tests for RecruiterCandidate model."""

    @pytest.mark.asyncio
    async def test_create_candidate(self, test_db):
        """Creating a candidate should work."""
        async with test_db.session_factory() as session:
            user = User(
                email="recruiter_candidate@test.com",
                password_hash="hashed",
                role="recruiter",
                full_name="Recruiter Test",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

            candidate = RecruiterCandidate(
                recruiter_id=user.id,
                full_name="John Doe",
                email="john@example.com",
                phone="+1234567890",
                notes="Good candidate",
            )
            session.add(candidate)
            await session.commit()

            assert candidate.id is not None
            assert candidate.full_name == "John Doe"
            assert candidate.email == "john@example.com"
            assert candidate.recruiter_id == user.id


class TestCandidateIsolation:
    """Security regression: cross-recruiter candidate isolation.

    Existence-leak rule: a foreign candidate id must be indistinguishable
    from a nonexistent one (404 CANDIDATE_NOT_FOUND), never a 403 that
    would confirm the candidate exists.
    """

    @pytest.mark.asyncio
    async def test_match_other_recruiters_candidate_404(
        self, async_client, clean_db, override_get_session, monkeypatch
    ):
        """recruiter_2 POSTs a match on recruiter_1's candidate -> 404, not 403.

        The endpoint filters by ``recruiter_id == current_user.id`` and raises
        404 when no row matches; this test pins that contract so a refactor
        cannot regress it into a 403 (existence leak) or a 200 (data leak).

        recruiter_2 carries a consent row and an active recruiter_starter
        subscription because both gates run BEFORE the ownership check:
        the consent gate would otherwise answer 403 CONSENT_REQUIRED, and
        recruiters on the free plan have zero match quota (tier_limits
        returns 402 PLAN_LIMIT_REACHED before the 404 is reachable).
        """
        jd_text = (
            "Buscamos Python developer con 5 años de experiencia en FastAPI, "
            "PostgreSQL y despliegues en AWS. Trabajo remoto, equipo pequeño."
        )

        async with clean_db.session_factory() as session:
            owner = User(
                email="roster_owner@test.com",
                password_hash="hashed",
                role="recruiter",
                full_name="Owner Recruiter",
            )
            attacker = User(
                email="roster_attacker@test.com",
                password_hash="hashed",
                role="recruiter",
                full_name="Attacker Recruiter",
            )
            session.add_all([owner, attacker])
            await session.commit()
            await session.refresh(owner)
            await session.refresh(attacker)

            # Consent gate (router + endpoint level) requires a consent row
            session.add(
                RecruiterConsent(
                    user_id=attacker.id,
                    accepted_at=datetime.now(UTC).replace(tzinfo=None),
                    tos_version="v1.2",
                )
            )
            # Tier check runs before the 404 path: free-plan recruiters have
            # 0 match quota, so the attacker needs an active paid plan
            session.add(
                Subscription(
                    user_id=attacker.id,
                    plan="recruiter_starter",
                    status="active",
                )
            )

            candidate = RecruiterCandidate(
                recruiter_id=owner.id,
                full_name="Foreign Candidate",
                email="foreign@example.com",
            )
            session.add(candidate)
            await session.commit()
            await session.refresh(candidate)
            foreign_candidate_id = candidate.id

        # Tier check + usage increment run via get_session_context (outside
        # DI): point it at the test DB like the patch_match_db fixture does
        factory = clean_db.session_factory

        @asynccontextmanager
        async def _session_context():
            async with factory() as session:
                yield session

        monkeypatch.setattr(
            recruiter_candidates_module, "get_session_context", _session_context
        )

        # Real JWT: the router-level verify_api_key guard calls
        # get_current_user() directly, bypassing dependency overrides
        token = create_access_token({"sub": str(attacker.id), "role": attacker.role})
        response = await async_client.post(
            f"/v1/recruiter/candidates/{foreign_candidate_id}/match",
            json={"jd_text": jd_text},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "CANDIDATE_NOT_FOUND"
