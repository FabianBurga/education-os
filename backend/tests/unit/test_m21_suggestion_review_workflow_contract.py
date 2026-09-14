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


def test_review_permission_dependency_exists():
    source = ACCESS.read_text(encoding="utf-8")
    assert "def require_intervention_suggestion_review(" in source
    assert '"intervention.suggestion.review"' in source


def test_accept_and_dismiss_payloads_require_human_note():
    source = SCHEMAS.read_text(encoding="utf-8")
    assert "class InterventionSuggestionAccept(BaseModel):" in source
    assert "class InterventionSuggestionDismiss(BaseModel):" in source
    assert "review_note: str = Field(min_length=1, max_length=1000)" in source


def test_accept_and_dismiss_routes_precede_dynamic_intervention_route():
    source = ROUTER.read_text(encoding="utf-8")
    accept_pos = source.index('"/suggestions/{suggestion_id}/accept"')
    dismiss_pos = source.index('"/suggestions/{suggestion_id}/dismiss"')
    dynamic_pos = source.index('@router.get("/{intervention_id}"')
    assert accept_pos < dynamic_pos
    assert dismiss_pos < dynamic_pos
    assert "SuggestionReviewPrincipalDep" in source


def test_acceptance_is_locked_atomic_and_human_authorized():
    source = SERVICE.read_text(encoding="utf-8")
    assert ".with_for_update()" in source
    assert 'suggestion.status != "PENDING"' in source
    assert 'origin_type="SYSTEM_SUGGESTION"' in source
    assert "suggestion.accepted_intervention_id = intervention.id" in source
    assert '"student.intervention.opened"' in source
    assert '"student.intervention_suggestion.accepted"' in source
    assert '"human_authorized": True' in source
    assert "create_intervention(" not in source


def test_dismissal_does_not_create_intervention():
    source = SERVICE.read_text(encoding="utf-8")
    start = source.index("def dismiss_intervention_suggestion(")
    block = source[start:]
    assert 'suggestion.status = "DISMISSED"' in block
    assert "suggestion.accepted_intervention_id = None" in block
    assert '"student.intervention_suggestion.dismissed"' in block
    assert "Intervention(" not in block


def test_review_events_do_not_emit_review_note():
    source = SERVICE.read_text(encoding="utf-8")
    helper_start = source.index("def _emit_suggestion_review_event(")
    helper_end = source.index("def _get_pending_suggestion_for_review(")
    helper = source[helper_start:helper_end]
    assert '"review_note"' not in helper
    assert "rationale_summary" not in helper
