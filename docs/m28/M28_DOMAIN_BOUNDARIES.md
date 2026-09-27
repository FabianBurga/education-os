# M28 domain boundaries and lifecycle contract v1

Status: scope/behavior freeze for implementation after M28-0 review.
Existing behavior and proposed behavior are distinguished in the
[inventory](M28_CAPABILITY_INVENTORY.md). This document does not assert that
the future guarantees are already implemented.

## Authorities and coexistence

| Concept | Owner | Mode in M28 |
| --- | --- | --- |
| Person, account, access membership | M0 identity, M8 admin service | OWN; reference one organization person, never equate account membership with enrollment |
| Student institutional profile | M1 students | OWN / IMPORT via M24 canonical command; no `m28_students` |
| Guardian/family/staff profile and relationship | M1 families, M8 staff service | OWN / REFERENCE; portal grants remain M6/M12 |
| Period and enrollment | M1 enrollment | OWN / IMPORT create-only via M24 |
| Levels, sections, subjects, offerings, placements, teaching assignments | M2 academics | OWN; future external mappings remain M24 responsibility |
| Attendance/session/code | M3 attendance | OWN; M10 online and M20 offline are entry paths, not authorities |
| Assessment/grade entry | M3 grades | OWN; no automatic official final result |
| Chronology, policy, offline protocol | M18 / M19 / M20 | REFERENCE / reuse |
| Timeline/intervention, intelligence, accountability | M21 / M22 / M27 | REFERENCE; consumers retain their own authority and permissions |
| Connector/external identity/run | M24 | IMPORT; current connector is create-only CSV, not SYNC |

SYNC is a deferred mode, not an available connector. Imported records carry
M24 lineage; immutable external student identity remains qualified by tenant
and connector. No person matching by name, email or student_code. A conflicting
mapping is an explicit conflict, never a merge. An external SIS can remain
upstream while Education OS owns accepted local operational facts. Bidirectional
updates or external ownership of additional entities require a later contract.

## Student identity and minimal record

`persons.id` is organization identity. `student_profiles.id` is institution
identity, unique by institution/person. `enrollments.id` is period enrollment.
`student_section_assignments.id` is placement and is referenced by attendance
and grades. These identifiers are stable and are not interchangeable.

`memberships` grants a user account institution access; a student needs neither
a login nor a new membership to be enrolled. No cross-organization identity
resolution is introduced. Current student_code is nullable and is not a
globally unique identifier; do not add uniqueness without a data preflight.

Student lifecycle remains ACTIVE/INACTIVE/ARCHIVED. Inactivation/archive is
explicit, authorized and reasoned. M28 rejects inactivation/archive while an
ACTIVE enrollment exists; staff resolve that enrollment first. Reactivation
of a profile does not reactivate enrollment or placement. No public delete,
person merge, tenant reassignment or cascading record deletion is added.

The operator record contains permitted name/code, profile state, enrollment
period/state, current placement and links to authorized history. Names stay in
Person, not in duplicate enrollment/metric records. Existing guardian links
are separately permission-gated; adding a link is audited and does not grant
portal access. Broad person editing, account creation and role assignment stay
in M8 under their existing boundaries. A minimized student-create command may
create Person + StudentProfile atomically without giving staff role-management
permission. Reusing a person requires an authorized institution reference or
explicit identity administration; organization RLS alone is insufficient.

## Enrollment v1

Meaning: one student's institutional registration for one academic period and
campus. Existing unique `(student_profile_id, academic_period_id)` remains.
Multiple historical enrollments across periods are valid. Never overwrite a
prior period's enrollment to promote a student.

