# M0 v0.1.1 Security/Bootstrap Patch

Changes from v0.1:

1. Fixes editable-install packaging for Hatch.
2. Adds `organization_id` to signed JWT tenant context.
3. Applies signed tenant context before membership validation so RLS participates correctly.
4. Adds RLS to `user_accounts` for post-auth self access.
5. Restricts runtime credential/catalog privileges.
6. Adds tests for `rolbypassrls`, forced RLS, cross-tenant update and delete.
7. Fixes demo-seed cleanup order.
8. Documents the deferred authentication-bootstrap boundary.

No product scope or approved Architecture Baseline decision changes.
