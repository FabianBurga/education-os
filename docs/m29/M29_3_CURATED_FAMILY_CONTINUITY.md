# M29-3 Curated Family Continuity

M29-3 is closed locally as a **DESIGN_A** frontend composition. The
Guardian Console remains the family authority; the React workspace adds one
bounded **Avisos para revisar** card and uses the existing M13 notice and
acknowledgement contracts.

## Boundary

- Notice visibility, student grants, and guardian revocation remain enforced
  by the Guardian Console/M13 backend.
- Acknowledgement is actor-specific recognition of the notice. It does not
  mean consent, agreement, approval, completion, or closure.
- M21, M27, and M22 are invisible to family users. No intervention,
  obligation, intelligence, teacher-note, contact, delivery-report, or
  SEC-TC1 data is requested or rendered.
- The card adds no backend API, migration, permission, event, persistence,
  projection, conversation, or free-text reply.

## Read behavior

The card reads the existing Guardian Console `GET /api/v1/guardian/notices`
and, when permitted, `GET /api/v1/guardian/students`. It does not poll;
refresh is explicit. The Guardian Console notice list is read-only, so card
rendering does not create receipts or change `read_at`/`acknowledged_at`.
The older Family Portal notice-list endpoint has a pre-existing `read_at`
side effect; it is not used by this card.

Only the current guardian's acknowledgement state is shown. Institution-wide
notices remain separate from student-specific labels, and revoked access is
enforced on the next backend request.

## Validation

- Frontend: 84 tests passed; typecheck and production build passed.
- Guardian/M13 contract checks: 21 focused backend tests passed.
- Full backend with the local issuer configured: 810 passed, 2 optional M21
  E2E skips, 144 warnings. No M29-3-specific backend skip was introduced.
- A3 privacy/security review and A4 independent QA passed with no unresolved
  critical or high findings.

Known legacy debt remains outside this slice: the existing Guardian Console
transport includes fields that this card ignores, the Family Portal notice
list retains its established read-state side effect, and broader legacy
receipt/read-state authorization is unchanged.
