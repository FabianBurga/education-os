# Validation baseline

Last accepted product validation is the M28 release closeout in
`docs/m28/M28_CLOSEOUT.md` (release commit `c21e7c1287a8bc7abd8f355aa619e67c0beee0c4`):

- Backend: 769 passed, 0 failed, 2 opt-in M21 E2E skipped by default; both
  specified E2E tests separately passed against the configured local DB.
- Focused M28-8 pilot / M28-6 assessment-results / M24 import continuity: 3
  passed; M21 online/offline E2E: 2 passed, 0 skipped.
- Frontend: 76 passed; typecheck/build passed (existing chunk/dynamic-import
  warnings recorded in closeout).
- Changed-file Ruff and `py_compile`, Alembic head/current
  (`0046_m28_attendance_perms`), and `git diff --check`: passed.

These are inherited facts, not validation of M29 tooling or new M29 behavior.
M29-AO should run its own cheap helper checks only; it must not rerun full
product regression for documentation/tooling-only changes. Migration, RLS,
authentication, permissions, M18/M21/M27 or cross-module behavior changes
require broader directed/security validation and full regression as justified
by project engineering policy.
