"""
Offer search pipeline — search → rank → persist.

Runs for one user per invocation (called by the cron scheduler).

Flow
----
1. Load the ``User`` row (no profile → short-circuit with empty result).
2. Check staleness via ``is_stale`` — stale or error → result with
   ``skipped_stale=True`` (no Tavily call).
3. Build the search query from the user's ``Profile.skills``.
4. Call ``search_client.search(query)``.
5. Rank each result by cosine similarity of its snippet embedding
   against the profile embedding (re-embed on-demand if NULL or model
   mismatch — mirrors the ``match.py`` pattern).
6. Filter results below ``settings.offer_search_min_score``.
7. Deduplicate by URL: ``SELECT url FROM job_offers WHERE owner_user_id``.
8. Persist new ``JobOffer`` rows (status="new", ``search_query``).
9. ``UPDATE users SET offer_preferences`` → ``last_offer_run_at = now()``.
10. Structured log ``offer_search_run {found, new_offers, skipped_stale, user_id}``.

RLS is respected throughout via ``set_rls_user``.

Errors
------
- Tavily errors (``OfferSearchAuthError``, ``OfferSearchRateLimitError``,
  ``OfferSearchTimeoutError``…) propagate to the caller — the cron
  handler decides retry / alert policy.
- DB errors propagate as ``SQLAlchemyError`` (caller wraps with context).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import select

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models import JobOffer, Profile, User
from app.llm.base import LLMProvider
from app.services.offer_prefs import OfferPrefs, get_offer_prefs, is_stale
from app.services.offer_search_client import (
    OfferSearchResult,
)
from app.services.rls_context import set_rls_user

logger = get_logger("app.services.offer_search_worker")

# ---------------------------------------------------------------------------
# LLM prompt constants for query refinement and result classification
# ---------------------------------------------------------------------------

_QUERY_REFINEMENT_SYSTEM = """Eres un asistente que genera queries de búsqueda para encontrar ofertas de empleo individuales.

REGLAS ESTRICTAS:
1. Usa SOLO las skills/experiencia del perfil del candidato. NO inventes skills.
2. Genera UNA query corta y específica (máximo 10-12 palabras).
3. La query debe buscar OFERTAS DE EMPLEO INDIVIDUALES, no portales de listado.
4. Incluye términos como "job", "empleo", "hiring" para evitar artículos y threads.
5. No incluyas: "search", "page", "portal", "reddit", "forum".
6. Responde ÚNICAMENTE con JSON válido: {"query": "..."}"""

_QUERY_REFINEMENT_USER_TEMPLATE = """## Perfil del candidato:
Skills: {skills}
Experiencia: {experience}

Genera una query de búsqueda específica para encontrar ofertas de empleo individuales."""

_CLASSIFY_RESULTS_SYSTEM = """Eres un clasificador de resultados de búsqueda de empleo.

REGLAS ESTRICTAS:
1. Clasifica cada resultado como oferta individual de empleo o NO-oferta.
2. DESCARTAR: portales de listado (LinkedIn search page, Indeed search, Remote.co listing),
   artículos de blog, posts de Reddit/Forums, páginas de empresa sin vacante específica.
3. MANTENER: páginas específicas de UNA vacante con título, descripción, y requisitos.
4. Incluye en keep_indices SOLO los índices que sean ofertas individuales.
5. Responde ÚNICAMENTE con JSON válido: {"keep_indices": [0, 3, 7]}
6. Si TODOS los resultados son no-ofertas, responde: {"keep_indices": []}"""

_CLASSIFY_RESULTS_USER_TEMPLATE = """## Resultados de búsqueda:
{results}

