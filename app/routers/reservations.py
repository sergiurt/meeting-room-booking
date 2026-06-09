"""Mutation routes: create and delete reservations (HTMX-aware)."""
import html

from fastapi import APIRouter, Depends, Form, Response
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.database import get_session
from app.schemas import ReservationCreate

router = APIRouter(prefix="/reservations", tags=["reservations"])


def _error_html(message: str) -> str:
    """Render an inline error fragment for HTMX to swap into the form."""
    return f'<div class="error" role="alert">{html.escape(message)}</div>'


@router.post("", response_class=HTMLResponse)
async def create_reservation(
    room_id: int = Form(...),
    responsible: str = Form(...),
    res_date: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    notes: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Validate and insert a reservation.

    On validation or overlap error: return an inline HTML error fragment (HTMX
    swaps it in, no page reload). On success: trigger an HTMX client-side
    redirect to the room's view.
    """
    try:
        data = ReservationCreate(
            room_id=room_id,
            responsible=responsible,
            res_date=res_date,
            start_time=start_time,
            end_time=end_time,
            notes=(notes or None),
        )
    except ValidationError as exc:
        message = "; ".join(err["msg"] for err in exc.errors())
        return HTMLResponse(_error_html(message), status_code=200)

    try:
        await crud.create_reservation(session, data)
    except crud.OverlapError as exc:
        return HTMLResponse(_error_html(str(exc)), status_code=200)

    response = Response(status_code=204)
    response.headers["HX-Redirect"] = f"/view?room_id={data.room_id}"
    return response


@router.delete("/{reservation_id}", response_class=HTMLResponse)
async def delete_reservation(
    reservation_id: int,
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    """Delete a reservation. Returns an empty body so HTMX removes the row."""
    await crud.delete_reservation(session, reservation_id)
    return HTMLResponse("", status_code=200)
