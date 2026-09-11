"""RC5 runtime hardening.

Revision ID: 0009_rc5
Revises: 0008_m7
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009_rc5"
down_revision: str | None = "0008_m7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Pilot Readiness reveals only the current migration revision.
    op.execute("GRANT SELECT ON TABLE alembic_version TO education_app")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON TABLE alembic_version FROM education_app")
