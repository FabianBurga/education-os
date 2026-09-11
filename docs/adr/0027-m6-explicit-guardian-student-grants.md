# ADR 0027 — Explicit guardian-student portal grants

Status: Accepted for v0.7.0.

## Decision

La relación familiar y el acceso digital son conceptos distintos.

`StudentGuardianRelationship` expresa relación/atributos familiares.
`GuardianStudentPortalAccess` expresa autorización digital.

El bootstrap inicial puede otorgar acceso solo cuando una relación es:
- legal guardian; o
- primary contact.

Después del bootstrap, grant/revoke es explícito y auditable por estado.
