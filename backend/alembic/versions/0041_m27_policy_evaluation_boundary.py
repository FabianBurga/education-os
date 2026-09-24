"""Add the internal tenant-scoped M19 policy evaluation boundary.

Revision ID: 0041_m27_policy_evaluation_boundary
Revises: 0040_m27_obligations_sla
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0041_m27_policy_eval"
down_revision: str | None = "0040_m27_obligations_sla"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION education_os_m27_read_effective_policy(
            requested_organization_id uuid,
            requested_institution_id uuid,
            requested_policy_key text
        )
        RETURNS TABLE(enabled boolean, policy_json jsonb, policy_version integer)
        LANGUAGE sql
        SECURITY DEFINER
        STABLE
        SET search_path = public
        AS $$
            SELECT p.enabled, p.policy_json, p.policy_version
            FROM institution_policy_controls p
            WHERE p.organization_id = requested_organization_id
              AND p.institution_id = requested_institution_id
              AND p.policy_key = requested_policy_key
              AND requested_organization_id = NULLIF(current_setting('app.organization_id', true), '')::uuid
              AND requested_institution_id = NULLIF(current_setting('app.institution_id', true), '')::uuid
              AND EXISTS (
                  SELECT 1
                  FROM memberships m
                  JOIN membership_roles mr ON mr.membership_id = m.id
                  JOIN role_permissions rp ON rp.role_id = mr.role_id
                  JOIN permissions permission ON permission.id = rp.permission_id
                  WHERE m.user_id = NULLIF(current_setting('app.user_id', true), '')::uuid
                    AND m.institution_id = requested_institution_id
                    AND m.status = 'ACTIVE'
                    AND permission.key = 'accountability.obligation.create'
              )
        $$
        """
    )
    op.execute("REVOKE ALL ON FUNCTION education_os_m27_read_effective_policy(uuid, uuid, text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION education_os_m27_read_effective_policy(uuid, uuid, text) TO education_app")


def downgrade() -> None:
    op.execute("REVOKE ALL ON FUNCTION education_os_m27_read_effective_policy(uuid, uuid, text) FROM education_app")
    op.execute("DROP FUNCTION education_os_m27_read_effective_policy(uuid, uuid, text)")
