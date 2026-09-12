from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine
from app.observability.runtime import runtime_metrics

router = APIRouter(tags=["runtime-observability"])

FRONTEND_DIST = (
    Path(__file__).resolve().parents[3]
    / "frontend"
    / "dist"
)


@router.get("/health/live", include_in_schema=False)
def live() -> dict[str, str]:
    return {
        "status": "alive",
        "milestone": "M17",
        "release": settings.RELEASE_ID,
    }


def _database_ready() -> tuple[bool, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, "ok"
    except Exception:
        return False, "unavailable"


def _frontend_ready() -> tuple[bool, str]:
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return True, "ok"
    if settings.FRONTEND_REQUIRED_FOR_READINESS:
        return False, "missing"
    return True, "optional-missing"


@router.get("/health/ready", include_in_schema=False)
def ready() -> Response:
    database_ok, database_status = _database_ready()
    frontend_ok, frontend_status = _frontend_ready()
    ready_status = database_ok and frontend_ok

    payload = {
        "status": "ready" if ready_status else "not-ready",
        "milestone": "M17",
        "release": settings.RELEASE_ID,
        "checks": {
            "database": database_status,
            "frontend": frontend_status,
        },
    }

    if ready_status:
        return JSONResponse(payload, status_code=status.HTTP_200_OK)
    return JSONResponse(
        payload,
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@router.get("/metrics", include_in_schema=False)
def metrics() -> PlainTextResponse:
    return PlainTextResponse(
        runtime_metrics.render_prometheus(),
        media_type="text/plain; version=0.0.4",
    )
