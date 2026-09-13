# Education OS — M21 Technical Specification v1

## Milestone

**M21 — Student Timeline + Intervention Engine**

Status: DESIGN BASELINE  
Base branch: `m21-student-timeline-interventions`  
Base commit: `49eef262135b6abe003fefc5e002403628640c92`  
Previous DB revision: `0019_m20`  
Planned DB revision: `0020_m21`

---

## 1. Product objective

M21 converts the operational data already present in Education OS into a longitudinal, auditable and actionable institutional history for each student.

The milestone formalizes the Education OS loop:

`Data → Event → Context → Signal → Intervention → Action → Follow-up → Outcome`

M21 must not become another student dashboard and must not create a second source of truth for attendance, grades, communications, signals or enrollment. It builds on the M18 Event Ledger and on existing operational domains.

The differentiating outcome of M21 is the ability to answer, with traceability:

- What was detected?
- Why did it matter?
- Who decided to intervene?
- What action was assigned?
- What follow-up occurred?
- What was the result?

---

## 2. Architectural invariants

1. **One institutional student history. Multiple authorized views.**
2. The M18 `event_ledger` remains the canonical event history.
3. The Student Timeline is a rebuildable read model/projection, not a second system of record.
4. Existing domain entities remain authoritative for their own data.
5. `IntelligenceSignal` remains the signal primitive.
6. Existing `AutomationCase` / `AutomationTask` are preserved for compatibility during M21 v1.
7. A signal may suggest an intervention, but does not automatically authorize a consequential intervention.
8. Human authorization is required for consequential workflow transitions.
9. Every intervention mutation must be auditable and must emit a canonical event.
10. Psychological/DECE information must support restricted visibility from day one.
11. Tenant isolation is mandatory at organization + institution boundaries.
12. Teacher access is additionally constrained by active teaching assignment / section scope.
13. Sensitive information is never exposed only because a user can see the student.
14. M21 must remain additive wherever possible; no destructive migration of M18–M20 domains.
15. M21 test strategy follows `TESTING_PLAYBOOK.md`: targeted regression only unless a release gate requires full regression.

---

## 3. Existing foundations to reuse

### M18 Event Plane

Reuse:

- `outbox_events`
- `event_ledger`
- `projection_checkpoints`
- canonical event envelope
- `enqueue_canonical_event(...)`
- correlation / causation metadata

M21 adds a new projection consumer; it does not alter the M18 ledger contract.

### Intelligence

Reuse `intelligence_signals` as the system signal primitive.

A signal is evidence/context. It is not itself an intervention.

### Automation

Preserve:

- `automation_rules`
- `automation_cases`
- `automation_tasks`
- `automation_timeline_events`

M21 may link to legacy automation records, but does not remove or redefine them in v1.

### Coordination / Rectorado

Current Rectorado/Coordination already combines signals, cases and tasks. M21 should gradually provide a common longitudinal layer instead of making each console reconstruct student history independently.

### Teacher Console

Teacher Console already sees scoped signals and teacher tasks. M21 extends that concept into a role-aware student timeline and intervention participation model.

### Audit

Continue writing to `audit_logs` for security/operational audit. Canonical M21 events and audit logs serve different purposes:

- Event Ledger = institutional/domain event history.
- Audit Log = actor/action security and operational trace.

---

## 4. M21 bounded components

### M21-A — Student Timeline Foundation

Responsibilities:

- normalize student-relevant ledger events into timeline entries;
- persist a rebuildable read model;
- maintain a projection checkpoint;
- provide student timeline query API;
- enforce role/scope/sensitivity filtering.

### M21-B — Intervention Core

Responsibilities:

- create and manage institutional interventions;
- support human-originated and signal-originated interventions;
- preserve accountable ownership and state transitions;
- emit canonical events.

### M21-C — Actions, Follow-ups and Outcomes

Responsibilities:

- intervention actions;
- assignment and due dates;
- structured follow-up records;
- structured outcome capture;
- closure/reopening semantics.

### M21-D — Role-aware institutional views

Initial actors:

