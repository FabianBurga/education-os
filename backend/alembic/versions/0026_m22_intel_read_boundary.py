"""M22 intelligence role/scope read boundary.

Revision ID: 0026_m22_intel_read_boundary
Revises: 0025_m22_intelligence_foundation
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "0026_m22_intel_read_boundary"
down_revision: str | None = "0025_m22_intelligence_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"

READ_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR", "TEACHER")
MANAGER_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR")

PERMISSIONS = (
    ("intelligence.read", "Read authorized institutional intelligence and student-level signals."),
    ("intelligence.manage", "Project and manage institutional intelligence state and signals."),
)

INTELLIGENCE_TABLES = (
    "intelligence_signals",
    "student_intelligence_snapshots",
    "cohort_intelligence_daily",
    "institution_intelligence_daily",
)
STUDENT_SCOPED_TABLES = (
    "intelligence_signals",
    "student_intelligence_snapshots",
)
MANAGER_ONLY_TABLES = (
    "cohort_intelligence_daily",
    "institution_intelligence_daily",
)


def _permission_id(bind, key: str, description: str):
    permission_id = bind.execute(
        sa.text("SELECT id FROM permissions WHERE key = :key"),
        {"key": key},
    ).scalar_one_or_none()
    if permission_id is not None:
        return permission_id

    permission_id = uuid4()
    bind.execute(
        sa.text(
            "INSERT INTO permissions (id, key, description) "
            "VALUES (:id, :key, :description)"
        ),
        {"id": permission_id, "key": key, "description": description},
    )
    return permission_id


def _grant_to_role_keys(bind, permission_id, role_keys: tuple[str, ...]) -> None:
    role_ids = bind.execute(
        sa.text("SELECT id FROM roles WHERE key = ANY(:role_keys)"),
        {"role_keys": list(role_keys)},
    ).scalars().all()
    for role_id in role_ids:
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "VALUES (:role_id, :permission_id) ON CONFLICT DO NOTHING"
            ),
            {"role_id": role_id, "permission_id": permission_id},
        )


def _drop_all_policies(table: str) -> None:
    op.execute(
        f"""
        DO $$
        DECLARE policy_row record;
        BEGIN
            FOR policy_row IN
                SELECT policyname
                FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = '{table}'
            LOOP
                EXECUTE format(
                    'DROP POLICY %I ON {table}',
                    policy_row.policyname
                );
            END LOOP;
        END
        $$;
        """
    )


def _create_functions() -> None:
    op.execute(
        f"""
        CREATE FUNCTION education_os_intelligence_has_permission(
            required_permission text
        )
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM memberships m
                JOIN membership_roles mr ON mr.membership_id = m.id
                JOIN role_permissions rp ON rp.role_id = mr.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE m.user_id = {USER_CTX}
                  AND m.institution_id = {INST_CTX}
                  AND m.status = 'ACTIVE'
                  AND p.key = required_permission
            )
        $$;
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "education_os_intelligence_has_permission(text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION "
        "education_os_intelligence_has_permission(text) TO education_app"
    )

    op.execute(
        f"""
        CREATE FUNCTION education_os_intelligence_is_manager()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM memberships m
                JOIN membership_roles mr ON mr.membership_id = m.id
                JOIN roles r ON r.id = mr.role_id
                WHERE m.user_id = {USER_CTX}
                  AND m.institution_id = {INST_CTX}
                  AND m.status = 'ACTIVE'
                  AND r.key IN (
                      'SYSTEM_ADMIN',
                      'RECTOR',
                      'ACADEMIC_COORDINATOR'
                  )
            )
        $$;
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION education_os_intelligence_is_manager() "
        "FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION education_os_intelligence_is_manager() "
        "TO education_app"
    )

    op.execute(
        f"""
        CREATE FUNCTION education_os_intelligence_teacher_student_scope(
            target_student_profile_id uuid,
            target_academic_period_id uuid
        )
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT EXISTS (
                SELECT 1
                FROM user_accounts ua
                JOIN staff_profiles sp
                  ON sp.person_id = ua.person_id
                 AND sp.institution_id = {INST_CTX}
                 AND sp.status = 'ACTIVE'
                JOIN teaching_assignments ta
                  ON ta.staff_profile_id = sp.id
                 AND ta.institution_id = {INST_CTX}
                JOIN course_offerings co
                  ON co.id = ta.course_offering_id
                 AND co.institution_id = {INST_CTX}
                 AND co.status = 'ACTIVE'
                JOIN student_section_assignments ssa
                  ON ssa.section_id = co.section_id
                 AND ssa.institution_id = {INST_CTX}
                 AND ssa.status = 'ACTIVE'
                JOIN enrollments e
                  ON e.id = ssa.enrollment_id
                 AND e.institution_id = {INST_CTX}
                 AND e.status = 'ACTIVE'
                WHERE ua.id = {USER_CTX}
                  AND ua.is_active = true
                  AND e.student_profile_id = target_student_profile_id
                  AND target_academic_period_id IS NOT NULL
                  AND e.academic_period_id = target_academic_period_id
                  AND ssa.academic_period_id = target_academic_period_id
                  AND co.academic_period_id = target_academic_period_id
                  AND (ta.starts_on IS NULL OR ta.starts_on <= CURRENT_DATE)
                  AND (ta.ends_on IS NULL OR ta.ends_on >= CURRENT_DATE)
            )
        $$;
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "education_os_intelligence_teacher_student_scope(uuid, uuid) "
        "FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION "
        "education_os_intelligence_teacher_student_scope(uuid, uuid) "
        "TO education_app"
    )


