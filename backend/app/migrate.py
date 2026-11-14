from sqlalchemy import Engine, func, select

from app.db import engine
from app.models import Booking, CONFIRMED_BOOKING_INDEX


def migrate(bind: Engine = engine) -> None:
    with bind.begin() as connection:
        duplicate_slots = connection.execute(
            select(Booking.slot_id)
            .where(Booking.status == "confirmed")
            .group_by(Booking.slot_id)
            .having(func.count() > 1)
        ).scalars().all()
        if duplicate_slots:
            slots = ", ".join(sorted(duplicate_slots))
            raise RuntimeError(
                "Cannot add the confirmed-booking uniqueness index; "
                f"multiple confirmed bookings exist for slots: {slots}"
            )

        CONFIRMED_BOOKING_INDEX.create(connection, checkfirst=True)


if __name__ == "__main__":
    migrate()
