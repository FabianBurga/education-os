from fastapi import APIRouter

from app.modules.interventions.router import router as intervention_router
from app.modules.student_timeline.router import router as student_timeline_router

router = APIRouter()
router.include_router(student_timeline_router)
router.include_router(intervention_router)
