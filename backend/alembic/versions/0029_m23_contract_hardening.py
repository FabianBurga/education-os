"""M23 frozen-contract hardening.

Revision ID: 0029_m23_contract_hardening
Revises: 0028_m23_advisory_answers
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0029_m23_contract_hardening"
down_revision: str | None = "0028_m23_advisory_answers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"

REGISTRY_TABLES = (
    "copilot_policy_versions",
    "copilot_prompt_versions",
    "copilot_model_registry",
)

RUN_UPDATE_COLUMNS = (
    "status",
    "evidence_manifest_sha256",
    "failure_code",
    "usage_json",
    "cost_json",
    "completed_at",
)


def _drop_policy(table: str, policy: str) -> None:
    op.execute(f'DROP POLICY IF EXISTS "{policy}" ON "{table}"')


def _registry_write_gate() -> str:
    return (
        f"{TENANT} "
        "AND education_os_copilot_has_permission('copilot.manage') "
        "AND education_os_copilot_is_manager()"
    )


def _own_run_gate() -> str:
    return (
        f"{TENANT} "
        f"AND actor_user_id = {USER_CTX} "
        "AND education_os_copilot_has_permission('copilot.use')"
    )


def _evidence_parent_visible_gate() -> str:
    parent_visible = (
        "EXISTS ("
        "SELECT 1 FROM copilot_runs cr "
        "WHERE cr.id = run_id "
        "AND cr.organization_id = organization_id "
        "AND cr.institution_id = institution_id "
        "AND education_os_copilot_run_visible(cr.actor_user_id)"
        ")"
    )
    return (
        f"{TENANT} "
        "AND education_os_copilot_has_permission('copilot.use') "
        f"AND {parent_visible}"
    )


def _evidence_actor_owned_insert_gate() -> str:
    return (
        f"{TENANT} "
        "AND education_os_copilot_has_permission('copilot.use') "
        "AND EXISTS ("
        "SELECT 1 FROM copilot_runs cr "
        "WHERE cr.id = run_id "
        "AND cr.organization_id = organization_id "
        "AND cr.institution_id = institution_id "
        f"AND cr.actor_user_id = {USER_CTX}"
        ")"
    )


def upgrade() -> None:
    bind = op.get_bind()

    # Frozen role contract:
    # SYSTEM_ADMIN: use + manage + approve
    # RECTOR / ACADEMIC_COORDINATOR: use + approve
    # TEACHER: use
    bind.execute(
        sa.text(
            """
            DELETE FROM role_permissions rp
            USING roles r, permissions p
            WHERE rp.role_id = r.id
              AND rp.permission_id = p.id
              AND p.key = 'copilot.manage'
              AND r.key IN ('RECTOR', 'ACADEMIC_COORDINATOR')
            """
        )
    )

    # Policy/prompt/model versions are append-only for runtime.
    for table in REGISTRY_TABLES:
        op.execute(
            f'REVOKE UPDATE, DELETE ON "{table}" FROM education_app'
        )
        _drop_policy(table, f"{table}_update")
        _drop_policy(table, f"{table}_delete")

    # Evidence history is append-only.
    op.execute(
        'REVOKE UPDATE, DELETE ON "copilot_evidence_refs" '
        "FROM education_app"
    )
    _drop_policy(
        "copilot_evidence_refs",
        "copilot_evidence_refs_update",
    )
    _drop_policy(
        "copilot_evidence_refs",
        "copilot_evidence_refs_delete",
    )

    # Runs cannot be deleted. Only execution-result columns may change.
    op.execute(
        'REVOKE UPDATE, DELETE ON "copilot_runs" FROM education_app'
    )
    columns = ", ".join(f'"{column}"' for column in RUN_UPDATE_COLUMNS)
    op.execute(
        f'GRANT UPDATE ({columns}) ON "copilot_runs" TO education_app'
    )
    _drop_policy("copilot_runs", "copilot_runs_delete")
    _drop_policy("copilot_runs", "copilot_runs_update")

    own_gate = _own_run_gate()
    op.execute(
        'CREATE POLICY copilot_runs_update ON "copilot_runs" '
        f"FOR UPDATE TO education_app USING ({own_gate}) "
        f"WITH CHECK ({own_gate})"
    )

    # Evidence insertion must belong to the current actor's own run.
    _drop_policy(
        "copilot_evidence_refs",
        "copilot_evidence_refs_insert",
    )
    evidence_insert_gate = _evidence_actor_owned_insert_gate()
    op.execute(
        'CREATE POLICY copilot_evidence_refs_insert '
        'ON "copilot_evidence_refs" '
        f"FOR INSERT TO education_app WITH CHECK ({evidence_insert_gate})"
    )


def downgrade() -> None:
    bind = op.get_bind()

    # Restore 0027 role grants.
    bind.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            SELECT r.id, p.id
            FROM roles r
            CROSS JOIN permissions p
            WHERE r.key IN ('RECTOR', 'ACADEMIC_COORDINATOR')
              AND p.key = 'copilot.manage'
              AND NOT EXISTS (
                  SELECT 1
                  FROM role_permissions rp
                  WHERE rp.role_id = r.id
                    AND rp.permission_id = p.id
              )
            """
        )
    )

    # Restore mutable registry semantics from 0027.
    write_gate = _registry_write_gate()
    for table in REGISTRY_TABLES:
        op.execute(
            f'GRANT UPDATE, DELETE ON "{table}" TO education_app'
        )
        op.execute(
            f'CREATE POLICY {table}_update ON "{table}" '
            f"FOR UPDATE TO education_app USING ({write_gate}) "
            f"WITH CHECK ({write_gate})"
        )
        op.execute(
            f'CREATE POLICY {table}_delete ON "{table}" '
            f"FOR DELETE TO education_app USING ({write_gate})"
        )

    # Restore evidence policies from 0027.
    op.execute(
        'GRANT UPDATE, DELETE ON "copilot_evidence_refs" '
        "TO education_app"
    )
    _drop_policy(
        "copilot_evidence_refs",
        "copilot_evidence_refs_insert",
    )
    evidence_write_gate = _evidence_parent_visible_gate()
    evidence_manage_gate = _registry_write_gate()
    op.execute(
        'CREATE POLICY copilot_evidence_refs_insert '
        'ON "copilot_evidence_refs" '
        f"FOR INSERT TO education_app WITH CHECK ({evidence_write_gate})"
    )
    op.execute(
        'CREATE POLICY copilot_evidence_refs_update '
        'ON "copilot_evidence_refs" '
        f"FOR UPDATE TO education_app USING ({evidence_write_gate}) "
        f"WITH CHECK ({evidence_write_gate})"
    )
    op.execute(
        'CREATE POLICY copilot_evidence_refs_delete '
        'ON "copilot_evidence_refs" '
        f"FOR DELETE TO education_app USING ({evidence_manage_gate})"
    )

    # Restore broad run update/delete semantics from 0027.
    columns = ", ".join(f'"{column}"' for column in RUN_UPDATE_COLUMNS)
    op.execute(
        f'REVOKE UPDATE ({columns}) ON "copilot_runs" FROM education_app'
    )
    op.execute(
        'GRANT UPDATE, DELETE ON "copilot_runs" TO education_app'
    )
    _drop_policy("copilot_runs", "copilot_runs_update")

    own_gate = _own_run_gate()
    manage_gate = _registry_write_gate()
    update_gate = f"(({own_gate}) OR ({manage_gate}))"
    op.execute(
        'CREATE POLICY copilot_runs_update ON "copilot_runs" '
        f"FOR UPDATE TO education_app USING ({update_gate}) "
        f"WITH CHECK ({update_gate})"
    )
    op.execute(
        'CREATE POLICY copilot_runs_delete ON "copilot_runs" '
        f"FOR DELETE TO education_app USING ({manage_gate})"
    )
