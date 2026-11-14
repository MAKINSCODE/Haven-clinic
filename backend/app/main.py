from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

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

app = FastAPI(title="Clinic Appointment Booking API")


@app.exception_handler(HTTPException)
async def http_error_response(_request: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "request failed"
    return JSONResponse(status_code=exc.status_code, content={"error": message}, headers=exc.headers)


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