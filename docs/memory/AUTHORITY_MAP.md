# Authority map — compact M17–M28 context

Earlier operational authorities: M0 identity/tenancy/RBAC; M1 student,
guardian and enrollment records; M2 academic structure, assignments and
placement; M3 attendance and results; M6 explicit family portal grants; M8
administration; M10 teacher console; M11/M12 student and guardian consoles;
M13 Communications Center. M29 consumes these authorities; it does not replace
them.

| Milestone | Authority |
|---|---|
| M17 | Production reliability: health, metrics, recovery, observability. |
| M18 | Canonical Event Ledger, transactional outbox, projections/checkpoints, correlation/causation, idempotent event processing. |
| M19 | Institution Control Plane: capabilities, policies, configuration, revisions, drift, institutional health. |
| M20 | Teacher Offline PWA: receipts, idempotency, sync/conflicts, teacher-scope revalidation. |
| M21 | Student Timeline, interventions, actions, follow-ups, outcomes. |
| M22 | Derived institutional intelligence: overview, priorities, cohorts, trends, intervention health, deterministic evidence. |
| M23 | Governed evidence/minimization/provenance and human-reviewed proposal boundary. |
| M24 | Integration runs/items/events, CSV import, mappings and connector versioning. |
| M25 | Governed agent/policy registry, planner/gates, typed tools, executor/verifier, evidence packs, budgets/fallback. |
| M26 | Institutional Mentor L0: overview/priorities/follow-ups; no autonomous mutation. |
| M27 | Accountability cases, ownership, review/decisions, SLA, recurrence, obligations, outcome traceability. |
| M28 | Operational adoption: student administration, enrollment, academic structure, assignment/roster, attendance/offline, assessments/results/corrections, permissions, import continuity. |

M29 must link through references and authorized views, not duplicate an
authority. Detailed M29 boundary: `docs/m29/M29_DOMAIN_BOUNDARIES.md`.
