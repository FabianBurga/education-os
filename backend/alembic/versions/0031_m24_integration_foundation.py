"""M24 tenant-scoped Integration Hub foundation.

Revision ID: 0031_m24_integration_foundation
Revises: 0030_m23_action_proposals
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0031_m24_integration_foundation"
down_revision: str | None = "0030_m23_action_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"

PERMISSIONS = (
    ("integrations.view", "View tenant-scoped integration connectors and runs."),
    ("integrations.manage", "Manage tenant-scoped integration connector definitions."),
    ("integrations.run", "Initiate governed tenant-scoped integration runs."),
    ("integrations.audit.read", "Read tenant-scoped integration audit and provenance."),
)


def _permission_id(bind, key: str, description: str):
    value = bind.execute(sa.text("SELECT id FROM permissions WHERE key = :key"), {"key": key}).scalar_one_or_none()
    if value is not None:
        return value
    value = uuid4()
    bind.execute(sa.text("INSERT INTO permissions (id, key, description) VALUES (:id, :key, :description)"),
                 {"id": value, "key": key, "description": description})
    return value


def _grant(bind, permission_id, role_keys: tuple[str, ...]) -> None:
    for role_id in bind.execute(sa.text("SELECT id FROM roles WHERE key = ANY(CAST(:keys AS text[]))"), {"keys": list(role_keys)}).scalars():
        bind.execute(sa.text("INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :permission_id) ON CONFLICT DO NOTHING"),
                     {"role_id": role_id, "permission_id": permission_id})


def upgrade() -> None:
    op.create_table(
        "integration_connectors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_key", sa.String(length=120), nullable=False),
        sa.Column("connector_type", sa.String(length=40), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="ENABLED"),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("configuration_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("connector_key ~ '^[a-z][a-z0-9_.-]{2,119}$'", name="ck_integration_connectors_key"),
        sa.CheckConstraint("connector_type = 'FILE_CSV'", name="ck_integration_connectors_type"),
        sa.CheckConstraint("status IN ('ENABLED','DISABLED')", name="ck_integration_connectors_status"),
        sa.CheckConstraint("config_version >= 1", name="ck_integration_connectors_config_version"),
        sa.CheckConstraint("jsonb_typeof(configuration_json) = 'object'", name="ck_integration_connectors_config_object"),
        sa.UniqueConstraint("institution_id", "connector_key", name="uq_integration_connectors_key"),
    )
    op.create_index("ix_integration_connectors_tenant", "integration_connectors", ["organization_id", "institution_id", "created_at", "id"])

    op.create_table(
        "integration_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("integration_connectors.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("mapping_key", sa.String(length=120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=False),
        sa.Column("mapping_sha256", sa.String(length=64), nullable=False),
        sa.Column("mapping_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("mapping_key ~ '^[a-z][a-z0-9_.-]{2,119}$'", name="ck_integration_mappings_key"),
        sa.CheckConstraint("version >= 1", name="ck_integration_mappings_version"),
        sa.CheckConstraint("mapping_sha256 ~ '^[0-9a-f]{64}$'", name="ck_integration_mappings_sha"),
        sa.CheckConstraint("jsonb_typeof(mapping_json) = 'object'", name="ck_integration_mappings_object"),
        sa.UniqueConstraint("connector_id", "mapping_key", "version", name="uq_integration_mappings_version"),
    )
    op.create_index("ix_integration_mappings_tenant", "integration_mappings", ["organization_id", "institution_id", "connector_id"])

    op.create_table(
        "integration_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connector_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("integration_connectors.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("mapping_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("integration_mappings.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("initiated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("source_fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("connector_config_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_kind = 'FILE'", name="ck_integration_runs_source_kind"),
        sa.CheckConstraint("mode IN ('DRY_RUN','APPLY')", name="ck_integration_runs_mode"),
        sa.CheckConstraint("source_fingerprint_sha256 ~ '^[0-9a-f]{64}$'", name="ck_integration_runs_source_sha"),
        sa.CheckConstraint("idempotency_key ~ '^[0-9a-f]{64}$'", name="ck_integration_runs_idempotency"),
        sa.CheckConstraint("connector_config_version >= 1", name="ck_integration_runs_config_version"),
        sa.UniqueConstraint("institution_id", "connector_id", "idempotency_key", name="uq_integration_runs_idempotency"),
    )
    op.create_index("ix_integration_runs_tenant", "integration_runs", ["organization_id", "institution_id", "created_at", "id"])

    op.create_table(
        "integration_run_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("integration_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_item_key", sa.String(length=180), nullable=False),
        sa.Column("source_item_fingerprint_sha256", sa.String(length=64), nullable=False),
        sa.Column("canonical_entity_type", sa.String(length=80), nullable=False),
        sa.Column("operation_class", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result_entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("detail_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_item_fingerprint_sha256 ~ '^[0-9a-f]{64}$'", name="ck_integration_run_items_sha"),
        sa.CheckConstraint("status IN ('PENDING','VALID','INVALID','APPLIED','CONFLICT','FAILED')", name="ck_integration_run_items_status"),
        sa.CheckConstraint("jsonb_typeof(detail_json) = 'object'", name="ck_integration_run_items_detail_object"),
        sa.UniqueConstraint("run_id", "source_item_key", name="uq_integration_run_items_source_key"),
    )
    op.create_index("ix_integration_run_items_tenant", "integration_run_items", ["organization_id", "institution_id", "run_id"])

    op.create_table(
        "integration_run_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("integration_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("run_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("integration_run_items.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_integration_run_events_sequence"),
        sa.CheckConstraint("event_type IN ('CREATED','VALIDATING','VALIDATED','APPLYING','COMPLETED','FAILED','CANCELLED')", name="ck_integration_run_events_type"),
        sa.CheckConstraint("jsonb_typeof(metadata_json) = 'object'", name="ck_integration_run_events_metadata_object"),
        sa.UniqueConstraint("run_id", "sequence", name="uq_integration_run_events_sequence"),
    )
    op.create_index("ix_integration_run_events_tenant", "integration_run_events", ["organization_id", "institution_id", "run_id", "sequence"])

    for table, grants in (("integration_connectors", "SELECT, INSERT, UPDATE"), ("integration_mappings", "SELECT, INSERT"), ("integration_runs", "SELECT, INSERT"), ("integration_run_items", "SELECT, INSERT"), ("integration_run_events", "SELECT, INSERT")):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'GRANT {grants} ON "{table}" TO education_app')

    op.execute("""
        CREATE FUNCTION education_os_m24_has_permission(required_permission text)
        RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
          SELECT EXISTS (
            SELECT 1 FROM memberships m JOIN membership_roles mr ON mr.membership_id=m.id
            JOIN role_permissions rp ON rp.role_id=mr.role_id JOIN permissions p ON p.id=rp.permission_id
            WHERE m.user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
              AND m.institution_id = NULLIF(current_setting('app.institution_id', true), '')::uuid
              AND m.status='ACTIVE' AND p.key=required_permission)
        $$
    """)
    op.execute("REVOKE ALL ON FUNCTION education_os_m24_has_permission(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION education_os_m24_has_permission(text) TO education_app")
    for table in ("integration_connectors", "integration_mappings", "integration_runs", "integration_run_items", "integration_run_events"):
        op.execute(f'CREATE POLICY {table}_select ON "{table}" FOR SELECT TO education_app USING ({TENANT} AND education_os_m24_has_permission(\'integrations.view\'))')
    op.execute(f'CREATE POLICY integration_connectors_insert ON integration_connectors FOR INSERT TO education_app WITH CHECK ({TENANT} AND created_by_user_id = {USER_CTX} AND education_os_m24_has_permission(\'integrations.manage\'))')
    op.execute(f'CREATE POLICY integration_connectors_update ON integration_connectors FOR UPDATE TO education_app USING ({TENANT} AND education_os_m24_has_permission(\'integrations.manage\')) WITH CHECK ({TENANT} AND education_os_m24_has_permission(\'integrations.manage\'))')
    for table, actor_column in (("integration_mappings", "created_by_user_id"), ("integration_runs", "initiated_by_user_id"), ("integration_run_events", "actor_user_id")):
        permission = "integrations.manage" if table == "integration_mappings" else "integrations.run"
        op.execute(f'CREATE POLICY {table}_insert ON "{table}" FOR INSERT TO education_app WITH CHECK ({TENANT} AND {actor_column} = {USER_CTX} AND education_os_m24_has_permission(\'{permission}\'))')
    op.execute(f'CREATE POLICY integration_run_items_insert ON integration_run_items FOR INSERT TO education_app WITH CHECK ({TENANT} AND EXISTS (SELECT 1 FROM integration_runs r WHERE r.id=run_id AND r.organization_id=organization_id AND r.institution_id=institution_id AND r.initiated_by_user_id={USER_CTX}) AND education_os_m24_has_permission(\'integrations.run\'))')

    bind = op.get_bind()
    ids = {key: _permission_id(bind, key, description) for key, description in PERMISSIONS}
    _grant(bind, ids["integrations.view"], ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR"))
    _grant(bind, ids["integrations.manage"], ("SYSTEM_ADMIN",))
    _grant(bind, ids["integrations.run"], ("SYSTEM_ADMIN", "RECTOR"))
    _grant(bind, ids["integrations.audit.read"], ("SYSTEM_ADMIN", "RECTOR"))


def downgrade() -> None:
    bind = op.get_bind()
    permission_ids = bind.execute(sa.text("SELECT id FROM permissions WHERE key LIKE 'integrations.%'")).scalars().all()
    for permission_id in permission_ids:
        bind.execute(sa.text("DELETE FROM role_permissions WHERE permission_id = :id"), {"id": permission_id})
    bind.execute(sa.text("DELETE FROM permissions WHERE key LIKE 'integrations.%'"))
    op.execute("DROP FUNCTION IF EXISTS education_os_m24_has_permission(text)")
    op.drop_table("integration_run_events")
    op.drop_table("integration_run_items")
    op.drop_table("integration_runs")
    op.drop_table("integration_mappings")
    op.drop_table("integration_connectors")
