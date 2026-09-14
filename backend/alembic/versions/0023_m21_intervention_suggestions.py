"""M21-E.A deterministic intervention suggestions.

Revision ID: 0023_m21_suggestions
Revises: 0022_m21_actions_followups
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0023_m21_suggestions"
down_revision: str | None = "0022_m21_actions_followups"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"

M21_E_PERMISSIONS = (
    (
        "intervention.suggestion.read",
        "View authorized deterministic intervention suggestions.",
    ),
    (
        "intervention.suggestion.generate",
        "Generate deterministic intervention suggestions for human review.",
    ),
    (
        "intervention.suggestion.review",
        "Accept, dismiss or expire authorized intervention suggestions.",
    ),
)

MANAGER_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR")


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


def _has_permission(permission_key: str) -> str:
    return f"""
    EXISTS (
        SELECT 1
        FROM memberships m
        JOIN membership_roles mr ON mr.membership_id = m.id
        JOIN role_permissions rp ON rp.role_id = mr.role_id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE m.user_id = {USER_CTX}
          AND m.institution_id = {INST_CTX}
          AND m.status = 'ACTIVE'
          AND p.key IN ('{permission_key}', 'intervention.admin')
    )
    """


HAS_RESTRICTED_READ = f"""
EXISTS (
    SELECT 1
    FROM memberships m
    JOIN membership_roles mr ON mr.membership_id = m.id
    JOIN role_permissions rp ON rp.role_id = mr.role_id
    JOIN permissions p ON p.id = rp.permission_id
    WHERE m.user_id = {USER_CTX}
      AND m.institution_id = {INST_CTX}
      AND m.status = 'ACTIVE'
      AND p.key = 'student_timeline.read_restricted'
)
"""

HAS_CONFIDENTIAL_READ = f"""
EXISTS (
    SELECT 1
    FROM memberships m
    JOIN membership_roles mr ON mr.membership_id = m.id
    JOIN role_permissions rp ON rp.role_id = mr.role_id
    JOIN permissions p ON p.id = rp.permission_id
    WHERE m.user_id = {USER_CTX}
      AND m.institution_id = {INST_CTX}
      AND m.status = 'ACTIVE'
      AND p.key = 'student_timeline.read_confidential'
)
"""

SENSITIVITY_SCOPE = f"""
(
    sensitivity = 'GENERAL'
    OR (
        sensitivity = 'RESTRICTED'
        AND ({HAS_RESTRICTED_READ})
    )
    OR (
        sensitivity = 'CONFIDENTIAL'
        AND ({HAS_CONFIDENTIAL_READ})
    )
)
"""

VISIBLE_SUGGESTION = f"""
EXISTS (
    SELECT 1
    FROM intervention_suggestions s
    WHERE s.id = suggestion_id
      AND s.organization_id = {ORG_CTX}
      AND s.institution_id = {INST_CTX}
)
"""


def upgrade() -> None:
    bind = op.get_bind()

    permission_ids = {
        key: _permission_id(bind, key, description)
        for key, description in M21_E_PERMISSIONS
    }
    for permission_id in permission_ids.values():
        _grant_to_role_keys(bind, permission_id, MANAGER_ROLE_KEYS)

    op.create_table(
        "intervention_suggestions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("student_profile_id", UUID, nullable=False),
        sa.Column("academic_period_id", UUID, nullable=True),
        sa.Column("section_id", UUID, nullable=True),
        sa.Column("rule_key", sa.String(80), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "generation_mode",
            sa.String(30),
            nullable=False,
            server_default="RULE_ENGINE",
        ),
        sa.Column("dedupe_key", sa.String(180), nullable=False),
        sa.Column(
            "recommended_intervention_type",
            sa.String(60),
            nullable=False,
        ),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column(
            "sensitivity",
            sa.String(20),
            nullable=False,
            server_default="GENERAL",
        ),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("rationale_summary", sa.String(1200), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_user_id", UUID, nullable=True),
        sa.Column("review_note", sa.String(1000), nullable=True),
        sa.Column("accepted_intervention_id", UUID, nullable=True),
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
            name="fk_intervention_suggestions_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["student_profile_id", "institution_id"],
            ["student_profiles.id", "student_profiles.institution_id"],
            name="fk_intervention_suggestions_student_inst",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["academic_period_id", "institution_id"],
            ["academic_periods.id", "academic_periods.institution_id"],
            name="fk_intervention_suggestions_period_inst",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["section_id", "institution_id"],
            ["sections.id", "sections.institution_id"],
            name="fk_intervention_suggestions_section_inst",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["user_accounts.id"],
            name="fk_intervention_suggestions_reviewer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_intervention_id"],
            ["interventions.id"],
            name="fk_intervention_suggestions_accepted_intervention",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "rule_version >= 1",
            name="ck_intervention_suggestions_rule_version",
        ),
        sa.CheckConstraint(
            "generation_mode = 'RULE_ENGINE'",
            name="ck_intervention_suggestions_generation_mode",
        ),
        sa.CheckConstraint(
            "severity IN ('LOW','MEDIUM','HIGH','CRITICAL')",
            name="ck_intervention_suggestions_severity",
        ),
        sa.CheckConstraint(
            "sensitivity IN ('GENERAL','RESTRICTED','CONFIDENTIAL')",
            name="ck_intervention_suggestions_sensitivity",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','ACCEPTED','DISMISSED','EXPIRED')",
            name="ck_intervention_suggestions_status",
        ),
        sa.CheckConstraint(
            "length(trim(rule_key)) > 0 "
            "AND length(trim(dedupe_key)) > 0 "
            "AND length(trim(title)) > 0 "
            "AND length(trim(rationale_summary)) > 0 "
            "AND length(trim(recommended_intervention_type)) > 0",
            name="ck_intervention_suggestions_required_text",
        ),
        sa.CheckConstraint(
            "("
            "status = 'PENDING' "
            "AND reviewed_at IS NULL "
            "AND reviewed_by_user_id IS NULL "
            "AND accepted_intervention_id IS NULL"
            ") OR ("
            "status = 'ACCEPTED' "
            "AND reviewed_at IS NOT NULL "
            "AND reviewed_by_user_id IS NOT NULL "
            "AND accepted_intervention_id IS NOT NULL"
            ") OR ("
            "status = 'DISMISSED' "
            "AND reviewed_at IS NOT NULL "
            "AND reviewed_by_user_id IS NOT NULL "
            "AND accepted_intervention_id IS NULL"
            ") OR ("
            "status = 'EXPIRED' "
            "AND accepted_intervention_id IS NULL"
            ")",
            name="ck_intervention_suggestions_human_review_boundary",
        ),
    )

    op.create_index(
        "ix_intervention_suggestions_organization",
        "intervention_suggestions",
        ["organization_id"],
    )
    op.create_index(
        "ix_intervention_suggestions_institution",
        "intervention_suggestions",
        ["institution_id"],
    )
    op.create_index(
        "ix_intervention_suggestions_student_status",
        "intervention_suggestions",
        ["student_profile_id", "status"],
    )
    op.create_index(
        "ix_intervention_suggestions_status_generated",
        "intervention_suggestions",
        ["status", "generated_at"],
    )
    op.create_index(
        "uq_intervention_suggestions_pending_dedupe",
        "intervention_suggestions",
        ["institution_id", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    op.create_table(
        "intervention_suggestion_evidence",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("suggestion_id", UUID, nullable=False),
        sa.Column("evidence_type", sa.String(40), nullable=False),
        sa.Column("evidence_id", UUID, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["institution_id", "organization_id"],
            ["institutions.id", "institutions.organization_id"],
            name="fk_intervention_suggestion_evidence_tenant",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["suggestion_id"],
            ["intervention_suggestions.id"],
            name="fk_intervention_suggestion_evidence_suggestion",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "evidence_type IN "
            "('INTELLIGENCE_SIGNAL','TIMELINE_ENTRY','EVENT_LEDGER')",
            name="ck_intervention_suggestion_evidence_type",
        ),
        sa.UniqueConstraint(
            "suggestion_id",
            "evidence_type",
            "evidence_id",
            name="uq_intervention_suggestion_evidence_identity",
        ),
    )

    op.create_index(
        "ix_intervention_suggestion_evidence_suggestion",
        "intervention_suggestion_evidence",
        ["suggestion_id"],
    )
    op.create_index(
        "ix_intervention_suggestion_evidence_source",
        "intervention_suggestion_evidence",
        ["evidence_type", "evidence_id"],
    )

    op.execute(
        'ALTER TABLE "intervention_suggestions" ENABLE ROW LEVEL SECURITY'
    )
    op.execute(
        'ALTER TABLE "intervention_suggestions" FORCE ROW LEVEL SECURITY'
    )
    op.execute(
        'GRANT SELECT, INSERT, UPDATE ON "intervention_suggestions" '
        "TO education_app"
    )

    op.execute(
        f"""
        CREATE POLICY intervention_suggestions_select
        ON intervention_suggestions
        FOR SELECT TO education_app
        USING (
            {TENANT}
            AND ({_has_permission("intervention.suggestion.read")})
            AND ({SENSITIVITY_SCOPE})
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY intervention_suggestions_insert
        ON intervention_suggestions
        FOR INSERT TO education_app
        WITH CHECK (
            {TENANT}
            AND ({_has_permission("intervention.suggestion.generate")})
            AND ({SENSITIVITY_SCOPE})
            AND status = 'PENDING'
            AND generation_mode = 'RULE_ENGINE'
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY intervention_suggestions_update
        ON intervention_suggestions
        FOR UPDATE TO education_app
        USING (
            {TENANT}
            AND ({SENSITIVITY_SCOPE})
            AND (
                ({_has_permission("intervention.suggestion.generate")})
                OR ({_has_permission("intervention.suggestion.review")})
            )
        )
        WITH CHECK (
            {TENANT}
            AND ({SENSITIVITY_SCOPE})
            AND (
                ({_has_permission("intervention.suggestion.generate")})
                OR ({_has_permission("intervention.suggestion.review")})
            )
        )
        """
    )

    op.execute(
        'ALTER TABLE "intervention_suggestion_evidence" '
        "ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        'ALTER TABLE "intervention_suggestion_evidence" '
        "FORCE ROW LEVEL SECURITY"
    )
    op.execute(
        'GRANT SELECT, INSERT ON "intervention_suggestion_evidence" '
        "TO education_app"
    )
    op.execute(
        f"""
        CREATE POLICY intervention_suggestion_evidence_select
        ON intervention_suggestion_evidence
        FOR SELECT TO education_app
        USING (
            {TENANT}
            AND ({VISIBLE_SUGGESTION})
        )
        """
    )
    op.execute(
        f"""
        CREATE POLICY intervention_suggestion_evidence_insert
        ON intervention_suggestion_evidence
        FOR INSERT TO education_app
        WITH CHECK (
            {TENANT}
            AND ({VISIBLE_SUGGESTION})
            AND ({_has_permission("intervention.suggestion.generate")})
        )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_table("intervention_suggestion_evidence")
    op.drop_table("intervention_suggestions")

    for key, _description in M21_E_PERMISSIONS:
        permission_id = bind.execute(
            sa.text("SELECT id FROM permissions WHERE key = :key"),
            {"key": key},
        ).scalar_one_or_none()
        if permission_id is None:
            continue

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
                "WHERE id = :permission_id "
                "AND NOT EXISTS ("
                "SELECT 1 FROM role_permissions "
                "WHERE permission_id = :permission_id"
                ")"
            ),
            {"permission_id": permission_id},
        )
