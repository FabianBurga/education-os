# Education OS - Project Handoff

## Current handoff point

Education OS is a security-sensitive, multi-tenant Institutional Intelligence & Action Platform. M25 - Agentic Control Plane is CLOSED at `bd0fbaa719eae4884d9a6c3ab8600939e88bb433` (`feat(m25): add governed provider-backed explainer`), tagged `m25-governed-provider-explainer-v0.25.3`, and remotely backed up and verified on `origin` (`FabianBurga/education-os`). M26-1 and M26-2 are CLOSED / PASS on `m26-mentor-os`; M26-3 is the next active slice. The local database is at `0037_m26_mentor_briefing`.

## M26-1 closed configuration baseline

M26-1 is CLOSED. It applies only persisted configuration for the future L0
`mentor_institution_briefing` v1 agent: capability
`mentor.institution.brief`, tool `m22.intelligence_snapshot.inspect`, request
type `M26_INSTITUTION_BRIEFING`, and permissions `agents.use` +
`intelligence.read`. Its policy is
`PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK`, with four logical steps and
one domain tool call maximum.

The exact seeds exist only for `Universidad de Otavalo` and `Education OS
Local Isolation Secondary`. M26-1 created no tables, RLS/grant changes, model
or provider configuration, credentials, runtime, or UI.

## M26-2 result

M26-2 delivered the governed `mentor_institution_briefing` L0 runtime through
the existing M25 path. It accepts only `OVERVIEW`, `PRIORITIES`, and
`FOLLOW_UPS`; reads only the typed M22 institutional snapshot boundary; builds
aggregate-only `m25.evidence.v1`; and uses deterministic fallback with an
optional in-process fake-provider path. Deterministic verification, append-only
audit, M18 lifecycle events, and replay/idempotency are preserved. Replay
identity includes tenant/principal scope, agent/version, focus, snapshot
identity, M22 provenance hash, and the Mentor prompt-contract hash. A changed
snapshot creates a new logical execution. The runtime performs no domain
mutation and requires no live provider.

The M26 capability remains permission-driven (`agents.use` and
`intelligence.read`). M22 independently retains its manager-role RLS boundary;
RECTOR and ACADEMIC_COORDINATOR satisfy that scope, while an arbitrary
non-manager cannot bypass it. No role-name RECTOR check was added to M26.

Closure evidence: 75 targeted tests passed, 61 M26 integration tests passed;
directed M25 57, M22 56, M21 282, M23 66, and M24 13 passed; full backend 711
passed, 0 failed, 1 skipped, 116 warnings, 42.50 seconds. The skipped test was
the opt-in M21 E2E because `M21_E2E_DATABASE_URL` was unset. RLS, FORCE RLS,
application-role restrictions, tenant isolation, and zero residue were verified.

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

Begin M26-3 Rector API/UI presentation. M26-4 controlled pilot and overall
milestone closure remain pending. M26-3 must build on the M25 control plane and
M26-2 runtime without bypassing context, policy, capability, tool gateway,
Evidence Pack, router, budget, verifier, audit, or RLS boundaries. Do not start
an optional live-provider pilot, L1+ actions, generic tools, or generic HTTP
without a separately approved milestone.

## Standard checks

Before changing code, read the continuity documents and verify Git HEAD/status plus Alembic source/current. Run focused module tests, directed M21/M22/M23 coverage, full backend regression, Ruff, `py_compile`, Alembic head/current, and `git diff --check`. Provider tests use fake/injected adapters only.
