# M28-7 — Operational history and evidence continuity

Status: CLOSED / PASS for M28-7. This document records the existing domain
boundaries and the paths exercised by the M28 operational integration suites.
It does not add another authority or projection.

## Authority and evidence map

| Fact | Authority and primary identity | Tenant/institution key | Canonical source | Downstream use | Audit / provenance |
| --- | --- | --- | --- | --- | --- |
| Student profile | M1 `student_profiles.id` | `organization_id`, `institution_id` | `student.profile.created`, `student.profile.updated` | M22 roster/evidence joins; M21 does not project profile events | M0 `audit_logs`; M18 outbox/ledger event IDs |
| Enrollment | M1 `enrollments.id` | `organization_id`, `institution_id` | `student.enrollment.created`, `student.enrollment.status_changed` | M21 ENROLLMENT; M22 roster | M0 audit + M18 event/outbox |
| Academic period | M1 `academic_periods.id` | `organization_id`, `institution_id` | `academic_period.created`, `academic_period.status_changed` | M2/M3 scope; M22 period calculations; not an M21 timeline event | M0 audit + M18 |
| Section | M2 `sections.id` | `organization_id`, `institution_id` | `academic.section.created` | M2 placements, M22 cohort/section evidence | M0 audit + M18 |
| Placement | M2 `student_section_assignments.id` | `organization_id`, `institution_id` | `student.section.assigned`, `student.section.transferred` | authoritative roster input for M10, M20, M22; not an M21 timeline event | retained placement rows + M0 audit + M18 |
| Roster | Derived from M1 enrollment and M2 active, date-valid placement and M2 teaching assignment | principal tenant/institution and assignment scope | no independent event or ID | M10/M20 teacher roster; M22 dimensions | source rows and their audits/events |
| Attendance | M3 `attendance_records.id`, unique by session and placement | `organization_id`, `institution_id` | `student.attendance.recorded`, `student.attendance.updated` | M18, M21 ATTENDANCE, M22 attendance facts | M0 audit records prior/current correction and actor; M18 source outbox ID |
| Assessment | M3 `assessments.id` | `organization_id`, `institution_id` | `assessment.created`, `assessment.status_changed` | M22 grading facts; no M21 assessment-definition timeline entry | M0 audit + M18 |
| Result | M3 `grade_entries.id`, unique by assessment and placement | `organization_id`, `institution_id` | `student.grade.recorded`, `student.grade.updated` | M18, M21 ACADEMIC, M22 result facts | M0 audit records prior/current state, revision, actor, and time; M18 source outbox ID |
| Student timeline | M21 `student_timeline_entries.id`; source unique `(institution_id, ledger_event_id)` | `organization_id`, `institution_id` | M18 ledger event | authorized student-history read | `ledger_event_id`, ledger position, source aggregate, actor, correlation/causation IDs, occurred/recorded/projected timestamps |
| Signal / priority | M22 `intelligence_signals.id` and versioned snapshots | `organization_id`, `institution_id` | deterministic M22 rules over M1/M2/M3 and M21 intervention evidence | existing M22 views; eligible source for governed M27 review | rule-set/projection version, evidence references, source data; signals do not replace operational facts |
| Accountability case | M27 `accountability_cases.id` | `organization_id`, `institution_id` | human-governed M27 commands and M27 source references | M27 queue/review/decision/obligation views | M27 source/event IDs, provenance/fingerprint hashes, actor and policy/projection versions |
| Decision | M27 `accountability_decisions.id` | `organization_id`, `institution_id` | explicit authorized human decision after review | M27 accountability state; may request an existing governed M21/M23 path | append-only decision and M18 event; no direct M3 mutation |
| Obligation / follow-up | M27 obligation ID for accountability responsibility; M21 action/follow-up ID for execution | `organization_id`, `institution_id` | M27 obligation command or M21 action/follow-up command, respectively | M27 queue references the M21 execution | each domain's audit/event history; the two authorities remain distinct |

