# M27 — Institutional Decision & Accountability OS

## M27-1 Contract & Metrics Freeze

Design freeze only. This document introduces no runtime, migration, endpoint,
UI, or autonomous decision authority.

## Authority map

M27 coordinates accountability over authoritative M18–M26 boundaries. M18
owns canonical event chronology; M19 owns versioned policies and capability
rollout; M21 owns interventions, actions, follow-ups, and outcomes; M22 owns
signals, priorities, and institutional intelligence; M25/M26 own the governed
agent, evidence, provider, audit, and human-control pipeline. M27 owns only
case identity, responsibility, human review, bounded institutional decision,
accountability obligations, SLA evaluation, recurrence classification, and
cross-domain projections.

| M27 datum | Classification |
| --- | --- |
| `case_id`, episode relations, M27 lifecycle facts | AUTHORITATIVE (M27) |
| source lineage, tenant/institution scope, actor/provenance refs | AUTHORITATIVE reference |
| case category, identity resolution, SLA, recurrence, metric values | DERIVED from named sources and versioned policy |
| current responsibility, queue state, next obligation, institution read model | PROJECTED and rebuildable |
| interventions/actions/follow-ups/outcomes | AUTHORITATIVE in M21, referenced by M27 |
| signals/priorities/snapshots | AUTHORITATIVE in M22, referenced by M27 |
| chronology and canonical events | AUTHORITATIVE in M18, referenced by M27 |

## Accountability Case

An Accountability Case is a bounded institutional responsibility episode. It is
not a signal, intervention, action, follow-up, outcome, or event replacement.
Required semantics are opaque `case_id`, `case_identity_version`, tenant and
institution scope, permitted subject reference, source lineage, category,
owner, lifecycle, current responsibility, review requirement, decision
requirement, next obligation, SLA state, resolution, recurrence, and
provenance. Owner means the accountable M27 principal/team; it does not change
M21 intervention ownership.

The minimum institution read model exposes identity, category, lifecycle,
owner, responsibility, review/decision pending state, next obligation, due
time, SLA/freshness, recurrence, and opaque provenance references. It uses
aggregate evidence and excludes unnecessary student/guardian PII.

## Deterministic Case / Episode Identity

Identity key: `(tenant, permitted subject reference, case category,
episode_anchor)`. The versioned resolver applies these rules in order:

1. A source already linked to an open case continues that case.
2. A matching unresolved case in the active episode window continues it.
3. A matching resolved case inside the reopen window is `REOPENED` with the
   original `case_id`.
4. A match outside the reopen window opens a new episode and records a related
   case reference.
5. A different category is a distinct case, even for the same subject/time.
6. Concurrent risks remain distinct and related; they are never merged by
   similarity or provider output.

The resolver records rule code, policy version, source lineage, and candidate
summary. No ML or probabilistic identity is allowed. Unresolved continuation,
reopened case, new episode, related case, and true recurrence are distinct
classifications; true recurrence is a new episode after resolution and outside
the reopen window.

## Human Review, Decision, and Action

`review ≠ decision ≠ action`. A completed review records actor, timestamp,
effective permission context, tenant/scope, evidence lineage, disposition,
next required step, and provenance. A decision is a separate append-only human
record with bounded vocabulary:

`NO_ACTION_REQUIRED`, `MONITOR`, `REQUEST_INFORMATION`, `CREATE_INTERVENTION`,
`CONTINUE_INTERVENTION`, `ESCALATE`, `CLOSE_CASE`.

`CREATE_INTERVENTION` requests the existing governed M23/M21 path; it does not
create an intervention directly. Other dispositions do not duplicate M21
transitions. No provider or agent may make a high-impact decision.

## Follow-up Obligation and SLA

An obligation is the responsibility to perform or verify a next step; follow-up
execution remains in its authoritative domain. Required fields: origin, owner,
`due_at`, SLA and policy version, status, completion evidence, waiver/exception
reason, provenance, and next obligation. Bounded status is `OPEN`,
`IN_PROGRESS`, `COMPLETED`, `WAIVED`, `EXPIRED`, or `CANCELLED`. Completion
requires a source event or explicit human evidence, not a dashboard read.

## Outcomes and provenance

M27 preserves association ≠ causation. It may say “after the intervention, an
outcome was observed”; it may not assert causality without a separately
approved causal design. Every case, review, decision, obligation, metric, and
projection carries source event/snapshot identity, provenance hashes,
policy/calculator/projection versions, scope, actor/system origin, and
timestamps. Raw prompts, provider payloads, secrets, hidden reasoning, and
unnecessary PII are prohibited.

## M27-1 resolved product decisions

- **Category taxonomy:** preserve M21/M22 source category semantics in
  provenance. A normalized accountability category is only a versioned,
  deterministic projection mapping with an explicit mapping code; no ML or
  opaque remapping.
- **Shared ownership:** exactly one primary accountable owner when human
  responsibility is required; zero or more collaborators may participate.
  `UNASSIGNED` is explicit and detectable. Transfers are audited and
  event-backed.
- **SLA:** values come only from versioned M19 policy. Without valid policy,
  state is `NOT_EVALUABLE`; never infer on-time, overdue, compliant, or
  non-compliant.
- **Small-cell privacy:** reuse an applicable repository threshold. If none
  applies, M19 must provide a versioned fail-closed policy; missing threshold
  yields `SUPPRESSED` or `NOT_EVALUABLE`, never disclosure.
- **`REQUEST_INFORMATION`:** bounded decision that creates or links a
  human-owned information obligation. It does not create an intervention,
  mutate an outcome, or imply confirmed risk; `due_at` exists only with a
  policy SLA, and completion returns to human review.

## Non-goals

No second intervention store, intelligence store, event ledger, or autonomous
high-impact action authority is introduced. M27 must reuse M18–M26 boundaries.
