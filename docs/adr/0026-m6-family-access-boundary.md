# ADR 0026 — Family access boundary

Status: Accepted for v0.7.0.

## Problem

La mera pertenencia (`membership`) a una institución no es suficiente para decidir
qué APIs puede utilizar una persona. Un representante no debe heredar acceso a
Students, Academics, Grades o Automation internos.

## Decision

M6 añade dos resoluciones ABAC:

- Staff access = user account → person → active StaffProfile.
- Guardian access = user account → person → active GuardianProfile.

Los routers internos de M1–M5 requieren StaffProfile. Family Portal requiere
GuardianProfile.

Una misma persona puede ser staff y guardian y, en ese caso, puede ejercer ambos
contextos sin duplicar identidad.
