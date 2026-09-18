# Education OS â€” Project Handoff

## Current handoff point

Education OS is a security-sensitive, multi-tenant Institutional Intelligence & Action Platform. The last committed source is `57aea73c71a403c2b85024dc0e554c011fa258a7` (`feat(m25): expand governed read-only agents`), which closes M25-2 only. The local database is at `0036_m25_run_explainer`. M25-3A through M25-3D are validated but uncommitted and ready for one source-control closure commit.

## M25-3 result

- M25-3A: `m25.evidence.v1` creates typed, bounded, canonical, SHA-256-manifested, tenant/subject-hashed Evidence Packs with opaque citations.
- M25-3B: tenant-scoped immutable model configuration, deterministic routing, advisory-lock budget admission, append-only provider audit, fake-only execution, and deterministic fallback.
- M25-3C: L0 `integration_run_explainer` uses typed `integration_run_id` and `SUMMARY`/`ERRORS`/`OUTCOME`, one M24 inspect tool call, strict output parsing, and a deterministic verifier.
- M25-3D: controlled fake-provider pilot PASS. Run `0f706b7f-de79-4bde-ba15-a3b0795bc67a` completed in `FAKE_PROVIDER` mode with one provider call, valid citation verification, and no domain mutation.
- M25-3E: optional live-provider pilot not executed.

The successful fake provider audit recorded `SUCCEEDED`, null normalized error, input/output tokens `1`/`1`, 30 micro-USD cost, 0 ms latency, and request/response/evidence/prompt hashes. It persists neither raw prompt nor raw response. Its budgets reserved 1,000, consumed 30, and released 970 micro-USD in RUN, TENANT_DAY, and TENANT_MONTH scopes.

Negative controls pass: duplicate or fabricated citations are rejected; malformed output, timeout, rate limit, unavailability, auth error, context overflow, and budget denial use deterministic fallback. Secondary access to a primary run returns safe 404/non-disclosure; replay returns the existing governed run without another provider call, budget reservation, domain tool execution, or mutation.

## Architecture and boundaries

The shared M25 path is: authenticated request â†’ principal context â†’ registries/policy â†’ deterministic planner â†’ closed typed gateway â†’ M21/M22/M24 read boundary â†’ Evidence Pack â†’ budget admission â†’ deterministic router â†’ fixed adapter â†’ strict parser â†’ deterministic verifier â†’ append-only audit â†’ M18 lifecycle event.

M21/M22/M24 remain authoritative for domain data and deterministic/statistical calculations. Providers only explain bounded evidence; they cannot choose tenants, permissions, tools, actions, or authoritative statistics. Never weaken FORCE RLS, effective-permission checks, closed registries, composite tenant links, deterministic planner/verifier, append-only audit, advisory-lock admission, or integer micro-USD accounting.

Existing `integration_run_advisor`, `student_timeline_advisor`, and `institution_intelligence_advisor` remain `DETERMINISTIC_ONLY`.

## Provider status

Only in-process `fake` is executable. OpenAI, Anthropic, and local are known but non-executable keys; network calls and API-credit consumption are zero. This does not close the historical M23 live-provider HOLD EXTERNAL caused by API-credit/HTTP-429 availability.

## Important locations

- `backend/app/modules/agents/`: M25 control plane, evidence, prompt, router, budget, providers, execution, verifier.
- `backend/app/modules/integrations/`: M24 authoritative run read boundary.
- `backend/app/modules/events/`: M18 lifecycle event/outbox path.
- `backend/alembic/versions/0035_m25_governed_provider_execution.py` and `0036_m25_run_explainer.py`: applied M25-3 schema/config.
- `backend/tests/unit/test_m25_*.py`: focused M25 contracts.

## Next step

Perform the approved single M25-3 source-control commit. Do not start an optional live-provider pilot, frontend work, Mentor OS, L1+ actions, generic tools, or generic HTTP as part of that commit.

## Standard checks

Before changing code, read the continuity documents and verify Git HEAD/status plus Alembic source/current. Run focused module tests, directed M21/M22/M23 coverage, full backend regression, Ruff, `py_compile`, Alembic head/current, and `git diff --check`. Provider tests use fake/injected adapters only.
