# M28-1 — Secure Student Record

Status: CLOSED / PASS on `m28-operational-adoption-core`.

## Authorities and scope

This slice reuses M0 `Person` and M1 `StudentProfile`. Enrollment remains the
separate M1 enrollment authority; academic placement remains M2. No M28 student,
person, enrollment or placement table was added. M28-1 exposes a minimized
institutional record and bounded profile maintenance only. It does not implement
enrollment lifecycle, guardian linking, person editing, account creation, or
academic placement.

## Permissions and tenant boundary

Migration `0043_m28_student_record_perms` adds catalog entries `students.read`,
`students.manage`, and the M24 prerequisite `enrollments.manage`. It grants none
of them to roles automatically. The API resolves effective permissions through
active institution membership and role-permission assignments. Existing M1
staff guards remain in force; teacher-only access remains on scoped teacher APIs.
`SYSTEM_ADMIN` or Rector labels alone do not grant student-record access.

Every student query and mutation is constrained by organization and institution
from the authenticated `CurrentPrincipal`, in addition to existing PostgreSQL
RLS/FORCE RLS. Unknown/out-of-scope identifiers return the same not-visible
response. Person reuse on the API create path additionally requires
`admin.people.manage`; the M24 import path instead creates its Person within the
authorized import transaction.

## API and concurrency

- `GET /api/v1/students/records?limit=50&cursor=<profile-id>` returns a bounded,
  keyset page with profile ID, display name, student code, status, and revision
  timestamp. Cursors are resolved only inside the caller's institution.
- `GET /api/v1/students?limit=100` retains the legacy array shape but is capped
  and returns the same minimized record fields.
- `GET /api/v1/students/{id}` reads a single scoped record.
- `POST /api/v1/students` creates a profile for an authorized existing Person;
  repeating the same person/code is idempotent and returns the existing record.
- `PATCH /api/v1/students/{id}` accepts only `student_code`, bounded `status`,
  and required `expected_updated_at`. A row lock plus revision comparison
  returns 409 for stale writes. Status changes that conflict with an active
  enrollment are rejected; enrollment transitions are not implemented here.

Unknown mutation fields are rejected. Tenant, identity ownership, creator,
permissions, audit fields, and timestamps are server-controlled. There is no
delete operation. The React workspace uses effective `students.read` and
`students.manage` capabilities for navigation and edit controls; backend checks
remain authoritative.

## Audit, events, and M24

Student create/update, audit rows, and M18 transactional-outbox events share the
caller's transaction. Event payloads contain opaque profile references and
changed field names only; names, contact data, and free text are not copied.
M24 CSV apply still uses the canonical Person/StudentProfile/Enrollment services
and additionally requires `integrations.run`, `students.manage`, and
`enrollments.manage`. Item savepoints keep import facts, lineage, audit, and
events atomic. No separate import or student authority was introduced.

## Validation and limitations

The implementation was validated with application-role PostgreSQL HTTP tests,
including cross-tenant/out-of-scope IDs and cursors, permission denial, mass
assignment, stale update conflict, duplicate create replay, and injected audit
failure rollback. Full backend: 749 passed, 1 skipped, 0 failed; the skip is the
opt-in M21 E2E without `M21_E2E_DATABASE_URL`. Frontend: 71 tests, typecheck,
and production build passed. Ruff and `py_compile` passed on changed Python
files. The production build retains existing M27 dynamic-import/chunk-size
warnings.

No guardian-link workflow, student creation UI, search, enrollment history, or
placement is included. Enrollment lifecycle and academic workflows remain
future slices; no M28-2 implementation is implied by this document.
