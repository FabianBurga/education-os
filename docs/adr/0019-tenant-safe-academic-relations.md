# ADR 0019 — Tenant-safe academic relationships

Status: Accepted for Education OS v0.3.0.

## Problem

RLS protege filas, pero una FK simple por UUID no garantiza por sí sola que un registro
hijo no apunte a un UUID conocido de otro tenant.

## Decision

M2 combina:

1. `organization_id` + `institution_id` en todas las tablas operativas.
2. PostgreSQL FORCE RLS.
3. FKs compuestas que obligan a que las referencias académicas pertenezcan a la misma institución.
4. Endurecimiento equivalente para relaciones críticas creadas en M1.
5. Validación de referencias a través de sesiones sometidas a RLS en la API.

La defensa no depende solamente de la capa HTTP.
