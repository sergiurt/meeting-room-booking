# Meeting Room Booking

A role-based internal meeting room booking tool. Admins reserve rooms and manage
users; all authenticated users can browse the weekly calendar and reservation list.
Overlapping bookings are prevented at the database level.

Built with FastAPI, async SQLAlchemy 2, Alembic, Jinja2 + HTMX, and PostgreSQL.

---

## 1. Requirements

- **Python 3.11+**
- **PostgreSQL** (with permission to create extensions and types)

The application relies on the PostgreSQL `btree_gist` extension and a custom
`timerange` range type for the no-overlap exclusion constraint. Both are created
automatically by the Alembic migration.

---

## 2. Setup

```bash
# Clone the repository
git clone <your-repo-url> meeting_rooms
cd meeting_rooms

# Create and activate a virtual environment
python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and set DATABASE_URL to point at your PostgreSQL instance
```

`.env` keys:

| Key               | Description                                                                              |
| ----------------- | ---------------------------------------------------------------------------------------- |
| `DATABASE_URL`    | Async SQLAlchemy URL, e.g. `postgresql+asyncpg://user:pass@localhost:5432/meeting_rooms` |
| `TEST_DATABASE_URL` | URL for the test database (used by pytest)                                             |
| `SECRET_KEY`      | Secret key for session cookie signing                                                    |
| `ADMIN_USERNAME`  | Username for the seeded admin account                                                    |
| `ADMIN_PASSWORD`  | Password for the seeded admin account                                                    |
| `APP_HOST`        | Host interface for the app server (e.g. `0.0.0.0`)                                      |
| `APP_PORT`        | Port for the app server (e.g. `8000`)                                                    |

Generate a session secret and set it in `.env`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"   # paste as SECRET_KEY
```

Set `ADMIN_USERNAME` and `ADMIN_PASSWORD` in `.env` **before** running migrations —
migration `002` seeds this admin account.

Make sure the target database exists before running migrations:

```bash
createdb meeting_rooms
```

---

## 3. Database setup

Apply the schema (creates the `btree_gist` extension, the `timerange` type, the
`rooms` and `reservations` tables, seed rooms, indexes, and the no-overlap
exclusion constraint):

```bash
alembic upgrade head
```

To roll the schema back:

```bash
alembic downgrade base
```

---

## Users & roles

- **Admin** — can create and delete reservations and manage users (`/admin/users`).
- **User** — can sign in and view room availability only.

The first admin is seeded from `.env` by `alembic upgrade head`. Sign in at
`/login`; the home page and all views require authentication. Admins add further
accounts from **Manage Users**.

---

## 4. Run

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

(Host and port also default from `APP_HOST` / `APP_PORT` when running
`python -m app.main`.)

---

## 5. Access

Open the app in your browser:

```
http://localhost:8000
```

The root URL redirects unauthenticated users to `/login` and authenticated users
to `/calendar`. Key pages:

- **Sign in** — `/login`
- **Weekly calendar** — `/calendar`
- **Reservations list** — `/view`
- **New Reservation** (admin only) — `/reservations/new`
- **Manage Users** (admin only) — `/admin/users`
