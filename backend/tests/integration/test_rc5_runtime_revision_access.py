import os

import psycopg

DATABASE_URL_PG = os.getenv(
    "DATABASE_URL_PG",
    "postgresql://education_app:education_app_dev@localhost:5432/education_os",
)


def test_runtime_can_read_current_schema_revision() -> None:
    with psycopg.connect(
        DATABASE_URL_PG
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        row = cur.fetchone()
    assert row == ("0015_m13",)
