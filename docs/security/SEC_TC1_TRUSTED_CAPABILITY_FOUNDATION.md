# SEC-TC1 — Trusted Database Capability Foundation

Status: implemented in migration `0047_sec_tc1_m29_ack_bridge`; M29-1 is its
first and only current product consumer.

## Trust boundary

`education_app` remains the ordinary shared runtime database role. Its
caller-settable `app.user_id`, `app.organization_id`, and
`app.institution_id` GUC values remain untrusted for privileged SEC-TC1
operations. A privileged operation accepts only a short-lived, one-use,
database-issued opaque capability bound to actor, organization, institution,
purpose, operation, target, and idempotency fingerprint. The database
rechecks current account activity, membership, permissions, tenant scope, and
domain authorization at consumption time. Capabilities expire after at most
60 seconds. There is no generic act-as-user capability.

This boundary addresses arbitrary SQL as `education_app`; it does not claim
protection against application-host compromise, stolen authentication
credentials, or compromise of the schema owner.

## Roles and access

- `education_context_issuer`: separate LOGIN role/credential used only by the
  authenticated FastAPI issuer path. It has no product-table DML and no direct
  capability-store access.
- `education_context_function_owner`: NOLOGIN, NOSUPERUSER, NOCREATEDB,
  NOCREATEROLE, NOINHERIT, NOBYPASSRLS. It owns narrowly scoped
  SECURITY DEFINER functions and is not owner of unrelated product tables.
- `education_owner`: schema/migration authority only; it is never used as the
  application issuer connection.
- `education_app`: has no direct privileges on the capability or M21/M27
  evidence/correction tables. It can call only the exact protected consumer
  functions. For legacy family receipts, its INSERT is limited to non-ack
  receipt/read fields, and UPDATE is limited to `read_at`; it cannot write
  `acknowledged_at`.

All SEC-TC1 tables use ENABLE RLS and FORCE RLS. RLS scopes database access;
it is not treated as authentication. Security-definer functions pin
`search_path`, qualify relations, revoke PUBLIC execution, and recheck current
authorization.

## First consumer: M13/M21/M27

M13 remains authoritative for `FamilyNoticeReceipt` and acknowledgement
lifecycle. Guardian acknowledgement is accepted only after current account,
guardian profile, published notice, tenant/institution, and student portal
grant checks. M21 owns follow-up evidence links/corrections; M27 owns
accountability-obligation evidence links/corrections. The link is an
institutional human assertion that an acknowledgement is relevant evidence;
it is not agreement, consent, completion, satisfaction, closure, or a
decision. No canonical event is added and no domain lifecycle is changed
automatically.

The full bridge and its validated behaviors are recorded in
[`M29_1_ACKNOWLEDGEMENT_EVIDENCE_BRIDGE.md`](../m29/M29_1_ACKNOWLEDGEMENT_EVIDENCE_BRIDGE.md).

## Provisioning and deployment order

1. With schema-owner administration, set `OWNER_DATABASE_URL` and a
   high-entropy `TRUSTED_CONTEXT_ISSUER_PASSWORD` in the provisioning
   process environment. Run `scripts/provision_sec_tc1_roles.py`. The helper
   verifies role attributes/memberships/grants, does not print the password,
   and refuses unsafe existing role state.
2. Apply the ordinary Alembic upgrade to `0047_sec_tc1_m29_ack_bridge` using
   schema-owner credentials. The migration contains no secret and expects the
   roles to exist.
3. Configure the application with a distinct
   `TRUSTED_CONTEXT_ISSUER_DATABASE_URL` using the issuer credential. Never
   fall back to `DATABASE_URL` or `OWNER_DATABASE_URL` for issuer operations.
4. Deploy/restart the application and verify ordinary legacy requests still
   use their existing `app.*` context while protected operations fail closed
   if the issuer URL is absent or unusable.
5. Rotate the issuer credential through the provisioning helper and runtime
   secret-management process. Do not place credentials in Alembic source,
   SQL, Git, logs, committed tests, or documentation.

Ordinary legacy behavior remains available if SEC-TC1 issuer configuration is
absent; SEC-TC1 protected operations fail closed. The local test deployment
validated a downgrade to 0046 and re-upgrade to 0047 only after confirming
new capability/evidence tables were empty. Production provisioning or
migration was not performed.

## Known limitations

- Capability rows are durable provenance for M29 links and currently have no
  scheduled cleanup. Expired capabilities cannot grant authority; consumed
  acknowledgement provenance must remain while dependent links exist.
- Legacy receipt SELECT/read-state authorization and the broader HTTP
  principal `is_active` path are unchanged debt; SEC-TC1 does not redefine
  legacy GUC or authentication behavior.
- Future consumers require their own reviewed purpose/function/migration
  contract. No M0-M28 module has been migrated to SEC-TC1.
