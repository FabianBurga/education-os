"""M29-2 governed, target-bound batch acknowledgement reads.

Revision ID: 0048_m29_batch_ack_reads
Revises: 0047_sec_tc1_m29_ack_bridge
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0048_m29_batch_ack_reads"
down_revision: str | None = "0047_sec_tc1_m29_ack_bridge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BATCH_FUNCTIONS = (
    "sec_tc1_issue_batch_capability(text,uuid,uuid,uuid,text,text,text)",
    "sec_tc1_validate_batch_capability(text,text,uuid[])",
    "m21_read_acknowledgement_evidence_batch(text,uuid[])",
    "m27_read_acknowledgement_evidence_batch(text,uuid[])",
)

_BATCH_PURPOSES = ("M21_ACK_BATCH_READ", "M27_ACK_BATCH_READ")


def upgrade() -> None:
    op.execute(
        "ALTER TABLE public.sec_tc1_capabilities "
        "ALTER COLUMN target_id DROP NOT NULL"
    )
    op.add_column(
        "sec_tc1_capabilities",
        sa.Column("target_set_digest", sa.String(64), nullable=True),
        schema="public",
    )
    op.execute(
        "ALTER TABLE public.sec_tc1_capabilities "
        "DROP CONSTRAINT ck_sec_tc1_purpose"
    )
    op.create_check_constraint(
        "ck_sec_tc1_purpose",
        "sec_tc1_capabilities",
        "purpose IN ('M13_NOTICE_ACK','M21_ACK_LINK','M21_ACK_CORRECT',"
        "'M21_ACK_READ','M27_ACK_LINK','M27_ACK_CORRECT','M27_ACK_READ',"
        "'M21_ACK_BATCH_READ','M27_ACK_BATCH_READ')",
        schema="public",
    )
    op.create_check_constraint(
        "ck_sec_tc1_binding_mode",
        "sec_tc1_capabilities",
        "((purpose IN ('M21_ACK_BATCH_READ','M27_ACK_BATCH_READ') "
        "AND target_id IS NULL AND target_set_digest ~ '^[0-9a-f]{64}$') "
        "OR (purpose NOT IN ('M21_ACK_BATCH_READ','M27_ACK_BATCH_READ') "
        "AND target_id IS NOT NULL AND target_set_digest IS NULL))",
        schema="public",
    )
    op.create_check_constraint(
        "ck_sec_tc1_target_set_digest",
        "sec_tc1_capabilities",
        "target_set_digest IS NULL OR target_set_digest ~ '^[0-9a-f]{64}$'",
        schema="public",
    )

    op.execute(
        """
        CREATE FUNCTION public.sec_tc1_issue_batch_capability(
            p_purpose text, p_actor uuid, p_org uuid, p_inst uuid,
            p_target_set_digest text, p_operation_key text, p_fingerprint text
        ) RETURNS text LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $f$
        DECLARE
            v_token text;
            v_perm text;
            v_existing public.sec_tc1_capabilities%ROWTYPE;
        BEGIN
            IF session_user <> 'education_context_issuer' THEN
                RAISE EXCEPTION 'SEC-TC1 issuer role required' USING ERRCODE='42501';
            END IF;
            IF p_purpose NOT IN ('M21_ACK_BATCH_READ','M27_ACK_BATCH_READ')
               OR p_actor IS NULL OR p_org IS NULL OR p_inst IS NULL
               OR p_target_set_digest !~ '^[0-9a-f]{64}$'
               OR p_operation_key !~ '^[0-9a-f]{64}$'
               OR p_fingerprint !~ '^[0-9a-f]{64}$' THEN
                RAISE EXCEPTION 'SEC-TC1 invalid batch capability binding' USING ERRCODE='22023';
            END IF;
            IF NOT EXISTS (
                SELECT 1
                FROM public.user_accounts u
                JOIN public.memberships m ON m.user_id=u.id
                    AND m.institution_id=p_inst AND m.status='ACTIVE'
                JOIN public.institutions i ON i.id=m.institution_id
                    AND i.organization_id=p_org AND i.status='ACTIVE'
                WHERE u.id=p_actor AND u.is_active=true
            ) THEN
                RAISE EXCEPTION 'SEC-TC1 actor scope is inactive' USING ERRCODE='42501';
            END IF;
            v_perm := CASE WHEN p_purpose='M21_ACK_BATCH_READ'
                           THEN 'intervention.read'
                           ELSE 'accountability.view' END;
            IF NOT EXISTS (
                SELECT 1
                FROM public.memberships m
                JOIN public.membership_roles mr ON mr.membership_id=m.id
                JOIN public.role_permissions rp ON rp.role_id=mr.role_id
                JOIN public.permissions p ON p.id=rp.permission_id
                WHERE m.user_id=p_actor AND m.institution_id=p_inst
                  AND m.status='ACTIVE' AND p.key='communications.delivery.view'
            ) OR NOT EXISTS (
                SELECT 1
                FROM public.memberships m
                JOIN public.membership_roles mr ON mr.membership_id=m.id
                JOIN public.role_permissions rp ON rp.role_id=mr.role_id
                JOIN public.permissions p ON p.id=rp.permission_id
                WHERE m.user_id=p_actor AND m.institution_id=p_inst
                  AND m.status='ACTIVE' AND p.key=v_perm
            ) THEN
                RAISE EXCEPTION 'SEC-TC1 batch permission denied' USING ERRCODE='42501';
            END IF;
            PERFORM pg_catalog.pg_advisory_xact_lock(
                pg_catalog.hashtextextended(
                    p_actor::text || ':' || p_purpose || ':' || p_operation_key, 0
                )
            );
            SELECT * INTO v_existing
            FROM public.sec_tc1_capabilities c
            WHERE c.actor_user_id=p_actor AND c.purpose=p_purpose
              AND c.operation_key=p_operation_key
            FOR UPDATE;
            IF FOUND THEN
                IF v_existing.organization_id IS DISTINCT FROM p_org
                   OR v_existing.institution_id IS DISTINCT FROM p_inst
                   OR v_existing.target_set_digest IS DISTINCT FROM p_target_set_digest
                   OR v_existing.operation_fingerprint IS DISTINCT FROM p_fingerprint
                   OR v_existing.target_id IS NOT NULL THEN
                    RAISE EXCEPTION 'SEC-TC1 idempotency conflict' USING ERRCODE='23505';
                END IF;
                IF v_existing.expires_at > clock_timestamp()
                   AND v_existing.consumed_at IS NULL THEN
                    RETURN v_existing.capability_value;
                END IF;
                v_token := pg_catalog.gen_random_uuid()::text || pg_catalog.gen_random_uuid()::text;
                UPDATE public.sec_tc1_capabilities
                SET capability_value=v_token, issued_at=clock_timestamp(),
                    expires_at=clock_timestamp()+interval '60 seconds', consumed_at=NULL,
                    result_id=NULL
                WHERE id=v_existing.id;
                RETURN v_token;
            END IF;
            v_token := pg_catalog.gen_random_uuid()::text || pg_catalog.gen_random_uuid()::text;
            INSERT INTO public.sec_tc1_capabilities(
                id, capability_value, actor_user_id, organization_id, institution_id,
                purpose, operation_key, operation_fingerprint, receipt_id, target_id,
                target_set_digest, expires_at
            ) VALUES (
                pg_catalog.gen_random_uuid(), v_token, p_actor, p_org, p_inst,
                p_purpose, p_operation_key, p_fingerprint, NULL, NULL,
                p_target_set_digest, clock_timestamp()+interval '60 seconds'
            );
            RETURN v_token;
        END $f$
        """
    )
    op.execute(
        "ALTER FUNCTION public.sec_tc1_issue_batch_capability(text,uuid,uuid,uuid,text,text,text) "
        "OWNER TO education_context_function_owner"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.sec_tc1_issue_batch_capability(text,uuid,uuid,uuid,text,text,text) "
        "FROM PUBLIC, education_app"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.sec_tc1_issue_batch_capability(text,uuid,uuid,uuid,text,text,text) "
        "TO education_context_issuer"
    )

    op.execute(
        """
        CREATE FUNCTION public.sec_tc1_validate_batch_capability(
            p_value text, p_expected text, p_target_ids uuid[]
        ) RETURNS public.sec_tc1_capabilities LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $f$
        DECLARE
            c public.sec_tc1_capabilities%ROWTYPE;
            v_expected_digest text;
            v_canonical text;
            v_required text;
            v_count integer;
        BEGIN
            IF session_user <> 'education_app' THEN
                RAISE EXCEPTION 'SEC-TC1 consumer role required' USING ERRCODE='42501';
            END IF;
            IF p_expected NOT IN ('M21_ACK_BATCH_READ','M27_ACK_BATCH_READ')
               OR p_target_ids IS NULL
               OR cardinality(p_target_ids) < 1
               OR cardinality(p_target_ids) > 25
               OR EXISTS (SELECT 1 FROM unnest(p_target_ids) x GROUP BY x HAVING count(*) > 1)
               OR EXISTS (SELECT 1 FROM unnest(p_target_ids) x WHERE x IS NULL) THEN
                RAISE EXCEPTION 'SEC-TC1 invalid bounded target set' USING ERRCODE='22023';
            END IF;
            SELECT count(*) INTO v_count FROM unnest(p_target_ids);
            v_canonical := p_expected || '|' ||
                (SELECT c.organization_id::text FROM public.sec_tc1_capabilities c
                 WHERE c.capability_value=p_value) || '|' ||
                (SELECT c.institution_id::text FROM public.sec_tc1_capabilities c
                 WHERE c.capability_value=p_value) || '|' ||
                array_to_string(ARRAY(SELECT x::text FROM unnest(p_target_ids) x ORDER BY x), ',');
            SELECT * INTO c
            FROM public.sec_tc1_capabilities
            WHERE capability_value=p_value
            FOR UPDATE;
            IF NOT FOUND OR c.purpose<>p_expected OR c.target_id IS NOT NULL
               OR c.target_set_digest IS NULL OR c.expires_at<=clock_timestamp()
               OR c.consumed_at IS NOT NULL THEN
                RAISE EXCEPTION 'SEC-TC1 batch capability invalid' USING ERRCODE='42501';
            END IF;
            v_canonical := p_expected || '|' || c.organization_id::text || '|' ||
                c.institution_id::text || '|' ||
                array_to_string(ARRAY(SELECT x::text FROM unnest(p_target_ids) x ORDER BY x), ',');
            v_expected_digest := encode(pg_catalog.sha256(convert_to(v_canonical, 'UTF8')), 'hex');
            IF c.target_set_digest IS DISTINCT FROM v_expected_digest THEN
                RAISE EXCEPTION 'SEC-TC1 target set binding mismatch' USING ERRCODE='42501';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM public.user_accounts u
                JOIN public.memberships m ON m.user_id=u.id
                    AND m.institution_id=c.institution_id AND m.status='ACTIVE'
                JOIN public.institutions i ON i.id=m.institution_id
                    AND i.organization_id=c.organization_id AND i.status='ACTIVE'
                WHERE u.id=c.actor_user_id AND u.is_active=true
            ) THEN
                RAISE EXCEPTION 'SEC-TC1 actor is no longer active' USING ERRCODE='42501';
            END IF;
            v_required := CASE WHEN p_expected='M21_ACK_BATCH_READ'
                               THEN 'intervention.read' ELSE 'accountability.view' END;
            IF NOT EXISTS (
                SELECT 1 FROM public.memberships m
                JOIN public.membership_roles mr ON mr.membership_id=m.id
                JOIN public.role_permissions rp ON rp.role_id=mr.role_id
                JOIN public.permissions p ON p.id=rp.permission_id
                WHERE m.user_id=c.actor_user_id AND m.institution_id=c.institution_id
                  AND m.status='ACTIVE' AND p.key='communications.delivery.view'
            ) OR NOT EXISTS (
                SELECT 1 FROM public.memberships m
                JOIN public.membership_roles mr ON mr.membership_id=m.id
                JOIN public.role_permissions rp ON rp.role_id=mr.role_id
                JOIN public.permissions p ON p.id=rp.permission_id
                WHERE m.user_id=c.actor_user_id AND m.institution_id=c.institution_id
                  AND m.status='ACTIVE' AND p.key=v_required
            ) THEN
                RAISE EXCEPTION 'SEC-TC1 batch permission denied' USING ERRCODE='42501';
            END IF;
            RETURN c;
        END $f$
        """
    )
    op.execute(
        "ALTER FUNCTION public.sec_tc1_validate_batch_capability(text,text,uuid[]) "
        "OWNER TO education_context_function_owner"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.sec_tc1_validate_batch_capability(text,text,uuid[]) "
        "FROM PUBLIC, education_app, education_context_issuer"
    )

    op.execute(
        """
        CREATE FUNCTION public.m21_read_acknowledgement_evidence_batch(
            p_value text, p_target_ids uuid[]
        ) RETURNS TABLE(
            target_id uuid, acknowledgement_evidence_present boolean,
            effective_state text, linked_at timestamptz
        ) LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $f$
        DECLARE c public.sec_tc1_capabilities%ROWTYPE;
        BEGIN
            c := public.sec_tc1_validate_batch_capability(p_value, 'M21_ACK_BATCH_READ', p_target_ids);
            RETURN QUERY
            WITH requested AS (
                SELECT x AS target_id FROM unnest(p_target_ids) x
            ), authorized AS (
                SELECT r.target_id, iv.student_profile_id
                FROM requested r
                JOIN public.intervention_followups f ON f.id=r.target_id
                  AND f.organization_id=c.organization_id AND f.institution_id=c.institution_id
                JOIN public.interventions iv ON iv.id=f.intervention_id
                  AND iv.organization_id=c.organization_id AND iv.institution_id=c.institution_id
                WHERE (
                  EXISTS (
                    SELECT 1 FROM public.memberships m
                    JOIN public.membership_roles mr ON mr.membership_id=m.id
                    JOIN public.roles ro ON ro.id=mr.role_id
                    WHERE m.user_id=c.actor_user_id AND m.institution_id=c.institution_id
                      AND m.status='ACTIVE' AND ro.key IN ('SYSTEM_ADMIN','RECTOR','ACADEMIC_COORDINATOR')
                      AND ro.institution_id=c.institution_id
                  ) OR EXISTS (
                    SELECT 1
                    FROM public.user_accounts ua
                    JOIN public.staff_profiles sp ON sp.person_id=ua.person_id
                      AND sp.institution_id=c.institution_id AND sp.status='ACTIVE'
                    JOIN public.teaching_assignments ta ON ta.staff_profile_id=sp.id
                      AND ta.institution_id=c.institution_id
                    JOIN public.course_offerings co ON co.id=ta.course_offering_id
                      AND co.institution_id=c.institution_id AND co.status='ACTIVE'
                    JOIN public.student_section_assignments ssa ON ssa.section_id=co.section_id
                      AND ssa.institution_id=c.institution_id AND ssa.status='ACTIVE'
                    JOIN public.enrollments e ON e.id=ssa.enrollment_id
                      AND e.institution_id=c.institution_id
                    WHERE ua.id=c.actor_user_id AND ua.is_active=true
                      AND e.student_profile_id=iv.student_profile_id
                      AND (ta.starts_on IS NULL OR ta.starts_on<=CURRENT_DATE)
                      AND (ta.ends_on IS NULL OR ta.ends_on>=CURRENT_DATE)
                  )
                )
            ), effective AS (
                SELECT DISTINCT ON (l.followup_id)
                    l.followup_id AS target_id,
                    (x.id IS NULL) AS acknowledgement_evidence_present,
                    CASE WHEN x.id IS NULL THEN 'ACTIVE'
                         WHEN x.replacement_link_id IS NULL THEN 'VOIDED'
                         ELSE 'SUPERSEDED' END AS effective_state,
                    l.linked_at
                FROM public.intervention_followup_acknowledgement_evidence_links l
                LEFT JOIN public.intervention_followup_acknowledgement_evidence_corrections x
                  ON x.original_link_id=l.id
                JOIN authorized a ON a.target_id=l.followup_id
                JOIN public.family_notice_receipts rr ON rr.id=l.receipt_id
                  AND rr.organization_id=c.organization_id AND rr.institution_id=c.institution_id
                JOIN public.family_notices nn ON nn.id=rr.family_notice_id
                  AND nn.organization_id=c.organization_id AND nn.institution_id=c.institution_id
                WHERE l.organization_id=c.organization_id AND l.institution_id=c.institution_id
                  AND rr.acknowledged_at IS NOT NULL AND nn.student_profile_id=a.student_profile_id
                  AND EXISTS (
                    SELECT 1 FROM public.sec_tc1_capabilities ack
                    WHERE ack.purpose='M13_NOTICE_ACK' AND ack.result_id=rr.id
                      AND ack.target_id=nn.id AND ack.guardian_profile_id=rr.guardian_profile_id
                      AND ack.organization_id=rr.organization_id AND ack.institution_id=rr.institution_id
                      AND ack.consumed_at IS NOT NULL
                  )
                  AND EXISTS (
                    SELECT 1 FROM public.guardian_student_portal_access g
                    WHERE g.guardian_profile_id=rr.guardian_profile_id
                      AND g.student_profile_id=a.student_profile_id
                      AND g.organization_id=c.organization_id AND g.institution_id=c.institution_id
                      AND g.status='ACTIVE'
                  )
                ORDER BY l.followup_id, l.generation DESC, l.id DESC
            )
            SELECT a.target_id, COALESCE(e.acknowledgement_evidence_present,false),
                   e.effective_state, e.linked_at
            FROM authorized a LEFT JOIN effective e ON e.target_id=a.target_id
            ORDER BY a.target_id;
            UPDATE public.sec_tc1_capabilities SET consumed_at=clock_timestamp() WHERE id=c.id;
        END $f$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.m27_read_acknowledgement_evidence_batch(
            p_value text, p_target_ids uuid[]
        ) RETURNS TABLE(
            target_id uuid, acknowledgement_evidence_present boolean,
            effective_state text, linked_at timestamptz
        ) LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $f$
        DECLARE c public.sec_tc1_capabilities%ROWTYPE;
        BEGIN
            c := public.sec_tc1_validate_batch_capability(p_value, 'M27_ACK_BATCH_READ', p_target_ids);
            RETURN QUERY
            WITH requested AS (
                SELECT x AS target_id FROM unnest(p_target_ids) x
            ), authorized AS (
                SELECT r.target_id, ac.subject_type, ac.subject_id
                FROM requested r
                JOIN public.accountability_obligations o ON o.id=r.target_id
                  AND o.organization_id=c.organization_id AND o.institution_id=c.institution_id
                JOIN public.accountability_cases ac ON ac.id=o.case_id
                  AND ac.organization_id=c.organization_id AND ac.institution_id=c.institution_id
                WHERE ac.lifecycle IN ('OPEN','REOPENED')
                  AND o.lifecycle IN ('OPEN','IN_PROGRESS')
                  AND EXISTS (
                    SELECT 1
                    FROM public.memberships m
                    JOIN public.membership_roles mr ON mr.membership_id=m.id
                    JOIN public.role_permissions rp ON rp.role_id=mr.role_id
                    JOIN public.permissions p ON p.id=rp.permission_id
                    WHERE m.user_id=c.actor_user_id
                      AND m.institution_id=c.institution_id
                      AND m.status='ACTIVE'
                      AND p.key='accountability.view'
                  )
            ), effective AS (
                SELECT DISTINCT ON (l.obligation_id)
                    l.obligation_id AS target_id,
                    (x.id IS NULL) AS acknowledgement_evidence_present,
                    CASE WHEN x.id IS NULL THEN 'ACTIVE'
                         WHEN x.replacement_link_id IS NULL THEN 'VOIDED'
                         ELSE 'SUPERSEDED' END AS effective_state,
                    l.linked_at
                FROM public.accountability_obligation_acknowledgement_evidence_links l
                LEFT JOIN public.accountability_obligation_acknowledgement_evidence_corrections x
                  ON x.original_link_id=l.id
                JOIN authorized a ON a.target_id=l.obligation_id
                JOIN public.family_notice_receipts rr ON rr.id=l.receipt_id
                  AND rr.organization_id=c.organization_id AND rr.institution_id=c.institution_id
                JOIN public.family_notices nn ON nn.id=rr.family_notice_id
                  AND nn.organization_id=c.organization_id AND nn.institution_id=c.institution_id
                WHERE l.organization_id=c.organization_id AND l.institution_id=c.institution_id
                  AND rr.acknowledged_at IS NOT NULL
                  AND ((a.subject_type='STUDENT' AND nn.student_profile_id=a.subject_id)
                       OR (a.subject_type<>'STUDENT' AND nn.student_profile_id IS NULL))
                  AND EXISTS (
                    SELECT 1 FROM public.sec_tc1_capabilities ack
                    WHERE ack.purpose='M13_NOTICE_ACK' AND ack.result_id=rr.id
                      AND ack.target_id=nn.id AND ack.guardian_profile_id=rr.guardian_profile_id
                      AND ack.organization_id=rr.organization_id AND ack.institution_id=rr.institution_id
                      AND ack.consumed_at IS NOT NULL
                  )
                  AND (a.subject_type<>'STUDENT' OR EXISTS (
                    SELECT 1 FROM public.guardian_student_portal_access g
                    WHERE g.guardian_profile_id=rr.guardian_profile_id
                      AND g.student_profile_id=a.subject_id
                      AND g.organization_id=c.organization_id AND g.institution_id=c.institution_id
                      AND g.status='ACTIVE'
                  ))
                ORDER BY l.obligation_id, l.generation DESC, l.id DESC
            )
            SELECT a.target_id, COALESCE(e.acknowledgement_evidence_present,false),
                   e.effective_state, e.linked_at
            FROM authorized a LEFT JOIN effective e ON e.target_id=a.target_id
            ORDER BY a.target_id;
            UPDATE public.sec_tc1_capabilities SET consumed_at=clock_timestamp() WHERE id=c.id;
        END $f$
        """
    )

    for signature in _BATCH_FUNCTIONS:
        op.execute(sa.text(f"ALTER FUNCTION public.{signature} OWNER TO education_context_function_owner"))
        revoke_roles = "PUBLIC, education_context_issuer" if signature != _BATCH_FUNCTIONS[0] else "PUBLIC, education_app"
        op.execute(sa.text(f"REVOKE ALL ON FUNCTION public.{signature} FROM {revoke_roles}"))
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.m21_read_acknowledgement_evidence_batch(text,uuid[]) TO education_app"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.m27_read_acknowledgement_evidence_batch(text,uuid[]) TO education_app"
    )


def downgrade() -> None:
    bind = op.get_bind()
    retained = bind.execute(
        sa.text(
            "SELECT count(*) FROM public.sec_tc1_capabilities "
            "WHERE purpose IN ('M21_ACK_BATCH_READ','M27_ACK_BATCH_READ')"
        )
    ).scalar_one()
    if retained:
        raise RuntimeError("Refusing 0048 downgrade while batch capability rows exist")
    for signature in _BATCH_FUNCTIONS:
        bind.execute(sa.text(f"REVOKE ALL ON FUNCTION public.{signature} FROM PUBLIC, education_app, education_context_issuer"))
    for signature in reversed(_BATCH_FUNCTIONS):
        bind.execute(sa.text(f"DROP FUNCTION IF EXISTS public.{signature} CASCADE"))
    bind.execute(sa.text("ALTER TABLE public.sec_tc1_capabilities DROP CONSTRAINT ck_sec_tc1_binding_mode"))
    bind.execute(sa.text("ALTER TABLE public.sec_tc1_capabilities DROP CONSTRAINT ck_sec_tc1_target_set_digest"))
    bind.execute(sa.text("ALTER TABLE public.sec_tc1_capabilities DROP CONSTRAINT ck_sec_tc1_purpose"))
    bind.execute(
        sa.text(
            "ALTER TABLE public.sec_tc1_capabilities ADD CONSTRAINT ck_sec_tc1_purpose "
            "CHECK (purpose IN ('M13_NOTICE_ACK','M21_ACK_LINK','M21_ACK_CORRECT',"
            "'M21_ACK_READ','M27_ACK_LINK','M27_ACK_CORRECT','M27_ACK_READ'))"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE public.sec_tc1_capabilities DROP COLUMN target_set_digest"
        )
    )
    bind.execute(
        sa.text(
            "ALTER TABLE public.sec_tc1_capabilities ALTER COLUMN target_id SET NOT NULL"
        )
    )
