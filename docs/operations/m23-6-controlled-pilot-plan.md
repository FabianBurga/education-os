# M23-6 Controlled Pilot + Release Plan

## Authoritative entry baseline

- M23-5 closure source: `d963a55520bf5914d42bb07afe2b3b715874f583`
- Database revision: `0030_m23_action_proposals`
- M23-5 Runtime Formal Gate: PASS
- Closure report: `C:\Users\USER\Downloads\M23_5_RUNTIME_FORMAL_GATE_REPORT_V1.json`
- Closure report SHA256: `9533e6a990418f113a44bc26c5aa65e14e3b4fdb0563851d25d4a8ac8431a4ad`

## Repository-grounded pilot baseline

The existing persistent synthetic institution contains exactly the required actor
set: one SYSTEM_ADMIN, one RECTOR, one ACADEMIC_COORDINATOR, and two distinct
TEACHER users. It also contains eight synthetic students, separate active course
offerings for both teachers, and the enabled `teacher.offline_pwa` capability.
The destructive legacy `scripts_seed_demo.py` is explicitly excluded.

The pilot uses existing public APIs and authoritative services only:

- M20: `/api/v1/teacher/offline/snapshot`
- M21: `/api/v1/student-timeline/students/{student_profile_id}` and intervention APIs
- M22: `/api/v1/intelligence/*`
- M23: governed query/run and action-proposal list/approve/reject APIs

## Controlled execution design

1. Read and validate the persistent synthetic actor/student/assignment baseline.
2. Bind FastAPI TestClient to the runtime PostgreSQL role through one outer
   transaction and `create_savepoint` session mode.
3. block network access and inject a deterministic fake provider gateway;
4. exercise both teachers' M20 snapshots and prove non-teacher denial;
5. exercise M21 timeline visibility for all required roles and teacher scope denial;
6. exercise M22 management views and teacher management denial;
7. execute governed M23 advisory queries for every required actor and read back
   evidence provenance through the public run API;
8. create proposals only through the internal governed proposal service, then
   prove teacher decision denial, rejection, approval, authoritative intervention
   execution, duplicate-decision denial, and cross-role proposal isolation;
9. verify the canonical `student.intervention.opened` event carries
   `human_authorized=true`;
10. roll back the outer transaction and compare tracked before/after counts.

## Release validation sequence

1. `py_compile` for touched Python;
2. targeted Ruff without fixes;
3. M23-6 controlled-pilot contract tests;
4. directed M20-M23 security regression;
5. controlled runtime pilot;
6. full backend pytest;
7. clean-tree and unchanged-revision verification;
8. stop at the formal release gate for human authorization before commit,
   push, tag, or publication.

No migration, new role, new permission, provider-selected tool, raw database-to-LLM
path, or new product API is introduced by this plan.
