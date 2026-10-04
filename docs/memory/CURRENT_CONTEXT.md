# Current context

Education OS is on `m29-teacher-family-continuity`. M28 remains CLOSED /
PUBLISHED / CANONICAL at tag `m28-operational-adoption-core-v0.28.0`, commit
`c21e7c1287a8bc7abd8f355aa619e67c0beee0c4`.

## Current slice

M29-1 — Family Acknowledgement Evidence Bridge: CLOSED / PASS after local
migration, security, and backend regression validation. Migration head:
`0047_sec_tc1_m29_ack_bridge`. SEC-TC1 is implemented as the first consumer
of the database-issued one-time capability boundary. The current memory
anchor remains the pre-slice accepted base `7134bad2608f60c81bc9d199ab277340d962caf7`;
the M29-1 implementation and evidence are captured below and in the linked
closeout documents.

## Accepted facts and authority

- M13 owns `FamilyNoticeReceipt` and guardian acknowledgement lifecycle.
  `education_app` cannot insert/update `acknowledged_at`; the protected M13
  operation rechecks the active guardian account/profile, notice, tenant, and
  current portal grant. Existing receipt SELECT/read-state limitations remain
  known debt.
- SEC-TC1 issues 60-second, operation/target/tenant/actor-bound opaque
  capabilities through the dedicated issuer connection. Legacy `app.*` GUCs
  are not privileged identity proof. `education_context_function_owner` is
  restricted, NOLOGIN, and NOBYPASSRLS.
- M21 owns follow-up acknowledgement evidence links/corrections; M27 owns
  obligation evidence links/corrections. Link evidence does not change
  intervention, follow-up, obligation, case, or academic lifecycle. No new
  canonical event or M29 authority was introduced.
- `education_app` has no direct access to the capability or four evidence
  tables. Those tables retain ENABLE/FORCE RLS, tenant-aware FKs, and append-only
  triggers. Downgrade refuses while capability/evidence rows remain.
- No frontend change, historical backfill, or external delivery integration
  was introduced.

## Validated baseline

Full backend: 801 passed, 0 failed, 2 opt-in M21 E2E skipped because
`M21_E2E_DATABASE_URL` was unset, 144 warnings. Focused M29/M6/M7 DB/security:
29 passed. Focused unit/contracts: 40 passed. Ruff, `py_compile`, memory and
architecture checks, Alembic single-head/current, local 0046→0047 upgrade,
0047→0046 downgrade and re-upgrade, and `git diff --check` passed. See
`docs/memory/VALIDATION_BASELINE.md`,
`docs/m29/M29_1_ACKNOWLEDGEMENT_EVIDENCE_BRIDGE.md`, and
`docs/security/SEC_TC1_TRUSTED_CAPABILITY_FOUNDATION.md`.

## Known debt

- Capability rows are durable provenance and have no scheduled cleanup;
  retain consumed M13 provenance while dependent evidence links exist.
- Ordinary legacy HTTP authentication does not globally recheck
  `user_accounts.is_active`; SEC-TC1 protected functions do. Do not widen this
  slice to rewrite legacy authentication.
- Receipt read authorization/read-state exposure is existing M6 debt.
- Two opt-in M21 E2E tests remain unrun without `M21_E2E_DATABASE_URL`.

## Operating rules

A0 remains the single orchestrator and Git mutation owner. Keep A1/A2/A3/A4
roles bounded, enforce one writer per file per wave, and use the Task Contract
and test-selection harness. Do not reconstruct M0-M28 when this memory is
fresh; repository evidence wins if it contradicts memory. No push, tag, or
release is authorized by this local implementation closeout.

Next: A0 should define the next bounded M29 slice from verified continuity
gaps; do not assume family conversations, consent/preferences, retention,
guardian disputes, or response moderation semantics.
