"""GET view routes: landing page, new-reservation form, by-room, by-month.

HTMX requests (identified by the HX-Request header) receive only the table
fragment; normal requests receive the full page.
"""
import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.auth import get_current_user, require_admin, require_user
from app.calendar_utils import DAY_NAMES, build_week_grid, generate_slots, week_dates
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


@router.get("/")
async def index(user: User | None = Depends(get_current_user)):
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    return RedirectResponse(url="/calendar", status_code=303)


@router.get("/reservations/new", response_class=HTMLResponse)
async def new_reservation_form(
    request: Request,
    room_id: str | None = None,
    res_date: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    rooms = await crud.get_rooms(session)
    prefill_room_id = int(room_id) if room_id and room_id.isdigit() else None
    return templates.TemplateResponse(
        "new_reservation.html",
        {
            "request": request,
            "current_user": admin,
            "rooms": rooms,
            "prefill_room_id": prefill_room_id,
            "prefill_date": res_date or "",
            "prefill_start": start_time or "",
            "prefill_end": end_time or "",
        },
    )


async def _render_calendar(
    request: Request,
    session: AsyncSession,
    user: User,
    room_id: str | None,
    week: str | None,
) -> HTMLResponse:
    """Build the calendar context and render it (full page or HTMX partial)."""
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


@router.get("/calendar", response_class=HTMLResponse)
async def calendar(
    request: Request,
    room_id: str | None = None,
    week: str | None = None,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    return await _render_calendar(request, session, user, room_id, week)


@router.get("/calendar/reservation/{reservation_id}", response_class=HTMLResponse)
async def reservation_card(
    request: Request,
    reservation_id: int,
    room_id: str | None = None,
    week: str | None = None,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Admin-only detail card for one reservation (HTMX fragment)."""
    reservation = await crud.get_reservation(session, reservation_id)
    if reservation is None:
        return HTMLResponse("", status_code=200)
    return templates.TemplateResponse(
        "reservation_card.html",
        {
            "request": request,
            "res": reservation,
            "room_id": room_id or "",
            "week": week or "",
        },
    )


@router.get("/calendar/card/close", response_class=HTMLResponse)
async def close_reservation_card(
    admin: User = Depends(require_admin),
) -> HTMLResponse:
    """Clear the detail card (admin-only HTMX fragment)."""
    return HTMLResponse("", status_code=200)


@router.post("/calendar/reservation/{reservation_id}/delete", response_class=HTMLResponse)
async def delete_reservation_from_calendar(
    request: Request,
    reservation_id: int,
    room_id: str | None = None,
    week: str | None = None,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Admin-only: delete a reservation and return the refreshed calendar."""
    await crud.delete_reservation(session, reservation_id)
    return await _render_calendar(request, session, admin, room_id, week)
