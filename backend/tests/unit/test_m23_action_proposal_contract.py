from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = ROOT / "app/modules/copilot/router.py"


def test_action_proposal_public_surfaces_match_frozen_contract():
    source = ROUTER.read_text(encoding="utf-8")

    assert '"/action-proposals"' in source
    assert '"/action-proposals/{proposal_id}/approve"' in source
    assert '"/action-proposals/{proposal_id}/reject"' in source
    assert '"/action-proposals/create"' not in source


def test_action_proposal_router_has_no_generic_execute_surface():
    source = ROUTER.read_text(encoding="utf-8").lower()

    for forbidden in (
        "execute-anything",
        "arbitrary-sql",
        "/tools",
        "provider-tool",
    ):
        assert forbidden not in source
