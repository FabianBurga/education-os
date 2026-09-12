from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse

from app.api.v1.router import router as api_v1_router
from app.core.config import settings
from app.observability.configuration import (
    assert_production_runtime_configuration,
)
from app.observability.router import router as observability_router
from app.observability.runtime import RuntimeObservabilityMiddleware

assert_production_runtime_configuration(settings)

app = FastAPI(
    title=settings.APP_NAME,
    version="0.15.0",
)

app.add_middleware(RuntimeObservabilityMiddleware)


@app.get("/health")
def health() -> dict[str, str]:
    # Compatibility contract required by frozen M15/M16 verifiers.
    return {"status": "ok", "milestone": "M15"}


app.include_router(observability_router)
app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)

FRONTEND_DIST = (
    Path(__file__).resolve().parents[2]
    / "frontend"
    / "dist"
)


def _frontend_response(frontend_path: str = ""):
    dist = FRONTEND_DIST.resolve()
    candidate = (dist / frontend_path).resolve()

    if candidate != dist and dist not in candidate.parents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Frontend asset not found",
        )

    if frontend_path and candidate.is_file():
        return FileResponse(candidate)

    index = dist / "index.html"
    if not index.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Unified frontend has not been built. "
                "Run the M15 frontend build first."
            ),
        )
    return FileResponse(index)


@app.get("/app", include_in_schema=False)
def unified_frontend_root():
    return _frontend_response()


@app.get("/app/{frontend_path:path}", include_in_schema=False)
def unified_frontend(frontend_path: str):
    return _frontend_response(frontend_path)
