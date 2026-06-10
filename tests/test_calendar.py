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
