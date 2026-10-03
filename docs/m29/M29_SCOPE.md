# M29 — Teacher & Family Continuity: Scope and Contract Freeze

Status: M29-0 discovery/contract freeze. No M29 product functionality or
database schema is implemented. Baseline is the immutable M28 release tag
`m28-operational-adoption-core-v0.28.0`, peeled to
`c21e7c1287a8bc7abd8f355aa619e67c0beee0c4`; Alembic head `0046_m28_attendance_perms`.

## Problem and intended outcome

Investigate where continuity breaks between an observation or fact recorded by
a teacher, authoritative student records, an existing intervention or
accountability obligation, authorized family communication, acknowledgement or
response, and the next human follow-up. The goal is governed, traceable
continuity across existing capabilities, not a new screen collection.

Conceptual flow only (not an implementation specification):

```text
teacher action -> authoritative domain command -> outbox/M18 -> applicable
M21/M22/M27 context -> human-authorized existing communication -> authorized
family acknowledgement/response -> responsible staff follow-up -> outcome
```

## Verified starting capabilities

- Teacher Console routes for classes, assigned rosters, attendance, grades,
  alerts, tasks, task acknowledgement and completion:
  `backend/app/modules/teacher_console/router.py`.
- M20 offline attendance receipt/sync and scope revalidation:
  `backend/app/modules/teacher_offline/` and
  `backend/tests/unit/test_m20_teacher_offline_auth_contract.py`.
- M1/M2/M3 operational authorities, strengthened by M28 for records,
  enrollment, academic structure, assignments, placement, attendance and
  results; see `docs/m28/M28_DOMAIN_BOUNDARIES.md`.
- M6 Family Portal and M12 Guardian Console with explicit guardian/student
  portal grants, attendance/results views, notices and acknowledgement.
- M13 Communications Center with human-authored, targeted, in-app publication,
  recipient resolution and delivery report; migration `0015_m13_communications_center`.
- M21 timeline/interventions/actions/follow-ups; M27 separately governs
  accountability cases, ownership, decisions, SLA and obligations.

The evidence and gap matrix is in [capability inventory](M29_CAPABILITY_INVENTORY.md)
and [continuity map](M29_CONTINUITY_MAP.md).

## Contract invariants

1. M0–M28 remain authoritative; M29 adds no parallel domain authority.
2. Tenant, institution, teacher assignment and guardian/student grant scopes
   are re-evaluated at access and action time. Revocation takes effect.
3. Guardian access is not staff access. A family receives only an explicit,
   purpose-appropriate, authorized view; no wholesale timeline or intelligence
   exposure.
4. Internal, teacher, student, guardian, coordination, rector and restricted
   intervention evidence remain distinct visibility classes.
5. Communication, notification, acknowledgement, response, follow-up,
   decision and intervention are separate concepts and states.
6. Publication and high-impact decisions remain human-governed. M23/M25/M26
   cannot autonomously communicate or mutate academic state.
7. Offline teacher operations reuse M20 receipts/sync and authoritative domain
   services. No offline direct-to-family dispatch.
8. Events describe authoritative transactions through the existing outbox/M18
   ledger. Projectors remain idempotent and read models remain derived.
9. Free text and minors' PII are minimized in audit, events, aggregate
   evidence, delivery telemetry and family payloads.
10. M29 metrics are not official until semantics, windows, denominators,
    exclusions, freshness and provenance are specified and validated.

## Accumulated authority map to preserve

| Milestone | Existing authority M29 reuses |
|---|---|
| M17 | Production reliability: health, metrics, recovery and observability. |
| M18 | Canonical Event Ledger, transactional outbox, projection checkpoints/read models, correlation/causation and idempotent processing. |
| M19 | Institution control plane: capabilities, policies, configuration, revisions, drift and institution health. |
| M20 | Teacher Offline PWA, immutable receipts, idempotency, sync/conflict and current teacher-scope revalidation. |
| M21 | Student Timeline, interventions, actions, follow-ups and outcomes. |
| M22 | Derived institutional intelligence: overview, priorities, cohorts, trends, intervention health and explainable deterministic evidence. |
| M23 | Governed evidence boundary, minimization/redaction, provenance and human-reviewed proposals. |
| M24 | Integration runs/items/events, CSV/import foundation, mapping and connector versioning. |
| M25 | Governed agent/policy registry, planner, policy gate, typed tools, executor/verifier, evidence packs, budgets and fallback. |
| M26 | Institutional Mentor L0 overview/priorities/follow-ups; no autonomous mutation authority. |
| M27 | Accountability cases, ownership, human reviews/decisions, SLA, recurrence, obligations and outcome traceability. |
| M28 | Student administration, enrollment, academic structure, assignments/roster, attendance/offline continuity, assessments/results/corrections, operational history, permissions, import continuity and synthetic journey. |

The repository-specific implementation anchors and test evidence are indexed
in [M29_CAPABILITY_INVENTORY.md](M29_CAPABILITY_INVENTORY.md); this map does
not redefine milestone contracts.

## Product boundary

M29 discovery may propose bounded continuity semantics within current
authorities: reason/context reference, authorized recipient, delivery purpose,
acknowledgement/response state, follow-up linkage and visibility lifecycle.
Every proposed persistence or API change is `PROPOSED / NOT IMPLEMENTED` and
requires an owning authority, privacy review and M29-1 contract acceptance.

## Frozen non-goals

Finance ERP; Admissions CRM; accounting or payment systems; full LMS rewrite;
second Student Timeline, Intervention Engine, Accountability Engine, Event
Ledger or communications backend; autonomous AI decisions or academic
sanctions; opaque student risk scoring; full mobile rewrite; microservices
migration; replacement of M20 offline protocol; reimplementation of M0–M28;
final-grade/GPA/promotion/graduation engine unless later evidence establishes
a minimal continuity dependency. No external communication channel is implied.

## Questions the eventual continuity product may answer

- Teacher: what needs attention, which student follow-ups are mine, which
  family acknowledgements/responses await action, and which interactions need
  another step?
- Family: what is authorized and necessary to know, what requires acknowledgement
  or response, what happened to a prior response, and what attendance/results
  may I see?
- Coordination/rector: which owned follow-ups are overdue, where continuity is
  lost, which obligations have no owner, and where follow-through/reopening
  patterns exist?

These are product questions, not current metrics or proven capabilities.
Official measures require defined population, numerator/denominator, period,
missingness, freshness, exclusions and provenance.

## Acceptance direction

Before M29-1, product owners must accept the capability inventory, actual gap
matrix, family privacy boundary, communications ownership and slice sequence.
M29-1 should implement only the smallest evidence-supported continuity link;
it must not assume new tables or routes from this conceptual contract.

## Evidence references

- M6/M12 family: `backend/app/modules/family_portal/`,
  `backend/app/modules/guardian_console/`, migrations `0007_m6_family_portal.py`
  and `0014_m12_guardian_console.py`.
- M13 communications: `backend/app/modules/communications/`, migration
  `0015_m13_communications_center.py`, `docs/releases/m13-communications-center-v0.13.0.md`.
- M20/M18: `docs/architecture/m20-offline-first-teacher-pwa.md`,
  `docs/architecture/m18-event-platform.md`.
- Privacy decisions: `docs/adr/0026-m6-family-access-boundary.md`,
  `docs/adr/0027-m6-explicit-guardian-student-grants.md`.
