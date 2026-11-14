from sqlalchemy import Engine, func, inspect, select, text

from app.db import engine
from app.models import (
    Booking,
    CONFIRMED_BOOKING_INDEX,
    IDEMPOTENCY_KEY_INDEX,
)


def migrate(bind: Engine = engine) -> None:
    """Apply the booking indexes and nullable idempotency columns in place."""
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

        existing_columns = {
            column["name"] for column in inspect(connection).get_columns("bookings")
        }
        new_columns = (
            ("idempotency_key", "VARCHAR"),
            ("request_fingerprint", "VARCHAR"),
            ("idempotency_response", "JSON"),
            ("idempotency_status_code", "INTEGER"),
        )
        for column_name, column_type in new_columns:
            if column_name not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE bookings ADD COLUMN {column_name} {column_type}")
                )

        duplicate_keys = connection.execute(
            select(Booking.idempotency_key)
            .where(Booking.idempotency_key.is_not(None))
            .group_by(Booking.idempotency_key)
            .having(func.count() > 1)
        ).scalars().all()
        if duplicate_keys:
            keys = ", ".join(sorted(duplicate_keys))
            raise RuntimeError(
                "Cannot add the idempotency-key uniqueness index; "
                f"duplicate keys exist: {keys}"
            )

        CONFIRMED_BOOKING_INDEX.create(connection, checkfirst=True)
        IDEMPOTENCY_KEY_INDEX.create(connection, checkfirst=True)


if __name__ == "__main__":
    migrate()
