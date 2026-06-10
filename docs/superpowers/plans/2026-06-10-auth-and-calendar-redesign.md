# Auth + Calendar Availability Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add username/password login with two roles (admin who creates/deletes bookings, user who only views availability) and replace the list-first UI with a per-room weekly availability calendar.

**Architecture:** A new `users` table (bcrypt password hashes + `role`) is added via Alembic migration `002`, which also seeds one admin from `.env`. Authentication uses Starlette `SessionMiddleware` (signed cookie holding `user_id`); FastAPI dependencies (`require_user`, `require_admin`) gate routes, and two custom exceptions are mapped to a login redirect / 403 by app-level handlers. The booking schema is unchanged, so the existing GiST no-overlap constraint keeps working. The main screen becomes a `/calendar` week grid (Mon–Sun, 30-minute slots, 08:00–20:00) built by a pure, unit-tested function; admins click free cells to pre-fill the booking form, and an `/admin/users` page manages accounts.

**Tech Stack:** Python 3.11, FastAPI, async SQLAlchemy 2 (asyncpg), Alembic, Jinja2 + HTMX, PostgreSQL, `bcrypt`, `itsdangerous` (Starlette sessions); tests with `pytest`, `pytest-asyncio`, `httpx`.

---

## File Map

**New files**
- `app/auth.py` — password hashing, `get_current_user`, `require_user`, `require_admin`, `NotAuthenticated`/`NotAuthorized`.
- `app/calendar_utils.py` — pure slot/week/grid helpers (no DB, no FastAPI).
- `app/routers/auth_routes.py` — `GET/POST /login`, `POST /logout`.
- `app/routers/admin.py` — `GET /admin/users`, `POST /admin/users`, `DELETE /admin/users/{user_id}`.
- `alembic/versions/002_users.py` — `users` table + seeded admin.
- `app/templates/login.html`, `app/templates/calendar.html`, `app/templates/admin_users.html`.
- `tests/conftest.py`, `tests/test_calendar_utils.py`, `tests/test_auth.py`, `tests/test_auth_routes.py`, `tests/test_admin.py`, `tests/test_calendar.py`, `tests/test_reservations_roles.py`.
- `pytest.ini`.

**Modified files**
- `requirements.txt` — add `bcrypt`, `itsdangerous`, `pytest`, `pytest-asyncio`, `httpx`.
- `.env.example` — add `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `TEST_DATABASE_URL`.
- `app/models.py` — add `User` model.
- `app/schemas.py` — add `UserCreate`.
- `app/crud.py` — add user CRUD + `get_reservations_for_room_week`.
- `app/main.py` — `SessionMiddleware`, exception handlers, include new routers.
- `app/routers/views.py` — protect routes, add `/calendar`, prefill `new_reservation`, pass `current_user`, make `/` redirect to `/calendar`.
- `app/routers/reservations.py` — gate create/delete behind `require_admin`.
- `app/templates/base.html` — role-aware nav + logged-in user/logout.
- `app/templates/index.html` — removed/repurposed (root redirects to `/calendar`).
- `app/templates/new_reservation.html` — accept prefill values.
- `app/templates/view_reservations.html` — hide Delete column for non-admins.
- `README.md` — auth setup, admin seeding, calendar usage.

---

## Phase 0 — Dependencies, config, test harness

### Task 1: Add dependencies and environment variables

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`

- [ ] **Step 1: Add runtime + test dependencies to `requirements.txt`**

Append these lines (keep existing pins):

```
bcrypt==4.2.1
itsdangerous==2.2.0
pytest==8.3.4
pytest-asyncio==0.25.0
httpx==0.28.1
```

- [ ] **Step 2: Install them**

Run: `source .venv/bin/activate && pip install -r requirements.txt`
Expected: installs `bcrypt`, `itsdangerous`, `pytest`, `pytest-asyncio`, `httpx` with no errors.

- [ ] **Step 3: Add new variables to `.env.example`**

Replace the file contents with:

```
DATABASE_URL=postgresql+asyncpg://meeting_user:meeting_pass@localhost:5432/meeting_rooms
TEST_DATABASE_URL=postgresql+asyncpg://meeting_user:meeting_pass@localhost:5432/meeting_rooms_test
APP_HOST=0.0.0.0
APP_PORT=8000

# Signed-session secret. Generate with:
#   python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=change-me-to-a-long-random-hex-string

# Seeded by migration 002 (the first/only admin account).
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change-me
```

- [ ] **Step 4: Update local `.env`**

Add `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and `TEST_DATABASE_URL` to your real `.env` (not committed). Generate the secret:

Run: `python -c "import secrets; print(secrets.token_hex(32))"`
Expected: prints a 64-char hex string; paste it as `SECRET_KEY` in `.env`.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .env.example
git commit -m "chore: add auth/test deps and env vars"
```

---

### Task 2: Test harness (pytest + async client + test DB)

**Files:**
- Create: `pytest.ini`
- Create: `tests/conftest.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create the test database**

Run: `export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH" && createdb meeting_rooms_test`
Expected: no output (DB created). If it already exists, that's fine.

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
addopts = -q
```

- [ ] **Step 3: Create `tests/__init__.py`**

```python
```

(empty file)

- [ ] **Step 4: Create `tests/conftest.py`**

```python
"""Pytest fixtures: migrated test database + async HTTP client.

Strategy: run Alembic migrations once per session against TEST_DATABASE_URL
(this creates the schema AND seeds the admin), then clean mutable tables after
each test. The seeded admin persists so login tests can use it.
"""
import os
import subprocess

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Test admin credentials — also passed to Alembic so the seed matches.
TEST_ADMIN_USERNAME = "admin"
TEST_ADMIN_PASSWORD = "admin-test-pw"

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://meeting_user:meeting_pass@localhost:5432/meeting_rooms_test",
)


