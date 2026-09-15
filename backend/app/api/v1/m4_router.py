from fastapi import APIRouter

from app.modules.intelligence.router import router as intelligence_router

router = APIRouter()
router.include_router(intelligence_router)
