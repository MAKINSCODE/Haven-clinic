from datetime import datetime, timezone

from pydantic import BaseModel, EmailStr, ValidationInfo, field_validator

from app.models import Slot


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class SlotInput(BaseModel):
    id: str
    provider: str
    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return as_utc(value)


class ResetRequest(BaseModel):
    slots: list[SlotInput]


class SlotResponse(BaseModel):
    id: str
    provider: str
    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        return as_utc(value)


class SlotAvailability(SlotResponse):
    available: bool


class NewBooking(BaseModel):
    slot_id: str
    name: str
    email: EmailStr

    @field_validator("slot_id", "name", "email", mode="before")
    @classmethod
    def normalize_required_values(cls, value: object, info: ValidationInfo) -> object:
        if not isinstance(value, str):
            return value

        trimmed_value = value.strip()
        if not trimmed_value:
            raise ValueError(f"{info.field_name} must not be empty")
        if info.field_name == "slot_id":
            return value
        # Normalize patient-entered text before validating and storing it.
        if info.field_name == "email":
            return trimmed_value.lower()
        return trimmed_value


class BookingResponse(BaseModel):
    id: str
    slot_id: str
    name: str
    email: str
    status: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        return as_utc(value)


class BookingHistoryResponse(BaseModel):
    bookings: list[BookingResponse]
    next_cursor: str | None


class ErrorResponse(BaseModel):
    error: str


def slot_response(slot: Slot, available: bool) -> SlotAvailability:
    return SlotAvailability(
        id=slot.id,
        provider=slot.provider,
        start=slot.start_at,
        end=slot.end_at,
        available=available,
    )