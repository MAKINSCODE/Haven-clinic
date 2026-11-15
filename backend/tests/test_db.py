import pytest
from sqlalchemy.engine import make_url

from app.db import _database_url


def test_database_url_requires_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL must be configured"):
        _database_url()


def test_database_url_rejects_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:///clinic.db")

    with pytest.raises(RuntimeError, match="must use PostgreSQL"):
        _database_url()


def test_database_url_uses_psycopg_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@db.example.test/clinic",
    )

    url = make_url(_database_url())

    assert url.drivername == "postgresql+psycopg"
