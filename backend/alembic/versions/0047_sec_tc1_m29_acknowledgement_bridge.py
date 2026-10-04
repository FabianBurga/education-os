"""SEC-TC1 capability gate and M29-1 acknowledgement evidence links.

Revision ID: 0047_sec_tc1_m29_ack_bridge
Revises: 0046_m28_attendance_perms
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "0047_sec_tc1_m29_ack_bridge"
down_revision: str | None = "0046_m28_attendance_perms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTIONS = (
    "sec_tc1_issue_capability(text,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text)",
    "m21_link_acknowledgement_evidence(text)",
    "m21_correct_acknowledgement_evidence(text)",
    "m21_read_acknowledgement_evidence(text)",
    "m27_link_acknowledgement_evidence(text)",
    "m27_correct_acknowledgement_evidence(text)",
    "m27_read_acknowledgement_evidence(text)",
    "m13_acknowledge_family_notice(text)",
    "sec_tc1_validate_capability(text,text)",
    "sec_tc1_reject_history_mutation()",
)

_ROW_LOCK_TABLES = (
    ("user_accounts", "sec_tc1_lock_1"),
    ("guardian_profiles", "sec_tc1_lock_2"),
    ("guardian_student_portal_access", "sec_tc1_lock_3"),
    ("family_notices", "sec_tc1_lock_4"),
    ("intervention_followups", "sec_tc1_lock_5"),
    ("accountability_obligations", "sec_tc1_lock_6"),
)
_ROW_LOCK_EVIDENCE_TABLES = (
    "intervention_followup_acknowledgement_evidence_links",
    "accountability_obligation_acknowledgement_evidence_links",
)


def _require_roles(bind: sa.Connection) -> None:
    rows = bind.execute(sa.text("""
        SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,
               rolinherit, rolbypassrls
        FROM pg_catalog.pg_roles
        WHERE rolname IN ('education_context_issuer', 'education_context_function_owner')
    """)).all()
    attrs = {row[0]: tuple(row[1:]) for row in rows}
    expected = {
        "education_context_issuer": (True, False, False, False, False, False),
        "education_context_function_owner": (False, False, False, False, False, False),
    }
    for role, values in expected.items():
        if attrs.get(role) != values:
            raise RuntimeError(
                f"SEC-TC1 requires provisioned role {role} with exact attributes {values}; "
                "run scripts/provision_sec_tc1_roles.py before upgrading."
            )
        memberships = bind.execute(sa.text("""
            SELECT count(*) FROM pg_catalog.pg_auth_members am
            JOIN pg_catalog.pg_roles granted ON granted.oid = am.roleid
            JOIN pg_catalog.pg_roles member ON member.oid = am.member
            WHERE granted.rolname = :role OR member.rolname = :role
        """), {"role": role}).scalar_one()
        if memberships:
            raise RuntimeError(f"SEC-TC1 role {role} has role memberships; remove them before upgrading")


def upgrade() -> None:
    bind = op.get_bind()
    _require_roles(bind)

    permissions = (
        ("intervention.followup.acknowledgement_evidence.manage", "Manage bounded family acknowledgement evidence links for M21 follow-ups.", ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR")),
        ("accountability.obligation.acknowledgement_evidence.manage", "Manage bounded family acknowledgement evidence links for M27 obligations.", ("RECTOR", "ACADEMIC_COORDINATOR")),
    )
    permission_ids: dict[str, object] = {}
    for key, description, role_keys in permissions:
        permission_id = bind.execute(sa.text("SELECT id FROM permissions WHERE key=:key"), {"key": key}).scalar_one_or_none()
        if permission_id is not None:
            raise RuntimeError(f"SEC-TC1 permission {key} already exists; refusing ambiguous migration ownership")
        permission_id = uuid4()
        bind.execute(sa.text("INSERT INTO permissions (id,key,description) VALUES (:id,:key,:description)"), {"id": permission_id, "key": key, "description": description})
        permission_ids[key] = permission_id
        role_rows = bind.execute(sa.text("SELECT id FROM roles WHERE key=ANY(CAST(:keys AS text[]))"), {"keys": list(role_keys)}).scalars()
        for role_id in role_rows:
            bind.execute(sa.text("INSERT INTO role_permissions(role_id,permission_id) VALUES(:role_id,:permission_id) ON CONFLICT DO NOTHING"), {"role_id": role_id, "permission_id": permission_id})

    for table in ("family_notice_receipts", "intervention_followups", "accountability_obligations"):
        bind.execute(sa.text(f'ALTER TABLE public."{table}" ADD CONSTRAINT "uq_{table}_tenant_id" UNIQUE (institution_id, organization_id, id)'))

    op.create_table(
        "sec_tc1_capabilities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("capability_value", sa.String(80), nullable=False, unique=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(48), nullable=False),
        sa.Column("operation_key", sa.String(64), nullable=False),
        sa.Column("operation_fingerprint", sa.String(64), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=True),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("guardian_profile_id", sa.Uuid(), nullable=True),
        sa.Column("related_link_id", sa.Uuid(), nullable=True),
        sa.Column("replacement_target_id", sa.Uuid(), nullable=True),
        sa.Column("reason_code", sa.String(48), nullable=True),
        sa.Column("result_id", sa.Uuid(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("clock_timestamp()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("actor_user_id", "purpose", "operation_key", name="uq_sec_tc1_operation"),
        sa.CheckConstraint("operation_key ~ '^[0-9a-f]{64}$' AND operation_fingerprint ~ '^[0-9a-f]{64}$'", name="ck_sec_tc1_operation_hashes"),
        sa.CheckConstraint("purpose IN ('M13_NOTICE_ACK','M21_ACK_LINK','M21_ACK_CORRECT','M21_ACK_READ','M27_ACK_LINK','M27_ACK_CORRECT','M27_ACK_READ')", name="ck_sec_tc1_purpose"),
        sa.CheckConstraint("reason_code IS NULL OR reason_code IN ('WRONG_CONTEXT','DUPLICATE_ASSOCIATION','ACKNOWLEDGEMENT_NOT_RELEVANT')", name="ck_sec_tc1_reason"),
    )
    op.create_index("ix_sec_tc1_capabilities_expiry", "sec_tc1_capabilities", ["expires_at"])

    op.create_table(
        "intervention_followup_acknowledgement_evidence_links",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False), sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.Column("followup_id", sa.Uuid(), nullable=False), sa.Column("linked_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("clock_timestamp()")),
        sa.Column("generation", sa.Integer(), nullable=False), sa.Column("operation_key", sa.String(64), nullable=False),
        sa.UniqueConstraint("institution_id", "organization_id", "id", name="uq_m21_ack_link_tenant_id"),
        sa.UniqueConstraint("receipt_id", "followup_id", "generation", name="uq_m21_ack_link_generation"),
        sa.UniqueConstraint("linked_by_user_id", "operation_key", name="uq_m21_ack_link_operation"),
        sa.ForeignKeyConstraint(["institution_id", "organization_id", "receipt_id"], ["family_notice_receipts.institution_id", "family_notice_receipts.organization_id", "family_notice_receipts.id"], name="fk_m21_ack_link_receipt", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["institution_id", "organization_id", "followup_id"], ["intervention_followups.institution_id", "intervention_followups.organization_id", "intervention_followups.id"], name="fk_m21_ack_link_followup", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["linked_by_user_id"], ["user_accounts.id"], name="fk_m21_ack_link_actor", ondelete="RESTRICT"),
        sa.CheckConstraint("generation >= 1 AND operation_key ~ '^[0-9a-f]{64}$'", name="ck_m21_ack_link_generation"),
    )
    op.create_table(
        "intervention_followup_acknowledgement_evidence_corrections",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False), sa.Column("original_link_id", sa.Uuid(), nullable=False),
        sa.Column("replacement_link_id", sa.Uuid(), nullable=True), sa.Column("corrected_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("reason_code", sa.String(48), nullable=False), sa.Column("operation_key", sa.String(64), nullable=False),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("clock_timestamp()")),
        sa.UniqueConstraint("original_link_id", name="uq_m21_ack_correction_original"), sa.UniqueConstraint("corrected_by_user_id", "operation_key", name="uq_m21_ack_correction_operation"),
        sa.ForeignKeyConstraint(["institution_id", "organization_id", "original_link_id"], ["intervention_followup_acknowledgement_evidence_links.institution_id", "intervention_followup_acknowledgement_evidence_links.organization_id", "intervention_followup_acknowledgement_evidence_links.id"], name="fk_m21_ack_correction_original", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["institution_id", "organization_id", "replacement_link_id"], ["intervention_followup_acknowledgement_evidence_links.institution_id", "intervention_followup_acknowledgement_evidence_links.organization_id", "intervention_followup_acknowledgement_evidence_links.id"], name="fk_m21_ack_correction_replacement", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["corrected_by_user_id"], ["user_accounts.id"], name="fk_m21_ack_correction_actor", ondelete="RESTRICT"),
        sa.CheckConstraint("reason_code IN ('WRONG_CONTEXT','DUPLICATE_ASSOCIATION','ACKNOWLEDGEMENT_NOT_RELEVANT') AND operation_key ~ '^[0-9a-f]{64}$'", name="ck_m21_ack_correction_reason"),
        sa.CheckConstraint("replacement_link_id IS NULL OR replacement_link_id <> original_link_id", name="ck_m21_ack_correction_not_self"),
    )
    op.create_table(
        "accountability_obligation_acknowledgement_evidence_links",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False), sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.Column("obligation_id", sa.Uuid(), nullable=False), sa.Column("linked_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("clock_timestamp()")),
        sa.Column("generation", sa.Integer(), nullable=False), sa.Column("operation_key", sa.String(64), nullable=False),
        sa.UniqueConstraint("institution_id", "organization_id", "id", name="uq_m27_ack_link_tenant_id"),
        sa.UniqueConstraint("receipt_id", "obligation_id", "generation", name="uq_m27_ack_link_generation"),
        sa.UniqueConstraint("linked_by_user_id", "operation_key", name="uq_m27_ack_link_operation"),
        sa.ForeignKeyConstraint(["institution_id", "organization_id", "receipt_id"], ["family_notice_receipts.institution_id", "family_notice_receipts.organization_id", "family_notice_receipts.id"], name="fk_m27_ack_link_receipt", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["institution_id", "organization_id", "obligation_id"], ["accountability_obligations.institution_id", "accountability_obligations.organization_id", "accountability_obligations.id"], name="fk_m27_ack_link_obligation", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["linked_by_user_id"], ["user_accounts.id"], name="fk_m27_ack_link_actor", ondelete="RESTRICT"),
        sa.CheckConstraint("generation >= 1 AND operation_key ~ '^[0-9a-f]{64}$'", name="ck_m27_ack_link_generation"),
    )
    op.create_table(
        "accountability_obligation_acknowledgement_evidence_corrections",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("institution_id", sa.Uuid(), nullable=False), sa.Column("original_link_id", sa.Uuid(), nullable=False),
        sa.Column("replacement_link_id", sa.Uuid(), nullable=True), sa.Column("corrected_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("reason_code", sa.String(48), nullable=False), sa.Column("operation_key", sa.String(64), nullable=False),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("clock_timestamp()")),
        sa.UniqueConstraint("original_link_id", name="uq_m27_ack_correction_original"), sa.UniqueConstraint("corrected_by_user_id", "operation_key", name="uq_m27_ack_correction_operation"),
        sa.ForeignKeyConstraint(["institution_id", "organization_id", "original_link_id"], ["accountability_obligation_acknowledgement_evidence_links.institution_id", "accountability_obligation_acknowledgement_evidence_links.organization_id", "accountability_obligation_acknowledgement_evidence_links.id"], name="fk_m27_ack_correction_original", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["institution_id", "organization_id", "replacement_link_id"], ["accountability_obligation_acknowledgement_evidence_links.institution_id", "accountability_obligation_acknowledgement_evidence_links.organization_id", "accountability_obligation_acknowledgement_evidence_links.id"], name="fk_m27_ack_correction_replacement", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["corrected_by_user_id"], ["user_accounts.id"], name="fk_m27_ack_correction_actor", ondelete="RESTRICT"),
        sa.CheckConstraint("reason_code IN ('WRONG_CONTEXT','DUPLICATE_ASSOCIATION','ACKNOWLEDGEMENT_NOT_RELEVANT') AND operation_key ~ '^[0-9a-f]{64}$'", name="ck_m27_ack_correction_reason"),
        sa.CheckConstraint("replacement_link_id IS NULL OR replacement_link_id <> original_link_id", name="ck_m27_ack_correction_not_self"),
    )

    for table in (
        "sec_tc1_capabilities", "intervention_followup_acknowledgement_evidence_links",
        "intervention_followup_acknowledgement_evidence_corrections",
        "accountability_obligation_acknowledgement_evidence_links",
        "accountability_obligation_acknowledgement_evidence_corrections",
    ):
        op.execute(sa.text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE public."{table}" FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM PUBLIC, education_app, education_context_issuer'))
        if table == "sec_tc1_capabilities":
            op.execute(sa.text(f'GRANT SELECT, INSERT, UPDATE ON TABLE public."{table}" TO education_context_function_owner'))
        else:
            op.execute(sa.text(f'GRANT SELECT, INSERT ON TABLE public."{table}" TO education_context_function_owner'))
        op.execute(sa.text(f'CREATE POLICY "{table}_function_owner" ON public."{table}" TO education_context_function_owner USING (true) WITH CHECK (true)'))

    # SEC-TC1 owner can inspect only the authoritative rows needed by the gate.
    for table in ("user_accounts", "institutions", "memberships", "membership_roles", "roles", "role_permissions", "permissions", "family_notice_receipts", "guardian_profiles", "guardian_student_portal_access", "staff_profiles", "teaching_assignments", "course_offerings", "student_section_assignments", "enrollments", "intervention_followups", "interventions", "accountability_obligations", "accountability_cases"):
        op.execute(sa.text(f'GRANT SELECT ON TABLE public."{table}" TO education_context_function_owner'))
        op.execute(sa.text(f'CREATE POLICY "{table}_sec_tc1_read" ON public."{table}" FOR SELECT TO education_context_function_owner USING (true)'))
    op.execute("GRANT SELECT (id, organization_id, institution_id, status, student_profile_id) ON TABLE public.family_notices TO education_context_function_owner")
    op.execute("CREATE POLICY family_notices_sec_tc1_read ON public.family_notices FOR SELECT TO education_context_function_owner USING (true)")
    # PostgreSQL requires UPDATE privilege and an UPDATE policy for row-locking
    # SELECTs. The restricted function owner receives only UPDATE(id); the
    # trusted function bodies use these rights to lock rows, not mutate them.
    for table, policy in _ROW_LOCK_TABLES:
        op.execute(sa.text(f'GRANT UPDATE (id) ON TABLE public."{table}" TO education_context_function_owner'))
        op.execute(sa.text(f'CREATE POLICY "{policy}" ON public."{table}" FOR UPDATE TO education_context_function_owner USING (true) WITH CHECK (true)'))
    for table in _ROW_LOCK_EVIDENCE_TABLES:
        # These tables already have the function-owner ALL policy; append-only
        # triggers reject any actual UPDATE while this grant permits row locks.
        op.execute(sa.text(f'GRANT UPDATE (id) ON TABLE public."{table}" TO education_context_function_owner'))
    op.execute('GRANT INSERT ON TABLE public.audit_logs TO education_context_function_owner')
    op.execute('CREATE POLICY audit_logs_sec_tc1_insert ON public.audit_logs FOR INSERT TO education_context_function_owner WITH CHECK (true)')

    # Guardian acknowledgement is a database-validated M13 mutation. Runtime
    # list views retain only read_at receipt writes; acknowledged_at is never
    # directly writable by education_app.
    op.execute("REVOKE INSERT, UPDATE, DELETE ON TABLE public.family_notice_receipts FROM education_app")
    op.execute("GRANT INSERT (id, organization_id, institution_id, family_notice_id, guardian_profile_id, read_at) ON TABLE public.family_notice_receipts TO education_app")
    op.execute("GRANT UPDATE (read_at) ON TABLE public.family_notice_receipts TO education_app")
    op.execute("GRANT INSERT (id, organization_id, institution_id, family_notice_id, guardian_profile_id, read_at, acknowledged_at) ON TABLE public.family_notice_receipts TO education_context_function_owner")
    op.execute("GRANT UPDATE (read_at, acknowledged_at) ON TABLE public.family_notice_receipts TO education_context_function_owner")
    op.execute("CREATE POLICY family_notice_receipts_tc1_insert ON public.family_notice_receipts FOR INSERT TO education_context_function_owner WITH CHECK (true)")
    op.execute("CREATE POLICY family_notice_receipts_tc1_update ON public.family_notice_receipts FOR UPDATE TO education_context_function_owner USING (true) WITH CHECK (true)")

    # This migration intentionally contains no secret. Provisioning must be
    # performed first with scripts/provision_sec_tc1_roles.py.
    op.execute("GRANT USAGE ON SCHEMA public TO education_context_issuer, education_context_function_owner")
    op.execute("GRANT CONNECT ON DATABASE education_os TO education_context_issuer")
    op.execute(r"""
        CREATE FUNCTION public.sec_tc1_issue_capability(
            p_purpose text, p_actor uuid, p_org uuid, p_inst uuid,
            p_receipt uuid, p_target uuid, p_guardian_profile uuid, p_related_link uuid,
            p_replacement_target uuid, p_reason text,
            p_operation_key text, p_fingerprint text
        ) RETURNS text LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $f$
        DECLARE v_token text; v_student uuid; v_perm text; v_read boolean;
        BEGIN
            IF session_user <> 'education_context_issuer' THEN
                RAISE EXCEPTION 'SEC-TC1 issuer role required' USING ERRCODE='42501';
            END IF;
            IF p_purpose NOT IN ('M13_NOTICE_ACK','M21_ACK_LINK','M21_ACK_CORRECT','M21_ACK_READ','M27_ACK_LINK','M27_ACK_CORRECT','M27_ACK_READ')
               OR p_operation_key !~ '^[0-9a-f]{64}$' OR p_fingerprint !~ '^[0-9a-f]{64}$'
               OR p_actor IS NULL OR p_org IS NULL OR p_inst IS NULL OR p_target IS NULL THEN
                RAISE EXCEPTION 'SEC-TC1 invalid bounded operation' USING ERRCODE='22023';
            END IF;
            IF p_reason IS NOT NULL AND p_reason NOT IN ('WRONG_CONTEXT','DUPLICATE_ASSOCIATION','ACKNOWLEDGEMENT_NOT_RELEVANT') THEN
                RAISE EXCEPTION 'SEC-TC1 invalid reason code' USING ERRCODE='22023';
            END IF;
            PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(p_actor::text || ':' || p_purpose || ':' || p_operation_key, 0));
            IF p_purpose='M13_NOTICE_ACK' THEN
                IF p_receipt IS NOT NULL OR p_guardian_profile IS NULL OR p_related_link IS NOT NULL OR p_replacement_target IS NOT NULL OR p_reason IS NOT NULL THEN
                    RAISE EXCEPTION 'SEC-TC1 invalid M13 acknowledgement binding' USING ERRCODE='22023';
                END IF;
                SELECT n.student_profile_id INTO v_student FROM public.family_notices n
                WHERE n.id=p_target AND n.organization_id=p_org AND n.institution_id=p_inst AND n.status='PUBLISHED';
                IF NOT FOUND OR NOT EXISTS (
                    SELECT 1 FROM public.guardian_profiles gp JOIN public.user_accounts u ON u.person_id=gp.person_id
                    JOIN public.institutions i ON i.id=gp.institution_id AND i.organization_id=gp.organization_id
                    WHERE gp.id=p_guardian_profile AND gp.organization_id=p_org AND gp.institution_id=p_inst
                      AND gp.status='ACTIVE' AND u.id=p_actor AND u.is_active=true AND i.status='ACTIVE'
                ) THEN RAISE EXCEPTION 'SEC-TC1 guardian notice unavailable' USING ERRCODE='42501'; END IF;
                IF v_student IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM public.guardian_profiles gp JOIN public.user_accounts u ON u.person_id=gp.person_id
                    JOIN public.guardian_student_portal_access g ON g.guardian_profile_id=gp.id AND g.student_profile_id=v_student
                    WHERE gp.id=p_guardian_profile AND gp.institution_id=p_inst AND gp.status='ACTIVE' AND u.id=p_actor AND u.is_active=true
                      AND g.organization_id=p_org AND g.institution_id=p_inst AND g.status='ACTIVE'
                ) THEN RAISE EXCEPTION 'SEC-TC1 guardian student scope unavailable' USING ERRCODE='42501'; END IF;
            ELSE
                IF NOT EXISTS (
                    SELECT 1 FROM public.user_accounts u
                    JOIN public.memberships m ON m.user_id=u.id AND m.institution_id=p_inst AND m.status='ACTIVE'
                    JOIN public.institutions i ON i.id=m.institution_id AND i.organization_id=p_org AND i.status='ACTIVE'
                    WHERE u.id=p_actor AND u.is_active=true
                ) THEN RAISE EXCEPTION 'SEC-TC1 actor scope is inactive' USING ERRCODE='42501'; END IF;
                IF p_receipt IS NULL OR p_guardian_profile IS NOT NULL THEN RAISE EXCEPTION 'SEC-TC1 receipt required' USING ERRCODE='22023'; END IF;
                SELECT n.student_profile_id INTO v_student
                FROM public.family_notice_receipts r
                JOIN public.family_notices n ON n.id=r.family_notice_id
                WHERE r.id=p_receipt AND r.organization_id=p_org AND r.institution_id=p_inst
                  AND r.acknowledged_at IS NOT NULL AND n.organization_id=p_org AND n.institution_id=p_inst
                  AND EXISTS (SELECT 1 FROM public.sec_tc1_capabilities ack WHERE ack.purpose='M13_NOTICE_ACK'
                    AND ack.result_id=r.id AND ack.target_id=n.id AND ack.guardian_profile_id=r.guardian_profile_id
                    AND ack.organization_id=r.organization_id AND ack.institution_id=r.institution_id AND ack.consumed_at IS NOT NULL);
                IF NOT FOUND THEN RAISE EXCEPTION 'SEC-TC1 acknowledged receipt unavailable' USING ERRCODE='42501'; END IF;
            END IF;

            v_read := p_purpose IN ('M21_ACK_READ','M27_ACK_READ');
            IF p_purpose='M13_NOTICE_ACK' THEN
                NULL; -- Guardian authorization is profile/grant based, not staff permission based.
            ELSIF left(p_purpose,3)='M21' THEN
                v_perm := CASE WHEN v_read THEN 'intervention.read' ELSE 'intervention.followup.acknowledgement_evidence.manage' END;
                IF NOT EXISTS (
                    SELECT 1 FROM public.intervention_followups f
                    JOIN public.interventions iv ON iv.id=f.intervention_id
                    WHERE f.id=p_target AND f.organization_id=p_org AND f.institution_id=p_inst
                      AND iv.organization_id=p_org AND iv.institution_id=p_inst
                      AND v_student IS NOT NULL AND iv.student_profile_id=v_student
                      AND EXISTS (SELECT 1 FROM public.guardian_student_portal_access g WHERE g.guardian_profile_id=(SELECT r.guardian_profile_id FROM public.family_notice_receipts r WHERE r.id=p_receipt) AND g.student_profile_id=v_student AND g.organization_id=p_org AND g.institution_id=p_inst AND g.status='ACTIVE')
                ) THEN RAISE EXCEPTION 'SEC-TC1 M21 target unavailable' USING ERRCODE='42501'; END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM public.memberships m JOIN public.membership_roles mr ON mr.membership_id=m.id
                    JOIN public.role_permissions rp ON rp.role_id=mr.role_id JOIN public.permissions p ON p.id=rp.permission_id
                    WHERE m.user_id=p_actor AND m.institution_id=p_inst AND m.status='ACTIVE' AND p.key='communications.delivery.view'
                ) OR NOT EXISTS (
                    SELECT 1 FROM public.memberships m JOIN public.membership_roles mr ON mr.membership_id=m.id
                    JOIN public.role_permissions rp ON rp.role_id=mr.role_id JOIN public.permissions p ON p.id=rp.permission_id
                    WHERE m.user_id=p_actor AND m.institution_id=p_inst AND m.status='ACTIVE' AND p.key=v_perm
                ) THEN RAISE EXCEPTION 'SEC-TC1 M21 permission denied' USING ERRCODE='42501'; END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM public.memberships m JOIN public.membership_roles mr ON mr.membership_id=m.id JOIN public.roles r ON r.id=mr.role_id
                    WHERE m.user_id=p_actor AND m.institution_id=p_inst AND m.status='ACTIVE'
                      AND r.institution_id=p_inst AND r.key IN ('SYSTEM_ADMIN','RECTOR','ACADEMIC_COORDINATOR')
                ) AND NOT EXISTS (
                    SELECT 1 FROM public.user_accounts u JOIN public.staff_profiles sp ON sp.person_id=u.person_id AND sp.institution_id=p_inst AND sp.status='ACTIVE'
                    JOIN public.teaching_assignments ta ON ta.staff_profile_id=sp.id AND ta.institution_id=p_inst
                    JOIN public.course_offerings co ON co.id=ta.course_offering_id AND co.institution_id=p_inst AND co.status='ACTIVE'
                    JOIN public.student_section_assignments ssa ON ssa.section_id=co.section_id AND ssa.institution_id=p_inst AND ssa.status='ACTIVE'
                    JOIN public.enrollments e ON e.id=ssa.enrollment_id AND e.institution_id=p_inst
                    WHERE u.id=p_actor AND u.is_active AND e.student_profile_id=v_student
                      AND (ta.starts_on IS NULL OR ta.starts_on<=CURRENT_DATE) AND (ta.ends_on IS NULL OR ta.ends_on>=CURRENT_DATE)
                ) THEN RAISE EXCEPTION 'SEC-TC1 M21 target scope denied' USING ERRCODE='42501'; END IF;
            ELSE
                v_perm := CASE WHEN v_read THEN 'accountability.view' ELSE 'accountability.obligation.acknowledgement_evidence.manage' END;
                IF NOT EXISTS (
                    SELECT 1 FROM public.accountability_obligations o
                    JOIN public.accountability_cases c ON c.id=o.case_id
                    WHERE o.id=p_target AND o.organization_id=p_org AND o.institution_id=p_inst
                      AND c.organization_id=p_org AND c.institution_id=p_inst
                      AND ((c.subject_type = 'STUDENT' AND v_student IS NOT NULL AND c.subject_id=v_student
                            AND EXISTS (SELECT 1 FROM public.guardian_student_portal_access g JOIN public.family_notice_receipts r ON r.guardian_profile_id=g.guardian_profile_id WHERE r.id=p_receipt AND g.student_profile_id=v_student AND g.organization_id=p_org AND g.institution_id=p_inst AND g.status='ACTIVE'))
                           OR (c.subject_type <> 'STUDENT' AND v_student IS NULL))
                ) THEN RAISE EXCEPTION 'SEC-TC1 M27 target unavailable' USING ERRCODE='42501'; END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM public.memberships m JOIN public.membership_roles mr ON mr.membership_id=m.id
                    JOIN public.role_permissions rp ON rp.role_id=mr.role_id JOIN public.permissions p ON p.id=rp.permission_id
                    WHERE m.user_id=p_actor AND m.institution_id=p_inst AND m.status='ACTIVE' AND p.key='communications.delivery.view'
                ) OR NOT EXISTS (
                    SELECT 1 FROM public.memberships m JOIN public.membership_roles mr ON mr.membership_id=m.id
                    JOIN public.role_permissions rp ON rp.role_id=mr.role_id JOIN public.permissions p ON p.id=rp.permission_id
                    WHERE m.user_id=p_actor AND m.institution_id=p_inst AND m.status='ACTIVE' AND p.key=v_perm
                ) THEN RAISE EXCEPTION 'SEC-TC1 M27 permission denied' USING ERRCODE='42501'; END IF;
            END IF;
            IF p_purpose LIKE '%CORRECT' AND (p_related_link IS NULL OR p_reason IS NULL) THEN
                RAISE EXCEPTION 'SEC-TC1 correction requires original link and reason' USING ERRCODE='22023';
            END IF;

            PERFORM 1 FROM public.sec_tc1_capabilities c
            WHERE c.actor_user_id=p_actor AND c.purpose=p_purpose AND c.operation_key=p_operation_key
            FOR UPDATE;
            IF FOUND THEN
                IF NOT EXISTS (SELECT 1 FROM public.sec_tc1_capabilities c WHERE c.actor_user_id=p_actor AND c.purpose=p_purpose AND c.operation_key=p_operation_key AND c.operation_fingerprint=p_fingerprint AND c.organization_id=p_org AND c.institution_id=p_inst AND c.receipt_id IS NOT DISTINCT FROM p_receipt AND c.target_id=p_target AND c.guardian_profile_id IS NOT DISTINCT FROM p_guardian_profile AND c.related_link_id IS NOT DISTINCT FROM p_related_link AND c.replacement_target_id IS NOT DISTINCT FROM p_replacement_target AND c.reason_code IS NOT DISTINCT FROM p_reason) THEN
                    RAISE EXCEPTION 'SEC-TC1 idempotency conflict' USING ERRCODE='23505';
                END IF;
                SELECT c.capability_value INTO v_token FROM public.sec_tc1_capabilities c
                WHERE c.actor_user_id=p_actor AND c.purpose=p_purpose AND c.operation_key=p_operation_key
                  AND c.expires_at>clock_timestamp()
                  AND (c.consumed_at IS NULL OR (c.result_id IS NOT NULL AND p_purpose NOT IN ('M21_ACK_READ','M27_ACK_READ')));
                IF FOUND THEN RETURN v_token; END IF;
                v_token := pg_catalog.gen_random_uuid()::text || pg_catalog.gen_random_uuid()::text;
                UPDATE public.sec_tc1_capabilities SET capability_value=v_token, issued_at=clock_timestamp(), expires_at=clock_timestamp()+interval '60 seconds', consumed_at=NULL
                WHERE actor_user_id=p_actor AND purpose=p_purpose AND operation_key=p_operation_key;
                RETURN v_token;
            END IF;
            v_token := pg_catalog.gen_random_uuid()::text || pg_catalog.gen_random_uuid()::text;
            INSERT INTO public.sec_tc1_capabilities(id, capability_value, actor_user_id, organization_id, institution_id, purpose, operation_key, operation_fingerprint, receipt_id, target_id, guardian_profile_id, related_link_id, replacement_target_id, reason_code, expires_at)
            VALUES (pg_catalog.gen_random_uuid(),v_token,p_actor,p_org,p_inst,p_purpose,p_operation_key,p_fingerprint,p_receipt,p_target,p_guardian_profile,p_related_link,p_replacement_target,p_reason,clock_timestamp()+interval '60 seconds');
            RETURN v_token;
        END $f$
    """)
    op.execute("ALTER FUNCTION public.sec_tc1_issue_capability(text,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text) OWNER TO education_context_function_owner")
    op.execute("REVOKE ALL ON FUNCTION public.sec_tc1_issue_capability(text,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text) FROM PUBLIC, education_app")
    op.execute("GRANT EXECUTE ON FUNCTION public.sec_tc1_issue_capability(text,uuid,uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text,text) TO education_context_issuer")

    op.execute("REVOKE ALL ON TABLE public.sec_tc1_capabilities, public.intervention_followup_acknowledgement_evidence_links, public.intervention_followup_acknowledgement_evidence_corrections, public.accountability_obligation_acknowledgement_evidence_links, public.accountability_obligation_acknowledgement_evidence_corrections FROM education_app, education_context_issuer, PUBLIC")

    op.execute(r"""
        CREATE FUNCTION public.sec_tc1_validate_capability(p_value text, p_expected text)
        RETURNS public.sec_tc1_capabilities LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $f$
        DECLARE v_cap public.sec_tc1_capabilities%ROWTYPE; v_student uuid; v_required text; v_read boolean;
        BEGIN
            IF session_user <> 'education_app' THEN RAISE EXCEPTION 'SEC-TC1 consumer role required' USING ERRCODE='42501'; END IF;
            SELECT * INTO v_cap FROM public.sec_tc1_capabilities c WHERE c.capability_value=p_value FOR UPDATE;
            IF NOT FOUND OR v_cap.expires_at<=clock_timestamp() OR v_cap.purpose<>p_expected THEN RAISE EXCEPTION 'SEC-TC1 capability invalid' USING ERRCODE='42501'; END IF;
            IF v_cap.purpose='M13_NOTICE_ACK' THEN
                IF v_cap.receipt_id IS NOT NULL OR NOT EXISTS (
                    SELECT 1 FROM public.family_notices n JOIN public.user_accounts u ON u.id=v_cap.actor_user_id
                    JOIN public.guardian_profiles gp ON gp.person_id=u.person_id AND gp.id=v_cap.guardian_profile_id AND gp.institution_id=v_cap.institution_id AND gp.organization_id=v_cap.organization_id AND gp.status='ACTIVE'
                    JOIN public.institutions i ON i.id=gp.institution_id AND i.organization_id=gp.organization_id AND i.status='ACTIVE'
                    WHERE n.id=v_cap.target_id AND n.organization_id=v_cap.organization_id AND n.institution_id=v_cap.institution_id AND n.status='PUBLISHED' AND u.is_active=true
                      AND (n.student_profile_id IS NULL OR EXISTS (
                        SELECT 1 FROM public.guardian_student_portal_access g WHERE g.guardian_profile_id=gp.id
                          AND g.student_profile_id=n.student_profile_id AND g.organization_id=v_cap.organization_id
                          AND g.institution_id=v_cap.institution_id AND g.status='ACTIVE'
                      ))
                ) THEN RAISE EXCEPTION 'SEC-TC1 guardian authorization unavailable' USING ERRCODE='42501'; END IF;
                SELECT n.student_profile_id INTO v_student FROM public.family_notices n WHERE n.id=v_cap.target_id;
            ELSE
                IF NOT EXISTS (SELECT 1 FROM public.user_accounts u JOIN public.memberships m ON m.user_id=u.id AND m.institution_id=v_cap.institution_id AND m.status='ACTIVE' JOIN public.institutions i ON i.id=m.institution_id AND i.organization_id=v_cap.organization_id AND i.status='ACTIVE' WHERE u.id=v_cap.actor_user_id AND u.is_active=true) THEN RAISE EXCEPTION 'SEC-TC1 actor is no longer active' USING ERRCODE='42501'; END IF;
                SELECT n.student_profile_id INTO v_student FROM public.family_notice_receipts r JOIN public.family_notices n ON n.id=r.family_notice_id WHERE r.id=v_cap.receipt_id AND r.organization_id=v_cap.organization_id AND r.institution_id=v_cap.institution_id AND r.acknowledged_at IS NOT NULL AND n.organization_id=v_cap.organization_id AND n.institution_id=v_cap.institution_id
                  AND EXISTS (SELECT 1 FROM public.sec_tc1_capabilities ack WHERE ack.purpose='M13_NOTICE_ACK' AND ack.result_id=r.id AND ack.target_id=n.id AND ack.guardian_profile_id=r.guardian_profile_id AND ack.organization_id=r.organization_id AND ack.institution_id=r.institution_id AND ack.consumed_at IS NOT NULL);
                IF NOT FOUND THEN RAISE EXCEPTION 'SEC-TC1 acknowledgement unavailable' USING ERRCODE='42501'; END IF;
            END IF;
            v_read := v_cap.purpose IN ('M21_ACK_READ','M27_ACK_READ');
            IF v_cap.consumed_at IS NOT NULL AND v_read THEN RAISE EXCEPTION 'SEC-TC1 read capability replay denied' USING ERRCODE='42501'; END IF;
            IF v_cap.purpose='M13_NOTICE_ACK' THEN
                NULL; -- Guardian profile/grant validation above is separate from staff authorization.
            ELSIF left(v_cap.purpose,3)='M21' THEN
                v_required := CASE WHEN v_read THEN 'intervention.read' ELSE 'intervention.followup.acknowledgement_evidence.manage' END;
                IF NOT EXISTS (SELECT 1 FROM public.intervention_followups f JOIN public.interventions iv ON iv.id=f.intervention_id JOIN public.family_notice_receipts r ON r.id=v_cap.receipt_id JOIN public.guardian_student_portal_access g ON g.guardian_profile_id=r.guardian_profile_id AND g.student_profile_id=v_student AND g.status='ACTIVE' WHERE f.id=v_cap.target_id AND f.organization_id=v_cap.organization_id AND f.institution_id=v_cap.institution_id AND iv.organization_id=v_cap.organization_id AND iv.institution_id=v_cap.institution_id AND v_student IS NOT NULL AND iv.student_profile_id=v_student AND g.organization_id=v_cap.organization_id AND g.institution_id=v_cap.institution_id) THEN RAISE EXCEPTION 'SEC-TC1 M21 target unavailable' USING ERRCODE='42501'; END IF;
                IF NOT EXISTS (SELECT 1 FROM public.memberships m JOIN public.membership_roles mr ON mr.membership_id=m.id JOIN public.role_permissions rp ON rp.role_id=mr.role_id JOIN public.permissions p ON p.id=rp.permission_id WHERE m.user_id=v_cap.actor_user_id AND m.institution_id=v_cap.institution_id AND m.status='ACTIVE' AND p.key='communications.delivery.view') OR NOT EXISTS (SELECT 1 FROM public.memberships m JOIN public.membership_roles mr ON mr.membership_id=m.id JOIN public.role_permissions rp ON rp.role_id=mr.role_id JOIN public.permissions p ON p.id=rp.permission_id WHERE m.user_id=v_cap.actor_user_id AND m.institution_id=v_cap.institution_id AND m.status='ACTIVE' AND p.key=v_required) THEN RAISE EXCEPTION 'SEC-TC1 M21 permission denied' USING ERRCODE='42501'; END IF;
                IF NOT EXISTS (SELECT 1 FROM public.memberships m JOIN public.membership_roles mr ON mr.membership_id=m.id JOIN public.roles r ON r.id=mr.role_id WHERE m.user_id=v_cap.actor_user_id AND m.institution_id=v_cap.institution_id AND m.status='ACTIVE' AND r.institution_id=v_cap.institution_id AND r.key IN ('SYSTEM_ADMIN','RECTOR','ACADEMIC_COORDINATOR')) AND NOT EXISTS (SELECT 1 FROM public.user_accounts u JOIN public.staff_profiles sp ON sp.person_id=u.person_id AND sp.institution_id=v_cap.institution_id AND sp.status='ACTIVE' JOIN public.teaching_assignments ta ON ta.staff_profile_id=sp.id AND ta.institution_id=v_cap.institution_id JOIN public.course_offerings co ON co.id=ta.course_offering_id AND co.institution_id=v_cap.institution_id AND co.status='ACTIVE' JOIN public.student_section_assignments ssa ON ssa.section_id=co.section_id AND ssa.institution_id=v_cap.institution_id AND ssa.status='ACTIVE' JOIN public.enrollments e ON e.id=ssa.enrollment_id AND e.institution_id=v_cap.institution_id WHERE u.id=v_cap.actor_user_id AND u.is_active AND e.student_profile_id=v_student AND (ta.starts_on IS NULL OR ta.starts_on<=CURRENT_DATE) AND (ta.ends_on IS NULL OR ta.ends_on>=CURRENT_DATE)) THEN RAISE EXCEPTION 'SEC-TC1 M21 target scope denied' USING ERRCODE='42501'; END IF;
            ELSE
                v_required := CASE WHEN v_read THEN 'accountability.view' ELSE 'accountability.obligation.acknowledgement_evidence.manage' END;
                IF NOT EXISTS (SELECT 1 FROM public.accountability_obligations o JOIN public.accountability_cases c ON c.id=o.case_id WHERE o.id=v_cap.target_id AND o.organization_id=v_cap.organization_id AND o.institution_id=v_cap.institution_id AND c.organization_id=v_cap.organization_id AND c.institution_id=v_cap.institution_id AND ((c.subject_type='STUDENT' AND v_student IS NOT NULL AND c.subject_id=v_student AND EXISTS (SELECT 1 FROM public.family_notice_receipts r JOIN public.guardian_student_portal_access g ON g.guardian_profile_id=r.guardian_profile_id WHERE r.id=v_cap.receipt_id AND g.student_profile_id=v_student AND g.organization_id=v_cap.organization_id AND g.institution_id=v_cap.institution_id AND g.status='ACTIVE')) OR (c.subject_type<>'STUDENT' AND v_student IS NULL))) THEN RAISE EXCEPTION 'SEC-TC1 M27 target unavailable' USING ERRCODE='42501'; END IF;
                IF NOT EXISTS (SELECT 1 FROM public.memberships m JOIN public.membership_roles mr ON mr.membership_id=m.id JOIN public.role_permissions rp ON rp.role_id=mr.role_id JOIN public.permissions p ON p.id=rp.permission_id WHERE m.user_id=v_cap.actor_user_id AND m.institution_id=v_cap.institution_id AND m.status='ACTIVE' AND p.key='communications.delivery.view') OR NOT EXISTS (SELECT 1 FROM public.memberships m JOIN public.membership_roles mr ON mr.membership_id=m.id JOIN public.role_permissions rp ON rp.role_id=mr.role_id JOIN public.permissions p ON p.id=rp.permission_id WHERE m.user_id=v_cap.actor_user_id AND m.institution_id=v_cap.institution_id AND m.status='ACTIVE' AND p.key=v_required) THEN RAISE EXCEPTION 'SEC-TC1 M27 permission denied' USING ERRCODE='42501'; END IF;
            END IF;
            RETURN v_cap;
        END $f$
    """)

    # The SECURITY DEFINER domain functions are typed and expose only bounded
    # link/correction/read results. The shared validator is not executable by
    # runtime roles and cannot mutate domain state itself.
    op.execute("ALTER FUNCTION public.sec_tc1_validate_capability(text,text) OWNER TO education_context_function_owner")
    op.execute("REVOKE ALL ON FUNCTION public.sec_tc1_validate_capability(text,text) FROM PUBLIC, education_app, education_context_issuer")

    op.execute(r"""
        CREATE FUNCTION public.m21_link_acknowledgement_evidence(p_value text)
        RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $f$
        DECLARE c public.sec_tc1_capabilities%ROWTYPE; v_student uuid; v_id uuid; v_gen integer;
        BEGIN
          c := public.sec_tc1_validate_capability(p_value,'M21_ACK_LINK');
          IF c.result_id IS NOT NULL THEN
            UPDATE public.sec_tc1_capabilities SET consumed_at=clock_timestamp() WHERE id=c.id;
            RETURN c.result_id;
          END IF;
          PERFORM 1 FROM public.family_notice_receipts WHERE id=c.receipt_id FOR UPDATE;
          PERFORM 1 FROM public.intervention_followups WHERE id=c.target_id FOR UPDATE;
          IF EXISTS (SELECT 1 FROM public.intervention_followup_acknowledgement_evidence_links l LEFT JOIN public.intervention_followup_acknowledgement_evidence_corrections x ON x.original_link_id=l.id WHERE l.receipt_id=c.receipt_id AND l.followup_id=c.target_id AND x.id IS NULL) THEN
            SELECT l.id INTO v_id FROM public.intervention_followup_acknowledgement_evidence_links l LEFT JOIN public.intervention_followup_acknowledgement_evidence_corrections x ON x.original_link_id=l.id WHERE l.receipt_id=c.receipt_id AND l.followup_id=c.target_id AND x.id IS NULL ORDER BY l.generation DESC LIMIT 1;
          ELSE
            SELECT COALESCE(max(generation),0)+1 INTO v_gen FROM public.intervention_followup_acknowledgement_evidence_links WHERE receipt_id=c.receipt_id AND followup_id=c.target_id;
            v_id:=pg_catalog.gen_random_uuid();
            INSERT INTO public.intervention_followup_acknowledgement_evidence_links(id,organization_id,institution_id,receipt_id,followup_id,linked_by_user_id,generation,operation_key) VALUES(v_id,c.organization_id,c.institution_id,c.receipt_id,c.target_id,c.actor_user_id,v_gen,c.operation_key);
            INSERT INTO public.audit_logs(id,institution_id,actor_user_id,action,entity_type,entity_id,metadata_json,created_at) VALUES(pg_catalog.gen_random_uuid(),c.institution_id,c.actor_user_id,'student.intervention.followup.acknowledgement_evidence.linked','InterventionFollowUpAcknowledgementEvidenceLink',v_id,json_build_object('link_id',v_id,'receipt_id',c.receipt_id,'target_id',c.target_id),clock_timestamp());
          END IF;
          UPDATE public.sec_tc1_capabilities SET consumed_at=clock_timestamp(),result_id=v_id WHERE id=c.id;
          RETURN v_id;
        END $f$
    """)
    op.execute("ALTER FUNCTION public.m21_link_acknowledgement_evidence(text) OWNER TO education_context_function_owner")

    op.execute(r"""
        CREATE FUNCTION public.m27_link_acknowledgement_evidence(p_value text)
        RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $f$
        DECLARE c public.sec_tc1_capabilities%ROWTYPE; v_id uuid; v_gen integer;
        BEGIN
          c:=public.sec_tc1_validate_capability(p_value,'M27_ACK_LINK');
          IF c.result_id IS NOT NULL THEN RETURN c.result_id; END IF;
          PERFORM 1 FROM public.family_notice_receipts WHERE id=c.receipt_id FOR UPDATE;
          PERFORM 1 FROM public.accountability_obligations WHERE id=c.target_id FOR UPDATE;
          IF EXISTS (SELECT 1 FROM public.accountability_obligation_acknowledgement_evidence_links l LEFT JOIN public.accountability_obligation_acknowledgement_evidence_corrections x ON x.original_link_id=l.id WHERE l.receipt_id=c.receipt_id AND l.obligation_id=c.target_id AND x.id IS NULL) THEN
            SELECT l.id INTO v_id FROM public.accountability_obligation_acknowledgement_evidence_links l LEFT JOIN public.accountability_obligation_acknowledgement_evidence_corrections x ON x.original_link_id=l.id WHERE l.receipt_id=c.receipt_id AND l.obligation_id=c.target_id AND x.id IS NULL ORDER BY l.generation DESC LIMIT 1;
          ELSE
            SELECT COALESCE(max(generation),0)+1 INTO v_gen FROM public.accountability_obligation_acknowledgement_evidence_links WHERE receipt_id=c.receipt_id AND obligation_id=c.target_id;
            v_id:=pg_catalog.gen_random_uuid();
            INSERT INTO public.accountability_obligation_acknowledgement_evidence_links(id,organization_id,institution_id,receipt_id,obligation_id,linked_by_user_id,generation,operation_key) VALUES(v_id,c.organization_id,c.institution_id,c.receipt_id,c.target_id,c.actor_user_id,v_gen,c.operation_key);
            INSERT INTO public.audit_logs(id,institution_id,actor_user_id,action,entity_type,entity_id,metadata_json,created_at) VALUES(pg_catalog.gen_random_uuid(),c.institution_id,c.actor_user_id,'accountability.obligation.acknowledgement_evidence.linked','AccountabilityObligationAcknowledgementEvidenceLink',v_id,json_build_object('link_id',v_id,'receipt_id',c.receipt_id,'target_id',c.target_id),clock_timestamp());
          END IF;
          UPDATE public.sec_tc1_capabilities SET consumed_at=clock_timestamp(),result_id=v_id WHERE id=c.id;
          RETURN v_id;
        END $f$
    """)
    op.execute("ALTER FUNCTION public.m27_link_acknowledgement_evidence(text) OWNER TO education_context_function_owner")

    # Correctors append one bounded correction. Supersession links are created
    # by the owning domain operation only after validating matching receipt.
    op.execute(r"""
        CREATE FUNCTION public.m21_correct_acknowledgement_evidence(p_value text)
        RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $f$
        DECLARE c public.sec_tc1_capabilities%ROWTYPE; v_id uuid; v_replacement uuid; v_gen integer;
        BEGIN
          c:=public.sec_tc1_validate_capability(p_value,'M21_ACK_CORRECT');
          IF c.result_id IS NOT NULL THEN RETURN c.result_id; END IF;
          PERFORM 1 FROM public.family_notice_receipts WHERE id=c.receipt_id FOR UPDATE;
          PERFORM 1 FROM public.intervention_followups WHERE id=c.target_id OR id=c.replacement_target_id ORDER BY id FOR UPDATE;
          PERFORM 1 FROM public.intervention_followup_acknowledgement_evidence_links WHERE id=c.related_link_id FOR UPDATE;
          IF NOT EXISTS (SELECT 1 FROM public.intervention_followup_acknowledgement_evidence_links WHERE id=c.related_link_id AND receipt_id=c.receipt_id AND followup_id=c.target_id AND organization_id=c.organization_id AND institution_id=c.institution_id) THEN RAISE EXCEPTION 'M21 evidence link unavailable' USING ERRCODE='42501'; END IF;
          IF EXISTS (SELECT 1 FROM public.intervention_followup_acknowledgement_evidence_corrections WHERE original_link_id=c.related_link_id) THEN RAISE EXCEPTION 'M21 evidence link already corrected' USING ERRCODE='23505'; END IF;
          IF c.replacement_target_id IS NOT NULL THEN
            IF NOT EXISTS (SELECT 1 FROM public.intervention_followups f JOIN public.interventions i ON i.id=f.intervention_id JOIN public.family_notice_receipts r ON r.id=c.receipt_id JOIN public.family_notices n ON n.id=r.family_notice_id WHERE f.id=c.replacement_target_id AND f.organization_id=c.organization_id AND f.institution_id=c.institution_id AND i.student_profile_id=n.student_profile_id) THEN RAISE EXCEPTION 'M21 replacement target invalid' USING ERRCODE='42501'; END IF;
            SELECT l.id INTO v_replacement FROM public.intervention_followup_acknowledgement_evidence_links l LEFT JOIN public.intervention_followup_acknowledgement_evidence_corrections x ON x.original_link_id=l.id WHERE l.receipt_id=c.receipt_id AND l.followup_id=c.replacement_target_id AND x.id IS NULL ORDER BY l.generation DESC LIMIT 1;
            IF v_replacement IS NULL THEN
              SELECT COALESCE(max(generation),0)+1 INTO v_gen FROM public.intervention_followup_acknowledgement_evidence_links WHERE receipt_id=c.receipt_id AND followup_id=c.replacement_target_id;
              v_replacement:=pg_catalog.gen_random_uuid();
              INSERT INTO public.intervention_followup_acknowledgement_evidence_links(id,organization_id,institution_id,receipt_id,followup_id,linked_by_user_id,generation,operation_key) VALUES(v_replacement,c.organization_id,c.institution_id,c.receipt_id,c.replacement_target_id,c.actor_user_id,v_gen,c.operation_key);
            END IF;
          END IF;
          v_id:=pg_catalog.gen_random_uuid();
          INSERT INTO public.intervention_followup_acknowledgement_evidence_corrections(id,organization_id,institution_id,original_link_id,replacement_link_id,corrected_by_user_id,reason_code,operation_key) VALUES(v_id,c.organization_id,c.institution_id,c.related_link_id,v_replacement,c.actor_user_id,c.reason_code,c.operation_key);
          INSERT INTO public.audit_logs(id,institution_id,actor_user_id,action,entity_type,entity_id,metadata_json,created_at) VALUES(pg_catalog.gen_random_uuid(),c.institution_id,c.actor_user_id,'student.intervention.followup.acknowledgement_evidence.corrected','InterventionFollowUpAcknowledgementEvidenceCorrection',v_id,json_build_object('correction_id',v_id,'link_id',c.related_link_id,'receipt_id',c.receipt_id,'target_id',c.target_id,'replacement_id',v_replacement,'reason_code',c.reason_code),clock_timestamp());
          UPDATE public.sec_tc1_capabilities SET consumed_at=clock_timestamp(),result_id=v_id WHERE id=c.id;
          RETURN v_id;
        END $f$
    """)
    op.execute("ALTER FUNCTION public.m21_correct_acknowledgement_evidence(text) OWNER TO education_context_function_owner")

    op.execute(r"""
        CREATE FUNCTION public.m27_correct_acknowledgement_evidence(p_value text)
        RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $f$
        DECLARE c public.sec_tc1_capabilities%ROWTYPE; v_id uuid; v_replacement uuid; v_gen integer;
        BEGIN
          c:=public.sec_tc1_validate_capability(p_value,'M27_ACK_CORRECT');
          IF c.result_id IS NOT NULL THEN RETURN c.result_id; END IF;
          PERFORM 1 FROM public.family_notice_receipts WHERE id=c.receipt_id FOR UPDATE;
          PERFORM 1 FROM public.accountability_obligations WHERE id=c.target_id OR id=c.replacement_target_id ORDER BY id FOR UPDATE;
          PERFORM 1 FROM public.accountability_obligation_acknowledgement_evidence_links WHERE id=c.related_link_id FOR UPDATE;
          IF NOT EXISTS (SELECT 1 FROM public.accountability_obligation_acknowledgement_evidence_links WHERE id=c.related_link_id AND receipt_id=c.receipt_id AND obligation_id=c.target_id AND organization_id=c.organization_id AND institution_id=c.institution_id) THEN RAISE EXCEPTION 'M27 evidence link unavailable' USING ERRCODE='42501'; END IF;
          IF EXISTS (SELECT 1 FROM public.accountability_obligation_acknowledgement_evidence_corrections WHERE original_link_id=c.related_link_id) THEN RAISE EXCEPTION 'M27 evidence link already corrected' USING ERRCODE='23505'; END IF;
          IF c.replacement_target_id IS NOT NULL THEN
            IF NOT EXISTS (SELECT 1 FROM public.accountability_obligations o JOIN public.accountability_cases ca ON ca.id=o.case_id JOIN public.family_notice_receipts r ON r.id=c.receipt_id JOIN public.family_notices n ON n.id=r.family_notice_id WHERE o.id=c.replacement_target_id AND o.organization_id=c.organization_id AND o.institution_id=c.institution_id AND ((ca.subject_type='STUDENT' AND n.student_profile_id IS NOT NULL AND ca.subject_id=n.student_profile_id AND EXISTS (SELECT 1 FROM public.guardian_student_portal_access g WHERE g.guardian_profile_id=r.guardian_profile_id AND g.student_profile_id=n.student_profile_id AND g.organization_id=c.organization_id AND g.institution_id=c.institution_id AND g.status='ACTIVE')) OR (ca.subject_type<>'STUDENT' AND n.student_profile_id IS NULL))) THEN RAISE EXCEPTION 'M27 replacement target invalid' USING ERRCODE='42501'; END IF;
            SELECT l.id INTO v_replacement FROM public.accountability_obligation_acknowledgement_evidence_links l LEFT JOIN public.accountability_obligation_acknowledgement_evidence_corrections x ON x.original_link_id=l.id WHERE l.receipt_id=c.receipt_id AND l.obligation_id=c.replacement_target_id AND x.id IS NULL ORDER BY l.generation DESC LIMIT 1;
            IF v_replacement IS NULL THEN
              SELECT COALESCE(max(generation),0)+1 INTO v_gen FROM public.accountability_obligation_acknowledgement_evidence_links WHERE receipt_id=c.receipt_id AND obligation_id=c.replacement_target_id;
              v_replacement:=pg_catalog.gen_random_uuid();
              INSERT INTO public.accountability_obligation_acknowledgement_evidence_links(id,organization_id,institution_id,receipt_id,obligation_id,linked_by_user_id,generation,operation_key) VALUES(v_replacement,c.organization_id,c.institution_id,c.receipt_id,c.replacement_target_id,c.actor_user_id,v_gen,c.operation_key);
            END IF;
          END IF;
          v_id:=pg_catalog.gen_random_uuid();
          INSERT INTO public.accountability_obligation_acknowledgement_evidence_corrections(id,organization_id,institution_id,original_link_id,replacement_link_id,corrected_by_user_id,reason_code,operation_key) VALUES(v_id,c.organization_id,c.institution_id,c.related_link_id,v_replacement,c.actor_user_id,c.reason_code,c.operation_key);
          INSERT INTO public.audit_logs(id,institution_id,actor_user_id,action,entity_type,entity_id,metadata_json,created_at) VALUES(pg_catalog.gen_random_uuid(),c.institution_id,c.actor_user_id,'accountability.obligation.acknowledgement_evidence.corrected','AccountabilityObligationAcknowledgementEvidenceCorrection',v_id,json_build_object('correction_id',v_id,'link_id',c.related_link_id,'receipt_id',c.receipt_id,'target_id',c.target_id,'replacement_id',v_replacement,'reason_code',c.reason_code),clock_timestamp());
          UPDATE public.sec_tc1_capabilities SET consumed_at=clock_timestamp(),result_id=v_id WHERE id=c.id;
          RETURN v_id;
        END $f$
    """)
    op.execute("ALTER FUNCTION public.m27_correct_acknowledgement_evidence(text) OWNER TO education_context_function_owner")

    op.execute(r"""
        CREATE FUNCTION public.m13_acknowledge_family_notice(p_value text)
        RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $f$
        DECLARE c public.sec_tc1_capabilities%ROWTYPE; v_id uuid; v_student uuid; v_acknowledged_at timestamptz; v_now timestamptz:=clock_timestamp();
        BEGIN
          c:=public.sec_tc1_validate_capability(p_value,'M13_NOTICE_ACK');
          SELECT n.student_profile_id INTO v_student FROM public.family_notices n WHERE n.id=c.target_id AND n.organization_id=c.organization_id AND n.institution_id=c.institution_id AND n.status='PUBLISHED' FOR SHARE;
          IF NOT FOUND THEN RAISE EXCEPTION 'M13 notice unavailable' USING ERRCODE='42501'; END IF;
          PERFORM 1 FROM public.guardian_profiles gp JOIN public.user_accounts u ON u.person_id=gp.person_id
          WHERE gp.id=c.guardian_profile_id AND gp.institution_id=c.institution_id AND gp.status='ACTIVE' AND u.id=c.actor_user_id AND u.is_active=true FOR SHARE OF gp,u;
          IF NOT FOUND THEN RAISE EXCEPTION 'M13 guardian unavailable' USING ERRCODE='42501'; END IF;
          IF v_student IS NOT NULL THEN
            PERFORM 1 FROM public.guardian_student_portal_access g WHERE g.guardian_profile_id=c.guardian_profile_id
              AND g.student_profile_id=v_student AND g.organization_id=c.organization_id AND g.institution_id=c.institution_id
              AND g.status='ACTIVE' FOR SHARE;
            IF NOT FOUND THEN RAISE EXCEPTION 'M13 guardian grant unavailable' USING ERRCODE='42501'; END IF;
          END IF;
          SELECT r.id,r.acknowledged_at INTO v_id,v_acknowledged_at FROM public.family_notice_receipts r
          WHERE r.family_notice_id=c.target_id AND r.guardian_profile_id=c.guardian_profile_id FOR UPDATE;
          IF c.result_id IS NOT NULL THEN
            IF NOT FOUND OR v_id IS DISTINCT FROM c.result_id OR v_acknowledged_at IS NULL THEN
              RAISE EXCEPTION 'M13 acknowledgement result unavailable' USING ERRCODE='42501';
            END IF;
            UPDATE public.sec_tc1_capabilities SET consumed_at=clock_timestamp() WHERE id=c.id;
            RETURN c.result_id;
          END IF;
          IF FOUND THEN
            UPDATE public.family_notice_receipts SET read_at=COALESCE(read_at,v_now),acknowledged_at=COALESCE(acknowledged_at,v_now) WHERE id=v_id;
          ELSE
            v_id:=pg_catalog.gen_random_uuid();
            INSERT INTO public.family_notice_receipts(id,organization_id,institution_id,family_notice_id,guardian_profile_id,read_at,acknowledged_at)
            VALUES(v_id,c.organization_id,c.institution_id,c.target_id,c.guardian_profile_id,v_now,v_now);
          END IF;
          INSERT INTO public.audit_logs(id,institution_id,actor_user_id,action,entity_type,entity_id,metadata_json,created_at)
          VALUES(pg_catalog.gen_random_uuid(),c.institution_id,c.actor_user_id,'FAMILY_NOTICE_ACKNOWLEDGED','FamilyNoticeReceipt',v_id,
            json_build_object('receipt_id',v_id,'notice_id',c.target_id,'guardian_profile_id',c.guardian_profile_id),v_now);
          UPDATE public.sec_tc1_capabilities SET consumed_at=v_now,result_id=v_id WHERE id=c.id;
          RETURN v_id;
        END $f$
    """)
    op.execute("ALTER FUNCTION public.m13_acknowledge_family_notice(text) OWNER TO education_context_function_owner")

    # Read interfaces expose only identifiers, generation and derived status.
    for domain, table, correction, targetcol, cap_purpose in (
        ("m21", "intervention_followup_acknowledgement_evidence_links", "intervention_followup_acknowledgement_evidence_corrections", "followup_id", "M21_ACK_READ"),
        ("m27", "accountability_obligation_acknowledgement_evidence_links", "accountability_obligation_acknowledgement_evidence_corrections", "obligation_id", "M27_ACK_READ"),
    ):
        op.execute(sa.text(f"""
            CREATE FUNCTION public.{domain}_read_acknowledgement_evidence(p_value text)
            RETURNS TABLE(link_id uuid, receipt_id uuid, target_id uuid, generation integer, linked_at timestamptz, effective_state text, reason_code text)
            LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $f$
            DECLARE c public.sec_tc1_capabilities%ROWTYPE;
            BEGIN
              c:=public.sec_tc1_validate_capability(p_value,'{cap_purpose}');
              RETURN QUERY SELECT l.id,l.receipt_id,l.{targetcol},l.generation,l.linked_at,
                CASE WHEN x.id IS NULL THEN 'ACTIVE' WHEN x.replacement_link_id IS NULL THEN 'VOIDED' ELSE 'SUPERSEDED' END,
                x.reason_code::text FROM public.{table} l LEFT JOIN public.{correction} x ON x.original_link_id=l.id
                WHERE l.organization_id=c.organization_id AND l.institution_id=c.institution_id AND l.{targetcol}=c.target_id
                ORDER BY l.generation;
              UPDATE public.sec_tc1_capabilities SET consumed_at=clock_timestamp() WHERE id=c.id;
            END $f$
        """))
        op.execute(sa.text(f"ALTER FUNCTION public.{domain}_read_acknowledgement_evidence(text) OWNER TO education_context_function_owner"))

    op.execute("""
        CREATE FUNCTION public.sec_tc1_reject_history_mutation() RETURNS trigger
        LANGUAGE plpgsql SET search_path=pg_catalog,public AS $f$
        BEGIN RAISE EXCEPTION 'SEC-TC1 evidence history is append-only' USING ERRCODE='55000'; END $f$
    """)
    op.execute("ALTER FUNCTION public.sec_tc1_reject_history_mutation() OWNER TO education_context_function_owner")
    history_tables = (
        ("intervention_followup_acknowledgement_evidence_links", "sec_tc1_hist_immutable_1", "sec_tc1_hist_no_truncate_1"),
        ("intervention_followup_acknowledgement_evidence_corrections", "sec_tc1_hist_immutable_2", "sec_tc1_hist_no_truncate_2"),
        ("accountability_obligation_acknowledgement_evidence_links", "sec_tc1_hist_immutable_3", "sec_tc1_hist_no_truncate_3"),
        ("accountability_obligation_acknowledgement_evidence_corrections", "sec_tc1_hist_immutable_4", "sec_tc1_hist_no_truncate_4"),
    )
    for table, immutable_trigger, truncate_trigger in history_tables:
        op.execute(sa.text(f'CREATE TRIGGER "{immutable_trigger}" BEFORE UPDATE OR DELETE ON public."{table}" FOR EACH ROW EXECUTE FUNCTION public.sec_tc1_reject_history_mutation()'))
        op.execute(sa.text(f'CREATE TRIGGER "{truncate_trigger}" BEFORE TRUNCATE ON public."{table}" FOR EACH STATEMENT EXECUTE FUNCTION public.sec_tc1_reject_history_mutation()'))

    for signature in _FUNCTIONS:
        if signature.startswith("sec_tc1_issue"):
            continue
        op.execute(sa.text(f"ALTER FUNCTION public.{signature} OWNER TO education_context_function_owner"))
        op.execute(sa.text(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC, education_context_issuer"))
        if signature != "sec_tc1_validate_capability(text,text)":
            op.execute(sa.text(f"GRANT EXECUTE ON FUNCTION public.{signature} TO education_app"))
    op.execute("REVOKE ALL ON FUNCTION public.sec_tc1_reject_history_mutation() FROM PUBLIC, education_app, education_context_issuer")


def downgrade() -> None:
    bind = op.get_bind()
    retained = bind.execute(sa.text("""
        SELECT
          (SELECT count(*) FROM public.sec_tc1_capabilities) +
          (SELECT count(*) FROM public.intervention_followup_acknowledgement_evidence_links) +
          (SELECT count(*) FROM public.intervention_followup_acknowledgement_evidence_corrections) +
          (SELECT count(*) FROM public.accountability_obligation_acknowledgement_evidence_links) +
          (SELECT count(*) FROM public.accountability_obligation_acknowledgement_evidence_corrections)
    """)).scalar_one()
    if retained:
        raise RuntimeError("Refusing SEC-TC1 downgrade while capability or acknowledgement evidence rows exist")
    for signature in _FUNCTIONS:
        bind.execute(sa.text(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC, education_app, education_context_issuer"))
    bind.execute(sa.text("DROP POLICY IF EXISTS audit_logs_sec_tc1_insert ON public.audit_logs"))
    bind.execute(sa.text("REVOKE INSERT ON TABLE public.audit_logs FROM education_context_function_owner"))
    bind.execute(sa.text("DROP POLICY IF EXISTS family_notice_receipts_tc1_insert ON public.family_notice_receipts"))
    bind.execute(sa.text("DROP POLICY IF EXISTS family_notice_receipts_tc1_update ON public.family_notice_receipts"))
    bind.execute(sa.text("REVOKE INSERT (id, organization_id, institution_id, family_notice_id, guardian_profile_id, read_at, acknowledged_at), UPDATE (read_at, acknowledged_at) ON TABLE public.family_notice_receipts FROM education_context_function_owner"))
    for table, immutable_trigger, truncate_trigger in (
        ("intervention_followup_acknowledgement_evidence_links", "sec_tc1_hist_immutable_1", "sec_tc1_hist_no_truncate_1"),
        ("intervention_followup_acknowledgement_evidence_corrections", "sec_tc1_hist_immutable_2", "sec_tc1_hist_no_truncate_2"),
        ("accountability_obligation_acknowledgement_evidence_links", "sec_tc1_hist_immutable_3", "sec_tc1_hist_no_truncate_3"),
        ("accountability_obligation_acknowledgement_evidence_corrections", "sec_tc1_hist_immutable_4", "sec_tc1_hist_no_truncate_4"),
    ):
        bind.execute(sa.text(f'DROP TRIGGER IF EXISTS "{immutable_trigger}" ON public."{table}"'))
        bind.execute(sa.text(f'DROP TRIGGER IF EXISTS "{truncate_trigger}" ON public."{table}"'))
    for table in ("user_accounts", "institutions", "memberships", "membership_roles", "roles", "role_permissions", "permissions", "family_notice_receipts", "guardian_profiles", "guardian_student_portal_access", "staff_profiles", "teaching_assignments", "course_offerings", "student_section_assignments", "enrollments", "intervention_followups", "interventions", "accountability_obligations", "accountability_cases"):
        bind.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_sec_tc1_read" ON public."{table}"'))
        bind.execute(sa.text(f'REVOKE SELECT ON TABLE public."{table}" FROM education_context_function_owner'))
    bind.execute(sa.text("DROP POLICY IF EXISTS family_notices_sec_tc1_read ON public.family_notices"))
    bind.execute(sa.text("REVOKE SELECT (id, organization_id, institution_id, status, student_profile_id) ON TABLE public.family_notices FROM education_context_function_owner"))
    for table, policy in _ROW_LOCK_TABLES:
        bind.execute(sa.text(f'DROP POLICY IF EXISTS "{policy}" ON public."{table}"'))
        bind.execute(sa.text(f'REVOKE UPDATE (id) ON TABLE public."{table}" FROM education_context_function_owner'))
    for table in _ROW_LOCK_EVIDENCE_TABLES:
        bind.execute(sa.text(f'REVOKE UPDATE (id) ON TABLE public."{table}" FROM education_context_function_owner'))
    for table in (
        "sec_tc1_capabilities", "intervention_followup_acknowledgement_evidence_links",
        "intervention_followup_acknowledgement_evidence_corrections",
        "accountability_obligation_acknowledgement_evidence_links",
        "accountability_obligation_acknowledgement_evidence_corrections",
    ):
        bind.execute(sa.text(f'DROP POLICY IF EXISTS "{table}_function_owner" ON public."{table}"'))
        bind.execute(sa.text(f'REVOKE ALL ON TABLE public."{table}" FROM education_context_function_owner'))
    for signature in reversed(_FUNCTIONS):
        bind.execute(sa.text(f"DROP FUNCTION IF EXISTS public.{signature} CASCADE"))
    for table in (
        "accountability_obligation_acknowledgement_evidence_corrections",
        "accountability_obligation_acknowledgement_evidence_links",
        "intervention_followup_acknowledgement_evidence_corrections",
        "intervention_followup_acknowledgement_evidence_links",
        "sec_tc1_capabilities",
    ):
        op.drop_table(table)
    for table in ("family_notice_receipts", "intervention_followups", "accountability_obligations"):
        op.drop_constraint(f"uq_{table}_tenant_id", table, type_="unique")
    for key, _description, _roles in (
        ("intervention.followup.acknowledgement_evidence.manage", "", ()),
        ("accountability.obligation.acknowledgement_evidence.manage", "", ()),
    ):
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE key=:key)"), {"key": key})
        bind.execute(sa.text("DELETE FROM permissions WHERE key=:key"), {"key": key})
    bind.execute(sa.text("REVOKE INSERT (id, organization_id, institution_id, family_notice_id, guardian_profile_id, read_at), UPDATE (read_at) ON TABLE public.family_notice_receipts FROM education_app"))
    # Restore the pre-0047 M6 runtime privilege contract on downgrade.
    bind.execute(sa.text("GRANT INSERT, UPDATE, DELETE ON TABLE public.family_notice_receipts TO education_app"))
