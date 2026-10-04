from collections.abc import Generator
from functools import lru_cache

from sqlalchemy.engine import make_url
from sqlmodel import Session, create_engine

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)
if make_url(settings.DATABASE_URL).username != "education_app":
    raise RuntimeError("DATABASE_URL must authenticate as education_app")


def get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session


@lru_cache(maxsize=1)
def get_trusted_context_issuer_engine():
    """Return the dedicated SEC-TC1 pool; never fall back to another URL."""
    issuer_url = settings.TRUSTED_CONTEXT_ISSUER_DATABASE_URL
    if not issuer_url:
        raise RuntimeError("SEC-TC1 is unavailable: TRUSTED_CONTEXT_ISSUER_DATABASE_URL is not configured")
    if issuer_url in {settings.DATABASE_URL, settings.OWNER_DATABASE_URL}:
        raise RuntimeError("SEC-TC1 issuer URL must be distinct from application and owner URLs")
    parsed = make_url(issuer_url)
    if parsed.username != "education_context_issuer":
        raise RuntimeError("SEC-TC1 issuer URL must authenticate as education_context_issuer")
    return create_engine(issuer_url, pool_pre_ping=True, pool_size=1, max_overflow=0)
