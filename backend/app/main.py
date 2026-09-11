from fastapi import FastAPI

from app.api.v1.router import router as api_v1_router
from app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "milestone": "M0"}


app.include_router(api_v1_router, prefix=settings.API_V1_PREFIX)
