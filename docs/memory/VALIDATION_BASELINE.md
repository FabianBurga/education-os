# Validation baseline

## M29-1 / SEC-TC1 local closeout

- Full backend regression: **801 passed, 0 failed, 2 skipped, 144 warnings**
  in 107.77 seconds. The skips are the opt-in M21 timeline E2E cases because
  `M21_E2E_DATABASE_URL` was not configured.
- Focused M29/M6/M7 DB and security set: **29 passed**. Includes guardian
  authorization/revocation, receipt source authenticity, direct runtime table
  access denial, role/grant boundaries, M21/M27 evidence semantics,
  idempotency, concurrent link/correction/supersession, rollback and retry.
- Focused unit/contract set: **40 passed**.
- Migration: local `0046_m28_attendance_perms` → `0047_sec_tc1_m29_ack_bridge`
  upgrade, downgrade to 0046 with empty evidence tables, and re-upgrade passed;
  `alembic current` and the single `alembic heads` result are 0047.
- Memory validation, architecture structural check, changed-file Ruff,
  `py_compile`, and `git diff --check`: passed.
- Test fixture tables were verified empty after the full suite. Append-only
  triggers were restored and checked by fixture teardown.
- No frontend code changed, so frontend regression was not applicable.

Warnings were existing dependency deprecations, unknown opt-in integration
marks, short local HS256 test keys, and Alembic `path_separator` deprecation.
No warning was treated as a test failure.

## Inherited baseline

M28 closeout evidence remains historical and authoritative for M28:
backend 769 passed; 2 opt-in M21 E2E cases separately passed at that milestone;
frontend 76 passed; typecheck/build/Ruff/`py_compile`/Alembic/diff-check passed.
See `docs/m28/M28_CLOSEOUT.md`.
