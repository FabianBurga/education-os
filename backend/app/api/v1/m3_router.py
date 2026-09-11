from fastapi import APIRouter

from app.modules.attendance.router import router as attendance_router
from app.modules.grades.router import router as grades_router

router = APIRouter()
router.include_router(attendance_router)
router.include_router(grades_router)
