# Education OS - Project Handoff

## Current handoff point

Education OS is a security-sensitive, multi-tenant Institutional Intelligence & Action Platform. M25 - Agentic Control Plane is CLOSED at `bd0fbaa719eae4884d9a6c3ab8600939e88bb433` (`feat(m25): add governed provider-backed explainer`), tagged `m25-governed-provider-explainer-v0.25.3`, and remotely backed up and verified on `origin` (`FabianBurga/education-os`). The local database is at `0036_m25_run_explainer`. The next active milestone is M26 - Human Experience Layer / Mentor OS.

## M25 result

- M25-1 and M25-2: CLOSED.
- M25-3A: `m25.evidence.v1` creates typed, bounded, canonical, SHA-256-manifested, tenant/subject-hashed Evidence Packs with opaque citations.
- M25-3B: tenant-scoped immutable model configuration, deterministic routing, advisory-lock budget admission, append-only provider audit, fake-only execution, and deterministic fallback.
- M25-3C: L0 `integration_run_explainer` uses typed `integration_run_id` and `SUMMARY`/`ERRORS`/`OUTCOME`, one M24 inspect tool call, strict output parsing, and a deterministic verifier.
- M25-3D: controlled fake-provider pilot PASS. Run `0f706b7f-de79-4bde-ba15-a3b0795bc67a` completed in `FAKE_PROVIDER` mode with one provider call, valid citation verification, and no domain mutation.
- M25-3E: OPTIONAL / NOT EXECUTED.

The successful fake-provider audit recorded `SUCCEEDED`, null normalized error, input/output tokens `1`/`1`, 30 micro-USD cost, 0 ms latency, and request/response/evidence/prompt hashes. It persists neither raw prompt nor raw response. Its budgets reserved 1,000, consumed 30, and released 970 micro-USD in RUN, TENANT_DAY, and TENANT_MONTH scopes. Tenant isolation and replay safety passed; replay returns the existing governed run without another provider call, budget reservation, domain tool execution, or mutation.

Negative controls pass: duplicate or fabricated citations are rejected; malformed output, timeout, rate limit, unavailability, auth error, context overflow, and budget denial use deterministic fallback. Secondary access to a primary run returns safe 404/non-disclosure.

## Architecture and boundaries

The shared M25 path is: authenticated request -> principal context -> registries/policy -> deterministic planner -> closed typed gateway -> M21/M22/M24 read boundary -> Evidence Pack -> budget admission -> deterministic router -> fixed adapter -> strict parser -> deterministic verifier -> append-only audit -> M18 lifecycle event.

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

Begin M26 planning/discovery. M26 must build on the M25 control plane and must not bypass its context, policy, capability, tool gateway, Evidence Pack, router, budget, verifier, audit, or RLS boundaries. Do not start an optional live-provider pilot, L1+ actions, generic tools, or generic HTTP without a separately approved milestone.

## Standard checks

Before changing code, read the continuity documents and verify Git HEAD/status plus Alembic source/current. Run focused module tests, directed M21/M22/M23 coverage, full backend regression, Ruff, `py_compile`, Alembic head/current, and `git diff --check`. Provider tests use fake/injected adapters only.
