from datetime import UTC, datetime
from uuid import uuid4

from app.api.access import GuardianPrincipal
from app.modules.family_portal import service


class _Result:
    def __init__(self, row):
        self._row = row

    def one(self):
        return self._row


class _Session:
    def __init__(self, notice, rows):
        self.notice = notice
        self.rows = iter(rows)
        self.committed = False

    def get(self, model, _notice_id):
        return self.notice

    def exec(self, _query):
        return _Result(next(self.rows))

    def commit(self):
        self.committed = True


def test_acknowledge_notice_uses_guardian_bound_capability_and_preserves_read_contract(monkeypatch):
    actor_id, org_id, inst_id, person_id, guardian_id, notice_id, receipt_id = [uuid4() for _ in range(7)]
    guardian = GuardianPrincipal(actor_id, org_id, inst_id, person_id, guardian_id)
    acknowledged_at = datetime.now(UTC)
    session = _Session(
        type("Notice", (), {"status": "PUBLISHED", "student_profile_id": None})(),
        [(receipt_id,), (acknowledged_at,)],
    )
    captured = {}

    def issue(**kwargs):
        captured.update(kwargs)
        return "opaque-capability"

    monkeypatch.setattr(service, "issue_guardian_notice_acknowledgement", issue)
    result = service.acknowledge_notice(session, guardian, notice_id)

    assert captured["guardian"] == guardian
    assert captured["notice_id"] == notice_id
    assert len(captured["operation_key"]) == 64
    assert len(captured["operation_fingerprint"]) == 64
    assert result.family_notice_id == notice_id
    assert result.guardian_profile_id == guardian_id
    assert result.acknowledged_at == acknowledged_at
    assert session.committed
