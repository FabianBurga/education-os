import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
M4_ROUTER = ROOT / "app/api/v1/m4_router.py"
INTEL_ROUTER = ROOT / "app/modules/intelligence/router.py"


def test_m4_parent_router_has_no_coordination_wide_dependency():
    source = M4_ROUTER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "router"
            for target in node.targets
        ):
            continue
        if isinstance(node.value, ast.Call):
            assignments.append(node.value)

    assert len(assignments) == 1
    assignment = assignments[0]
    assert ast.unparse(assignment.func) == "APIRouter"
    assert all(keyword.arg != "dependencies" for keyword in assignment.keywords)
    assert "require_coordination_access" not in source
    assert "Depends" not in source


def test_m4_parent_router_wraps_only_intelligence():
    source = M4_ROUTER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    includes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "include_router"
        ):
            continue
        includes.append(ast.unparse(node))

    assert includes == ["router.include_router(intelligence_router)"]


def test_intelligence_routes_keep_specific_access_controls():
    source = INTEL_ROUTER.read_text(encoding="utf-8")
    assert "require_intelligence_read" in source
    assert "require_intelligence_manager_read" in source
    assert "require_intelligence_manage" in source
    assert '@router.get("/rector/overview"' in source
    assert '@router.get("/signals"' in source
    assert '@router.post("/signals/refresh"' in source
    assert '@router.post("/signals/{signal_id}/resolve"' in source
    assert '@router.get("/overview"' in source
    assert '@router.get("/priorities"' in source
    assert '@router.get("/cohorts"' in source
    assert '@router.get("/trends"' in source
    assert '@router.get("/interventions"' in source
