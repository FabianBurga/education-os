# Current State

## Current planning/bootstrap

M27 is CLOSED / PASS and published as `m27-decision-accountability-os-v0.27.0`
at `8af4557ee77d04adb2cb20d5994684268aacd194`. M28-0 — Canonical Bootstrap &
Scope Freeze is planning only on `m28-operational-adoption-core`, created from
that exact tag. No M28 production code or migration is implemented. Source head
remains `0042_m27_true_recurrence`; this planning stage does not recertify DB
runtime state. Contracts and the Luna handoff are in [docs/m28](m28/M28_SCOPE.md).
Next action: ASTRA review, then a separate M28-1 handoff. No publication in M28-0.

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

## M26 closure

M26 - Human Experience Layer / Mentor OS is CLOSED / PASS on `m26-mentor-os`.

- M26-1 configuration: CLOSED.
- M26-2 governed Mentor runtime: CLOSED / PASS.
- M26-3 Rector presentation with Panorama, Prioridades, and Revisión humana: CLOSED / PASS.
- M26-4 controlled synthetic pilot and manual visual/browser gate: CLOSED / PASS.

The Rector experience remains L0 read/explain only, with human review and
decision authority. The controlled pilot used synthetic aggregate evidence,
zero live provider calls, no domain mutation, and no persistent test residue.
Desktop and tablet presentation were manually verified.

Final validation: 718 backend tests passed, 0 failed, 1 skipped, and 126
warnings in 53.24 seconds. The skipped test was the opt-in M21 E2E because
`M21_E2E_DATABASE_URL` was unset. Frontend tests, typecheck, production build,
Ruff, `py_compile`, Alembic heads/current, and `git diff --check` passed.
No production pentest, load certification, or live-provider production
validation is claimed.

Security closure preserved RLS and FORCE RLS, application-role restrictions,
tenant isolation, unchanged policies/grants/ownership, no PII exposure, and
zero temporary residue.

## Canonical M27 closure

M27 - Institutional Decision & Accountability OS is CLOSED / PASS at
`8af4557ee77d04adb2cb20d5994684268aacd194` (published closeout) on branch
`m27-decision-accountability-os`. Migration head/current is
`0042_m27_true_recurrence`. Technical validation and synthetic operational
validation are PASS; value evidence is PASS_WITH_HUMAN_LIMITATIONS. The system
is ready for a controlled human pilot, but is not field validated or production
certified. Next engineering milestone: M28 - Operational Adoption Core.

M27-1 through M27-8 are complete. Full backend evidence is 743 passed, 0
failed, 1 skipped; the skip is the intentionally absent `M21_E2E_DATABASE_URL`
opt-in E2E. Frontend evidence is 61 tests passed, typecheck PASS, and
production build PASS. The synthetic pilot has 20 PASS scenarios, tenant leak
rate 0, and autonomous high-impact mutation rate 0. Administrative Time Saved
is `NOT_COMPUTABLE / BASELINE_REQUIRED`; Time to Priority Identification requires
human observation.

## Historical M27 implementation summary

M27 - Institutional Decision & Accountability OS is CLOSED / PASS, not active.
M27-2 - Accountability Projection Foundation is closed locally at
`0038_m27_accountability`. M27-3 - Human Review, Decision & Ownership Ledger
is closed locally at `0039_m27_review_decision`. M27-4 - Follow-up Obligations
& SLA is CLOSED / PASS locally at `0040_m27_obligations_sla`, with the
forward-only policy-evaluation boundary at `0041_m27_policy_eval` and the
forward-only recurrence constraint at `0042_m27_true_recurrence`. M27-6 metrics,
M27-7 Rector/Coordinator experience, and M27-8 controlled synthetic operational
pilot are CLOSED / PASS. M27 remains non-causal, does not execute M21 actions,
and the Mentor remains a human-controlled L0 read/explain experience.

M26-1 - Mentor institution-briefing contract and configuration is CLOSED at
database revision `0037_m26_mentor_briefing`. It seeds
`mentor_institution_briefing` v1 for the controlled tenants with L0 autonomy,
`mentor.institution.brief`, `m22.intelligence_snapshot.inspect`, request type
`M26_INSTITUTION_BRIEFING`, `agents.use` + `intelligence.read`, and
`PROVIDER_OPTIONAL_WITH_DETERMINISTIC_FALLBACK`.

M26-1 is CLOSED at database revision `0037_m26_mentor_briefing`.
M26-2, M26-3, and M26-4 are CLOSED / PASS. M26 overall is CLOSED / PASS.

## Living documentation rule

A milestone is closed only after technical closure and knowledge closure. Every closure updates this file, [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md), and `docs/project_state.json`; architecture changes also update [ARCHITECTURE.md](ARCHITECTURE.md), [TECHNICAL_DECISIONS.md](TECHNICAL_DECISIONS.md), and applicable ADRs.
