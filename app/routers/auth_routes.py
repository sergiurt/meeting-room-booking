"""Login and logout routes."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.auth import get_current_user, verify_password
from app.database import get_session

router = APIRouter(tags=["auth"])

templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    if request.session.get("user_id") is not None:
        return RedirectResponse(url="/calendar", status_code=303)
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": None}
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    user = await crud.get_user_by_username(session, username)
    if user is None or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password."},
            status_code=401,
        )
    request.session["user_id"] = user.user_id
    return RedirectResponse(url="/calendar", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
