# M28-5 — Attendance Operational Continuity

## Authority and meaning

M3 remains the sole attendance authority: `attendance_codes`, `class_sessions`,
and one `attendance_records` row for each `(class_session_id,
student_section_assignment_id)`. M10 is the online teacher entry path. M20
captures attendance offline and synchronizes through the same M3 mutation
service. Neither entry path owns a separate attendance truth.

Attendance can be entered only for an open session in an active academic period
and a roster placement valid on the session date. New records require an active
enrollment, active student profile, active placement, active section, and
matching campus. Historical corrections require the current attendance
correction permission and an explicit expected state and bounded reason.

Existing values are not silently overwritten. Writers lock the session/student
target and compare the submitted expected state with the authoritative row.
Stale online corrections return conflict; stale offline operations return
`CONFLICT` with the current server state. A correction is auditable with the
prior and current attendance code/minutes, actor, reason, source, and timestamp;
the canonical update event describes only minimized attendance fields. Free
text notes are excluded from event payloads and metadata.

## Authorization and roster

The M28-5 migration adds `attendance.read`, `attendance.manage`, and
`attendance.correct` permission definitions. It does not grant these
permissions to any role. Access checks use the authenticated principal's user,
organization, and institution and active memberships/role grants. SYSTEM_ADMIN
receives no implicit academic authority. Teacher entry and offline sync also
require the existing teacher attendance dependency and a current teaching
assignment covering both today and the class-session date. The target student
must be in the session's institution, section, academic period, campus, and
date-valid placement. Cross-tenant references fail closed.

The generic M3 router remains behind the existing `require_staff_access` and
`require_privileged_staff_access` boundary. Teacher-only actors use the scoped
M10/M20 paths; the new institutional attendance permissions do not bypass that
boundary and migration 0046 grants none of them to TEACHER.

## Offline capture and convergence

M20's tenant/user-partitioned local queue, bounded batches, operation IDs,
receipts, and result vocabulary remain in use. The server rechecks capability,
teacher assignment, session, roster, and active attendance code on every sync,
including receipt replay. Snapshot authorization alone is not sufficient.

Online and offline mutations call the M3 attendance mutation service. M20 adds
only its sync receipt, sync audit entry, and sync-activity event after that
canonical mutation succeeds. A replay with the same operation ID and payload
returns `REPLAYED`; a changed payload returns `IDEMPOTENCY_MISMATCH`. Distinct
operations for the same target are serialized. A stale base returns `CONFLICT`
and does not mutate attendance, audit, or events. Revoked assignment scope
returns `REJECTED`, including on replay.

The teacher PWA distinguishes pending, synchronized, conflict, and rejected
work. A conflict requires explicit teacher resolution against current server
state. A rejected operation cannot be resubmitted until discarded and access is
restored. The PWA does not present a rejected or conflicted local value as a
confirmed server fact.

## Audit, events, and privacy

The M3 attendance change, audit row, and canonical outbox event share the same
transaction. Failure to enqueue the canonical event rolls back the attendance
change. First marks emit `student.attendance.recorded`; corrections emit
`student.attendance.updated`. M20's `teacher.attendance.synced` is operational
activity only and is not an M21 timeline source. M18 ingests the canonical M3
events, and M21 already projects those event types into the ATTENDANCE category.
M28-5 does not write M21 storage directly.

Event payloads omit attendance notes and carry only the identifiers and bounded
attendance fields needed by downstream projections. The existing M21 projector
filters payload fields and excludes notes from timeline context. Audit metadata
records the actor, source, correction reason, previous/current code and minutes,
and whether the note changed; it does not copy free-text note contents.

## Validation boundary and limitations

The controlled M28 integration fixture exercises online creation and
correction, stale online state, offline conflict, apply, replay, idempotency
mismatch, scope revocation, event counts, rollback behavior, and audit/outbox
atomicity. Unit contracts cover M21's canonical attendance event mapping and
note minimization. The separate M21 database end-to-end test requires an active
teacher/session/student fixture and skipped in this local database because no
such fixture was available. The owner database role cannot run the M21 runtime
projection function, by design; the runtime role cannot insert into the
append-only M18 ledger. This slice therefore records the canonical M3 event and
the existing M21 consumer contract, but did not claim a local end-to-end
projection run.

There is no explicit attendance revision column: concurrency is guarded by a
locked target plus expected-state comparison, while correction history is
retained in audit evidence. Offline correction currently accepts the bounded
`OFFLINE_RECONCILIATION` reason as part of the frozen M20 operation contract.
