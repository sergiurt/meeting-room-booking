# Meeting Room Booking

A single-user internal meeting room booking tool. Reserve one of three rooms,
prevent overlapping bookings at the database level, and browse reservations by
room or by month.

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

| Key            | Description                                              |
| -------------- | -------------------------------------------------------- |
| `DATABASE_URL` | Async SQLAlchemy URL, e.g. `postgresql+asyncpg://user:pass@localhost:5432/meeting_rooms` |
| `APP_HOST`     | Host interface for the app server (e.g. `0.0.0.0`)       |
| `APP_PORT`     | Port for the app server (e.g. `8000`)                    |

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

From the landing page you can:

- **New Reservation** — `/reservations/new`
- **View by Room** — `/view/room`
- **View by Month** — `/view/month`
