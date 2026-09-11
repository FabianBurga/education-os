# ADR-001: Use a modular monolith

**Status:** Accepted  
**Baseline:** Education OS Architecture Baseline v0.1

## Context

Education OS must scale from an initial private-school pilot to multi-institution operation without rebuilding the foundation.

## Decision

Education OS starts as one deployable backend with strict domain module boundaries. Microservices are deferred until independent scaling, reliability or ownership creates a proven need.

## Consequences

- This is the default architecture for new work.
- A conflicting implementation requires a new ADR.
- Security and tenant isolation take precedence over short-term UI speed.
