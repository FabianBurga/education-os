# ADR-012: Do not adopt an existing SIS/ERP as core

**Status:** Accepted  
**Baseline:** Education OS Architecture Baseline v0.1

## Context

Education OS must scale from an initial private-school pilot to multi-institution operation without rebuilding the foundation.

## Decision

Use mature SIS products as domain references, not inherited architecture, due stack, licensing and country-specific constraints.

## Consequences

- This is the default architecture for new work.
- A conflicting implementation requires a new ADR.
- Security and tenant isolation take precedence over short-term UI speed.