UUIDs remain the primary references across these domains. A timeline row is a
projection of one M18 ledger event, not a replacement for its source record.
External import identity remains in M24's `integration_external_student_refs`
and import-run records; the created student/enrollment retain their M1 IDs.

## Operational history reconstruction

The source-of-truth record and M0 audit history reconstruct student updates,
enrollment transitions, placement transfers, attendance corrections, and
result corrections. The M28 services write the business mutation, required
audit, and canonical outbox event in one transaction. M18 ingestion preserves
the source outbox ID, event type/version, tenant/institution, actor when
available, correlation/causation, occurred time, and recorded time. Placement
transfer retains the previous placement with its end date and creates the new
placement; attendance/result correction audit retains before/after values
while the operational row holds the current value.

Reconstruction therefore uses the authoritative row for current state, the
audit row(s) for exact correction history, and the M18 ledger for canonical
cross-domain chronology. Mutable screen state is not evidence. Student profile
event payloads are identifier-only; the event is a chronology marker and does
not replace the profile or audit record.

## Event and projection continuity

For supported event facts, the path is:

```text
M1/M2/M3 command
  → same-transaction outbox_events row
  → M18 event_ledger row (source_outbox_event_id is unique)
  → existing versioned consumer / projection
```

M20 offline attendance calls the same M3 attendance mutation service. Its
`teacher.attendance.synced` event and immutable receipt describe sync
operations; they are not attendance truth and are not M21 timeline inputs.
Online and offline attendance therefore use the same M3 row and canonical
`student.attendance.*` family. M3 result commands retain
`student.grade.recorded` / `student.grade.updated`. Assessment-definition
events remain distinct and are not added to the student timeline.

M21 consumes its explicit event allowlist from M18 and inserts idempotently on
`(institution_id, ledger_event_id)`. The executed M28-6 result integration
observed recorded and updated grade facts in the ledger and timeline, including
correction sequence. The opt-in M21 E2E executed both online and M20 offline
attendance paths against the configured local DB; the offline path observed
one canonical attendance timeline fact after retry. M21 does not receive a
direct M28 write.

M22 is not an M18/M21 event consumer: its established projector derives
signals and snapshots from tenant-scoped operational attendance, grade,
enrollment/placement and M21 intervention/outcome data under its existing
rules and policy. M21 and M22 can therefore expose different views over the
same authoritative facts. No new M22 rule or M28-specific signal is added.

M27 source rows refer to existing M22/M21 evidence and retain entity/event
references plus provenance and fingerprint hashes. Case review, decision,
ownership, and obligations remain explicit M27 commands. A priority does not
automatically create a case decision or intervention. A `CREATE_INTERVENTION`
decision only requests the established human-approved M23/M21 path.

## Provenance, freshness, and asynchronous boundaries

M18 ledger rows identify the source outbox row, tenant/institution, event type
and version, aggregate identity, actor when present, event/record times, and
correlation/causation. M21 stores the ledger event ID/position, source
aggregate, actor and timestamps and sets `projected_at`. Its institution
checkpoint records `last_position`, `processed_count`, and `updated_at`.
M18 activity projections expose their own checkpoint and projection update
time. M22 snapshots/signals carry named rule-set and projection versions and
refresh timestamps. M27 projections and source records retain their
projection/policy versions and source lineage.

Outbox-to-ledger ingestion and downstream projections are asynchronous batch
steps; a committed operational write does not itself mean a downstream view
has caught up. Consumers advance checkpoints independently. Freshness must be
read from the corresponding checkpoint/projection metadata where exposed; a
timeline or intelligence view without a newer checkpoint is not proof of
current processing. The platform has no single distributed watermark across
M18, M21, M22, and M27, so this slice does not claim one.

## Security and authority continuity

