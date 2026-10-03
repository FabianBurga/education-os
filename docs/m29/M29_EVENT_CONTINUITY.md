# M29 event and offline continuity contract

No new event, projection, schema or offline behavior is implemented in M29-0.

## Existing path

```text
authorized teacher command
  -> authoritative M1/M2/M3 transaction
  -> transactional outbox_events
  -> idempotent M18 event_ledger ingestion
  -> explicit M21/M22/M27 consumer/projection where supported
  -> authorized staff decision / existing M13 publication
  -> family_notice + family_notice_receipt acknowledgement
```

M18 remains the only canonical event ledger. Its source-outbox identity,
tenant/institution scope, event version, correlation/causation and checkpointed
idempotent projections are described in `docs/architecture/m18-event-platform.md`.
Domain tables remain operational truth.

## M20 offline continuity

M20 queues teacher attendance operations in the existing PWA/IndexedDB and
syncs through `/api/v1/teacher/offline/sync`. It reauthorizes current teacher
permission and assignment, compares base state, records immutable
`teacher_offline_receipts`, mutates the authoritative M3 attendance row, writes
audit and emits canonical event/outbox in the transaction. A receipt/status is
sync provenance, not attendance truth. M28 verifies online/offline convergence
and M18/M21 replay continuity (`test_m28_attendance_continuity_contract.py`,
M21 timeline E2E tests).

M29 must not add a family-send queue to the offline client. A family
communication may only be authored/published through the existing server-side
M13 authority after sync and current authorization. Offline fact → family
notification is not an existing contract and must not be inferred from an
attendance event.

## Candidate continuity references (PROPOSED / NOT IMPLEMENTED)

If discovery/accepted requirements prove it necessary, a continuity link may
reference an authoritative event/domain ID, communication/recipient, M21
follow-up or M27 obligation by opaque ID. Before any schema proposal define:
tenant composite ownership, source/destination authorization, idempotency,
revocation behavior, correction/deletion retention, event version, causal
lineage, projection checkpoint, and no-copy privacy semantics. Do not duplicate
mutable delivery or obligation status.

Communication published, recipient delivery, family acknowledgement, family
response, staff follow-up and accountability decision remain separate event
families/lifecycles. No official continuity metric is defined until its event
semantics, denominator, missingness and freshness contract are accepted.
