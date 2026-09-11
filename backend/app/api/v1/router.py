from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.api.v1.m1_router import router as m1_router
from app.db.session import get_session

router = APIRouter()
router.include_router(m1_router)


@router.get("/me")
def me(principal: CurrentPrincipal = Depends(get_current_principal)) -> dict:
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
    rows = session.exec(text("SELECT id, institution_id, name FROM campuses ORDER BY name")).all()
    return [{"id": str(r[0]), "institution_id": str(r[1]), "name": r[2]} for r in rows]
