from pathlib import Path

from sqlalchemy import CheckConstraint

from app.modules.interventions.models import (
    InterventionAction,
    InterventionFollowUp,
)

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "alembic"
    / "versions"
    / "0022_m21_intervention_actions_followups.py"
)


def test_m21_c1_action_model_contract():
    assert InterventionAction.__tablename__ == "intervention_actions"
    columns = InterventionAction.__table__.columns
    expected = {
        "id",
        "organization_id",
        "institution_id",
        "intervention_id",
        "action_type",
        "title",
        "description",
        "status",
        "assigned_role_code",
        "assigned_user_id",
        "due_at",
        "acknowledged_at",
        "started_at",
        "completed_at",
        "completed_by_user_id",
        "completion_note",
        "created_by_user_id",
        "created_at",
        "updated_at",
    }
    assert expected <= set(columns.keys())


def test_m21_c1_followup_model_contract():
    assert InterventionFollowUp.__tablename__ == "intervention_followups"
    columns = InterventionFollowUp.__table__.columns
    expected = {
        "id",
        "organization_id",
        "institution_id",
        "intervention_id",
        "followup_type",
        "sensitivity",
        "note",
        "observed_at",
        "created_by_user_id",
        "created_at",
    }
    assert expected <= set(columns.keys())


def test_m21_c1_action_status_constraint_is_present():
    constraints = {
        c.name: str(c.sqltext)
        for c in InterventionAction.__table__.constraints
        if isinstance(c, CheckConstraint)
    }
    assert "ck_intervention_actions_status" in constraints
    assert "OVERDUE" in constraints["ck_intervention_actions_status"]
    assert "COMPLETED" in constraints["ck_intervention_actions_status"]


def test_m21_c1_followup_sensitivity_constraint_is_present():
    constraints = {
        c.name: str(c.sqltext)
        for c in InterventionFollowUp.__table__.constraints
        if isinstance(c, CheckConstraint)
    }
    assert "ck_intervention_followups_sensitivity" in constraints
    assert "CONFIDENTIAL" in constraints["ck_intervention_followups_sensitivity"]


def test_m21_c1_migration_contract():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'revision: str = "0022_m21_actions_followups"' in src
    assert 'down_revision: str | None = "0021_m21_intervention_core"' in src
    assert '"intervention.action.manage"' in src
    assert '"intervention.followup.create"' in src
    assert '"intervention_actions"' in src
    assert '"intervention_followups"' in src
    assert 'ENABLE ROW LEVEL SECURITY' in src
    assert 'FORCE ROW LEVEL SECURITY' in src
    assert "intervention_actions_select" in src
    assert "intervention_actions_insert" in src
    assert "intervention_actions_update" in src
    assert "intervention_followups_select" in src
    assert "intervention_followups_insert" in src


def test_m21_c1_followups_are_append_only_for_runtime_role():
    src = MIGRATION.read_text(encoding="utf-8")
    assert (
        'GRANT SELECT, INSERT ON "intervention_followups" TO education_app'
        in src
    )
    assert (
        'GRANT SELECT, INSERT, UPDATE ON "intervention_followups" TO education_app'
        not in src
    )


def test_m21_c1_permissions_default_to_managers():
    src = MIGRATION.read_text(encoding="utf-8")
    assert (
        'MANAGER_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", "ACADEMIC_COORDINATOR")'
        in src
    )
    assert "TEACHER" not in src.split("MANAGER_ROLE_KEYS", maxsplit=1)[1].split(
        "\n", maxsplit=1
    )[0]