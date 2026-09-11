# M0 Acceptance Gate

M0 is approved only when every blocking item is green.

## BLOCKING

- [ ] Repository created from this package / approved seed
- [ ] CI running on every PR
- [ ] PostgreSQL migrations apply from empty database
- [ ] Runtime DB role is non-owner
- [ ] RLS is enabled and forced
- [ ] Two synthetic organizations/institutions exist in tests
- [ ] Tenant A can read its own rows
- [ ] Tenant A cannot read Tenant B rows
- [ ] Tenant A cannot insert/update Tenant B rows
- [ ] No tenant context returns no scoped rows
- [ ] Identity + membership context works
- [ ] Permission data model exists
- [ ] Outbox table and transactional enqueue contract exist
- [ ] Audit table/service contract exists
- [ ] Backend lint passes
- [ ] Backend tests pass
- [ ] `/health` responds
- [ ] `/api/v1/me` contract exists
- [ ] `/api/v1/campuses` relies on RLS for boundary

## NON-BLOCKING FOR M0

- [ ] Final branding
- [ ] Final rector dashboard
- [ ] Student module
- [ ] Parent app
- [ ] Attendance
- [ ] Grades
- [ ] Finance
- [ ] Production email/WhatsApp
- [ ] AI

## Exit

When blocking items are green, tag:

`m0-foundation-v0.1`

Then open:

`M1 — Students / Families / Enrollment`
