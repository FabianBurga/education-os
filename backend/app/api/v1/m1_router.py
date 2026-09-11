from fastapi import APIRouter, Depends

from app.api.access import require_privileged_staff_access, require_staff_access
from app.modules.enrollment.router import router as enrollment_router
from app.modules.families.router import router as families_router
from app.modules.students.router import router as students_router

router = APIRouter(
    dependencies=[
        Depends(require_staff_access),
        Depends(require_privileged_staff_access),
    ]
)
router.include_router(students_router)
router.include_router(families_router)
router.include_router(enrollment_router)
