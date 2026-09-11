from fastapi import APIRouter

from app.modules.family_portal.admin_router import router as family_admin_router
from app.modules.family_portal.router import router as family_portal_router

router = APIRouter()
router.include_router(family_portal_router)
router.include_router(family_admin_router)