- Rector / academic coordination
- Teacher
- Psychology / DECE / student support
- System administrator

Student and guardian M21 views are explicitly out of scope for the first M21 implementation unless separately approved.

### M21-E — Detection / Suggestions

Rules may correlate signals/events and produce suggestions. They must not autonomously execute high-impact student decisions.

### M21-F — UI, pilot and freeze

Initial UI target: **Student 360 Timeline**.

---

## 5. Data model

### 5.1 `student_timeline_entries`

Purpose: rebuildable timeline read model derived primarily from `event_ledger`.

Proposed columns:

- `id UUID PK`
- `organization_id UUID NOT NULL`
- `institution_id UUID NOT NULL`
- `student_profile_id UUID NOT NULL`
- `ledger_event_id UUID NOT NULL`
- `ledger_position BIGINT NOT NULL`
- `event_type VARCHAR(180) NOT NULL`
- `event_version INTEGER NOT NULL`
- `category VARCHAR(40) NOT NULL`
- `importance VARCHAR(20) NOT NULL DEFAULT 'NORMAL'`
- `sensitivity VARCHAR(20) NOT NULL DEFAULT 'GENERAL'`
- `title VARCHAR(240) NOT NULL`
- `summary VARCHAR(1000) NULL`
- `source_aggregate_type VARCHAR(100) NOT NULL`
- `source_aggregate_id UUID NOT NULL`
- `actor_user_id UUID NULL`
- `correlation_id UUID NULL`
- `causation_id UUID NULL`
- `context_json JSONB NOT NULL DEFAULT '{}'`
- `occurred_at TIMESTAMPTZ NOT NULL`
- `recorded_at TIMESTAMPTZ NOT NULL`
- `projected_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Required constraints/indexes:

- `UNIQUE (institution_id, ledger_event_id)`
- index `(institution_id, student_profile_id, occurred_at DESC)`
- index `(institution_id, student_profile_id, category, occurred_at DESC)`
- index `(institution_id, ledger_position)`
- tenant FK where existing schema conventions permit.

Timeline categories v1:

- `ENROLLMENT`
- `ATTENDANCE`
- `ACADEMIC`
- `SIGNAL`
- `INTERVENTION`
- `ACTION`
- `FOLLOW_UP`
- `COMMUNICATION`
- `OUTCOME`
- `SYSTEM`

Sensitivity levels v1:

- `GENERAL`
- `RESTRICTED`
- `CONFIDENTIAL`

The stored sensitivity is necessary but is not sufficient authorization by itself. API authorization must combine permission + actor scope + entry sensitivity + domain-specific rules.

### 5.2 `interventions`

Purpose: new transactional system of record for institutional intervention workflow.

Proposed columns:

- `id UUID PK`
- `organization_id UUID NOT NULL`
- `institution_id UUID NOT NULL`
- `student_profile_id UUID NOT NULL`
- `academic_period_id UUID NULL`
- `section_id UUID NULL`
- `intervention_type VARCHAR(60) NOT NULL`
- `severity VARCHAR(20) NOT NULL DEFAULT 'MEDIUM'`
- `status VARCHAR(30) NOT NULL DEFAULT 'OPEN'`
- `sensitivity VARCHAR(20) NOT NULL DEFAULT 'GENERAL'`
- `title VARCHAR(240) NOT NULL`
- `reason VARCHAR(2000) NOT NULL`
- `objective VARCHAR(2000) NULL`
- `origin_type VARCHAR(30) NOT NULL`
- `opened_by_user_id UUID NOT NULL`
- `assigned_role_code VARCHAR(60) NULL`
- `assigned_user_id UUID NULL`
- `opened_at TIMESTAMPTZ NOT NULL`
- `target_at TIMESTAMPTZ NULL`
- `resolved_at TIMESTAMPTZ NULL`
- `closed_at TIMESTAMPTZ NULL`
- `outcome_type VARCHAR(30) NULL`
- `outcome_summary VARCHAR(2000) NULL`
- `outcome_recorded_at TIMESTAMPTZ NULL`
- `outcome_recorded_by_user_id UUID NULL`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`

