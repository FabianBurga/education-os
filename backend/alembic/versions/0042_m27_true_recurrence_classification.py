"""M27-8: persist the frozen TRUE_RECURRENCE classification."""

from collections.abc import Sequence

from alembic import op

revision: str = "0042_m27_true_recurrence"
down_revision: str | None = "0041_m27_policy_eval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_accountability_cases_recurrence",
        "accountability_cases",
        type_="check",
    )
    op.create_check_constraint(
        "ck_accountability_cases_recurrence",
        "accountability_cases",
        "recurrence_classification IN ('NEW_EPISODE','SAME_ACTIVE_EPISODE','REOPENED_CASE','NEW_RELATED_EPISODE','NEW_CATEGORY_CASE','TRUE_RECURRENCE')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_accountability_cases_recurrence",
        "accountability_cases",
        type_="check",
    )
    op.create_check_constraint(
        "ck_accountability_cases_recurrence",
        "accountability_cases",
        "recurrence_classification IN ('NEW_EPISODE','SAME_ACTIVE_EPISODE','REOPENED_CASE','NEW_RELATED_EPISODE','NEW_CATEGORY_CASE')",
    )
