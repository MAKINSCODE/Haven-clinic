import os
from collections.abc import Generator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")


def _database_url() -> str:
    configured_url = os.getenv("DATABASE_URL")
    if not configured_url:
        raise RuntimeError(
            "DATABASE_URL must be configured in the backend environment or backend/.env"
        )

    try:
        url = make_url(configured_url)
    except ArgumentError:
        raise RuntimeError("DATABASE_URL must be a valid PostgreSQL connection URL") from None

    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise RuntimeError("DATABASE_URL must use PostgreSQL")
    return url.set(drivername="postgresql+psycopg").render_as_string(
        hide_password=False
    )


DATABASE_URL = _database_url()
engine_options = {"pool_pre_ping": True}
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