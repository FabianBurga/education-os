# Education OS — M21-A.1 Event Inventory v1

## Status

**DECISION: EVENT_INVENTORY_COMPLETE — READY_FOR_M21_A2_EVENT_INSTRUMENTATION**

Branch: `m21-student-timeline-interventions`  
Spec baseline: `M21_TECHNICAL_SPEC_V1.md`  
Spec commit: `637cd178a0547bd304b5d968a8dfad010824aca8`

---

## 1. Purpose

M21 Student Timeline is defined as a projection of the M18 Event Ledger.

The repository inspection confirms that the Event Plane is operational, but the student-facing operational domains were built before M18 and therefore do not all emit canonical events yet.

M21-A must first add minimal transactional event instrumentation to the relevant domains before implementing the Student Timeline projector.

This avoids a second pseudo-event system based on direct cross-domain table queries.

---

## 2. M18 behavior confirmed

`enqueue_canonical_event(...)` already supports:

- canonical lowercase event type;
- event version;
- aggregate type/id;
- actor;
- correlation id;
- causation id;
- metadata;
- canonical payload envelope.

`ingest_outbox_events(...)` accepts both:

- M18+ canonical envelope; and
- legacy M0-M17 payloads.

Legacy events are ingested into `event_ledger` with:

- `event_version = 1`;
- no actor/correlation/causation;
- metadata `legacy_envelope = true`.

Therefore M21 should emit new student events using `enqueue_canonical_event(...)` rather than adding a second event mechanism.

---

## 3. Domain inventory

| Domain | Student identity | Current event emission | M21 decision |
|---|---|---|---|
| Enrollment | Direct `student_profile_id` | None | Instrument in M21-A2 |
| Attendance | Via `student_section_assignment → enrollment → student_profile` | None in attendance service | Instrument in M21-A2 |
| Grades | Via `student_section_assignment → enrollment → student_profile` | None in grades service | Instrument in M21-A2 |
| Intelligence signals | Direct `student_profile_id` | None | Instrument OPEN/CLOSED/RESOLVED in M21-A2 |
| Automation | Direct on `AutomationCase.student_profile_id` | Internal `AutomationTimelineEvent`, not Event Ledger | Preserve; canonical integration belongs to M21-B compatibility slice |
| Communications | Can target STUDENT/SECTION/COURSE/FAMILY/INSTITUTION | Legacy `COMMUNICATION_PUBLISHED` outbox event | Preserve legacy event; student-level canonical expansion belongs to M21-D |
| M18 Event Plane | N/A | Canonical infrastructure ready | Reuse unchanged |

---

## 4. Enrollment findings

Enrollment operations are implemented directly in `backend/app/modules/enrollment/router.py`.

Current mutations:

- create enrollment;
- update enrollment status.

The `Enrollment` object contains direct `student_profile_id`, so no identity lookup is required for timeline projection.

No event is currently emitted.

### M21-A2 canonical contracts

#### `student.enrollment.created`

Aggregate:

- `aggregate_type = "enrollment"`
- `aggregate_id = enrollment.id`

Payload:

```json
{
  "student_profile_id": "...",
  "academic_period_id": "...",
  "campus_id": "...",
  "status": "PENDING|ACTIVE",
  "enrolled_on": "YYYY-MM-DD|null"
}
```

#### `student.enrollment.status_changed`

Aggregate: enrollment.

Payload:

```json
{
  "student_profile_id": "...",
  "academic_period_id": "...",
  "previous_status": "...",
  "status": "...",
  "withdrawn_on": "YYYY-MM-DD|null"
}
```

Timeline category: `ENROLLMENT`  
Sensitivity: `GENERAL`

---

## 5. Attendance findings

Attendance record mutation currently receives a `student_section_assignment_id`.

Student identity is deterministically resolved:

`student_section_assignments.enrollment_id → enrollments.student_profile_id`

No Event Ledger event is emitted by `attendance/service.py`.

### M21-A2 canonical contracts

#### `student.attendance.recorded`

Aggregate:

- `aggregate_type = "attendance_record"`
- `aggregate_id = attendance_record.id`

Payload:

```json
{
  "student_profile_id": "...",
  "student_section_assignment_id": "...",
  "class_session_id": "...",
  "section_id": "...",
  "attendance_code_id": "...",
  "minutes_late": 0
}
```

#### `student.attendance.updated`

Same aggregate and payload, plus prior/new values when practical.

Timeline category: `ATTENDANCE`  
Sensitivity: `GENERAL`

Notes MUST NOT be blindly copied to the timeline/event payload if they may contain sensitive free text. The operational attendance record remains authoritative for the full note.

---

## 6. Grade findings

Grade mutation also uses `student_section_assignment_id`.

Student identity is deterministically resolved through enrollment.

No Event Ledger event is emitted by `grades/service.py`.

### M21-A2 canonical contracts

#### `student.grade.recorded`

Aggregate:

- `aggregate_type = "grade_entry"`
- `aggregate_id = grade_entry.id`

Payload:

```json
{
  "student_profile_id": "...",
  "student_section_assignment_id": "...",
  "assessment_id": "...",
  "section_id": "...",
  "status": "...",
  "score": 0.0
}
```

#### `student.grade.updated`

Same aggregate and payload, with previous/new status/score where practical.

Timeline category: `ACADEMIC`  
Sensitivity: `GENERAL`

Teacher feedback is not copied automatically into the canonical timeline payload in M21-A2.

---

## 7. Intelligence signal findings

`IntelligenceSignal` already contains direct:

- `student_profile_id`;
- `academic_period_id`;
- `section_id`;
- `signal_type`;
- `severity`;
- metrics and summary.

Signal types currently include:

