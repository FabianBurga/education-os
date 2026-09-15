from app.modules.copilot.router import router as copilot_router


def test_copilot_leaf_router_exposes_exact_paths():
    paths = {
        route.path
        for route in copilot_router.routes
        if getattr(route, "path", None) is not None
    }

    assert "/copilot/queries" in paths
    assert "/copilot/runs/{run_id}" in paths
    assert all("action-proposals" not in path for path in paths)
