from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

EXPECTED_PERMISSIONS = {
    "communications.console.access",
    "communications.messages.view",
    "communications.messages.manage",
    "communications.publish",
    "communications.templates.manage",
    "communications.delivery.view",
}


def test_m13_migration_contract() -> None:
    source = (
        ROOT
        / "alembic"
        / "versions"
        / "0015_m13_communications_center.py"
    ).read_text(encoding="utf-8")

    assert 'revision: str = "0015_m13"' in source
    assert 'down_revision: str | None = "0014_m12"' in source
    for permission in EXPECTED_PERMISSIONS:
        assert permission in source

    for table in (
        "communication_templates",
        "communications",
        "communication_targets",
        "communication_recipients",
    ):
        assert table in source
        assert f'_enable_staff_rls("{table}")' in source

    assert "membership_roles" not in source.split("def upgrade() -> None:", 1)[1].split(
        "def downgrade() -> None:", 1
    )[0]


def test_m13_router_contract() -> None:
    source = (
        ROOT / "app" / "modules" / "communications" / "router.py"
    ).read_text(encoding="utf-8")

    expected = (
        '"/dashboard"',
        '"/summary"',
        '"/target-options"',
        '"/templates"',
        '"/messages"',
        '"/messages/{communication_id}/targets"',
        '"/messages/{communication_id}/preview"',
        '"/messages/{communication_id}/publish"',
        '"/messages/{communication_id}/archive"',
        '"/messages/{communication_id}/delivery"',
    )
    for route in expected:
        assert route in source


def test_m13_api_router_is_additive() -> None:
    source = (ROOT / "app" / "api" / "v1" / "router.py").read_text(
        encoding="utf-8"
    )
    assert "m13_router" in source
    assert "router.include_router(m13_router)" in source
    for milestone in ("m12_router", "m11_router", "m10_router", "m9_router"):
        assert f"router.include_router({milestone})" in source
