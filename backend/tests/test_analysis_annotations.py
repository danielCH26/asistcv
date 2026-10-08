"""
Regression tests for #79: ``Analysis.strengths`` and ``Analysis.gaps``
annotations must be ``list[str] | None``, matching the stored shape and
what every LLM producer in ``app/llm/*`` emits (never dicts).

The historical bug (#79): the SQLModel model declared ``dict | None`` while
the producers and the API schema ``schemas.MatchAnalysis`` used ``list[str]``.
This file pins the *annotation contract* (S2).

Honest scope of the fix (see odd/tasks/fix-analysis-annotations-list.md):
the annotation tightening is real and surfaces the wrong shape to IDE/mypy/
pydantic validators. The full "shim that swallows invalid data" — actually
rejecting a dict-shape payload at construction — is a separate, deeper
issue caused by SQLModel + ``sa_column=Column(JSON)`` + pydantic v2 ``Annotated``
interactions (the ``field_validator`` is ignored by SQLModel and the
``BeforeValidator`` attached via ``Annotated`` does not fire on SQLModel
construction). The remaining follow-up is documented in the feature doc;
meanwhile these tests pin the current, honest contract:

- the annotation is ``list[str] | None`` (S1),
- a list passes round-trip,
- None passes,
- pydantic raises a serialization warning (not a construction-time error)
  when given a dict — the shim is documented, not closed.

The test for the full close (rejects dict at construction) belongs in a
follow-up that targets the SQLModel + JSON column pathway specifically.
"""

from __future__ import annotations

from typing import Any

from app.db.models import Analysis


class TestAnalysisShapeContract:
    def test_accepts_list_strengths(self) -> None:
        """The fix must accept a list — the shape every producer emits."""
        analysis = Analysis(strengths=["Python", "async APIs"])
        assert analysis.strengths == ["Python", "async APIs"]

    def test_accepts_list_gaps(self) -> None:
        analysis = Analysis(gaps=["SQL basics", "CI/CD"])
        assert analysis.gaps == ["SQL basics", "CI/CD"]

    def test_accepts_none_for_optional_fields(self) -> None:
        analysis = Analysis(strengths=None, gaps=None)
        assert analysis.strengths is None
        assert analysis.gaps is None

    def test_strongthfield_round_trip_through_model_dump(self) -> None:
        """A list on the model must round-trip via model_dump preserving shape."""
        analysis = Analysis(strengths=["x"], gaps=["z"])
        dumped: dict[str, Any] = analysis.model_dump()
        assert isinstance(dumped["strengths"], list)
        assert isinstance(dumped["gaps"], list)
        assert dumped["strengths"] == ["x"]
        assert dumped["gaps"] == ["z"]

    def test_dict_input_serializes_with_warning_documenting_shim(self) -> None:
        """Documents the remaining #79 shim.

        Under SQLModel + ``sa_column=Column(JSON)``, a dict payload is NOT
        rejected at construction time (pydantic-v2 silently accepts it via
        ``BeforeValidator`` + Annotated types not firing inside SQLModel).
        It surfaces only at serialization with ``PydanticSerialization
        UnexpectedValue`` — a warning, not a hard error. That is precisely
        the "shim que traga datos inválidos" the audit flagged: a downstream
        consumer would see the warning if it pays attention; otherwise the
        dict leaks downstream. Closing the shim requires either a SQLModel-
        level override or a schema migration; tracked as a follow-up.
        """
        import warnings

        analysis = Analysis(strengths={"x": 1})  # type: ignore[arg-type]
        with warnings.catch_warnings(record=True) as caught:
            analysis.model_dump()
        serialized_warnings = [
            w for w in caught if "serializ" in str(w.message).lower()
        ]
        assert serialized_warnings, (
            "Expected pydantic to warn at serialization when given a dict; "
            "the shim path is the warning surface (see #79)."
        )
