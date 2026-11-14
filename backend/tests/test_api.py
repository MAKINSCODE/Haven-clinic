from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(test_engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()


def sample_slots() -> list[dict[str, str]]:
    return [
        {
            "id": "s1",
            "provider": "Dr Ade",
            "start": "2026-12-10T09:00:00Z",
            "end": "2026-12-10T09:30:00Z",
        },
        {
            "id": "s2",
            "provider": "Dr Bello",
            "start": "2026-12-09T14:00:00Z",
            "end": "2026-12-09T14:30:00Z",
        },
    ]


def is_utc(value: str) -> bool:
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return timestamp.utcoffset() == timezone.utc.utcoffset(None)


def test_reset_lists_slots_in_time_order_and_filters_provider(client: TestClient) -> None:
    response = client.post("/reset", json={"slots": sample_slots()})

    assert response.status_code == 200
    assert response.content == b""

    slots = client.get("/slots").json()
    assert [slot["id"] for slot in slots] == ["s2", "s1"]
    assert all(slot["available"] for slot in slots)
    assert is_utc(slots[0]["start"])
    assert client.get("/slots", params={"provider": "Dr Ade"}).json() == [slots[1]]
    assert client.get("/slots", params={"provider": "Dr"}).json() == []


def test_reset_replaces_slots_and_clears_previous_bookings(client: TestClient) -> None:
    client.post("/reset", json={"slots": sample_slots()})
    booking = client.post(
        "/bookings",
        json={"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"},
    )

    response = client.post("/reset", json={"slots": [sample_slots()[1]]})

    assert response.status_code == 200
    assert [slot["id"] for slot in client.get("/slots").json()] == ["s2"]
    assert client.get(f"/bookings/{booking.json()['id']}").status_code == 404


def test_reset_rolls_back_if_replacement_slots_are_invalid(client: TestClient) -> None:
    client.post("/reset", json={"slots": sample_slots()})
    invalid_slots = [sample_slots()[0], sample_slots()[0]]

    response = client.post("/reset", json={"slots": invalid_slots})

    assert response.status_code == 500
    assert [slot["id"] for slot in client.get("/slots").json()] == ["s2", "s1"]


def test_create_and_retrieve_booking_marks_slot_unavailable(client: TestClient) -> None:
    client.post("/reset", json={"slots": sample_slots()})
    created = client.post(
        "/bookings",
        json={"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"},
    )

    assert created.status_code == 201
    booking = created.json()
    assert booking["id"]
    assert booking["status"] == "confirmed"
    assert is_utc(booking["created_at"])
    assert client.get(f"/bookings/{booking['id']}").json() == booking
    slot = next(slot for slot in client.get("/slots").json() if slot["id"] == "s1")
    assert slot["available"] is False


def test_unknown_booking_returns_json_error(client: TestClient) -> None:
    response = client.get("/bookings/not-a-booking")

    assert response.status_code == 404
    assert response.json() == {"error": "booking not found"}


def test_reset_accepts_past_slots(client: TestClient) -> None:
    past_slot = {
        "id": "past",
        "provider": "Dr Past",
        "start": "2000-01-01T00:00:00Z",
        "end": "2000-01-01T00:30:00Z",
    }

    assert client.post("/reset", json={"slots": [past_slot]}).status_code == 200
    assert client.get("/slots").json()[0]["id"] == "past"