from fastapi import APIRouter, Depends

from app.api.access import require_coordination_access
from app.modules.intelligence.router import router as intelligence_router

router = APIRouter(dependencies=[Depends(require_coordination_access)])
router.include_router(intelligence_router)
