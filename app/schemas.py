"""Pydantic v2 schemas for input validation."""
from datetime import date, time

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReservationCreate(BaseModel):
    """Validated payload for creating a reservation."""

    room_id: int = Field(..., gt=0)
    responsible: str = Field(..., min_length=1, max_length=150)
    res_date: date
    start_time: time
    end_time: time
    notes: str | None = Field(default=None)

    @model_validator(mode="after")
    def check_time_order(self) -> "ReservationCreate":
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time.")
        return self


class RoomOut(BaseModel):
    """Read schema for a room."""

    model_config = ConfigDict(from_attributes=True)

    room_id: int
    name: str
    capacity: int | None = None
