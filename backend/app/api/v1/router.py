from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlmodel import Session

from app.api.access import require_staff_access
from app.api.deps import CurrentPrincipal, get_current_principal
from app.api.v1.m1_router import router as m1_router
from app.api.v1.m2_router import router as m2_router
from app.api.v1.m3_router import router as m3_router
from app.api.v1.m4_router import router as m4_router
from app.api.v1.m5_router import router as m5_router
from app.api.v1.m6_router import router as m6_router
from app.api.v1.m7_router import router as m7_router
from app.api.v1.m8_router import router as m8_router
from app.api.v1.m9_router import router as m9_router
from app.api.v1.m10_router import router as m10_router
from app.db.session import get_session

router = APIRouter()
router.include_router(m10_router)
router.include_router(m9_router)
router.include_router(m8_router)
router.include_router(m7_router)
router.include_router(m6_router)
router.include_router(
    m5_router,
    dependencies=[Depends(require_staff_access)],
)
router.include_router(
    m4_router,
    dependencies=[Depends(require_staff_access)],
)
router.include_router(
    m3_router,
    dependencies=[Depends(require_staff_access)],
)
router.include_router(
    m2_router,
    dependencies=[Depends(require_staff_access)],
)
router.include_router(
    m1_router,
    dependencies=[Depends(require_staff_access)],
)


@router.get("/me")
def me(
    principal: CurrentPrincipal = Depends(get_current_principal),
) -> dict:
    return {
        "user_id": str(principal.user_id),
        "organization_id": str(principal.organization_id),
        "institution_id": str(principal.institution_id),
    }


@router.get("/campuses")
def list_campuses(
    _: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
) -> list[dict]:
    rows = session.exec(
        text(
            """
            SELECT id, institution_id, name
            FROM campuses
            ORDER BY name
            """
        )
    ).all()
    return [
        {
            "id": str(row[0]),
            "institution_id": str(row[1]),
            "name": row[2],
        }
        for row in rows
    ]
