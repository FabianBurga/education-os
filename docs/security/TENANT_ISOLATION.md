# Tenant Isolation Security Contract

## Threat model

A user or bug may try to:

- replace an institution ID in a URL
- craft an API request manually
- omit expected frontend filters
- reuse a valid token for another institution
- exploit a missing ORM predicate
- access another tenant through an internal job

M0 assumes these attempts will happen.

## Required controls

### Runtime DB role

`education_app`:

- is not SUPERUSER
- is not table owner
- cannot create roles/databases
- receives only required table privileges

### Transaction tenant context

Every authenticated institution request sets:

- `app.organization_id`
- `app.institution_id`
- `app.user_id`

with transaction-local scope.

### RLS

Institution-scoped tables have:

- RLS enabled
- FORCE RLS
- `USING` policy
- `WITH CHECK` policy

### Automated negative tests

CI must fail if Tenant A can:

- select a row from Tenant B
- insert a row for Tenant B
- update/delete Tenant B
- see rows with no tenant context

## Production hardening still required after M0

- dedicated migration role separate from infrastructure owner
- secret manager
- DB TLS enforcement
- connection-pool context reset validation
- backup/restore drills
- audit retention policy


## Authentication bootstrap note

M0 protected requests trust only tenant scope claims from an Education OS-signed JWT, then validate the membership under RLS.

The initial email/password login lookup is intentionally **not** implemented in M0. Before adding it, choose one audited pattern:

- a narrowly scoped SECURITY DEFINER authentication function, or
- a dedicated authentication provider/service boundary.

Do not solve login by granting the runtime role unrestricted credential-table access.
