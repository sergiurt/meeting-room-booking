"""Admin-only user management routes."""
import html

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.auth import hash_password, require_admin
from app.database import get_session
from app.models import User
from app.schemas import UserCreate

router = APIRouter(prefix="/admin", tags=["admin"])

templates = Jinja2Templates(directory="app/templates")


async def _render_users(
    request: Request, session: AsyncSession, current: User, error: str | None = None
) -> HTMLResponse:
    users = await crud.list_users(session)
    return templates.TemplateResponse(
        "admin_users.html",
        {
            "request": request,
            "users": users,
            "current_user": current,
            "error": error,
        },
    )


@router.get("/users", response_class=HTMLResponse)
async def users_page(
    request: Request,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await _render_users(request, session, admin)


@router.post("/users", response_class=HTMLResponse)
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = UserCreate(username=username, password=password, role=role)
    except ValidationError as exc:
        message = "; ".join(e["msg"] for e in exc.errors())
        return await _render_users(request, session, admin, error=message)

    try:
        await crud.create_user(
            session, data.username, hash_password(data.password), data.role
        )
    except IntegrityError:
        await session.rollback()
        return await _render_users(
            request,
            session,
            admin,
            error=f"Username '{html.escape(data.username)}' already exists.",
        )
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    admin: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if user_id == admin.user_id:
        # Never let an admin delete their own account.
        return RedirectResponse(url="/admin/users", status_code=303)
    await crud.delete_user(session, user_id)
    return RedirectResponse(url="/admin/users", status_code=303)
