"""
Endpoint tests for ``/v1/job-offers`` and ``/v1/me/offer-preferences``.

Exercises the API surface end-to-end:

- GET /v1/job-offers → 401 without auth, 200 with auth (RLS-filtered),
  200 with status filter, 200 with pagination.
- POST /v1/job-offers/{id}/archive → 200, status changes to archived;
  404 for another user's offer (RLS).
- PUT /v1/me/offer-preferences → 200, persists in JSONB;
  422 on invalid body.
- POST /v1/job-offers/run → 200, calls run_offer_search (mocked).

Auth uses ``app.dependency_overrides[get_current_user]`` with a real
``CurrentUser`` object — same pattern as ``test_adaptation_endpoints.py``.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from app.api.deps import CurrentUser, get_current_user
from app.db.models import JobOffer, User
from app.services.offer_search_worker import OfferRunResult
from app.services.rls_context import set_rls_user

# === Auth + user fixtures =====================================================


def _make_current_user(user: User) -> CurrentUser:
    return CurrentUser(
        id=user.id, name=user.full_name, role=user.role, auth_method="jwt"
    )


async def _create_user(
    clean_db, email: str = "owner@example.com", role: str = "job_seeker"
) -> User:
    async with clean_db.session_factory() as session:
        user = User(
            email=email,
            password_hash="x",
            role=role,
            full_name=email.split("@")[0].title(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@asynccontextmanager
async def _override_current_user(user: User):
    """Install a ``get_current_user`` override and clean up after."""
    from app.main import app

    current = _make_current_user(user)
    app.dependency_overrides[get_current_user] = lambda: current
    try:
        yield current
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def _create_offer(
    clean_db,
    owner_user_id: int,
    title: str = "Backend Engineer",
    company: str | None = "Acme",
    status: str = "new",
    search_query: str | None = "python developer jobs",
) -> JobOffer:
    async with clean_db.session_factory() as session:
        await set_rls_user(session, owner_user_id, "job_seeker")
        offer = JobOffer(
            owner_user_id=owner_user_id,
            title=title,
            company=company,
            url=f"https://example.com/{owner_user_id}/{title.lower().replace(' ', '-')}",
            snippet="Great opportunity for a talented developer.",
            published_date="2025-01-15",
            score=75,
            status=status,
            search_query=search_query,
        )
        session.add(offer)
        await session.commit()
        await session.refresh(offer)
        return offer


# === GET /v1/job-offers ========================================================


class TestListJobOffers:
    """GET /v1/job-offers list endpoint."""

    @pytest.mark.asyncio
    async def test_get_401_without_auth(self, async_client, clean_db) -> None:
        """No auth → 401."""
        response = await async_client.get("/v1/job-offers")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_200_with_auth(self, async_client, clean_db) -> None:
        """Auth → 200 with the user's own offers (RLS)."""
        user = await _create_user(clean_db)
        other = await _create_user(clean_db, "other@example.com")

        # Own offer
        own = await _create_offer(clean_db, user.id, "Python Dev")
        # Another user's offer
        await _create_offer(clean_db, other.id, "Java Dev")

        async with _override_current_user(user):
            response = await async_client.get("/v1/job-offers")

        assert response.status_code == 200, response.text
        body = response.json()
        items = body.get("items", [])
        ids = [item["id"] for item in items]
        assert own.id in ids
        # other's offer must NOT appear (RLS)
        other_offers = [i for i in items if i["id"] == other.id]
        assert other_offers == []

    @pytest.mark.asyncio
    async def test_get_filter_status_new(self, async_client, clean_db) -> None:
        """status=new returns only new offers."""
        user = await _create_user(clean_db)
        new_offer = await _create_offer(clean_db, user.id, "New Role", status="new")
        archived = await _create_offer(clean_db, user.id, "Old Role", status="archived")

        async with _override_current_user(user):
            response = await async_client.get("/v1/job-offers?status=new")

        assert response.status_code == 200, response.text
        items = response.json().get("items", [])
        ids = [item["id"] for item in items]
        assert new_offer.id in ids
        assert archived.id not in ids

    @pytest.mark.asyncio
    async def test_get_filter_status_archived(self, async_client, clean_db) -> None:
        """status=archived returns only archived offers."""
        user = await _create_user(clean_db)
        await _create_offer(clean_db, user.id, "Still Active", status="new")
        archived = await _create_offer(clean_db, user.id, "Gone", status="archived")

        async with _override_current_user(user):
            response = await async_client.get("/v1/job-offers?status=archived")

        assert response.status_code == 200, response.text
        items = response.json().get("items", [])
        ids = [item["id"] for item in items]
        assert archived.id in ids

    @pytest.mark.asyncio
    async def test_get_pagination_limit_offset(self, async_client, clean_db) -> None:
        """limit/offset pagination works correctly.

        ORDER BY created_at DESC means the newest items come first.
        """
        user = await _create_user(clean_db)
        # Create 5 offers sequentially — ids[n] is the nth created (oldest=n, newest=n+4)
        ids = []
        for i in range(5):
            offer = await _create_offer(clean_db, user.id, f"Role {i}", company=f"Co{i}")
            ids.append(offer.id)

        async with _override_current_user(user):
            # First page: newest 2 items (last 2 ids in insertion order)
            page1 = await async_client.get("/v1/job-offers?limit=2&offset=0")
            assert page1.status_code == 200
            items1 = page1.json().get("items", [])
            assert len(items1) == 2
            # Newest first: ids[4] (most recent), then ids[3]
            assert items1[0]["id"] == ids[4], f"expected newest={ids[4]}, got {items1[0]['id']}"
            assert items1[1]["id"] == ids[3], f"expected second-newest={ids[3]}, got {items1[1]['id']}"

            # Second page: next 2 (ids[2], ids[1])
            page2 = await async_client.get("/v1/job-offers?limit=2&offset=2")
            assert page2.status_code == 200
            items2 = page2.json().get("items", [])
            assert len(items2) == 2
            assert items2[0]["id"] == ids[2], f"expected {ids[2]}, got {items2[0]['id']}"
            assert items2[1]["id"] == ids[1], f"expected {ids[1]}, got {items2[1]['id']}"

            # Total count
            total = page1.json().get("total", 0)
            assert total == 5

    @pytest.mark.asyncio
    async def test_get_ordered_by_created_at_desc(self, async_client, clean_db) -> None:
        """Offers are returned newest-first."""
        user = await _create_user(clean_db)
        from datetime import timedelta

        now = datetime.now(UTC)
        ids = []
        for i in range(3):
            async with clean_db.session_factory() as session:
                await set_rls_user(session, user.id, "job_seeker")
                offer = JobOffer(
                    owner_user_id=user.id,
                    title=f"Role {i}",
                    url=f"https://example.com/role-{i}",
                    created_at=now - timedelta(hours=i * 2),
                )
                session.add(offer)
                await session.commit()
                await session.refresh(offer)
                ids.append(offer.id)

        async with _override_current_user(user):
            response = await async_client.get("/v1/job-offers")
            items = response.json().get("items", [])
            returned_ids = [item["id"] for item in items]
            # created_at DESC: newest (i=0, created_at=now) first, oldest (i=2) last
            assert returned_ids == [ids[0], ids[1], ids[2]], (
                f"expected newest-first [{ids[0]}, {ids[1]}, {ids[2]}], got {returned_ids}"
            )

    @pytest.mark.asyncio
    async def test_get_excludes_search_query_from_response(self, async_client, clean_db) -> None:
        """search_query is NOT exposed in the response (audit field)."""
        user = await _create_user(clean_db)
        await _create_offer(
            clean_db,
            user.id,
            "DevOps Engineer",
            search_query="kubernetes aws python",
        )

        async with _override_current_user(user):
            response = await async_client.get("/v1/job-offers")

        assert response.status_code == 200
        items = response.json().get("items", [])
        assert len(items) == 1
        # search_query must NOT be in the response
        assert "search_query" not in items[0], (
            "search_query is an internal audit field and must not be exposed"
        )