Intervention states v1:

- `OPEN`
- `IN_PROGRESS`
- `MONITORING`
- `RESOLVED`
- `CLOSED`
- `CANCELLED`

State semantics:

- `OPEN`: intervention created, not yet actively worked.
- `IN_PROGRESS`: active actions/follow-up underway.
- `MONITORING`: immediate action completed; student is being observed for stability.
- `RESOLVED`: operational problem considered resolved but closure is not yet finalized.
- `CLOSED`: institutional workflow finalized with an outcome.
- `CANCELLED`: intervention invalidated/withdrawn with a recorded reason.

Direct `OPEN → CLOSED` should normally be rejected except privileged administrative correction with explicit audit metadata.

### 5.3 `intervention_links`

Purpose: link an intervention to multiple pieces of evidence without filling the intervention table with nullable foreign keys.

Columns:

- `id UUID PK`
- `organization_id UUID NOT NULL`
- `institution_id UUID NOT NULL`
- `intervention_id UUID NOT NULL`
- `link_type VARCHAR(30) NOT NULL`
- `entity_type VARCHAR(100) NOT NULL`
- `entity_id UUID NOT NULL`
- `created_by_user_id UUID NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`

Initial link types:

- `ORIGIN`
- `EVIDENCE`
- `RELATED`
- `LEGACY_CASE`

Examples:

- `IntelligenceSignal`
- `EventLedger`
- `AutomationCase`
- `CommunicationMessage`

Constraint:

- unique `(intervention_id, link_type, entity_type, entity_id)`.

### 5.4 `intervention_actions`

Columns:

- `id UUID PK`
- `organization_id UUID NOT NULL`
- `institution_id UUID NOT NULL`
- `intervention_id UUID NOT NULL`
- `action_type VARCHAR(40) NOT NULL DEFAULT 'REVIEW'`
- `title VARCHAR(240) NOT NULL`
- `description VARCHAR(2000) NULL`
- `status VARCHAR(30) NOT NULL DEFAULT 'OPEN'`
- `assigned_role_code VARCHAR(60) NULL`
- `assigned_user_id UUID NULL`
- `due_at TIMESTAMPTZ NULL`
- `acknowledged_at TIMESTAMPTZ NULL`
- `started_at TIMESTAMPTZ NULL`
- `completed_at TIMESTAMPTZ NULL`
- `completed_by_user_id UUID NULL`
- `completion_note VARCHAR(2000) NULL`
- `created_by_user_id UUID NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`

Action states:

- `OPEN`
- `ACKNOWLEDGED`
- `IN_PROGRESS`
- `COMPLETED`
- `CANCELLED`
- `OVERDUE`

### 5.5 `intervention_followups`

Columns:

- `id UUID PK`
- `organization_id UUID NOT NULL`
- `institution_id UUID NOT NULL`
- `intervention_id UUID NOT NULL`
- `followup_type VARCHAR(50) NOT NULL`
- `sensitivity VARCHAR(20) NOT NULL DEFAULT 'GENERAL'`
- `note VARCHAR(4000) NOT NULL`
- `observed_at TIMESTAMPTZ NOT NULL`
- `created_by_user_id UUID NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`

Initial follow-up types:

- `MEETING`
- `PHONE_CALL`
- `FAMILY_CONTACT`
- `STUDENT_CONVERSATION`
- `TEACHER_REVIEW`
- `ACADEMIC_REVIEW`
- `ATTENDANCE_REVIEW`
- `PSYCHOLOGY_SESSION`
- `REFERRAL`
- `OTHER`

### 5.6 Optional future table — `intervention_suggestions`

Not required for M21-A/B. If introduced in M21-E, suggestions must be separate from active interventions so machine-generated proposals cannot silently become institutional decisions.

---

## 6. Outcome model

Outcome type v1:

- `IMPROVED`
- `STABLE`
- `NO_CHANGE`
- `WORSENED`
- `REFERRED`
- `TRANSFERRED`
- `NOT_ASSESSABLE`

