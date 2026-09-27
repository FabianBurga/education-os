# M28-3 — Academic structure operations

Status: CLOSED / PASS on `m28-operational-adoption-core`.

## Authorities and relationships

M1 `academic_periods` remains the institution's canonical temporal boundary;
no SchoolYear table was introduced. M2 `academic_levels` → `grade_levels` →
`sections` and the `subjects` catalog remain authoritative. `CourseOffering`
continues to bind one section to one subject for its period. Curriculum plans
and curriculum-subject links remain optional M2 configuration, not a new
curriculum engine. M0 campuses and M1 staff profiles are referenced, never
copied. No new academic structure or assignment table was created.

Student enrollment and M2 placement stay distinct. This slice does not create,
transfer, end, or derive a student roster. The pre-existing section-assignment
endpoint remains protected by `academics.assign`; placement lifecycle belongs
to M28-4. Teacher-assignment creation is available only to `academics.assign`,
while its historical end/reassignment workflow remains M28-4.

## Authorization and API

Forward-only migration `0045_m28_academic_permissions` registers
`academics.read`, `academics.manage`, and `academics.assign`. It grants none of
them to a role. They must be explicitly granted to an institution-owned role;
role names, `SYSTEM_ADMIN`, and legacy console access do not themselves grant
academic authority. Every service command checks active principal-bound
institution membership, an institution-owned role, and the effective key.
Queries use the signed principal's organization/institution and explicit
tenant predicates; hidden and foreign references return not-visible responses.

Existing `/api/v1/academics/*` list/create endpoints now use operation-level
permissions. Academic reads include bounded institutional lists and
`/academics/options` for non-closed periods and campuses. Assignment options
require `academics.assign` and expose only active staff identifiers plus a
bounded staff code/fallback label. Strict mutation schemas reject unknown and
server-owned fields.

`GET /api/v1/academic-periods` requires `academics.read`; creation requires
`academics.manage` and creates only `PLANNED`. The added status command accepts
only `PLANNED → ACTIVE → CLOSED`, carries `expected_status`, and returns 409 for
stale/invalid transitions. Closing is rejected while the period has an ACTIVE
enrollment. No overlap/calendar assumptions are added. Existing periods,
enrollments, and their foreign references are retained.

M2 commands continue through the existing API paths for levels, grades,
subjects, sections, curriculum plans/subjects, course offerings, teaching
assignments, schedule slots, and the already-existing student-section
assignment command. Create operations validate all referenced IDs in the
authenticated institution. Sections require an in-scope, non-closed period,
campus and grade. Course offerings require in-scope section/subject, and an
optional curriculum-subject link must match the subject, grade and period.
Teacher assignment requires active in-scope staff and dates within the
offering period. Natural unique constraints remain the duplicate defense;
conflicts return 409. No delete or arbitrary update command was added because
the existing models have no revision fields/history contract for generic
editing. Period lifecycle is the only new bounded update.

## History, audit and events

Every touched create/status mutation appends its existing M1/M2 canonical
business event and a bounded audit record in the same database transaction.
Events carry opaque entity references and bounded codes/relationship IDs, not
student/teacher names or free text. A failed outbox enqueue prevents the domain
write from committing. Period closure emits the additive
`academic_period.status_changed` event with previous/new status. No UI activity
events are emitted. RLS/FORCE RLS and existing composite tenant foreign keys
were not modified; migration 0045 changes only the permission catalog.

## React workspace and limits

The existing TanStack Router/Query shell exposes an “Estructura académica”
workspace via effective `academics.read`. `academics.manage` reveals period,
level/grade, subject, section, and course-offering setup forms; assignment
creation additionally requires `academics.assign`. Period transitions refetch
server state. Loading, empty collections, 403/404/409/422 and generic network
errors have distinct bounded messages. Frontend checks are UX only; the API
repeats authorization and relationship validation.

There is no new authority, RLS policy, calendar engine, placement transfer,
roster mutation, attendance, assessment/result workflow, delete operation, or
generic editing framework. The existing uniqueness constraints are preserved.

## Validation

Directed validation: 49 passed, 0 failed across M28-3 PostgreSQL/HTTP security
and integrity, M2 contracts/RLS, M1 contracts, M24 import, M18 event/outbox,
and M28-1/2 compatibility. Tests include a real foreign-tenant academic
relationship attempt, operation permission denial (including teacher and bare
SYSTEM_ADMIN), period close with active enrollment, preserved enrollment after
period closure, and injected outbox failure rollback. Focused frontend tests,
typecheck and production build passed. Full backend was not required: no shared
authorization/RLS/transaction primitive or cross-domain schema was changed.
