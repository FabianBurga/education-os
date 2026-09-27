from fastapi import APIRouter

from app.modules.academics.router import router as academics_router

router = APIRouter()
router.include_router(academics_router)
