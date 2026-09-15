from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.deps import CurrentPrincipal
from app.modules.intelligence import access


@pytest.fixture
def principal() -> CurrentPrincipal:
    return CurrentPrincipal(
        user_id=uuid4(),
        organization_id=uuid4(),
        institution_id=uuid4(),
    )


def test_read_requires_permission(monkeypatch, principal):
    monkeypatch.setattr(access, "has_permission", lambda *_args: False)

    with pytest.raises(HTTPException) as exc:
        access.require_intelligence_read(object(), principal)

    assert exc.value.status_code == 403
    assert "intelligence.read" in str(exc.value.detail)


def test_manager_read_requires_manager_role(monkeypatch, principal):
    monkeypatch.setattr(access, "has_permission", lambda *_args: True)
    monkeypatch.setattr(access, "has_any_role", lambda *_args: False)

    with pytest.raises(HTTPException) as exc:
        access.require_intelligence_manager_read(object(), principal)

    assert exc.value.status_code == 403
    assert "management role" in str(exc.value.detail)


def test_manager_read_allows_manager(monkeypatch, principal):
    monkeypatch.setattr(access, "has_permission", lambda *_args: True)
    monkeypatch.setattr(access, "has_any_role", lambda *_args: True)

    assert access.require_intelligence_manager_read(object(), principal) is None


def test_manage_requires_manage_permission(monkeypatch, principal):
    monkeypatch.setattr(access, "has_permission", lambda *_args: False)
    monkeypatch.setattr(access, "has_any_role", lambda *_args: True)

    with pytest.raises(HTTPException) as exc:
        access.require_intelligence_manage(object(), principal)

    assert exc.value.status_code == 403
    assert "intelligence.manage" in str(exc.value.detail)


def test_manage_rejects_teacher_even_with_permission(monkeypatch, principal):
    monkeypatch.setattr(access, "has_permission", lambda *_args: True)
    monkeypatch.setattr(access, "has_any_role", lambda *_args: False)

    with pytest.raises(HTTPException) as exc:
        access.require_intelligence_manage(object(), principal)

    assert exc.value.status_code == 403
    assert "management role" in str(exc.value.detail)
