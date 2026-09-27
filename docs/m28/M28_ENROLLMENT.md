# M28-2 — Enrollment lifecycle and history

Status: CLOSED / PASS on `m28-operational-adoption-core`.

## Authority and state

M1 `enrollments` remains the sole enrollment authority. It references the
existing M1 `StudentProfile`, `AcademicPeriod`, and M0 `Campus`; M2 placement
remains separate. No enrollment or history table was added. The existing
unique `(student_profile_id, academic_period_id)` rule is preserved: multiple
periods are historical records, while a second record for the same student
and period conflicts. `TRANSFERRED` is not an enrollment state.

The bounded state machine is:

| Current state | Allowed next state |
| --- | --- |
| PENDING | ACTIVE, CANCELLED |
| ACTIVE | WITHDRAWN, COMPLETED |
| WITHDRAWN | ACTIVE only through the explicit, dated reactivation command |
| COMPLETED | none |
| CANCELLED | none |

Reactivation does not erase the withdrawn interval: the prior enrollment date,
withdrawal date, actor, effective date, reason code, and before/after states
remain in append-only audit and canonical event evidence before the current
row's interval dates are advanced. A new placement is not created by this
slice. Transfer-out is represented by withdrawal; placement transfer remains
the later M28-4 command.

## Authorization and API

Migration `0044_m28_enrollment_read` adds the catalog key `enrollments.read`
without granting it to any role. M28-1's `enrollments.manage` remains the
write capability. Reads require `enrollments.read`; create/transitions require
`enrollments.manage`. Effective permission is joined through the caller's
active institutional membership and an institution-owned role. Tenant and
institution are taken from the signed principal and applied to student,
period, campus, enrollment, and history lookups. Invisible references return
404. There is no implicit SYSTEM_ADMIN or teacher authority.

- `GET /api/v1/enrollments/options`: caller-scoped, non-closed periods and
  institutional campuses for the create form.
- `GET /api/v1/enrollments?student_profile_id=...&limit=...`: bounded records
  with period label, dates, revision and backend-provided allowed actions.
- `GET /api/v1/enrollments/{id}` and `GET .../{id}/history`: scoped record and
  minimized append-only transition audit.
- `POST /api/v1/enrollments`: strict create-only contract; accepts PENDING or
  ACTIVE. ACTIVE requires an ACTIVE period and an in-period effective date.
- `PATCH /api/v1/enrollments/{id}/status`: bounded target, required expected
  revision, effective date where required, and bounded reason code where
  contracted. Unknown/server-controlled fields and `TRANSFERRED` are rejected.

Closed periods are read-only. All effective dates must fit the configured
period; activation, withdrawal, completion and reactivation cannot precede
the applicable enrollment interval. Withdrawal closes active placement rows
atomically and rejects a date that would leave a placement starting later.
Cancellation rejects an active placement. No calendar assumption is
hard-coded.

## Idempotency, concurrency and evidence

An exact create retry resolves to the existing same-period row and emits no
duplicate audit/event; a differing duplicate is 409. A transition command
locks the enrollment row and compares `expected_updated_at`. Replaying the
same committed target/date/reason is a no-op; stale or competing transitions
receive 409. Unique constraints remain the final defense for concurrent
creates.

The canonical enrollment service owns `student.enrollment.created` and
`student.enrollment.status_changed` v1 events, preserving existing M21 fields.
Every create/status change writes bounded audit metadata and the M18 outbox in
the caller's transaction. Effective/business dates are not substituted for
ledger timestamps. Audit/outbox failure rolls the domain change back. M24 CSV
still calls the same create service, retains its create-only item/savepoint
flow, and must satisfy `students.manage` plus `enrollments.manage` at apply.
Its preview also rejects ACTIVE rows without `enrolled_on`, rows outside the
period dates, and rows targeting a non-ACTIVE or closed period before they are
marked valid.

No schema/RLS policy or migration before 0044 was altered. Revision 0044 only
adds the missing frozen read permission; it adds no role grants and does not
modify RLS. Completion effective date is retained in audit/event history; the
authoritative M1 row has no dedicated `completed_on` column.

## React experience and limits

The existing student-record workspace presents a separate enrollment panel:
period/campus selection, PENDING/ACTIVE create, history across periods,
backend-supplied allowed transition buttons, effective dates, and transition
history on demand. Read and manage controls use effective permission keys;
commands refetch authoritative state and a 409 refreshes the query. It does
not offer placement/section transfer or create one automatically.

Validation uses focused lifecycle/HTTP/PostgreSQL/RLS tests, M1/M18/M24/M28-1
regression, focused React tests, typecheck/build, changed-file Ruff,
`py_compile`, Alembic and diff checks. The full backend suite is not required
for this bounded service/migration; M28-7 and M28-8 remain the integration
gates. No M28-3 work is implied.
