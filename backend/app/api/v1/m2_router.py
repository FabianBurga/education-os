from fastapi import APIRouter, Depends

from app.api.access import require_privileged_staff_access, require_staff_access
from app.modules.academics.router import router as academics_router

router = APIRouter(
    dependencies=[
        Depends(require_staff_access),
        Depends(require_privileged_staff_access),
    ]
)
router.include_router(academics_router)
