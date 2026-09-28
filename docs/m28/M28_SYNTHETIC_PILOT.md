# M28-8 synthetic operational pilot

Status: pilot journey executed successfully in a rollback-contained local
PostgreSQL transaction. Synthetic data only; no institution or student data was
retained.

## Pilot model and roles

The integration journey provisions one isolated organization and institution,
one campus, one active academic period, two grade/section contexts, two
subjects, four course offerings, two assigned teachers, and ten synthetic
students. Each student has an active enrollment and placement. Teacher A and
Teacher B have distinct assignment scopes. The rector-equivalent and
coordinator receive only the explicit institutional permissions used by the
scenario. The SYSTEM_ADMIN test identity receives only `admin.console.access`
and `student_timeline.read`; it has no academic permissions. An unprivileged
identity is used for denial checks.

The fixture provisions only identities and tenant roots with the owner setup
connection. Student profiles, academic structure, enrollment, placements,
attendance, assessments, results, corrections, and transfers use the existing
application APIs/services. The app-role session is enclosed in an outer
transaction and rolled back after the scenario. Bootstrap rows are removed by
their exact synthetic IDs. Repeated runs do not depend on prior pilot rows.

## Executed journey

The live API journey creates and updates a student record, proves stale update
conflict and minimal response fields, creates an academic period and activates
it, configures grade/section/subjects/offerings and teacher assignments, then
creates ten PENDING enrollments and transitions them to ACTIVE. Placements are
distributed five per section. Teacher roster reads return only the assigned
five students; cross-teacher reads fail closed. One student transfers sections;
the old placement remains `TRANSFERRED`, the new placement is current, and the
enrollment remains ACTIVE.

Teacher A and Teacher B create separate assessment categories and assessments
with explicit maximum score 20. The assessments use the scoped Teacher Console
publication route. Ten eligible students receive results including a valid
zero. A correction records the prior zero, new `12.125` value, actor and
revision; a stale correction receives 409. Assessments and the grading period
are closed through expected-state commands after entry.

Teacher A records and corrects online attendance. Five class sessions exercise
the existing M22 attendance-risk condition. The M20 offline endpoint applies a
new attendance operation, returns `REPLAYED` for the same operation ID, and
returns deterministic `CONFLICT` for a stale operation with a new ID. All
online and offline attendance uses the same M3 attendance rows. A wrong-tenant
student read and an enrollment request with a foreign/nonexistent student
reference fail closed.

The test ingests application outbox rows into M18 under the limited projector
identity and verifies M1 enrollment, M3 attendance/result event families and
matching organization/institution keys. The existing M21 projector creates
attendance and grade timeline evidence; a second replay inserts zero rows.
M22's existing attendance rule produces an `ATTENDANCE_RISK` signal. The actual
signal and its M18 event feed M27 case projection. A manager assigns ownership;
an authorized coordinator reviews, records a human `MONITOR` decision and
completes a follow-up obligation against that human review. No intervention is
created automatically.

The existing M24 student/enrollment import continuity integration test is run
as part of the pilot gates. It applies one synthetic external enrollment
through the canonical M1 authority and verifies the external reference and
import event provenance, then activates the imported enrollment through the
normal lifecycle API.

## Security and evidence

The journey checks unauthorized student access, teacher attempts to configure
institution-wide academic structure, wrong-teacher roster access, SYSTEM_ADMIN
academic access, wrong-tenant student lookup, foreign student enrollment
injection, and exact student-record response fields. The broader existing M28
integration regression covers RLS/FORCE RLS, IDOR, foreign tenant references,
mass assignment, transactional outbox/audit behavior and role/scope matrices.
Projector activity uses the application connection and tenant context; no
owner/superuser projection path is used.

For one student, the reconstructable record is the M1 profile and enrollment,
M2 placement history, M3 attendance and result rows, M0 audit history for
corrections, M18 event ledger rows, and M21 entries keyed to source ledger
events. M22 signals are deterministic views over operational facts. M27
ownership, review, decision and obligation records remain separately governed.

## Observed boundaries and limitations

- M21's frozen consumer projects attendance and grade facts used here. It does
  not project the M22 signal-opened fact; M27 consumes that signal via its
  canonical M18 source event.
- The import continuity test is an existing separate M24 controlled fixture,
  not an import performed by the same ten-student journey.
- The pilot is synthetic technical evidence. It does not establish field
  validation, teacher adoption, time saved, learning outcomes or production
  certification.
- The application emits expected JWT key-length and Starlette/httpx deprecation
  warnings in the local test environment; they do not change the assertions or
  test result.

## Reproduction

From `backend`:

```powershell
..\.venv\Scripts\python.exe -m pytest -q tests/integration/test_m28_synthetic_pilot.py
..\.venv\Scripts\python.exe -m pytest -q tests/integration/test_m28_student_record_security.py::test_m24_imported_enrollment_continues_through_authorized_lifecycle
```
