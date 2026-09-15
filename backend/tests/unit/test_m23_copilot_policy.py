from uuid import uuid4

from app.modules.copilot.policy import GateFacts, decide_pre_invocation


def _facts(**changes):
    values = {
        "intent": "INSTITUTION_RISK_SUMMARY",
        "has_use_permission": True,
        "is_manager": True,
        "is_teacher_actor": False,
        "target_student_profile_id": None,
        "teacher_has_target_scope": False,
        "policy_enabled": True,
        "prompt_enabled": True,
        "model_eligible": True,
        "daily_run_count": 0,
        "max_daily_runs_per_user": 50,
    }
    values.update(changes)
    return GateFacts(**values)


def test_pre_gate_allows_manager_institution_summary_when_all_gates_pass():
    decision = decide_pre_invocation(_facts())
    assert decision.allowed is True
    assert decision.code == "ALLOW"


def test_pre_gate_denies_missing_permission_before_model_use():
    decision = decide_pre_invocation(
        _facts(has_use_permission=False)
    )
    assert decision.allowed is False
    assert decision.code == "MISSING_COPILOT_USE"


def test_pre_gate_denies_teacher_manager_only_intent():
    decision = decide_pre_invocation(
        _facts(
            is_manager=False,
            is_teacher_actor=True,
        )
    )
    assert decision.allowed is False
    assert decision.code == "MANAGER_SCOPE_REQUIRED"


def test_pre_gate_requires_teacher_student_scope():
    decision = decide_pre_invocation(
        _facts(
            intent="STUDENT_SUPPORT_SUMMARY",
            is_manager=False,
            is_teacher_actor=True,
            target_student_profile_id=uuid4(),
            teacher_has_target_scope=False,
        )
    )
    assert decision.allowed is False
    assert decision.code == "STUDENT_SCOPE_DENIED"


def test_pre_gate_denies_when_no_registered_model_is_eligible():
    decision = decide_pre_invocation(
        _facts(model_eligible=False)
    )
    assert decision.allowed is False
    assert decision.code == "NO_ELIGIBLE_MODEL"


def test_pre_gate_denies_quota_before_invocation():
    decision = decide_pre_invocation(
        _facts(
            daily_run_count=50,
            max_daily_runs_per_user=50,
        )
    )
    assert decision.allowed is False
    assert decision.code == "QUOTA_EXCEEDED"
