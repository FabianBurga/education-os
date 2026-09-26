from fastapi import APIRouter

from app.modules.accountability.command_router import router as command_router
from app.modules.accountability.metrics_router import router as metrics_router
from app.modules.accountability.queue_router import router as accountability_router

router = APIRouter()
router.include_router(accountability_router)
router.include_router(metrics_router)
router.include_router(command_router)
