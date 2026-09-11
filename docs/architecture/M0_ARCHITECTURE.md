# M0 Architecture — Foundation & Tenant Isolation

## Purpose

M0 proves that every future module can safely share one PostgreSQL cluster while preserving hard institutional boundaries.

## Request path

```text
Client
  ↓
FastAPI authentication
  ↓
Membership validation
  ↓
TenantContext(org, institution, user)
  ↓
set_config(..., true) inside transaction
  ↓
Permission / domain scope
  ↓
PostgreSQL RLS
  ↓
Rows
```

## Two security layers

1. **Application authorization**
   - user identity
   - active membership
   - permissions
   - assignment/domain scope

2. **Database isolation**
   - application connection is not table owner
   - `ENABLE ROW LEVEL SECURITY`
   - `FORCE ROW LEVEL SECURITY`
   - tenant context read from PostgreSQL session settings

Neither layer replaces the other.

## Tenant hierarchy

```text
Platform
└── Organization
    └── Institution
        └── Campus
```

`Organization` is the commercial/legal grouping.  
`Institution` is the primary operational tenant.  
`Campus` is a physical/operational subdivision.

## M0 tables

- organizations
- institutions
- campuses
- institution_capabilities
- persons
- user_accounts
- memberships
- roles
- permissions
- role_permissions
- membership_roles
- outbox_events
- audit_logs

## RLS principle

No institution-scoped query should require the frontend to send a security filter such as `institution_id=...`.

The authenticated request establishes tenant context. RLS supplies the hard boundary.

Explicit filters may still be used for performance and clarity, but they are **not** the security mechanism.
