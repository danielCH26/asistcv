# Feature: analysis-annotations-list (#79)

> **Issue**: #79 (P2, audit C6 follow-up)
> **Branch**: `fix/analysis-annotations-list`
> **Scope**: 2-line fix + 1 test on a backend annotation bug discovered during sprint-adapt-cv-outreach verification.

---

## Specs

### S1 — Annotations match the stored shape

Issue verbatim: *"Analysis.strengths/gaps anotados dict guardando listas, enmascarado por un shim que traga datos inválidos."*

- `backend/app/db/models.py` `Analysis.strengths` and `Analysis.gaps`: `dict | None` → `list[str] | None`.
- The SQLModel `RecruiterAnalysis` model already uses `list[str] | None` with an explanatory docstring ("populated from this column"). Apply the same convention to `Analysis`.
- No DB migration. The underlying column is JSON; the wire type was already `list[str]` (LLM producers in `app/llm/*` only emit arrays). The fix is annotation-only — the stored data has always been arrays, only the declared type was permissive (accepted both dict and list at parse time).

### S2 — Test pins the contract

A new test (`tests/test_analysis_annotations.py`) that loads an `Analysis` instance from a row whose `strengths`/`gaps` JSON is a list and asserts:
- `Analysis(strengths=["a","b"]).strengths` round-trips as `list[str]`.
- Re-asserts (sanity, pre-fix sanity): if you construct with `strengths={...}` a dict, pydantic-v2's strict-ish mode rejects (or coerces). The test class documents that the only valid shape is `list[str] | None`.

The shim problem — that a dict could pass parse and silently corrupt downstream rendering — is fixed by tightening the annotation: pydantic raises on dict input to the new field.

---

## Tasks

| ID | Title | Commit |
|---|---|---|
| T1 | RED test (asserts current permissive behavior is dict-accepted) → fix models.py L130-134 + drop redundant assert | `fix(models): tighten Analysis.strengths/gaps annotations to list[str]` |

---

## Log

### L1 — User's verbatim request (2026-10-07)

> "Sigamos desarrollando, que viene"

(Within the standing directive: v1.0 milestone shipped + QA-verified. Board cleanup flaggeó que #79 sigue abierta y es un quick win real.)

### L2 — Pre-fix mapping

- `backend/app/db/models.py:130-134` `Analysis.strengths: dict | None` / `gaps: dict | None` (the bug)
- `backend/app/db/models.py:524-530` `RecruiterAnalysis.strengths: list[str] | None` (already correct — model was fixed in a prior session for C3, comment says "populated from this column")
- LLM producers in `backend/app/llm/{base,composite,groq_provider,mock}.py` all emit lists — never dicts. The producers are consistent.
- Pydantic schema `backend/app/schemas.py:13` already says `list[str]`. The mismatch is purely in the SQLModel model.
- Baseline tests: 19 passed in `test_match_persistence.py` + `test_analyses.py`.

### L3 — Evidence / commits (appended as work progresses)

- TBD per task.