from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Slot(Base):
    __tablename__ = "slots"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    start_at: Mapped[datetime] = mapped_column("start", DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column("end", DateTime(timezone=True), nullable=False)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    slot_id: Mapped[str] = mapped_column(ForeignKey("slots.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="confirmed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String, nullable=True)
    idempotency_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    idempotency_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)


class BookingAttempt(Base):
    __tablename__ = "booking_attempts"
    __table_args__ = (
        Index("ix_booking_attempts_email_time", "email_hash", "attempted_at"),
        Index("ix_booking_attempts_attempted_at", "attempted_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    email_hash: Mapped[str] = mapped_column(String, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


# Only confirmed bookings occupy a slot; cancelled rows remain in booking history.
CONFIRMED_BOOKING_INDEX = Index(
    "uq_bookings_one_confirmed_per_slot",
    Booking.slot_id,
    unique=True,
    postgresql_where=text("status = 'confirmed'"),
)

IDEMPOTENCY_KEY_INDEX = Index(
    "uq_bookings_idempotency_key",
    Booking.idempotency_key,
    unique=True,
    postgresql_where=text("idempotency_key IS NOT NULL"),
)