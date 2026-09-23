"""M27 deterministic accountability case projection foundation.

Revision ID: 0038_m27_accountability_foundation
Revises: 0037_m26_mentor_briefing
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0038_m27_accountability"
down_revision: str | None = "0037_m26_mentor_briefing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"


def _permission(bind, key: str, description: str):
    value = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar_one_or_none()
    if value is None:
        value = uuid4()
        bind.execute(
            sa.text("INSERT INTO permissions (id, key, description) VALUES (:id, :key, :description)"),
            {"id": value, "key": key, "description": description},
        )
    return value


def _grant(bind, permission_id, roles: tuple[str, ...]) -> None:
    for role_id in bind.execute(
        sa.text("SELECT id FROM roles WHERE key = ANY(CAST(:keys AS text[]))"),
        {"keys": list(roles)},
    ).scalars():
        bind.execute(
            sa.text(
                "INSERT INTO role_permissions (role_id, permission_id) "
                "VALUES (:role_id, :permission_id) ON CONFLICT DO NOTHING"
            ),
            {"role_id": role_id, "permission_id": permission_id},
        )


def upgrade() -> None:
    bind = op.get_bind()
    view_permission = _permission(bind, "accountability.view", "View scoped accountability cases and lineage.")
    manage_permission = _permission(bind, "accountability.manage", "Project scoped accountability cases and lineage.")
    manager_roles = ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR")
    _grant(bind, view_permission, manager_roles)
    _grant(bind, manage_permission, manager_roles)

    op.create_table(
        "accountability_cases",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("subject_type", sa.String(80), nullable=False),
        sa.Column("subject_id", UUID, nullable=False),
        sa.Column("source_category", sa.String(120), nullable=False),
        sa.Column("normalized_category", sa.String(120), nullable=False),
        sa.Column("category_mapping_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("identity_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("identity_key_sha256", sa.String(64), nullable=False),
        sa.Column("episode_anchor", sa.String(180), nullable=False),
        sa.Column("lifecycle", sa.String(30), nullable=False, server_default="OPEN"),
        sa.Column("owner_state", sa.String(20), nullable=False, server_default="UNASSIGNED"),
        sa.Column("primary_owner_user_id", UUID, nullable=True),
        sa.Column("recurrence_classification", sa.String(30), nullable=False, server_default="NEW_EPISODE"),
        sa.Column("related_case_id", UUID, nullable=True),
        sa.Column("projection_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["institution_id", "organization_id"], ["institutions.id", "institutions.organization_id"], name="fk_accountability_cases_tenant", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["primary_owner_user_id"], ["user_accounts.id"], name="fk_accountability_cases_owner", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_case_id"], ["accountability_cases.id"], name="fk_accountability_cases_related", ondelete="RESTRICT"),
        sa.CheckConstraint("category_mapping_version >= 1", name="ck_accountability_cases_category_mapping_version"),
        sa.CheckConstraint("identity_version >= 1", name="ck_accountability_cases_identity_version"),
        sa.CheckConstraint("projection_version >= 1", name="ck_accountability_cases_projection_version"),
        sa.CheckConstraint("identity_key_sha256 ~ '^[0-9a-f]{64}$'", name="ck_accountability_cases_identity_sha"),
        sa.CheckConstraint("lifecycle IN ('OPEN','REOPENED','RESOLVED')", name="ck_accountability_cases_lifecycle"),
        sa.CheckConstraint("owner_state IN ('UNASSIGNED','ASSIGNED')", name="ck_accountability_cases_owner_state"),
        sa.CheckConstraint("(owner_state = 'UNASSIGNED' AND primary_owner_user_id IS NULL) OR (owner_state = 'ASSIGNED' AND primary_owner_user_id IS NOT NULL)", name="ck_accountability_cases_owner_consistency"),
        sa.CheckConstraint("recurrence_classification IN ('NEW_EPISODE','SAME_ACTIVE_EPISODE','REOPENED_CASE','NEW_RELATED_EPISODE','NEW_CATEGORY_CASE')", name="ck_accountability_cases_recurrence"),
        sa.UniqueConstraint("institution_id", "identity_version", "identity_key_sha256", name="uq_accountability_cases_identity"),
        sa.UniqueConstraint("institution_id", "organization_id", "id", name="uq_accountability_cases_tenant_id"),
    )
    op.create_table(
        "accountability_case_sources",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("case_id", UUID, nullable=False),
        sa.Column("source_kind", sa.String(30), nullable=False),
        sa.Column("source_entity_id", UUID, nullable=False),
        sa.Column("source_event_id", UUID, nullable=True),
        sa.Column("source_event_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_category", sa.String(120), nullable=False),
        sa.Column("source_provenance_sha256", sa.String(64), nullable=False),
        sa.Column("source_fingerprint_sha256", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["institution_id", "organization_id", "case_id"], ["accountability_cases.institution_id", "accountability_cases.organization_id", "accountability_cases.id"], name="fk_accountability_case_sources_case", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_event_id"], ["event_ledger.id"], name="fk_accountability_case_sources_event", ondelete="RESTRICT"),
        sa.CheckConstraint("source_kind IN ('M18_LEDGER','M21','M22')", name="ck_accountability_case_sources_kind"),
        sa.CheckConstraint("source_event_version >= 1", name="ck_accountability_case_sources_event_version"),
        sa.CheckConstraint("source_provenance_sha256 ~ '^[0-9a-f]{64}$'", name="ck_accountability_case_sources_provenance_sha"),
        sa.CheckConstraint("source_fingerprint_sha256 ~ '^[0-9a-f]{64}$'", name="ck_accountability_case_sources_fingerprint_sha"),
        sa.UniqueConstraint("institution_id", "source_fingerprint_sha256", name="uq_accountability_case_sources_fingerprint"),
    )
    for table in ("accountability_cases", "accountability_case_sources"):
        op.create_index(f"ix_{table}_tenant", table, ["organization_id", "institution_id", "created_at"])
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute('GRANT SELECT, INSERT' + (', UPDATE' if table == "accountability_cases" else '') + f' ON "{table}" TO education_app')
        op.execute(f"""
            CREATE POLICY {table}_select ON {table}
            FOR SELECT TO education_app
            USING ({TENANT} AND EXISTS (
                SELECT 1 FROM memberships m JOIN membership_roles mr ON mr.membership_id = m.id
                JOIN role_permissions rp ON rp.role_id = mr.role_id JOIN permissions p ON p.id = rp.permission_id
                WHERE m.user_id = {USER_CTX} AND m.institution_id = {INST_CTX}
                  AND m.status = 'ACTIVE' AND p.key = 'accountability.view'
            ))
        """)
        op.execute(f"""
            CREATE POLICY {table}_insert ON {table}
            FOR INSERT TO education_app
            WITH CHECK ({TENANT} AND EXISTS (
                SELECT 1 FROM memberships m JOIN membership_roles mr ON mr.membership_id = m.id
                JOIN role_permissions rp ON rp.role_id = mr.role_id JOIN permissions p ON p.id = rp.permission_id
                WHERE m.user_id = {USER_CTX} AND m.institution_id = {INST_CTX}
                  AND m.status = 'ACTIVE' AND p.key = 'accountability.manage'
            ))
        """)
    op.execute("""
        CREATE POLICY accountability_cases_update ON accountability_cases
        FOR UPDATE TO education_app
        USING (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
           AND institution_id = NULLIF(current_setting('app.institution_id', true), '')::uuid
           AND EXISTS (
               SELECT 1 FROM memberships m JOIN membership_roles mr ON mr.membership_id = m.id
               JOIN role_permissions rp ON rp.role_id = mr.role_id JOIN permissions p ON p.id = rp.permission_id
               WHERE m.user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
                 AND m.institution_id = NULLIF(current_setting('app.institution_id', true), '')::uuid
                 AND m.status = 'ACTIVE' AND p.key = 'accountability.manage'))
        WITH CHECK (organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
           AND institution_id = NULLIF(current_setting('app.institution_id', true), '')::uuid
           AND EXISTS (
               SELECT 1 FROM memberships m JOIN membership_roles mr ON mr.membership_id = m.id
               JOIN role_permissions rp ON rp.role_id = mr.role_id JOIN permissions p ON p.id = rp.permission_id
               WHERE m.user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
                 AND m.institution_id = NULLIF(current_setting('app.institution_id', true), '')::uuid
                 AND m.status = 'ACTIVE' AND p.key = 'accountability.manage'))
    """)


def downgrade() -> None:
    op.drop_table("accountability_case_sources")
    op.drop_table("accountability_cases")
    bind = op.get_bind()
    permission_ids = bind.execute(sa.text("SELECT id FROM permissions WHERE key IN ('accountability.view','accountability.manage')")).scalars().all()
    for permission_id in permission_ids:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :permission_id"), {"permission_id": permission_id})
    bind.execute(sa.text("DELETE FROM permissions WHERE key IN ('accountability.view','accountability.manage')"))
