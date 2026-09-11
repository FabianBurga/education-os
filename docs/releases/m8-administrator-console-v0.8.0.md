# M8 — Administrator Console v0.8.0

Base: `v1.0.0-rc5`

M8 converts the administrator role from an API-first gap into a human-usable,
institution-scoped console.

Delivered:
- SYSTEM_ADMIN permission boundary (`admin.console.access`);
- current institution settings and campus creation;
- person creation;
- secure account + membership creation;
- staff profile creation;
- role and permission administration;
- Administrator Console visual surface;
- academic setup forms using M2 APIs;
- student/guardian/family/enrollment setup using M1 APIs;
- onboarding readiness checklist;
- administrative audit events;
- owner-only explicit SYSTEM_ADMIN bootstrap utility;
- isolated end-to-end verifier.

M8 does not let an institution administrator create a brand-new organization
or sibling institution. Tenant provisioning remains a platform/bootstrap
action.

Do not tag `m8-administrator-console-v0.8.0` until local verification and
GitHub CI are green.
