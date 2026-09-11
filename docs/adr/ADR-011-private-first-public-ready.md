# ADR-011: Private Edition first, public-ready core

**Status:** Accepted  
**Baseline:** Education OS Architecture Baseline v0.1

## Context

Education OS must scale from an initial private-school pilot to multi-institution operation without rebuilding the foundation.

## Decision

Commercial V1 targets private institutions while institutional type/capabilities remain configurable for public/fiscomisional editions.

## Consequences

- This is the default architecture for new work.
- A conflicting implementation requires a new ADR.
- Security and tenant isolation take precedence over short-term UI speed.