- `ATTENDANCE_RISK`
- `REPEATED_LATE`
- `ACADEMIC_RISK`
- `MISSING_WORK`

Signal refresh can:

- create a new OPEN signal;
- refresh an existing OPEN signal;
- auto-close an OPEN signal when the triggering condition stops;
- manually resolve an OPEN signal.

M21 Timeline should avoid noisy refresh events on every engine pass.

### M21-A2 canonical contracts

#### `student.signal.opened`

Emit only when a new signal entity is created.

Aggregate:

- `aggregate_type = "intelligence_signal"`
- `aggregate_id = signal.id`

Payload:

```json
{
  "student_profile_id": "...",
  "academic_period_id": "...|null",
  "section_id": "...|null",
  "signal_type": "...",
  "severity": "...",
  "metric_value": 0.0,
  "threshold_value": 0.0,
  "summary": "..."
}
```

#### `student.signal.closed`

Emit when refresh automatically closes the signal.

Payload additionally contains:

```json
{
  "closure_type": "AUTO",
  "resolution_note": "..."
}
```

#### `student.signal.resolved`

Emit when an authorized human explicitly resolves a signal.

Payload additionally contains:

```json
{
  "closure_type": "HUMAN",
  "resolution_note": "..."
}
```

Timeline category: `SIGNAL`  
Sensitivity default: `GENERAL`

No `student.signal.refreshed` event in M21-A2 to avoid timeline/event noise.

---

## 8. Automation findings

Automation currently has its own local workflow history:

- `CASE_OPENED`
- `TASK_CREATED`
- `TASK_ACKNOWLEDGED`
- `TASK_COMPLETED`
- `CASE_CLOSED`
- `TASK_ESCALATED`

These are persisted as `AutomationTimelineEvent`, not as canonical M18 Event Ledger events.

`AutomationCase` already contains `student_profile_id`.

M21 decision:

- do not remove or alter the legacy automation timeline in M21-A;
- do not dual-write blindly in the first instrumentation patch;
- add canonical compatibility events in M21-B when `Intervention` is introduced and linked to `AutomationCase`.

Reason: M21-A must establish a trustworthy student-data event stream first without changing the proven Rector/Coordination workflow.

---

## 9. Communications findings

Communications already uses the legacy `enqueue_event(...)` helper when a communication is published:

- event type: `COMMUNICATION_PUBLISHED`
- aggregate type: `communication`

The published legacy payload contains aggregate counts:

- target count;
- students reached count;
- guardian recipients count;
- family notices created count.

It does **not** contain the exact student identities required to safely build one timeline entry per student.

M21 decision:

- preserve the legacy event unchanged for backward compatibility;
- do not infer student recipients later from mutable target state;
- in M21-D add a canonical student-relevant communication event at publication time with immutable recipient/student linkage.

This prevents historical timeline reconstruction from changing when section membership changes later.

---

## 10. Canonical naming decision

All new M21 student-domain events use lowercase canonical names compatible with M18 validation:

```text
student.enrollment.created
student.enrollment.status_changed

student.attendance.recorded
student.attendance.updated

student.grade.recorded
student.grade.updated

student.signal.opened
student.signal.closed
student.signal.resolved
```

`event_version = 1` for the first contracts.

---

## 11. Transaction invariant

Every M21-A2 mutation follows:

```text
domain mutation
      +
enqueue_canonical_event(...)
      +
single transaction commit
```

The following is forbidden:

```text
commit domain mutation
      ↓
attempt event later
```

If event creation fails, the domain mutation must not be committed.

---

## 12. Historical data policy

M21-A2 instrumentation captures **new mutations from deployment forward**.

Existing historical attendance, grade, enrollment and signal rows must not be silently converted into fake historical events by assigning current timestamps.

Historical timeline backfill is a separate controlled operation.

If a future backfill is approved, it must:

- preserve actual source timestamps;
- mark metadata with a backfill source;
- be deterministic/idempotent;
- never overwrite live canonical events;
- be separately tested.

---

## 13. M21-A2 scope

The first code patch will instrument only:

1. Enrollment create/status change.
2. Attendance record create/update.
3. Grade entry create/update.
4. Intelligence signal open/auto-close/manual-resolve.

Explicitly deferred:

- Automation canonical compatibility → M21-B.
- Communications student-recipient canonical expansion → M21-D.
- Intervention events → M21-B/C.
- Psychology/DECE events → M21-C/D.

---

## 14. Regression boundary

M21-A2 targeted tests must verify:

- operational mutation still works;
- one outbox canonical event is created in the same transaction;
- payload contains correct `student_profile_id`;
- actor is preserved;
- event names pass canonical validation;
- updates emit update contract, not create contract;
- signal refresh does not emit duplicate OPEN events for existing OPEN signals;
- auto-close emits one CLOSED event;
- manual resolve emits one RESOLVED event;
- tenant/RLS behavior remains unchanged;
- M18 pipeline ingests new events.

Do not rerun unrelated Finance, Family, Communication templates or full M20 PWA regression for this instrumentation patch.

---

## 15. Exit decision

```text
M21-A.1 EVENT INVENTORY          PASS
M18 EVENT INFRASTRUCTURE         READY
ENROLLMENT EVENT GAP             CONFIRMED
ATTENDANCE EVENT GAP             CONFIRMED
GRADE EVENT GAP                  CONFIRMED
SIGNAL EVENT GAP                 CONFIRMED
AUTOMATION LOCAL TIMELINE        CONFIRMED / DEFER M21-B
COMMUNICATION LEGACY EVENT       CONFIRMED / DEFER M21-D

NEXT                             M21-A.2 EVENT INSTRUMENTATION
DECISION                         READY_TO_IMPLEMENT
```
