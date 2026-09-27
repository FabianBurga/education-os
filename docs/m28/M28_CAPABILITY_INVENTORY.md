# M28 repository capability inventory

Inspected source: published M27 commit `8af4557ee77d04adb2cb20d5994684268aacd194`.
This is source inspection, not a new dynamic gate. API paths below omit
`/api/v1`. Tables are existing authorities unless explicitly identified as
derived. All paths are repository-relative; see source anchors below.

## Matrix

| Capability / current state | Authority / tables | API | Frontend | Security / existing tests | Gap / M28 action |
| --- | --- | --- | --- | --- | --- |
| Person identity: implemented, organization-scoped | M0 identity: `persons`, `user_accounts` | M8 `/admin/people`, `/admin/accounts` | M8 HTML admin, React shell link | Org RLS for persons; self/admin account policies; M8 tests | Never clone a person per school year; minimize organization-wide lookup; bounded identity input in M28-1 |
| Student identity: implemented | M1 students: `student_profiles`, unique institution/person | `/students`, `/{id}`, PATCH | M8 create/list form; M21 Student360 reads | FORCE RLS + tenant composite links; M1 contract/metadata tests | No granular CRUD permission, unbounded list, update service accepts arbitrary dict internally; M28-1 allowlist, permission, bounded read and audit |
| Student institutional affiliation: implemented, distinct from login | M1 `student_profiles`; M0 `memberships` are user access only | student APIs versus admin memberships/roles | M8 | Signed principal, active membership; M8 access tests | Do not require student user account or turn enrollment into an auth membership |
| Enrollment: create/read/status PATCH | M1 enrollment: `enrollments`, unique student/period | `/enrollments`, `/{id}/status` | M8 create/list, no complete lifecycle UX | Tenant RLS/composite FKs; M1 + M24 tests | PATCH assigns any allowed status, no transition/expected revision; M28-2 bounded lifecycle/history |
| Academic period / school year: implemented | M1 enrollment: `academic_periods`, PLANNED/ACTIVE/CLOSED | GET/POST `/academic-periods` | M8 period form | M1 dates/schema/RLS tests | No separate school-year authority needed; M28-3 safe lifecycle/containment |
| Grade/year level: implemented | M2 academics: `academic_levels`, `grade_levels` | `/academics/levels`, `/academics/grades` | M8 forms | M2 composite links/FORCE RLS, route/schema tests | Configured labels/order, not hardcoded country levels; reuse in M28-3 |
| Section/class: implemented | M2 `sections` binds period/campus/grade | `/academics/sections` | M8 create/list | M2 unique period/campus/grade/code; capacity validation | Period/campus consistency; bounded maintenance M28-3 |
| Subject/course: implemented | M2 `subjects`, `course_offerings`, `curriculum_plans`, `curriculum_subjects` | `/academics/subjects`, `/course-offerings`, `/curriculum-plans` | M8 partial configuration; M10 class read | M2 tenant FKs; subject isolation test | Preserve course = section + subject, no duplicate Course table; M28-3 minimal offering setup |
| Staff/teacher identity: implemented | M1 families defines `staff_profiles`, M0 person/account | `/admin/staff` | M8 | Active staff + effective permissions in consoles | Staff is not automatically a teacher; M28 reuses identity and teaching assignment |
| Teacher assignment: create API, date window | M2 `teaching_assignments`, unique course/staff | POST `/academics/teaching-assignments`; M10 `/teacher/classes` | Teacher view, incomplete operator maintenance | M10 course/staff/date checks; source-contract tests | Missing bounded assignment list/change/end journey; M28-4, preserve unique pair |
| Roster / placement: implemented | M2 `student_section_assignments`; M1 active enrollment; roster is derived | `/academics/student-section-assignments`; `/teacher/classes/{id}/roster` | M10 HTML + M20 PWA | Unique ACTIVE placement/enrollment, M10 scope tests | No transfer command; active/date checks differ across entry paths; M28-4 atomic transfer/history |
| Attendance: implemented | M3 `attendance_codes`, `class_sessions`, `attendance_records` | `/attendance/*`; scoped `/teacher/*` | M10 HTML + M20 PWA | M3 RLS/code isolation; M10/M20 contract tests | Online upsert overwrites fields; nested commit before teacher audit; M28-5 atomic correction and consistent roster/date checks |
| Assessment: implemented | M3 grades: `grading_periods`, `assessment_categories`, `assessments` | `/grades/periods`, `/categories`, `/assessments`; teacher variants | M10 HTML; React teacher workspace primarily PWA | M3 date/score contracts, M10 scope checks | Minimum assessment workflow exists; M28-6 coherent definition/result UI, closed-period checks |
| Grade/result: implemented, final transcript absent | M3 `grade_entries`, `grading_scales`, `grading_scale_bands` | `/grades/assessments/{id}/entries` | M10, student/guardian permitted views | unique assessment/placement; M3 schemas + M10–M12 tests | GRADED requires score, max checked; no audited conflict-safe correction history contract; M28-6; final grades deferred |
| Guardian relationship: implemented | M1 `guardian_profiles`, `student_guardian_relationships`, `family_households`, `family_members` | `/guardians`, `/student-guardian-links`, `/families` | M8 + M6/M12 family surfaces | Tenant FK/RLS; separate `guardian_student_portal_access`; M6/M12 privacy tests | Separate administrative linking from portal grant; M28-1 only minimal linking/authorized read |
| Student status: implemented enum | M1 student ACTIVE/INACTIVE/ARCHIVED | PATCH `/students/{id}` | Partial M8 | RLS; schema validation | Not enrollment status; safe status/history guard M28-1; no cascading history deletion |
| Transfer/withdrawal: partially represented | enrollment WITHDRAWN; placement TRANSFERRED/WITHDRAWN | enrollment status PATCH; no placement transfer API | No complete operator journey | Existing unique placement index | M28-2 withdrawal; M28-4 transfer. TRANSFERRED is NOT an enrollment state |
| Basic record / academic history: fragmented | M1/M2/M3 authorities; M21 `student_timeline_entries` is derived | Student360/timeline + existing domain reads | Student360 exists | M21 subject scope/visibility tiers and projection tests | M28-7 bounded links/history; no parallel transcript/PII store |
| Institution/calendar: foundational support | M0 institutions/campuses; M2 `schedule_slots`; M3 sessions | M8 institution/campus; `/academics/schedule-slots` | M8 + teacher/student schedules | M0 tenant context; M2 slot time/weekday checks | Reuse dates/weekly slots; holiday engine and optimization deferred |
| Imports / overlay: implemented create-only CSV | M24 integration modules; `integration_external_student_refs` | `/integrations` validate/apply/run read | React IntegrationWorkspace | integrations permissions, bounded CSV, tenant idempotency; M24 tests | Canonical student/enrollment services already used; retain create-only semantics; M28-1/2 compatibility and M28-7 lineage proof |
| Offline: attendance only | M20 `teacher_offline_receipts`; M3 records remain authoritative | `/teacher/offline/snapshot`, `/teacher/offline/sync` | IndexedDB partition, PWA, service worker | Batch/conflict/expiry/auth tests and frontend tests | Reuse receipt/base-state protocol; canonical timeline event continuity M28-5; offline grades deferred |

