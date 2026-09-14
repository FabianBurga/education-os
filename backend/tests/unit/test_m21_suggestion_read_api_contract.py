from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ACCESS = ROOT / "app" / "api" / "access.py"
ROUTER = ROOT / "app" / "modules" / "interventions" / "router.py"
SCHEMAS = ROOT / "app" / "modules" / "interventions" / "schemas.py"
SERVICE = (
    ROOT
    / "app"
    / "modules"
    / "interventions"
    / "suggestion_service.py"
)


def test_suggestion_api_permissions_exist():
    source = ACCESS.read_text(encoding="utf-8")

    assert "def require_intervention_suggestion_read(" in source
    assert '"intervention.suggestion.read"' in source
    assert "def require_intervention_suggestion_generate(" in source
    assert '"intervention.suggestion.generate"' in source


def test_suggestion_read_routes_precede_dynamic_intervention_route():
    source = ROUTER.read_text(encoding="utf-8")

    list_pos = source.index('@router.get("/suggestions"')
    detail_pos = source.index('@router.get(\n    "/suggestions/{suggestion_id}"')
    refresh_pos = source.index('@router.post(\n    "/suggestions/refresh"')
    dynamic_pos = source.index('@router.get("/{intervention_id}"')

    assert refresh_pos < dynamic_pos
    assert list_pos < dynamic_pos
    assert detail_pos < dynamic_pos

    assert "response_model=InterventionSuggestionPage" in source
    assert "response_model=InterventionSuggestionRead" in source
    assert "response_model=InterventionSuggestionRefreshRead" in source


def test_suggestion_list_supports_operational_filters():
    source = ROUTER.read_text(encoding="utf-8")

    assert 'alias="status"' in source
    assert 'alias="severity"' in source
    assert 'alias="sensitivity"' in source
    assert "student_profile_id: UUID | None" in source


def test_suggestion_service_uses_rls_visible_rows_and_404_hiding():
    source = SERVICE.read_text(encoding="utf-8")

    assert "select(InterventionSuggestion)" in source
    assert "InterventionSuggestionEvidence" in source
    assert '"intervention.suggestion.read"' in source
    assert "status.HTTP_404_NOT_FOUND" in source
    assert "Intervention suggestion not found" in source


def test_refresh_api_calls_deterministic_engine_only():
    source = ROUTER.read_text(encoding="utf-8")

    assert "refresh_intervention_suggestions(" in source
    assert "Intervention(" not in source
    assert "accepted_intervention_id" not in source


def test_refresh_schema_exposes_only_counts():
    source = SCHEMAS.read_text(encoding="utf-8")

    assert "class InterventionSuggestionRefreshRead(BaseModel):" in source
    for field in ("generated", "refreshed", "expired", "pending"):
        assert f"    {field}: int" in source
