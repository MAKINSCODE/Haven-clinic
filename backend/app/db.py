import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool


def _database_url() -> str:
    configured_url = os.getenv("DATABASE_URL")
    if os.getenv("VERCEL") == "1":
        if not configured_url:
            raise RuntimeError("DATABASE_URL must be configured for Vercel deployments")
        if configured_url.startswith("sqlite"):
            raise RuntimeError("Vercel deployments require a persistent PostgreSQL database")

    url = configured_url or "sqlite:///./clinic.db"
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = _database_url()
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine_options = {"connect_args": connect_args, "pool_pre_ping": True}
if os.getenv("VERCEL") == "1":
    engine_options["poolclass"] = NullPool
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()