def _alembic_env() -> dict:
    return {
        **os.environ,
        "DATABASE_URL": TEST_DATABASE_URL,
        "ADMIN_USERNAME": TEST_ADMIN_USERNAME,
        "ADMIN_PASSWORD": TEST_ADMIN_PASSWORD,
        "SECRET_KEY": os.environ.get("SECRET_KEY", "test-secret-key-not-for-prod"),
    }


@pytest.fixture(scope="session", autouse=True)
def _migrated_db():
    env = _alembic_env()
    subprocess.run(["alembic", "upgrade", "head"], check=True, env=env)
    yield
    subprocess.run(["alembic", "downgrade", "base"], check=True, env=env)


@pytest.fixture(scope="session", autouse=True)
def _app_secret():
    # Ensure the app's SessionMiddleware has a key during tests.
    os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-prod")
    yield


@pytest_asyncio.fixture
async def db_engine(_migrated_db):
    engine = create_async_engine(TEST_DATABASE_URL)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_engine):
    # Import inside the fixture so SECRET_KEY is set before app construction.
    from app.database import get_session
    from app.main import app

    test_sessionmaker = async_sessionmaker(bind=db_engine, expire_on_commit=False)

    async def _override_get_session():
        async with test_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

    # Clean mutable rows after each test; keep the seeded admin.
    async with db_engine.begin() as conn:
        await conn.execute(text("DELETE FROM reservations"))
        await conn.execute(
            text("DELETE FROM users WHERE username <> :u"),
            {"u": TEST_ADMIN_USERNAME},
        )


