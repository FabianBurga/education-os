# M29 domain and authority boundaries

M29 is a continuity layer over existing authorities. No M29-0 model, API,
table, event, or migration is implemented.

| Concern | Authority | M29 may consume | M29 must not do |
|---|---|---|---|
| Identity, tenant, roles and domain permissions | M0 identity/RBAC; M19 institution policy/control plane | Effective actor, tenant and policy decisions. | Create a second identity, membership, or authorization source. |
| Student profile/enrollment | M1; M28 operational hardening | Authorized references and facts. | Create a parallel student/enrollment record. |
| Academic structure, placements, assignment, attendance, results | M2/M3; M20 for offline entry; M28 continuity | Scoped facts and canonical commands/events. | Treat a communication, event, or AI output as academic truth. |
| Guardian relationship/access | M1/M6/M12; `guardian_student_portal_access` | Current explicit grant and guardian scope. | Infer access from contact/relationship alone or equate guardian and staff. |
| Communication authoring/publication/delivery | M13 `communications`; M6 notice/receipt compatibility | Existing message, target, recipient and receipt state. | Create another message, delivery, template or acknowledgement backend. |
| Transactional events and derived views | M18 outbox/ledger/checkpoints/read models | Existing versioned event/evidence references. | Add another ledger or use a projection as source of truth. |
| Offline teacher workflow | M20 receipt/sync/conflict protocol | Successfully synchronized canonical domain facts. | Add M29-specific offline protocol or direct client dispatch. |
| Student timeline/interventions/actions/follow-ups/outcomes | M21 | Authorized evidence and existing action/follow-up references. | Create second timeline/intervention/follow-up authority. |
| Intelligence/signals/priorities/cohorts | M22 | Deterministic derived evidence at current permissions. | Send raw signals/risk labels to families or create opaque risk scoring. |
| Governed evidence/proposals | M23; governed agents M25; Mentor M26 | Minimized, authorized evidence for human review. | Grant autonomous communication, academic decisions or domain mutation. |
| Accountability cases, decisions, obligations and SLA | M27 | Human-governed case/obligation references. | Collapse notices, acknowledgements, interventions and decisions into one state. |
| Adoption workflows/records | M28 plus existing domain services | Operational journeys and history. | Reimplement M0–M28. |

## Vocabulary that must stay distinct

- **Notification:** a prompt that something may need attention; not the
  communication content or proof of delivery.
- **Communication:** human-authored and authorized content, with target,
  publication and recipient delivery state.
- **Acknowledgement:** recipient confirmation of a notice; not necessarily a
  substantive response or completed follow-up.
- **Response:** recipient-provided information; no general family response
  workflow was verified in discovery.
- **Follow-up:** M21 operational action/follow-up or M27 accountability
  obligation, each under its own authority.
- **Decision:** explicit human review/decision (M27, or other established
  authorized command), not a delivery state.
- **Intervention:** M21 governed student support process, with sensitivity and
  its own lifecycle.

Any future cross-domain relation is proposed only as an opaque, tenant-bound
reference with an owning authority, lifecycle, authorization check, audit and
event contract. No duplicated mutable status is assumed.
