from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_m18_migration_is_after_m14_without_rewriting_frozen_schema() -> None:
    source = (
        ROOT
        / "backend"
        / "alembic"
        / "versions"
        / "0017_m18_event_ledger_read_models.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0017_m18"' in source
    assert 'down_revision: str | None = "0016_m14"' in source
    for table in (
        "event_ledger",
        "projection_checkpoints",
        "institution_event_daily",
        "aggregate_activity_snapshots",
    ):
        assert f'"{table}"' in source

    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "education_os_reject_event_ledger_mutation" in source
    assert "UPDATE and DELETE are forbidden" in source


def test_m18_router_is_additive() -> None:
    source = (
        ROOT / "backend" / "app" / "api" / "v1" / "router.py"
    ).read_text(encoding="utf-8")

    assert "m18_router" in source
    assert "router.include_router(m18_router)" in source
    for milestone in (
        "m15_router",
        "m14_router",
        "m13_router",
        "m12_router",
        "m11_router",
        "m10_router",
        "m9_router",
        "m8_router",
    ):
        assert f"router.include_router({milestone})" in source


def test_m18_recent_event_api_excludes_payloads() -> None:
    router = (
        ROOT / "backend" / "app" / "api" / "v1" / "m18_router.py"
    ).read_text(encoding="utf-8")
    service = (
        ROOT
        / "backend"
        / "app"
        / "modules"
        / "events"
        / "projection_service.py"
    ).read_text(encoding="utf-8")

    assert '"/events/recent"' in router
    recent_block = service.split("def recent_event_metadata", 1)[1]
    assert '"payload_json"' not in recent_block.split(
        "def daily_read_model",
        1,
    )[0]
    assert "correlation_id" in recent_block


def test_m18_projection_is_checkpointed_and_idempotent() -> None:
    source = (
        ROOT
        / "backend"
        / "app"
        / "modules"
        / "events"
        / "projection_service.py"
    ).read_text(encoding="utf-8")

    assert 'PROJECTION_KEY = "institution_activity_v1"' in source
    assert "last_position" in source
    assert "ON CONFLICT (source_outbox_event_id) DO NOTHING" in source
    assert "ON CONFLICT (" in source
    assert "processed_count" in source


def test_m18_preserves_m17_release_contract() -> None:
    config = (
        ROOT / "backend" / "app" / "core" / "config.py"
    )
    if config.exists():
        source = config.read_text(encoding="utf-8")
        assert 'RELEASE_ID: str = "v1.0.0-rc7"' in source

def test_m18_preserves_frozen_outbox_table_model_contract() -> None:
    source = (
        ROOT
        / "backend"
        / "app"
        / "modules"
        / "events"
        / "models.py"
    ).read_text(encoding="utf-8")
    outbox_block = source.split("class OutboxEvent", 1)[1].split(
        "class EventLedger",
        1,
    )[0]

    for forbidden in (
        "event_version",
        "actor_user_id",
        "correlation_id",
        "causation_id",
        "metadata_json",
    ):
        assert forbidden not in outbox_block

