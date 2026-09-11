from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_auth_and_access_raw_uuid_comparisons_are_typed() -> None:
    deps = (BACKEND_ROOT / "app/api/deps.py").read_text(encoding="utf-8")
    access = (BACKEND_ROOT / "app/api/access.py").read_text(encoding="utf-8")
    assert "m.user_id = CAST(:user_id AS uuid)" in deps
    assert "m.institution_id = CAST(:institution_id AS uuid)" in deps
    assert "i.organization_id = CAST(:organization_id AS uuid)" in deps
    assert "id = CAST(:user_id AS uuid)" in access
    assert "person_id = CAST(:person_id AS uuid)" in access
    assert "institution_id = CAST(:institution_id AS uuid)" in access
