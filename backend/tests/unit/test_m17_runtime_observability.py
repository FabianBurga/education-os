from fastapi.testclient import TestClient

from app.main import app
from app.observability.configuration import production_runtime_errors

client = TestClient(app)


def test_m17_liveness_and_request_id() -> None:
    response = client.get(
        "/health/live",
        headers={"X-Request-ID": "m17-test-request"},
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "m17-test-request"
    assert response.json() == {
        "status": "alive",
        "milestone": "M17",
        "release": "v1.0.0-rc7",
    }


def test_m17_invalid_request_id_is_replaced() -> None:
    response = client.get(
        "/health/live",
        headers={"X-Request-ID": "invalid request id"},
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] != "invalid request id"
    assert response.headers["x-request-id"]


def test_m17_metrics_are_low_cardinality() -> None:
    client.get("/health/live")
    client.get("/m17-missing-path/abcdef")

    response = client.get("/metrics")
    assert response.status_code == 200
    body = response.text
    assert "education_os_build_info" in body
    assert 'status_class="2xx"' in body
    assert 'status_class="4xx"' in body
    assert "path=" not in body
    assert "user_id" not in body
    assert "institution_id" not in body


def test_m17_production_runtime_guard() -> None:
    valid = {
        "APP_ENV": "production",
        "SECRET_KEY": "m17-production-secret-0123456789012345",
        "DATABASE_URL": (
            "postgresql+psycopg://education_app:"
            "strong-runtime-secret@db.internal:5432/education_os"
        ),
        "PUBLIC_BASE_URL": "https://education.example.org",
        "FRONTEND_REQUIRED_FOR_READINESS": True,
        "OWNER_DATABASE_URL": None,
    }
    assert production_runtime_errors(valid) == []

    bad = dict(valid)
    bad["SECRET_KEY"] = "change-me"
    bad["DATABASE_URL"] = (
        "postgresql+psycopg://education_owner:"
        "education_owner_dev@localhost:5432/education_os"
    )
    bad["PUBLIC_BASE_URL"] = "http://localhost"
    bad["FRONTEND_REQUIRED_FOR_READINESS"] = False
    bad["OWNER_DATABASE_URL"] = (
        "postgresql+psycopg://education_owner:owner@db:5432/education_os"
    )
    errors = production_runtime_errors(bad)
    assert len(errors) >= 5
