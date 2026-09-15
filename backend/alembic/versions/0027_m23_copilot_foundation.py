"""M23 governed Copilot context/evidence foundation.

Revision ID: 0027_m23_copilot_foundation
Revises: 0026_m22_intel_read_boundary
"""

from collections.abc import Sequence
from hashlib import sha256
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0027_m23_copilot_foundation"
down_revision: str | None = "0026_m22_intel_read_boundary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"

PERMISSIONS = (
    (
        "copilot.use",
        "Use governed Copilot within existing authorized institutional scope.",
    ),
    (
        "copilot.manage",
        "Manage governed Copilot policy, prompts, and provider eligibility.",
    ),
    (
        "copilot.action.approve",
        "Approve governed Copilot action proposals when otherwise authorized.",
    ),
)
USE_ROLES = (
    "SYSTEM_ADMIN",
    "RECTOR",
    "ACADEMIC_COORDINATOR",
    "TEACHER",
)
MANAGER_ROLES = (
    "SYSTEM_ADMIN",
    "RECTOR",
    "ACADEMIC_COORDINATOR",
)

REGISTRY_TABLES = (
    "copilot_policy_versions",
    "copilot_prompt_versions",
    "copilot_model_registry",
)
RUNTIME_TABLES = (
    "copilot_runs",
    "copilot_evidence_refs",
)
ALL_TABLES = REGISTRY_TABLES + RUNTIME_TABLES

PROMPTS = {
    "INSTITUTION_RISK_SUMMARY": (
        "institution_risk_summary",
        "Summarize only the authorized institutional evidence supplied by "
        "Education OS. Cite evidence references and state uncertainty. "
        "Do not make autonomous decisions or execute actions.",
    ),
    "STUDENT_SUPPORT_SUMMARY": (
        "student_support_summary",
        "Summarize only the authorized student-support evidence supplied by "
        "Education OS. Cite evidence references and state uncertainty. "
        "Do not diagnose, sanction, or execute actions.",
    ),
}


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
        {
            "id": permission_id,
            "key": key,
            "description": description,
        },
    )
    return permission_id


def _grant_to_roles(bind, permission_id, role_keys: tuple[str, ...]) -> None:
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
            {
                "role_id": role_id,
                "permission_id": permission_id,
            },
        )


def _tenant_fk(name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["institution_id", "organization_id"],
        ["institutions.id", "institutions.organization_id"],
        name=name,
        ondelete="RESTRICT",
    )


def _tenant_indexes(table: str) -> None:
    op.create_index(
        f"ix_{table}_organization",
        table,
        ["organization_id"],
    )
    op.create_index(
        f"ix_{table}_institution",
        table,
        ["institution_id"],
    )


def _create_helper_functions() -> None:
    op.execute(
        f"""
        CREATE FUNCTION education_os_copilot_has_permission(
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
        "education_os_copilot_has_permission(text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION "
        "education_os_copilot_has_permission(text) TO education_app"
    )

    op.execute(
        f"""
        CREATE FUNCTION education_os_copilot_is_manager()
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
        "REVOKE ALL ON FUNCTION education_os_copilot_is_manager() FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION education_os_copilot_is_manager() "
        "TO education_app"
    )

    op.execute(
        f"""
        CREATE FUNCTION education_os_copilot_run_visible(
            target_actor_user_id uuid
        )
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT (
                target_actor_user_id = {USER_CTX}
                OR education_os_copilot_is_manager()
            )
        $$;
        """
    )
    op.execute(
        "REVOKE ALL ON FUNCTION "
        "education_os_copilot_run_visible(uuid) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION "
        "education_os_copilot_run_visible(uuid) TO education_app"
    )


def _enable_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO education_app'
    )


