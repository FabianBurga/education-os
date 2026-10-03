# M29 implementation plan

Status: M29-0 is the current documentation/discovery slice. No M29 product
implementation or migration is authorized by this plan. Base is M28 tag
`m28-operational-adoption-core-v0.28.0` at
`c21e7c1287a8bc7abd8f355aa619e67c0beee0c4`.

## M29-0 — Canonical Bootstrap, Context Normalization & Contract Freeze

- Create `m29-teacher-family-continuity` exactly from the immutable M28 tag.
- Normalize current-state documentation while preserving milestone history.
- Inventory current teacher/student/family/communications capabilities.
- Map end-to-end continuity gaps and permission/evidence boundaries.
- Freeze bounded product scope, authorities, privacy rules, event/offline
  reuse, non-goals and a design-only validation strategy.
- No application code, API, migration, database mutation, push, tag or release.
- Acceptance: clean branch base, documentation consistency, verified references,
  JSON parsing, `git diff --check`, source diff empty; local documentation-only
  commit if all gates pass.

## Proposed future slices — require M29-0 contract approval

1. **M29-1 — Continuity workflow contract and smallest bridge.** Implement only
   a proven gap connecting existing communication recipient/acknowledgement to
   the correct existing owner/follow-up, if accepted. Preserve M13 ownership and
   separate M21 action from M27 obligation. Any new field/table/API is
   PROPOSED / NOT IMPLEMENTED until authority and migration need are approved.
2. **M29-2 — Teacher continuity experience.** Present existing assigned
   student context, owned follow-ups and authorized communication state; no
   duplicate intervention/accountability workflow.
3. **M29-3 — Family continuity experience.** Extend curated M6/M12/M13 views
   only after consent, grant, visibility, response and retention contracts are
   accepted. No wholesale timeline/intelligence exposure or external channel
   implied.
4. **M29-4 — Controlled continuity pilot and closure.** Synthetic tenant
   evidence, authorized role matrix, event/offline replay and residue checks;
   real adoption/value claims require separate human field evidence.

Slice count/order is provisional. Contract review may narrow or combine slices;
it must not expand authority implicitly.

## Design-only test families

Reuse fixtures and actual HTTP/RLS patterns from `test_m6_guardian_rls.py`,
M12 guardian access/contract/privacy tests, M13 communications targeting/privacy
tests, M10 teacher access tests, M20 offline contract/auth tests, M21 timeline
and intervention integration tests, M27 review/obligation tests, and M28
security/continuity/synthetic pilot tests.

Future acceptance should cover tenant isolation; guardian/student active grant;
teacher assignment scope; family visibility; restricted-note non-disclosure;
cross-student/family IDOR; communication authorization; acknowledgement
idempotency and duplicate response behavior; follow-up/accountability linkage;
event idempotency; offline eventual continuity; revoked teacher/guardian scope;
historical evidence preservation; audit and PII minimization. Use real
FastAPI/TestClient and application-role PostgreSQL/RLS checks, fake providers,
rollback-contained fixtures, and zero-residue verification. This list is not
test implementation or proof of currently supported response behavior.

## Migration policy

Known M28 head is `0046_m28_attendance_perms`. M29-0 creates no migration. If a
later contract requires schema, first prove why M13 communication recipients/
receipts or M21/M27-owned follow-up state cannot represent it. Any possible
communication-to-follow-up relation is `PROPOSED / NOT IMPLEMENTED`: M13 owns
publication/recipient delivery, M21 owns operational action/follow-up, and M27
owns accountability obligations. Do not choose an owner or duplicate status
before product/security review.

For any future migration proposal, document why it is needed; authoritative
data owner; tenant composite keys, RLS/FORCE RLS and grants; migration/preflight
and any backfill; family/minor-data privacy and historical evidence impact;
rolling compatibility; forward repair; rollback strategy; and operational
verification. Never modify committed migrations or downgrade the valid M28
baseline as a repair.
