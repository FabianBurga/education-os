from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SUGGESTION_MIGRATION = (
    ROOT
    / "alembic"
    / "versions"
    / "0023_m21_intervention_suggestions.py"
)
ACCESS = ROOT / "app" / "api" / "access.py"
ROUTER = ROOT / "app" / "modules" / "interventions" / "router.py"
SUGGESTION_SERVICE = (
    ROOT
    / "app"
    / "modules"
    / "interventions"
    / "suggestion_service.py"
)
SUGGESTION_ENGINE = (
    ROOT
    / "app"
    / "modules"
    / "interventions"
    / "suggestion_engine.py"
)
SCHEMAS = ROOT / "app" / "modules" / "interventions" / "schemas.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_ec3_suggestion_permissions_are_manager_only():
    source = _read(SUGGESTION_MIGRATION)

    assert (
        'MANAGER_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", '
        '"ACADEMIC_COORDINATOR")'
    ) in source

    for permission in (
        "intervention.suggestion.read",
        "intervention.suggestion.generate",
        "intervention.suggestion.review",
    ):
        assert f'"{permission}"' in source

    assert "TEACHER" not in source[source.index("MANAGER_ROLE_KEYS"):source.index("def _permission_id")]


def test_ec3_suggestion_rls_is_tenant_and_sensitivity_scoped():
    source = _read(SUGGESTION_MIGRATION)

    assert "ALTER TABLE \"intervention_suggestions\" FORCE ROW LEVEL SECURITY" in source
    assert "intervention_suggestions_select" in source
    assert "intervention_suggestions_insert" in source
    assert "intervention_suggestions_update" in source
    assert "student_timeline.read_restricted" in source
    assert "student_timeline.read_confidential" in source
    assert "sensitivity = 'GENERAL'" in source
    assert "sensitivity = 'RESTRICTED'" in source
    assert "sensitivity = 'CONFIDENTIAL'" in source


def test_ec3_all_suggestion_api_surfaces_have_explicit_permission_dependencies():
    access = _read(ACCESS)
    router = _read(ROUTER)

    for name in (
        "require_intervention_suggestion_read",
        "require_intervention_suggestion_generate",
        "require_intervention_suggestion_review",
    ):
        assert f"def {name}(" in access

    assert "principal: SuggestionReadPrincipalDep" in router
    assert "principal: SuggestionGeneratePrincipalDep" in router
    assert "principal: SuggestionReviewPrincipalDep" in router


def test_ec3_review_routes_are_static_before_intervention_uuid_route():
    router = _read(ROUTER)

    dynamic = router.index('@router.get("/{intervention_id}"')
    for route in (
        '"/suggestions/refresh"',
        '@router.get("/suggestions"',
        '"/suggestions/{suggestion_id}"',
        '"/suggestions/{suggestion_id}/accept"',
        '"/suggestions/{suggestion_id}/dismiss"',
    ):
        assert router.index(route) < dynamic


def test_ec3_read_service_hides_rows_via_rls_and_returns_404():
    service = _read(SUGGESTION_SERVICE)

    assert "select(InterventionSuggestion)" in service
    assert '"intervention.suggestion.read"' in service
    assert "status.HTTP_404_NOT_FOUND" in service
    assert "Intervention suggestion not found" in service


def test_ec3_accept_requires_human_review_and_intervention_create_permissions():
    service = _read(SUGGESTION_SERVICE)

    accept_start = service.index("def accept_intervention_suggestion(")
    dismiss_start = service.index("def dismiss_intervention_suggestion(")
    accept_block = service[accept_start:dismiss_start]

    assert '"intervention.suggestion.review"' in accept_block
    assert '"intervention.create"' in accept_block
    assert ".with_for_update()" in service
    assert 'suggestion.status != "PENDING"' in service
    assert 'origin_type="SYSTEM_SUGGESTION"' in accept_block
    assert "suggestion.accepted_intervention_id = intervention.id" in accept_block
    assert "session.commit()" in accept_block


def test_ec3_dismiss_never_creates_an_intervention():
    service = _read(SUGGESTION_SERVICE)
    dismiss_start = service.index("def dismiss_intervention_suggestion(")
    dismiss_block = service[dismiss_start:]

    assert '"intervention.suggestion.review"' in dismiss_block
    assert 'suggestion.status = "DISMISSED"' in dismiss_block
    assert "suggestion.accepted_intervention_id = None" in dismiss_block
    assert "Intervention(" not in dismiss_block


def test_ec3_human_review_events_are_explicit_and_do_not_copy_private_note():
    service = _read(SUGGESTION_SERVICE)

    assert '"student.intervention_suggestion.accepted"' in service
    assert '"student.intervention_suggestion.dismissed"' in service
    assert '"student.intervention.opened"' in service
    assert '"human_authorized": True' in service

    helper_start = service.index("def _emit_suggestion_review_event(")
    helper_end = service.index("def _get_pending_suggestion_for_review(")
    helper = service[helper_start:helper_end]

    assert '"review_note"' not in helper
    assert "rationale_summary" not in helper


def test_ec3_rule_engine_cannot_accept_or_create_interventions():
    engine = _read(SUGGESTION_ENGINE).lower()

    assert "human_authorized" in engine
    assert '"human_authorized": false' in engine
    assert "intervention(" not in engine
    assert "accepted_intervention_id" not in engine
    assert "openai" not in engine
    assert "anthropic" not in engine
    assert "deepseek" not in engine
    assert "llm" not in engine


def test_ec3_review_payloads_require_nonempty_human_note():
    schemas = _read(SCHEMAS)

    assert "class InterventionSuggestionAccept(BaseModel):" in schemas
    assert "class InterventionSuggestionDismiss(BaseModel):" in schemas
    assert schemas.count(
        "review_note: str = Field(min_length=1, max_length=1000)"
    ) >= 2


def test_ec3_reviewed_same_evidence_episode_is_not_regenerated():
    engine = _read(SUGGESTION_ENGINE)

    assert "def _reviewed_suggestion_suppresses_candidate(" in engine
    assert '("ACCEPTED", "DISMISSED")' in engine
    assert "InterventionSuggestionEvidence.evidence_type" in engine
    assert '== "INTELLIGENCE_SIGNAL"' in engine
    assert "evidence_ids == target_evidence" in engine
    assert "_reviewed_suggestion_suppresses_candidate(" in engine
