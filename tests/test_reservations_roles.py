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
    assert resp.headers["hx-redirect"] == "/calendar?room_id=1&week=2026-06-15"


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
