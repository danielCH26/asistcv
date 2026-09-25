```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:601f8d9f99e96ebc8c11b8e3a844043ee2ce24156455d0688bc07480c2138c30
verdict: pass_with_warnings
blockers: 0
critical_findings: 0
requirements: 7/7
scenarios: 19/19
test_command: uv run pytest -q --tb=short (run1) + uv run pytest -q (run2, stability)
test_exit_code: 0
test_output_hash: sha256:95b6760f7c535ccf51bc949ae1b7385cbab4dde18a5552d5d51c3b5755b3e535
build_command: uv run mypy app (+ uv run ruff check app tests, exit 0)
build_exit_code: 0
build_output_hash: sha256:e2479fb5ce6c136224daf202ea4ddc07bec5455a164ed2676d6effeb7b5887d7
```

## Verification Report

**Change**: sprint-2-user-profile (BILLING scope final verify — PR5 focused, round 4)
**Mode**: Standard (openspec-file persistence)

### Completeness
| Metric | Value |
|--------|-------|
| Billing tasks E1–E7 | 7/7 checked in tasks.md (E7 ticked since round 3) |
| Round-3 delta claims | All confirmed at source (see Correctness) |
| Billing scenarios | 19/19 accounted for at runtime: 18 passing covering tests + 1 justified skip (documented in-test, pre-accepted descope) |

### Build & Tests Execution
**Build**: Passed
```text
uv run ruff check app tests -> All checks passed! (exit 0)
uv run mypy app -> Success: no issues found in 51 source files (exit 0)
```

**Tests**: ✅ 225 passed / ❌ 0 failed / ⚠️ 1 skipped — stable across 2 consecutive runs
```text
run 1 (pytest -q --tb=short) -> 225 passed, 1 skipped, 31 warnings in 297.03s (exit 0)
run 2 (pytest -q, stability) -> 225 passed, 1 skipped, 31 warnings in 257.45s (exit 0)
```
The single skip is `test_pse_payment_records_currency` (`@pytest.mark.skip`), reason documented in its docstring.

**Coverage**: ➖ Not available (no coverage threshold configured for this run)

### Spec Compliance Matrix (specs/billing/spec.md — 7 requirements, 19 scenarios)
| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| Catálogo de planes | Plan job_seeker mensual | `test_billing.py > test_plans_endpoint_seeker_tier` | ✅ COMPLIANT |
| Catálogo de planes | Plan recruiter Starter | `test_billing.py > test_plans_endpoint_recruiter_starter_limits` | ✅ COMPLIANT |
| Catálogo de planes | Plan recruiter Agency | `test_billing.py > test_plans_endpoint_recruiter_agency_unlimited` | ✅ COMPLIANT |
| Creación de Checkout Session | Checkout con tarjeta (job_seeker) | `test_billing.py > test_checkout_creates_session_seeker` | ✅ COMPLIANT |
| Creación de Checkout Session | Checkout con PSE (recruiter CO) | `test_billing.py > test_checkout_pse_payment_method` | ✅ COMPLIANT |
| Creación de Checkout Session | Idempotencia de checkout | `test_billing.py > test_checkout_idempotency_key_passthrough` | ⚠️ PARTIAL — passthrough asserted; same-URL guarantee delegated to Stripe server-side idempotency (code comment in billing.py checkout; accepted round 3) |
| Webhooks firmados e idempotentes | Verificación de firma | `test_stripe_webhook.py > test_webhook_invalid_signature_400` | ✅ COMPLIANT |
| Webhooks firmados e idempotentes | Evento duplicado | `test_stripe_webhook.py > test_webhook_duplicate_event_already_processed` | ✅ COMPLIANT |
| Webhooks firmados e idempotentes | checkout.session.completed | `test_stripe_webhook.py > test_checkout_completed_activates_subscription` | ✅ COMPLIANT |
| Webhooks firmados e idempotentes | customer.subscription.deleted | `test_stripe_webhook.py > test_subscription_deleted_downgrades_to_free` | ✅ COMPLIANT |
| Webhooks firmados e idempotentes | invoice.payment_failed | `test_stripe_webhook.py > test_payment_failed_past_due_and_notification` | ✅ COMPLIANT |
| Suscripción activa y límites | Usuario con plan activo | `test_billing.py > test_subscription_overage_positive_when_over` (+ `test_subscription_shape`) | ✅ COMPLIANT |
| Suscripción activa y límites | Usuario free (job_seeker) | `test_billing.py > test_subscription_shape` (plan_id=free, status=active, limits=3) | ✅ COMPLIANT |
| Suscripción activa y límites | Reclutador Starter agotado | `test_billing.py > test_recruiter_starter_at_50_402` (+ `test_match_at_limit_402`) | ✅ COMPLIANT |
| Cancelación desde el portal | Portal session exitoso | `test_billing.py > test_portal_session_success` | ✅ COMPLIANT |
| Cancelación desde el portal | Usuario sin customer | `test_billing.py > test_portal_no_customer_400` | ✅ COMPLIANT |
| Conteo de uso mensual | Incremento tras match | `test_billing.py > test_match_under_limit_200_and_increments` (+ `test_match_failed_does_not_consume`) | ✅ COMPLIANT |
| Conteo de uso mensual | Reset mensual | `test_billing.py > test_usage_period_rollover` | ✅ COMPLIANT |
| Monedas y payouts soportados | Pago PSE en USD | `test_billing.py > test_pse_payment_records_currency` | ⚠️ SKIPPED (justified) — checkout.session.completed writes no Payment row and no invoice.paid handler exists; payments persistence descoped to follow-up; reason documented in test docstring |

