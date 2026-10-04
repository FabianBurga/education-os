# M29-4 Controlled Institutional Pilot & Acceptance

Status: **PASS locally**. This acceptance uses synthetic fixtures and the
existing M13, M21, M27, M29-1, M29-2, M29-3, and SEC-TC1 contracts. No product
code, migration, permission, event, or persistence change was made.

## Pilot dataset and personas

The repeatable SEC-TC1 integration fixture creates one organization and
institution, one authorized student, a second hidden student, two guardian
identities where required, one published notice, one acknowledged receipt,
one M21 follow-up, one M27 obligation/case, and staff memberships for current
authorization checks. Fixture teardown removes its rows. No real student,
guardian, or institutional data is used.

Personas covered: teacher, academic coordinator, rector, and guardian.

## Scenario results

| Scenario | Expected | Observed | Result |
| --- | --- | --- | --- |
| A — teacher continuity | Current assignment exposes authorized M21 follow-up; M27 and evidence remain omitted without intersecting permissions | Source-owned M21 reads are assignment/current-scope bounded; unauthorized categories are omitted | PASS |
| B — coordinator/rector continuity | M21/M27 and evidence appear only under current domain permissions; deep links remain source-owned | Batch evidence tests pass for authorized staff; target-first enrichment and bounded deep links are preserved | PASS |
| C — family communication | Published notice is visible only to the current guardian and active student grant; acknowledgement is actor-specific | Guardian/M13 tests and protected acknowledgement integration pass; institution-wide notices remain institution-scoped | PASS |
| D — acknowledgement bridge | M13 acknowledgement can become explicit M21/M27 evidence without lifecycle mutation | Receipt, link/correction, read, idempotency, rollback, and retry tests pass; no completion/closure mutation occurs | PASS |
| E — family continuity | Bounded “Avisos para revisar” card only; no internal institutional data | Frontend tests, A3 review, and UX review confirm M21/M27/M22, notes, contacts, SEC-TC1, chat, and consent semantics are absent | PASS |
| F — revocation | Assignment, permission, grant, profile, and actor revocation removes current access | Revocation tests fail closed or omit data on the next request; historical involvement does not restore access | PASS |
| G — tenant/IDOR | Cross-tenant, cross-institution, cross-student, cross-guardian, hidden-target, and arbitrary target access fails closed or omits | Tenant-aware SQL, Guardian Console grants, target-first batch reads, and hidden-target tests pass | PASS |
| H — retry/idempotency | Repeated acknowledgement, capability, link, correction, and canonical batch requests converge safely | Permanent SEC-TC1 integration tests pass for retries, ordering, conflict, expiry, concurrency, and supersession | PASS |

## UX acceptance

Teacher continuity is bounded to 25 items and shows source, state, due
context, acknowledgement indicator, loading/empty/error states, refresh, and
authoritative deep links. Family continuity uses one bounded notice card with
“Reconocido”, “Requiere revisión”, and “Reconocer aviso”; these do not imply
consent, agreement, completion, or closure. Existing responsive navigation and
wrapping card layouts are retained.

Coordinator and rector continuity is validated through the shared authorized
backend service and source-domain contracts. A separate coordinator/rector
React card is not present; this is a follow-up usability item, not a release
blocker because no new frontend surface is required by the accepted scope.

## Security and privacy

A3: PASS with zero unresolved CRITICAL/HIGH findings. A4: PASS. Existing
medium follow-up debt is limited to Guardian Console transport minimization,
legacy Family Portal read-state mutation, and the accepted institution-level
M27 scope semantics. No M29 release blocker remains.

The cross-domain evidence rule remains enforced: a source record is trusted
for another domain only after its mutation boundary has been evaluated under
the same threat model. M29-1 evidence is consumed through its governed
M21/M27 contracts, never through raw cross-domain joins.

## Operational readiness

Migration head remains `0048_m29_batch_ack_reads`. Operators must provision the
SEC-TC1 roles, configure the separate `TRUSTED_CONTEXT_ISSUER_DATABASE_URL`,
and keep issuer credentials out of source, logs, and documentation. Existing
SEC-TC1 provisioning, rotation, fail-closed behavior, and verification steps
are documented in `docs/security/SEC_TC1_TRUSTED_CAPABILITY_FOUNDATION.md`.

Observability uses existing request/runtime logs and database audit records;
no telemetry subsystem or read-audit stream was added.

## Validation evidence

- Focused M29/M13/Guardian suite: 61 passed with issuer configuration.
- Frontend: 84 passed, 0 failed, 0 skipped; typecheck and production build
  passed.
- Full issuer-backed backend: 810 passed, 0 failed, 2 optional M21 E2E skips,
  144 warnings. The skips require `M21_E2E_DATABASE_URL` and are defined as
  opt-in by the existing test contract.
- A3 security review: PASS.
- A4 independent QA: PASS.
- Alembic: one head, `0048_m29_batch_ack_reads`.

## Release recommendation

M29 is ready for release consideration. No push, tag, or release was
performed. Remaining work is follow-up debt only: finer M27 target scope,
transport-level notice minimization, human-readable staff student labels, and
optional M21 E2E environment provisioning.
