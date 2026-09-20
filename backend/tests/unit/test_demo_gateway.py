from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core import demo
from app.core.config import settings
from app.main import app


def configuration(**changes):
    values = dict(
        EDUCATION_OS_DEMO_MODE=True,
        APP_ENV="staging",
        EDUCATION_OS_DEMO_SYNTHETIC_ONLY=True,
        OWNER_DATABASE_URL=None,
        DATABASE_URL="postgresql://education_app@db/demo",
        SECRET_KEY="x" * 40,
        EDUCATION_OS_DEMO_ACCESS_CODE="y" * 32,
        PUBLIC_BASE_URL="https://demo.example.test",
        EDUCATION_OS_DEMO_ORGANIZATION_ID=str(uuid4()),
        EDUCATION_OS_DEMO_INSTITUTION_ID=str(uuid4()),
        EDUCATION_OS_DEMO_PRINCIPALS={key: str(uuid4()) for key in demo.ROLES},
    )
    values.update(changes)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    "changes",
    [
        {"APP_ENV": "production"},
        {"APP_ENV": "development"},
        {"EDUCATION_OS_DEMO_SYNTHETIC_ONLY": False},
        {"OWNER_DATABASE_URL": "secret"},
        {"PUBLIC_BASE_URL": "http://localhost"},
        {"EDUCATION_OS_DEMO_ORGANIZATION_ID": ""},
        {"EDUCATION_OS_DEMO_INSTITUTION_ID": ""},
        {"EDUCATION_OS_DEMO_PRINCIPALS": {}},
        {"EDUCATION_OS_DEMO_ACCESS_CODE": "short"},
        {"SECRET_KEY": "change-me"},
    ],
)
def test_startup_fails_closed(changes):
    with pytest.raises(RuntimeError, match="Invalid staging"):
        demo.validate_demo_configuration(configuration(**changes))


def test_valid_configuration_and_disabled_defaults():
    demo.validate_demo_configuration(configuration())
    demo.validate_demo_configuration(SimpleNamespace(EDUCATION_OS_DEMO_MODE=False))


def test_store_expiration_revocation_and_bounded_rate(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(demo.time, "monotonic", lambda: clock[0])
    store = demo.SessionStore()
    first = store.issue("RECTOR")
    second = store.issue("STUDENT")
    assert store.get(first).alias == "RECTOR"
    store.revoke(first)
    assert store.get(first) is None and store.get(second).alias == "STUDENT"
    clock[0] += demo.TTL
    assert store.get(second) is None
    for _ in range(10):
        store.admit()
    with pytest.raises(Exception) as error:
        store.admit()
    assert error.value.status_code == 429


def test_disabled_routes_and_normal_bearer(monkeypatch):
    monkeypatch.setattr(settings, "EDUCATION_OS_DEMO_MODE", False)
    client = TestClient(app)
    for path in ("session", "entrance", "exit", "logout"):
        result = (
            client.get("/api/demo/session")
            if path == "session"
            else client.post("/api/demo/" + path, json={})
        )
        assert result.status_code == 404
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer invalid"}).status_code == 401


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "EDUCATION_OS_DEMO_MODE", True)
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://demo.example.test")
    monkeypatch.setattr(
        settings, "EDUCATION_OS_DEMO_ACCESS_CODE", "unit-only-entrance-code-never-deployed"
    )
    monkeypatch.setattr(demo, "store", demo.SessionStore())
    return TestClient(
        app, base_url="https://demo.example.test", headers={"Origin": "https://demo.example.test"}
    )


def test_outer_gate_csrf_cookie_and_logout(client):
    assert client.get("/api/demo/session").json() == {
        "demo": True,
        "entrance": False,
        "alias": None,
    }
    assert client.post("/api/demo/session", json={"alias": "RECTOR"}).status_code == 401
    assert client.post("/api/demo/entrance", json={"code": "wrong"}).status_code == 403
    assert (
        client.post(
            "/api/demo/entrance",
            json={"code": settings.EDUCATION_OS_DEMO_ACCESS_CODE},
            headers={"Origin": "https://evil.test"},
        ).status_code
        == 403
    )
    result = client.post(
        "/api/demo/entrance", json={"code": settings.EDUCATION_OS_DEMO_ACCESS_CODE}
    )
    assert result.status_code == 200
    cookie = result.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
    assert "Max-Age" not in cookie  # browser-session cookie; server enforces TTL
    token = client.cookies.get(demo.COOKIE)
    assert token not in result.text and token not in str(result.url)
    assert client.post("/api/demo/logout", json={}).status_code == 200
    assert demo.store.get(token) is None


@pytest.mark.parametrize(
    "body",
    [
        {"alias": "ADMIN"},
        {"alias": str(uuid4())},
        {"alias": "RECTOR", "institution_id": str(uuid4())},
        {"alias": "TEACHER", "permissions": ["*"]},
        {"alias": "RECTOR", "user_id": str(uuid4())},
    ],
)
def test_strict_alias_input(client, body):
    assert client.post("/api/demo/session", json=body).status_code == 422


def test_no_cookie_cannot_use_bearer_to_enter_demo(client):
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer anything"}).status_code == 401
    assert client.get("/api/v1/student/dashboard").status_code == 401


def test_validation_does_not_reflect_secret(client):
    secret = "private-test-input" * 30
    response = client.post("/api/demo/entrance", json={"code": secret})
    assert response.status_code == 422 and secret not in response.text


def test_http_expiry_and_csrf_fail_closed(client, monkeypatch):
    result = client.post(
        "/api/demo/entrance", json={"code": settings.EDUCATION_OS_DEMO_ACCESS_CODE}
    )
    assert result.status_code == 200
    assert client.post("/api/demo/exit", json={}, headers={"Origin": ""}).status_code == 403
    now = demo.time.monotonic()
    monkeypatch.setattr(demo.time, "monotonic", lambda: now + demo.TTL + 1)
    assert client.get("/api/demo/session").json()["entrance"] is False
    assert client.get("/api/v1/me").status_code == 401


def test_entrance_rate_limit(client):
    for _ in range(10):
        assert client.post("/api/demo/entrance", json={"code": "incorrect"}).status_code == 403
    assert client.post("/api/demo/entrance", json={"code": "incorrect"}).status_code == 429
