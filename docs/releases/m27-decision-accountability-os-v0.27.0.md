# M27 — Institutional Decision & Accountability OS v0.27.0

Status: CLOSED / PASS
Release candidate: `692a8c2b6f79b1c773d001a2e4e1117f8f356d1c`
Branch: `m27-decision-accountability-os`
Migration head/current: `0042_m27_true_recurrence`

## Scope

M27 turns institutional signals and intelligence into an auditable,
human-controlled accountability flow. It covers case and episode identity,
ownership, human review, bounded human decisions, obligations and SLA
accountability, queue/detail read APIs, reproducible metrics, outcome
intelligence, and the Rector/Academic Coordinator experience.

M27 does not introduce autonomous high-impact action, causal attribution,
student administration, messaging, or a new analytics platform.

## Delivered slices

- M27-1 froze the accountability contracts, event model, metrics, and security
  boundary.
- M27-2 added the tenant-safe accountability projection foundation.
- M27-3 added append-only ownership, human review, and decision history.
- M27-4 added obligations, evidence completion/waiver, and policy-backed SLA
  accountability.
- M27-5 added the institutional accountability queue and detail boundary.
- M27-6 added bounded, explainable accountability metrics and outcome views.
- M27-7 added the permission-driven Rector/Coordinator queue-to-case
  experience and command APIs.
- M27-8 executed a rollback-contained synthetic operational pilot with 20
  passing scenarios and machine-readable evidence.

## Architecture and authority

M18 remains authoritative for canonical lifecycle events and chronology. M19
remains authoritative for institution policy and governance. M21 remains
authoritative for interventions, actions, follow-ups, and outcomes. M22 remains
authoritative for signals, priorities, and institutional intelligence. M27 owns
accountability case/episode identity, ownership, human review and decision
ledgers, obligations, SLA accountability, queues, derived metrics, and the
Rector/Coordinator experience.

Review is not decision; decision is not action; obligation is not execution.
`CREATE_INTERVENTION` records a decision and does not create an M21
intervention. Mentor remains an L0 read/explain boundary without mutation
authority.

## Migrations

The forward-only chain is:

- `0038_m27_accountability`: accountability projection foundation.
- `0039_m27_review_decision`: review, decision, and ownership ledger.
- `0040_m27_obligations_sla`: obligations and SLA state.
- `0041_m27_policy_eval`: tenant-scoped policy evaluation boundary.
- `0042_m27_true_recurrence`: permits the frozen `TRUE_RECURRENCE`
  classification that the earlier historical constraint could not persist.

Historical migrations were not rewritten. The 0042 change is tenant-safe,
preserves RLS implications, and adds no M21/M22 authority.

## Metrics

M27-6 freezes explainable, versioned results for:

`TIME_TO_DETECTION`, `TIME_TO_REVIEW`, `TIME_TO_INTERVENTION`,
`FOLLOW_UP_COMPLIANCE`, `LOST_CASE_RATE`, `RECURRENCE_RATE`,
`INTERVENTION_OUTCOME`, `REVIEW_ACCOUNTABILITY_RATE`,
`DECISION_ACCOUNTABILITY_RATE`, `NEXT_ACTION_COMPLIANCE`, and
`ADMINISTRATIVE_TIME_SAVED`.

Metrics are windowed, policy-aware, tenant-scoped, freshness/provenance aware,
and fail closed for small cells. `OPEN` is not `LOST`; `TRUE_RECURRENCE`
requires episode semantics; and no metric makes a causal claim. Administrative
Time Saved is `NOT_COMPUTABLE` with reason `BASELINE_REQUIRED` until a real
baseline study exists.

## Security and privacy

The release preserves RLS/FORCE RLS, principal-derived tenant context, effective
permissions, scope enforcement, append-only histories, command idempotency,
audit/provenance, and the closed tool gateway. It does not add arbitrary SQL,
shell, HTTP, provider bypass, raw provider payload persistence, hidden reasoning
persistence, secrets, or unnecessary PII. Small-cell suppression is fail-closed;
suppressed numerator, denominator, ratios, percentages, and reconstructable
complements are not returned. Cross-tenant queue, case, metric, and command
access are rejected.

## Experience

The shared accountability experience provides queue filters, case detail,
ownership transfer, human review, bounded decisions, obligations, evidence
completion/waiver, metrics, freshness, provenance, and explicit error states.
The UI presents `DECISION RECORDED` separately from `ACTION EXECUTED`, does not
reimplement backend business rules, and supports desktop/tablet use with the
existing frontend design system.

## Pilot and evidence

M27-8 is a controlled synthetic pilot only. Dataset identity is
`M27-8-SYNTHETIC-TRANSACTION-ROLLBACK`; it contains no real student PII and no
external provider calls. Evidence is recorded in
`artifacts/m27_pilot_result.json` and reproducible through
`docs/m27/M27_CONTROLLED_PILOT.md`. Twenty deterministic scenarios passed,
including authorization, privacy, provenance, idempotency, concurrency,
replay, request-information, recurrence, and outcome boundaries.

Technical gate: PASS. Synthetic operational gate: PASS. Value evidence gate:
`PASS_WITH_HUMAN_LIMITATIONS`.

## Validation evidence

- Backend: 743 passed, 0 failed, 1 skipped, exit code 0.
- The sole skip is the intentionally opt-in M21 E2E without
  `M21_E2E_DATABASE_URL`.
- Frontend: 61 tests passed; typecheck PASS; production build PASS.
- RLS/FORCE RLS: PASS.
- Tenant leak rate: 0.
- Autonomous high-impact mutation rate: 0.
- Ruff on M27 changed files: PASS. Repository-wide Ruff findings remain
  pre-existing historical debt and were not changed by M27-8.

## Limitations and next step

The pilot is synthetic and does not establish real institutional outcomes,
field usability, causal effectiveness, production readiness, load
certification, or a production security certification. Time to Priority
Identification requires human observation. Administrative Time Saved remains
unmeasured until a baseline method, task definition, sample, period, and
provenance are collected in a field study.

M27 is ready for a controlled human pilot. It is not field validated and is not
production certified. The next engineering milestone is **M28 — Operational
Adoption Core**. No M28 implementation is included in this release.
