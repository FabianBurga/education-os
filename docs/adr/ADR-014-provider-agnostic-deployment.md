# ADR-014: Provider-agnostic containers

**Status:** Accepted  
**Baseline:** Education OS Architecture Baseline v0.1

## Context

Education OS must scale from an initial private-school pilot to multi-institution operation without rebuilding the foundation.

## Decision

Develop with containers and managed PostgreSQL-compatible deployment assumptions. Avoid infrastructure lock-in in domain code.

## Consequences

- This is the default architecture for new work.
- A conflicting implementation requires a new ADR.
- Security and tenant isolation take precedence over short-term UI speed.
