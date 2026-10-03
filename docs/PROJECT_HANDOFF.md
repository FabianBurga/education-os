# Education OS - Project Handoff

## Current handoff — M29-0

M29 — Teacher & Family Continuity is CURRENT on branch
`m29-teacher-family-continuity`, stage M29-0 — Canonical Bootstrap & Contract
Freeze. Base: immutable M28 tag `m28-operational-adoption-core-v0.28.0`, commit
`c21e7c1287a8bc7abd8f355aa619e67c0beee0c4`. M28 is CLOSED / PUBLISHED /
CANONICAL; do not modify its release branch or tag. M29-1 must wait until the
discovered capabilities, continuity gaps and privacy contract in [docs/m29](m29/M29_SCOPE.md)
are reviewed. The milestone notes below are historical records; older “current”
status wording does not supersede this handoff.

## Historical M28-1 handoff point

M28-1 Secure Student Record is CLOSED / PASS locally on
`m28-operational-adoption-core`, descended from published tag
`m27-decision-accountability-os-v0.27.0` at
`8af4557ee77d04adb2cb20d5994684268aacd194`. Current Alembic head/current is
`0043_m28_student_record_perms`. Review [M28-1 evidence](m28/M28_STUDENT_RECORD.md)
and the [slice plan](m28/M28_IMPLEMENTATION_PLAN.md) before Luna implements
M28-2 Enrollment Lifecycle. No push/tag/release is authorized.
The M27 implementation/pilot evidence below remains historical evidence;
its 692a8c2 implementation SHA is not the published closeout/tag SHA.

The following M26/M27 implementation notes are retained as historical evidence from their handoff dates. Their earlier milestone pointers and implementation SHAs do not supersede the current M29-0 handoff above; M28's canonical release identity is recorded there.

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

## M26 result

M26 is CLOSED / PASS. The governed `mentor_institution_briefing` runtime now
serves the Rector experience through Panorama, Prioridades, and Revisión humana.
It preserves the typed M22 evidence boundary, canonical `m25.evidence.v1`,
deterministic fallback, optional governed provider path, deterministic
verification, replay identity, append-only audit, and M18 lifecycle events.
The UI presents aggregate evidence and freshness, keeps human authority
explicit, and exposes no student PII or provider internals. The controlled
synthetic pilot and manual desktop/tablet visual gate passed with zero provider
or external network calls, zero domain mutation, and zero temporary residue.

Final regression passed 718 backend tests with 0 failures, 1 configured opt-in
M21 E2E skip, and 126 warnings. Frontend tests, typecheck, production build,
Ruff, `py_compile`, Alembic heads/current, and `git diff --check` passed. No
production pentest, load certification, or live-provider production validation
is claimed.

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

## M27-1 contract freeze

M27 is named **Institutional Decision & Accountability OS**. The historical
working name “Institutional Intelligence Agents” remains only in historical
evidence and is not the active milestone name. M27-1 freezes the design set in
`docs/m27/`: case/episode identity, human review and bounded decision,
obligations/SLA, reproducible metrics, M18 event model, security, provenance,
and optimized implementation slices. M21 remains authoritative for
interventions/actions/follow-ups/outcomes; M22 for signals/intelligence/
snapshots; M18 for chronology; M19 for governance; and M25/M26 for governed
evidence and human control. No runtime or persistence is introduced by M27-1.

M27-2 implements the minimum projection foundation in migration
`0038_m27_accountability` using `accountability_cases` and
`accountability_case_sources`. It preserves source references and provenance,
uses deterministic versioned identity, supports replay-safe source ingestion,
and enforces tenant/RLS boundaries. Reviews, decisions, obligations, SLA
engine, queue UI, and metrics remain deferred.

M27-3 adds `accountability_reviews`, `accountability_decisions`, and
`accountability_ownership_events` with append-only history, effective
permission context, provenance, audit, and canonical M18 outbox events. It
does not execute interventions, actions, follow-ups, outcomes, notifications,
or provider actions.

## M27 final closure

M27-1 through M27-8 are closed. The published canonical release is
`8af4557ee77d04adb2cb20d5994684268aacd194`; the controlled pilot is synthetic
only, with no real student PII or external providers. The full backend gate was
743 passed, 0 failed, 1 skipped; frontend tests, typecheck, and production build
passed. The single skip is the intentionally opt-in M21 E2E without
`M21_E2E_DATABASE_URL`. Administrative Time Saved remains
`NOT_COMPUTABLE / BASELINE_REQUIRED`; Time to Priority Identification requires
human observation. Do not claim field outcomes or production certification.

## Next step

M28-1 student-record operations are closed locally. M28-2 Enrollment Lifecycle
is the next planned slice and requires its separate reviewed handoff. Preserve
M26's L0 read/explain scope, M22 boundary, human-control language, and
no-live-provider posture until a later approved slice changes them.

## Standard checks

Before changing code, read the continuity documents and verify Git HEAD/status plus Alembic source/current. Run focused module tests, directed M21/M22/M23 coverage, full backend regression, Ruff, `py_compile`, Alembic head/current, and `git diff --check`. Provider tests use fake/injected adapters only.
