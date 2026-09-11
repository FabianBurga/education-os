from fastapi import APIRouter

from app.modules.operations.router import router as operations_router

router = APIRouter()
router.include_router(operations_router)
