# ADR-013: shadcn/ui + selected shadcn-admin patterns

**Status:** Accepted  
**Baseline:** Education OS Architecture Baseline v0.1

## Context

Education OS must scale from an initial private-school pilot to multi-institution operation without rebuilding the foundation.

## Decision

Keep Education OS on TanStack/Vite/shadcn conventions; do not add a second full CRUD framework unless justified by ADR.

## Consequences

- This is the default architecture for new work.
- A conflicting implementation requires a new ADR.
- Security and tenant isolation take precedence over short-term UI speed.
