import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_m15_frontend_stack_is_instantiated() -> None:
    package_path = REPO_ROOT / "frontend" / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))

    dependencies = {
        **package["dependencies"],
        **package["devDependencies"],
    }
    for dependency in (
        "react",
        "react-dom",
        "vite",
        "typescript",
        "tailwindcss",
        "@tanstack/react-router",
        "@tanstack/react-query",
        "@tanstack/react-table",
    ):
        assert dependency in dependencies

    assert package["version"] == "0.15.0"
    assert "typecheck" in package["scripts"]
    assert "test" in package["scripts"]
    assert "build" in package["scripts"]


def test_m15_frontend_uses_permission_driven_navigation() -> None:
    source = (
        REPO_ROOT / "frontend" / "src" / "navigation.ts"
    ).read_text(encoding="utf-8")

    for permission in (
        "admin.console.access",
        "coord.console.access",
        "teacher.console.access",
        "student.console.access",
        "guardian.console.access",
        "communications.console.access",
        "finance.console.access",
    ):
        assert permission in source

    assert "modulesForContext" in source
    assert "finance.billing" in source


def test_m15_fastapi_serves_spa_without_replacing_legacy_consoles() -> None:
    main_source = (
        REPO_ROOT / "backend" / "app" / "main.py"
    ).read_text(encoding="utf-8")
    api_router = (
        REPO_ROOT / "backend" / "app" / "api" / "v1" / "router.py"
    ).read_text(encoding="utf-8")

    assert 'version="0.15.0"' in main_source
    assert '@app.get("/app"' in main_source
    assert '"/app/{frontend_path:path}"' in main_source
    assert "frontend/dist" not in main_source
    assert "m15_router" in api_router

    for milestone in (
        "m14_router",
        "m13_router",
        "m12_router",
        "m11_router",
        "m10_router",
        "m9_router",
        "m8_router",
    ):
        assert f"router.include_router({milestone})" in api_router
