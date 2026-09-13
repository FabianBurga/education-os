from pathlib import Path


def test_m20_teacher_offline_router_has_separate_read_write_boundaries():
    router = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "modules"
        / "teacher_offline"
        / "router.py"
    )
    source = router.read_text(encoding="utf-8")

    assert "OfflineSnapshotPrincipalDep" in source
    assert "Depends(require_teacher_access)" in source
    assert "OfflineSyncPrincipalDep" in source
    assert "Depends(require_teacher_attendance)" in source
    assert "TeacherPrincipal" in source
    assert "Depends(require_staff_access)" not in source
    assert "/snapshot" in source
    assert "/sync" in source
