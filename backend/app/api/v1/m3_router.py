from fastapi import APIRouter, Depends

from app.api.access import require_privileged_staff_access, require_staff_access
from app.modules.attendance.router import router as attendance_router
from app.modules.grades.router import router as grades_router

router = APIRouter(
    dependencies=[
        Depends(require_staff_access),
        Depends(require_privileged_staff_access),
    ]
)
router.include_router(attendance_router)
router.include_router(grades_router)