Identifica cuáles son ofertas de empleo individuales (mantener) y cuáles no (descartar)."""

# Default minimum score for an offer to be persisted.
_DEFAULT_MIN_SCORE = 40

# Query template: interpolate the user's skills.
_SEARCH_QUERY_TEMPLATE = "jobs for {skills} remote"


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OfferRunResult:
    """Outcome of one ``run_offer_search`` invocation."""

    found: int = 0
    """Total results returned by Tavily."""
    new_offers: int = 0
    """Offers actually persisted (after dedup + threshold filter)."""
    skipped_stale: bool = False
    """``True`` when staleness check prevented the Tavily call."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_offer_search(
    user_id: int,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    search_client,  # ``TavilyOfferSearchClient`` or test mock
    embedding_provider: LLMProvider,
    llm_provider: LLMProvider | None = None,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> OfferRunResult:
    """Run the offer-search pipeline for one user.

    Args:
        user_id: Primary key of the user to process.
        session_factory: Async session maker (injected for testability).
        settings: Application settings (``resolved_embedding_model``,
            ``offer_search_max_results``, ``offer_search_min_score``).
        search_client: Tavily client (or test mock).
        embedding_provider: Provider that produces embeddings (Gemini, HF,
            or mock — must implement ``LLMProvider``).
        llm_provider: Optional; reserved for future query-enhancement
            via LLM (not used in this slice).
        now: Reference timestamp (UTC); defaults to ``datetime.now(timezone.utc)``.
            Exists so tests get deterministic ordering without mocking ``datetime``.

    Returns:
        ``OfferRunResult`` with counts and the ``skipped_stale`` flag.

    Raises:
        ``OfferSearchTimeoutError`` and subclasses: Tavily errors propagate.
        ``SQLAlchemyError``: DB errors propagate.
    """
    from datetime import datetime as _dt

    if now is None:
        now = _dt.now(UTC)

    t0 = time.monotonic()

    # Step 1: load user + profile.
    user, profile = await _get_user_and_profile(user_id, session_factory)

    if profile is None:
        logger.warning(
            "offer_search_no_profile",
            user_id=user_id,
        )
        return OfferRunResult(found=0, new_offers=0, skipped_stale=False)

    # Step 2: staleness check (before any I/O). A manual run passes
    # force=True: explicit user intent to search NOW overrides the
    # frequency window — the staleness gate is for the automatic catch-up.
    prefs = get_offer_prefs(user)
    if not force and is_stale(user, prefs, now):
        # Not stale yet — skip the search call and record the decision.
        logger.info(
            "offer_search_run",
            user_id=user_id,
            found=0,
            new_offers=0,
            skipped_stale=True,
            duration_ms=round((time.monotonic() - t0) * 1000),
        )
        return OfferRunResult(found=0, new_offers=0, skipped_stale=True)

    # Step 3a: build base query from skills.
    base_query = _build_query(profile)

    # Step 3b: optionally refine query with LLM.
    use_llm_query = getattr(settings, "offer_search_llm_query", True)
    if use_llm_query and llm_provider is not None:
        query = await _refine_query_with_llm(llm_provider, profile)
        logger.info(
            "offer_search_query_refined",
            user_id=user_id,
            base_query=base_query,
            refined_query=query,
        )
    else:
        query = base_query

    max_results = getattr(settings, "offer_search_max_results", 10)

    # Step 4: parse include_domains from settings (comma-separated string → list).
    include_domains: list[str] | None = None
    domains_setting = getattr(settings, "offer_search_include_domains", None)
    if domains_setting and isinstance(domains_setting, str) and domains_setting.strip():
        include_domains = [d.strip() for d in domains_setting.split(",") if d.strip()]

    # Step 5: Tavily search (errors propagate).
    raw_results: list[OfferSearchResult] = await search_client.search(
        query, max_results=max_results, include_domains=include_domains
    )
    found = len(raw_results)

    if found == 0:
        # No results — still record the run so we don't re-query immediately.
        await _update_last_run_at(user_id, session_factory, prefs, now)
        logger.info(
            "offer_search_run",
            user_id=user_id,
            found=0,
            new_offers=0,
            skipped_stale=False,
            duration_ms=round((time.monotonic() - t0) * 1000),
        )
        return OfferRunResult(found=0, new_offers=0, skipped_stale=False)

    # Step 5b: optionally classify results with LLM to filter out portal pages.
    use_llm_classify = getattr(settings, "offer_search_llm_classify", True)
    if use_llm_classify and llm_provider is not None:
        raw_results = await _classify_results_with_llm(llm_provider, raw_results)
        logger.info(
            "offer_search_results_classified",
            user_id=user_id,
            original_count=found,
            classified_count=len(raw_results),
        )
        # Update found count to reflect filtered results
        found = len(raw_results)
        if found == 0:
            await _update_last_run_at(user_id, session_factory, prefs, now)
            logger.info(
                "offer_search_run",
                user_id=user_id,
                found=0,
                new_offers=0,
                skipped_stale=False,
                duration_ms=round((time.monotonic() - t0) * 1000),
            )
            return OfferRunResult(found=found, new_offers=0, skipped_stale=False)

    # Step 6: profile embedding (re-embed on-demand).
    profile_emb = await _get_profile_embedding(
        profile, embedding_provider, settings, user_id
    )
    min_score = getattr(settings, "offer_search_min_score", _DEFAULT_MIN_SCORE)

    # Step 7: rank + filter.
    ranked = await _rank_results(raw_results, profile_emb, embedding_provider, min_score)

    # Step 7: deduplicate against existing URLs for this user.
    existing_urls: set[str] = await _get_existing_urls(user_id, session_factory)
    to_persist = [pair for pair in ranked if pair[1].url not in existing_urls]

    # Step 8: persist new offers.
    new_offers = await _persist_offers(
        user_id, to_persist, session_factory, query
    )

    # Step 9: record last run.
    await _update_last_run_at(user_id, session_factory, prefs, now)

    duration_ms = round((time.monotonic() - t0) * 1000)
    logger.info(
        "offer_search_run",
        user_id=user_id,
        found=found,
        new_offers=new_offers,
        skipped_stale=False,
        duration_ms=duration_ms,
    )

    return OfferRunResult(found=found, new_offers=new_offers, skipped_stale=False)


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------


