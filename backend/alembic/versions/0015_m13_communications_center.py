"""M13 Communications Center.

Revision ID: 0015_m13
Revises: 0014_m12
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_m13"
down_revision: str | None = "0014_m12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"

TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"

STAFF_CURRENT = f"""
EXISTS (
    SELECT 1
    FROM user_accounts ua
    JOIN staff_profiles sp ON sp.person_id = ua.person_id
    WHERE ua.id = {USER_CTX}
      AND sp.institution_id = {INST_CTX}
      AND sp.status = 'ACTIVE'
)
"""

M13_PERMISSIONS = (
    (
        "communications.console.access",
        "Access the institutional Communications Center.",
    ),
    (
        "communications.messages.view",
        "View institutional communications and targeting context.",
    ),
    (
        "communications.messages.manage",
        "Create, edit, target and archive draft communications.",
    ),
    (
        "communications.publish",
        "Publish communications to resolved family recipients.",
    ),
    (
        "communications.templates.manage",
        "Create and maintain reusable communication templates.",
    ),
    (
        "communications.delivery.view",
        "View communication delivery, read and acknowledgement status.",
    ),
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
            """
            INSERT INTO permissions (id, key, description)
            VALUES (:id, :key, :description)
            """
        ),
        {
            "id": permission_id,
            "key": key,
            "description": description,
        },
    )
    return permission_id


def _grant(bind, role_id, permission_id) -> None:
    bind.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            VALUES (:role_id, :permission_id)
            ON CONFLICT DO NOTHING
            """
        ),
        {
            "role_id": role_id,
            "permission_id": permission_id,
        },
    )


def _common_indexes(table: str) -> None:
    op.create_index(f"ix_{table}_organization", table, ["organization_id"])
    op.create_index(f"ix_{table}_institution", table, ["institution_id"])


def _enable_staff_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO education_app'
    )

    op.execute(
        f"""
        CREATE POLICY {table}_select
        ON "{table}"
        FOR SELECT TO education_app
        USING ({TENANT} AND ({STAFF_CURRENT}))
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table}_insert
        ON "{table}"
        FOR INSERT TO education_app
        WITH CHECK ({TENANT} AND ({STAFF_CURRENT}))
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table}_update
        ON "{table}"
        FOR UPDATE TO education_app
        USING ({TENANT} AND ({STAFF_CURRENT}))
        WITH CHECK ({TENANT} AND ({STAFF_CURRENT}))
        """
    )
    op.execute(
        f"""
        CREATE POLICY {table}_delete
        ON "{table}"
        FOR DELETE TO education_app
        USING ({TENANT} AND ({STAFF_CURRENT}))
        """
    )


