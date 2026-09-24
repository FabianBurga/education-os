from fastapi import APIRouter

from app.modules.accountability.queue_router import router as accountability_router

router = APIRouter()
router.include_router(accountability_router)
