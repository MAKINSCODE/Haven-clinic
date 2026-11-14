import logging
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import require_api_key
from app.db import get_db
from app.models import Booking, Slot
from app.schemas import (
    BookingResponse,
    ErrorResponse,
    NewBooking,
    ResetRequest,
    SlotAvailability,
    slot_response,
)

logger = logging.getLogger(__name__)
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


@app.get("/slots", response_model=list[SlotAvailability])
def list_slots(
    provider: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[SlotAvailability]:
    query = select(Slot).order_by(Slot.start_at, Slot.id)
    if provider is not None:
        query = query.where(Slot.provider == provider)
    slots = db.scalars(query).all()

    if not slots:
        return []

    confirmed_slot_ids = set(
        db.scalars(
            select(Booking.slot_id).where(
                Booking.status == "confirmed",
                Booking.slot_id.in_([slot.id for slot in slots]),
            )
        ).all()
    )
    return [
        slot_response(slot, available=slot.id not in confirmed_slot_ids)
        for slot in slots
    ]


@app.post("/bookings", response_model=BookingResponse, status_code=201)
def create_booking(booking: NewBooking, db: Session = Depends(get_db)) -> Booking:
    slot = db.get(Slot, booking.slot_id)
    if slot is None:
        raise HTTPException(status_code=404, detail="slot not found")
    if as_utc(slot.start_at) <= current_utc_time():
        raise HTTPException(status_code=400, detail="appointment has already started")

    record = Booking(
        slot_id=booking.slot_id,
        name=booking.name,
        email=booking.email,
        status="confirmed",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


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