# === POST /v1/job-offers/{id}/archive ==========================================


class TestArchiveJobOffer:
    """POST /v1/job-offers/{id}/archive endpoint."""

    @pytest.mark.asyncio
    async def test_archive_200_own_offer(self, async_client, clean_db) -> None:
        """Own offer → 200, status changes to archived."""
        user = await _create_user(clean_db)
        offer = await _create_offer(clean_db, user.id, "Backend Dev", status="new")

        async with _override_current_user(user):
            response = await async_client.post(f"/v1/job-offers/{offer.id}/archive")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "archived"

        # DB state check
        async with clean_db.session_factory() as session:
            await set_rls_user(session, user.id, "job_seeker")
            row = await session.get(JobOffer, offer.id)
            assert row is not None
            assert row.status == "archived"

    @pytest.mark.asyncio
    async def test_archive_404_cross_user(self, async_client, clean_db) -> None:
        """Another user's offer → 404 (RLS)."""
        owner = await _create_user(clean_db, "owner@example.com")
        attacker = await _create_user(clean_db, "attacker@example.com")
        offer = await _create_offer(clean_db, owner.id, "Private Role")

        async with _override_current_user(attacker):
            response = await async_client.post(f"/v1/job-offers/{offer.id}/archive")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_archive_404_nonexistent(self, async_client, clean_db) -> None:
        """Non-existent id → 404."""
        user = await _create_user(clean_db)
        async with _override_current_user(user):
            response = await async_client.post("/v1/job-offers/999999/archive")
        assert response.status_code == 404


