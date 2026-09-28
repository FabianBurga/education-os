# M28 closeout

## Status

| Gate | Result |
| --- | --- |
| TECHNICAL_GATE | PASS |
| OPERATIONAL_GATE | PASS |
| SYNTHETIC_PILOT | PASS |
| READY_FOR_CONTROLLED_HUMAN_PILOT | YES |
| FIELD_VALIDATED | NO |
| PRODUCTION_CERTIFIED | NO |

This closeout is based on local synthetic integration evidence. It makes no
claim of real teacher adoption, field validation, measured time savings,
learning outcomes, or production certification. No push, tag, merge, or release
was performed. Release publication remains a separate reviewed decision.

## Delivered

M28 hardened the existing M1/M2/M3 operational authorities for student
records, enrollment, academic setup, placement/roster, attendance and
assessment/results. M20 remains the offline attendance capture/sync authority;
M18 remains the canonical event ledger; M21 remains the student timeline and
intervention authority; M22 remains the deterministic intelligence authority;
M27 remains the human accountability and decision authority. No parallel
student, enrollment, placement, attendance, assessment, or result authority
was added. M28 did not add final-grade calculation, promotion, retention,
graduation or autonomous high-impact action.

The M28-8 pilot exposed a missing operational transition for M3 grading
periods: creation produced `PLANNED`, while assessment creation required
`ACTIVE`. A tenant-scoped `PATCH /api/v1/grades/periods/{id}/status` now applies
expected-state `PLANNED → ACTIVE → CLOSED` transitions. Activation requires an
active parent academic period. The operation requires institutional
`academics.manage`, locks and checks the expected state, and writes audit plus
`grading_period.status_changed` to the transactional outbox. Teacher actors
cannot use this institution-wide route. No migration or RLS change was needed.

## Synthetic evidence

The rollback-contained local journey created one organization/institution,
one campus, one active academic period, two grade/section contexts, two
subjects, four offerings, two teachers, and ten synthetic students. It covered
student create/update and stale update, pending-to-active enrollment, current
and historical placements with transfer, assignment-scoped roster reads,
explicit-maximum published assessments, numeric zero, a distinct `MISSING`
result with null score, decimal result correction, stale correction conflict,
assessment/grading-period closure,
online attendance correction, offline sync/replay/conflict, M18 ingestion,
M21 projection/replay, the supported M22 attendance-risk signal, and the
existing human-reviewed M27 accountability path. Fixture rows were rolled back
and bootstrap roots removed by exact synthetic IDs; post-run database checks
found zero M28-8 synthetic organization or institution rows.

The existing M24 enrollment import continuity test passed separately. It
preserved M1 enrollment authority and the external student reference/import
run provenance.

M18 ledger rows preserved tenant/institution keys and source event family for
enrollment, grading-period status, attendance and result facts. M21 received
attendance and grade evidence through the existing projector and inserted no
duplicates on replay. M22 used its existing attendance rule. M27 used the
resulting signal and its canonical M18 event to project a case; the human
reviewer recorded a `MONITOR` decision and a follow-up obligation. The signal
did not automatically create an intervention or change enrollment, placement,
or result state.

## Security posture

The live pilot exercised an unauthorized principal, teacher A/B assignment
boundaries, an institutional manager and coordinator, and a bare SYSTEM_ADMIN
with no academic grants. Wrong-tenant reads, foreign student references,
wrong-teacher roster access, teacher institution-wide academic setup, generic
teacher grading-period administration, and SYSTEM_ADMIN academic access failed
closed. Projection ran on the application connection with tenant context and
the established projector permissions. Existing M28 integration regressions
cover FORCE RLS, cross-tenant references, IDOR, mass assignment, correction
history, and transactional audit/outbox behavior. No RLS policy was weakened.

The synthetic pilot did not produce discipline, enrollment termination,
promotion, retention, grade override, sanction, or an autonomous high-impact
intervention. M27 remains the human-governed accountability path.

## Validation

- Focused M28-8 pilot, M28-6 assessment/results, and M24 import continuity:
  3 passed.
- M21 online/offline attendance continuity tests, explicitly configured to
  use the local application database: 2 passed, 0 skipped.
- Full backend: 769 passed, 0 failed, 2 expected skips. Both skips are the
  opt-in M21 E2E tests; those exact tests separately passed as noted above.
- Full frontend: 76 passed across 13 files.
- Frontend typecheck: passed.
- Production build: passed. Existing dynamic-import and chunk-size warnings
  remain non-blocking.
- Ruff on changed Python files: passed.
- `py_compile` on changed Python files: passed.
- Alembic heads/current: `0046_m28_attendance_perms`; no M28-8 migration.
- Migration chain files 0043, 0044, 0045 and 0046 are present and unmodified.
- `git diff --check`: passed.

## Limitations and readiness

Evidence is synthetic and local. M21's current allowlist projects attendance
and grade facts; it does not project the M22 signal-opened fact. M27 consumes
that M22 signal through its canonical M18 source event. M24 import was proven
by its existing separate rollback-controlled test rather than inside the
ten-student journey. There is no cross-domain freshness watermark; event and
projection processing remain asynchronous according to their existing
contracts.

Existing frontend role-aware paths passed the complete frontend suite,
typecheck and production build. No new dashboard or UI was introduced. The
pilot is appropriate for a controlled human pilot with synthetic or properly
authorized institutional data and explicit human oversight. Field validation
and production certification remain outstanding.

Deferred scope includes all M29+ roadmap work, automatic final grades, GPA,
promotion, retention, graduation, report cards, new M22 signals, autonomous
decisions, new connectors, production deployment and release publication.