Operational commands derive organization and institution from the authenticated
principal and validate linked period, section, placement, offering and student
relationships. RLS remains enabled and forced on the protected M18/M21/M22/M27
tables; composite tenant links and institution context remain in force.
Projector permission is a distinct system projection boundary: the M21 runtime
insert needs the installed INSERT policy and, for `INSERT ... RETURNING`, the
installed SELECT visibility policy. It does not grant teachers timeline write
authority or grant academic command permission to `SYSTEM_ADMIN`.

Cross-tenant event/projection data is rejected or invisible under existing
tenant policies. No owner/superuser role is used by runtime projections. The
M21 RLS regression also exercises same-tenant insertion and denies mismatched
tenant/context and unauthorized principal attempts. Read permission remains
separate from projection permission.

Operational events cannot directly perform discipline, promotion, retention,
enrollment termination, grade override, sanction, or high-impact intervention.
Those outcomes remain behind their existing domain services and, where
required, human review and decision authority.

## M24 and M20 continuity

M24's create-only student/enrollment import records its connector/external
student reference and run/item provenance, then calls the canonical student
and enrollment services. Imported enrollment therefore uses the ordinary M1
enrollment ID, validation, audit, and lifecycle event; a subsequent status
change uses the same enrollment lifecycle service. No import-only enrollment
authority exists.

M20 stores an actor-bound idempotency receipt, reauthorizes current teacher
assignment and roster on sync, and calls the M3 mutation. Replay returns the
receipt without a second attendance mutation/event; a sync-activity event is
additional provenance only. No grade offline protocol is introduced.

## Privacy and non-expansion

M18 and M21 use allowlisted minimized event fields. Attendance notes and grade
feedback are excluded from M18/M21 projection context. Profile names, guardian
contact, health, and unrelated profile fields are not added to these payloads.
M22/M27 retain their existing evidence and small-cell/privacy controls; no
provider payload or hidden reasoning is included in provenance.

M28-7 adds no schema, migration, event family, signal rule, accountability
automation, dashboard, or high-impact action. M28-6's historical M3
`assessments.max_score` database default of 10 remains for direct-SQL/backward
compatibility. Supported M3 and M10 definition commands require explicit
`max_score`, and the M28-6 HTTP integration rejects its omission. Direct SQL is
outside that command contract.

## Validation evidence and boundaries

The cleanup-safe M28-3/4 integration fixture proves the real authorized
placement, online attendance creation/correction, M20 offline convergence,
receipt/replay, revocation, audit/outbox rollback and tenant/scope checks. The
M28-6 integration fixture proves explicit assessment scale, result creation
and correction history, canonical M3 → M18 ingestion, M21 projection, and
projector RLS denials. The M21 E2E is opt-in through
`M21_E2E_DATABASE_URL`; when explicitly pointed to the configured local
application database, its two online/offline tests execute and pass. M24
import-to-enrollment and M27 append-only human review/decision/ownership tests
are separate suites, not one combined cross-milestone transaction.

M22 does not derive its signals from M21 timeline rows, and no existing
contract automatically creates an M27 case from every M22 signal. The valid
boundary is that M22 evaluates supported operational/M21 evidence and M27 can
reference eligible existing signal/evidence through its authorized human
review path. M22/M27 synthetic scenarios are not fabricated merely to force a
single automated chain. Projection processing is asynchronous as described
above.

For this closeout, the focused cross-milestone run passed 60 tests with two
opt-in M21 cases skipped because the environment variable was absent. The
same two M21 cases were then run with `M21_E2E_DATABASE_URL` explicitly set to
the local application database and passed (2 passed, 0 skipped). The required
full backend run passed 768 tests with the two opt-in cases skipped in its
default environment (0 failed). The full frontend suite passed 76 tests;
typecheck and one production build passed. The build reported the existing
dynamic-import/chunk-size warnings. No Python source changed, so changed-file
Ruff and `py_compile` had no targets. Alembic remained at
`0046_m28_attendance_perms`; `git diff --check` passed.
