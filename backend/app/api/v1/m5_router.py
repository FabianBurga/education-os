from fastapi import APIRouter, Depends

from app.api.access import require_privileged_staff_access, require_staff_access
from app.modules.automation.router import router as automation_router

router = APIRouter(
    dependencies=[
        Depends(require_staff_access),
        Depends(require_privileged_staff_access),
    ]
)
router.include_router(automation_router)
