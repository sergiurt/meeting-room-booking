"""Pytest fixtures: migrated test database + async HTTP client.

Strategy: run Alembic migrations once per session against TEST_DATABASE_URL
(this creates the schema AND seeds the admin), then clean mutable tables after
each test. The seeded admin persists so login tests can use it.
"""
import os
import subprocess

import pytest
from dotenv import load_dotenv

load_dotenv()
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
