from fastapi import APIRouter

from app.modules.copilot.router import router as copilot_router

router = APIRouter()
router.include_router(copilot_router)
