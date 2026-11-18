"""Reference-date grounding for the Groq prompts.

A hosted LLM has no reliable sense of "today": it answers relative to its
training cutoff, so a CV whose latest role ends after that cutoff reads as a
"future date", and recency/overlap/"years of experience" get computed against
a stale now. Every LLM call must therefore carry the server's current UTC date.

Rendering is tested with an injected ``now`` (same convention as
``offer_search_worker(now=...)``) so nothing here depends on the wall clock;
the wiring tests assert the header plus an ISO date, not a particular day.
"""

import re
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.llm.groq_provider import (
    REFERENCE_DATE_HEADER,
    SYSTEM_PROMPT,
    GroqProvider,
    reference_date_block,
    with_reference_date,
)

ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

MATCH_PAYLOAD = {"score": 75, "energy_level": "high", "reasoning": "ok"}
AUDIT_PAYLOAD = {"score": 75}
ADAPTATION_PAYLOAD = {"full_name": "Ana Perez"}


@pytest.fixture
def provider() -> GroqProvider:
    return GroqProvider(api_key="test_api_key", model="llama-3.3-70b-versatile")


def test_reference_date_block_renders_the_injected_day():
    """The block must carry the exact day it was given, not 'today' by chance."""
    block = reference_date_block(datetime(2026, 10, 20, 15, 0, tzinfo=UTC))

    assert REFERENCE_DATE_HEADER in block
    assert "2026-10-20" in block


def test_reference_date_block_defaults_to_the_server_clock():
    """With no ``now`` the block must reflect the real UTC date."""
    assert datetime.now(UTC).date().isoformat() in reference_date_block()


def test_reference_date_block_tells_the_model_to_ignore_its_own_cutoff():
    """The instruction is the whole point: without it the date is ignored."""
    block = reference_date_block(datetime(2026, 10, 20, tzinfo=UTC))

    assert "fecha de corte de tu entrenamiento" in block
    assert "posterior a hoy es una fecha futura" in block


def test_with_reference_date_preserves_the_prompt_and_its_json_contract():
    """Appending must not disturb the literal JSON braces of the system prompt."""
    rendered = with_reference_date(SYSTEM_PROMPT, datetime(2026, 10, 20, tzinfo=UTC))

    assert rendered.startswith(SYSTEM_PROMPT)
    assert "2026-10-20" in rendered
    # Literal braces that would break a naive str.format-based fix.
    assert '"score": 0-100' in rendered
    assert '"energy_level": "low|medium|high"' in rendered


def test_with_reference_date_does_not_mutate_the_module_constant():
    """A stale date baked into the constant would outlive the day it was set."""
    before = SYSTEM_PROMPT

    with_reference_date(SYSTEM_PROMPT, datetime(2026, 10, 20, tzinfo=UTC))

    assert SYSTEM_PROMPT == before
    assert REFERENCE_DATE_HEADER not in SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_generate_match_sends_the_reference_date(provider: GroqProvider):
    """POST /v1/match: without the date the model judges recency against its cutoff."""
    spy = AsyncMock(return_value=MATCH_PAYLOAD)
    with patch.object(GroqProvider, "_complete_json", new=spy):
        await provider.generate_match("JD text", {"skills": ["Python"]})

    system_prompt = spy.call_args.args[0]
    assert REFERENCE_DATE_HEADER in system_prompt
    assert ISO_DATE.search(system_prompt)


@pytest.mark.asyncio
async def test_generate_cv_audit_sends_the_reference_date(provider: GroqProvider):
    """The audit prompt explicitly checks 'Fechas inconsistentes': it needs the date."""
    spy = AsyncMock(return_value=AUDIT_PAYLOAD)
    with patch.object(GroqProvider, "_complete_json", new=spy):
        await provider.generate_cv_audit("CV text")

    system_prompt = spy.call_args.args[0]
    assert REFERENCE_DATE_HEADER in system_prompt
    assert ISO_DATE.search(system_prompt)


@pytest.mark.asyncio
async def test_generate_adaptation_sends_the_reference_date(provider: GroqProvider):
    """The adapter rewrites bullets but keeps dates: it still needs the date."""
    spy = AsyncMock(return_value=ADAPTATION_PAYLOAD)
    with patch.object(GroqProvider, "_complete_json", new=spy):
        await provider.generate_adaptation({"full_name": "Ana Perez"}, "JD text")

    system_prompt = spy.call_args.args[0]
    assert REFERENCE_DATE_HEADER in system_prompt
    assert ISO_DATE.search(system_prompt)
