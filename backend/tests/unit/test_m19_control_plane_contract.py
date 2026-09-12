from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_m19_migration_follows_m18_and_creates_control_plane_tables() -> None:
    source = (
        ROOT
        / "backend"
        / "alembic"
        / "versions"
        / "0018_m19_institution_control_plane.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0018_m19"' in source
    assert 'down_revision: str | None = "0017_m18"' in source
    for table in (
        "institution_control_state",
        "institution_policy_controls",
        "institution_control_changes",
    ):
        assert f'"{table}"' in source

    assert "control_plane.view" in source
    assert "control_plane.manage" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "education_os_reject_control_change_mutation" in source
    assert "BEFORE TRUNCATE" in source


def test_m19_is_additive_to_m18_router() -> None:
    source = (
        ROOT / "backend" / "app" / "api" / "v1" / "router.py"
    ).read_text(encoding="utf-8")

    assert "m19_router" in source
    assert "router.include_router(m19_router)" in source
    assert "router.include_router(m18_router)" in source
    assert source.index("router.include_router(m19_router)") < source.index(
        "router.include_router(m18_router)"
    )


def test_m19_control_plane_has_separate_view_and_manage_boundaries() -> None:
    security = (
        ROOT
        / "backend"
        / "app"
        / "modules"
        / "control_plane"
        / "security.py"
    ).read_text(encoding="utf-8")
    router = (
        ROOT
        / "backend"
        / "app"
        / "modules"
        / "control_plane"
        / "router.py"
    ).read_text(encoding="utf-8")

    assert '"control_plane.view"' in security
    assert '"control_plane.manage"' in security
    assert "ControlPlaneViewDep" in router
    assert "ControlPlaneManageDep" in router
    assert '"/capabilities/{capability_key}"' in router
    assert '"/policies/{policy_key}"' in router


def test_m19_policy_store_rejects_secret_like_keys_and_large_documents() -> None:
    source = (
        ROOT
        / "backend"
        / "app"
        / "modules"
        / "control_plane"
        / "service.py"
    ).read_text(encoding="utf-8")

    assert "FORBIDDEN_POLICY_KEY_RE" in source
    assert "MAX_POLICY_BYTES = 16_384" in source
    assert "Control Plane policies are not a secrets store" in source


def test_m19_detects_capability_drift_and_emits_canonical_events() -> None:
    source = (
        ROOT
        / "backend"
        / "app"
        / "modules"
        / "control_plane"
        / "service.py"
    ).read_text(encoding="utf-8")

    assert "managed_enabled IS DISTINCT FROM ic.enabled" in source
    assert '"institution.capability.changed"' in source
    assert '"institution.policy.changed"' in source
    assert "enqueue_canonical_event" in source


def test_m19_unified_navigation_exposes_control_plane_permission() -> None:
    source = (
        ROOT / "frontend" / "src" / "navigation.ts"
    ).read_text(encoding="utf-8")

    assert 'id: "control-plane"' in source
    assert 'permission: "control_plane.view"' in source
    assert 'legacyPath: "/api/v1/control-plane/dashboard"' in source


def test_m19_dashboard_uses_unified_session_token() -> None:
    source = (
        ROOT
        / "backend"
        / "app"
        / "modules"
        / "control_plane"
        / "control_plane_dashboard.html"
    ).read_text(encoding="utf-8")

    assert "education_os_access_token" in source
    assert "/api/v1/control-plane" in source
    assert "Institution Control Plane" in source

def test_m19_health_queries_use_bounded_high_water_mark() -> None:
    migration = (
        ROOT
        / "backend"
        / "alembic"
        / "versions"
        / "0018_m19_institution_control_plane.py"
    ).read_text(encoding="utf-8")
    service = (
        ROOT
        / "backend"
        / "app"
        / "modules"
        / "control_plane"
        / "service.py"
    ).read_text(encoding="utf-8")
    summary_source = service.split("def control_plane_summary", 1)[1]

    assert "ix_m19_event_ledger_institution_position" in migration
    assert "ix_m19_outbox_institution_created_id" in migration
    assert "ix_institution_control_changes_lookup" in migration
    assert "SET LOCAL statement_timeout = '3000ms'" in summary_source
    assert "ORDER BY l.position DESC" in summary_source
    assert "l.source_outbox_event_id" in summary_source
    assert "o.created_at > :last_created_at" in summary_source
    assert "NOT EXISTS (" not in summary_source
    assert "LEFT JOIN event_ledger" not in summary_source

def test_m19_rls_uses_security_definer_permission_helper() -> None:
    migration = (
        ROOT
        / "backend"
        / "alembic"
        / "versions"
        / "0018_m19_institution_control_plane.py"
    ).read_text(encoding="utf-8")

    assert "education_os_control_plane_has_permission" in migration
    assert "SECURITY DEFINER" in migration
    assert "SET search_path = public" in migration
    assert (
        "education_os_control_plane_has_permission('control_plane.view')"
        in migration
    )
    assert (
        "education_os_control_plane_has_permission('control_plane.manage')"
        in migration
    )
    assert "GRANT EXECUTE" in migration

