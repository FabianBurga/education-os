"""M6 family portal.

Revision ID: 0007_m6
Revises: 0006_m5
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_m6"
down_revision: str | None = "0006_m5"
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

OWN_GUARDIAN = f"""
EXISTS (
    SELECT 1
    FROM user_accounts ua
    JOIN guardian_profiles gp ON gp.person_id = ua.person_id
    WHERE ua.id = {USER_CTX}
      AND gp.id = guardian_profile_id
      AND gp.institution_id = {INST_CTX}
      AND gp.status = 'ACTIVE'
)
"""


def common_indexes(table: str) -> None:
    op.create_index(f"ix_{table}_organization", table, ["organization_id"])
    op.create_index(f"ix_{table}_institution", table, ["institution_id"])


def enable_force(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO education_app')


def upgrade() -> None:
    op.create_table(
        "guardian_student_portal_access",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("guardian_profile_id", UUID, nullable=False),
        sa.Column("student_profile_id", UUID, nullable=False),
        sa.Column("access_level", sa.String(20), nullable=False, server_default="STANDARD"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_guardian_portal_access_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["guardian_profile_id", "institution_id"],
            ["guardian_profiles.id", "guardian_profiles.institution_id"],
            name="fk_guardian_portal_access_guardian_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id", "institution_id"],
            ["student_profiles.id", "student_profiles.institution_id"],
            name="fk_guardian_portal_access_student_inst",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "access_level IN ('STANDARD','LIMITED')",
            name="ck_guardian_portal_access_level",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','REVOKED')",
            name="ck_guardian_portal_access_status",
        ),
        sa.UniqueConstraint(
            "guardian_profile_id",
            "student_profile_id",
            name="uq_guardian_student_portal_access_pair",
        ),
        sa.UniqueConstraint(
            "id",
            "institution_id",
            name="uq_guardian_student_portal_access_id_inst",
        ),
    )
    common_indexes("guardian_student_portal_access")
    op.create_index(
        "ix_guardian_portal_access_guardian",
        "guardian_student_portal_access",
        ["guardian_profile_id", "status"],
    )
    op.create_index(
        "ix_guardian_portal_access_student",
        "guardian_student_portal_access",
        ["student_profile_id", "status"],
    )
    enable_force("guardian_student_portal_access")

    op.create_table(
        "family_notices",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("student_profile_id", UUID, nullable=True),
        sa.Column("notice_type", sa.String(30), nullable=False, server_default="GENERAL"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.String(4000), nullable=False),
        sa.Column("requires_acknowledgement", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", UUID, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_family_notices_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id", "institution_id"],
            ["student_profiles.id", "student_profiles.institution_id"],
            name="fk_family_notices_student_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user_accounts.id"],
            name="fk_family_notices_creator",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "notice_type IN ('GENERAL','ANNOUNCEMENT','REMINDER','ACADEMIC','ATTENDANCE')",
            name="ck_family_notices_type",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','PUBLISHED','ARCHIVED')",
            name="ck_family_notices_status",
        ),
        sa.UniqueConstraint(
            "id",
            "institution_id",
            name="uq_family_notices_id_inst",
        ),
    )
    common_indexes("family_notices")
    op.create_index("ix_family_notices_student", "family_notices", ["student_profile_id"])
    op.create_index("ix_family_notices_status", "family_notices", ["status", "published_at"])
    enable_force("family_notices")

    op.create_table(
        "family_notice_receipts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("family_notice_id", UUID, nullable=False),
        sa.Column("guardian_profile_id", UUID, nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_family_notice_receipts_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["family_notice_id", "institution_id"],
            ["family_notices.id", "family_notices.institution_id"],
            name="fk_family_notice_receipts_notice_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["guardian_profile_id", "institution_id"],
            ["guardian_profiles.id", "guardian_profiles.institution_id"],
            name="fk_family_notice_receipts_guardian_inst",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "family_notice_id",
            "guardian_profile_id",
            name="uq_family_notice_receipt_notice_guardian",
        ),
    )
    common_indexes("family_notice_receipts")
    op.create_index(
        "ix_family_notice_receipts_guardian",
        "family_notice_receipts",
        ["guardian_profile_id"],
    )
    enable_force("family_notice_receipts")

    # Portal access: guardians can read only their own grants; staff can manage all.
    op.execute(
        f"""
        CREATE POLICY guardian_portal_access_select
        ON guardian_student_portal_access
        FOR SELECT TO education_app
        USING ({TENANT} AND (({STAFF_CURRENT}) OR ({OWN_GUARDIAN})))
        """
    )
    op.execute(
        f"""
        CREATE POLICY guardian_portal_access_insert
        ON guardian_student_portal_access
        FOR INSERT TO education_app
        WITH CHECK ({TENANT} AND ({STAFF_CURRENT}))
        """
    )
    op.execute(
        f"""
        CREATE POLICY guardian_portal_access_update
        ON guardian_student_portal_access
        FOR UPDATE TO education_app
        USING ({TENANT} AND ({STAFF_CURRENT}))
        WITH CHECK ({TENANT} AND ({STAFF_CURRENT}))
        """
    )
    op.execute(
        f"""
        CREATE POLICY guardian_portal_access_delete
        ON guardian_student_portal_access
        FOR DELETE TO education_app
        USING ({TENANT} AND ({STAFF_CURRENT}))
        """
    )

    # Notices: staff sees all; guardians only published notices that are general
    # or target a student covered by one of their active portal grants.
    guardian_notice_visible = f"""
    status = 'PUBLISHED'
    AND (
        student_profile_id IS NULL
        OR EXISTS (
            SELECT 1
            FROM guardian_student_portal_access pa
            JOIN user_accounts ua ON ua.id = {USER_CTX}
            JOIN guardian_profiles gp
              ON gp.person_id = ua.person_id
             AND gp.id = pa.guardian_profile_id
            WHERE pa.student_profile_id = family_notices.student_profile_id
              AND pa.status = 'ACTIVE'
              AND gp.institution_id = {INST_CTX}
              AND gp.status = 'ACTIVE'
        )
    )
    """
    op.execute(
        f"""
        CREATE POLICY family_notices_select
        ON family_notices
        FOR SELECT TO education_app
        USING ({TENANT} AND (({STAFF_CURRENT}) OR ({guardian_notice_visible})))
        """
    )
    for command in ("INSERT", "UPDATE", "DELETE"):
        if command == "INSERT":
            op.execute(
                f"""
                CREATE POLICY family_notices_insert
                ON family_notices
                FOR INSERT TO education_app
                WITH CHECK ({TENANT} AND ({STAFF_CURRENT}))
                """
            )
        elif command == "UPDATE":
            op.execute(
                f"""
                CREATE POLICY family_notices_update
                ON family_notices
                FOR UPDATE TO education_app
                USING ({TENANT} AND ({STAFF_CURRENT}))
                WITH CHECK ({TENANT} AND ({STAFF_CURRENT}))
                """
            )
        else:
            op.execute(
                f"""
                CREATE POLICY family_notices_delete
                ON family_notices
                FOR DELETE TO education_app
                USING ({TENANT} AND ({STAFF_CURRENT}))
                """
            )

    # Receipts: guardian owns own receipt; staff can inspect/manage.
    op.execute(
        f"""
        CREATE POLICY family_notice_receipts_select
        ON family_notice_receipts
        FOR SELECT TO education_app
        USING ({TENANT} AND (({STAFF_CURRENT}) OR ({OWN_GUARDIAN})))
        """
    )
    op.execute(
        f"""
        CREATE POLICY family_notice_receipts_insert
        ON family_notice_receipts
        FOR INSERT TO education_app
        WITH CHECK ({TENANT} AND (({STAFF_CURRENT}) OR ({OWN_GUARDIAN})))
        """
    )
    op.execute(
        f"""
        CREATE POLICY family_notice_receipts_update
        ON family_notice_receipts
        FOR UPDATE TO education_app
        USING ({TENANT} AND (({STAFF_CURRENT}) OR ({OWN_GUARDIAN})))
        WITH CHECK ({TENANT} AND (({STAFF_CURRENT}) OR ({OWN_GUARDIAN})))
        """
    )
    op.execute(
        f"""
        CREATE POLICY family_notice_receipts_delete
        ON family_notice_receipts
        FOR DELETE TO education_app
        USING ({TENANT} AND ({STAFF_CURRENT}))
        """
    )


def downgrade() -> None:
    op.drop_table("family_notice_receipts")
    op.drop_table("family_notices")
    op.drop_table("guardian_student_portal_access")
