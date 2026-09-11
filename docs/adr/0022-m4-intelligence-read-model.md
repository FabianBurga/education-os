# ADR 0022 — Rector Intelligence read model

Status: Accepted for v0.5.0.

## Decision

M4 no crea una segunda base analítica ni replica datos. El dashboard lee directamente
el modelo transaccional protegido por RLS y produce un read model agregado.

Las agregaciones permanecen simples y auditables en V1. Si el volumen futuro requiere
materialización/caching, se podrá introducir sin cambiar los contratos REST.

## Why

La prioridad de M4 es exactitud, trazabilidad y aislamiento multi-tenant, no complejidad
prematura de data warehouse.
