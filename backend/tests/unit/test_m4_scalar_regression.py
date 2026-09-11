from sqlalchemy import create_engine
from sqlmodel import Session

from app.modules.intelligence.service import _scalar


def test_scalar_unwraps_sqlalchemy_row() -> None:
    engine = create_engine("sqlite://")
    with Session(engine) as session:
        assert _scalar(session, "SELECT 7") == 7
