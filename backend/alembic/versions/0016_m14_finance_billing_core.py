"""M14 Finance / Billing Core.

Revision ID: 0016_m14
Revises: 0015_m13
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_m14"
down_revision: str | None = "0015_m13"
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

M14_PERMISSIONS = (
    (
        "finance.console.access",
        "Access the Finance / Billing Console.",
    ),
    (
        "finance.summary.view",
        "View finance summary and billing balances.",
    ),
    (
        "finance.concepts.manage",
        "Create and maintain billing concepts.",
    ),
    (
        "finance.charges.manage",
        "Create and manage student billing charges.",
    ),
    (
        "finance.payments.manage",
        "Post student payments and payment allocations.",
    ),
    (
        "finance.statements.view",
        "View student billing statements and transaction history.",
    ),
    (
        "finance.reversals.manage",
        "Void finance charges and payments with an audit reason.",
    ),
    (
        "finance.capability.manage",
        "Enable or disable the Finance / Billing capability for an institution.",
    ),
)

FINANCE_MANAGER_PERMISSIONS = {
    "finance.console.access",
    "finance.summary.view",
    "finance.concepts.manage",
    "finance.charges.manage",
    "finance.payments.manage",
    "finance.statements.view",
    "finance.reversals.manage",
}

RECTOR_PERMISSIONS = {
    "finance.console.access",
    "finance.summary.view",
    "finance.statements.view",
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


def _ensure_finance_manager_roles(bind) -> None:
    institution_rows = bind.execute(
        sa.text("SELECT id FROM institutions ORDER BY id")
    ).all()
    for (institution_id,) in institution_rows:
        existing = bind.execute(
            sa.text(
                """
                SELECT id
                FROM roles
                WHERE institution_id = :institution_id
                  AND key = 'FINANCE_MANAGER'
                """
            ),
            {"institution_id": institution_id},
        ).scalar_one_or_none()
        if existing is not None:
            continue

        bind.execute(
            sa.text(
                """
                INSERT INTO roles (id, institution_id, key, name)
                VALUES (:id, :institution_id, 'FINANCE_MANAGER', 'Finance Manager')
                """
            ),
            {
                "id": uuid4(),
                "institution_id": institution_id,
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
        for key, description in M14_PERMISSIONS
    }

    _ensure_finance_manager_roles(bind)

    role_rows = bind.execute(
        sa.text(
            """
            SELECT id, key
            FROM roles
            WHERE key IN ('SYSTEM_ADMIN','RECTOR','FINANCE_MANAGER')
            """
        )
    ).all()
    for role_id, role_key in role_rows:
        if role_key == "SYSTEM_ADMIN":
            keys = set(permission_ids)
        elif role_key == "RECTOR":
            keys = RECTOR_PERMISSIONS
        else:
            keys = FINANCE_MANAGER_PERMISSIONS

        for key in keys:
            _grant(bind, role_id, permission_ids[key])

    # Capability defaults are based on institution type, but remain explicitly
    # overridable later by an authorized SYSTEM_ADMIN.
    bind.execute(
        sa.text(
            """
            INSERT INTO institution_capabilities (
                institution_id,
                capability_key,
                enabled
            )
            SELECT
                i.id,
                'finance.billing',
                CASE
                    WHEN i.type IN ('PRIVATE','FISCOMISIONAL') THEN true
                    ELSE false
                END
            FROM institutions i
            ON CONFLICT (institution_id, capability_key) DO NOTHING
            """
        )
    )

    op.create_table(
        "billing_concepts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column(
            "default_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "currency",
            sa.String(3),
            nullable=False,
            server_default="USD",
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
            name="fk_billing_concepts_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user_accounts.id"],
            name="fk_billing_concepts_creator",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "default_amount >= 0",
            name="ck_billing_concepts_default_amount",
        ),
        sa.CheckConstraint(
            "currency = 'USD'",
            name="ck_billing_concepts_currency",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','ARCHIVED')",
            name="ck_billing_concepts_status",
        ),
        sa.UniqueConstraint(
            "institution_id",
            "code",
            name="uq_billing_concepts_inst_code",
        ),
        sa.UniqueConstraint(
            "id",
            "institution_id",
            name="uq_billing_concepts_id_inst",
        ),
    )
    _common_indexes("billing_concepts")
    op.create_index(
        "ix_billing_concepts_status",
        "billing_concepts",
        ["status", "name"],
    )
    _enable_staff_rls("billing_concepts")

    op.create_table(
        "billing_accounts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("student_profile_id", UUID, nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_billing_accounts_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id", "institution_id"],
            ["student_profiles.id", "student_profiles.institution_id"],
            name="fk_billing_accounts_student_inst",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','CLOSED')",
            name="ck_billing_accounts_status",
        ),
        sa.UniqueConstraint(
            "institution_id",
            "student_profile_id",
            name="uq_billing_accounts_inst_student",
        ),
        sa.UniqueConstraint(
            "id",
            "institution_id",
            name="uq_billing_accounts_id_inst",
        ),
    )
    _common_indexes("billing_accounts")
    op.create_index(
        "ix_billing_accounts_student",
        "billing_accounts",
        ["student_profile_id"],
    )
    _enable_staff_rls("billing_accounts")

    op.create_table(
        "billing_charges",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("billing_account_id", UUID, nullable=False),
        sa.Column("billing_concept_id", UUID, nullable=False),
        sa.Column("academic_period_id", UUID, nullable=True),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="OPEN",
        ),
        sa.Column("created_by_user_id", UUID, nullable=True),
        sa.Column("voided_by_user_id", UUID, nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
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
            name="fk_billing_charges_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["billing_account_id", "institution_id"],
            ["billing_accounts.id", "billing_accounts.institution_id"],
            name="fk_billing_charges_account_inst",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["billing_concept_id", "institution_id"],
            ["billing_concepts.id", "billing_concepts.institution_id"],
            name="fk_billing_charges_concept_inst",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["academic_period_id"],
            ["academic_periods.id"],
            name="fk_billing_charges_period",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["user_accounts.id"],
            name="fk_billing_charges_creator",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["voided_by_user_id"],
            ["user_accounts.id"],
            name="fk_billing_charges_voider",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_billing_charges_amount",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','PARTIAL','PAID','VOID')",
            name="ck_billing_charges_status",
        ),
        sa.UniqueConstraint(
            "id",
            "institution_id",
            name="uq_billing_charges_id_inst",
        ),
    )
    _common_indexes("billing_charges")
    op.create_index(
        "ix_billing_charges_account_due",
        "billing_charges",
        ["billing_account_id", "due_on"],
    )
    op.create_index(
        "ix_billing_charges_status",
        "billing_charges",
        ["status", "due_on"],
    )
    _enable_staff_rls("billing_charges")

    op.create_table(
        "billing_payments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("billing_account_id", UUID, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("payment_method", sa.String(30), nullable=False),
        sa.Column("reference", sa.String(160), nullable=True),
        sa.Column(
            "paid_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="POSTED",
        ),
        sa.Column("posted_by_user_id", UUID, nullable=True),
        sa.Column("voided_by_user_id", UUID, nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_billing_payments_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["billing_account_id", "institution_id"],
            ["billing_accounts.id", "billing_accounts.institution_id"],
            name="fk_billing_payments_account_inst",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["posted_by_user_id"],
            ["user_accounts.id"],
            name="fk_billing_payments_poster",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["voided_by_user_id"],
            ["user_accounts.id"],
            name="fk_billing_payments_voider",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_billing_payments_amount",
        ),
        sa.CheckConstraint(
            "payment_method IN ('CASH','BANK_TRANSFER','CARD','OTHER')",
            name="ck_billing_payments_method",
        ),
        sa.CheckConstraint(
            "status IN ('POSTED','VOID')",
            name="ck_billing_payments_status",
        ),
        sa.UniqueConstraint(
            "id",
            "institution_id",
            name="uq_billing_payments_id_inst",
        ),
    )
    _common_indexes("billing_payments")
    op.create_index(
        "ix_billing_payments_account_paid",
        "billing_payments",
        ["billing_account_id", "paid_at"],
    )
    op.create_index(
        "ix_billing_payments_status",
        "billing_payments",
        ["status", "paid_at"],
    )
    _enable_staff_rls("billing_payments")

    op.create_table(
        "billing_allocations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("billing_payment_id", UUID, nullable=False),
        sa.Column("billing_charge_id", UUID, nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_billing_allocations_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["billing_payment_id", "institution_id"],
            ["billing_payments.id", "billing_payments.institution_id"],
            name="fk_billing_allocations_payment_inst",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["billing_charge_id", "institution_id"],
            ["billing_charges.id", "billing_charges.institution_id"],
            name="fk_billing_allocations_charge_inst",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_billing_allocations_amount",
        ),
        sa.UniqueConstraint(
            "billing_payment_id",
            "billing_charge_id",
            name="uq_billing_allocations_payment_charge",
        ),
    )
    _common_indexes("billing_allocations")
    op.create_index(
        "ix_billing_allocations_payment",
        "billing_allocations",
        ["billing_payment_id"],
    )
    op.create_index(
        "ix_billing_allocations_charge",
        "billing_allocations",
        ["billing_charge_id"],
    )
    _enable_staff_rls("billing_allocations")


def downgrade() -> None:
    bind = op.get_bind()

    for table in (
        "billing_allocations",
        "billing_payments",
        "billing_charges",
        "billing_accounts",
        "billing_concepts",
    ):
        op.drop_table(table)

    bind.execute(
        sa.text(
            """
            DELETE FROM institution_capabilities
            WHERE capability_key = 'finance.billing'
            """
        )
    )

    permission_ids = []
    for key, _description in M14_PERMISSIONS:
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

    bind.execute(
        sa.text(
            """
            DELETE FROM roles r
            WHERE r.key = 'FINANCE_MANAGER'
              AND NOT EXISTS (
                  SELECT 1
                  FROM membership_roles mr
                  WHERE mr.role_id = r.id
              )
            """
        )
    )

    for key, _description in M14_PERMISSIONS:
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