def _registry_policies(table: str) -> None:
    read_gate = (
        f"{TENANT} "
        "AND education_os_copilot_has_permission('copilot.use')"
    )
    write_gate = (
        f"{TENANT} "
        "AND education_os_copilot_has_permission('copilot.manage') "
        "AND education_os_copilot_is_manager()"
    )
    op.execute(
        f'CREATE POLICY {table}_select ON "{table}" '
        f"FOR SELECT TO education_app USING ({read_gate})"
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


def _run_policies() -> None:
    read_gate = (
        f"{TENANT} "
        "AND education_os_copilot_has_permission('copilot.use') "
        "AND education_os_copilot_run_visible(actor_user_id)"
    )
    own_gate = (
        f"{TENANT} "
        "AND actor_user_id = "
        f"{USER_CTX} "
        "AND education_os_copilot_has_permission('copilot.use')"
    )
    manage_gate = (
        f"{TENANT} "
        "AND education_os_copilot_has_permission('copilot.manage') "
        "AND education_os_copilot_is_manager()"
    )
    update_gate = f"(({own_gate}) OR ({manage_gate}))"

    op.execute(
        'CREATE POLICY copilot_runs_select ON "copilot_runs" '
        f"FOR SELECT TO education_app USING ({read_gate})"
    )
    op.execute(
        'CREATE POLICY copilot_runs_insert ON "copilot_runs" '
        f"FOR INSERT TO education_app WITH CHECK ({own_gate})"
    )
    op.execute(
        'CREATE POLICY copilot_runs_update ON "copilot_runs" '
        f"FOR UPDATE TO education_app USING ({update_gate}) "
        f"WITH CHECK ({update_gate})"
    )
    op.execute(
        'CREATE POLICY copilot_runs_delete ON "copilot_runs" '
        f"FOR DELETE TO education_app USING ({manage_gate})"
    )


def _evidence_policies() -> None:
    parent_visible = (
        "EXISTS ("
        "SELECT 1 FROM copilot_runs cr "
        "WHERE cr.id = run_id "
        "AND cr.organization_id = organization_id "
        "AND cr.institution_id = institution_id "
        "AND education_os_copilot_run_visible(cr.actor_user_id)"
        ")"
    )
    read_gate = (
        f"{TENANT} "
        "AND education_os_copilot_has_permission('copilot.use') "
        f"AND {parent_visible}"
    )
    write_gate = (
        f"{TENANT} "
        "AND education_os_copilot_has_permission('copilot.use') "
        f"AND {parent_visible}"
    )
    manage_gate = (
        f"{TENANT} "
        "AND education_os_copilot_has_permission('copilot.manage') "
        "AND education_os_copilot_is_manager()"
    )

    op.execute(
        'CREATE POLICY copilot_evidence_refs_select '
        'ON "copilot_evidence_refs" '
        f"FOR SELECT TO education_app USING ({read_gate})"
    )
    op.execute(
        'CREATE POLICY copilot_evidence_refs_insert '
        'ON "copilot_evidence_refs" '
        f"FOR INSERT TO education_app WITH CHECK ({write_gate})"
    )
    op.execute(
        'CREATE POLICY copilot_evidence_refs_update '
        'ON "copilot_evidence_refs" '
        f"FOR UPDATE TO education_app USING ({write_gate}) "
        f"WITH CHECK ({write_gate})"
    )
    op.execute(
        'CREATE POLICY copilot_evidence_refs_delete '
        'ON "copilot_evidence_refs" '
        f"FOR DELETE TO education_app USING ({manage_gate})"
    )


def _seed_defaults(bind) -> None:
    institutions = bind.execute(
        sa.text("SELECT id, organization_id FROM institutions")
    ).all()

    for institution_id, organization_id in institutions:
        policy_id = uuid4()
        bind.execute(
            sa.text(
                """
                INSERT INTO copilot_policy_versions (
                    id,
                    organization_id,
                    institution_id,
                    policy_key,
                    version,
                    status,
                    max_daily_runs_per_user,
                    max_evidence_items,
                    allow_action_proposals,
                    config_json
                )
                VALUES (
                    :id,
                    :organization_id,
                    :institution_id,
                    'governed_copilot',
                    1,
                    'ENABLED',
                    50,
                    30,
                    false,
                    CAST(:config_json AS jsonb)
                )
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "id": policy_id,
                "organization_id": institution_id
                if organization_id is None
                else organization_id,
                "institution_id": institution_id,
                "config_json": "{}",
            },
        )

        for intent, (prompt_key, template_text) in PROMPTS.items():
            bind.execute(
                sa.text(
                    """
                    INSERT INTO copilot_prompt_versions (
                        id,
                        organization_id,
                        institution_id,
                        prompt_key,
                        version,
                        intent,
                        output_schema_version,
                        policy_key,
                        policy_version,
                        status,
                        template_text,
                        template_sha256
                    )
                    VALUES (
                        :id,
                        :organization_id,
                        :institution_id,
                        :prompt_key,
                        1,
                        :intent,
                        'copilot.advisory.v1',
                        'governed_copilot',
                        1,
                        'ENABLED',
                        :template_text,
                        :template_sha256
                    )
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "id": uuid4(),
                    "organization_id": institution_id
                    if organization_id is None
                    else organization_id,
                    "institution_id": institution_id,
                    "prompt_key": prompt_key,
                    "intent": intent,
                    "template_text": template_text,
                    "template_sha256": sha256(
                        template_text.encode("utf-8")
                    ).hexdigest(),
                },
            )


def upgrade() -> None:
    bind = op.get_bind()

    permission_ids = {
        key: _permission_id(bind, key, description)
        for key, description in PERMISSIONS
    }
    _grant_to_roles(bind, permission_ids["copilot.use"], USE_ROLES)
    _grant_to_roles(bind, permission_ids["copilot.manage"], MANAGER_ROLES)
    _grant_to_roles(
        bind,
        permission_ids["copilot.action.approve"],
        MANAGER_ROLES,
    )

    op.create_table(
        "copilot_policy_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("policy_key", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "max_daily_runs_per_user",
            sa.Integer(),
            nullable=False,
            server_default="50",
        ),
        sa.Column(
            "max_evidence_items",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
        sa.Column(
            "allow_action_proposals",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "config_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by_user_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        _tenant_fk("fk_copilot_policy_versions_tenant"),
        sa.CheckConstraint(
            "version >= 1",
            name="ck_copilot_policy_versions_version",
        ),
        sa.CheckConstraint(
            "status IN ('ENABLED','DISABLED')",
            name="ck_copilot_policy_versions_status",
        ),
        sa.CheckConstraint(
            "max_daily_runs_per_user >= 1",
            name="ck_copilot_policy_versions_daily_limit",
        ),
        sa.CheckConstraint(
            "max_evidence_items BETWEEN 1 AND 100",
            name="ck_copilot_policy_versions_evidence_limit",
        ),
        sa.UniqueConstraint(
            "institution_id",
            "policy_key",
            "version",
            name="uq_copilot_policy_version",
        ),
    )
    _tenant_indexes("copilot_policy_versions")
    op.create_index(
        "ix_copilot_policy_versions_lookup",
        "copilot_policy_versions",
        ["institution_id", "policy_key", "status", "version"],
    )

    op.create_table(
        "copilot_prompt_versions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("prompt_key", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("intent", sa.String(80), nullable=False),
        sa.Column("output_schema_version", sa.String(80), nullable=False),
        sa.Column("policy_key", sa.String(120), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("template_text", sa.Text(), nullable=False),
        sa.Column("template_sha256", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        _tenant_fk("fk_copilot_prompt_versions_tenant"),
        sa.CheckConstraint(
            "version >= 1 AND policy_version >= 1",
            name="ck_copilot_prompt_versions_versions",
        ),
        sa.CheckConstraint(
            "status IN ('ENABLED','DISABLED')",
            name="ck_copilot_prompt_versions_status",
        ),
        sa.CheckConstraint(
            "length(template_sha256) = 64",
            name="ck_copilot_prompt_versions_sha",
        ),
        sa.UniqueConstraint(
            "institution_id",
            "prompt_key",
            "version",
            name="uq_copilot_prompt_version",
        ),
    )
    _tenant_indexes("copilot_prompt_versions")
    op.create_index(
        "ix_copilot_prompt_versions_lookup",
        "copilot_prompt_versions",
        ["institution_id", "intent", "status", "version"],
    )

    op.create_table(
        "copilot_model_registry",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("provider_key", sa.String(80), nullable=False),
        sa.Column("model_key", sa.String(160), nullable=False),
        sa.Column(
            "config_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("capability_class", sa.String(40), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "policy_eligible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "max_input_tokens",
            sa.Integer(),
            nullable=False,
            server_default="4096",
        ),
        sa.Column(
            "metadata_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by_user_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        _tenant_fk("fk_copilot_model_registry_tenant"),
        sa.CheckConstraint(
            "config_version >= 1 AND max_input_tokens >= 1",
            name="ck_copilot_model_registry_limits",
        ),
        sa.UniqueConstraint(
            "institution_id",
            "provider_key",
            "model_key",
            "config_version",
            name="uq_copilot_model_registry_version",
        ),
    )
    _tenant_indexes("copilot_model_registry")
    op.create_index(
        "ix_copilot_model_registry_lookup",
        "copilot_model_registry",
        [
            "institution_id",
            "enabled",
            "policy_eligible",
            "config_version",
        ],
    )

    op.create_table(
        "copilot_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("actor_user_id", UUID, nullable=False),
        sa.Column("intent", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("target_student_profile_id", UUID, nullable=True),
        sa.Column("policy_key", sa.String(120), nullable=True),
        sa.Column("policy_version", sa.Integer(), nullable=True),
        sa.Column("prompt_key", sa.String(120), nullable=True),
        sa.Column("prompt_version", sa.Integer(), nullable=True),
        sa.Column("provider_key", sa.String(80), nullable=True),
        sa.Column("model_key", sa.String(160), nullable=True),
        sa.Column("model_config_version", sa.Integer(), nullable=True),
        sa.Column("evidence_manifest_sha256", sa.String(64), nullable=True),
        sa.Column("output_schema_version", sa.String(80), nullable=True),
        sa.Column("failure_code", sa.String(80), nullable=True),
        sa.Column(
            "usage_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "cost_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        _tenant_fk("fk_copilot_runs_tenant"),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["user_accounts.id"],
            name="fk_copilot_runs_actor",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'REQUESTED','READY','REFUSED','FAILED','COMPLETED'"
            ")",
            name="ck_copilot_runs_status",
        ),
        sa.CheckConstraint(
            "length(request_sha256) = 64",
            name="ck_copilot_runs_request_sha",
        ),
        sa.CheckConstraint(
            "evidence_manifest_sha256 IS NULL "
            "OR length(evidence_manifest_sha256) = 64",
            name="ck_copilot_runs_manifest_sha",
        ),
    )
    _tenant_indexes("copilot_runs")
    op.create_index(
        "ix_copilot_runs_actor_created",
        "copilot_runs",
        ["institution_id", "actor_user_id", "created_at"],
    )
    op.create_index(
        "ix_copilot_runs_status_created",
        "copilot_runs",
        ["institution_id", "status", "created_at"],
    )

    op.create_table(
        "copilot_evidence_refs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("evidence_type", sa.String(80), nullable=False),
        sa.Column("source_module", sa.String(80), nullable=False),
        sa.Column("source_entity_type", sa.String(120), nullable=False),
        sa.Column("source_entity_id", UUID, nullable=True),
        sa.Column("reference_key", sa.String(220), nullable=False),
        sa.Column("freshness_status", sa.String(20), nullable=False),
        sa.Column("source_version", sa.String(160), nullable=True),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column(
            "scope_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "content_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        _tenant_fk("fk_copilot_evidence_refs_tenant"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["copilot_runs.id"],
            name="fk_copilot_evidence_refs_run",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "freshness_status IN ('CURRENT','DELAYED','STALE','UNKNOWN')",
            name="ck_copilot_evidence_refs_freshness",
        ),
        sa.CheckConstraint(
            "length(evidence_sha256) = 64",
            name="ck_copilot_evidence_refs_sha",
        ),
        sa.UniqueConstraint(
            "run_id",
            "reference_key",
            name="uq_copilot_evidence_run_reference",
        ),
    )
    _tenant_indexes("copilot_evidence_refs")
    op.create_index(
        "ix_copilot_evidence_refs_run",
        "copilot_evidence_refs",
        ["run_id"],
    )

    _create_helper_functions()
    for table in ALL_TABLES:
        _enable_rls(table)
    for table in REGISTRY_TABLES:
        _registry_policies(table)
    _run_policies()
    _evidence_policies()

    _seed_defaults(bind)


def downgrade() -> None:
    bind = op.get_bind()

    for table in reversed(ALL_TABLES):
        op.drop_table(table)

    op.execute(
        "DROP FUNCTION IF EXISTS education_os_copilot_run_visible(uuid)"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS education_os_copilot_is_manager()"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS "
        "education_os_copilot_has_permission(text)"
    )

    permission_rows = bind.execute(
        sa.text(
            "SELECT id FROM permissions "
            "WHERE key IN ("
            "'copilot.use',"
            "'copilot.manage',"
            "'copilot.action.approve'"
            ")"
        )
    ).scalars().all()
    for permission_id in permission_rows:
        bind.execute(
            sa.text(
                "DELETE FROM role_permissions "
                "WHERE permission_id = :permission_id"
            ),
            {"permission_id": permission_id},
        )
    bind.execute(
        sa.text(
            "DELETE FROM permissions "
            "WHERE key IN ("
            "'copilot.use',"
            "'copilot.manage',"
            "'copilot.action.approve'"
            ")"
        )
    )