| Command | Allowed state change | Required evidence / effect |
| --- | --- | --- |
| Create | absent -> PENDING or ACTIVE | visible active student, period/campus in tenant; ACTIVE requires valid enrolled_on |
| Activate | PENDING -> ACTIVE | period ACTIVE; enrolled_on within period |
| Cancel | PENDING -> CANCELLED | explicit confirmation + bounded reason; no active placement |
| Withdraw | ACTIVE -> WITHDRAWN | withdrawn_on >= enrolled_on and within period; close current placement atomically |
| Complete | ACTIVE -> COMPLETED | explicit human action; completion date within period, never inferred from grade |
| Reactivate | WITHDRAWN -> ACTIVE | same row/period, reason, expected revision, period ACTIVE; new placement must be explicit |

Other transitions are rejected, including COMPLETED/CANCELLED -> ACTIVE.
Repeat of the same command identity replays; a different command requesting
the current status is a no-op and emits no transition. TRANSFERRED is not an
enrollment status. Do not add it. Institutional transfer-out uses withdrawal;
destination admission is separately authorized in its own tenant. No command
mutates two institutions.

Before-images, transition time, actor, command ID, effective date and reason
are retained in audit/event history. Reactivation may clear the current
withdrawn_on field only after the previous withdrawal fact has been retained;
it cannot erase that interval or change prior attendance/grade references.
Withdrawing closes placement as WITHDRAWN; completion leaves historical
placement rows intact and removes effective roster eligibility via terminal
enrollment. No invented COMPLETED placement state. Before reactivation/new
placement, an old terminal placement must not be reused for a new interval.

## Academic structure and dates

AcademicPeriod represents the institution's configured cycle (including a
school year); GradingPeriod is its assessment/reporting subperiod. Do not add
a second SchoolYear table. Level -> GradeLevel -> Section is reused.
Section binds period/campus/grade. Subject is a catalog item; CourseOffering
binds section/subject and inherits its period. Curriculum remains optional
existing configuration; no new curriculum authoring platform.

Periods remain PLANNED/ACTIVE/CLOSED. M28 supports PLANNED -> ACTIVE -> CLOSED;
closed periods are read-only for operational mutations. Closing requires an
explicit confirmation and no ACTIVE enrollments. Do not automatically complete
students. Overlapping periods are not globally prohibited because the schema
permits multiple programs/cycles; no invented one-year-only rule. Subperiod
dates must fit their parent. Class session dates fit the offering's period;
schedule slot must belong to that offering. Configuration labels/maxima are
institutional data, not hardcoded Ecuador-specific rules.

Placement transfer on date D closes prior placement with inclusive ended_on
D-1, status TRANSFERRED, then inserts a new ACTIVE placement at D in the same
period and campus. For M28 v1, D must be later than prior assigned_on and must
not strand existing attendance/grade facts outside their original placement.
Same-day ambiguous placement correction and cross-campus transfer are deferred
to an explicit correction contract; reject instead of moving historical facts.
Stored date ranges are inclusive. Withdrawal uses its explicit last eligible
date. Record historical interpretation in the migration preflight; never
reinterpret old ended_on values by bulk update. Retain unique ACTIVE placement
per enrollment and lock that enrollment during transfers.

TeachingAssignment remains one row per offering/staff; starts_on/ends_on are
inclusive, nullable bounds. End/revise that assignment with an audited command,
not delete/recreate hidden history. A second disjoint tenure for the same pair
needs a separate future history design; do not drop the unique constraint to
make an insert pass. Roster is a bounded query, never a new authority.

## Attendance and result guarantees

Attendance unit: `(class_session_id, student_section_assignment_id)`; session
identity is `(course_offering_id, session_date, starts_at)`. Preserve attendance
code semantics PRESENT/ABSENT/LATE/EXCUSED/REMOTE/OTHER and configured counting
flags. Missing attendance is unknown, never silently ABSENT. A teacher requires
current assignment plus permission and eligible historical roster/date for the
fact being entered. A revoked assignment rejects pending writes at sync time.
Historical correction after withdrawal requires separately scoped institutional
correction permission, never a bypass through the teacher route.

