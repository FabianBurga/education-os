from app.modules.copilot.router import router as copilot_router


def test_copilot_leaf_router_exposes_exact_paths():
    paths = {
        route.path
        for route in copilot_router.routes
        if getattr(route, "path", None) is not None
    }

    assert "/copilot/queries" in paths
    assert "/copilot/runs/{run_id}" in paths
    assert paths == {
        "/copilot/queries",
        "/copilot/runs/{run_id}",
        "/copilot/action-proposals",
        "/copilot/action-proposals/{proposal_id}/approve",
        "/copilot/action-proposals/{proposal_id}/reject",
    }