# === PUT /v1/me/offer-preferences ==============================================


class TestUpdateOfferPreferences:
    """PUT /v1/me/offer-preferences endpoint."""

    @pytest.mark.asyncio
    async def test_put_200_persists_jsonb(self, async_client, clean_db) -> None:
        """Valid body → 200, preferences stored in the user's JSONB."""
        user = await _create_user(clean_db)

        async with _override_current_user(user):
            response = await async_client.put(
                "/v1/me/offer-preferences",
                json={
                    "frequency_hours": 48,
                    "top_n": 10,
                    "email_frequency": "daily",
                    "filters": {"remote_only": True},
                },
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["frequency_hours"] == 48
        assert body["top_n"] == 10
        assert body["email_frequency"] == "daily"
        assert body["filters"] == {"remote_only": True}

        # DB persistence check
        async with clean_db.session_factory() as session:
            row = await session.get(User, user.id)
            assert row is not None
            prefs = row.offer_preferences or {}
            assert prefs["frequency_hours"] == 48
            assert prefs["top_n"] == 10
            assert prefs["email_frequency"] == "daily"
            assert prefs["filters"] == {"remote_only": True}

    @pytest.mark.asyncio
    async def test_put_200_partial_body_uses_defaults(self, async_client, clean_db) -> None:
        """Partial body → 200, missing fields get defaults."""
        user = await _create_user(clean_db)

        async with _override_current_user(user):
            response = await async_client.put(
                "/v1/me/offer-preferences",
                json={"frequency_hours": 12},
            )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["frequency_hours"] == 12
        assert body["top_n"] == 5  # default
        assert body["email_frequency"] == "none"  # default
        assert body["filters"] is None  # default

    @pytest.mark.asyncio
    async def test_put_422_invalid_frequency_hours_too_high(self, async_client, clean_db) -> None:
        """frequency_hours > 168 → 422."""
        user = await _create_user(clean_db)
        async with _override_current_user(user):
            response = await async_client.put(
                "/v1/me/offer-preferences",
                json={"frequency_hours": 200},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_put_422_invalid_frequency_hours_zero(self, async_client, clean_db) -> None:
        """frequency_hours < 1 → 422."""
        user = await _create_user(clean_db)
        async with _override_current_user(user):
            response = await async_client.put(
                "/v1/me/offer-preferences",
                json={"frequency_hours": 0},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_put_422_invalid_top_n_too_high(self, async_client, clean_db) -> None:
        """top_n > 20 → 422."""
        user = await _create_user(clean_db)
        async with _override_current_user(user):
            response = await async_client.put(
                "/v1/me/offer-preferences",
                json={"top_n": 25},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_put_422_invalid_email_frequency(self, async_client, clean_db) -> None:
        """email_frequency not in enum → 422."""
        user = await _create_user(clean_db)
        async with _override_current_user(user):
            response = await async_client.put(
                "/v1/me/offer-preferences",
                json={"email_frequency": "hourly"},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_put_200_email_frequency_values(self, async_client, clean_db) -> None:
        """Each valid email_frequency value is accepted."""
        user = await _create_user(clean_db)
        for freq in ("none", "daily", "weekly"):
            async with _override_current_user(user):
                response = await async_client.put(
                    "/v1/me/offer-preferences",
                    json={"email_frequency": freq},
                )
            assert response.status_code == 200, f"email_frequency={freq} failed"
            assert response.json()["email_frequency"] == freq


# === POST /v1/job-offers/run ====================================================


class TestRunOfferSearch:
    """POST /v1/job-offers/run endpoint."""

    @pytest.mark.asyncio
    async def test_run_200_calls_worker(
        self, async_client, clean_db, monkeypatch
    ) -> None:
        """Valid request → 200, run_offer_search called with correct args."""
        user = await _create_user(clean_db)

        calls: list[dict[str, Any]] = []

        async def _fake_run(
            user_id,
            session_factory,
            settings,
            search_client,
            embedding_provider,
            llm_provider=None,
            *,
            now=None,
        ):
            calls.append(
                {
                    "user_id": user_id,
                    "has_session_factory": session_factory is not None,
                    "has_settings": settings is not None,
                    "has_search_client": search_client is not None,
                    "has_embedding_provider": embedding_provider is not None,
                    "llm_provider": llm_provider,
                }
            )
            return OfferRunResult(found=3, new_offers=2, skipped_stale=False)

        monkeypatch.setattr(
            "app.api.v1.job_offers.run_offer_search", _fake_run
        )
        # Bypass the TAVILY_API_KEY check so the endpoint reaches the worker
        monkeypatch.setattr(
            "app.api.v1.job_offers._build_search_client",
            lambda settings: "fake-client",
        )

        async with _override_current_user(user):
            response = await async_client.post("/v1/job-offers/run")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["found"] == 3
        assert body["new_offers"] == 2
        assert body["skipped_stale"] is False

        assert len(calls) == 1
        call = calls[0]
        assert call["user_id"] == user.id
        assert call["has_session_factory"] is True
        assert call["has_settings"] is True
        assert call["has_search_client"] is True
        assert call["has_embedding_provider"] is True
        assert call["llm_provider"] is None

    @pytest.mark.asyncio
    async def test_run_200_skipped_stale(
        self, async_client, clean_db, monkeypatch
    ) -> None:
        """Stale check prevents search → skipped_stale=True."""
        user = await _create_user(clean_db)

        async def _fake_run(*args, **kwargs):
            return OfferRunResult(found=0, new_offers=0, skipped_stale=True)

        monkeypatch.setattr(
            "app.api.v1.job_offers.run_offer_search", _fake_run
        )
        monkeypatch.setattr(
            "app.api.v1.job_offers._build_search_client",
            lambda settings: "fake-client",
        )

        async with _override_current_user(user):
            response = await async_client.post("/v1/job-offers/run")

        assert response.status_code == 200
        body = response.json()
        assert body["skipped_stale"] is True
        assert body["found"] == 0
        assert body["new_offers"] == 0
