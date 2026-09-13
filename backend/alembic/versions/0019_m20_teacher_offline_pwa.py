"""M20 Offline-first Teacher PWA.

Revision ID: 0019_m20
Revises: 0018_m19
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_m20"
down_revision: str | None = "0018_m19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
UUID = postgresql.UUID(as_uuid=True)
ORG_CTX = "NULLIF(current_setting('app.organization_id', true), '')::uuid"
INST_CTX = "NULLIF(current_setting('app.institution_id', true), '')::uuid"
USER_CTX = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TENANT = f"organization_id = {ORG_CTX} AND institution_id = {INST_CTX}"
ACTOR = f"actor_user_id = {USER_CTX}"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        INSERT INTO institution_capabilities (institution_id, capability_key, enabled)
        SELECT id, 'teacher.offline_pwa', false FROM institutions
        ON CONFLICT (institution_id, capability_key) DO NOTHING
    """))
    op.execute("""
        CREATE FUNCTION education_os_teacher_offline_allowed()
        RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$
          SELECT EXISTS (
            SELECT 1
            FROM user_accounts ua
            JOIN staff_profiles sp ON sp.person_id=ua.person_id
              AND sp.institution_id=NULLIF(current_setting('app.institution_id', true),'')::uuid
              AND sp.status='ACTIVE'
            JOIN memberships m ON m.user_id=ua.id AND m.institution_id=sp.institution_id AND m.status='ACTIVE'
            JOIN membership_roles mr ON mr.membership_id=m.id
            JOIN role_permissions rp ON rp.role_id=mr.role_id
            JOIN permissions p ON p.id=rp.permission_id
            WHERE ua.id=NULLIF(current_setting('app.user_id', true),'')::uuid
              AND ua.is_active=true AND p.key='teacher.attendance.manage'
          )
        $$
    """)
    op.execute("REVOKE ALL ON FUNCTION education_os_teacher_offline_allowed() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION education_os_teacher_offline_allowed() TO education_app")
    op.create_table(
        "teacher_offline_receipts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("institution_id", UUID, nullable=False),
        sa.Column("actor_user_id", UUID, nullable=False),
        sa.Column("operation_id", UUID, nullable=False),
        sa.Column("operation_type", sa.String(40), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("result_entity_id", UUID, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="APPLIED"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["institution_id","organization_id"],["institutions.id","institutions.organization_id"],name="fk_teacher_offline_receipts_tenant",ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"],["user_accounts.id"],name="fk_teacher_offline_receipts_actor",ondelete="RESTRICT"),
        sa.CheckConstraint("operation_type='ATTENDANCE_MARK'", name="ck_teacher_offline_receipts_type"),
        sa.CheckConstraint("status='APPLIED'", name="ck_teacher_offline_receipts_status"),
        sa.CheckConstraint("request_sha256 ~ '^[0-9a-f]{64}$'", name="ck_teacher_offline_receipts_hash"),
        sa.UniqueConstraint("institution_id","actor_user_id","operation_id",name="uq_teacher_offline_receipts_actor_operation"),
    )
    op.create_index("ix_teacher_offline_receipts_actor_created","teacher_offline_receipts",["actor_user_id","created_at"])
    op.execute("""
      CREATE FUNCTION education_os_reject_teacher_offline_receipt_mutation()
      RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        RAISE EXCEPTION 'teacher_offline_receipts is append-only; UPDATE, DELETE and TRUNCATE are forbidden';
      END; $$
    """)
    op.execute("CREATE TRIGGER trg_teacher_offline_receipts_immutable BEFORE UPDATE OR DELETE ON teacher_offline_receipts FOR EACH ROW EXECUTE FUNCTION education_os_reject_teacher_offline_receipt_mutation()")
    op.execute("CREATE TRIGGER trg_teacher_offline_receipts_no_truncate BEFORE TRUNCATE ON teacher_offline_receipts FOR EACH STATEMENT EXECUTE FUNCTION education_os_reject_teacher_offline_receipt_mutation()")
    op.execute('ALTER TABLE "teacher_offline_receipts" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "teacher_offline_receipts" FORCE ROW LEVEL SECURITY')
    op.execute('GRANT SELECT, INSERT ON "teacher_offline_receipts" TO education_app')
    op.execute(f"CREATE POLICY teacher_offline_receipts_select ON teacher_offline_receipts FOR SELECT TO education_app USING ({TENANT} AND {ACTOR} AND education_os_teacher_offline_allowed())")
    op.execute(f"CREATE POLICY teacher_offline_receipts_insert ON teacher_offline_receipts FOR INSERT TO education_app WITH CHECK ({TENANT} AND {ACTOR} AND education_os_teacher_offline_allowed())")


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DROP TRIGGER IF EXISTS trg_teacher_offline_receipts_no_truncate ON teacher_offline_receipts")
    op.execute("DROP TRIGGER IF EXISTS trg_teacher_offline_receipts_immutable ON teacher_offline_receipts")
    op.execute("DROP FUNCTION IF EXISTS education_os_reject_teacher_offline_receipt_mutation()")
    op.drop_table("teacher_offline_receipts")
    op.execute("DROP FUNCTION IF EXISTS education_os_teacher_offline_allowed()")
    bind.execute(sa.text("DELETE FROM institution_capabilities WHERE capability_key='teacher.offline_pwa'"))
