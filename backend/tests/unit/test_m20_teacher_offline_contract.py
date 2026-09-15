import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_migration():
    s = read("backend/alembic/versions/0019_m20_teacher_offline_pwa.py")
    assert 'revision: str = "0019_m20"' in s
    assert 'down_revision: str | None = "0018_m19"' in s
    assert "FORCE ROW LEVEL SECURITY" in s
    assert "SECURITY DEFINER" in s
    assert "BEFORE TRUNCATE" in s
    assert "'teacher.offline_pwa', false" in s


def test_router_additive():
    source = read("backend/app/api/v1/router.py")
    tree = ast.parse(source)

    included_names = []
    for node in tree.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue

        call = node.value
        if not (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "router"
            and call.func.attr == "include_router"
            and call.args
            and isinstance(call.args[0], ast.Name)
        ):
            continue

        included_names.append(call.args[0].id)

    legacy_router_order = [
        "m20_router",
        "m19_router",
        "m18_router",
        "m15_router",
        "m14_router",
        "m13_router",
        "m12_router",
        "m11_router",
        "m10_router",
        "m9_router",
        "m8_router",
        "m7_router",
        "m6_router",
        "m5_router",
        "m4_router",
        "m3_router",
        "m2_router",
        "m1_router",
    ]

    # Routers introduced after M20 are additive. They may appear ahead of the
    # frozen M20->M1 chain, while that historical chain itself must remain
    # complete, contiguous and ordered.
    legacy_start = included_names.index("m20_router")
    newer_routers = included_names[:legacy_start]

    assert included_names[legacy_start:] == legacy_router_order
    assert "m21_router" in newer_routers
    assert len(included_names) == len(set(included_names))

    assert "from app.api.v1.m20_router import router as m20_router" in source
    assert "router.include_router(m20_router)" in source
    assert "router.include_router(m19_router)" in source


def test_sync_contract():
    s = read("backend/app/modules/teacher_offline/service.py")
    assert "pg_advisory_xact_lock" in s
    assert "teacher-offline:operation:" in s
    assert "teacher-offline:target:" in s
    assert "return sorted(keys)" in s
    assert "IDEMPOTENCY_MISMATCH" in s
    assert 'status="CONFLICT"' in s
    assert 'event_type="teacher.attendance.synced"' in s
    assert '"note_excluded"' in s


def test_snapshot_bound():
    s = read("backend/app/modules/teacher_offline/service.py")
    r = read("backend/app/modules/teacher_offline/router.py")
    assert "SNAPSHOT_TTL_HOURS=24" in s
    assert "ge=1,le=30" in r


def test_service_worker_privacy():
    s = read("frontend/public/sw.js")
    assert 'url.pathname.startsWith("/api/")' in s
    assert 'url.pathname.startsWith("/health")' in s


def test_offline_store_no_token():
    s = read("frontend/src/lib/teacher-offline-store.ts")
    assert "indexedDB" in s
    assert "Authorization" not in s
    assert "education_os_access_token" not in s


def test_bootstrap_session_scoped():
    s = read("frontend/src/lib/session.ts")
    r = read("frontend/src/router.tsx")
    assert "sessionStorage" in s
    assert "localStorage" not in s
    assert "readCachedBootstrap" in r
    assert "purgeTeacherOfflinePartition" in r
    assert "async function signOut" in r
    assert "await purgeTeacherOfflinePartition" in r


def test_frontend_batch_and_expiry_guards():
    page = read("frontend/src/pages/teacher-pwa-page.tsx")
    core = read("frontend/src/teacher-offline-core.ts")
    assert "chunkTeacherOfflineOperations(operations)" in page
    assert "size>100" in core.replace(" ", "")
    assert "deleteTeacherOfflineSnapshot" in page
    assert "disabled={expired||" in page.replace(" ", "")


def test_teacher_workspace():
    w = read("frontend/src/pages/workspace-page.tsx")
    p = read("frontend/src/pages/teacher-pwa-page.tsx")
    assert 'module.id==="teacher"' in w
    assert "<TeacherPwaPage/>" in w
    assert 'data-testid="teacher-pwa-page"' in p


def test_manifest_scope():
    m = read("frontend/public/manifest.webmanifest")
    i = read("frontend/index.html")
    main = read("frontend/src/main.tsx")
    assert '"start_url":"/app/workspace/teacher"' in m
    assert '"scope":"/app/"' in m
    assert "/app/manifest.webmanifest" in i
    assert '"/app/sw.js"' in main
