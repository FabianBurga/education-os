# ADR-004: PostgreSQL as system of record

**Status:** Accepted  
**Baseline:** Education OS Architecture Baseline v0.1

## Context

Education OS must scale from an initial private-school pilot to multi-institution operation without rebuilding the foundation.

## Decision

Use PostgreSQL for relational integrity, transactions, RLS, JSONB where appropriate and future analytical extensions.

## Consequences

- This is the default architecture for new work.
- A conflicting implementation requires a new ADR.
- Security and tenant isolation take precedence over short-term UI speed.