async def _get_user_and_profile(
    user_id: int, session_factory: async_sessionmaker[AsyncSession]
) -> tuple[User, Profile | None]:
    """Load the User and their primary Profile (owner match, RLS respected)."""
    async with session_factory() as session:
        await set_rls_user(session, user_id, "job_seeker")

        # Load user (offer_preferences lives here).
        user = await session.get(User, user_id)
        if user is None:
            return _null_user(user_id), None

        # Load profile: most recent one for this owner.
        # Mirrors match.py: profiles filtered by owner_user_id.
        result = await session.execute(
            select(Profile)
            .where(Profile.owner_user_id == user_id)
            .order_by(Profile.updated_at.desc())
            .limit(1)
        )
        profile = result.scalar_one_or_none()

        # Detach from session so callers can use the objects after the
        # session closes (safe because we only read JSONB/Vector columns
        # that are already loaded; no lazy relationships are accessed).
        session.expunge_all()

        return user, profile


def _build_query(profile: Profile) -> str:
    """Build a Tavily query from the profile's skills.

    Extracts ``skills.items`` (list of strings) from the profile JSONB.
    Falls back to an empty list if the field is absent/malformed.
    """
    skills_list: list[str] = []
    raw_skills = getattr(profile, "skills", None)
    if isinstance(raw_skills, dict):
        raw_items = raw_skills.get("items")
        if isinstance(raw_items, list):
            skills_list = [str(s) for s in raw_items if s]

    if skills_list:
        skills_str = " ".join(skills_list)
        return _SEARCH_QUERY_TEMPLATE.format(skills=skills_str)

    return "remote jobs for developers"


async def _get_profile_embedding(
    profile: Profile,
    provider: LLMProvider,
    settings: Settings,
    user_id: int,
) -> list[float]:
    """Return the profile's embedding vector, re-embedding on-demand.

    Mirrors the on-demand re-embed logic in ``match.py``:
    - If ``embedding`` is NULL or ``embedding_model`` differs from
      ``settings.resolved_embedding_model``, re-embed the serialised
      profile text and return the new vector.
    - The updated ``embedding`` / ``embedding_model`` are NOT written
      back in this function (the cron pipeline is read-most); the
      caller can do so if needed.

    Returns:
        768-dim embedding vector as a plain ``list[float]``.
    """
    current_model = getattr(profile, "embedding_model", None)
    resolved = settings.resolved_embedding_model

    if profile.embedding is None or current_model != resolved:
        # Re-embed.
        payload = {
            "name": profile.name,
            "headline": profile.headline,
            "experience": profile.experience,
            "skills": profile.skills,
            "preferences": profile.preferences,
        }
        text_for_embed = json.dumps(payload, ensure_ascii=False, default=str)
        emb = await provider.generate_embedding(text_for_embed)
        logger.warning(
            "offer_search_profile_reembedded",
            user_id=user_id,
            embedding_model=emb.model,
        )
        return list(emb.vector)

    return list(profile.embedding)


