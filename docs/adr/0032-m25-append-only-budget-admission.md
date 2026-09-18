# ADR 0032 — M25 Append-Only Budget Admission

## Decision

Provider costs are integer micro-USD append-only ledger events, not mutable balances. Admission reserves RUN, tenant-day UTC, and tenant-month UTC budget before invocation. PostgreSQL transaction-scoped advisory locks serialize each tenant-period admission.

## Consequences

The lock, exposure calculation, and RESERVED writes must remain in one transaction. Budget denial invokes no provider. Finalization appends CONSUMED and RELEASED events; it never updates prior events.
