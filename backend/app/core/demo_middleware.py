from fastapi import HTTPException
from sqlmodel import Session
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core import demo
from app.core.config import settings
from app.db.session import engine


class DemoBoundaryMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not settings.EDUCATION_OS_DEMO_MODE:
            return await call_next(request)
        path = request.url.path
        # HTML dashboards are ordinarily public shells. In demo, authenticate
        # before serving them; exclude admin, finance, communications and Copilot.
        if path.startswith("/api/v1/") and path.endswith("/dashboard"):
            try:
                await run_in_threadpool(_authorize_dashboard, request)
            except HTTPException as exc:
                return JSONResponse(
                    {"detail": exc.detail},
                    status_code=exc.status_code,
                    headers={"Cache-Control": "no-store"},
                )
        response = await call_next(request)
        if path.startswith(("/api/", "/app")):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
        return response


def _authorize_dashboard(request):
    with Session(engine) as session:
        demo.demo_identity(request, session)
