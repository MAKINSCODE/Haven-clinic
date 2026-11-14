from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base, get_db
from app.migrate import migrate
from app.main import app, list_bookings
from app.models import Booking, CONFIRMED_BOOKING_INDEX, Slot


@pytest.fixture()
def client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("API_KEY", "test-api-key")
    test_engine = create_engine(
        URL.create("sqlite", database=str(tmp_path / "test.db")),
        connect_args={"check_same_thread": False, "timeout": 15},
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


def appointment_slots(count: int) -> list[dict[str, str]]:
    first_start = datetime(2026, 12, 10, 9, tzinfo=timezone.utc)
    return [
        {
            "id": f"history-{index}",
            "provider": "Dr Ade",
            "start": (first_start + timedelta(days=index)).isoformat(),
            "end": (first_start + timedelta(days=index, minutes=30)).isoformat(),
        }
        for index in range(count)
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
        ("GET", "/bookings?email=ada@example.com", None),
        ("GET", "/bookings/missing", None),
        ("DELETE", "/bookings/missing", None),
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


def test_second_confirmed_booking_for_slot_returns_conflict(client: TestClient) -> None:
    client.post("/reset", json={"slots": sample_slots()})
    first = client.post(
        "/bookings",
        json={"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"},
    )

    second = client.post(
        "/bookings",
        json={"slot_id": "s1", "name": "Bola Obi", "email": "bola@example.com"},
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json() == {"error": "slot already booked"}


def test_idempotent_retry_replays_original_booking(client: TestClient) -> None:
    client.post("/reset", json={"slots": sample_slots()})
    payload = {"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"}

    original = client.post("/bookings", json=payload, headers={"Idempotency-Key": "retry-1"})
    replay = client.post("/bookings", json=payload, headers={"Idempotency-Key": "retry-1"})

    assert original.status_code == replay.status_code == 201
    assert original.json() == replay.json()


def test_idempotency_key_with_different_body_returns_unprocessable(
    client: TestClient,
) -> None:
    client.post("/reset", json={"slots": sample_slots()})
    headers = {"Idempotency-Key": "different-body"}
    first = client.post(
        "/bookings",
        json={"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"},
        headers=headers,
    )

    second = client.post(
        "/bookings",
        json={"slot_id": "s1", "name": "Bola Obi", "email": "bola@example.com"},
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 422
    assert second.json() == {
        "error": "Idempotency-Key was already used with a different request"
    }


def test_idempotent_retry_replays_original_response_after_cancellation(
    client: TestClient,
) -> None:
    client.post("/reset", json={"slots": sample_slots()})
    payload = {"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"}
    headers = {"Idempotency-Key": "cancelled-retry"}
    original = client.post("/bookings", json=payload, headers=headers)
    client.delete(f"/bookings/{original.json()['id']}")

    replay = client.post("/bookings", json=payload, headers=headers)

    assert replay.status_code == 201
    assert replay.json() == original.json()


def test_bookings_without_idempotency_key_still_work(client: TestClient) -> None:
    client.post("/reset", json={"slots": sample_slots()})

    first = client.post(
        "/bookings",
        json={"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"},
    )
    second = client.post(
        "/bookings",
        json={"slot_id": "s2", "name": "Bola Obi", "email": "bola@example.com"},
    )

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_database_index_rejects_duplicate_confirmed_bookings() -> None:
    test_engine = create_engine(
        URL.create("sqlite", database=":memory:"),
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(test_engine)
    test_session = sessionmaker(bind=test_engine, expire_on_commit=False)

    try:
        with test_session.begin() as db:
            db.add(
                Slot(
                    id="indexed",
                    provider="Dr Ade",
                    start_at=datetime(2026, 12, 10, 9, tzinfo=timezone.utc),
                    end_at=datetime(2026, 12, 10, 9, 30, tzinfo=timezone.utc),
                )
            )
        with pytest.raises(IntegrityError):
            with test_session.begin() as db:
                db.add_all(
                    [
                        Booking(slot_id="indexed", name="One", email="one@example.com"),
                        Booking(slot_id="indexed", name="Two", email="two@example.com"),
                    ]
                )
                db.flush()
    finally:
        test_engine.dispose()


def test_migration_adds_confirmed_booking_index_idempotently() -> None:
    test_engine = create_engine(URL.create("sqlite", database=":memory:"))
    Base.metadata.create_all(test_engine)
    CONFIRMED_BOOKING_INDEX.drop(test_engine, checkfirst=True)

    try:
        migrate(test_engine)
        migrate(test_engine)

        indexes = inspect(test_engine).get_indexes("bookings")
        assert any(
            index["name"] == "uq_bookings_one_confirmed_per_slot"
            and index["unique"]
            for index in indexes
        )
    finally:
        test_engine.dispose()


def test_migration_reports_preexisting_duplicate_confirmed_bookings() -> None:
    test_engine = create_engine(URL.create("sqlite", database=":memory:"))
    Base.metadata.create_all(test_engine)
    CONFIRMED_BOOKING_INDEX.drop(test_engine, checkfirst=True)
    test_session = sessionmaker(bind=test_engine, expire_on_commit=False)

    try:
        with test_session.begin() as db:
            db.add(
                Slot(
                    id="duplicate",
                    provider="Dr Ade",
                    start_at=datetime(2026, 12, 10, 9, tzinfo=timezone.utc),
                    end_at=datetime(2026, 12, 10, 9, 30, tzinfo=timezone.utc),
                )
            )
        with test_session.begin() as db:
            db.add_all(
                [
                    Booking(slot_id="duplicate", name="One", email="one@example.com"),
                    Booking(slot_id="duplicate", name="Two", email="two@example.com"),
                ]
            )

        with pytest.raises(RuntimeError, match="multiple confirmed bookings"):
            migrate(test_engine)
    finally:
        test_engine.dispose()


def test_migration_adds_level_four_columns_to_existing_database() -> None:
    test_engine = create_engine(URL.create("sqlite", database=":memory:"))
    with test_engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE slots (id VARCHAR PRIMARY KEY, provider VARCHAR NOT NULL, "
            "start DATETIME NOT NULL, end DATETIME NOT NULL)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE bookings (id VARCHAR PRIMARY KEY, slot_id VARCHAR NOT NULL, "
            "name VARCHAR NOT NULL, email VARCHAR NOT NULL, status VARCHAR NOT NULL, "
            "created_at DATETIME NOT NULL)"
        )

    try:
        migrate(test_engine)
        migrate(test_engine)

        columns = {column["name"] for column in inspect(test_engine).get_columns("bookings")}
        indexes = {index["name"] for index in inspect(test_engine).get_indexes("bookings")}
        assert {
            "idempotency_key",
            "request_fingerprint",
            "idempotency_response",
            "idempotency_status_code",
        } <= columns
        assert "uq_bookings_one_confirmed_per_slot" in indexes
        assert "uq_bookings_idempotency_key" in indexes
    finally:
        test_engine.dispose()


def test_simultaneous_booking_requests_only_confirm_one(client: TestClient) -> None:
    client.post("/reset", json={"slots": sample_slots()})
    barrier = Barrier(2)

    def book(name: str, email: str):
        barrier.wait()
        return client.post(
            "/bookings",
            json={"slot_id": "s1", "name": name, "email": email},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        requests = [
            executor.submit(book, "Ada Obi", "ada@example.com"),
            executor.submit(book, "Bola Obi", "bola@example.com"),
        ]
        responses = [request.result(timeout=30) for request in requests]

    assert sorted(response.status_code for response in responses) == [201, 409]
    assert sum(response.json().get("status") == "confirmed" for response in responses) == 1
    assert next(slot for slot in client.get("/slots").json() if slot["id"] == "s1")[
        "available"
    ] is False


def test_simultaneous_requests_with_same_idempotency_key_replay_one_booking(
    client: TestClient,
) -> None:
    client.post("/reset", json={"slots": sample_slots()})
    barrier = Barrier(2)
    payload = {"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"}

    def book():
        barrier.wait()
        return client.post(
            "/bookings",
            json=payload,
            headers={"Idempotency-Key": "simultaneous-retry"},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        requests = [executor.submit(book) for _ in range(2)]
        responses = [request.result(timeout=30) for request in requests]

    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json() == responses[1].json()


def test_booking_history_filters_email_case_insensitively_and_orders_oldest_first(
    client: TestClient,
) -> None:
    slots = appointment_slots(4)
    client.post("/reset", json={"slots": slots})
    created = []
    for index, email in enumerate(
        ["ADA@example.com", "other@example.com", "ada@example.com", "ada@example.com"]
    ):
        response = client.post(
            "/bookings",
            json={
                "slot_id": slots[index]["id"],
                "name": f"Patient {index}",
                "email": email,
            },
        )
        created.append(response.json())

    history = client.get("/bookings", params={"email": "ADA@EXAMPLE.COM"}).json()

    assert [booking["id"] for booking in history["bookings"]] == [
        created[0]["id"],
        created[2]["id"],
        created[3]["id"],
    ]
    assert history["next_cursor"] is None


def test_booking_history_default_limit_and_cursor_pagination(client: TestClient) -> None:
    slots = appointment_slots(12)
    client.post("/reset", json={"slots": slots})
    created_ids = []
    for index, slot in enumerate(slots):
        created = client.post(
            "/bookings",
            json={
                "slot_id": slot["id"],
                "name": f"Patient {index}",
                "email": "history@example.com",
            },
        )
        created_ids.append(created.json()["id"])

    first_page = client.get("/bookings", params={"email": "history@example.com"}).json()
    assert len(first_page["bookings"]) == 10
    assert first_page["next_cursor"] is not None

    second_page = client.get(
        "/bookings",
        params={
            "email": "history@example.com",
            "cursor": first_page["next_cursor"],
        },
    ).json()

    assert len(second_page["bookings"]) == 2
    assert second_page["next_cursor"] is None
    assert [
        booking["id"] for booking in first_page["bookings"] + second_page["bookings"]
    ] == created_ids


def test_booking_history_cursor_uses_id_to_break_timestamp_ties() -> None:
    test_engine = create_engine(URL.create("sqlite", database=":memory:"))
    Base.metadata.create_all(test_engine)
    test_session = sessionmaker(bind=test_engine, expire_on_commit=False)
    timestamp = datetime(2026, 12, 1, 10, tzinfo=timezone.utc)

    try:
        with test_session.begin() as db:
            for suffix in ("a", "b", "c"):
                db.add(
                    Slot(
                        id=f"tie-{suffix}",
                        provider="Dr Ade",
                        start_at=datetime(2026, 12, 10, 9, tzinfo=timezone.utc),
                        end_at=datetime(2026, 12, 10, 9, 30, tzinfo=timezone.utc),
                    )
                )
                db.add(
                    Booking(
                        id=f"booking-{suffix}",
                        slot_id=f"tie-{suffix}",
                        name=f"Patient {suffix}",
                        email="ties@example.com",
                        created_at=timestamp,
                    )
                )

        with test_session() as db:
            first = list_bookings("ties@example.com", 2, None, db)
            second = list_bookings(
                "ties@example.com", 2, first.next_cursor, db
            )

        assert [booking.id for booking in first.bookings] == [
            "booking-a",
            "booking-b",
        ]
        assert [booking.id for booking in second.bookings] == ["booking-c"]
        assert second.next_cursor is None
    finally:
        test_engine.dispose()


def test_booking_history_supports_custom_limit_and_rejects_invalid_limits(
    client: TestClient,
) -> None:
    slots = appointment_slots(4)
    client.post("/reset", json={"slots": slots})
    for index, slot in enumerate(slots):
        client.post(
            "/bookings",
            json={
                "slot_id": slot["id"],
                "name": f"Patient {index}",
                "email": "history@example.com",
            },
        )

    page = client.get(
        "/bookings",
        params={"email": "history@example.com", "limit": 2},
    ).json()
    assert len(page["bookings"]) == 2
    assert page["next_cursor"] is not None

    for invalid_limit in ["0", "51", "not-a-number"]:
        response = client.get(
            "/bookings",
            params={"email": "history@example.com", "limit": invalid_limit},
        )
        assert response.status_code == 400
        assert response.json()["error"]


def test_booking_history_requires_email_and_rejects_invalid_cursor(
    client: TestClient,
) -> None:
    missing_email = client.get("/bookings")
    invalid_cursor = client.get(
        "/bookings",
        params={"email": "history@example.com", "cursor": "not-a-cursor"},
    )

    assert missing_email.status_code == 400
    assert missing_email.json() == {"error": "email is required"}
    assert invalid_cursor.status_code == 400
    assert invalid_cursor.json() == {"error": "invalid booking cursor"}


def test_cancel_booking_frees_slot_for_rebooking(client: TestClient) -> None:
    client.post("/reset", json={"slots": sample_slots()})
    created = client.post(
        "/bookings",
        json={"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"},
    )
    booking_id = created.json()["id"]

    cancelled = client.delete(f"/bookings/{booking_id}")

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert next(slot for slot in client.get("/slots").json() if slot["id"] == "s1")[
        "available"
    ] is True
    rebooked = client.post(
        "/bookings",
        json={"slot_id": "s1", "name": "Bola Obi", "email": "bola@example.com"},
    )
    assert rebooked.status_code == 201


def test_cancel_booking_returns_not_found_for_unknown_id(client: TestClient) -> None:
    response = client.delete("/bookings/unknown")

    assert response.status_code == 404
    assert response.json() == {"error": "booking not found"}


def test_cancel_booking_returns_conflict_if_already_cancelled(client: TestClient) -> None:
    client.post("/reset", json={"slots": sample_slots()})
    created = client.post(
        "/bookings",
        json={"slot_id": "s1", "name": "Ada Obi", "email": "ada@example.com"},
    )
    booking_id = created.json()["id"]
    assert client.delete(f"/bookings/{booking_id}").status_code == 200

    response = client.delete(f"/bookings/{booking_id}")

    assert response.status_code == 409
    assert response.json() == {"error": "booking already cancelled"}


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