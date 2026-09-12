# Education OS — M14 Finance / Billing Core v0.14.0

## Frozen base

- Base tag: `m13-communications-center-v0.13.0`
- Base commit: `73cab587c7901df02b5ead7b3c574f63481770de`
- Database before M14: `0015_m13`
- Database after M14: `0016_m14`

M14 is additive. It does not rewrite frozen M8-M13 application behavior.

## Product scope

M14 introduces a capability-based institutional billing core for student
obligations, payments, allocations, balances and staff-facing statements.

Core flow:

`Concepto → Obligación → Pago → Aplicación → Saldo → Estado de cuenta`

The finance domain remains anchored to the canonical student profile. A billing
account is created lazily for a student only when the first finance operation
requires it.

## Capability model

M14 introduces the existing-platform capability key:

`finance.billing`

Migration defaults:

- `PRIVATE` → enabled
- `FISCOMISIONAL` → enabled
- `PUBLIC` → disabled
- `MUNICIPAL` → disabled

This is a default, not a permanent rule. An authorized `SYSTEM_ADMIN` can
explicitly enable or disable the capability per institution. This allows an
institution type to remain a default signal while capabilities remain the
actual runtime control.

Operational finance endpoints require both:

1. the relevant finance RBAC permission; and
2. `finance.billing = enabled`.

The capability-status endpoint remains available to an authorized finance
console actor even when the capability is disabled so that the UI can explain
why finance operations are unavailable.

## Finance role and permissions

M14 creates one `FINANCE_MANAGER` role per institution and does **not** assign
that role to any user automatically.

Eight permissions are introduced:

- `finance.console.access`
- `finance.summary.view`
- `finance.concepts.manage`
- `finance.charges.manage`
- `finance.payments.manage`
- `finance.statements.view`
- `finance.reversals.manage`
- `finance.capability.manage`

Default grants:

- `SYSTEM_ADMIN`: all 8
- `FINANCE_MANAGER`: all except `finance.capability.manage`
- `RECTOR`: console + summary + statements (read-only finance visibility)

No user membership is created by the migration.

## Tables

M14 adds five tenant-isolated tables:

- `billing_concepts`
- `billing_accounts`
- `billing_charges`
- `billing_payments`
- `billing_allocations`

All five have PostgreSQL RLS and `FORCE ROW LEVEL SECURITY` and are not owned by
the runtime `education_app` role.

## Billing concepts

Concepts provide reusable codes and default amounts, for example tuition,
enrollment or transport. M14 uses `USD` only.

Concepts can be archived but are not physically deleted through the M14 API.

## Charges

A charge records:

- student billing account
- billing concept
- optional academic period
- description
- amount
- due date
- lifecycle status

Statuses:

- `OPEN`
- `PARTIAL`
- `PAID`
- `VOID`

Charge state is derived/recalculated from posted payment allocations.

## Payments and allocations

A posted payment must be fully allocated to one or more charges belonging to
the same student billing account.

M14 deliberately requires:

`payment amount == sum(payment allocations)`

This avoids hidden/unapplied credits in the first billing core.

Supported recorded methods:

- `CASH`
- `BANK_TRANSFER`
- `CARD`
- `OTHER`

`CARD` means the institution records a card payment that has already occurred.
M14 does not process a card transaction.

## Reversals

Financial history is not deleted through the API.

A payment is reversed by changing it to `VOID`; its allocations remain as
historical records but are excluded from active balance calculations.

A charge can be voided only while it has no posted payment allocation.

Both payment and charge void operations require:

- `finance.reversals.manage`
- a textual reason
- audit logging
- transactional outbox event

## Statements and balances

M14 provides staff-facing student statements containing:

- billed total
- paid total
- outstanding balance
- charge history
- payment history

Family/Guardian self-service financial statements are intentionally deferred.
M14 does not change the frozen M12 Guardian Console privacy boundary.

## Audit and transactional outbox

Human financial actions are audited. Money-state and capability changes also
emit transactional outbox events in the same database transaction, including:

- `FINANCE_CAPABILITY_CHANGED`
- `BILLING_CHARGE_CREATED`
- `BILLING_PAYMENT_POSTED`
- `BILLING_PAYMENT_VOIDED`
- `BILLING_CHARGE_VOIDED`

## Deliberate exclusions

M14 is a billing core, not a statutory accounting or payment-gateway product.

It does **not** provide:

- Ecuador SRI electronic invoicing
- tax invoices / tax authorization
- accounting ledger / journal entries
- bank synchronization
- payment-gateway execution
- card acquiring
- PayPal / Stripe / Datafast integration
- external refunds
- automatic late fees or interest
- automated punitive action for unpaid balances
- AI-driven financial decisions

Those concerns require independent legal, accounting, consent, provider and
operational acceptance milestones.

## Privacy and safety

The finance surface does not expose student intelligence signals, automation
cases or risk labels.

M14 does not automatically create charges from academic or behavioral signals.

## Frontend architecture debt

M14 retains the milestone pattern of server-served HTML for operational
acceptance. The architecture baseline still calls for React + TypeScript +
Vite + Tailwind + shadcn/ui. M14 does not claim that debt is resolved.

## Acceptance gate

The installer requires:

- exact frozen M13 source/tag;
- PRIMARY database at `0015_m13`;
- clone migration round-trip `0015 → 0016 → 0015 → 0016`;
- Ruff;
- full pytest;
- M7 release gate;
- M8/M9/M10 regression;
- frozen M11 verifier at native `0013_m11`;
- frozen M12 verifier at native `0014_m12`;
- frozen M13 verifier at native `0015_m13`;
- M14 capability/RBAC/RLS/accounting/reversal/outbox verifier;
- actual HTTP server;
- actual Microsoft Edge browser;
- pre/post database backups;
- PRIMARY migration only after all clone preflights pass;
- no billing data automatically seeded in PRIMARY;
- no automatic `FINANCE_MANAGER` membership assignment.

M14 is not formally frozen until local acceptance, commit/push, main CI,
annotated tag and tag CI all succeed.