Closing a normal intervention requires:

- `outcome_type`
- `outcome_summary`
- actor identity
- closure timestamp

This structure allows future effectiveness metrics without relying on free-text NLP.

---

## 7. Human-in-the-loop rules

System/rules may:

- detect patterns;
- correlate evidence;
- rank/prioritize;
- generate suggestions;
- remind;
- escalate overdue operational work.

System/rules must not autonomously:

- sanction a student;
- alter a grade;
- diagnose a psychological/medical condition;
- expel/suspend;
- close a high-impact case without authorized human action;
- reveal confidential psychological information to unauthorized actors.

M21 must make the human authorization boundary explicit in service methods and API dependencies, not merely in UI copy.

---

## 8. Role and permission model

M21 introduces permissions rather than relying only on role names.

Proposed permission keys:

- `student_timeline.read`
- `student_timeline.read_restricted`
- `student_timeline.read_confidential`
- `intervention.read`
- `intervention.create`
- `intervention.update`
- `intervention.assign`
- `intervention.action.manage`
- `intervention.followup.create`
- `intervention.resolve`
- `intervention.close`
- `intervention.admin`

Initial access intent:

### SYSTEM_ADMIN

- full institutional M21 administration;
- not automatically a reason to bypass application audit;
- confidential content access should be explicit by permission.

### RECTOR / COORDINATOR

- timeline institutional view;
- intervention create/manage/assign/resolve/close;
- general + restricted data as configured;
- confidential psychology detail only with explicit confidential permission.

### TEACHER

- timeline access only for students within active teaching assignment scope;
- pedagogically relevant GENERAL entries;
- selected RESTRICTED entries only when explicitly allowed;
- interventions in which the teacher has legitimate scope/participation;
- create pedagogical follow-up/action where permitted;
- no implicit access to CONFIDENTIAL psychology notes.

### PSYCHOLOGY / DECE / STUDENT SUPPORT

M21 should establish a dedicated institutional support permission set. Role naming may be finalized during implementation, but permissions must support:

- relevant student timeline access;
- confidential intervention/follow-up access;
- creation of psychology/student-support interventions;
- protected follow-up notes;
- referral and outcome workflows.

A future canonical role may be named `STUDENT_SUPPORT` with institution-specific staff titles such as Psychologist or DECE Counselor. This avoids hard-coding one national organizational label into core authorization logic.

---

## 9. Visibility and sensitivity model

Principle:

**A user being authorized to see a student does not imply authorization to see every timeline entry for that student.**

Authorization must evaluate:

1. correct organization/institution;
2. permission key;
3. student scope;
4. intervention participation/assignment where relevant;
5. timeline entry category;
6. sensitivity level;
7. domain-specific restrictions.

Teacher may see:

- attendance;
- academic events;
- relevant signals;
- teacher-assigned actions;
- general intervention status;
- general follow-up outcomes.

Teacher must not automatically see:

- confidential psychology session notes;
- restricted family information unrelated to pedagogy;
- confidential referrals;
- sensitive diagnostic or health information.

Rector/Coordination may see institutional status without necessarily seeing confidential note bodies. A restricted entry may therefore expose a safe summary while suppressing protected detail.

---

## 10. Timeline projection design

Projection key:

`m21.student_timeline.v1`

Algorithm:

1. read `ProjectionCheckpoint` for institution + projection key;
2. fetch ledger events where `position > last_position`, ordered ascending;
3. map supported event types to zero or more student timeline entries;
4. resolve `student_profile_id` from canonical payload/aggregate mapping;
5. normalize category/title/summary/context/sensitivity;
6. insert idempotently using `(institution_id, ledger_event_id)` uniqueness;
7. update checkpoint only after successful processing;
8. commit atomically for the processed batch.

Rules:

- unknown event types are skipped safely, not fatal;
- malformed supported events are surfaced as projection errors/metrics and must not silently corrupt data;
- projection can be rebuilt from ledger;
- no operational domain mutation is performed by the timeline projector.

Initial supported event families must be confirmed from the exact canonical event types already emitted by current modules before implementation.

