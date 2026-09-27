# M28-4 — Student placement and roster

Status: CLOSED / PASS on `m28-operational-adoption-core`.

## Authority and placement lifecycle

M2 `student_section_assignments` remains the sole placement authority. A row
references the existing M1 enrollment, M1 academic period and M2 section; no
`m28_*` placement or roster table was added. Enrollment remains unchanged by a
section placement or transfer. The existing M2 values `ACTIVE`, `TRANSFERRED`
and `WITHDRAWN` are retained; `TRANSFERRED` is only a placement status.

Initial placement requires an active student profile, active enrollment with
an effective enrollment date, an active academic period and section, and an
effective date within that period and enrollment. Enrollment, period, section
and campus must belong to the authenticated institution; section and enrollment
must share period and campus. Placement into a non-active enrollment is
rejected. The bounded v1 transfer stays within the same campus and period;
cross-campus/institution transfer and same-day correction remain unsupported.

Transfer locks the enrollment row, checks the expected current placement and
rejects a stale competitor with 409. For effective date D, the prior placement
is retained with `TRANSFERRED` and inclusive `ended_on = D - 1`; a new `ACTIVE`
placement begins on D. Attendance on/after D and grade evidence with due date
on/after D (or no due date) prevent transfer, so the move cannot strand facts
outside the original placement interval. Both row changes, bounded audit,
canonical `student.section.transferred` outbox event and commit belong to one
transaction. A failed outbox write rolls back both placements.

No request receipt table was needed. The enrollment lock plus the stable
command identity (enrollment + expected placement + target section + effective
date) makes exact retries return the already committed row without another
event/audit; a changed or stale competitor conflicts. The existing partial
unique index `uq_student_section_active_enrollment` remains the final database
guard against two active placements. Placement intervals are inclusive and
readers evaluate dates against the backend's current date.

## Teaching assignments and authorization

The existing M2 `teaching_assignments` relation remains the teacher-scope
authority. The existing create path still requires effective `academics.assign`.
The bounded end command sets only `ends_on`; it locks the row and compares the
expected prior end date. Exact replay is a no-op; a stale update returns 409.
The end date must respect the assignment start and active academic period.
Before/after dates are retained in audit and the canonical
`teaching.assignment.updated` event. Rows are not deleted or recreated.

Institutional placement history requires `academics.read`, `students.read` and
`enrollments.read`. Placement options require `academics.assign` and
`enrollments.read`. Institutional section roster requires `academics.read` and
`students.read`, and returns only current, date-valid placements for active
enrollments/profiles in an active section/period. It is ordered by family name,
given name and profile ID, with bounded 100-row pages (maximum 250).

The teacher roster continues through the existing assigned-course endpoint.
It requires the existing teacher effective permissions and an active,
date-valid teaching assignment for that course. The SQL additionally scopes
the course, placement, enrollment and profile to the principal's tenant and
institution, and filters to date-valid placements. Ending an assignment
immediately removes that teacher's roster access. A teacher role alone,
SYSTEM_ADMIN role alone, or knowledge of a UUID grants no access. Invisible
foreign students/sections remain not found; errors contain no student PII.

Roster fields are minimized to student profile reference, student code,
display name, enrollment number, placement status, assigned date and inclusive
end date when present. A future-effective transfer remains visible through the
prior placement's end date. No guardian, contact, attendance or grade data is
copied into the roster.

## API and frontend

- `POST /api/v1/academics/student-section-assignments` — initial placement.
- `POST /api/v1/academics/enrollments/{id}/placements/transfer` — bounded,
  expected-placement transfer.
- `GET /api/v1/academics/students/{student_profile_id}/placements` — scoped
  placement history with server-computed current interval state.
- `GET /api/v1/academics/enrollments/{id}/placement-options` — only active
  sections in the enrollment's period and campus; current section omitted.
- `GET /api/v1/academics/sections/{section_id}/roster` — current institutional
  roster with bounded `limit`/`offset` pagination.
- `PATCH /api/v1/academics/teaching-assignments/{id}` — expected-state,
  audited end-date command.
- Existing `/api/v1/teacher/classes/{course_offering_id}/roster` remains the
  teacher read path; no new teacher authority or parallel roster API was added.

Student detail shows placement history and allows authorized initial placement
or a confirmed section transfer using server-provided options. Academic
structure provides a paginated section roster. Teacher roster remains in the
existing Teacher Console. Commands refetch authoritative state; 403/404/409/
422 and network failures remain bounded and distinct, with no optimistic
placement state.

## Persistence, events and validation

No migration was required. The existing M2 table already has status/date
history, tenant composite foreign keys, RLS/FORCE RLS and a unique active
placement index. All M1–M2 migrations through `0045_m28_academic_permissions`
remain unchanged. `student.section.assigned` remains the initial-placement
event; transfer and assignment end emit the additive M2 event names above.
Payloads contain opaque references and bounded dates/status only, not student
names, free text or unnecessary PII.

The focused PostgreSQL HTTP test proves initial placement, retry without event
duplication, two competing transfers (one succeeds and one receives 409),
history preservation, exact D-1 closure, current roster derivation, assigned
teacher visibility/revocation, unchanged ACTIVE enrollment, cross-tenant
not-found behavior and outbox-failure rollback. Directed regression passed 56
tests across M1/M2/M10/M18/M24/M28-1/2. Focused frontend tests: 14 passed;
typecheck and production build passed. The build retains an existing Vite
dynamic-import/chunk-size warning. Changed-file Ruff and `py_compile` passed;
Alembic head/current remains `0045_m28_academic_permissions`.

Limits: no cross-campus transfer, same-day correction, attendance or grade
mutation, new roster projection, new migration, or M28-5 work is included.