def upgrade() -> None:
    bind = op.get_bind()

    permission_ids = {
        key: _permission_id(bind, key, description)
        for key, description in M13_PERMISSIONS
    }

    role_rows = bind.execute(
        sa.text(
            """
            SELECT id
            FROM roles
            WHERE key IN ('SYSTEM_ADMIN','RECTOR','ACADEMIC_COORDINATOR')
            """
        )
    ).all()
    for (role_id,) in role_rows:
        for permission_id in permission_ids.values():
            _grant(bind, role_id, permission_id)

    op.create_table(
        "communication_templates",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("title_template", sa.String(200), nullable=False),
        sa.Column("body_template", sa.String(4000), nullable=False),
        sa.Column(
            "notice_type",
            sa.String(30),
            nullable=False,
            server_default="ANNOUNCEMENT",
        ),
        sa.Column(
            "requires_acknowledgement",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column("created_by_user_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
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
            name="fk_communication_templates_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user_accounts.id"],
            name="fk_communication_templates_creator",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "notice_type IN ('GENERAL','ANNOUNCEMENT','REMINDER','ACADEMIC','ATTENDANCE')",
            name="ck_communication_templates_notice_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','ARCHIVED')",
            name="ck_communication_templates_status",
        ),
        sa.UniqueConstraint(
            "institution_id",
            "name",
            name="uq_communication_templates_inst_name",
        ),
        sa.UniqueConstraint(
            "id",
            "institution_id",
            name="uq_communication_templates_id_inst",
        ),
    )
    _common_indexes("communication_templates")
    op.create_index(
        "ix_communication_templates_status",
        "communication_templates",
        ["status", "name"],
    )
    _enable_staff_rls("communication_templates")

    op.create_table(
        "communications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("template_id", UUID, nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.String(4000), nullable=False),
        sa.Column(
            "notice_type",
            sa.String(30),
            nullable=False,
            server_default="ANNOUNCEMENT",
        ),
        sa.Column(
            "requires_acknowledgement",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("created_by_user_id", UUID, nullable=True),
        sa.Column("published_by_user_id", UUID, nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
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
            name="fk_communications_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "institution_id"],
            ["communication_templates.id", "communication_templates.institution_id"],
            name="fk_communications_template_inst",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user_accounts.id"],
            name="fk_communications_creator",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["published_by_user_id"],
            ["user_accounts.id"],
            name="fk_communications_publisher",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "notice_type IN ('GENERAL','ANNOUNCEMENT','REMINDER','ACADEMIC','ATTENDANCE')",
            name="ck_communications_notice_type",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','ARCHIVED')",
            name="ck_communications_status",
        ),
        sa.UniqueConstraint(
            "id",
            "institution_id",
            name="uq_communications_id_inst",
        ),
    )
    _common_indexes("communications")
    op.create_index(
        "ix_communications_status",
        "communications",
        ["status", "published_at"],
    )
    op.create_index(
        "ix_communications_created",
        "communications",
        ["created_at"],
    )
    _enable_staff_rls("communications")

    op.create_table(
        "communication_targets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("communication_id", UUID, nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", UUID, nullable=False),
        sa.Column("target_label", sa.String(240), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_communication_targets_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["communication_id", "institution_id"],
            ["communications.id", "communications.institution_id"],
            name="fk_communication_targets_message_inst",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "target_type IN ('INSTITUTION','CAMPUS','SECTION','COURSE','STUDENT','FAMILY')",
            name="ck_communication_targets_type",
        ),
        sa.UniqueConstraint(
            "communication_id",
            "target_type",
            "target_id",
            name="uq_communication_targets_scope",
        ),
    )
    _common_indexes("communication_targets")
    op.create_index(
        "ix_communication_targets_message",
        "communication_targets",
        ["communication_id"],
    )
    op.create_index(
        "ix_communication_targets_target",
        "communication_targets",
        ["target_type", "target_id"],
    )
    _enable_staff_rls("communication_targets")

    op.create_table(
        "communication_recipients",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("communication_id", UUID, nullable=False),
        sa.Column("guardian_profile_id", UUID, nullable=False),
        sa.Column("student_profile_id", UUID, nullable=False),
        sa.Column("family_notice_id", UUID, nullable=False),
        sa.Column(
            "delivery_status",
            sa.String(20),
            nullable=False,
            server_default="DELIVERED",
        ),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_communication_recipients_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["communication_id", "institution_id"],
            ["communications.id", "communications.institution_id"],
            name="fk_communication_recipients_message_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["guardian_profile_id", "institution_id"],
            ["guardian_profiles.id", "guardian_profiles.institution_id"],
            name="fk_communication_recipients_guardian_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id", "institution_id"],
            ["student_profiles.id", "student_profiles.institution_id"],
            name="fk_communication_recipients_student_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["family_notice_id", "institution_id"],
            ["family_notices.id", "family_notices.institution_id"],
            name="fk_communication_recipients_notice_inst",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "delivery_status IN ('DELIVERED','FAILED')",
            name="ck_communication_recipients_delivery_status",
        ),
        sa.UniqueConstraint(
            "communication_id",
            "guardian_profile_id",
            "student_profile_id",
            name="uq_communication_recipient_guardian_student",
        ),
    )
    _common_indexes("communication_recipients")
    op.create_index(
        "ix_communication_recipients_message",
        "communication_recipients",
        ["communication_id"],
    )
    op.create_index(
        "ix_communication_recipients_guardian",
        "communication_recipients",
        ["guardian_profile_id"],
    )
    op.create_index(
        "ix_communication_recipients_notice",
        "communication_recipients",
        ["family_notice_id"],
    )
    _enable_staff_rls("communication_recipients")


def downgrade() -> None:
    bind = op.get_bind()

    for table in (
        "communication_recipients",
        "communication_targets",
        "communications",
        "communication_templates",
    ):
        op.drop_table(table)

    permission_ids = []
    for key, _description in M13_PERMISSIONS:
        permission_id = bind.execute(
            sa.text("SELECT id FROM permissions WHERE key = :key"),
            {"key": key},
        ).scalar_one_or_none()
        if permission_id is not None:
            permission_ids.append(permission_id)

    for permission_id in permission_ids:
        bind.execute(
            sa.text(
                """
                DELETE FROM role_permissions
                WHERE permission_id = :permission_id
                """
            ),
            {"permission_id": permission_id},
        )

    for key, _description in M13_PERMISSIONS:
        bind.execute(
            sa.text(
                """
                DELETE FROM permissions p
                WHERE p.key = :key
                  AND NOT EXISTS (
                      SELECT 1
                      FROM role_permissions rp
                      WHERE rp.permission_id = p.id
                  )
                """
            ),
            {"key": key},
        )
