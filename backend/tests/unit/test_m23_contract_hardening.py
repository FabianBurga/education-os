from pathlib import Path

from app.modules.copilot import access

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (
    ROOT
    / "alembic"
    / "versions"
    / "0029_m23_contract_hardening.py"
)


def test_role_semantics_match_frozen_contract():
    assert access.COPILOT_MANAGE_ROLES == {"SYSTEM_ADMIN"}
    assert access.COPILOT_APPROVER_ROLES == {
        "SYSTEM_ADMIN",
        "RECTOR",
        "ACADEMIC_COORDINATOR",
    }
    # Compatibility alias may remain for old tests, but must not authorize manage.
    assert access.COPILOT_MANAGER_ROLES == access.COPILOT_APPROVER_ROLES


def test_manage_and_approve_use_separate_role_sets():
    source = Path(access.__file__).read_text(encoding="utf-8")

    manage_body = source.split(
        "def require_copilot_manage(",
        1,
    )[1].split(
        "def require_copilot_action_approve(",
        1,
    )[0]
    approve_body = source.split(
        "def require_copilot_action_approve(",
        1,
    )[1]

    assert "COPILOT_MANAGE_ROLES" in manage_body
    assert "COPILOT_APPROVER_ROLES" not in manage_body
    assert "COPILOT_APPROVER_ROLES" in approve_body


def test_0029_is_forward_hardening_not_history_rewrite():
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'revision: str = "0029_m23_contract_hardening"' in source
    assert (
        'down_revision: str | None = "0028_m23_advisory_answers"'
        in source
    )
    assert "DELETE FROM role_permissions" in source
    assert "'copilot.manage'" in source
    assert "'RECTOR'" in source
    assert "'ACADEMIC_COORDINATOR'" in source

    for table in (
        "copilot_policy_versions",
        "copilot_prompt_versions",
        "copilot_model_registry",
        "copilot_evidence_refs",
    ):
        assert table in source

    assert (
        'REVOKE UPDATE, DELETE ON "copilot_runs" FROM education_app'
        in source
    )
    assert "RUN_UPDATE_COLUMNS" in source
    allowed_block = source.split(
        "RUN_UPDATE_COLUMNS = (",
        1,
    )[1].split(")", 1)[0]
    for forbidden in (
        "actor_user_id",
        "organization_id",
        "institution_id",
        "intent",
        "request_sha256",
        "policy_key",
        "prompt_key",
        "provider_key",
        "model_key",
        "created_at",
    ):
        assert f'"{forbidden}"' not in allowed_block


def test_run_update_allowlist_matches_runtime_mutations():
    expected = {
        "status",
        "evidence_manifest_sha256",
        "failure_code",
        "usage_json",
        "cost_json",
        "completed_at",
    }

    service = (
        ROOT / "app/modules/copilot/service.py"
    ).read_text(encoding="utf-8")
    advisory = (
        ROOT / "app/modules/copilot/advisory.py"
    ).read_text(encoding="utf-8")

    for field in expected:
        assert (
            f"run.{field} =" in service
            or f"run.{field} =" in advisory
        )
