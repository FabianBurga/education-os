# M28 implementation plan and ASTRA/Luna handoff

## Baseline and constraints

M28-0 is documentation only, based on published M27 tag at
`8af4557ee77d04adb2cb20d5994684268aacd194`. Branch:
`m28-operational-adoption-core`; source head `0042_m27_true_recurrence`.
All slices below are NOT STARTED. Do not implement M28-1 as part of M28-0.

Read [scope](M28_SCOPE.md), [inventory](M28_CAPABILITY_INVENTORY.md),
[domain](M28_DOMAIN_BOUNDARIES.md), [security](M28_SECURITY_BOUNDARY.md) and
[events](M28_EVENT_MODEL.md) before implementation. Keep the modular monolith,
existing domain modules, React shell/components, TanStack Query/Router and
Vitest. No new design system, state framework, worker, Redis or parallel SIS.

Every migration below is a plan, not an existing revision. First required
forward revision follows 0042; choose <=32-character revision IDs. Never
reserve several empty migrations, edit 0001–0042, or apply schema during M28-0.
Physical receipt/history/version design is Luna's bounded implementation
choice subject to the frozen behavior and ASTRA security acceptance.

## M28-1 — Permission-safe student record

- Goal: an explicitly authorized operator can find/create/read/update a
  student without inheriting account/role administration or another institution's
  person directory.
- Backend: introduce catalog/gates from the security contract for M1–M3, reuse
  permission resolver; typed student mutations, bounded record/list and minimal
  guardian reference/link operation. Reuse existing canonical services; protect
  legacy endpoints too. Keep M10 teacher APIs and M24 separately authorized;
  seed no blanket academic SYSTEM_ADMIN grants.
- Frontend: one student record/list entry in the existing administration
  workspace, selected by effective permissions; reuse current components and
  error/loading patterns. No account/role creation in the student form.
- Migration: expected permission catalog; receipt/version support only if
  existing storage cannot enforce command retry/conflict. No Student copy.
- Security: custom role versus no-permission staff, bare SYSTEM_ADMIN,
  teacher bypass, org Person exposure, cross-tenant link and mass assignment.
- Tests: real HTTP create/read/patch + PostgreSQL RLS; duplicate/retry/rollback;
  M1/M8/M10/M24 directed regression; focused student UX and privacy tests.
- Dependencies: M28-0 review.
- Full backend suite: YES, once after focused gates, because this consolidates
  authorization on shared legacy entry points. Frontend build if routing changes.
- Stop: safe basic record only; no enrollment lifecycle/placement implementation.

## M28-2 — Enrollment lifecycle

- Goal: enroll/activate/withdraw/reactivate/complete/cancel with reconstructable
  history, including the already-supported M24 create-only intake.
- Backend: move status mutation into enrollment service; implement the frozen
  transitions, validation, revision, idempotency and atomic placement closure
  on withdrawal; preserve uniqueness and source events.
- Frontend: enrollment panel in the student record; bounded actions, explicit
  withdrawal/completion confirmation, dates, conflicts and history.
- Migration: likely revision/idempotency support if not supplied in M28-1;
  minimal forward constraints if data preflight demonstrates need. No new
  enrollment authority or TRANSFERRED enrollment enum.
- Security: lifecycle permissions, student/period/campus IDOR, no auto-activation
  by profile status, no cross-institution transfer command.
- Tests: transition table, date boundaries, all retries and stale commands,
  same-period duplicate, old-period preservation, withdrawal atomicity,
  M1/M2/M18/M21 enrollment projection/M24 regressions, focused panel tests.
- Dependencies: M28-1; uses existing periods/placements, not future new entities.
- Full backend suite: NO.
- Stop: no automated progression, admissions, cross-tenant transfer or import sync.

## M28-3 — Academic setup to course offering

- Goal: configure one operational period/level/grade/section/subject/offering
  through the existing model with valid relationships.
- Backend: bounded config lists/commands, period lifecycle, subperiod/date
  consistency and safe immutable identifiers. Reuse M1 period/M2 academic services.
- Frontend: extend existing administration academic setup with a small guided
  sequence; keep existing legacy console reachable and governed.
- Migration: NONE expected; use forward revision only for demonstrated
  invariant/command-history need. No SchoolYear/calendar schema.
