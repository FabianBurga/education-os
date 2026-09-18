from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, status

from app.modules.agents import tools, verifier
from app.modules.m21_access import require_existing_student_scope
from app.modules.student_timeline import service as timeline_service
from app.modules.student_timeline.schemas import StudentTimelinePage


class _Result:
    def __init__(self, *, first=None, rows=None):
        self._first = first
        self._rows = rows or []

    def first(self):
        return self._first

    def all(self):
        return self._rows


class _Session:
    def __init__(self, results):
        self._results = iter(results)

    def exec(self, *_args, **_kwargs):
        return next(self._results)


def _principal():
    return SimpleNamespace(user_id=uuid4(), organization_id=uuid4(), institution_id=uuid4())


def test_existing_authorized_student_with_zero_timeline_events_remains_valid(monkeypatch):
    student_id = uuid4()
    monkeypatch.setattr(timeline_service, "require_student_scope", lambda *args, **kwargs: None)
    monkeypatch.setattr(timeline_service, "require_existing_student_scope", lambda *args, **kwargs: None)
    page = timeline_service.list_student_timeline(
        _Session([_Result(rows=[])]), _principal(), student_profile_id=student_id,
    )
    assert page.student_profile_id == student_id
    assert page.entries == []


def test_nonexistent_and_cross_tenant_student_use_identical_safe_non_disclosure(monkeypatch):
    monkeypatch.setattr("app.modules.m21_access.require_student_scope", lambda *args, **kwargs: None)
    principal = _principal()
    for student_id in (uuid4(), uuid4()):
        with pytest.raises(HTTPException) as exc:
            require_existing_student_scope(
                _Session([_Result(first=None)]), principal, student_id,
                permission_key="student_timeline.read",
            )
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND
        assert exc.value.detail == "Student not found in authorized M21 scope"


def test_nonexistent_subject_stops_before_timeline_or_evidence_materialization(monkeypatch):
    student_id = uuid4()

    def reject_subject(*_args, **_kwargs):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found in authorized M21 scope")

    monkeypatch.setattr(timeline_service, "require_student_scope", lambda *args, **kwargs: None)
    monkeypatch.setattr(timeline_service, "require_existing_student_scope", reject_subject)
    with pytest.raises(HTTPException):
        timeline_service.list_student_timeline(
            _Session([]), _principal(), student_profile_id=student_id,
        )


def test_verifier_rechecks_authoritative_subject_boundary_and_rejects_empty_executor_output(monkeypatch):
    student_id = uuid4()
    monkeypatch.setattr(
        tools,
        "list_student_timeline",
        lambda *args, **kwargs: StudentTimelinePage(student_profile_id=student_id, entries=[]),
    )
    output = tools.inspect_student_timeline(object(), SimpleNamespace(), student_id=student_id)

    def reject_subject(*_args, **_kwargs):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found in authorized M21 scope")

    monkeypatch.setattr(verifier, "require_existing_student_scope", reject_subject)
    with pytest.raises(HTTPException) as exc:
        verifier.verify_student_timeline_advisor_output(
            output, session=object(), principal=SimpleNamespace(),
        )
    assert exc.value.status_code == status.HTTP_404_NOT_FOUND


def test_m25_runtime_establishes_subject_precondition_before_replay_lookup():
    source = (timeline_service.__file__.replace("student_timeline\\service.py", "agents\\service.py"))
    with open(source, encoding="utf-8") as file:
        agent_service = file.read()
    assert agent_service.index("require_existing_student_scope(") < agent_service.index("existing = session.exec")