The offline router prefix `/teacher/offline` is defined in
`teacher_offline/router.py` and mounted by `api/v1/m20_router.py`.
No generic sync engine is proposed.

## Source anchors and coverage interpretation

- `backend/app/modules/{identity,students,enrollment,families,academics,attendance,grades}/models.py`
  and their routers/services/schemas establish the tables, enums and commands.
- `backend/app/api/v1/m1_router.py`, `m2_router.py`, `m3_router.py` mount
  `require_staff_access` plus `require_privileged_staff_access` from
  `backend/app/api/access.py`. That guard checks TEACHER specially and permits
  other active staff without an operation-specific permission. This is a
  source-confirmed gap; no new exploit execution was performed in M28-0.
- `backend/app/modules/teacher_console/service.py`: `_offering_scope`,
  `_session_scope`, `_assessment_scope`, `list_roster`, `mark_attendance`,
  `mark_grade`. Teaching dates use current date. Generic and teacher mutation
  checks are not identical to offline `_assert_target`.
- `backend/app/modules/teacher_offline/{schemas,service,router}.py`,
  `frontend/src/{teacher-offline-core,teacher-pwa.test}.ts`,
  `frontend/src/lib/teacher-offline-store.ts`: ATTENDANCE_MARK only, batches
  bounded to 100, receipt/hash replay, base-state conflicts and tenant/user
  cache partition. Online/offline competing writes need a shared lock protocol.
