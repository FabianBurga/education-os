import os
from pathlib import Path

import psycopg
from alembic.config import Config
from alembic.script import ScriptDirectory

DATABASE_URL_PG = os.getenv(
    "DATABASE_URL_PG",
    "postgresql://education_app:education_app_dev@localhost:5432/education_os",
)
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _repository_head_revision() -> str:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1
    return heads[0]


def test_runtime_can_read_current_schema_revision() -> None:
    with psycopg.connect(
        DATABASE_URL_PG
    ) as conn, conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        row = cur.fetchone()

    assert row == (_repository_head_revision(),)
