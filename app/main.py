"""FastAPI application entrypoint."""
import os

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app.auth import NotAuthenticated, NotAuthorized
from app.routers import admin, auth_routes, reservations, views

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set; add it to your .env file.")

app = FastAPI(title="Meeting Room Booking")

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


@app.exception_handler(NotAuthenticated)
async def _not_authenticated_handler(request: Request, exc: NotAuthenticated):
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(NotAuthorized)
async def _not_authorized_handler(request: Request, exc: NotAuthorized):
    return HTMLResponse(
        "<h2>403 — Forbidden</h2><p>Admin access is required for this action.</p>"
        '<p><a href="/calendar">Back to calendar</a></p>',
        status_code=403,
    )


app.include_router(auth_routes.router)
app.include_router(admin.router)
app.include_router(views.router)
app.include_router(reservations.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", "8000")),
        reload=True,
    )