- `backend/app/modules/student_timeline/projector.py` and migration 0024:
  allowlisted `student.enrollment.*`, `student.attendance.*`, `student.grade.*`.
  M20 emits `teacher.attendance.synced`, not currently in that allowlist.
- `backend/app/modules/intelligence/projector.py`: M22 derives roster and
  attendance/grade facts from domain tables, not solely the M21 timeline.
- `backend/app/modules/integrations/{service,csv_student_enrollment}.py`:
  create-only CSV invokes `create_person`, `create_student_profile`,
  `create_enrollment_record`; imported run details include names. Do not claim
  the import staging area has no PII; minimize user-facing/audit exposure.
- `frontend/src/router.tsx`, `frontend/src/navigation.ts`,
  `frontend/src/pages/workspace-page.tsx`: existing React shell, TanStack
  Query/Router, admin legacy link, teacher PWA, native M21/M24/M26/M27 screens.
- `backend/app/modules/admin_console/admin_dashboard.html`: existing student,
  guardian, period, grade, section and enrollment forms; its initial load
  fetches many unbounded lists. This is partial working UX, not an absent UI.
- `backend/tests/unit/test_m{1,2,3}_contracts.py`: primarily routes, schemas,
  event-name constants. `tests/integration/test_m{1,2,3}_rls_metadata.py` checks
  RLS and DML grants. M2 subject/M3 code tenant isolation adds behavior tests.
  M8/M10/M20 tests include many source assertions. New acceptance needs actual
  HTTP + database behavior, not only extending those assertions.

## Historical migration ownership review (0001–0042)

| Revisions | Existing ownership / extension decision |
| --- | --- |
| 0001 | M0 tenancy, persons/accounts/memberships/roles, outbox, audit. Persons org scope; do not reinterpret as institution-exclusive identity |
| 0002 | M1 profiles/families/periods/enrollment, FORCE RLS, tenant policies. Runtime DML includes DELETE; do not describe old tables as append-only |
| 0003 | M2 ten academic tables, tenant-safe M1 composite FKs, unique active placement. Extend domain services, never clone tables |
| 0004 | M3 attendance and assessment/results; FORCE RLS, tenant/section references; existing authority |
| 0005–0006 | Legacy intelligence signals and automation rules/cases/tasks/timeline; no new M28 competing risk/task engine |
| 0007 | Family portal access/notices/receipts; relationship does not grant portal visibility |
| 0008–0009 | Readiness runs and runtime Alembic visibility grant; preserve |
| 0010–0014 | Admin, coordination, teacher, student, guardian permissions/read boundaries. 0012 seeds teacher permissions also to SYSTEM_ADMIN; a role label alone is not proof of academic authority |
| 0015–0016 | Communications and billing authorities; out of M28 scope |
| 0017 | M18 event ledger, checkpoints, daily/aggregate projections; no second ledger |
| 0018 | M19 versioned control/policy/change records and permission evaluator; reuse governance |
| 0019 | M20 actor-bound offline receipts; reuse, not a general M28 receipt for other commands |
| 0020–0024 | M21 timeline/interventions/actions/follow-ups/suggestions; 0024 minimized projection source function. Frozen authority and history |
| 0025–0026 | M22 student/cohort/institution intelligence; read/role/scope boundary. Do not recalculate priorities in M28 |
| 0027–0030 | Governed copilot/advisory/contract hardening/action proposal ledgers; no new autonomous actions |
| 0031–0032 | M24 connectors/mappings/runs/items/events/external student refs; immutable import identity and create-only application |
| 0033–0036 | M25 agent control plane, advisor seeds/provider/budget/explainer; preserve closed gateway |
| 0037 | M26 briefing configuration; explanation only |
| 0038–0041 | M27 case/source/review/decision/ownership/obligation and internal policy evaluation; no direct operational writes |
| 0042 | Forward recurrence CHECK extension TRUE_RECURRENCE; sole source head, no operational schema addition |

All 42 revision/down_revision declarations form the existing linear chain.
M28-0 leaves every migration byte unchanged. Source head verification does not
claim a fresh database-current/RLS execution; those checks are required before
Luna applies a forward migration. A future schema change must follow 0042,
retain composite tenant references and FORCE RLS, and preflight existing data.
