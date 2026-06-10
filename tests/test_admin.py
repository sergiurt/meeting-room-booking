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
