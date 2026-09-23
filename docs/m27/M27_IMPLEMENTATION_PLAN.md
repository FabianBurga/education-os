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

Avoid one table per screen or metric. The likely minimum later model is a
bounded M27 case/episode projection plus append-only review, decision, and
obligation ledgers, linked to M18 event identity and source lineage. Queue and
metric models are rebuildable projections, not authoritative stores. Exact
schema is intentionally deferred to M27-2 after review.

New persistence is needed only for M27-owned case identity/relations,
accountability ownership, human review, bounded decisions, obligations, and
provenance. No new persistence is needed for M21 interventions/follow-ups/
outcomes, M22 signals/snapshots, M18 chronology, M19 policy definitions, or
M25/M26 Evidence Packs and runs.

## Gates and product boundary

Each slice runs contract tests, targeted RLS/tenant/permission/replay tests,
directed M18/M19/M21/M22/M25/M26 regression, migration checks when applicable,
then full gates proportional to impact, diff-check, clean-tree, provenance,
and residue checks. M27-2 does not begin in this session.

Before M27-2, product approval is required for category taxonomy, shared-case
ownership, default SLA targets, privacy small-cell thresholds, and whether
`REQUEST_INFORMATION` creates an obligation or remains decision-only. These are
the only open product decisions for the freeze.
