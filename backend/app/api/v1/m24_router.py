from fastapi import APIRouter

from app.modules.integrations.router import router as integrations_router

router = APIRouter()
router.include_router(integrations_router)
