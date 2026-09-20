# Current State

## Formally closed

M25 - Agentic Control Plane is CLOSED at `bd0fbaa719eae4884d9a6c3ab8600939e88bb433`, `feat(m25): add governed provider-backed explainer`. It is tagged `m25-governed-provider-explainer-v0.25.3` and remotely backed up and verified on `origin` (`FabianBurga/education-os`). The database revision is `0036_m25_run_explainer`.

M25 status:

- M25-1 - CLOSED.
- M25-2 - CLOSED.
- M25-3A Evidence Pack Foundation - PASS.
- M25-3B Provider Routing, Budget Admission, and Fake Provider - PASS.
- M25-3C `integration_run_explainer` - PASS / CLOSED.
- M25-3D controlled fake-provider pilot - PASS.
- M25-3E optional live-provider pilot - OPTIONAL / NOT EXECUTED.

The first provider-backed L0 agent is `integration_run_explainer`. Its fake-provider mode and mandatory deterministic fallback are both validated. Successful controlled provider run: `0f706b7f-de79-4bde-ba15-a3b0795bc67a`; it completed in `FAKE_PROVIDER` mode with one in-process call, one valid opaque citation, 30 micro-USD consumed per budget scope, and no domain mutation.

No OpenAI, Anthropic, or local provider call was made. The historical M23 live-provider HOLD EXTERNAL remains open for API-credit/HTTP-429 availability; M25 does not close or supersede it.

## Validation evidence

- Focused M25/M24: 70 passed.
- Focused M25 provider/explainer: 28 passed.
- Directed M21/M22/M23: 403 passed.
- Full backend: 641 passed, 1 skipped.
- Ruff, `py_compile`, Alembic source/current, and `git diff --check`: PASS.

## M26-2 closure evidence

M26-2 - Governed Mentor runtime is CLOSED / PASS on `m26-mentor-os`.

Delivered behavior:

- governed `mentor_institution_briefing`, version 1, L0;
- typed `OVERVIEW`, `PRIORITIES`, and `FOLLOW_UPS` focus inputs;
- permission-gated `agents.use` + `intelligence.read` capability access;
- typed M22 institutional snapshot boundary through `m22.intelligence_snapshot.inspect`;
- canonical aggregate-only `m25.evidence.v1` pack with opaque `ev_01` citation;
- deterministic fallback and optional in-process fake-provider path;
- deterministic verifier, prohibited-action claim filter, append-only audit, and M18 lifecycle events;
- replay identity scoped by tenant/principal, agent/version, focus, snapshot identity,
  M22 provenance hash, and Mentor prompt-contract hash;
- changed snapshot identity creates a new governed execution rather than replaying stale evidence;
- no M21, M22, or M24 domain mutation and no live provider dependency.

Validation evidence: 75 targeted tests passed, including 61 M26 integration tests;
directed M25 57, M22 56, M21 282, M23 66, and M24 13 tests passed; the full
backend suite passed 711 tests with 0 failures, 1 skipped, 116 warnings, in
42.50 seconds. The skipped test was the opt-in M21 E2E because
`M21_E2E_DATABASE_URL` was unset. Ruff, py_compile, Alembic heads/current, and
`git diff --check` passed.

Security closure preserved RLS and FORCE RLS, application-role non-superuser
and non-BYPASSRLS status, owner-only fixture setup/cleanup, unchanged policies,
grants, and ownership, no cross-tenant evidence leak, and zero test residue.
Fake/in-process provider validation was allowed; live provider and external
network model calls were zero. The historical M23 live-provider HOLD EXTERNAL
remains unchanged.

## Active milestone

M26 - Human Experience Layer / Mentor OS remains the active overall milestone;
M26 itself is not yet closed.

M26-1 - Mentor institution-briefing contract and configuration is CLOSED at
database revision `0037_m26_mentor_briefing`. It seeds
`mentor_institution_briefing` v1 for the controlled tenants with L0 autonomy,
`mentor.institution.brief`, `m22.intelligence_snapshot.inspect`, request type
`M26_INSTITUTION_BRIEFING`, `agents.use` + `intelligence.read`, and
`PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK`.

M26-1 is CLOSED at database revision `0037_m26_mentor_briefing`.
M26-2 is CLOSED / PASS. M26-3 - Rector API/UI presentation is the next active
slice. M26-4 - controlled pilot and milestone closure remains pending.

## Living documentation rule

A milestone is closed only after technical closure and knowledge closure. Every closure updates this file, [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md), and `docs/project_state.json`; architecture changes also update [ARCHITECTURE.md](ARCHITECTURE.md), [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md), and applicable ADRs.
