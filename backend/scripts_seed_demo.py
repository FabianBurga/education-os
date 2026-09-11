from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text

from app.core.config import settings
from app.core.security import hash_password


def main() -> None:
    engine = create_engine(settings.OWNER_DATABASE_URL)

    org_a, org_b = uuid4(), uuid4()
    inst_a, inst_b = uuid4(), uuid4()
    campus_a, campus_b = uuid4(), uuid4()
    person_a, person_b = uuid4(), uuid4()
    user_a, user_b = uuid4(), uuid4()
    mem_a, mem_b = uuid4(), uuid4()
    now = datetime.now(timezone.utc)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_logs"))
        conn.execute(text("DELETE FROM outbox_events"))
        conn.execute(text("DELETE FROM membership_roles"))
        conn.execute(text("DELETE FROM role_permissions"))
        conn.execute(text("DELETE FROM roles"))
        conn.execute(text("DELETE FROM memberships"))
        conn.execute(text("DELETE FROM user_accounts"))
        conn.execute(text("DELETE FROM persons"))
        conn.execute(text("DELETE FROM campuses"))
        conn.execute(text("DELETE FROM institutions"))
        conn.execute(text("DELETE FROM organizations"))

        for oid, oname in [(org_a, "Demo Network A"), (org_b, "Demo Network B")]:
            conn.execute(
                text("INSERT INTO organizations(id,name,status,created_at) VALUES(:id,:name,'ACTIVE',:now)"),
                {"id": oid, "name": oname, "now": now},
            )

        for iid, oid, name in [
            (inst_a, org_a, "Unidad Educativa Demo A"),
            (inst_b, org_b, "Unidad Educativa Demo B"),
        ]:
            conn.execute(
                text("""
                    INSERT INTO institutions(id,organization_id,name,type,status,created_at)
                    VALUES(:id,:org,:name,'PRIVATE','ACTIVE',:now)
                """),
                {"id": iid, "org": oid, "name": name, "now": now},
            )

        for cid, iid, name in [
            (campus_a, inst_a, "Campus Norte A"),
            (campus_b, inst_b, "Campus Norte B"),
        ]:
            conn.execute(
                text("INSERT INTO campuses(id,institution_id,name,created_at) VALUES(:id,:inst,:name,:now)"),
                {"id": cid, "inst": iid, "name": name, "now": now},
            )

        demo_password = hash_password("Demo-Only-Change-Me-123!")
        for pid, oid, uid, email, first, last in [
            (person_a, org_a, user_a, "rector.a@example.test", "Rector", "Demo A"),
            (person_b, org_b, user_b, "rector.b@example.test", "Rector", "Demo B"),
        ]:
            conn.execute(
                text("""
                    INSERT INTO persons(id,organization_id,given_names,family_names,primary_email,created_at)
                    VALUES(:id,:org,:first,:last,:email,:now)
                """),
                {"id": pid, "org": oid, "first": first, "last": last, "email": email, "now": now},
            )
            conn.execute(
                text("""
                    INSERT INTO user_accounts(id,person_id,login_email,password_hash,is_active,created_at)
                    VALUES(:id,:person,:email,:hash,true,:now)
                """),
                {"id": uid, "person": pid, "email": email, "hash": demo_password, "now": now},
            )

        for mid, uid, iid in [(mem_a, user_a, inst_a), (mem_b, user_b, inst_b)]:
            conn.execute(
                text("""
                    INSERT INTO memberships(id,user_id,institution_id,status,created_at)
                    VALUES(:id,:user,:inst,'ACTIVE',:now)
                """),
                {"id": mid, "user": uid, "inst": iid, "now": now},
            )

    print("Synthetic tenants created.")
    print(f"A: org={org_a} institution={inst_a} user={user_a}")
    print(f"B: org={org_b} institution={inst_b} user={user_b}")


if __name__ == "__main__":
    main()