**Compliance summary**: 19/19 scenarios accounted for: 16 full ✅ COMPLIANT + 1 ⚠️ PARTIAL (idempotency passthrough, Stripe-side guarantee accepted) + 1 ⚠️ PARTIAL/active pair for active-plan shape + 1 ⚠️ SKIPPED-by-design (PSE USD — payments persistence descoped to follow-up, reason documented in test docstring lines 601–610). Requirement "Monedas y payouts soportados" is carried entirely by the skipped scenario → covered only as a documented descope (WARNING 1).

### Correctness (Static Evidence — round-4 delta claims)
| Claim | Status | Evidence |
|-------|--------|----------|
| 7 new tests (plans ×3, portal ×2, rollover, PSE-skip) | Confirmed | test_billing.py:445, 469, 484, 502, 540, 553, 602 — 6 active + 1 skip |
| `stripe.billing_portal.Session.create` fix | Confirmed | app/services/stripe_client.py:106 — `s.billing_portal.Session.create(...)`; zero `billingportal` references in app code (single hit is a test docstring, see WARNING 4) |
| `check_and_increment` deleted | Confirmed | grep over backend (app + tests): no matches |
| match.py:16 docstring fixed | Confirmed | "check_limit before the match runs; increment_usage is called only after the match succeeds, so failed matches never consume credits" |
| match.py endpoint docstring (~line 81) fixed | Confirmed | lines 81–84: check (read-only) → run → increment ONLY on success → 402 PLAN_LIMIT_REACHED |
| tasks.md E7 ticked | Confirmed | tasks.md line 202 `- [x] E7. Tests PR5` |
| Stale test_tier_runtime pyc cleaned | Confirmed | no `test_tier_runtime*` artifact under backend (only app-module `tier_limits.cpython-312.pyc`, expected) |
| Stripe-side idempotency comment | Confirmed | code comment present in billing.py checkout path (accepted round 3) |

Increment-on-success wiring verified end-to-end: check_limit (match.py:93, read-only) → pipeline → persist (single tx, :249) → increment_usage (:258–266, separate post-commit tx, best-effort). Failed matches never consume credits (covered by `test_match_failed_does_not_consume`).

### Coherence (Design — billing delta)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| Tier enforcement 402 + counter on success | ✅ Yes | Matches spec scenarios 17–18 and current docstrings; increment is post-commit best-effort (safer direction than E6 AC letter — accepted in round 3) |
| Webhook dedupe/four handlers | ✅ Yes | Path differs from spec literal (see WARNING 2) |

### Issues Found
**CRITICAL**: None
**WARNING**:
1. PSE USD scenario (Monedas requirement) has no runtime evidence — payments persistence descoped to follow-up; skip reason documented in test (lines 601–610).
2. Webhook route is `/api/v1/webhooks/stripe` vs spec's `/v1/billing/webhook` — reconcile at spec sync during archive.
3. Checkout idempotency coverage is passthrough-level; same-URL guarantee rests on Stripe server-side idempotency (comment in billing.py).
4. Stale prose: `test_portal_session_success` docstring (test_billing.py:507–510) still describes the `billingportal` bug as latent/out-of-scope, but the bug was fixed this round in stripe_client.py:106 — docstring is now outdated (cosmetic).
5. E6 AC letter deviation (pre-existing, accepted): usage increment runs in a separate post-commit transaction rather than inside the match transaction (fails safe: undercount possible, never overcount).

### Verdict
PASS WITH WARNINGS (billing scope verified-with-caveats)
Suite green and stable ×2 (225 passed / 0 failed / 1 skipped; ruff + mypy clean), all round-3 deltas confirmed at source (7 new tests, portal fix, docstrings, E7 ticked, dead code deleted, pyc cleaned), and 18/19 billing scenarios have passing covering tests — the single skip is justified and documented (payments persistence = follow-up). Remaining caveats are the accepted descope notes plus one stale test docstring; none block the next phase.
