# M28-6 — Assessment and results operations

## Authority

Assessment definitions and student results remain the M3 `assessments` and
`grade_entries` records. An assessment is the activity being evaluated; a
result is evidence for one eligible student's placement against that
assessment. M2 course offerings, periods, teacher assignments, enrollments and
placements remain the academic scope authorities. No gradebook or parallel
result store is introduced.

Assessment status follows the existing `DRAFT`, `PUBLISHED`, `CLOSED`, and
`ARCHIVED` vocabulary. New definitions start as `DRAFT`. Bounded expected-state
commands move them through the lifecycle. A closed or archived assessment is
not writable. Grading periods must belong to the offering's academic period;
categories and assessments are likewise scoped to that offering and period.

## Result semantics and scores

`GradeEntry` retains M3's `PENDING`, `GRADED`, `MISSING`, and `EXCUSED`
statuses. `GRADED` requires a finite numeric score. Other statuses require a
null score. Zero is a numeric result, not missing. The maximum must be supplied
for each assessment and is the upper bound; the entry path does not substitute
a universal 10, 20, or 100 scale. Inputs preserve the existing `NUMERIC(8,3)`
precision and reject excess fractional precision instead of silently rounding
authoritative values.

Every result must reference the assessment's course offering and a current,
active placement/enrollment for its student in the same institution and
academic period. The student is not copied into a new M28 authority. A unique
M3 assessment/placement result remains the only current result.

## Authorization

Teacher commands use the established M10 Teacher Console permission
`teacher.grades.manage` and recheck the current teacher assignment to the
offering, tenant, active period and offering scope. The generic M3 management
API remains for institutional actors with effective `academics.read` or
`academics.manage` permission as appropriate. Those grants are not inferred
from role names; `SYSTEM_ADMIN` alone does not authorize academic mutations.
Tenant and institution are always derived from the authenticated principal.
Object reads and relationship validation fail closed for foreign references.

## Correction, concurrency, and retry

Writes use explicit payload schemas and operation IDs. Transaction-scoped
advisory locks serialize retries for one logical operation; assessment and
result rows are locked for state checks. Corrections require the caller's
expected revision and a bounded correction classification. Stale writes return
409; duplicate logical commands return the authoritative result without
duplicating result, correction, audit, or event. Exact no-op submissions are
receipted without increasing the result revision.

Revision and reconstructable before/after values are recorded in audit rows,
including actor, timestamp and correction classification. Result
mutation, audit, and canonical outbox event commit together. Failed transaction
steps leave none of them authoritative. The audit record is the change history;
M3's current result row remains the current value.

## Events and downstream continuity

M3 retains the established `student.grade.recorded` and
`student.grade.updated` business event names. Payloads contain only identifiers,
status, score, revision and the prior score/status needed to interpret a
correction; feedback and unrelated student data are excluded. M20 is not a
result authority and no offline grade protocol is added.

M18 ingests the transactional outbox into its canonical event ledger. The
existing M21 projector consumes supported grade events and creates timeline
evidence through its RLS-protected projection path; M28 does not write M21
storage directly. The projector principal must satisfy both the timeline
projection INSERT policy (`admin.console.access`) and the SELECT visibility
policy required by `INSERT ... RETURNING` (base timeline read plus a recognized
institutional projector role or the existing teacher student scope). Result
facts are projected as academic evidence. Assessment definition events are not
added to the M21 timeline. M22 and M27 receive no new rules or authority here.

## Privacy and exclusions

Result responses contain only assessment/result and placement identifiers,
score/status, revision and the fields required by the existing teacher
workflow. Free-text feedback is not placed in canonical event payloads.
Authorization errors do not disclose foreign object details.

M28-6 does not calculate weighted terms, final grades, GPA, report cards,
promotion, retention, graduation or student progression. It does not add a new
curriculum authority, grading scale, offline result protocol, or bulk grade
engine. Existing scale/category/period setup remains in M3; no new schema or
RLS policy was required for this slice.

The historical M3 `assessments.max_score` database default remains for
compatibility. Supported M3 and M10 assessment creation requests require an
explicit maximum and never rely on that default. Direct SQL writes remain
outside the domain command contract.

## Validation note

The M21 continuity integration uses an isolated synthetic projector role with
only the permissions needed to exercise the installed RLS contract. Negative
attempts prove that a teacher, an unprivileged principal, and a mismatched
institution row cannot insert timeline evidence. No runtime projector or RLS
policy change was required.
