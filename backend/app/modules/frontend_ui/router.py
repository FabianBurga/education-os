from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import CurrentPrincipal, get_current_principal
from app.db.session import get_session
from app.modules.frontend_ui.schemas import UiBootstrapRead
from app.modules.frontend_ui.service import ui_bootstrap

router = APIRouter(prefix="/ui", tags=["unified-frontend"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/bootstrap", response_model=UiBootstrapRead)
def bootstrap(
    principal: CurrentPrincipal = Depends(get_current_principal),
    session: Session = Depends(get_session),
):
    return ui_bootstrap(session, principal)
