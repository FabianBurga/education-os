# M29-2 Teacher Continuity Workspace

## Status

M29-2 is CLOSED / PASS locally on migration `0048_m29_batch_ack_reads`.
The workspace is a bounded read orchestration surface. M13, M21, M27 and
SEC-TC1 remain authoritative for their existing data and authorization.

## Read contract

`GET /api/v1/continuity/worklist?limit=1..25` composes current, authorized
M21 follow-up and M27 obligation source reads. It enriches already-visible
targets with the protected SEC-TC1 batch purposes `M21_ACK_BATCH_READ` and
`M27_ACK_BATCH_READ`. Target authorization always precedes evidence lookup;
evidence never discovers targets.

Batch capabilities bind actor, tenant, purpose and a canonical sorted target
set digest. The database rejects empty, duplicate, mixed, oversized or
scalar/batch-mismatched target sets. Unauthorized targets are omitted.

## Visibility and privacy

Teachers receive only current M21 items within assignment/intervention scope
and only acknowledgement indicators when current communications visibility
also permits them. M27 items are omitted unless current `accountability.view`
and target scope authorize them. Coordinators and rectors use the same
current intersections of M13/M21/M27 permissions. Revocation is evaluated on
each request; no M29-2 state or cache restores access.

The payload contains bounded source and student identifiers, source state,
due metadata, an acknowledgement indicator, optional linked time, and a
source deep link. It contains no guardian data, message content, free text,
delivery report, M22 fields or restricted notes.

## UX and authority

The teacher workspace renders one `Mi continuidad` worklist with loading,
empty, error and bounded-page states. Actions are deep links into the owning
M21/M27 routes. M29-2 has no mutation, lifecycle, task, evidence or
continuity persistence authority, no new product permission, and no event.

## Validation

- Backend regression: 797 passed, 13 skipped, 144 warnings.
- Frontend: 79 tests passed; typecheck and production build passed.
- Local migration: 0047 -> 0048, 0048 -> 0047, and re-upgrade passed; one
  Alembic head is `0048_m29_batch_ack_reads`.
- Database ACL/RLS inspection confirms no direct `education_app` access to
  protected tables, no PUBLIC batch-function execution, issuer EXECUTE only
  on issuance, restricted function ownership, and FORCE RLS on all protected
  tables.
- Ruff, memory validation, architecture check and diff-check passed.

## Known limitations

- `accountability.view` currently has institution-wide M27 queue semantics;
  a future narrower case scope would require an explicit target-scope rule.
- The combined M21/M27 bounded page computes `has_more` after source-local
  limits, so the indicator is conservative/approximate.
- SEC-TC1 issuer integration tests remain skipped until a dedicated local
  issuer URL is provisioned; no credential is stored in the repository.
