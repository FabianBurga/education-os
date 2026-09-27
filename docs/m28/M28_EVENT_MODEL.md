# M28 operational event and evidence contract v1

## Actual data flow

Operational commands write M1/M2/M3 facts plus M18 transactional outbox and
audit. M18 ledger/projectors retain chronology; M21 timeline consumes its
minimized, allowlisted source function. M22 independently projects domain
attendance/grade/roster and M21 intervention facts with versioned policy.
M27 ingests authorized M22/M21/M18 source references through its existing
projection service. The conceptual learning chain is not a mandatory serial
ETL pipeline through M21: M22 currently reads operational tables too.

M28 does not write `accountability_cases`, intelligence snapshots or timeline
entries from a student/attendance command. Use existing authorized ingestion
and projector boundaries, with bounded refresh and checkpoints. Queries emit
no business events. Do not create a dashboard-refresh event or synthetic risk
fact to make a demonstration look complete.

## Existing names versus declarations

`m1_events.py`, `m2_events.py`, `m3_events.py` contain historical name constants;
presence in those sets is not proof of event emission. Actual M21-enabled
enrollment/attendance/grade services emit the `student.*` names below. Preserve
these v1 payloads and the M18 envelope. No wholesale namespace rename.

| Event / version | Starting state | M28 producer and effect |
| --- | --- | --- |
| `student.enrollment.created` v1 | emitted by canonical enrollment service; M21 recognized | reuse for operator and M24 intake; one per successful new enrollment |
| `student.enrollment.status_changed` v1 | emitted by router; M21 recognized | lifecycle service owns emission atomically; payload retains previous/status and dates |
| `student.attendance.recorded` / `.updated` v1 | M3 online service emits; M21 recognized | shared attendance command; first fact versus genuine amendment; include student_profile_id and existing scope refs |
| `teacher.attendance.synced` v1 | M20 emits, M21 does not currently recognize it | retain as sync receipt fact; additionally emit the appropriate canonical student attendance event for an actual changed domain fact |
| `student.grade.recorded` / `.updated` v1 | M3 emits; M21 recognized | shared bounded result command, with existing score/status/scope fields |
| `student.profile.created` v1 | historical M1 declared name, not emitted by current student service | emit when M28 create is implemented; opaque identity only; M18, no automatic M21 consumption |
| `student.profile.updated` v1 | proposed additive event | code/status change metadata; field names and reason, no names/contact values |
| `student.guardian.linked` v1 | historical declared name, not current router emission | authorized relationship creation, opaque link/student/guardian refs; restricted source read, no guardian PII in generic timeline |
| `academic_period.created`, `academic.section.created`, `course.offering.created`, `teaching.assignment.created`, `student.section.assigned` v1 | declared M1/M2 names | emit only when corresponding M28 touched command commits; M18 auditability |
| `academic_period.status_changed` v1 | proposed additive event | explicit activation/closure, actor/previous/new state |
| `teaching.assignment.updated` v1 | proposed additive event | assignment end/date change, before/after dates and actor; not an authority grant |
| `student.section.transferred` v1 | proposed additive event | old/new placement refs, enrollment/section refs, effective transfer date; one atomic transfer fact |
| `class.session.status_changed`, `assessment.status_changed` v1 | proposed additive events | explicit bounded lifecycle transition; target ref, previous/new status, actor, command identity; no new M21 event category |

A transfer emits the transfer fact, not two misleading independent business
commands; new placement creation internal to transfer is correlated to it.
Withdrawal includes prior placement reference in restricted audit without
inventing a second withdrawal event. Legacy event consumers continue to receive
their exact required fields. Do not persist a new event without a frozen typed
payload, its owning service and a retry/rollback test.

## Envelope, time and provenance

Reuse `enqueue_canonical_event` in `modules/events/service.py`. It wraps data
with `_education_os_event`: version, actor_user_id, correlation_id, causation_id,
metadata. Tenant comes from the principal. Server/outbox/ledger timestamps
remain canonical recording times. `session_date`, enrolled_on, withdrawn_on
and command effective date are separate business dates. Offline receipt time
is not proof of when a teacher observed the student; do not backdate ledger
timestamps or claim precise detection latency from a client clock.

New payload allowlist: opaque target/student/period/section/placement refs as
applicable, bounded prior/new state or score/code, effective date, reason code,
command identity, source reference and schema version. Carry policy version
when a rule actually used one. Restricted audit holds permission context and
bounded before/after state; mutable field values with PII stay outside generic
ledger. No raw import rows, names, email, guardian contact, notes, feedback,
tokens, providers or hidden reasoning. Existing score fields are educational
records; their existing M21/M18 restricted read boundaries remain in force.

## Atomicity, replay and corrections

One successful mutation transaction contains domain fact, audit, outbox and
receipt. Same request/payload replays without another domain event, including
M20 sync retries and M24 applied-row retries. The M20 sync event and canonical
attendance event describe distinct facts; the timeline must project the
attendance fact once, not both. Use shared operation correlation, distinct
event identity and existing ledger deduplication.

An amendment retains before/after bounded academic value and reason in
append-only audit. Do not overwrite the earlier event or silently rewrite
earlier metrics. New aggregate computation records versions/freshness and
source evidence; stale results remain explicit until refresh. M18/M21 replay
must preserve event identity and produce no duplicates.

No new M21 event category is required for M28-1..6. New profile/placement facts
can be reconstructed in an authorized operational history without expanding
the frozen M21 safe-context function. If a later slice needs new timeline
consumption, ASTRA must approve an additive payload allowlist and forward-only
migration; never edit 0024 or expose raw ledger payloads.

## Required continuity proof (M28-7, repeated in pilot)

1. Operator or M24 creates a synthetic enrollment; capture domain and outbox IDs.
2. Assign placement and teacher; verify the permitted roster and its lineage.
3. Record attendance online, amend via M20 under its base-state protocol, then
   retry. Record and amend an assessment result online.
4. Ingest M18 and run existing M21 projection under authorized context;
   one timeline fact per committed canonical source event, no duplicates.
5. Refresh M22 for explicit period/date/policy. Verify roster and corrected
   academic/attendance evidence, freshness and permitted/suppressed aggregates.
6. For an actual seeded qualifying signal, invoke the existing M27 projection
   boundary and prove queue/detail provenance and permission isolation.
7. Replay the same source set and equivalent versions/window. Prove stable
   identities and equivalent metrics, read-only queries and zero autonomous
   M21 intervention creation. No event is fabricated to force a signal.

The chain records source domain IDs -> outbox/event IDs -> M21 projection refs,
M22 snapshot/rule/policy versions -> M27 source/case refs. No global PII export
or long-running new worker is needed for the controlled pilot.
