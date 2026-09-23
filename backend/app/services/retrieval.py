"""
Semantic retrieval for the match flow (PR-C, issue #16).

Short-circuits with the full profile when the serialized text fits under
`retrieval_size_threshold_chars`; otherwise fragments the profile by
section.key, embeds each fragment via the configured HF provider, ranks
them by cosine similarity against the JD embedding, and returns the
top-K as a JSON-serializable `ProfileContext`.

Ranking is in-process with numpy (fragments live inside JSON columns, so
pgvector `<=>` is not directly applicable at this granularity). The HNSW
index at the profile level (PR-A, migration 002) is the right tool for
*profile-level* ranking, which is out of scope here.

Cache is a simple in-memory dict keyed by
`(profile_id, profile.updated_at, embedding_model)`. It survives across
requests within the same process (lifetime of `get_settings()`) and is
flushed implicitly when `updated_at` advances (any profile edit).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.models import Profile
from app.llm.base import LLMProvider

logger = get_logger("app.services.retrieval")

# Sections of the profile that we fragment for retrieval.
_FRAGMENT_SECTIONS: tuple[str, ...] = ("experience", "skills", "preferences")


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProfileContext:
    """Serializable profile context handed to the LLM prompt.

    `mode="complete"` means the full profile JSON was sent; `chunks_used`
    is `None`. `mode="retrieved"` means only the top-K fragments were
    sent; `chunks_used` is the number of fragments included.
    """

    mode: Literal["complete", "retrieved"]
    text: str
    chunks_used: int | None = None
    chunks: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


@dataclass
class _CacheEntry:
    fragments: list[dict[str, Any]]
    embeddings: np.ndarray  # shape (N, 1024)


_cache: dict[tuple[int, str, str], _CacheEntry] = {}


def _cache_key(profile: Profile, embedding_model: str) -> tuple[int, str, str]:
    """Cache key: profile identity + content fingerprint (updated_at) + model."""
    updated_iso = profile.updated_at.isoformat()
    return (int(profile.id or 0), updated_iso, embedding_model)


def clear_cache() -> None:
    """Drop all cached entries. Test-only convenience."""
    _cache.clear()


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def _fragment_text(text: str, target_chars: int) -> list[str]:
    """Split a text into ~`target_chars`-sized windows.

    The last window may be shorter. No overlap: retrieval is by fragment
    identity, not by sliding window. Empty / whitespace-only inputs
    return a single empty fragment so downstream code has stable indices.
    """
    text = text.strip()
    if not text:
        return [""]
    if len(text) <= target_chars:
        return [text]
    return [text[i : i + target_chars] for i in range(0, len(text), target_chars)]


def build_fragments(profile: Profile, target_chars: int) -> list[dict[str, Any]]:
    """Fragment the profile into retrievable chunks.

    For each section in `{experience, skills, preferences}`:
      * dict: one fragment per (key, value) pair, JSON-serialized.
      * list: one fragment per item, JSON-serialized.
      * scalar / None: skipped.

    If a serialized fragment is smaller than half of `target_chars`, we
    merge it with the next fragment in the same section to amortize the
    per-fragment embedding call. This keeps the fragment count small
    (single-digit) for typical profiles while preserving section origin.
    """
    fragments: list[dict[str, Any]] = []
    min_merge_chars = max(target_chars // 2, 64)

    for section in _FRAGMENT_SECTIONS:
        data = getattr(profile, section, None)
        if data is None:
            continue

        # Materialize one or more (origin, text) candidates for the section.
        candidates: list[tuple[str, str]] = []
        if isinstance(data, dict):
            for key, value in data.items():
                candidates.append(
                    (str(key), json.dumps({key: value}, ensure_ascii=False, default=str))
                )
        elif isinstance(data, list):
            for idx, item in enumerate(data):
                candidates.append(
                    (str(idx), json.dumps(item, ensure_ascii=False, default=str))
                )
        else:
            continue

        # Merge candidates that are too small with their next neighbor.
        merged: list[tuple[str, str]] = []
        buffer_text: str | None = None
        buffer_origin: list[str] = []

        def _flush() -> None:
            nonlocal buffer_text, buffer_origin
            if buffer_text is not None:
                merged.append(("+".join(buffer_origin), buffer_text))
                buffer_text = None
                buffer_origin = []

        for origin, text in candidates:
            if buffer_text is None:
                buffer_text = text
                buffer_origin = [origin]
                continue
            if len(buffer_text) < min_merge_chars:
                buffer_text = buffer_text + "\n" + text
                buffer_origin.append(origin)
                continue
            _flush()
            buffer_text = text
            buffer_origin = [origin]
        _flush()

        for origin, text in merged:
            for piece_idx, piece in enumerate(_fragment_text(text, target_chars)):
                fragments.append(
                    {
                        "section": section,
                        "index": origin,
                        "piece": piece_idx,
                        "text": piece,
                    }
                )

    return fragments


# ---------------------------------------------------------------------------
# Profile size
# ---------------------------------------------------------------------------


def profile_text_length(profile: Profile) -> int:
    """Total serialized length of all profile fields used for retrieval."""
    total = 0
    for field_name in ("experience", "skills", "preferences"):
        data = getattr(profile, field_name, None)
        if data is None:
            continue
        total += len(json.dumps(data, ensure_ascii=False, default=str))
    return total


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine similarity of each row of `a` against the row vector `b`.

    Both inputs are L2-normalized inside the function so the result is
    the dot product — robust against accidental re-normalization in the
    embedding provider.
    """
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-12)
    b_norm = b / (np.linalg.norm(b) + 1e-12)
    result = a_norm @ b_norm
    return result  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def retrieve_profile_context(
    profile: Profile,
    jd_embedding: list[float],
    settings: Settings,
    provider: LLMProvider,
    *,
    regenerate_profile_embedding: bool = False,
) -> ProfileContext:
    """Return a `ProfileContext` ready to be passed to the LLM prompt.

    Args:
        profile: The persisted profile (must be loaded from the DB).
        jd_embedding: The 1024-dim embedding of the JD (already computed
            upstream in the match flow).
        settings: Application settings (threshold + top-K + fragment size).
        provider: The LLM provider whose `generate_embedding` we use to
            embed fragments.
        regenerate_profile_embedding: When True, the caller (match flow)
            has already determined that the profile's stored embedding is
            stale or missing. We embed fragments regardless because the
            profile vector itself is not used for fragment ranking — we
            only need the JD embedding for similarity. The flag is
            honored for logging parity with the on-demand re-embedding
            path in `match.py`.

    Behavior:
      * `profile_text_length(profile) <= threshold` → mode="complete".
      * Else: embed each fragment (cached by profile content + model),
        rank by cosine similarity to JD embedding, take top-K.

    Errors during embedding or ranking degrade to mode="complete" with a
    warning log — the match endpoint must never break because retrieval
    failed (spec: "Fallback por error de pgvector" / embedding ausente).
    """
    text_length = profile_text_length(profile)
    threshold = settings.retrieval_size_threshold_chars

    if text_length <= threshold:
        full_context = _full_profile_text(profile)
        return ProfileContext(mode="complete", text=full_context, chunks_used=None)

    # Retrieval path.
    cache_key = _cache_key(profile, settings.hf_embedding_model)
    cached = _cache.get(cache_key)

    if regenerate_profile_embedding:
        logger.warning(
            "profile_embedding_stale_for_retrieval",
            profile_id=profile.id,
            embedding_model=settings.hf_embedding_model,
        )

    if cached is None:
        fragments = build_fragments(profile, settings.retrieval_fragment_target_chars)
        if not fragments:
            # No fragments to rank — fall back to complete.
            logger.warning(
                "retrieval_no_fragments",
                profile_id=profile.id,
            )
            return ProfileContext(
                mode="complete",
                text=_full_profile_text(profile),
                chunks_used=None,
            )

        try:
            vectors = await _embed_fragments(fragments, provider)
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning(
                "retrieval_embedding_failed",
                profile_id=profile.id,
                error=str(exc)[:200],
            )
            return ProfileContext(
                mode="complete",
                text=_full_profile_text(profile),
                chunks_used=None,
            )

        cached = _CacheEntry(fragments=fragments, embeddings=vectors)
        _cache[cache_key] = cached

    jd_vec = np.asarray(jd_embedding, dtype=np.float64)
    if jd_vec.ndim != 1 or jd_vec.shape[0] != cached.embeddings.shape[1]:
        logger.warning(
            "retrieval_jd_dim_mismatch",
            expected_dim=cached.embeddings.shape[1],
            got_dim=int(jd_vec.shape[0]) if jd_vec.ndim > 0 else 0,
        )
        return ProfileContext(
            mode="complete",
            text=_full_profile_text(profile),
            chunks_used=None,
        )

    similarities = _cosine_similarity(cached.embeddings, jd_vec)
    top_k = max(1, settings.retrieval_top_k)
    k = min(top_k, len(cached.fragments))
    top_indices = np.argsort(-similarities)[:k]

    selected = [cached.fragments[int(i)] for i in top_indices]
    text = _render_retrieved(selected)

    return ProfileContext(
        mode="retrieved",
        text=text,
        chunks_used=len(selected),
        chunks=selected,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _full_profile_text(profile: Profile) -> str:
    """Serialize the full profile as the prompt context."""
    payload = {
        "id": profile.id,
        "name": profile.name,
        "headline": profile.headline,
        "experience": profile.experience,
        "skills": profile.skills,
        "preferences": profile.preferences,
    }
    return json.dumps(payload, ensure_ascii=False, default=str)


def _render_retrieved(fragments: list[dict[str, Any]]) -> str:
    """Render selected fragments as a readable block for the prompt."""
    lines: list[str] = []
    for frag in fragments:
        section = frag["section"]
        origin = frag["index"]
        piece = frag.get("piece", 0)
        header = f"[{section}/{origin}/piece{piece}]"
        lines.append(header)
        lines.append(frag["text"])
        lines.append("")
    return "\n".join(lines).strip()


async def _embed_fragments(
    fragments: list[dict[str, Any]],
    provider: LLMProvider,
) -> np.ndarray:
    """Embed each fragment via the provider, returning a (N, D) array."""
    vectors: list[list[float]] = []
    for frag in fragments:
        embedding = await provider.generate_embedding(frag["text"])
        vectors.append(list(embedding.vector))
    arr = np.asarray(vectors, dtype=np.float64)
    return arr
