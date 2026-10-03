# M29 capability inventory — repository discovery

Baseline: M28 v0.28.0, commit `c21e7c1287a8bc7abd8f355aa619e67c0beee0c4`.
This is static repository discovery, not a new runtime acceptance gate. Status
labels: IMPLEMENTED, PARTIAL, FOUNDATIONAL ONLY, NOT IMPLEMENTED, DEFERRED.

## Teacher

| Capability | Status and evidence |
|---|---|
| Teacher console/classes/roster | IMPLEMENTED: `/api/v1/teacher/classes`, `/classes/{course_offering_id}/roster`, `teacher_console/router.py` and `service.py`; M10 access/contract tests. Assignment scope is enforced. |
| Attendance and grades/results | IMPLEMENTED: teacher attendance/session and assessment/grade routes in `teacher_console/router.py`; M28 hardens corresponding M3 services; `test_m28_assessment_results.py`, `test_m28_synthetic_pilot.py`. |
| Offline capture/sync | IMPLEMENTED: `teacher_offline/router.py`, `service.py`, M20 IndexedDB code `frontend/src/lib/teacher-offline-store.ts`; receipts and idempotency; M20 auth/contract tests and M28 attendance continuity tests. |
| Teacher alerts/tasks | IMPLEMENTED/PARTIAL: `/teacher/alerts`, `/teacher/tasks`, acknowledge/complete task routes. These are not proven to be family communication obligations. |
| Teacher observation | PARTIAL: domain facts and M21 follow-ups exist; repository discovery did not establish a general teacher observation journal with family visibility semantics. |
| Teacher-family follow-up inbox | NOT IMPLEMENTED as a unified continuity view; existing tasks, M21 actions and M27 obligations have separate semantics/owners. |
| Teacher notifications | PARTIAL: task/console alert surfaces exist; no evidence found of a general teacher notification delivery system with family response linkage. |

## Student

| Capability | Status and evidence |
|---|---|
| Profile/enrollment/placement | IMPLEMENTED: M1/M2 services, M28 APIs; migrations `0043`–`0046`; M28 security/pilot tests. |
| Attendance/results | IMPLEMENTED: M3 authoritative services and student/guardian views. M28 tests cover correction history and privacy-minimized event/audit data. |
| Student console | IMPLEMENTED: `student_console/router.py` routes for profile, summary, classes, schedule, attendance, grades, pending, progress and notices; M11 tests. |
| Student Timeline | IMPLEMENTED as a derived M21 read model: `student_timeline/service.py`, projector and `/api/v1/students/{id}/timeline` route; M21 timeline tests. It is not a family portal payload. |
| Interventions/actions/follow-ups/outcomes | IMPLEMENTED in M21 `interventions` service/router, with sensitivity levels and permission-gated views; M21 tests. |
| Signals/intelligence | IMPLEMENTED as M22 derived views/signals; not a student operational authority and not suitable for wholesale family exposure. |

## Family / guardian

| Capability | Status and evidence |
|---|---|
| Guardian identity and explicit access | IMPLEMENTED: M6 `guardian_profiles`, `student_guardian_relationships`, `guardian_student_portal_access`; ADRs `0026`, `0027`; migration `0007_m6_family_portal.py`; `test_m6_guardian_rls.py`. Relationship alone does not imply portal access. |
| Family Portal | IMPLEMENTED: `/family-portal/me`, children, overview, attendance, grades, notices and notice acknowledge in `family_portal/router.py`; scoped service queries. |
| Guardian Console | IMPLEMENTED: M12 `/guardian/students/...` overview/attendance/grades/progress/pending and notices in `guardian_console/router.py`; M12 access/privacy tests. |
| Family-facing frontend | IMPLEMENTED, legacy server-served HTML (`family_dashboard.html`, `guardian_dashboard.html`); React parity/unified UX is not established. |
| Acknowledgement | IMPLEMENTED for family notices through `POST /family-portal/notices/{id}/acknowledge` and guardian notice route; `family_notice_receipts`. This is acknowledgement, not a general response/conversation lifecycle. |
| Family-originated response/message | NOT IMPLEMENTED as a general conversation/reply workflow in the inspected family APIs. |
| Family notification preferences/contact consent | PARTIAL/NOT ESTABLISHED as a unified policy in inspected M6/M13 contracts; recipient delivery currently resolves active portal grants. Must be audited before extension. |

## Communications

| Capability | Status and evidence |
|---|---|
| Communications authority | IMPLEMENTED: M13 `communications` module; do not create another backend. |
| Templates/targets/authoring | IMPLEMENTED: `/communications/templates`, `/messages`, `/messages/{id}/targets`; target types include institution, campus, section, course, student, family. |
| Preview/publication | IMPLEMENTED: preview and explicit staff publish route; publication is human-authorized and audited/outboxed. |
| In-app delivery | IMPLEMENTED: publish materializes legacy `family_notices`; recipients resolve to active student/guardian portal grants; migration `0015_m13_communications_center.py`. |
| Delivery/read/ack state | PARTIAL but foundational: `/messages/{id}/delivery` derives recipient status from notice receipts; read/ack telemetry exists. Retryable external transport delivery is not implemented. |
| External adapters | NOT IMPLEMENTED in M13: no SMS, WhatsApp, SMTP/email or push provider. M13 release document explicitly excludes them. |
| Communication-to-intervention/accountability linkage | PARTIAL/NOT ESTABLISHED: M21 follow-up type includes `FAMILY_CONTACT`; M27 obligations exist, but no verified first-class link from communication recipient response to M21/M27 obligation was found. |

## Key tests and schema evidence

- Teacher: `test_m10_teacher_access.py`, `test_m10_teacher_contract.py`,
  `test_m20_teacher_offline_auth_contract.py`, `test_m20_teacher_offline_contract.py`.
- Student: `test_m11_student_access.py`, `test_m11_student_contract.py`,
  M21 timeline tests, M28 record/result/security tests.
- Family: `test_m6_guardian_rls.py`, `test_m12_guardian_access.py`,
  `test_m12_guardian_contract.py`, `test_m12_guardian_privacy.py`.
- Communications: `test_m13_communications_contract.py`,
  `test_m13_communications_targeting.py`, `test_m13_communications_privacy.py`.
- Event/outbox: M18 event contracts, M28 continuity tests, migration
  `0017_m18_event_ledger_read_models.py`.

Inventory limits: endpoint existence and tests establish current contracts,
not actual real-world adoption, external transport delivery, or family response
completion semantics beyond notice acknowledgement.
