from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "app/modules/copilot/actions.py"


def test_action_service_is_bounded_to_create_intervention():
    source = SERVICE.read_text(encoding="utf-8")

    assert 'ACTION_TYPE_CREATE_INTERVENTION = "CREATE_INTERVENTION"' in source
    assert "create_intervention(" in source
    assert "commit=False" in source

    for forbidden in (
        "finance",
        "communications",
        "void_payment",
        "publish_announcement",
        "send_message",
        "getattr(service",
    ):
        assert forbidden not in source.lower()


def test_action_service_requires_human_approval_and_reauthorization():
    source = SERVICE.read_text(encoding="utf-8")

    assert "require_copilot_action_approve(session, principal)" in source
    assert "InterventionCreate.model_validate" in source
    assert "SYSTEM_SUGGESTION" in source
    assert "Action proposal cannot widen student scope" in source
    assert "Action proposal citations must be backed" in source


def test_action_service_records_approval_before_domain_execution():
    source = SERVICE.read_text(encoding="utf-8")

    approve = source.split(
        "def approve_action_proposal(",
        1,
    )[1].split("def reject_action_proposal(", 1)[0]

    approved_pos = approve.index('event_type="APPROVED"')
    first_commit_pos = approve.index("session.commit()")
    execution_pos = approve.index("create_intervention(")

    assert approved_pos < first_commit_pos < execution_pos
    assert 'event_type="EXECUTED"' in approve
    assert 'event_type="FAILED"' in approve


def test_action_decisions_serialize_without_proposal_update_privilege():
    source = SERVICE.read_text(encoding="utf-8")

    assert "FOR UPDATE" not in source
    assert "pg_advisory_xact_lock" in source

    approve = source.split(
        "def approve_action_proposal(",
        1,
    )[1].split("def reject_action_proposal(", 1)[0]
    reject = source.split("def reject_action_proposal(", 1)[1]

    for decision in (approve, reject):
        lock_pos = decision.index("_lock_proposal_lifecycle(")
        latest_pos = decision.index("_latest_event_type(")
        insert_pos = decision.index("_insert_event(")
        assert lock_pos < latest_pos < insert_pos


def test_internal_creation_requires_sufficient_evidence():
    source = SERVICE.read_text(encoding="utf-8")

    assert "def create_action_proposal_internal(" in source
    assert '"SUFFICIENT"' in source
    assert "target_student_profile_id" in source
    assert "evidence_citations" in source
