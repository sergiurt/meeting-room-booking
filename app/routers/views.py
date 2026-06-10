"""GET view routes: landing page, new-reservation form, by-room, by-month.

HTMX requests (identified by the HX-Request header) receive only the table
fragment; normal requests receive the full page.
"""
import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.auth import get_current_user, require_admin, require_user
from app.calendar_utils import DAY_NAMES, build_week_grid, generate_slots, monday_of, week_dates
from app.database import get_session
from app.models import User

router = APIRouter(tags=["views"])

templates = Jinja2Templates(directory="app/templates")


def _format_duration(value: datetime.timedelta | None) -> str:
    """Render an INTERVAL/timedelta as 'Hh MMm'."""
    if value is None:
        return ""
    total_seconds = int(value.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h {minutes:02d}m"


templates.env.filters["duration"] = _format_duration


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") is not None


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/reservations/new", response_class=HTMLResponse)
async def new_reservation_form(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    rooms = await crud.get_rooms(session)
    return templates.TemplateResponse(
        "new_reservation.html",
        {"request": request, "rooms": rooms},
    )


@router.get("/calendar", response_class=HTMLResponse)
async def calendar(
    request: Request,
    room_id: str | None = None,
    week: str | None = None,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    rooms = await crud.get_rooms(session)

    selected_id: int | None = None
    if room_id and room_id.isdigit():
        selected_id = int(room_id)
    elif rooms:
        selected_id = rooms[0].room_id

    try:
        base_day = datetime.date.fromisoformat(week) if week else datetime.date.today()
    except ValueError:
        base_day = datetime.date.today()

    dates = week_dates(base_day)
    slots = generate_slots()

    reservations = []
    if selected_id is not None:
        reservations = await crud.get_reservations_for_room_week(
            session, selected_id, dates[0]
        )

    grid = build_week_grid(reservations, dates, slots)

    return templates.TemplateResponse(
        "calendar.html",
        {
            "request": request,
            "current_user": user,
            "is_admin": user.role == "admin",
            "rooms": rooms,
            "selected_id": selected_id,
            "dates": dates,
            "day_names": DAY_NAMES,
            "grid": grid,
            "week_start": dates[0],
            "prev_week": (dates[0] - datetime.timedelta(days=7)).isoformat(),
            "next_week": (dates[0] + datetime.timedelta(days=7)).isoformat(),
            "today": datetime.date.today(),
            "full": not _is_htmx(request),
        },
    )


@router.get("/view", response_class=HTMLResponse)
async def view_reservations(
    request: Request,
    room_id: str | None = None,
    period: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Unified reservations list.

    Shows all reservations by default. Optional filters (combinable):
    - room_id: a room id, or "" / absent for all rooms.
    - period:  a "YYYY-MM" month (from an <input type="month">), or "" for all.

    Query params arrive as strings (the HTMX selects may send empty values),
    so they are parsed defensively here.
    """
    rooms = await crud.get_rooms(session)

    selected_room_id: int | None = None
    if room_id:
        try:
            selected_room_id = int(room_id)
        except ValueError:
            selected_room_id = None

    year: int | None = None
    month: int | None = None
    if period:
        parts = period.split("-")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            year, month = int(parts[0]), int(parts[1])

    reservations = await crud.get_reservations(
        session, room_id=selected_room_id, year=year, month=month
    )

    return templates.TemplateResponse(
        "view_reservations.html",
        {
            "request": request,
            "rooms": rooms,
            "room_id": selected_room_id,
            "period": period or "",
            "reservations": reservations,
            "full": not _is_htmx(request),
        },
    )
