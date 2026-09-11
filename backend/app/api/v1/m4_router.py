from fastapi import APIRouter, Depends

from app.api.access import require_staff_access
from app.modules.intelligence.router import router as intelligence_router

router = APIRouter(dependencies=[Depends(require_staff_access)])
router.include_router(intelligence_router)
