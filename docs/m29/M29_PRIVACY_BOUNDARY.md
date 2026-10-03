# M29 privacy boundary — minors and family continuity

Status: M29-0 contract. Existing route/data behavior is summarized from code,
migrations and tests; any extension is proposed and not implemented.

## Current authorization evidence

- Guardian authentication resolves an active `GuardianProfile` (ADR 0026).
- Digital access is distinct from family relationship. M6
  `guardian_student_portal_access` is an explicit grant; bootstrap is bounded
  to legal guardian/primary contact and later grants/revocations are explicit
  and auditable (ADR 0027, migration `0007_m6_family_portal.py`).
- Family routes use `GuardianPrincipalDep`; per-student service queries require
  active portal access. M6 RLS tests and M12 access/privacy tests cover scope
  and non-disclosure. Revocation must take effect on subsequent requests.
- Teacher routes use teacher principal plus active assignment and permission;
  SYSTEM_ADMIN/guardian membership does not substitute for domain permission.
- M13 resolves communication recipients using active portal grants and
  delivers in-app family notices. Publication is a human staff action.

## Visibility classes

| Evidence class | Default permitted audience | Contract constraint |
|---|---|---|
| Institutional/internal operational evidence | Authorized institutional staff by domain permission | Not automatically family-visible. |
| Teacher-visible evidence | Assigned teacher for current/effective assignment scope | Reauthorize assignment; do not expose another class/student. |
| Student-visible evidence | Authenticated student's own permitted console views | Does not imply guardian access. |
| Guardian-visible evidence | Only curated M6/M12/M13 fields for a student with active explicit grant | Never infer from contact relation; minimize by purpose. |
| Coordination-only evidence | Explicit coordination permissions and institution scope | No automatic forwarding to guardians. |
| Rector-only/aggregate intelligence | M22/M26/M27 permissions and aggregation policy | No wholesale M22 snapshots or raw cohort/risk evidence to families. |
| Restricted intervention evidence | M21 sensitivity + explicit restricted/confidential permission | No timeline export or communication copy-through. |
| AI/Mentor evidence | M23/M25/M26 minimized authorized evidence boundary | L0 explanation only; no hidden reasoning, raw prompts, autonomous dispatch or authority. |

## M29 privacy rules

1. Family endpoints remain curated. Never expose Student Timeline wholesale or
   institutional intelligence wholesale.
2. No free-text teacher notes, intervention follow-up notes, restricted
   observations or M27 review/decision rationale are copied into family
   messages by default.
3. Results/attendance may be shown only under existing family endpoint
   permissions and current grant. Publication/notification semantics do not
   broaden data visibility.
4. A communication should carry only minimum necessary content and opaque
   source references; source identifiers must be reauthorized at read time.
5. Audit/outbox/delivery telemetry store bounded metadata, not message body,
   sensitive note, provider internals or unnecessary student identifiers.
   Existing M28 result audit explicitly excludes free-text feedback.
6. Relationship revocation, account deactivation, tenant changes and staff
   assignment revocation must invalidate pending access/action; cached UI or
   prior receipt is not authorization.
7. Guardian response, if proposed, needs identity proof, active grant,
   student/recipient linkage, input minimization, retention rules and staff
   routing before implementation.

## Unresolved policy questions

Repository evidence does not establish complete consent/contact-preference,
retention, age/assent, guardian dispute, multi-guardian delivery, response
moderation or notification opt-out policy for every channel. Resolve these
with product/privacy owners before external channels or new family response
flows. M13 supports in-app delivery only; SMS, email, WhatsApp and push are not
implemented in its release contract.
