from pathlib import Path

from app.modules.interventions.schemas import (
    InterventionActionPage,
    InterventionActionRead,
    InterventionFollowUpPage,
    InterventionFollowUpRead,
)
from app.modules.interventions.service import (
    get_intervention_action,
    get_intervention_followup,
    list_intervention_actions,
    list_intervention_followups,
)


def test_m21_c4_read_schemas_are_from_attributes():
    assert InterventionActionRead.model_config.get("from_attributes") is True
    assert InterventionFollowUpRead.model_config.get("from_attributes") is True


def test_m21_c4_page_contracts():
    assert "items" in InterventionActionPage.model_fields
    assert "count" in InterventionActionPage.model_fields
    assert "items" in InterventionFollowUpPage.model_fields
    assert "count" in InterventionFollowUpPage.model_fields


def test_m21_c4_read_service_exports_exist():
    assert callable(get_intervention_action)
    assert callable(list_intervention_actions)
    assert callable(get_intervention_followup)
    assert callable(list_intervention_followups)


def test_m21_c4_router_contract_contains_action_and_followup_endpoints():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "interventions"
        / "router.py"
    ).read_text(encoding="utf-8")

    required_routes = (
        "/{intervention_id}/actions",
        "/actions/{action_id}",
        "/actions/{action_id}/assign",
        "/actions/{action_id}/transition",
        "/actions/{action_id}/complete",
        "/{intervention_id}/followups",
        "/followups/{followup_id}",
    )
    for route in required_routes:
        assert route in source


def test_m21_c4_write_routes_use_dedicated_permissions():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "interventions"
        / "router.py"
    ).read_text(encoding="utf-8")

    assert "ActionManagePrincipalDep" in source
    assert "FollowUpCreatePrincipalDep" in source
    assert "require_intervention_action_manage" in source
    assert "require_intervention_followup_create" in source


def test_m21_c4_access_helpers_use_c1_permissions():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "api"
        / "access.py"
    ).read_text(encoding="utf-8")

    assert '"intervention.action.manage"' in source
    assert '"intervention.followup.create"' in source


def test_m21_c4_read_service_relies_on_rls_and_parent_scope():
    source = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "interventions"
        / "service.py"
    ).read_text(encoding="utf-8")

    assert '_require_permission(session, principal, "intervention.read")' in source
    assert "_get_intervention(session, principal, intervention_id)" in source
    assert "select(InterventionAction)" in source
    assert "select(InterventionFollowUp)" in source
