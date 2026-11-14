from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, text
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


# Only confirmed bookings occupy a slot; cancelled rows remain in booking history.
CONFIRMED_BOOKING_INDEX = Index(
    "uq_bookings_one_confirmed_per_slot",
    Booking.slot_id,
    unique=True,
    postgresql_where=text("status = 'confirmed'"),
    sqlite_where=text("status = 'confirmed'"),
)