---

## 11. Canonical M21 event contracts

Planned event names:

- `intervention.opened`
- `intervention.assigned`
- `intervention.status_changed`
- `intervention.action_created`
- `intervention.action_acknowledged`
- `intervention.action_started`
- `intervention.action_completed`
- `intervention.followup_recorded`
- `intervention.outcome_recorded`
- `intervention.closed`
- `intervention.reopened`
- `intervention.cancelled`

All start at `event_version = 1`.

Required common payload fields where applicable:

- `student_profile_id`
- `intervention_id`
- `academic_period_id`
- `section_id`
- `sensitivity`
- relevant transition/action/follow-up fields

Use canonical envelope fields for:

- `actor_user_id`
- `correlation_id`
- `causation_id`
- metadata

---

## 12. API contract v1

### Timeline

- `GET /api/v1/students/{student_profile_id}/timeline`
- query filters: `category`, `from`, `to`, `limit`, `cursor`
- returns only authorized/sanitized entries.

Administration/projection:

- `GET /api/v1/student-timeline/projection/status`
- `POST /api/v1/student-timeline/projection/run`

Projection run requires privileged/admin permission.

### Interventions

- `GET /api/v1/interventions`
- `POST /api/v1/interventions`
- `GET /api/v1/interventions/{intervention_id}`
- `POST /api/v1/interventions/{intervention_id}/assign`
- `POST /api/v1/interventions/{intervention_id}/status`
- `POST /api/v1/interventions/{intervention_id}/actions`
- `POST /api/v1/interventions/{intervention_id}/followups`
- `POST /api/v1/interventions/{intervention_id}/outcome`
- `POST /api/v1/interventions/{intervention_id}/close`
- `POST /api/v1/interventions/{intervention_id}/reopen`

Avoid generic unrestricted PATCH for high-impact state transitions in v1.

---

## 13. Compatibility with legacy AutomationCase

M21 v1 does not delete or transparently mutate existing automation cases.

Compatibility approach:

- an intervention may link to an `AutomationCase` using `intervention_links` + `LEGACY_CASE`;
- existing Rectorado endpoints continue to work;
- existing automation rules/tasks remain functional;
- future migration from AutomationCase to Intervention requires a separate approved milestone/change set.

No dual-write from legacy AutomationCase into Intervention should be introduced unless it is deterministic, idempotent and explicitly tested.

---

## 14. RLS and tenant security

M21 tables must follow current PostgreSQL tenant context conventions:

- `app.organization_id`
- `app.institution_id`
- `app.user_id`

Minimum RLS expectation:

- ENABLE RLS
- FORCE RLS
- runtime role only receives necessary privileges
- tenant policies enforce organization + institution

Tenant RLS alone is not sufficient for Teacher or confidential-data access. Fine-grained student scope and sensitivity must also be enforced in application services and, where practical, supporting DB predicates/functions.

No M21 policy should allow cross-institution reads.

---

## 15. Audit requirements

Every mutation must create an `AuditLog` entry with:

- actor;
- action;
- entity type;
- entity id;
- safe metadata.

Do not place confidential psychology note bodies into generic audit metadata.

Suggested audit actions:

- `M21_INTERVENTION_OPENED`
- `M21_INTERVENTION_ASSIGNED`
- `M21_INTERVENTION_STATUS_CHANGED`
- `M21_ACTION_CREATED`
- `M21_ACTION_COMPLETED`
- `M21_FOLLOWUP_RECORDED`
- `M21_OUTCOME_RECORDED`
- `M21_INTERVENTION_CLOSED`
- `M21_INTERVENTION_REOPENED`

Audit and event creation must occur in the same transaction as the domain mutation where possible.

---

## 16. Migration `0020_m21`

Migration must be additive.

Planned objects:

- `student_timeline_entries`
- `interventions`
- `intervention_links`
- `intervention_actions`
- `intervention_followups`
- new permissions
- required indexes/check constraints/FKs
- RLS policies/functions

Do not modify/drop:

- `event_ledger`
- `intelligence_signals`
- `automation_cases`
- `automation_tasks`
- M20 offline tables

