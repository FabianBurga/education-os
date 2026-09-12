# Education OS — M13 Communications Center v0.13.0

## Frozen base

- Base tag: `m12-guardian-console-v0.12.0`
- Base commit: `0af3e81afb44ff5a68fa098aae2ea14599e70a15`
- Database before M13: `0014_m12`
- Database after M13: `0015_m13`

M13 is additive. It does not rewrite the frozen M12 Guardian Console, M11
Student Console, M10 Teacher Console, M9 Coordination Console, or M8
Administrator Console.

## Product scope

M13 introduces an institutional Communications Center for staff-authorized,
in-app communication toward families linked through active portal grants.

The authoring flow is:

`Mensaje → Segmentación → Vista previa → Publicación → Entrega → Lectura / Confirmación`

Supported target scopes:

- institution
- campus
- section
- course offering
- individual student
- family / household

The target resolves to active students and their active
`guardian_student_portal_access` relationships. M13 is deliberately
family-facing in v0.13.0. It does not introduce private student-only messaging.

## Backward-compatible delivery

M13 does not replace or break M6/M12 notices. When a communication is
published, M13 materializes one `family_notices` row per reached student and
links recipient telemetry through `communication_recipients`.

This keeps the existing Family Portal / Guardian Console notice and
acknowledgement behavior operational while making M13 the structured authoring
and targeting layer for new institutional communications.

A student-specific legacy notice can also remain visible through existing
student notice behavior inherited from M11. M13 does not alter that frozen
policy.

## Tables

M13 adds:

- `communication_templates`
- `communications`
- `communication_targets`
- `communication_recipients`

All four tables use tenant columns, PostgreSQL RLS, `FORCE ROW LEVEL SECURITY`,
and are not owned by the runtime `education_app` role.

## Permissions

M13 adds exactly six permissions:

- `communications.console.access`
- `communications.messages.view`
- `communications.messages.manage`
- `communications.publish`
- `communications.templates.manage`
- `communications.delivery.view`

The permissions are granted to existing institution roles:

- `SYSTEM_ADMIN`
- `RECTOR`
- `ACADEMIC_COORDINATOR`

M13 does not create user memberships and does not auto-assign roles.

## Templates

Templates store reusable title/body/type/acknowledgement defaults. M13 does not
perform AI-generated personalization or variable substitution in this
milestone. This avoids accidental leakage of student-specific information into
bulk messages.

## Delivery status

`communication_recipients` records the resolved guardian/student pair and the
legacy `family_notice_id` used for in-app delivery.

Read and acknowledgement status are derived from the existing
`family_notice_receipts` table instead of duplicating receipt truth.

## Audit

M13 records human staff actions such as:

- `COMMUNICATION_TEMPLATE_CREATED`
- `COMMUNICATION_TEMPLATE_UPDATED`
- `COMMUNICATION_CREATED`
- `COMMUNICATION_UPDATED`
- `COMMUNICATION_TARGETS_REPLACED`
- `COMMUNICATION_PUBLISHED`
- `COMMUNICATION_ARCHIVED`

A successful publication also enqueues `COMMUNICATION_PUBLISHED` in the existing transactional outbox in the same database transaction, preserving the architecture baseline for downstream integrations without introducing an external provider in M13.

## Channels intentionally excluded

v0.13.0 has no SMS, WhatsApp, SMTP, email-provider, push-provider, or external
messaging connector. Those channels require separate provider, consent,
delivery, retry, opt-out and data-protection decisions.

The M13 delivery channel is **in-app only**.

## Privacy / safety

The Communications Center does not expose internal intelligence signals,
automation cases, risk labels or private reasoning to families.

Publication is always a human staff action. M13 does not automatically send
communications because of an AI-generated risk signal.

## Frontend architecture debt

Like M8-M12, M13 uses server-served HTML for the milestone acceptance surface.
The frozen architecture baseline still calls for React + TypeScript + Vite +
Tailwind + shadcn/ui. The unified frontend foundation remains a later
milestone; M13 does not claim that debt is resolved.

## Acceptance gate

The installer is clone-first and requires:

- exact frozen M12 Git base;
- PRIMARY DB at `0014_m12`;
- migration round-trip `0014 → 0015 → 0014 → 0015`;
- Ruff;
- full pytest;
- M7 release gate;
- M8/M9/M10 regressions;
- frozen M11 verifier at native `0013_m11`;
- frozen M12 verifier at native `0014_m12`;
- M13 DB/RBAC/RLS/API/targeting/delivery/audit acceptance;
- real HTTP server;
- real Microsoft Edge browser acceptance;
- PRIMARY migration only after every clone preflight passes;
- pre/post backups and final diff hygiene.

M13 must not be tagged or called frozen until local acceptance, commit/push,
main CI success, annotated tag, and tag CI success are all confirmed.
