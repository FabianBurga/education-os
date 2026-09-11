# Domain Model M0

## Organization

A network, legal operator or grouping of institutions.

## Institution

The operational school tenant. Holds `institution_type`:

- PRIVATE
- PUBLIC
- FISCOMISIONAL
- MUNICIPAL

## Campus

Institution subdivision. A school may have one or many.

## Person

A human identity inside an organization.

A person is **not** a role.

Later milestones may attach:

- StudentProfile
- GuardianProfile
- StaffProfile

## UserAccount

Digital credential linked to one Person.

## Membership

Links UserAccount to Institution.

A single user may have memberships in multiple institutions.

## Role and Permission

Roles are institution-local bundles. Permissions are stable capability keys.

Future domain scope can further restrict a granted permission.

## OutboxEvent

Durable domain/integration event inserted in the same transaction as a mutation.

## AuditLog

Immutable operational trace of a sensitive action.