@pytest_asyncio.fixture
async def admin_client(client):
    """An AsyncClient already logged in as the seeded admin."""
    resp = await client.post(
        "/login",
        data={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code in (303, 302)
    return client
```

- [ ] **Step 5: Commit**

```bash
git add pytest.ini tests/__init__.py tests/conftest.py
git commit -m "test: add pytest async harness with migrated test DB"
```

> Note: `tests/conftest.py` references migration `002`, the `User` model, login route, and `SECRET_KEY` wiring built in later tasks. It will not run green until Task 8 is complete; that is expected. Unit tests in Task 4 and Task 11 do not depend on it.

---

## Phase 1 — Users schema

### Task 3: Alembic migration `002` — users table + seeded admin

**Files:**
- Create: `alembic/versions/002_users.py`

- [ ] **Step 1: Write the migration**

```python
"""users table + seeded admin

Revision ID: 002
Revises: 001
Create Date: 2026-06-10

Adds the users table (username, bcrypt password_hash, role) and seeds a single
admin account from the ADMIN_USERNAME / ADMIN_PASSWORD environment variables
(loaded from .env by alembic/env.py).
"""
import os
from typing import Sequence, Union

import bcrypt
from alembic import op
from sqlalchemy import text

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users (
            user_id       SERIAL        PRIMARY KEY,
            username      VARCHAR(150)  NOT NULL UNIQUE,
            password_hash TEXT          NOT NULL,
            role          VARCHAR(20)   NOT NULL,
            created_at    TIMESTAMPTZ   NOT NULL DEFAULT now(),
            CONSTRAINT chk_user_role CHECK (role IN ('admin', 'user'))
        );
        """
    )

    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "change-me")
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    bind = op.get_bind()
    bind.execute(
        text(
            "INSERT INTO users (username, password_hash, role) "
            "VALUES (:u, :p, 'admin') ON CONFLICT (username) DO NOTHING"
        ),
        {"u": username, "p": password_hash},
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS users;")
```

- [ ] **Step 2: Apply the migration to the dev DB**

Run: `source .venv/bin/activate && alembic upgrade head`
Expected: `Running upgrade 001 -> 002, users table + seeded admin`.

- [ ] **Step 3: Verify the admin row exists**

Run: `export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH" && psql -d meeting_rooms -c "SELECT user_id, username, role FROM users;"`
Expected: one row with `username=admin`, `role=admin`.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/002_users.py
git commit -m "feat: add users table and seed admin (migration 002)"
```

---

## Phase 2 — Auth core (TDD)

### Task 4: Password hashing helpers

**Files:**
- Create: `app/auth.py`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth.py
from app.auth import hash_password, verify_password


def test_hash_is_not_plaintext_and_verifies():
    hashed = hash_password("hunter2")
    assert hashed != "hunter2"
    assert verify_password("hunter2", hashed) is True


def test_verify_rejects_wrong_password():
    hashed = hash_password("hunter2")
    assert verify_password("wrong", hashed) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source .venv/bin/activate && pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.auth'` (or ImportError).

- [ ] **Step 3: Create `app/auth.py` with hashing helpers**

```python
"""Authentication helpers: password hashing and current-user dependencies."""
import bcrypt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import User


class NotAuthenticated(Exception):
    """Raised when a protected route is accessed without a valid session."""


class NotAuthorized(Exception):
    """Raised when an authenticated user lacks the required role."""


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:
        return False


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User | None:
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    return await session.get(User, user_id)


async def require_user(
    user: User | None = Depends(get_current_user),
) -> User:
    if user is None:
        raise NotAuthenticated()
    return user


async def require_admin(
    user: User = Depends(require_user),
) -> User:
    if user.role != "admin":
        raise NotAuthorized()
    return user
```

- [ ] **Step 4: Run test to verify it passes**

Run: `source .venv/bin/activate && pytest tests/test_auth.py -v`
Expected: 2 passed. (This imports `app.models.User`, added in Task 5; if `User` does not exist yet, do Task 5 Step 3 first, then return here. Recommended order: do Task 5 Step 3 before running.)

- [ ] **Step 5: Commit**

```bash
git add app/auth.py tests/test_auth.py
git commit -m "feat: add password hashing and auth dependencies"
```

---

### Task 5: `User` model + user CRUD

**Files:**
- Modify: `app/models.py`
- Modify: `app/crud.py`
- Modify: `app/schemas.py`

- [ ] **Step 1: Add the `User` model to `app/models.py`**

Add this class at the end of `app/models.py` (the imports `CheckConstraint`, `DateTime`, `Integer`, `String`, `Text`, `func`, `Mapped`, `mapped_column` are already imported in that file):

```python
class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("role IN ('admin', 'user')", name="chk_user_role"),
    )
```

- [ ] **Step 2: Add `UserCreate` schema to `app/schemas.py`**

Append:

```python
from typing import Literal


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=6, max_length=200)
    role: Literal["admin", "user"] = "user"
```

(`BaseModel` and `Field` are already imported at the top of `schemas.py`.)

- [ ] **Step 3: Add user CRUD functions to `app/crud.py`**

Add at the end of `app/crud.py` (imports `select`, `AsyncSession`, and `User` need to be available — `select` and `AsyncSession` are imported; add `User` to the existing `from app.models import ...` line so it reads `from app.models import Reservation, Room, User`):

```python
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
```

- [ ] **Step 4: Add the week query to `app/crud.py`**

Add at the end of `app/crud.py`:

```python
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
```

- [ ] **Step 5: Verify it imports cleanly**

Run: `source .venv/bin/activate && python -c "import app.models, app.crud, app.schemas, app.auth; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 6: Run the Task 4 auth tests now that `User` exists**

Run: `source .venv/bin/activate && pytest tests/test_auth.py -v`
Expected: 2 passed.

- [ ] **Step 7: Commit**

```bash
git add app/models.py app/crud.py app/schemas.py
git commit -m "feat: add User model, user CRUD, and weekly room query"
```

---

## Phase 3 — Login, sessions, route protection

### Task 6: Session middleware + exception handlers

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Rewrite `app/main.py`**

```python
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
```

- [ ] **Step 2: Verify import fails cleanly only on missing routers (expected until Task 7/8)**

Run: `source .venv/bin/activate && python -c "import app.main" 2>&1 | tail -1`
Expected: `ModuleNotFoundError` for `app.routers.auth_routes` or `app.routers.admin` (created next). This confirms wiring; proceed to Task 7.

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: add session middleware and auth exception handlers"
```

---

### Task 7: Login / logout routes + template

**Files:**
- Create: `app/routers/auth_routes.py`
- Create: `app/templates/login.html`

- [ ] **Step 1: Create `app/routers/auth_routes.py`**

```python
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
```

- [ ] **Step 2: Create `app/templates/login.html`**

```html
{% extends "base.html" %}
{% block title %}Sign in — Meeting Room Booking{% endblock %}
{% block content %}
<h2>Sign in</h2>
<div class="card" style="max-width: 360px;">
    <form method="post" action="/login">
        <label>Username
            <input type="text" name="username" autofocus required>
        </label>
        <label>Password
            <input type="password" name="password" required>
        </label>
        <button type="submit">Sign in</button>
        {% if error %}<div class="error" role="alert">{{ error }}</div>{% endif %}
    </form>
</div>
{% endblock %}
```

- [ ] **Step 3: Verify the app boots**

Run: `source .venv/bin/activate && python -c "import app.main" 2>&1 | tail -1`
Expected: still fails on `app.routers.admin` import (created in Task 9). Temporarily confirm auth import works:
Run: `source .venv/bin/activate && python -c "import app.routers.auth_routes; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add app/routers/auth_routes.py app/templates/login.html
git commit -m "feat: add login/logout routes and login page"
```

---

### Task 8: Login integration test

**Files:**
- Create: `tests/test_auth_routes.py`

> Requires Task 9 (admin router) for `app.main` to import. If executing strictly in order, create a temporary empty `app/routers/admin.py` with `from fastapi import APIRouter; router = APIRouter()` now, then complete it in Task 9. Otherwise do Task 9 first and run this test afterward.

- [ ] **Step 1: Write the integration test**

```python
# tests/test_auth_routes.py
import pytest

from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME


@pytest.mark.asyncio
async def test_login_success_sets_session_and_redirects(client):
    resp = await client.post(
        "/login",
        data={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/calendar"


@pytest.mark.asyncio
async def test_login_failure_returns_401(client):
    resp = await client.post(
        "/login",
        data={"username": TEST_ADMIN_USERNAME, "password": "wrong"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    assert "Invalid username or password" in resp.text


@pytest.mark.asyncio
async def test_protected_route_redirects_anonymous_to_login(client):
    resp = await client.get("/calendar", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
```

- [ ] **Step 2: Run it**

Run: `source .venv/bin/activate && pytest tests/test_auth_routes.py -v`
Expected: 3 passed. (The third assertion depends on `/calendar` being protected, built in Task 13. If running before Task 13, expect that one to fail until then.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_auth_routes.py
git commit -m "test: login success/failure and anonymous redirect"
```

---

## Phase 4 — Admin user management

### Task 9: Admin user-management routes + template

**Files:**
- Create: `app/routers/admin.py`
- Create: `app/templates/admin_users.html`

- [ ] **Step 1: Create `app/routers/admin.py`**

```python
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
```

- [ ] **Step 2: Create `app/templates/admin_users.html`**

```html
{% extends "base.html" %}
{% block title %}Manage Users — Meeting Room Booking{% endblock %}
{% block content %}
<h2>Manage Users</h2>

<div class="card" style="max-width: 420px; margin-bottom: 1.5rem;">
    <h3>Add user</h3>
    <form method="post" action="/admin/users">
        <label>Username
            <input type="text" name="username" maxlength="150" required>
        </label>
        <label>Password
            <input type="password" name="password" minlength="6" required>
        </label>
        <label>Role
            <select name="role">
                <option value="user" selected>user</option>
                <option value="admin">admin</option>
            </select>
        </label>
        <button type="submit">Create user</button>
        {% if error %}<div class="error" role="alert">{{ error }}</div>{% endif %}
    </form>
</div>

<div class="table-wrap">
    <table>
        <thead>
            <tr><th>Username</th><th>Role</th><th>Created</th><th></th></tr>
        </thead>
        <tbody>
            {% for u in users %}
            <tr>
                <td>{{ u.username }}</td>
                <td>{{ u.role }}</td>
                <td>{{ u.created_at.strftime('%Y-%m-%d') }}</td>
                <td>
                    {% if u.user_id != current_user.user_id %}
                    <form method="post" action="/admin/users/{{ u.user_id }}/delete"
                          onsubmit="return confirm('Delete user {{ u.username }}?');">
                        <button class="del" type="submit">Delete</button>
                    </form>
                    {% else %}
                    <span style="color: var(--muted);">(you)</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
```

- [ ] **Step 3: Verify the app imports**

Run: `source .venv/bin/activate && python -c "import app.main; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 4: Commit**

```bash
git add app/routers/admin.py app/templates/admin_users.html
git commit -m "feat: admin user-management page (create/delete users)"
```

---

### Task 10: Admin route integration tests

**Files:**
- Create: `tests/test_admin.py`

- [ ] **Step 1: Write the tests**

```python
# tests/test_admin.py
import pytest

from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME


async def _login_as_admin(client):
    await client.post(
        "/login",
        data={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
    )


@pytest.mark.asyncio
async def test_admin_can_create_user(admin_client):
    resp = await admin_client.post(
        "/admin/users",
        data={"username": "alice", "password": "secret1", "role": "user"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    page = await admin_client.get("/admin/users")
    assert "alice" in page.text


@pytest.mark.asyncio
async def test_duplicate_username_shows_error(admin_client):
    await admin_client.post(
        "/admin/users",
        data={"username": "bob", "password": "secret1", "role": "user"},
    )
    resp = await admin_client.post(
        "/admin/users",
        data={"username": "bob", "password": "secret1", "role": "user"},
    )
    assert "already exists" in resp.text


@pytest.mark.asyncio
async def test_normal_user_cannot_access_admin(admin_client):
    # admin creates a normal user
    await admin_client.post(
        "/admin/users",
        data={"username": "carol", "password": "secret1", "role": "user"},
    )
    await admin_client.post("/logout")
    await admin_client.post(
        "/login", data={"username": "carol", "password": "secret1"}
    )
    resp = await admin_client.get("/admin/users", follow_redirects=False)
    assert resp.status_code == 403
```

- [ ] **Step 2: Run the tests**

Run: `source .venv/bin/activate && pytest tests/test_admin.py -v`
Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_admin.py
git commit -m "test: admin create/delete users and role enforcement"
```

---

## Phase 5 — Calendar availability

### Task 11: Calendar grid helpers (pure, TDD)

**Files:**
- Create: `app/calendar_utils.py`
- Test: `tests/test_calendar_utils.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_calendar_utils.py
import datetime

from app.calendar_utils import (
    build_week_grid,
    generate_slots,
    monday_of,
    reservation_covers_slot,
    week_dates,
)


class FakeRes:
    def __init__(self, res_date, start, end, responsible="X"):
        self.res_date = res_date
        self.start_time = start
        self.end_time = end
        self.responsible = responsible


def test_generate_slots_first_and_last():
    slots = generate_slots()
    assert slots[0] == (datetime.time(8, 0), datetime.time(8, 30))
    assert slots[-1] == (datetime.time(19, 30), datetime.time(20, 0))
    assert len(slots) == 24


def test_monday_of_returns_monday():
    # 2026-06-10 is a Wednesday; its Monday is 2026-06-08.
    assert monday_of(datetime.date(2026, 6, 10)) == datetime.date(2026, 6, 8)


def test_week_dates_is_seven_days_mon_to_sun():
    dates = week_dates(datetime.date(2026, 6, 10))
    assert dates[0] == datetime.date(2026, 6, 8)
    assert dates[-1] == datetime.date(2026, 6, 14)
    assert len(dates) == 7


def test_reservation_covers_slot_overlap_rules():
    res = FakeRes(datetime.date(2026, 6, 8), datetime.time(9, 0), datetime.time(10, 0))
    assert reservation_covers_slot(res, datetime.time(9, 0), datetime.time(9, 30))
    assert reservation_covers_slot(res, datetime.time(9, 30), datetime.time(10, 0))
    # touching boundaries do not count as overlap
    assert not reservation_covers_slot(res, datetime.time(8, 30), datetime.time(9, 0))
    assert not reservation_covers_slot(res, datetime.time(10, 0), datetime.time(10, 30))


def test_build_week_grid_marks_booked_cells_and_start():
    monday = datetime.date(2026, 6, 8)
    res = FakeRes(monday, datetime.time(9, 0), datetime.time(10, 0), "Alice")
    dates = week_dates(monday)
    slots = generate_slots()
    grid = build_week_grid([res], dates, slots)

    # grid is list of (slot_start, slot_end, [cell per day])
    # Find the 09:00-09:30 row.
    row_0900 = next(r for r in grid if r[0] == datetime.time(9, 0))
    monday_cell = row_0900[2][0]  # day index 0 == Monday
    assert monday_cell["res"] is res
    assert monday_cell["is_start"] is True

    row_0930 = next(r for r in grid if r[0] == datetime.time(9, 30))
    assert row_0930[2][0]["res"] is res
    assert row_0930[2][0]["is_start"] is False

    # A free slot is None.
    row_0800 = next(r for r in grid if r[0] == datetime.time(8, 0))
    assert row_0800[2][0]["res"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && pytest tests/test_calendar_utils.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.calendar_utils'`.

- [ ] **Step 3: Implement `app/calendar_utils.py`**

```python
"""Pure helpers for building the weekly availability grid.

No database or FastAPI imports — easy to unit test. Reservations are duck-typed:
any object with .res_date (date), .start_time (time), .end_time (time),
.responsible (str) works.
"""
import datetime

DAY_START_HOUR = 8
DAY_END_HOUR = 20
SLOT_MINUTES = 30

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def generate_slots() -> list[tuple[datetime.time, datetime.time]]:
    """Return [(08:00,08:30), ..., (19:30,20:00)] at SLOT_MINUTES granularity."""
    slots: list[tuple[datetime.time, datetime.time]] = []
    minutes = DAY_START_HOUR * 60
    end_minutes = DAY_END_HOUR * 60
    while minutes < end_minutes:
        start = datetime.time(minutes // 60, minutes % 60)
        nxt = minutes + SLOT_MINUTES
        end = datetime.time(nxt // 60, nxt % 60) if nxt < 24 * 60 else datetime.time(0, 0)
        slots.append((start, end))
        minutes = nxt
    return slots


def monday_of(day: datetime.date) -> datetime.date:
    return day - datetime.timedelta(days=day.weekday())


def week_dates(day: datetime.date) -> list[datetime.date]:
    start = monday_of(day)
    return [start + datetime.timedelta(days=i) for i in range(7)]


def reservation_covers_slot(
    res, slot_start: datetime.time, slot_end: datetime.time
) -> bool:
    """True if the reservation overlaps [slot_start, slot_end)."""
    return res.start_time < slot_end and res.end_time > slot_start


def build_week_grid(reservations, dates, slots):
    """Build rows of (slot_start, slot_end, cells).

    Each cell is {"res": reservation_or_None, "is_start": bool}. is_start marks
    the slot where the reservation begins (used to print the label once).
    """
    by_date: dict[datetime.date, list] = {d: [] for d in dates}
    for r in reservations:
        if r.res_date in by_date:
            by_date[r.res_date].append(r)

    grid = []
    for slot_start, slot_end in slots:
        cells = []
        for d in dates:
            booked = next(
                (
                    r
                    for r in by_date[d]
                    if reservation_covers_slot(r, slot_start, slot_end)
                ),
                None,
            )
            is_start = bool(booked and slot_start <= booked.start_time < slot_end)
            cells.append({"res": booked, "is_start": is_start})
        grid.append((slot_start, slot_end, cells))
    return grid
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `source .venv/bin/activate && pytest tests/test_calendar_utils.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add app/calendar_utils.py tests/test_calendar_utils.py
git commit -m "feat: add pure weekly availability grid helpers (TDD)"
```

---

### Task 12: Calendar route + template

**Files:**
- Modify: `app/routers/views.py`
- Create: `app/templates/calendar.html`

- [ ] **Step 1: Update imports and add the `/calendar` route in `app/routers/views.py`**

At the top of `app/routers/views.py`, add to the imports:

```python
from app.auth import get_current_user, require_admin, require_user
from app.calendar_utils import DAY_NAMES, build_week_grid, generate_slots, monday_of, week_dates
from app.models import User
```

Then add this route (place it above the existing `/view` route):

```python
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
```

- [ ] **Step 2: Create `app/templates/calendar.html`**

```html
{% if full %}{% extends "base.html" %}{% endif %}
{% block title %}Calendar — Meeting Room Booking{% endblock %}
{% block content %}
{% if full %}
<h2>Room Availability</h2>
<div class="controls">
    <label>Room
        <select name="room_id"
                hx-get="/calendar"
                hx-target="#calendar-grid"
                hx-swap="innerHTML"
                hx-trigger="change"
                hx-include="[name='week']">
            {% for room in rooms %}
            <option value="{{ room.room_id }}"
                    {% if room.room_id == selected_id %}selected{% endif %}>
                {{ room.name }}
            </option>
            {% endfor %}
        </select>
    </label>
    <input type="hidden" name="week" value="{{ week_start.isoformat() }}">
    <span>
        <a href="/calendar?room_id={{ selected_id }}&week={{ prev_week }}">&larr; Prev week</a>
        &nbsp;|&nbsp;
        <strong>Week of {{ week_start.strftime('%Y-%m-%d') }}</strong>
        &nbsp;|&nbsp;
        <a href="/calendar?room_id={{ selected_id }}&week={{ next_week }}">Next week &rarr;</a>
    </span>
</div>
<div id="calendar-grid">
{% endif %}
    <div class="table-wrap">
        <table class="calendar">
            <thead>
                <tr>
                    <th>Time</th>
                    {% for d in dates %}
                    <th {% if d == today %}class="today"{% endif %}>
                        {{ day_names[loop.index0] }}<br>
                        <span class="date">{{ d.strftime('%m-%d') }}</span>
                    </th>
                    {% endfor %}
                </tr>
            </thead>
            <tbody>
                {% for slot_start, slot_end, cells in grid %}
                <tr>
                    <td class="time">{{ slot_start.strftime('%H:%M') }}</td>
                    {% for cell in cells %}
                    {% set d = dates[loop.index0] %}
                    {% if cell.res %}
                    <td class="booked" title="{{ cell.res.responsible }} {{ cell.res.start_time.strftime('%H:%M') }}-{{ cell.res.end_time.strftime('%H:%M') }}">
                        {% if cell.is_start %}{{ cell.res.responsible }}{% endif %}
                    </td>
                    {% elif is_admin %}
                    <td class="free">
                        <a class="book"
                           href="/reservations/new?room_id={{ selected_id }}&res_date={{ d.isoformat() }}&start_time={{ slot_start.strftime('%H:%M') }}&end_time={{ slot_end.strftime('%H:%M') }}">+</a>
                    </td>
                    {% else %}
                    <td class="free"></td>
                    {% endif %}
                    {% endfor %}
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
{% if full %}
</div>
{% endif %}
{% endblock %}
```

- [ ] **Step 3: Add calendar CSS to `app/templates/base.html`**

Inside the `<style>` block in `base.html`, add before the closing `</style>`:

```css
table.calendar td, table.calendar th { text-align: center; min-width: 70px; }
table.calendar td.time { font-size: 0.8rem; color: var(--muted); white-space: nowrap; }
table.calendar td.booked {
    background: #fca5a5;
    color: #7f1d1d;
    font-size: 0.75rem;
    font-weight: 600;
}
table.calendar td.free { background: #dcfce7; }
table.calendar td.free a.book {
    display: block;
    color: #15803d;
    text-decoration: none;
    font-weight: 700;
    opacity: 0;
}
table.calendar td.free:hover a.book { opacity: 1; }
table.calendar th.today { background: #dbeafe; }
table.calendar th .date { font-weight: 400; color: var(--muted); font-size: 0.75rem; }
```

- [ ] **Step 4: Verify the app boots**

Run: `source .venv/bin/activate && python -c "import app.main; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 5: Commit**

```bash
git add app/routers/views.py app/templates/calendar.html app/templates/base.html
git commit -m "feat: weekly per-room availability calendar"
```

---

### Task 13: Calendar integration test

**Files:**
- Create: `tests/test_calendar.py`

- [ ] **Step 1: Write the test**

```python
# tests/test_calendar.py
import pytest

from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME


@pytest.mark.asyncio
async def test_calendar_requires_login(client):
    resp = await client.get("/calendar", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


@pytest.mark.asyncio
async def test_calendar_shows_booking_for_week(admin_client):
    # Create a booking on a fixed Monday.
    await admin_client.post(
        "/reservations",
        data={
            "room_id": "1",
            "responsible": "Zoe",
            "res_date": "2026-06-08",
            "start_time": "09:00",
            "end_time": "10:00",
        },
    )
    resp = await admin_client.get("/calendar?room_id=1&week=2026-06-08")
    assert resp.status_code == 200
    assert "Zoe" in resp.text
    assert 'class="booked"' in resp.text


@pytest.mark.asyncio
async def test_admin_sees_book_links_user_does_not(admin_client):
    # admin view has the "+" book link
    resp = await admin_client.get("/calendar?room_id=1&week=2026-06-08")
    assert 'class="book"' in resp.text

    # create a normal user, log in as them, confirm no book link
    await admin_client.post(
        "/admin/users",
        data={"username": "viewer", "password": "secret1", "role": "user"},
    )
    await admin_client.post("/logout")
    await admin_client.post(
        "/login", data={"username": "viewer", "password": "secret1"}
    )
    resp = await admin_client.get("/calendar?room_id=1&week=2026-06-08")
    assert resp.status_code == 200
    assert 'class="book"' not in resp.text
```

- [ ] **Step 2: Run the test**

Run: `source .venv/bin/activate && pytest tests/test_calendar.py -v`
Expected: 3 passed. (Depends on Task 14 making reservations admin-gated for the create call to succeed as admin — it does, admin_client is admin.)

- [ ] **Step 3: Commit**

```bash
git add tests/test_calendar.py
git commit -m "test: calendar auth gating and availability rendering"
```

---

## Phase 6 — Role gating + navigation + prefill

### Task 14: Gate reservation create/delete behind admin; protect + prefill views

**Files:**
- Modify: `app/routers/reservations.py`
- Modify: `app/routers/views.py`
- Modify: `app/templates/new_reservation.html`
- Modify: `app/templates/view_reservations.html`

- [ ] **Step 1: Require admin for create/delete in `app/routers/reservations.py`**

Add to the imports:

```python
from app.auth import require_admin
from app.models import User
```

Then add an admin dependency to both routes. In `create_reservation`, add this parameter (before `session`):

```python
    admin: User = Depends(require_admin),
```

In `delete_reservation`, add the same parameter (before `session`):

```python
    admin: User = Depends(require_admin),
```

- [ ] **Step 2: Update `new_reservation` GET route in `app/routers/views.py` to accept prefill + require admin**

Replace the existing `new_reservation_form` function with:

```python
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
```

- [ ] **Step 3: Protect `/view` and pass `current_user` in `app/routers/views.py`**

In the `view_reservations` route signature, add `user` and remove anonymous access by depending on `require_user`:

```python
async def view_reservations(
    request: Request,
    room_id: str | None = None,
    period: str | None = None,
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
```

And add to its `TemplateResponse` context dict these keys:

```python
            "current_user": user,
            "is_admin": user.role == "admin",
```

- [ ] **Step 4: Make `/` redirect to `/calendar` in `app/routers/views.py`**

Replace the existing `index` route with:

```python
@router.get("/")
async def index(user: User | None = Depends(get_current_user)):
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    return RedirectResponse(url="/calendar", status_code=303)
```

Add `RedirectResponse` to the `fastapi.responses` import line in `views.py`:

```python
from fastapi.responses import HTMLResponse, RedirectResponse
```

- [ ] **Step 5: Apply prefill values in `app/templates/new_reservation.html`**

Update the form inputs to use prefill values. Replace the room `<select>`, date, start, and end inputs with:

```html
        <label>Room
            <select name="room_id" required>
                {% for room in rooms %}
                <option value="{{ room.room_id }}"
                        {% if room.room_id == prefill_room_id %}selected{% endif %}>
                    {{ room.name }}
                </option>
                {% endfor %}
            </select>
        </label>
        <label>Date
            <input type="date" name="res_date" value="{{ prefill_date }}" required>
        </label>
        <label>Start time
            <input type="time" name="start_time" value="{{ prefill_start }}" required>
        </label>
        <label>End time
            <input type="time" name="end_time" value="{{ prefill_end }}" required>
        </label>
```

- [ ] **Step 6: Hide the Delete column from non-admins in `app/templates/view_reservations.html`**

Wrap the Delete `<th>` and the Delete `<td>` cell in `{% if is_admin %}`. Change the header cell:

```html
                    <th>Notes</th>
                    {% if is_admin %}<th></th>{% endif %}
```

And the body action cell:

```html
                    <td>{{ r.notes or '' }}</td>
                    {% if is_admin %}
                    <td>
                        <button class="del"
                                hx-delete="/reservations/{{ r.reservation_id }}"
                                hx-target="closest tr"
                                hx-swap="outerHTML"
                                hx-confirm="Delete this reservation?">
                            Delete
                        </button>
                    </td>
                    {% endif %}
```

Also update the empty-row `colspan` to adapt:

```html
                <tr><td class="empty" colspan="{% if is_admin %}8{% else %}7{% endif %}">No reservations match these filters.</td></tr>
```

- [ ] **Step 7: Write the role-gating test**

Create `tests/test_reservations_roles.py`:

```python
# tests/test_reservations_roles.py
import pytest

from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME


async def _make_user_and_login(admin_client, username):
    await admin_client.post(
        "/admin/users",
        data={"username": username, "password": "secret1", "role": "user"},
    )
    await admin_client.post("/logout")
    await admin_client.post(
        "/login", data={"username": username, "password": "secret1"}
    )


@pytest.mark.asyncio
async def test_admin_can_create_reservation(admin_client):
    resp = await admin_client.post(
        "/reservations",
        data={
            "room_id": "1",
            "responsible": "Amy",
            "res_date": "2026-06-15",
            "start_time": "09:00",
            "end_time": "10:00",
        },
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    assert resp.status_code == 204
    assert resp.headers["hx-redirect"] == "/view?room_id=1"


@pytest.mark.asyncio
async def test_user_cannot_create_reservation(admin_client):
    await _make_user_and_login(admin_client, "ned")
    resp = await admin_client.post(
        "/reservations",
        data={
            "room_id": "1",
            "responsible": "Ned",
            "res_date": "2026-06-15",
            "start_time": "09:00",
            "end_time": "10:00",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_user_cannot_open_new_form(admin_client):
    await _make_user_and_login(admin_client, "olive")
    resp = await admin_client.get("/reservations/new", follow_redirects=False)
    assert resp.status_code == 403
```

- [ ] **Step 8: Run the full test suite**

Run: `source .venv/bin/activate && pytest -v`
Expected: all tests pass (auth, admin, calendar, calendar_utils, reservation roles).

- [ ] **Step 9: Commit**

```bash
git add app/routers/reservations.py app/routers/views.py app/templates/new_reservation.html app/templates/view_reservations.html tests/test_reservations_roles.py
git commit -m "feat: gate create/delete behind admin, prefill form, protect views"
```

---

### Task 15: Role-aware navigation

**Files:**
- Modify: `app/templates/base.html`
- Delete: `app/templates/index.html`

- [ ] **Step 1: Replace the nav block in `app/templates/base.html`**

Replace the `<nav>` inside `<header>` with:

```html
        <nav>
            <span class="brand">📅 Meeting Rooms</span>
            {% if current_user %}
            <a href="/calendar">Calendar</a>
            <a href="/view">Reservations</a>
            {% if current_user.role == 'admin' %}
            <a href="/reservations/new">New Reservation</a>
            <a href="/admin/users">Manage Users</a>
            {% endif %}
            <span style="margin-left:auto; color: var(--muted);">{{ current_user.username }} ({{ current_user.role }})</span>
            <form method="post" action="/logout" style="display:inline;">
                <button type="submit" style="background:transparent; color:var(--accent); padding:0; font-weight:600;">Logout</button>
            </form>
            {% endif %}
        </nav>
```

- [ ] **Step 2: Delete the now-unused landing template**

Run: `git rm app/templates/index.html`
Expected: `index.html` removed (root now redirects to `/calendar` or `/login`).

- [ ] **Step 3: Manual smoke test**

Run (in one terminal): `source .venv/bin/activate && uvicorn app.main:app --reload`
Then verify in a browser:
1. Visit `http://localhost:8000/` → redirected to `/login`.
2. Log in with your `.env` admin creds → lands on `/calendar`.
3. Calendar shows the room dropdown, week nav, and green free cells with `+` links.
4. Click a free cell `+` → new-reservation form is pre-filled with that room/date/time. Submit → redirected to `/view`.
5. Go back to `/calendar` for that week → the slot is now red/booked with the responsible name.
6. Open `/admin/users`, create a `user`-role account, log out, log in as them → no "New Reservation"/"Manage Users" nav links, calendar has no `+` links, `/view` has no Delete column, and visiting `/admin/users` returns 403.

- [ ] **Step 4: Commit**

```bash
git add app/templates/base.html
git commit -m "feat: role-aware navigation with logout"
```

---

### Task 16: Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update `README.md`**

Add a `SECRET_KEY` / admin note to the Setup section and a new "Users & roles" section. Insert after the `.env` table:

```markdown
Generate a session secret and set it in `.env`:

\`\`\`bash
python -c "import secrets; print(secrets.token_hex(32))"   # paste as SECRET_KEY
\`\`\`

Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `.env` **before** running migrations —
migration `002` seeds this admin account.
```

And add this section before "## 4. Run":

```markdown
## Users & roles

- **Admin** — can create and delete reservations and manage users (`/admin/users`).
- **User** — can sign in and view room availability only.

The first admin is seeded from `.env` by `alembic upgrade head`. Sign in at
`/login`; the home page and all views require authentication. Admins add further
accounts from **Manage Users**.
```

- [ ] **Step 2: Run the full suite once more**

Run: `source .venv/bin/activate && pytest -v`
Expected: all green.

- [ ] **Step 3: Commit and push**

```bash
git add README.md
git commit -m "docs: document auth, admin seeding, and roles"
git push
```

---

## Self-Review

**Spec coverage:**
- "See when rooms are free to book" → Task 11 (grid logic) + Task 12/13 (calendar view, free=green/booked=red). ✓
- "Login part" → Tasks 6–8 (session middleware, login/logout). ✓
- "Two user types: admin creates/deletes, user views" → Tasks 9, 14 (`require_admin` on create/delete + user mgmt; `require_user` on views; nav/template gating). ✓
- "Visualization like a calendar with start/end" → Task 12 week grid with per-slot start/end and week navigation. ✓
- Admin can create/delete bookings → Task 14 (create/delete gated) + existing delete in `/view`, plus calendar `+` prefill. ✓

**Placeholder scan:** No "TBD"/"add validation"/"similar to Task N". Every code step shows full code. Test steps include real assertions and exact `pytest` commands. ✓

**Type/name consistency:**
- `hash_password`/`verify_password` (Task 4) used in Tasks 7, 9, migration 002. ✓
- `require_user`/`require_admin`/`get_current_user`/`NotAuthenticated`/`NotAuthorized` (Task 4) used in Tasks 6, 12, 14. ✓
- `build_week_grid`/`generate_slots`/`week_dates`/`monday_of`/`reservation_covers_slot`/`DAY_NAMES` (Task 11) used in Task 12 and tested in Task 11. ✓
- Cell shape `{"res", "is_start"}` (Task 11) consumed by `calendar.html` (Task 12) as `cell.res` / `cell.is_start`. ✓
- `current_user` context key set in Tasks 9, 12, 14 and read by `base.html` (Task 15) and `admin_users.html` (Task 9). ✓
- `get_reservations_for_room_week(session, room_id, week_start)` (Task 5) called in Task 12 with `dates[0]`. ✓

**Known ordering note:** `app.main` imports `app.routers.admin` (Task 9) and `app.routers.auth_routes` (Task 7), so `app.main` won't import until those exist. Tasks are ordered so pure-logic tests (Tasks 4, 11) run independently, and integration tests (Tasks 8, 10, 13, 14) run after their routers exist. If executing strictly top-to-bottom, Task 8's note explains the temporary admin-router stub.
