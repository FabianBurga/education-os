import pytest

from app.core.config import settings
from tools import demo_fixture


def test_fixture_aliases_and_story_constants_are_fixed():
    assert demo_fixture.ALIASES == ("RECTOR", "COORDINATION", "TEACHER", "STUDENT", "GUARDIAN")
    assert demo_fixture.ORG_NAME == "Education OS Demo"
    assert "wildcard" not in " ".join(sorted(demo_fixture.PERMISSIONS["RECTOR"]))
    assert all("*" not in permission for values in demo_fixture.PERMISSIONS.values() for permission in values)


def test_fixture_refuses_without_explicit_demo_mode(monkeypatch):
    monkeypatch.setattr(settings, "EDUCATION_OS_DEMO_MODE", False)
    monkeypatch.delenv("EDUCATION_OS_DEMO_MODE", raising=False)
    with pytest.raises(RuntimeError, match="EDUCATION_OS_DEMO_MODE=true"):
        demo_fixture._require_demo_mode()


def test_fixture_state_file_is_external_by_default():
    assert "Education_OS_M0_Foundation" not in str(demo_fixture.STATE_FILE)


def test_fixture_principal_config_shape_has_distinct_roles_and_scopes():
    assert set(demo_fixture.ROLE_KEYS) == set(demo_fixture.ALIASES)
    assert len(set(demo_fixture.ROLE_KEYS.values())) == 5
    assert all(demo_fixture.PERMISSIONS[alias] for alias in demo_fixture.ALIASES)