- Security: academic read/manage, campus/period references, closed-period writes.
- Tests: tenant/period mismatches, dates, duplicate configuration, close with
  active enrollment rejection; M1/M2/M3 config/M8 regressions and setup UX.
- Dependencies: M28-1 and lifecycle semantics in M28-2.
- Full backend suite: NO.
- Stop: no scheduling optimization, report cards or curriculum authoring engine.

## M28-4 — Placement and teacher roster continuity

- Goal: place/transfer a student and assign/end a teacher assignment with a
  correct current roster and preserved historical references.
- Backend: atomic placement transfer locking enrollment; teacher-assignment
  list/update/end; shared date/eligibility helpers scoped to existing M2/M10
  domains. Preserve unique ACTIVE placement and unique course/staff pair.
- Frontend: placement/assignment panels; teacher sees refreshed assigned roster.
- Migration: NONE expected; conditional narrow history/concurrency support,
  not a roster table. Do not loosen historical unique constraints.
- Security: academics.assign distinct from role granting; cross-course teacher
  and foreign section denied; transfer cannot change historical grades/attendance.
- Tests: two competing transfers, exact dates, withdrawn student, ended teacher,
  other course in same section, roster changes and history; M2/M10/M20/M21 scope
  and M22 roster regressions plus focused UI/refetch.
- Dependencies: M28-2, M28-3.
- Full backend suite: NO, unless an actual shared security-boundary redesign
  beyond this plan is approved; such a change gets its own integration gate.
- Stop: no multi-tenure assignment redesign or cross-campus/institution transfer.

## M28-5 — Attendance correction and offline evidence

- Goal: teacher records and corrects one session safely online/offline, with
  one logical canonical fact per successful change.
- Backend: shared attendance transaction/target locking, history/reason/revision,
  consistent roster/date checks, canonical student event alongside existing M20
  sync event. Keep ATTENDANCE_MARK protocol, receipts and batch result vocabulary.
- Frontend: use existing teacher PWA; show pending/replayed/conflict/rejected
  state and require explicit conflict resolution; no optimistic confirmed fact.
- Migration: conditional receipt/revision support for online writers; M20 table
  and frozen protocol remain usable. No second offline engine.
- Security: reauthorize on replay and apply; revoke teacher while offline,
  expired snapshot, tenant/user cache isolation, historical correction permission.
- Tests: online-vs-offline race, double submit, first mark/correction/no-op,
  transaction failure, revoked scope; M3/M10/M18/M20/M21 attendance regression,
  existing `teacher-pwa.test.ts` plus focused conflict flows.
- Dependencies: M28-4.
- Full backend suite: NO here; required at M28-7 after continuity consolidation.
- Stop: attendance only; no offline grade entry or new sync queue technology.

## M28-6 — Assessment result correction

- Goal: assigned teacher creates a bounded assessment, records and corrects
  results without losing prior evidence or fabricating zero grades.
- Backend: existing assessment/category/period/entry services; finite score
  and status rules, immutable used denominator, explicit correction history,
  expected revision and single transaction including audit/event.
- Frontend: extend existing teacher workspace with minimal assessment/result
  panel, reuse M10 APIs and source permissions; display missing/excused explicitly.
- Migration: conditional result revision/receipt support; no final transcript store.
- Security: assignment/roster, grade/manage versus historical correction,
  private feedback, period/offering/category mismatch.
- Tests: score/status/precision boundaries, duplicate/retry/concurrent correction,
  missing != zero, failed audit rollback; M3/M10/M11/M12/M18/M21/M22 affected
  result regressions and focused frontend entry/error tests.
- Dependencies: M28-3, M28-4; reuse command mechanics accepted in M28-5.
- Full backend suite: NO.
- Stop: no GPA/final-grade algorithm, promotion decision, national scale or LMS.

## M28-7 — Operational history and evidence continuity

- Goal: operator/rector/coordinator can follow an accepted record to M18,
  M21/M22 and existing M27 with correct provenance, permissions and freshness.
- Backend: bounded composed history/readiness queries and existing projection
  orchestration; include M24 source-run references. No direct writes to M27,
  no new authoritative history/analytics store and no dashboard side-effect.
- Frontend: reuse record workspace and Student360 links, institutional context,
  actionable next steps and stale/suppressed states; no per-card fetch waterfall.
