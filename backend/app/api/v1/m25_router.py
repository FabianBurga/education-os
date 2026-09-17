from fastapi import APIRouter

from app.modules.agents.router import router as agents_router

router = APIRouter()
router.include_router(agents_router)
