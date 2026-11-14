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
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("API_KEY", "test-api-key")
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
        with TestClient(
            app,
            headers={"X-API-Key": "test-api-key"},
            raise_server_exceptions=False,
        ) as test_client:
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


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/reset", {"slots": []}),
        ("GET", "/slots", None),
        ("POST", "/bookings", {"slot_id": "s1", "name": "Ada", "email": "ada@example.com"}),
        ("GET", "/bookings/missing", None),
    ],
)
@pytest.mark.parametrize("api_key", [None, "incorrect-key"])
def test_all_routes_reject_missing_or_incorrect_api_keys(
    client: TestClient,
    method: str,
    path: str,
    body: dict[str, object] | None,
    api_key: str | None,
) -> None:
    if api_key is None:
        client.headers.pop("X-API-Key", None)
        headers: dict[str, str] = {}
    else:
        headers = {"X-API-Key": api_key}
    response = client.request(method, path, json=body, headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]


def test_valid_api_key_is_accepted(client: TestClient) -> None:
    response = client.get("/slots", headers={"X-API-Key": "test-api-key"})

    assert response.status_code == 200


def test_api_key_must_be_configured(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_KEY")

    response = client.get("/slots")

    assert response.status_code == 500
    assert response.json() == {"error": "API key is not configured"}


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
    assert response.json() == {"error": "internal server error"}
    assert [slot["id"] for slot in client.get("/slots").json()] == ["s2", "s1"]


def test_create_and_retrieve_booking_marks_slot_unavailable(client: TestClient) -> None:
    client.post("/reset", json={"slots": sample_slots()})
    created = client.post(
        "/bookings",
        json={"slot_id": "s1", "name": "  Ada Obi  ", "email": " ADA@EXAMPLE.COM "},
    )

    assert created.status_code == 201
    booking = created.json()
    assert booking["id"]
    assert booking["status"] == "confirmed"
    assert booking["name"] == "Ada Obi"
    assert booking["email"] == "ada@example.com"
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


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": "Ada", "email": "ada@example.com"},
        {"slot_id": "s1", "email": "ada@example.com"},
        {"slot_id": "s1", "name": "Ada"},
        {"slot_id": "", "name": "Ada", "email": "ada@example.com"},
        {"slot_id": "s1", "name": "   ", "email": "ada@example.com"},
        {"slot_id": "s1", "name": "Ada", "email": "   "},
    ],
)
def test_booking_rejects_missing_or_empty_fields(
    client: TestClient, payload: dict[str, str]
) -> None:
    response = client.post("/bookings", json=payload)

    assert response.status_code == 400
    assert response.json()["error"]


@pytest.mark.parametrize("email", ["not-an-email", "ada@", "@example.com"])
def test_booking_rejects_invalid_email(client: TestClient, email: str) -> None:
    response = client.post(
        "/bookings",
        json={"slot_id": "s1", "name": "Ada Obi", "email": email},
    )

    assert response.status_code == 400
    assert "email" in response.json()["error"]


def test_booking_returns_not_found_for_unknown_slot(client: TestClient) -> None:
    response = client.post(
        "/bookings",
        json={"slot_id": "missing", "name": "Ada Obi", "email": "ada@example.com"},
    )

    assert response.status_code == 404
    assert response.json() == {"error": "slot not found"}


def test_booking_rejects_appointment_that_has_started(client: TestClient) -> None:
    past_slot = {
        "id": "past",
        "provider": "Dr Past",
        "start": "2000-01-01T00:00:00Z",
        "end": "2000-01-01T00:30:00Z",
    }
    client.post("/reset", json={"slots": [past_slot]})

    response = client.post(
        "/bookings",
        json={"slot_id": "past", "name": "Ada Obi", "email": "ada@example.com"},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "appointment has already started"}


def test_booking_rejects_appointment_start_equal_to_current_time(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import main

    monkeypatch.setattr(
        main, "current_utc_time", lambda: datetime(2026, 12, 10, 9, tzinfo=timezone.utc)
    )
    slot = {
        "id": "now",
        "provider": "Dr Ade",
        "start": "2026-12-10T09:00:00Z",
        "end": "2026-12-10T09:30:00Z",
    }
    client.post("/reset", json={"slots": [slot]})

    response = client.post(
        "/bookings",
        json={"slot_id": "now", "name": "Ada Obi", "email": "ada@example.com"},
    )

    assert response.status_code == 400
    assert response.json() == {"error": "appointment has already started"}