def _create_write_policies(table: str) -> None:
    write_gate = (
        f"{TENANT} "
        "AND education_os_intelligence_has_permission('intelligence.manage') "
        "AND education_os_intelligence_is_manager()"
    )
    op.execute(
        f'CREATE POLICY {table}_insert ON "{table}" '
        f"FOR INSERT TO education_app WITH CHECK ({write_gate})"
    )
    op.execute(
        f'CREATE POLICY {table}_update ON "{table}" '
        f"FOR UPDATE TO education_app USING ({write_gate}) "
        f"WITH CHECK ({write_gate})"
    )
    op.execute(
        f'CREATE POLICY {table}_delete ON "{table}" '
        f"FOR DELETE TO education_app USING ({write_gate})"
    )


def _create_student_scoped_policies(table: str) -> None:
    select_policy_name = (
        "intelligence_signals_tenant_isolation"
        if table == "intelligence_signals"
        else f"{table}_select"
    )
    op.execute(
        f"""
        CREATE POLICY {select_policy_name}
        ON "{table}"
        FOR SELECT TO education_app
        USING (
            {TENANT}
            AND education_os_intelligence_has_permission('intelligence.read')
            AND (
                education_os_intelligence_is_manager()
                OR education_os_intelligence_teacher_student_scope(
                    student_profile_id,
                    academic_period_id
                )
            )
        )
        """
    )
    _create_write_policies(table)


def _create_manager_only_policies(table: str) -> None:
    op.execute(
        f"""
        CREATE POLICY {table}_select
        ON "{table}"
        FOR SELECT TO education_app
        USING (
            {TENANT}
            AND education_os_intelligence_has_permission('intelligence.read')
            AND education_os_intelligence_is_manager()
        )
        """
    )
    _create_write_policies(table)


def upgrade() -> None:
    bind = op.get_bind()
    permission_ids = {
        key: _permission_id(bind, key, description)
        for key, description in PERMISSIONS
    }
    _grant_to_role_keys(bind, permission_ids["intelligence.read"], READ_ROLE_KEYS)
    _grant_to_role_keys(
        bind,
        permission_ids["intelligence.manage"],
        MANAGER_ROLE_KEYS,
    )
    _create_functions()

    for table in INTELLIGENCE_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        _drop_all_policies(table)

    for table in STUDENT_SCOPED_TABLES:
        _create_student_scoped_policies(table)
    for table in MANAGER_ONLY_TABLES:
        _create_manager_only_policies(table)


def downgrade() -> None:
    bind = op.get_bind()

    for table in INTELLIGENCE_TABLES:
        _drop_all_policies(table)
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation
            ON "{table}"
            FOR ALL TO education_app
            USING ({TENANT})
            WITH CHECK ({TENANT})
            """
        )

    op.execute(
        "DROP FUNCTION IF EXISTS "
        "education_os_intelligence_teacher_student_scope(uuid, uuid)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS education_os_intelligence_is_manager()"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "education_os_intelligence_has_permission(text)"
    )

    permission_rows = bind.execute(
        sa.text(
            "SELECT id FROM permissions "
            "WHERE key IN ('intelligence.read', 'intelligence.manage')"
        )
    ).scalars().all()
    for permission_id in permission_rows:
        bind.execute(
            sa.text(
                "DELETE FROM role_permissions WHERE permission_id = :permission_id"
            ),
            {"permission_id": permission_id},
        )
    bind.execute(
        sa.text(
            "DELETE FROM permissions "
            "WHERE key IN ('intelligence.read', 'intelligence.manage')"
        )
    )
