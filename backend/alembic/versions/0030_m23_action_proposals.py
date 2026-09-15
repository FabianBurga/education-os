"""M23 human-governed action proposals.

Revision ID: 0030_m23_action_proposals
Revises: 0029_m23_contract_hardening
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0030_m23_action_proposals"
down_revision: str | None = "0029_m23_contract_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"

EVENT_TRIGGER = "trg_copilot_action_proposal_event_transition"
EVENT_TRIGGER_FUNCTION = "education_os_copilot_validate_action_event"


def upgrade() -> None:
    op.create_table(
        "copilot_action_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("copilot_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("proposed_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("target_student_profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("rationale_text", sa.Text(), nullable=False),
        sa.Column(
            "evidence_citations_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action_type = 'CREATE_INTERVENTION'",
            name="ck_copilot_action_proposals_action_type",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(payload_json) = 'object'",
            name="ck_copilot_action_proposals_payload_object",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(evidence_citations_json) = 'array'",
            name="ck_copilot_action_proposals_citations_array",
        ),
        sa.CheckConstraint(
            "payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_copilot_action_proposals_payload_sha256",
        ),
        sa.CheckConstraint(
            "length(btrim(rationale_text)) > 0",
            name="ck_copilot_action_proposals_rationale_nonempty",
        ),
    )
    op.create_index(
        "ix_copilot_action_proposals_tenant_created",
        "copilot_action_proposals",
        ["organization_id", "institution_id", "created_at", "id"],
    )
    op.create_index(
        "ix_copilot_action_proposals_run",
        "copilot_action_proposals",
        ["run_id"],
    )
    op.create_index(
        "ix_copilot_action_proposals_student",
        "copilot_action_proposals",
        ["institution_id", "target_student_profile_id"],
    )

    op.create_table(
        "copilot_action_proposal_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "proposal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("copilot_action_proposals.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column(
            "result_ref_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("failure_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('PROPOSED','APPROVED','REJECTED','EXECUTED','FAILED')",
            name="ck_copilot_action_proposal_events_type",
        ),
        sa.CheckConstraint(
            "result_ref_json IS NULL OR jsonb_typeof(result_ref_json) = 'object'",
            name="ck_copilot_action_proposal_events_result_object",
        ),
    )
    op.create_index(
        "ix_copilot_action_proposal_events_proposal_created",
        "copilot_action_proposal_events",
        ["proposal_id", "created_at", "id"],
    )
    op.create_index(
        "ix_copilot_action_proposal_events_tenant",
        "copilot_action_proposal_events",
        ["organization_id", "institution_id"],
    )

    for table in ("copilot_action_proposals", "copilot_action_proposal_events"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f'GRANT SELECT, INSERT ON "{table}" TO education_app')

    proposal_visible = (
        f"{TENANT} AND ("
        f"proposed_by_user_id = {USER_CTX} "
        "OR education_os_copilot_has_permission('copilot.action.approve'))"
    )
    proposal_insert = (
        f"{TENANT} "
        f"AND proposed_by_user_id = {USER_CTX} "
        "AND education_os_copilot_has_permission('copilot.use') "
        "AND EXISTS ("
        "SELECT 1 FROM copilot_runs cr "
        "WHERE cr.id = run_id "
        "AND cr.organization_id = organization_id "
        "AND cr.institution_id = institution_id "
        f"AND cr.actor_user_id = {USER_CTX})"
    )
    op.execute(
        'CREATE POLICY copilot_action_proposals_select '
        'ON "copilot_action_proposals" '
        f"FOR SELECT TO education_app USING ({proposal_visible})"
    )
    op.execute(
        'CREATE POLICY copilot_action_proposals_insert '
        'ON "copilot_action_proposals" '
        f"FOR INSERT TO education_app WITH CHECK ({proposal_insert})"
    )

    event_visible = (
        f"{TENANT} AND EXISTS ("
        "SELECT 1 FROM copilot_action_proposals p "
        "WHERE p.id = proposal_id "
        "AND p.organization_id = organization_id "
        "AND p.institution_id = institution_id "
        "AND ("
        f"p.proposed_by_user_id = {USER_CTX} "
        "OR education_os_copilot_has_permission('copilot.action.approve')))"
    )
    event_insert = (
        f"{TENANT} "
        f"AND actor_user_id = {USER_CTX} "
        "AND EXISTS ("
        "SELECT 1 FROM copilot_action_proposals p "
        "WHERE p.id = proposal_id "
        "AND p.organization_id = organization_id "
        "AND p.institution_id = institution_id "
        "AND (("
        "event_type = 'PROPOSED' "
        f"AND p.proposed_by_user_id = {USER_CTX} "
        "AND education_os_copilot_has_permission('copilot.use')) "
        "OR (event_type IN ('APPROVED','REJECTED','EXECUTED','FAILED') "
        "AND education_os_copilot_has_permission('copilot.action.approve'))))"
    )
    op.execute(
        'CREATE POLICY copilot_action_proposal_events_select '
        'ON "copilot_action_proposal_events" '
        f"FOR SELECT TO education_app USING ({event_visible})"
    )
    op.execute(
        'CREATE POLICY copilot_action_proposal_events_insert '
        'ON "copilot_action_proposal_events" '
        f"FOR INSERT TO education_app WITH CHECK ({event_insert})"
    )

    op.execute(
        f"""
        CREATE FUNCTION {EVENT_TRIGGER_FUNCTION}()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            proposal_owner uuid;
            latest_event text;
        BEGIN
            SELECT proposed_by_user_id
              INTO proposal_owner
              FROM copilot_action_proposals
             WHERE id = NEW.proposal_id
               AND organization_id = NEW.organization_id
               AND institution_id = NEW.institution_id;

            IF proposal_owner IS NULL THEN
                RAISE EXCEPTION 'action proposal parent not found';
            END IF;

            SELECT event_type
              INTO latest_event
              FROM copilot_action_proposal_events
             WHERE proposal_id = NEW.proposal_id
             ORDER BY created_at DESC, id DESC
             LIMIT 1;

            IF NEW.event_type = 'PROPOSED' THEN
                IF latest_event IS NOT NULL THEN
                    RAISE EXCEPTION 'PROPOSED must be first event';
                END IF;
                IF NEW.actor_user_id <> proposal_owner THEN
                    RAISE EXCEPTION 'PROPOSED actor must own proposal';
                END IF;
            ELSIF NEW.event_type IN ('APPROVED', 'REJECTED') THEN
                IF latest_event IS DISTINCT FROM 'PROPOSED' THEN
                    RAISE EXCEPTION 'approval decision requires PROPOSED state';
                END IF;
            ELSIF NEW.event_type IN ('EXECUTED', 'FAILED') THEN
                IF latest_event IS DISTINCT FROM 'APPROVED' THEN
                    RAISE EXCEPTION 'execution result requires APPROVED state';
                END IF;
            ELSE
                RAISE EXCEPTION 'unsupported action proposal event';
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER {EVENT_TRIGGER}
        BEFORE INSERT ON copilot_action_proposal_events
        FOR EACH ROW
        EXECUTE FUNCTION {EVENT_TRIGGER_FUNCTION}();
        """
    )


def downgrade() -> None:
    op.execute(
        f"DROP TRIGGER IF EXISTS {EVENT_TRIGGER} "
        "ON copilot_action_proposal_events"
    )
    op.execute(f"DROP FUNCTION IF EXISTS {EVENT_TRIGGER_FUNCTION}()")
    op.drop_table("copilot_action_proposal_events")
    op.drop_table("copilot_action_proposals")