async def _rank_results(
    raw_results: list[OfferSearchResult],
    profile_emb: list[float],
    provider: LLMProvider,
    min_score: int,
) -> list[tuple[int | None, OfferSearchResult]]:
    """Rank search results by cosine similarity to the profile embedding.

    Embeds every snippet, computes cosine similarity vs ``profile_emb``,
    discards results below ``min_score`` (score = round(similarity * 100)),
    and returns the surviving ``(score, result)`` pairs in descending score
    order — the score persists with the offer so the UI can show it.

    Falls back to the original list unranked (score ``None``) on any error
    (defensive).
    """
    if not raw_results:
        return []

    try:
        profile_vec = np.asarray(profile_emb, dtype=np.float64)
        if profile_vec.ndim != 1:
            return [(None, r) for r in raw_results]

        snippet_texts = [r.snippet or r.title for r in raw_results]

        # Embed all snippets in one shot.
        # For providers that lack batch embedding, sequential is fine
        # (snippet texts are short; overhead is acceptable).
        import inspect
        snippet_vectors: list[list[float]] = []
        for text in snippet_texts:
            result = provider.generate_embedding(text)
            # Support both sync (returns Embedding directly) and async
            # (returns awaitable) providers without using run_until_complete
            # inside an already-running loop.
            if inspect.iscoroutine(result):
                emb = await result
            else:
                emb = result
            snippet_vectors.append(list(emb.vector))

        if not snippet_vectors:
            return []

        snippet_arr = np.asarray(snippet_vectors, dtype=np.float64)

        # Cosine similarity: both vectors are L2-normalised in retrieval.py style.
        p_norm = profile_vec / (np.linalg.norm(profile_vec) + 1e-12)
        s_norm = snippet_arr / (np.linalg.norm(snippet_arr, axis=1, keepdims=True) + 1e-12)
        sims = s_norm @ p_norm

        scored: list[tuple[int, OfferSearchResult]] = []
        for i, sim in enumerate(sims):
            score = int(round(float(sim) * 100))
            if score >= min_score:
                scored.append((score, raw_results[i]))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    except Exception:
        # Degrade gracefully: if ranking fails, return all results unranked.
        return [(None, r) for r in raw_results]


async def _get_existing_urls(
    user_id: int, session_factory: async_sessionmaker[AsyncSession]
) -> set[str]:
    """Return the set of URLs already persisted for this user (RLS respected)."""
    async with session_factory() as session:
        await set_rls_user(session, user_id, "job_seeker")
        result = await session.execute(
            select(JobOffer.url).where(JobOffer.owner_user_id == user_id)
        )
        return {row[0] for row in result.fetchall() if row[0]}


async def _persist_offers(
    user_id: int,
    ranked: list[tuple[int | None, OfferSearchResult]],
    session_factory: async_sessionmaker[AsyncSession],
    search_query: str,
) -> int:
    """Persist new JobOffer rows (with their ranking score) and return the
    count inserted."""
    if not ranked:
        return 0

    async with session_factory() as session:
        await set_rls_user(session, user_id, "job_seeker")
        for score, r in ranked:
            row = JobOffer(
                owner_user_id=user_id,
                title=r.title or "",
                url=r.url,
                snippet=r.snippet or None,
                published_date=r.published_date or None,
                score=score,
                status="new",
                search_query=search_query,
            )
            session.add(row)
        await session.commit()
        return len(ranked)


