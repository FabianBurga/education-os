from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.access import TeacherPrincipal, require_teacher_access, require_teacher_attendance
from app.db.session import get_session
from app.modules.teacher_offline.schemas import (
    TeacherOfflineSnapshot,
    TeacherOfflineSyncBatch,
    TeacherOfflineSyncResponse,
)
from app.modules.teacher_offline.service import (
    sync_teacher_offline_operations,
    teacher_offline_snapshot,
)

router=APIRouter(prefix="/teacher/offline",tags=["teacher-offline-pwa"])
OfflineSnapshotPrincipalDep = Annotated[
    TeacherPrincipal,
    Depends(require_teacher_access),
]
OfflineSyncPrincipalDep = Annotated[
    TeacherPrincipal,
    Depends(require_teacher_attendance),
]

SessionDep=Annotated[Session,Depends(get_session)]
OfflineTeacherDep=Annotated[TeacherPrincipal,Depends(require_teacher_attendance)]

@router.get("/snapshot",response_model=TeacherOfflineSnapshot)
def snapshot(principal: OfflineSnapshotPrincipalDep, session: SessionDep, days: int=Query(default=14,ge=1,le=30)):
    return teacher_offline_snapshot(session,principal,days=days)

@router.post("/sync",response_model=TeacherOfflineSyncResponse)
def sync(payload: TeacherOfflineSyncBatch, principal: OfflineSyncPrincipalDep, session: SessionDep):
    return sync_teacher_offline_operations(session,principal,payload)
