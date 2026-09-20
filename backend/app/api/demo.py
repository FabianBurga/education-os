from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlmodel import Session

from app.core import demo
from app.core.config import settings
from app.db.session import get_session


class DemoRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_validation(request: Request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                # Do not reflect a submitted access code or identity in errors.
                raise HTTPException(422, "Invalid demo request") from exc

        return safe_validation


router = APIRouter(prefix="/api/demo", dependencies=[Depends(demo.enabled)], route_class=DemoRoute)


class Entrance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: SecretStr = Field(min_length=1, max_length=256)


class Persona(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alias: Literal["RECTOR", "COORDINATION", "TEACHER", "STUDENT", "GUARDIAN"]


def replace_session(request, response, alias=None, require_previous=False):
    token = demo.store.issue(
        alias, previous=request.cookies.get(demo.COOKIE), require_previous=require_previous
    )
    response.set_cookie(demo.COOKIE, token, httponly=True, secure=True, samesite="strict", path="/")
    response.headers["Cache-Control"] = "no-store"


@router.get("/session")
def status(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    session = demo.store.get(request.cookies.get(demo.COOKIE))
    return {
        "demo": True,
        "entrance": session is not None,
        "alias": session.alias if session else None,
    }


@router.post("/entrance", dependencies=[Depends(demo.same_origin)])
def entrance(payload: Entrance, request: Request, response: Response):
    demo.store.admit()
    actual = demo.hashlib.sha256(payload.code.get_secret_value().encode()).digest()
    expected = demo.hashlib.sha256(settings.EDUCATION_OS_DEMO_ACCESS_CODE.encode()).digest()
    if not demo.secrets.compare_digest(actual, expected):
        raise HTTPException(403, "Demo access denied")
    replace_session(request, response)
    return {"entrance": True}


@router.post("/session")
def select(
    payload: Persona, request: Request, response: Response, session: Session = Depends(get_session)
):
    demo.browser_session(request)
    demo.resolve_actor(session, payload.alias)
    replace_session(request, response, payload.alias, require_previous=True)
    return {"alias": payload.alias}


@router.post("/exit")
def exit_profile(request: Request, response: Response):
    demo.browser_session(request)
    replace_session(request, response, require_previous=True)
    return {"entrance": True}


@router.post("/logout", dependencies=[Depends(demo.same_origin)])
def logout(request: Request, response: Response):
    demo.store.revoke(request.cookies.get(demo.COOKIE))
    response.delete_cookie(demo.COOKIE, path="/", httponly=True, secure=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    return {"logged_out": True}