Downgrade should remove M21-specific objects and permissions only.

---

## 17. Targeted test matrix

### M21-A Timeline

Must test:

- canonical ledger event projects once;
- rerun is idempotent;
- checkpoint advances correctly;
- unknown event does not break pipeline;
- institution A cannot see institution B timeline;
- Teacher can read assigned student timeline;
- Teacher cannot read non-assigned student timeline;
- Teacher cannot read confidential psychology detail;
- privileged support actor can read authorized confidential entry;
- category/date pagination works;
- event ordering is deterministic.

### M21-B Intervention

Must test:

- authorized human can open intervention;
- unauthorized actor receives 403;
- cross-tenant student cannot be targeted;
- signal can be linked as origin;
- intervention can exist without a signal origin;
- canonical event emitted;
- audit emitted;
- invalid state transition rejected.

### M21-C Actions/follow-up/outcome

Must test:

- assign scoped Teacher action;
- Teacher sees only legitimate assigned/scoped action;
- completion creates event + audit;
- confidential follow-up hidden from Teacher;
- support actor can record protected follow-up;
- closure requires structured outcome;
- reopen preserves prior history.

### Directed regressions

Run targeted regression on:

- M18 event pipeline;
- intelligence signals;
- automation cases/tasks;
- Rector/Coordination services;
- Teacher scope/access;
- audit;
- tenant context/RLS.

Do not rerun Finance, Communications templates, Family Portal or full M20 offline E2E unless M21 implementation directly modifies those surfaces or a release gate explicitly requires it.

---

## 18. Implementation order

### Slice 1 — M21-A foundation

1. identify exact current canonical event types that contain student identity;
2. implement models + `0020_m21` timeline table/security/permissions;
3. implement projector + checkpoint;
4. implement role-aware timeline service/API;
5. add targeted tests.

Exit criterion: authorized users can retrieve a deterministic, role-filtered student timeline produced from the Event Ledger without intervention-domain dependencies.

### Slice 2 — M21-B Intervention Core

1. intervention/link models;
2. state machine;
3. command service/API;
4. event + audit transaction;
5. security tests.

### Slice 3 — M21-C Actions/Follow-up/Outcome

1. actions;
2. follow-ups;
3. sensitivity rules;
4. structured outcomes;
5. closure/reopen workflow.

### Slice 4 — M21-D role views

1. Rector/Coordination integration;
2. Teacher scoped view;
3. Student Support/Psychology view;
4. confidentiality redaction.

### Slice 5 — M21-E suggestions

Only after deterministic workflow is stable.

### Slice 6 — M21-F UI/pilot/freeze

Build Student 360 Timeline, execute internal pilot, fix non-blockers, then release gate/tag/freeze.

---

## 19. Explicit non-goals for M21 v1

- AI copilot or LLM decisions — belongs to M22.
- external system integrations — belongs to M23.
- microservice extraction — belongs to M24+.
- autonomous psychological diagnosis.
- autonomous sanctions or grading.
- replacing the Event Ledger.
- replacing all existing automation workflows in one migration.
- exposing confidential support notes to students/guardians in v1.

---

## 20. M21-A definition of done

M21-A is complete when all conditions are true:

1. `0020_m21` applies cleanly from `0019_m20`.
2. Timeline entries are generated from supported Event Ledger events.
3. Reprocessing is idempotent.
4. Timeline API returns chronological student history.
5. Institution isolation passes.
6. Teacher assignment scope passes.
7. Sensitivity filtering passes.
8. Confidential support data cannot leak to Teacher.
9. M18 event pipeline targeted regression passes.
10. Rector/Teacher targeted regressions pass.
11. Ruff/unit tests for changed surfaces pass.
12. Evidence report records PASS/HOLD without repeating the full M20 functional pilot.

---

## 21. Architecture decision

**DECISION: READY_TO_IMPLEMENT_M21_A**

The first implementation slice is Student Timeline Foundation. Intervention workflow implementation starts only after the timeline projection/security foundation is proven.