All online/offline attendance writers must share target-lock/conflict rules,
one atomic fact/audit/outbox transaction and a durable idempotency identity.
First insert emits recorded; actual correction emits updated; unchanged retry
does neither again. Preserve M20 base-state comparison and receipt vocabulary;
additive canonical event emission must not change its request/response schema.
Existing notes remain minimized domain data, not ledger payloads. Closed or
cancelled sessions reject routine writes. Exceptional reopening is deferred.

Assessment definition remains separate from GradeEntry and GradingPeriod.
Preserve result states PENDING/GRADED/MISSING/EXCUSED. GRADED requires a finite
score between zero and assessment.max_score. For new M28 commands, other states
carry no score; existing mixed historical data is surfaced, not silently
rewritten. Missing/excused is not numeric zero. DB Numeric(8,3) and existing
numeric API compatibility must be handled consistently; no arbitrary national
scale or hidden rounding. Maxima/period/category must agree with offering.

Corrections record prior/new bounded values, actor/reason/revision. A published
or used assessment's denominator is immutable in M28 v1; no mass recalculation.
No automatic final grade, pass/fail, promotion, ranking or causal claim.
Assessment vocabulary remains DRAFT/PUBLISHED/CLOSED/ARCHIVED. M28 permits
explicit DRAFT -> PUBLISHED -> CLOSED -> ARCHIVED and unused DRAFT -> ARCHIVED;
no automatic publication or reopening. Preserve existing entry into a DRAFT
assessment for compatibility, but label it as draft and never interpret absent
draft entries as MISSING. Entries in CLOSED/ARCHIVED assessments reject routine
mutation; exceptional reopening/final certification is deferred. Attendance
sessions remain OPEN/CLOSED/CANCELLED: close explicitly, cancel only an unused
OPEN session, and never erase its records. These bounded lifecycle commands
belong in the existing attendance/grades services and emit minimized audit facts.

## Transactions and compatibility

New bounded commands require request identity, expected revision/base state,
explicit typed field allowlist and server-derived tenant. Same identity + same
payload replays after authorization; changed payload is 409. Concurrent
competitors produce one authoritative result and a conflict. New commands may
use a narrow receipt/version extension if existing audit/outbox identifiers
cannot enforce uniqueness. M20 receipts stay attendance-only; M24 receipt/run
identity stays integration-owned. No generic workflow/command engine.

New reason vocabulary is closed per command: profile correction uses
DATA_ENTRY_ERROR or INSTITUTIONAL_REQUEST; cancellation uses DATA_ENTRY_ERROR
or INSTITUTIONAL_REQUEST; withdrawal uses STUDENT_WITHDRAWAL or TRANSFER_OUT;
reactivation uses RETURN_TO_STUDY; completion uses PERIOD_COMPLETION; placement
transfer uses PLACEMENT_CHANGE; attendance/result amendments use
DATA_ENTRY_ERROR or EVIDENCE_CORRECTION. These are audit classifications, not
automatic grants. M20 v1 has no human reason field: keep its wire contract and
record OFFLINE_RECONCILIATION as a server-derived technical source reason for
ordinary sync. It cannot perform the exceptional historical correction flow
that requires explicit human evidence/reason. Do not invent free-text reasons
or require M20 v1 clients to submit an unsupported field.

Mutations, audit, receipt and canonical event are one transaction owned by the
outer command. Remove nested commits only in the touched domain, with directed
M10/M20/M24 regression. Existing endpoints keep their successful response
shape; stricter authorization must cover them too. Pagination is additive
(a bounded new read contract or explicit compatible parameters), not a silent
array-to-envelope replacement. No new operation may retain a legacy bypass.

M18–M27 frozen schemas/events/permissions retain meaning. Additive adapters
and forward migrations are allowed only to implement these scoped guarantees.
If a fix requires weakening or redefining those contracts, Luna escalates to
ASTRA before implementing it. No migration or runtime change occurs in M28-0.
