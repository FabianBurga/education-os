from app.modules.accountability.command_schemas import (
    DecisionCommand,
    ObligationCompletionCommand,
    ObligationWaiverCommand,
    OwnerCommand,
    ReviewCommand,
)
from app.modules.accountability.command_router import router


def test_m27_command_schemas_keep_bounded_authority_and_evidence() -> None:
    assert "CREATE_INTERVENTION" in str(DecisionCommand.model_fields["decision_type"].annotation)
    assert "M27_INFORMATION" in str(ObligationCompletionCommand.model_fields["evidence_type"].annotation)
    assert "REQUEST_INFORMATION" in str(DecisionCommand.model_fields["decision_type"].annotation)
    assert "provenance_sha256" in ReviewCommand.model_fields
    assert "reason_code" in ObligationWaiverCommand.model_fields
    assert "owner_user_id" in OwnerCommand.model_fields


def test_m27_commands_require_sha256_idempotency_and_provenance() -> None:
    required = {
        "idempotency_key": "a" * 64,
        "provenance_sha256": "b" * 64,
    }
    payload = OwnerCommand(owner_user_id="00000000-0000-0000-0000-000000000001", **required)
    assert len(payload.idempotency_key) == 64
    assert len(payload.provenance_sha256) == 64


def test_m27_command_routes_are_explicit_and_bounded() -> None:
    paths = {route.path for route in router.routes}
    assert "/accountability/cases/{case_id}/review" in paths
    assert "/accountability/cases/{case_id}/decision" in paths
    assert "/accountability/obligations/{obligation_id}/complete" in paths
    assert "/accountability/obligations/{obligation_id}/waive" in paths
    assert not any("/interventions" in path for path in paths)
