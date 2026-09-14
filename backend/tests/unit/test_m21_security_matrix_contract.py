from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TIMELINE_MIGRATION = (
    ROOT / "alembic" / "versions" / "0020_m21_student_timeline.py"
)
INTERVENTION_MIGRATION = (
    ROOT / "alembic" / "versions" / "0021_m21_intervention_core.py"
)
ACCESS = ROOT / "app" / "api" / "access.py"
M21_ACCESS = ROOT / "app" / "modules" / "m21_access.py"
TIMELINE_ROUTER = (
    ROOT / "app" / "modules" / "student_timeline" / "router.py"
)
TIMELINE_SERVICE = (
    ROOT / "app" / "modules" / "student_timeline" / "service.py"
)
INTERVENTION_ROUTER = (
    ROOT / "app" / "modules" / "interventions" / "router.py"
)
INTERVENTION_SERVICE = (
    ROOT / "app" / "modules" / "interventions" / "service.py"
)
INSTITUTIONAL_VIEWS = (
    ROOT
    / "app"
    / "modules"
    / "interventions"
    / "institutional_views.py"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_m21_dc_role_matrix_is_explicit_in_rls_migrations():
    timeline = _read(TIMELINE_MIGRATION)
    interventions = _read(INTERVENTION_MIGRATION)

    assert (
        'GENERAL_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", '
        '"ACADEMIC_COORDINATOR", "TEACHER")'
    ) in timeline
    assert (
        'RESTRICTED_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", '
        '"ACADEMIC_COORDINATOR")'
    ) in timeline
    assert 'CONFIDENTIAL_ROLE_KEYS = ("SYSTEM_ADMIN",)' in timeline

    assert (
        'MANAGER_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", '
        '"ACADEMIC_COORDINATOR")'
    ) in interventions
    assert (
        'READ_ROLE_KEYS = ("SYSTEM_ADMIN", "RECTOR", '
        '"ACADEMIC_COORDINATOR", "TEACHER")'
    ) in interventions


def test_m21_dc_teacher_is_read_only_for_intervention_core():
    source = _read(INTERVENTION_MIGRATION)

    assert (
        '_grant_to_role_keys(bind, '
        'permission_ids["intervention.read"], READ_ROLE_KEYS)'
    ) in source
    for permission in (
        "intervention.create",
        "intervention.update",
        "intervention.assign",
        "intervention.resolve",
        "intervention.close",
        "intervention.admin",
    ):
        assert f'"{permission}",' in source


def test_m21_dc_permission_dependencies_cover_every_mutation_surface():
    access = _read(ACCESS)
    router = _read(INTERVENTION_ROUTER)

    required_access_functions = (
        "require_intervention_read",
        "require_intervention_create",
        "require_intervention_update",
        "require_intervention_assign",
        "require_intervention_resolve",
        "require_intervention_close",
        "require_intervention_action_manage",
        "require_intervention_followup_create",
    )
    for name in required_access_functions:
        assert f"def {name}(" in access

    assert "principal: CreatePrincipalDep" in router
    assert "principal: AssignPrincipalDep" in router
    assert "principal: UpdatePrincipalDep" in router
    assert "principal: ResolvePrincipalDep" in router
    assert "principal: ClosePrincipalDep" in router
    assert "principal: ActionManagePrincipalDep" in router
    assert "principal: FollowUpCreatePrincipalDep" in router


def test_m21_dc_student_scope_is_enforced_beyond_ui():
    timeline_router = _read(TIMELINE_ROUTER)
    timeline_service = _read(TIMELINE_SERVICE)
    intervention_service = _read(INTERVENTION_SERVICE)
    access = _read(M21_ACCESS)

    assert "Depends(require_student_timeline_read)" in timeline_router
    assert "require_student_scope(" in timeline_service
    assert "teacher_has_student_scope(" in access
    assert "Student not found in authorized M21 scope" in access
    assert intervention_service.count("require_student_scope(") >= 6


def test_m21_dc_sensitive_rows_are_not_teacher_visible_in_rls():
    timeline = _read(TIMELINE_MIGRATION)
    interventions = _read(INTERVENTION_MIGRATION)

    for source in (timeline, interventions):
        assert "sensitivity = 'GENERAL'" in source
        assert "sensitivity = 'RESTRICTED'" in source
        assert "sensitivity = 'CONFIDENTIAL'" in source
        assert "TEACHER_STUDENT_SCOPE" in source
        assert "HAS_RESTRICTED_READ" in source
        assert "HAS_CONFIDENTIAL_READ" in source


def test_m21_dc_all_intervention_read_surfaces_use_privacy_sanitizers():
    service = _read(INTERVENTION_SERVICE)
    views = _read(INSTITUTIONAL_VIEWS)

    assert "intervention_read_for_principal(" in service
    assert "action_read_for_principal(" in service
    assert "followup_read_for_principal(" in service

    assert '"reason": None if protected else entity.reason' in views
    assert '"objective": None if protected else entity.objective' in views
    assert '"outcome_summary": (' in views
    assert '"description": None if protected else action.description' in views
    assert '"completion_note": (' in views
    assert '"note": None if protected else followup.note' in views


def test_m21_dc_institutional_queue_is_management_only_and_safe_summary():
    router = _read(INTERVENTION_ROUTER)
    views = _read(INSTITUTIONAL_VIEWS)

    assert '"/institutional/queue"' in router
    assert '"SYSTEM_ADMIN"' in views
    assert '"RECTOR"' in views
    assert '"ACADEMIC_COORDINATOR"' in views
    assert "Institutional intervention view requires management role" in views

    queue_fn = views.index("def list_institutional_intervention_queue(")
    queue_source = views[queue_fn:]

    assert "reason" not in queue_source
    assert "objective" not in queue_source
    assert "outcome_summary" not in queue_source


def test_m21_dc_static_queue_route_precedes_uuid_detail_route():
    router = _read(INTERVENTION_ROUTER)

    assert router.index('"/institutional/queue"') < router.index(
        '@router.get("/{intervention_id}"'
    )


def test_m21_dc_cross_tenant_checks_exist_on_intervention_children():
    service = _read(INTERVENTION_SERVICE)

    assert "organization_id != principal.organization_id" in service
    assert "institution_id != principal.institution_id" in service
    assert "Intervention not found in authorized scope" in service
    assert "Intervention action not found in authorized scope" in service
    assert "Intervention follow-up not found in authorized scope" in service


def test_m21_dc_confidential_full_detail_requires_explicit_permission():
    views = _read(INSTITUTIONAL_VIEWS)

    assert '"student_timeline.read_confidential"' in views
    assert 'if sensitivity == "GENERAL":' in views
    assert "return not is_teacher(session, principal)" in views