- Migration: NONE expected. If new M21 payload consumption is required, stop
  for ASTRA additive contract review; the default uses existing event allowlists.
- Security: destination reauthorization, counts match row scope, suppressed
  values never recomputed, no broad ledger payload endpoint.
- Tests: real event -> ledger -> timeline, domain -> M22 -> M27 source continuity,
  replay/no duplication, correction/freshness, read-only and no causal claims;
  directed M18/M19/M20/M21/M22/M24/M27. M25/M26 only if those boundaries touched.
- Dependencies: M28-2..6.
- Full backend suite: YES once after directed PASS; full frontend tests,
  typecheck and production build. This is the major integration boundary.
- Stop: no new signals/metrics/case rules, providers or autonomous intervention.

## M28-8 — Controlled operational pilot and closeout

- Goal: prove daily synthetic operation and prepare a controlled human run.
- Backend/frontend: existing harnesses plus deterministic, synthetic fixtures
  and strongest existing UI integration harness; repair only pilot blockers.
- Migration: NONE expected; any genuine schema defect needs forward migration
  and affected tests before returning to pilot. Never edit a historical revision.
- Security: two institutions; operator, rector/coordinator, teachers A/B,
  bare SYSTEM_ADMIN and guardian negative controls. Application-role sessions,
  no real PII/providers; replay, concurrency and cleanup/reprovision safety.
- Tests: one complete lifecycle, one withdrawal/reactivation/transfer history,
  online/offline conflict, result correction, M24 import equivalence, cross-tenant
  denial, current/suppressed evidence, and manual instrument preparation.
- Dependencies: all previous slices accepted by ASTRA.
- Full backend suite: YES once at final accepted product state; full frontend
  tests/typecheck/build, changed-file Ruff, compile, Alembic and diff-check.
  A later docs-only closeout reuses this evidence. Real post-gate code changes
  invalidate the relevant evidence and require justified revalidation.
- Artifact: commit/schema/dataset/clock, actors, scenarios, observed facts,
  metric denominators, lineage, test summaries, cleanup and three gate decisions.
- Stop: local closeout only; push/tag/release and later milestones need new
  authorization. No claim of field validation or production certification.

## Validation economy and reproducibility

Per ordinary slice: focused behavior/HTTP tests; affected-domain regression;
changed Python Ruff + py_compile; frontend focused tests/typecheck if touched;
production build for new routes or build configuration; Alembic heads/current
and application-role RLS/constraints if DB touched; diff-check; local commit.
Check installed scripts: frontend has `test`, `typecheck`, `build` (no lint
script). Do not invent a frontend lint gate. Use existing pytest layout and
declared dependencies, no heavy new test framework.

Full backend points are exactly M28-1 (security), M28-7 (integration), M28-8
(final pilot), once per accepted code state after focused/directed gates.
Failures: diagnose -> minimal compatible fix -> focused retest -> affected
regression. Do not repeatedly run full suite during repairs. Record passed,
failed, skipped and exit code persistently; identify the M21 opt-in skip.

M28-0 uses source inspection, revision-chain verification, link/JSON/document
consistency and git diff checks only. It does not repeat the published M27
743/1 backend or 61 frontend gate or claim those as new M28 validation.
Before dynamic work, recover the declared interpreter safely if necessary;
the previous Python314 venv launcher was inaccessible in the sandbox. Verify
actual environment rather than altering dependencies/product to hide that.

## ASTRA / Luna contract

ASTRA: architecture, authority and event freeze, security/threat review, hard
contract problems, slice acceptance and final readiness classification.
Luna: implementation in existing modules, minimal forward migrations,
frontend/backend, fixtures/tests, debugging, targeted repair, and local commits.

Each handoff identifies accepted parent SHA, this contract version, one slice,
allowed files/domains, migration decision, focused/regression commands and stop
boundary. Luna records what changed and the evidence, including limitations;
ASTRA checks the behavior against this freeze before the next slice begins.

Luna resolves routine imports/types/lint/harness/local PostgreSQL/fixtures and
compatible bugs autonomously. Escalate only a changed frozen contract, security
relaxation, irreversible or production operation, external credentials/cost,
genuine product choice, or push/tag/release. Unknown institution settings remain
unconfigured/fail-closed and do not justify invented business defaults.
