"""M18 Event Ledger + Read Models.

Revision ID: 0017_m18
Revises: 0016_m14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_m18"
down_revision: str | None = "0016_m14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"

TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"

CAN_ANALYTICS = f"""
EXISTS (
    SELECT 1
    FROM memberships m
    JOIN membership_roles mr ON mr.membership_id = m.id
    JOIN role_permissions rp ON rp.role_id = mr.role_id
    JOIN permissions p ON p.id = rp.permission_id
    WHERE m.user_id = {USER_CTX}
      AND m.institution_id = {INST_CTX}
      AND m.status = 'ACTIVE'
      AND p.key IN ('admin.console.access', 'coord.analytics.view')
)
"""

CAN_ADMIN = f"""
EXISTS (
    SELECT 1
    FROM memberships m
    JOIN membership_roles mr ON mr.membership_id = m.id
    JOIN role_permissions rp ON rp.role_id = mr.role_id
    JOIN permissions p ON p.id = rp.permission_id
    WHERE m.user_id = {USER_CTX}
      AND m.institution_id = {INST_CTX}
      AND m.status = 'ACTIVE'
      AND p.key = 'admin.console.access'
)
"""


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


def _enable_rls(
    table: str,
    *,
    insert_allowed: bool,
    update_allowed: bool,
) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')

    privileges = ["SELECT"]
    if insert_allowed:
        privileges.append("INSERT")
    if update_allowed:
        privileges.append("UPDATE")
    op.execute(
        f'GRANT {", ".join(privileges)} ON "{table}" TO education_app'
    )

    op.execute(
        f"""
        CREATE POLICY {table}_select
        ON "{table}"
        FOR SELECT TO education_app
        USING ({TENANT} AND ({CAN_ANALYTICS}))
        """
    )

    if insert_allowed:
        op.execute(
            f"""
            CREATE POLICY {table}_insert
            ON "{table}"
            FOR INSERT TO education_app
            WITH CHECK ({TENANT} AND ({CAN_ADMIN}))
            """
        )

    if update_allowed:
        op.execute(
            f"""
            CREATE POLICY {table}_update
            ON "{table}"
            FOR UPDATE TO education_app
            USING ({TENANT} AND ({CAN_ADMIN}))
            WITH CHECK ({TENANT} AND ({CAN_ADMIN}))
            """
        )


def upgrade() -> None:
    op.execute("CREATE SEQUENCE event_ledger_position_seq")

    op.create_table(
        "event_ledger",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "position",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("nextval('event_ledger_position_seq')"),
        ),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column(
            "source_kind",
            sa.String(40),
            nullable=False,
            server_default="TRANSACTIONAL_OUTBOX",
        ),
        sa.Column("source_outbox_event_id", UUID, nullable=False),
        sa.Column("event_type", sa.String(180), nullable=False),
        sa.Column(
            "event_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", UUID, nullable=False),
        sa.Column("actor_user_id", UUID, nullable=True),
        sa.Column("correlation_id", UUID, nullable=True),
        sa.Column("causation_id", UUID, nullable=True),
        sa.Column(
            "payload_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metadata_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_event_ledger_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["user_accounts.id"],
            name="fk_event_ledger_actor",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "event_version >= 1",
            name="ck_event_ledger_event_version",
        ),
        sa.CheckConstraint(
            "length(trim(event_type)) > 0",
            name="ck_event_ledger_event_type",
        ),
        sa.CheckConstraint(
            "length(trim(aggregate_type)) > 0",
            name="ck_event_ledger_aggregate_type",
        ),
        sa.UniqueConstraint(
            "position",
            name="uq_event_ledger_position",
        ),
        sa.UniqueConstraint(
            "source_outbox_event_id",
            name="uq_event_ledger_source_outbox",
        ),
    )
    _tenant_indexes("event_ledger")
    op.create_index(
        "ix_event_ledger_type_position",
        "event_ledger",
        ["event_type", "position"],
    )
    op.create_index(
        "ix_event_ledger_aggregate",
        "event_ledger",
        ["aggregate_type", "aggregate_id", "position"],
    )
    op.create_index(
        "ix_event_ledger_correlation",
        "event_ledger",
        ["correlation_id"],
    )
    op.create_index(
        "ix_event_ledger_occurred",
        "event_ledger",
        ["occurred_at"],
    )

    op.create_table(
        "projection_checkpoints",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("projection_key", sa.String(120), nullable=False),
        sa.Column(
            "last_position",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "processed_count",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_projection_checkpoints_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "last_position >= 0",
            name="ck_projection_checkpoint_position",
        ),
        sa.CheckConstraint(
            "processed_count >= 0",
            name="ck_projection_checkpoint_count",
        ),
        sa.UniqueConstraint(
            "institution_id",
            "projection_key",
            name="uq_projection_checkpoint_inst_key",
        ),
    )
    _tenant_indexes("projection_checkpoints")
    op.create_index(
        "ix_projection_checkpoints_key",
        "projection_checkpoints",
        ["projection_key"],
    )

    op.create_table(
        "institution_event_daily",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_type", sa.String(180), nullable=False),
        sa.Column(
            "event_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "event_count",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "first_event_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "last_event_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "projection_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_institution_event_daily_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "event_version >= 1",
            name="ck_inst_event_daily_version",
        ),
        sa.CheckConstraint(
            "event_count >= 0",
            name="ck_inst_event_daily_count",
        ),
        sa.UniqueConstraint(
            "institution_id",
            "event_date",
            "event_type",
            "event_version",
            name="uq_inst_event_daily_key",
        ),
    )
    _tenant_indexes("institution_event_daily")
    op.create_index(
        "ix_inst_event_daily_date",
        "institution_event_daily",
        ["event_date", "event_type"],
    )

    op.create_table(
        "aggregate_activity_snapshots",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", UUID, nullable=False),
        sa.Column("first_position", sa.BigInteger(), nullable=False),
        sa.Column("last_position", sa.BigInteger(), nullable=False),
        sa.Column(
            "first_event_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "last_event_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "event_count",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_event_type", sa.String(180), nullable=False),
        sa.Column(
            "last_event_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "projection_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_aggregate_activity_tenant",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "first_position > 0 AND last_position >= first_position",
            name="ck_aggregate_activity_positions",
        ),
        sa.CheckConstraint(
            "event_count >= 0",
            name="ck_aggregate_activity_count",
        ),
        sa.CheckConstraint(
            "last_event_version >= 1",
            name="ck_aggregate_activity_version",
        ),
        sa.UniqueConstraint(
            "institution_id",
            "aggregate_type",
            "aggregate_id",
            name="uq_aggregate_activity_inst_aggregate",
        ),
    )
    _tenant_indexes("aggregate_activity_snapshots")
    op.create_index(
        "ix_aggregate_activity_lookup",
        "aggregate_activity_snapshots",
        ["aggregate_type", "aggregate_id"],
    )
    op.create_index(
        "ix_aggregate_activity_last_position",
        "aggregate_activity_snapshots",
        ["last_position"],
    )

    op.execute(
        """
        CREATE FUNCTION education_os_reject_event_ledger_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION
                'event_ledger is append-only; UPDATE and DELETE are forbidden';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_event_ledger_immutable
        BEFORE UPDATE OR DELETE ON event_ledger
        FOR EACH ROW
        EXECUTE FUNCTION education_os_reject_event_ledger_mutation()
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_event_ledger_no_truncate
        BEFORE TRUNCATE ON event_ledger
        FOR EACH STATEMENT
        EXECUTE FUNCTION education_os_reject_event_ledger_mutation()
        """
    )

    _enable_rls(
        "event_ledger",
        insert_allowed=True,
        update_allowed=False,
    )
    op.execute("REVOKE SELECT ON event_ledger FROM education_app")
    op.execute(
        """
        GRANT SELECT (
            id,
            position,
            organization_id,
            institution_id,
            source_kind,
            source_outbox_event_id,
            event_type,
            event_version,
            aggregate_type,
            aggregate_id,
            actor_user_id,
            correlation_id,
            causation_id,
            occurred_at,
            recorded_at
        )
        ON event_ledger
        TO education_app
        """
    )
    _enable_rls(
        "projection_checkpoints",
        insert_allowed=True,
        update_allowed=True,
    )
    _enable_rls(
        "institution_event_daily",
        insert_allowed=True,
        update_allowed=True,
    )
    _enable_rls(
        "aggregate_activity_snapshots",
        insert_allowed=True,
        update_allowed=True,
    )

    op.execute(
        "GRANT USAGE, SELECT ON SEQUENCE "
        "event_ledger_position_seq TO education_app"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_event_ledger_no_truncate ON event_ledger"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_event_ledger_immutable ON event_ledger"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS education_os_reject_event_ledger_mutation()"
    )

    op.drop_table("aggregate_activity_snapshots")
    op.drop_table("institution_event_daily")
    op.drop_table("projection_checkpoints")
    op.drop_table("event_ledger")
    op.execute("DROP SEQUENCE IF EXISTS event_ledger_position_seq")

