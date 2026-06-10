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
    resp = await client.get("/admin/users", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
