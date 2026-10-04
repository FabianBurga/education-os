# Current context

Education OS is on `m29-teacher-family-continuity`. M28 remains CLOSED /
PUBLISHED / CANONICAL at tag `m28-operational-adoption-core-v0.28.0`, commit
`c21e7c1287a8bc7abd8f355aa619e67c0beee0c4`.

## Current slice

M29-3 — Curated Family Continuity: CLOSED / PASS after frontend,
Guardian Console/M13 contract, privacy, and backend regression validation.
The implementation is DESIGN_A: one bounded React “Avisos para revisar” card
composed from existing family-safe Guardian Console reads. Migration head
remains `0048_m29_batch_ack_reads`; no backend API, migration, permission,
event, persistence, or new authority was added.

M29-2 — Teacher Continuity Workspace: CLOSED / PASS after local migration,
security, frontend and backend regression validation. Migration head:
`0048_m29_batch_ack_reads`. The workspace is a read-only orchestration layer
over M21/M27 source reads and the governed SEC-TC1 batch evidence contract.
M29-1 remains the trusted acknowledgement bridge. The current memory anchor
remains the accepted pre-slice project baseline; inspect the accepted delta
before wider discovery.

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
- M29-2 introduced no frontend change, historical backfill, or external
  delivery integration; M29-3 later added only the approved family card.
- M29-2 adds `M21_ACK_BATCH_READ` and `M27_ACK_BATCH_READ` with canonical
  target-set digest binding and a 25-target bound. Unauthorized targets are
  omitted and acknowledgement evidence cannot discover targets.
- `GET /api/v1/continuity/worklist` is read-only and bounded. It adds no
  permission, event, projection, persistence authority or lifecycle state.
  Teachers receive current authorized M21 continuity; M27 is omitted unless
  current M27 authorization exists.
- M29-3 is a family-only DESIGN_A composition in the existing Guardian
  Console workspace. It shows one bounded “Avisos para revisar” notice card
  using existing M13 notice and acknowledgement contracts.
- M21, M27, and M22 remain invisible to family users. Acknowledgement display
  is actor-specific; no consent, conversation, free text, persistence,
  backend API, permission, migration, or event was added.
- The M29-3 card uses the read-only Guardian Console notice list with no
  polling. The older Family Portal notice list's established read-state side
  effect is outside this card.

## Validated baseline

Full backend issuer-backed remediation baseline: 810 passed, 2 skipped, 144
warnings. The only skips are opt-in M21 E2E cases requiring
`M21_E2E_DATABASE_URL`; SEC-TC1 issuer tests ran.
Frontend: 79 passed; typecheck and production build passed. Focused M29-2
contracts: 16 passed. Permanent SEC-TC1 integration coverage: 24 passed,
0 skipped. Ruff, memory and architecture checks, Alembic
0047→0048 upgrade, 0048→0047 downgrade and re-upgrade, local ACL/RLS checks,
and `git diff --check` passed. See
`docs/memory/VALIDATION_BASELINE.md`,
`docs/m29/M29_1_ACKNOWLEDGEMENT_EVIDENCE_BRIDGE.md`, and
`docs/security/SEC_TC1_TRUSTED_CAPABILITY_FOUNDATION.md`.

## M29-3 closeout baseline

Frontend: 84 passed; typecheck and production build passed. Focused
Guardian/M13 contract checks: 21 passed. Full issuer-backed backend: 810
passed, 2 optional M21 E2E skips, 144 warnings. A3 privacy/security review
and A4 independent QA passed with zero unresolved CRITICAL/HIGH findings.
See `docs/m29/M29_3_CURATED_FAMILY_CONTINUITY.md`.

## Known debt

- Capability rows are durable provenance and have no scheduled cleanup;
  retain consumed M13 provenance while dependent evidence links exist.
- Ordinary legacy HTTP authentication does not globally recheck
  `user_accounts.is_active`; SEC-TC1 protected functions do. Do not widen this
  slice to rewrite legacy authentication.
- Receipt read authorization/read-state exposure is existing M6 debt.
- Two opt-in M21 E2E tests remain unrun without `M21_E2E_DATABASE_URL`.
- SEC-TC1 issuer credentials remain process/deployment managed and are never
  stored in Git.
- Existing Guardian Console notice transport and legacy Family Portal
  read-state behavior remain outside the curated frontend boundary and are
  known legacy debt.

## Operating rules

A0 remains the single orchestrator and Git mutation owner. Keep A1/A2/A3/A4
roles bounded, enforce one writer per file per wave, and use the Task Contract
and test-selection harness. Do not reconstruct M0-M28 when this memory is
fresh; repository evidence wins if it contradicts memory. No push, tag, or
release is authorized by this local implementation closeout.

Next: A0 should define the next bounded M29 slice from verified continuity
gaps; do not assume family conversations, consent/preferences, retention,
guardian disputes, response moderation, or broader SEC-TC1 adoption.
