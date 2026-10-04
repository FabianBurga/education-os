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

## M29-2 Teacher Continuity Workspace local closeout

- Full backend regression: **797 passed, 13 skipped, 144 warnings**. Skips
  are the opt-in M21 E2E cases and SEC-TC1 issuer integration cases without
  local issuer URLs.
- Frontend regression: **79 passed**; typecheck and production build passed.
- Focused M29-2 contracts: **16 passed**. Focused M29 database boundary:
  11 passed and 11 issuer-dependent cases skipped without issuer URL.
- Migration `0047_sec_tc1_m29_ack_bridge` -> `0048_m29_batch_ack_reads`,
  downgrade to 0047 and re-upgrade passed. Alembic has one head at 0048.
- Local ACL/RLS evidence: `education_app` has no direct SELECT/INSERT/UPDATE/
  DELETE on the capability/evidence tables; PUBLIC has no batch EXECUTE;
  issuer EXECUTE is limited to issuance; function owner is NOLOGIN,
  NOSUPERUSER, NOINHERIT and NOBYPASSRLS; protected tables retain FORCE RLS.
- Ruff, memory validation, architecture check and `git diff --check` passed.

Warnings were existing dependency deprecations, unknown opt-in integration
marks, short local HS256 test keys, bundle-size/dynamic-import build warnings,
and missing optional issuer/E2E URLs. No warning was treated as a test failure.

## M29-2V issuer-backed remediation closeout

- Corrected the existing `0048_m29_batch_ack_reads` validator by removing its
  unused pre-lock canonical query, which collided with the PL/pgSQL capability
  record variable `c`. No authorization, digest, tenant, purpose, RLS, grant,
  or role semantics changed.
- Permanent issuer-backed SEC-TC1 integration coverage: **24 passed, 0
  skipped**, including application-service M21/M27 batch reads, canonical
  ordering, hidden-target omission, target-set mismatch, and expiry rejection.
- Full backend regression with issuer configuration: **810 passed, 2 skipped,
  144 warnings**. The only skips are optional M21 E2E cases requiring
  `M21_E2E_DATABASE_URL`; no SEC-TC1 issuer tests were skipped.
- Local migration round-trip `0047 -> 0048 -> 0047 -> 0048`, Alembic current,
  and the single-head check passed. Ruff, `py_compile`, memory validation,
  architecture check, and `git diff --check` passed.
- A3 and A4 remediation reviews: PASS; zero unresolved CRITICAL/HIGH findings.

## Inherited baseline

M28 closeout evidence remains historical and authoritative for M28:
backend 769 passed; 2 opt-in M21 E2E cases separately passed at that milestone;
frontend 76 passed; typecheck/build/Ruff/`py_compile`/Alembic/diff-check passed.
See `docs/m28/M28_CLOSEOUT.md`.