async def _update_last_run_at(
    user_id: int,
    session_factory: async_sessionmaker[AsyncSession],
    prefs: OfferPrefs,
    now: datetime,
) -> None:
    """Write ``last_offer_run_at`` into the user's ``offer_preferences`` JSONB."""
    async with session_factory() as session:
        await set_rls_user(session, user_id, "job_seeker")
        user = await session.get(User, user_id)
        if user is None:
            return

        raw = user.offer_preferences
        if not isinstance(raw, dict):
            raw = {}

        raw["last_offer_run_at"] = now.isoformat()
        # Preserve the other preference fields exactly as they were;
        # re-serialise the whole dict so SQLAlchemy marks it dirty.
        user.offer_preferences = dict(raw)
        await session.commit()


# ---------------------------------------------------------------------------
# LLM helper functions
# ---------------------------------------------------------------------------


async def _refine_query_with_llm(
    llm_provider: LLMProvider,
    profile: Profile,
) -> str:
    """Refine the search query using LLM based on profile skills/experience.

    Uses the Groq provider's structured output pattern to generate a
    targeted search query for finding individual job offers.

    Falls back to the template-based query on any error.
    """
    import inspect

    skills_list: list[str] = []
    raw_skills = getattr(profile, "skills", None)
    if isinstance(raw_skills, dict):
        raw_items = raw_skills.get("items")
        if isinstance(raw_items, list):
            skills_list = [str(s) for s in raw_items if s]

    experience_text = getattr(profile, "experience", "") or ""

    user_prompt = _QUERY_REFINEMENT_USER_TEMPLATE.format(
        skills=", ".join(skills_list) if skills_list else "No skills listed",
        experience=experience_text[:500] if experience_text else "No experience listed",
    )

    try:
        result = llm_provider.generate_structured(
            system_prompt=_QUERY_REFINEMENT_SYSTEM,
            user_prompt=user_prompt,
            output_schema={"query": str},
        )
        # Support both sync and async providers
        if inspect.iscoroutine(result):
            structured = await result
        else:
            structured = result

        refined_query = structured.get("query") if isinstance(structured, dict) else None
        if refined_query and isinstance(refined_query, str) and refined_query.strip():
            return refined_query.strip()
    except Exception as e:
        logger.warning(
            "offer_search_query_refine_failed",
            error=str(e),
        )

    # Fallback: use template query
    if skills_list:
        return _SEARCH_QUERY_TEMPLATE.format(skills=" ".join(skills_list[:5]))
    return "remote jobs for developers"


async def _classify_results_with_llm(
    llm_provider: LLMProvider,
    results: list[OfferSearchResult],
) -> list[OfferSearchResult]:
    """Classify search results using LLM to filter out non-offer results.

    Uses the Groq provider's structured output pattern to identify which
    results are individual job offers vs portal pages, articles, etc.

    Returns the filtered list of results (indices that are actual offers).
    Falls back to returning all results on any error.
    """
    import inspect

    if not results:
        return results

    # Build result descriptions for the LLM
    result_descriptions = []
    for i, r in enumerate(results):
        result_descriptions.append(
            f"[{i}] Title: {r.title}\nSnippet: {r.snippet[:200]}..."
        )

    user_prompt = _CLASSIFY_RESULTS_USER_TEMPLATE.format(
        results="\n\n".join(result_descriptions)
    )

    try:
        result = llm_provider.generate_structured(
            system_prompt=_CLASSIFY_RESULTS_SYSTEM,
            user_prompt=user_prompt,
            output_schema={"keep_indices": list},
        )
        # Support both sync and async providers
        if inspect.iscoroutine(result):
            structured = await result
        else:
            structured = result

        if isinstance(structured, dict):
            keep_indices = structured.get("keep_indices")
            if isinstance(keep_indices, list):
                # Filter results to only keep those with indices in keep_indices
                filtered = [
                    results[i]
                    for i in keep_indices
                    if isinstance(i, int) and 0 <= i < len(results)
                ]
                if filtered:
                    return filtered
    except Exception as e:
        logger.warning(
            "offer_search_classify_failed",
            error=str(e),
        )

    # Fallback: return all results if classification fails
    return results


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------


def _null_user(user_id: int) -> User:
    """Return a minimal User stub for the "no row" path."""
    return User(
        id=user_id,
        email="",
        role="job_seeker",
        full_name="",
        password_hash="",
        offer_preferences=None,
    )
