"""All database operations for the meeting-room booking app.

Routers must call these functions rather than issuing inline queries.
"""
import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Reservation, Room, User
from app.schemas import ReservationCreate


class OverlapError(Exception):
    """Raised when a reservation overlaps an existing booking for the room/date."""


async def get_rooms(session: AsyncSession) -> list[Room]:
    """Return all rooms, ordered by name."""
    result = await session.execute(select(Room).order_by(Room.name))
    return list(result.scalars().all())


async def get_room(session: AsyncSession, room_id: int) -> Room | None:
    """Return a single room by id, or None."""
    return await session.get(Room, room_id)


async def create_reservation(
    session: AsyncSession, data: ReservationCreate
) -> Reservation:
    """Insert a reservation.

    Translates the DB-level no_room_overlap exclusion violation into a clean
    OverlapError for the caller to surface to the user.
    """
    reservation = Reservation(
        room_id=data.room_id,
        responsible=data.responsible,
        res_date=data.res_date,
        start_time=data.start_time,
        end_time=data.end_time,
        notes=data.notes,
    )
    session.add(reservation)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        # asyncpg raises ExclusionViolationError, wrapped by SQLAlchemy as
        # IntegrityError; the constraint name appears in the original error.
        if "no_room_overlap" in str(exc.orig):
            raise OverlapError(
                "This room is already booked for an overlapping time on that date."
            ) from exc
        if "chk_time_order" in str(exc.orig):
            raise OverlapError("End time must be after start time.") from exc
        raise

    await session.refresh(reservation)
    return reservation


async def delete_reservation(session: AsyncSession, reservation_id: int) -> bool:
    """Delete a reservation by id. Returns True if a row was removed."""
    reservation = await session.get(Reservation, reservation_id)
    if reservation is None:
        return False
    await session.delete(reservation)
    await session.commit()
    return True


async def get_reservations(
    session: AsyncSession,
    *,
    room_id: int | None = None,
    year: int | None = None,
    month: int | None = None,
) -> list[Reservation]:
    """Return reservations, optionally filtered by room and/or by month.

    - No filters -> all reservations across all rooms.
    - room_id only -> all reservations for that room.
    - year + month -> all reservations in that calendar month.
    - both -> that room within that month.

    Sorted by date then start_time ascending. The related room is eager-loaded
    so the room name is available without lazy loading.
    """
    stmt = select(Reservation).options(selectinload(Reservation.room))

    if room_id is not None:
        stmt = stmt.where(Reservation.room_id == room_id)

    if year is not None and month is not None:
        start = datetime.date(year, month, 1)
        end = (
            datetime.date(year + 1, 1, 1)
            if month == 12
            else datetime.date(year, month + 1, 1)
        )
        stmt = stmt.where(
            Reservation.res_date >= start,
            Reservation.res_date < end,
        )

    stmt = stmt.order_by(Reservation.res_date, Reservation.start_time)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_user_by_username(
    session: AsyncSession, username: str
) -> User | None:
    result = await session.execute(
        select(User).where(User.username == username)
    )
    return result.scalar_one_or_none()


async def create_user(
    session: AsyncSession, username: str, password_hash: str, role: str
) -> User:
    user = User(username=username, password_hash=password_hash, role=role)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def list_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.username))
    return list(result.scalars().all())


async def delete_user(session: AsyncSession, user_id: int) -> bool:
    user = await session.get(User, user_id)
    if user is None:
        return False
    await session.delete(user)
    await session.commit()
    return True


async def get_reservations_for_room_week(
    session: AsyncSession, room_id: int, week_start: datetime.date
) -> list[Reservation]:
    """Return one room's reservations for the 7 days starting at week_start."""
    week_end = week_start + datetime.timedelta(days=7)
    stmt = (
        select(Reservation)
        .where(
            Reservation.room_id == room_id,
            Reservation.res_date >= week_start,
            Reservation.res_date < week_end,
        )
        .order_by(Reservation.res_date, Reservation.start_time)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
