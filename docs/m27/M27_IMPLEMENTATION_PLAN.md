# M27 — Implementation Plan

## M27-1 result

This freeze authorizes no runtime, persistence, endpoint, UI, or autonomous
behavior. M27 must reuse M18 ledger, M19 policies, M21/M22 read boundaries, and
M25/M26 governed evidence and human-control paths.

## Recommended sequence

1. **M27-1 — Contract & Metrics Freeze.** Freeze identity, review/decision/
   obligation semantics, events, formulas, security, provenance, and slices.
2. **M27-2 — Projection Foundation and Identity.** Implement one tenant-scoped,
   rebuildable case/episode projection and deterministic resolver over M18/M21/
   M22 references; prove RLS, replay, lineage, and non-disclosure.
3. **M27-3 — Human Review + Decision Ledger.** Add append-only review/decision
   facts with effective permission context; route `CREATE_INTERVENTION` only
   through the existing governed M23/M21 path.
4. **M27-4 — Obligations + SLA.** Add bounded obligation lifecycle and policy-
   versioned SLA calculator; reference M21 execution/outcome evidence.
5. **M27-5 — Institutional Accountability Queue.** Build the minimum scoped
   queue and deterministic ordering from existing events/projections; add
   privacy suppression and HTTP security tests.
6. **M27-6 — Metrics + Outcome Intelligence.** Add versioned metric projections,
   lost-case and recurrence calculations, M21 outcome association, missingness,
   and non-causal language. Administrative Time Saved remains not computable.
7. **M27-7 — Rector / Coordination Experience.** Expose queue, review,
   bounded decision, obligation, and aggregates through permission-driven UI.
8. **M27-8 — Controlled Operational Pilot.** Use rollback-contained synthetic
   fixtures and fake/in-process providers only; prove isolation, replay,
   provenance, reproducibility, no autonomous action, and zero residue.

M27-1 resolves the former open decisions conservatively: source categories
remain authoritative with optional normalized mappings; one primary owner plus
collaborators is required for accountable cases; missing M19 SLA is
`NOT_EVALUABLE`; missing small-cell policy is fail-closed; and
`REQUEST_INFORMATION` creates or links a human-owned information obligation
without creating an intervention. Implementation may not add convenience
defaults.

## Persistence strategy

Avoid one table per screen or metric. M27-2 implements the minimum foundation:
`accountability_cases` owns deterministic case identity and current rebuildable
projection state; `accountability_case_sources` is append-only source lineage.
They link to M18 event identity and M21/M22 source references without copying
domain payloads. Review, decision, and obligation ledgers remain deferred.
Queue and metric models are rebuildable projections, not authoritative stores.

New persistence is needed only for M27-owned case identity/relations,
accountability ownership, human review, bounded decisions, obligations, and
provenance. No new persistence is needed for M21 interventions/follow-ups/
outcomes, M22 signals/snapshots, M18 chronology, M19 policy definitions, or
M25/M26 Evidence Packs and runs.

## Gates and product boundary

Each slice runs contract tests, targeted RLS/tenant/permission/replay tests,
directed M18/M19/M21/M22/M25/M26 regression, migration checks when applicable,
then full gates proportional to impact, diff-check, clean-tree, provenance,
and residue checks. M27-2 implementation is limited to the case/source
foundation described above; M27-3 is closed locally and M27-4 is implemented
at `0040_m27_obligations_sla`.

M27-4 preserves the frozen lifecycle vocabulary. `EXPIRED` is reserved for a
future explicit policy-defined terminal event and is never assigned merely
because `now > due_at`; overdue/non-compliance remains derived. `CANCELLED` is
also reserved and has no implicit transition in M27-4. `REVIEW_REQUIRED` is an
obligation type, while `HUMAN_REVIEW_REQUIRED` is a next-required-step value.
M19 policy evaluation uses the forward-only tenant-scoped internal evaluation
boundary at `0041_m27_policy_evaluation_boundary`; policy administration and
visibility remain separate Control Plane concerns.

M27-3 implements three append-only ledgers: human reviews, bounded decisions,
and ownership history. Commands are service-first and reuse effective
permission checks, principal-derived tenant context, audit, and the M18
transactional outbox. Decision recording sets only a future execution intent;
it does not invoke M21 or any provider. M27-5 remains the next boundary for
the institutional accountability queue.

The M27-1 product decisions are resolved conservatively: source categories
remain authoritative with optional versioned normalized mappings; one primary
owner plus collaborators is required for accountable cases; missing M19 SLA is
`NOT_EVALUABLE`; missing small-cell policy is fail-closed; and
`REQUEST_INFORMATION` creates or links a human-owned information obligation
without creating an intervention. These decisions are prerequisites for later
review/decision/obligation slices, not blockers for this foundation.
## M27-5 - Institutional Accountability Queue

M27-5 is a read-only query boundary over the existing M27 case, ownership,
review, decision, and obligation projections plus authoritative M18/M21/M22
references. It uses no new table and emits no event on read. The contract is
documented in [M27_QUEUE.md](M27_QUEUE.md). Ordering is deterministic and
bounded; there is no opaque score or model ranking. M27-6 owns institutional
metrics and outcome intelligence.
