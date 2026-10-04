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

## M29-3 Curated Family Continuity closeout

- DESIGN_A frontend composition: one bounded Guardian Console “Avisos para
  revisar” card; no backend API, migration, permission, event, persistence,
  projection, or new authority.
- Focused frontend: **5 passed**; full frontend: **84 passed**; typecheck and
  production build passed.
- Guardian/M13 contract validation: **21 passed**. Full issuer-backed backend:
  **810 passed, 2 skipped, 144 warnings**. The only skips are the optional
  M21 E2E cases requiring `M21_E2E_DATABASE_URL`.
- A3 privacy/security review and A4 independent QA passed with zero unresolved
  CRITICAL/HIGH findings. The Guardian Console notice list is read-only for
  this card; the older Family Portal read-state side effect remains legacy
  behavior outside the card.

## M29-4 Controlled Institutional Pilot & Acceptance

- Synthetic scenarios A–H passed across M13, M21, M27, M29-1, M29-2, M29-3,
  and SEC-TC1. No real institutional data was used.
- Full issuer-backed backend: **810 passed, 0 failed, 2 optional M21 E2E
  skips, 144 warnings**. The skips require `M21_E2E_DATABASE_URL`.
- Frontend: **84 passed, 0 failed, 0 skipped**; typecheck and production
  build passed. Focused M29/M13/Guardian suite passed.
- A3 security review and A4 independent QA: PASS; zero unresolved
  CRITICAL/HIGH findings. Release blockers: none.
- Migration remains `0048_m29_batch_ack_reads`; no product or schema changes
  were made during acceptance.

## Inherited baseline

M28 closeout evidence remains historical and authoritative for M28:
backend 769 passed; 2 opt-in M21 E2E cases separately passed at that milestone;
frontend 76 passed; typecheck/build/Ruff/`py_compile`/Alembic/diff-check passed.
See `docs/m28/M28_CLOSEOUT.md`.
