from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "alembic" / "versions" / "0030_m23_action_proposals.py"


def test_0030_action_proposal_migration_contract():
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "0030_m23_action_proposals"' in source
    assert (
        'down_revision: str | None = "0029_m23_contract_hardening"'
        in source
    )
    assert "copilot_action_proposals" in source
    assert "copilot_action_proposal_events" in source
    assert "FORCE ROW LEVEL SECURITY" in source
    assert "GRANT SELECT, INSERT" in source
    assert "GRANT UPDATE" not in source
    assert "GRANT DELETE" not in source
    assert "CREATE_INTERVENTION" in source
    assert "PROPOSED" in source
    assert "APPROVED" in source
    assert "REJECTED" in source
    assert "EXECUTED" in source
    assert "FAILED" in source
    assert "education_os_copilot_validate_action_event" in source


def test_0030_status_is_event_derived_not_mutable_proposal_column():
    source = MIGRATION.read_text(encoding="utf-8")

    create_block = source.split(
        'op.create_table(\n        "copilot_action_proposals"',
        1,
    )[1].split("op.create_index(", 1)[0]
    assert '"status"' not in create_block
