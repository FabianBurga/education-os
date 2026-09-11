from fastapi import APIRouter

from app.modules.automation.router import router as automation_router

router = APIRouter()
router.include_router(automation_router)
