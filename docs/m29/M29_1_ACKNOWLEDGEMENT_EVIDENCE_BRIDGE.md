# M29-1 — Family Acknowledgement Evidence Bridge

Status: CLOSED / PASS. Migration `0047_sec_tc1_m29_ack_bridge` is applied and validated on the local test database. The release branch/tag were not changed, and no remote publication occurred.

The reusable security boundary is documented in [SEC-TC1 Trusted Capability Foundation](../security/SEC_TC1_TRUSTED_CAPABILITY_FOUNDATION.md).

## Authority and provenance

M13 remains authoritative for family notices and receipt identity. A guardian acknowledgement is recorded through the M13-owned `m13_acknowledge_family_notice` SEC-TC1 operation. The operation binds the authenticated user to the exact active guardian profile, verifies the published notice and current student grant where applicable, then writes the receipt and a minimized audit entry in one transaction. It emits no new canonical event.

M21 and M27 may link only to a receipt whose notice has a successful, consumed `M13_NOTICE_ACK` capability with `result_id` equal to the receipt, and with matching notice and guardian identifiers. A pre-0047 non-null `acknowledged_at` value alone is not proof. Such a receipt becomes linkable only after an explicit guardian acknowledgement call passes the protected operation. There is no historical backfill.

Consumed M13 acknowledgement capability rows are durable provenance relied on by M21/M27. Do not purge or expire-delete them while links depend on them. There is no runtime cleanup path. Migration downgrade refuses while any capability or evidence rows remain.

## Receipt write boundary

`education_app` retains receipt reads and may insert/update only read-receipt data: INSERT columns exclude `acknowledged_at`, and UPDATE is limited to `read_at`. A SECURITY DEFINER M13 operation writes `acknowledged_at` after rechecking current identity, membership, guardian profile and grant. Evidence links and corrections remain inaccessible by direct runtime table DML.

The ordinary Family Portal and Guardian Console response contracts remain unchanged. Existing route-specific behavior is preserved: Family Portal acknowledgement requires the authenticated active guardian principal; Guardian Console continues its existing `guardian.notices.acknowledge` permission dependency. The database gate validates guardian identity/profile/student grant and does not invent a staff permission requirement.

## Accepted implementation

Migration `0047_sec_tc1_m29_ack_bridge` is the single successor to
`0046_m28_attendance_perms`. It adds the restricted SEC-TC1 capability store,
the four M21/M27 typed append-only link/correction tables, tenant-aware
composite foreign keys, FORCE RLS, bounded permissions, and narrow
security-definer functions. The migration adds no canonical event and no
backfill. Direct `education_app` SELECT/INSERT/UPDATE/DELETE on the new
capability/evidence tables is revoked. On `family_notice_receipts`, the app
retains only column-level INSERT for unacknowledged/read fields and UPDATE of
`read_at`; it cannot write `acknowledged_at`.

The M13 acknowledgement capability is guardian-specific and short-lived.
Consumption revalidates the active user, guardian profile, published notice,
tenant/institution, and current portal grant before writing or returning a
committed result. M21/M27 capabilities revalidate current staff membership,
permission, target scope, receipt provenance, and student/case lineage. M21
and M27 own their evidence services. Link/correction/audit/capability
consumption commit atomically; no follow-up, obligation, intervention, case,
or academic lifecycle is automatically changed.

## Validation and limitations

- Local migration: `0046_m28_attendance_perms` → `0047_sec_tc1_m29_ack_bridge`,
  downgrade to 0046, and re-upgrade to 0047 passed. Exactly one Alembic head
  exists; current is 0047.
- Focused M29/M6/M7 database security set: 29 passed, including concurrent
  acknowledgement/link issuance and consumption, correction/supersession
  races, rollback/retry, lost-response retry, permissions, RLS, direct-DML
  denial, and fixture cleanup.
- Focused unit/contract set: 40 passed.
- Full backend regression: 801 passed, 0 failed, 2 opt-in M21 E2E tests
  skipped because `M21_E2E_DATABASE_URL` was not configured; 144 warnings.
- Changed-file Ruff, `py_compile`, memory validation, architecture check, and
  `git diff --check` passed. The local full-suite fixture tables were empty
  after validation.

Known follow-up: capability rows remain durable provenance and currently have
no scheduled cleanup; do not delete consumed M13 provenance while links
depend on it. Existing direct receipt-read/read-state visibility limitations
remain separate M6 debt. The ordinary HTTP principal path's `is_active`
enforcement is also unchanged; SEC-TC1 protected operations recheck it.

Workflow evidence: three delegated roles were activated (A1, A3, A4), with a
maximum of three active delegates; one implementation agent; no frontend
change. The full-suite impact selector returned `FULL_REQUIRED`. Elapsed time
was not measured by the orchestration harness.

## Rollback warning

The 0047 downgrade restores the pre-migration M6 table-level INSERT/UPDATE/DELETE grant on `family_notice_receipts`. That is the prior, weaker write boundary. Downgrade is blocked while durable capability or evidence rows exist; do not bypass that guard or treat downgrade as routine cleanup.
