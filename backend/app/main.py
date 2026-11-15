import base64
import binascii
import hashlib
import hmac
import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, and_, delete, func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth import require_api_key
from app.db import get_db
from app.models import Booking, BookingAttempt, Slot
from app.schemas import (
    BookingHistoryResponse,
    BookingResponse,
    ErrorResponse,
    NewBooking,
    ResetRequest,
    SlotAvailability,
    SlotListResponse,
    slot_response,
)

logger = logging.getLogger(__name__)
BOOKING_ATTEMPT_LIMIT = 5
BOOKING_ATTEMPT_WINDOW = timedelta(minutes=1)
app = FastAPI(
    title="Clinic Appointment Booking API",
    dependencies=[Depends(require_api_key)],
)


@app.exception_handler(HTTPException)
async def http_error_response(request: Request, exc: HTTPException) -> JSONResponse:
    logger.debug("Returning HTTP %s for %s", exc.status_code, request.url.path)
    message = exc.detail if isinstance(exc.detail, str) else "request failed"
    return JSONResponse(status_code=exc.status_code, content={"error": message}, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def request_validation_error_response(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    is_booking_request = request.method == "POST" and request.url.path == "/bookings"
    is_history_request = request.method == "GET" and request.url.path == "/bookings"
    if is_booking_request:
        messages = []
        for error in exc.errors():
            field = error["loc"][-1] if error["loc"] else None
            if error["type"] == "missing" and isinstance(field, str):
                messages.append(f"{field} is required")
            elif field == "email":
                messages.append("email must be a valid email address")
            elif isinstance(field, str):
                context_error = error.get("ctx", {}).get("error")
                if context_error is not None:
                    messages.append(str(context_error))
                else:
                    messages.append(f"{field} is invalid")
        message = "; ".join(dict.fromkeys(messages)) or "invalid booking input"
        return JSONResponse(status_code=400, content={"error": message})

    if is_history_request:
        messages = []
        for error in exc.errors():
            field = error["loc"][-1] if error["loc"] else None
            if field == "email" and error["type"] == "missing":
                messages.append("email is required")
            elif field == "limit":
                messages.append("limit must be between 1 and 50")
            elif isinstance(field, str):
                messages.append(f"{field} is invalid")
        message = "; ".join(dict.fromkeys(messages)) or "invalid booking history request"
        return JSONResponse(status_code=400, content={"error": message})

    return JSONResponse(status_code=422, content={"error": "invalid request"})


@app.exception_handler(Exception)
async def unexpected_error_response(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled API error for %s",
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(status_code=500, content={"error": "internal server error"})


def current_utc_time() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    # SQLite drops timezone metadata from DateTime columns; persisted values are UTC.
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def record_booking_attempt(bind: Engine, email: str) -> int | None:
    api_key = os.getenv("API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="API key is not configured")
    email_hash = hmac.new(
        api_key.encode("utf-8"),
        email.strip().lower().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    retry_after: int | None = None
    lock_id = int.from_bytes(bytes.fromhex(email_hash[:16]), "big", signed=True)

    with Session(bind=bind) as db:
        with db.begin():
            dialect_name = bind.dialect.name
            if dialect_name == "sqlite":
                # SQLite has no row-level locks; a write serializes rate-limit checks.
                db.execute(
                    update(BookingAttempt)
                    .where(BookingAttempt.id == "__rate_limit_write_lock__")
                    .values(attempted_at=BookingAttempt.attempted_at)
                )
            elif dialect_name == "postgresql":
                db.execute(
                    text("SELECT pg_advisory_xact_lock(CAST(:lock_id AS BIGINT))"),
                    {"lock_id": lock_id},
                )
            else:
                raise RuntimeError(
                    f"Unsupported database dialect for rate limiting: {dialect_name}"
                )

            now = current_utc_time()
            cutoff = now - BOOKING_ATTEMPT_WINDOW
            attempts = db.scalars(
                select(BookingAttempt.attempted_at)
                .where(
                    BookingAttempt.email_hash == email_hash,
                    BookingAttempt.attempted_at >= cutoff,
                )
                .order_by(BookingAttempt.attempted_at)
            ).all()

            if len(attempts) >= BOOKING_ATTEMPT_LIMIT:
                oldest_attempt = as_utc(attempts[0])
                retry_after = max(
                    1,
                    math.ceil(
                        (
                            oldest_attempt
                            + BOOKING_ATTEMPT_WINDOW
                            - now
                        ).total_seconds()
                    ),
                )
            else:
                db.add(BookingAttempt(email_hash=email_hash, attempted_at=now))
                db.flush()

        with db.begin():
            db.execute(
                delete(BookingAttempt).where(BookingAttempt.attempted_at < cutoff)
            )

    return retry_after


async def enforce_booking_attempt_limit(
    request: Request,
    _api_key: None = Depends(require_api_key),
    db: Session = Depends(get_db),
) -> None:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return

    if not isinstance(payload, dict) or not isinstance(payload.get("email"), str):
        return

    email = payload["email"].strip()
    if not email:
        return

    retry_after = await run_in_threadpool(record_booking_attempt, db.get_bind(), email)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="too many booking attempts",
            headers={"Retry-After": str(retry_after)},
        )


def lock_slot(db: Session, slot_id: str) -> Slot | None:
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        # SQLite ignores FOR UPDATE, so take its write lock before reading the slot.
        db.execute(update(Slot).where(Slot.id == slot_id).values(id=Slot.id))
    return db.scalar(select(Slot).where(Slot.id == slot_id).with_for_update())


def lock_booking(db: Session, booking_id: str) -> Booking | None:
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        # Serialize cancellation requests because SQLite does not implement FOR UPDATE.
        db.execute(
            update(Booking)
            .where(Booking.id == booking_id)
            .values(status=Booking.status)
        )
    return db.scalar(
        select(Booking).where(Booking.id == booking_id).with_for_update()
    )


def request_fingerprint(booking: NewBooking) -> str:
    # Hash validated, normalized fields so equivalent retries have the same fingerprint.
    canonical_body = json.dumps(
        booking.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_body.encode("utf-8")).hexdigest()


def booking_response(booking: Booking) -> BookingResponse:
    return BookingResponse(
        id=booking.id,
        slot_id=booking.slot_id,
        name=booking.name,
        email=booking.email,
        status=booking.status,
        created_at=booking.created_at,
    )


def replay_idempotent_booking(
    existing: Booking,
    fingerprint: str,
    response: Response,
) -> BookingResponse:
    if existing.request_fingerprint != fingerprint:
        raise HTTPException(
            status_code=422,
            detail="Idempotency-Key was already used with a different request",
        )
    if existing.idempotency_response is None or existing.idempotency_status_code is None:
        raise HTTPException(status_code=500, detail="stored idempotent response is incomplete")

    # Replay the stored snapshot; a later cancellation must not alter the original response.
    response.status_code = existing.idempotency_status_code
    return BookingResponse.model_validate(existing.idempotency_response)


def encode_cursor(booking: Booking) -> str:
    # Include both ordering fields so bookings sharing a timestamp paginate deterministically.
    payload = {
        "created_at": as_utc(booking.created_at).isoformat(),
        "id": booking.id,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return encoded.decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("cursor must contain an object")
        created_at = payload["created_at"]
        booking_id = payload["id"]
        if not isinstance(created_at, str) or not isinstance(booking_id, str):
            raise ValueError("cursor fields must be strings")
        return as_utc(datetime.fromisoformat(created_at)), booking_id
    except (binascii.Error, KeyError, TypeError, UnicodeDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="invalid booking cursor")


@app.post("/reset", status_code=200, response_class=Response)
def reset(request: ResetRequest, db: Session = Depends(get_db)) -> Response:
    # Keep deleting bookings and replacing slots atomic if inserting new slots fails.
    with db.begin():
        db.execute(delete(Booking))
        db.execute(delete(Slot))
        db.add_all(
            [
                Slot(
                    id=slot.id,
                    provider=slot.provider,
                    start_at=slot.start,
                    end_at=slot.end,
                )
                for slot in request.slots
            ]
        )
    return Response(status_code=200)


@app.get("/slots", response_model=SlotListResponse)
def list_slots(
    provider: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> SlotListResponse:
    query = select(Slot).order_by(Slot.start_at, Slot.id)
    if provider is not None:
        query = query.where(Slot.provider == provider)
    slots = db.scalars(query).all()

    if not slots:
        return SlotListResponse(slots=[])

    confirmed_slot_ids = set(
        db.scalars(
            select(Booking.slot_id).where(
                Booking.status == "confirmed",
                Booking.slot_id.in_([slot.id for slot in slots]),
            )
        ).all()
    )
    return SlotListResponse(
        slots=[
            slot_response(slot, available=slot.id not in confirmed_slot_ids)
            for slot in slots
        ]
    )


@app.post(
    "/bookings",
    response_model=BookingResponse,
    status_code=201,
    responses={
        429: {
            "model": ErrorResponse,
            "description": "More than five booking attempts were made for this email in one minute.",
            "headers": {
                "Retry-After": {
                    "description": "Seconds until another booking attempt is allowed.",
                    "schema": {"type": "integer"},
                }
            },
        }
    },
)
def create_booking(
    booking: NewBooking,
    response: Response,
    _rate_limit: None = Depends(enforce_booking_attempt_limit),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    db: Session = Depends(get_db),
) -> BookingResponse:
    fingerprint = request_fingerprint(booking)
    replay: BookingResponse | None = None
    record: Booking | None = None
    slot: Slot | None = None

    try:
        with db.begin():
            is_sqlite = db.bind is not None and db.bind.dialect.name == "sqlite"
            if idempotency_key is not None and not is_sqlite:
                existing = db.scalar(
                    select(Booking).where(Booking.idempotency_key == idempotency_key)
                )
                if existing is not None:
                    replay = replay_idempotent_booking(existing, fingerprint, response)

            if replay is None:
                # On SQLite, lock before any read so concurrent retries do not race to
                # upgrade simultaneous read transactions into write transactions.
                slot = lock_slot(db, booking.slot_id)
                if idempotency_key is not None:
                    existing = db.scalar(
                        select(Booking).where(Booking.idempotency_key == idempotency_key)
                    )
                    if existing is not None:
                        replay = replay_idempotent_booking(existing, fingerprint, response)

            if replay is None:
                if slot is None:
                    raise HTTPException(status_code=404, detail="slot not found")
                if as_utc(slot.start_at) <= current_utc_time():
                    raise HTTPException(
                        status_code=400, detail="appointment has already started"
                    )

                existing_booking = db.scalar(
                    select(Booking.id)
                    .where(
                        Booking.slot_id == booking.slot_id,
                        Booking.status == "confirmed",
                    )
                    .limit(1)
                )
                if existing_booking is not None:
                    raise HTTPException(status_code=409, detail="slot already booked")

                record = Booking(
                    slot_id=booking.slot_id,
                    name=booking.name,
                    email=booking.email,
                    status="confirmed",
                    idempotency_key=idempotency_key,
                    request_fingerprint=(
                        fingerprint if idempotency_key is not None else None
                    ),
                )
                db.add(record)
                db.flush()
                if idempotency_key is not None:
                    record.idempotency_response = booking_response(record).model_dump(
                        mode="json"
                    )
                    record.idempotency_status_code = 201
                    db.flush()
    except IntegrityError:
        # Unique indexes arbitrate requests that race before either can observe the other.
        db.rollback()
        if idempotency_key is not None:
            existing = db.scalar(
                select(Booking).where(Booking.idempotency_key == idempotency_key)
            )
            if existing is not None:
                return replay_idempotent_booking(existing, fingerprint, response)

        conflicting_booking = db.scalar(
            select(Booking.id).where(
                Booking.slot_id == booking.slot_id,
                Booking.status == "confirmed",
            )
        )
        if conflicting_booking is not None:
            raise HTTPException(status_code=409, detail="slot already booked")
        raise

    if replay is not None:
        return replay
    if record is None:
        raise RuntimeError("booking transaction completed without a booking or replay")

    db.refresh(record)
    return booking_response(record)


@app.delete(
    "/bookings/{booking_id}",
    response_model=BookingResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
def cancel_booking(booking_id: str, db: Session = Depends(get_db)) -> Booking:
    with db.begin():
        booking = lock_booking(db, booking_id)
        if booking is None:
            raise HTTPException(status_code=404, detail="booking not found")
        if booking.status == "cancelled":
            raise HTTPException(status_code=409, detail="booking already cancelled")
        booking.status = "cancelled"
        db.flush()
    return booking


@app.get("/bookings", response_model=BookingHistoryResponse)
def list_bookings(
    email: str = Query(...),
    limit: int = Query(default=10, ge=1, le=50),
    cursor: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> BookingHistoryResponse:
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=400, detail="email must not be empty")

    query = (
        select(Booking)
        .where(func.lower(Booking.email) == normalized_email)
        .order_by(Booking.created_at, Booking.id)
    )
    if cursor is not None:
        cursor_created_at, cursor_id = decode_cursor(cursor)
        query = query.where(
            or_(
                Booking.created_at > cursor_created_at,
                and_(
                    Booking.created_at == cursor_created_at,
                    Booking.id > cursor_id,
                ),
            )
        )

    results = db.scalars(query.limit(limit + 1)).all()
    has_more = len(results) > limit
    page = results[:limit]
    next_cursor = encode_cursor(page[-1]) if has_more else None
    return BookingHistoryResponse(
        bookings=[booking_response(booking) for booking in page],
        next_cursor=next_cursor,
    )


@app.get(
    "/bookings/{booking_id}",
    response_model=BookingResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_booking(booking_id: str, db: Session = Depends(get_db)) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="booking not found")
    return booking