from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_m17_is_additive_reliability_foundation() -> None:
    release = (
        ROOT
        / "docs"
        / "releases"
        / "m17-production-reliability-foundation-v1.0.0-rc7.md"
    ).read_text(encoding="utf-8")

    assert "v1.0.0-rc6" in release
    assert "v1.0.0-rc7" in release
    assert "0016_m14" in release
    assert "no database migration" in release.lower()
    assert "production" in release.lower()
    assert "v1.0.0" in release


def test_m17_preserves_frozen_m15_health_contract() -> None:
    source = (ROOT / "backend" / "app" / "main.py").read_text(
        encoding="utf-8"
    )
    assert '{"status": "ok", "milestone": "M15"}' in source
    assert "RuntimeObservabilityMiddleware" in source
    assert 'version="0.15.0"' in source
    assert "assert_production_runtime_configuration" in source


def test_m17_observability_has_privacy_minimized_dimensions() -> None:
    source = (
        ROOT
        / "backend"
        / "app"
        / "observability"
        / "runtime.py"
    ).read_text(encoding="utf-8")

    assert "request_id" in source
    assert "status_class" in source
    assert "route" in source
    assert "authorization" not in source.lower()
    assert "organization_id" not in source
    assert "institution_id" not in source
    assert "user_id" not in source


def test_m17_acceptance_harness_is_reusable() -> None:
    source = (
        ROOT
        / "backend"
        / "tools"
        / "acceptance"
        / "harness.py"
    ).read_text(encoding="utf-8")

    for symbol in (
        "free_port",
        "http",
        "wait_for_health",
        "start_uvicorn",
        "stop_process",
        "edge_path",
    ):
        assert f"def {symbol}" in source


def test_m17_owner_credentials_are_not_runtime_required() -> None:
    config = (ROOT / "backend" / "app" / "core" / "config.py").read_text(
        encoding="utf-8"
    )
    alembic = (ROOT / "backend" / "alembic" / "env.py").read_text(
        encoding="utf-8"
    )

    assert "OWNER_DATABASE_URL: str | None = None" in config
    assert "OWNER_DATABASE_URL is required for Alembic migrations" in alembic
def test_m17_runtime_logging_is_nonblocking_for_legacy_verifiers() -> None:
    source = (
        ROOT
        / "backend"
        / "app"
        / "observability"
        / "runtime.py"
    ).read_text(encoding="utf-8")

    assert "QueueHandler" in source
    assert "QueueListener" in source
    assert "put_nowait" in source
    assert "runtime_log_dropped_total" in source
