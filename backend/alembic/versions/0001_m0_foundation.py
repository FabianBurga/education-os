"""M0 foundation, runtime grants and RLS policies.

Revision ID: 0001_m0
Revises:
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_m0"
down_revision = None
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_organizations_name", "organizations", ["name"])

    op.create_table(
        "institutions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("type", sa.String(30), nullable=False, server_default="PRIVATE"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_institutions_org", "institutions", ["organization_id"])

    op.create_table(
        "campuses",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("institution_id", UUID, sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_campuses_institution", "campuses", ["institution_id"])

    op.create_table(
        "institution_capabilities",
        sa.Column("institution_id", UUID, sa.ForeignKey("institutions.id"), primary_key=True),
        sa.Column("capability_key", sa.String(100), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "persons",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("given_names", sa.String(160), nullable=False),
        sa.Column("family_names", sa.String(160), nullable=False),
        sa.Column("primary_email", sa.String(320)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_persons_organization", "persons", ["organization_id"])

    op.create_table(
        "user_accounts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("person_id", UUID, sa.ForeignKey("persons.id"), nullable=False, unique=True),
        sa.Column("login_email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_accounts_login_email", "user_accounts", ["login_email"], unique=True)

    op.create_table(
        "memberships",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("user_accounts.id"), nullable=False),
        sa.Column("institution_id", UUID, sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "institution_id", name="uq_membership_user_institution"),
    )
    op.create_index("ix_memberships_institution", "memberships", ["institution_id"])
    op.create_index("ix_memberships_user", "memberships", ["user_id"])

    op.create_table(
        "roles",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("institution_id", UUID, sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.UniqueConstraint("institution_id", "key", name="uq_role_institution_key"),
    )

    op.create_table(
        "permissions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("key", sa.String(160), nullable=False, unique=True),
        sa.Column("description", sa.String(500), nullable=False),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", UUID, sa.ForeignKey("roles.id"), primary_key=True),
        sa.Column("permission_id", UUID, sa.ForeignKey("permissions.id"), primary_key=True),
    )

    op.create_table(
        "membership_roles",
        sa.Column("membership_id", UUID, sa.ForeignKey("memberships.id"), primary_key=True),
        sa.Column("role_id", UUID, sa.ForeignKey("roles.id"), primary_key=True),
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("institution_id", UUID, sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("event_type", sa.String(180), nullable=False),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", UUID, nullable=False),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_outbox_pending", "outbox_events", ["status", "created_at"])

    op.create_table(
        "audit_logs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("institution_id", UUID, sa.ForeignKey("institutions.id"), nullable=False),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("user_accounts.id")),
        sa.Column("action", sa.String(160), nullable=False),
        sa.Column("entity_type", sa.String(120), nullable=False),
        sa.Column("entity_id", UUID),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_institution_created", "audit_logs", ["institution_id", "created_at"])

    op.execute("GRANT USAGE ON SCHEMA public TO education_app")
    mutable_runtime_tables = [
        "organizations", "institutions", "campuses", "institution_capabilities",
        "persons", "memberships", "roles", "role_permissions", "membership_roles",
        "outbox_events", "audit_logs"
    ]
    for table in mutable_runtime_tables:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO education_app")

    # Authentication bootstrap is intentionally deferred. At runtime M0 only
    # needs self-read access after a signed token establishes app.user_id.
    op.execute("GRANT SELECT ON TABLE user_accounts TO education_app")
    op.execute("GRANT SELECT ON TABLE permissions TO education_app")

    rls_tables = [
        "organizations", "institutions", "campuses", "institution_capabilities",
        "persons", "user_accounts", "memberships", "roles", "role_permissions",
        "membership_roles", "outbox_events", "audit_logs"
    ]
    for table in rls_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    org_ctx = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
    inst_ctx = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
    user_ctx = "NULLIF(current_setting('app.user_id', true), '')::uuid"

    op.execute(f"""
        CREATE POLICY organizations_tenant_policy ON organizations
        USING (id = {org_ctx})
        WITH CHECK (id = {org_ctx})
    """)
    op.execute(f"""
        CREATE POLICY institutions_tenant_policy ON institutions
        USING (organization_id = {org_ctx} AND id = {inst_ctx})
        WITH CHECK (organization_id = {org_ctx} AND id = {inst_ctx})
    """)
    op.execute(f"""
        CREATE POLICY campuses_tenant_policy ON campuses
        USING (institution_id = {inst_ctx})
        WITH CHECK (institution_id = {inst_ctx})
    """)
    op.execute(f"""
        CREATE POLICY institution_capabilities_tenant_policy ON institution_capabilities
        USING (institution_id = {inst_ctx})
        WITH CHECK (institution_id = {inst_ctx})
    """)
    op.execute(f"""
        CREATE POLICY persons_org_policy ON persons
        USING (organization_id = {org_ctx})
        WITH CHECK (organization_id = {org_ctx})
    """)
    op.execute(f"""
        CREATE POLICY user_accounts_self_policy ON user_accounts
        USING (id = {user_ctx})
        WITH CHECK (id = {user_ctx})
    """)
    op.execute(f"""
        CREATE POLICY memberships_tenant_policy ON memberships
        USING (institution_id = {inst_ctx})
        WITH CHECK (institution_id = {inst_ctx})
    """)
    op.execute(f"""
        CREATE POLICY roles_tenant_policy ON roles
        USING (institution_id = {inst_ctx})
        WITH CHECK (institution_id = {inst_ctx})
    """)
    op.execute(f"""
        CREATE POLICY role_permissions_tenant_policy ON role_permissions
        USING (
          EXISTS (
            SELECT 1 FROM roles r
            WHERE r.id = role_permissions.role_id
              AND r.institution_id = {inst_ctx}
          )
        )
        WITH CHECK (
          EXISTS (
            SELECT 1 FROM roles r
            WHERE r.id = role_permissions.role_id
              AND r.institution_id = {inst_ctx}
          )
        )
    """)
    op.execute(f"""
        CREATE POLICY membership_roles_tenant_policy ON membership_roles
        USING (
          EXISTS (
            SELECT 1 FROM memberships m
            WHERE m.id = membership_roles.membership_id
              AND m.institution_id = {inst_ctx}
          )
        )
        WITH CHECK (
          EXISTS (
            SELECT 1 FROM memberships m
            WHERE m.id = membership_roles.membership_id
              AND m.institution_id = {inst_ctx}
          )
        )
    """)
    op.execute(f"""
        CREATE POLICY outbox_events_tenant_policy ON outbox_events
        USING (institution_id = {inst_ctx})
        WITH CHECK (institution_id = {inst_ctx})
    """)
    op.execute(f"""
        CREATE POLICY audit_logs_tenant_policy ON audit_logs
        USING (institution_id = {inst_ctx})
        WITH CHECK (institution_id = {inst_ctx})
    """)

    # Permission catalog remains global read-only in M0.


def downgrade() -> None:
    for table in [
        "audit_logs", "outbox_events", "membership_roles", "role_permissions",
        "permissions", "roles", "memberships", "user_accounts", "persons",
        "institution_capabilities", "campuses", "institutions", "organizations"
    ]:
        op.drop_table(table)
