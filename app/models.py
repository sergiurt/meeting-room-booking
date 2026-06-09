"""SQLAlchemy ORM models for the meeting-room booking schema."""
import datetime

from sqlalchemy import (
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Interval,
    SmallInteger,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Room(Base):
    __tablename__ = "rooms"

    room_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    capacity: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    reservations: Mapped[list["Reservation"]] = relationship(
        back_populates="room",
        passive_deletes="all",
    )


class Reservation(Base):
    __tablename__ = "reservations"

    reservation_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.room_id", ondelete="RESTRICT"), nullable=False
    )
    responsible: Mapped[str] = mapped_column(String(150), nullable=False)
    res_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    start_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[datetime.time] = mapped_column(Time, nullable=False)
    # Generated/stored column: end_time - start_time (read-only, computed by PG).
    duration: Mapped[datetime.timedelta | None] = mapped_column(
        Interval, Computed("end_time - start_time", persisted=True)
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    room: Mapped["Room"] = relationship(back_populates="reservations")

    # The no_room_overlap GiST EXCLUDE constraint is enforced at the database
    # level (see alembic/versions/001_initial_schema.py); it relies on the
    # custom `timerange` type and is not declared in the ORM mapping.
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="chk_time_order"),
        Index("idx_res_room", "room_id"),
        Index("idx_res_date", "res_date"),
        Index("idx_res_room_date", "room_id", "res_date"),
    )
