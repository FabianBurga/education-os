# Automation Worker — M0 contract

M0 does not yet ship external notification adapters.

The first worker implementation must:

1. Claim `outbox_events` in `PENDING` state with a concurrency-safe strategy.
2. Process idempotently.
3. Increment attempts.
4. Mark `PROCESSED` only after required handlers succeed.
5. Mark `FAILED` or `DEAD` after policy limits.
6. Preserve original event and error metadata.
7. Set the same tenant context before reading institution-scoped data.

Do not place SMTP, WhatsApp or SMS credentials in domain code.
