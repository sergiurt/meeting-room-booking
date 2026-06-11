# tests/test_calendar.py
import re

import pytest

from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME


async def _create_booking_get_id(admin_client, *, room_id="1", responsible="Zoe",
                                 res_date="2026-06-08", start="09:00", end="10:00"):
    """Create a booking as admin and return its reservation_id (parsed from the
    calendar's detail-card link)."""
    await admin_client.post(
        "/reservations",
        data={
            "room_id": room_id,
            "responsible": responsible,
            "res_date": res_date,
            "start_time": start,
            "end_time": end,
        },
    )
    cal = await admin_client.get(f"/calendar?room_id={room_id}&week={res_date}")
    match = re.search(r"/calendar/reservation/(\d+)", cal.text)
    assert match, "expected a reservation detail link in the calendar"
    return match.group(1)


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
    assert 'class="booked' in resp.text


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


@pytest.mark.asyncio
async def test_admin_can_open_reservation_card(admin_client):
    rid = await _create_booking_get_id(admin_client, responsible="Zoe")
    card = await admin_client.get(
        f"/calendar/reservation/{rid}?room_id=1&week=2026-06-08"
    )
    assert card.status_code == 200
    assert "Reservation details" in card.text
    assert "Zoe" in card.text
    assert "Delete reservation" in card.text


@pytest.mark.asyncio
async def test_admin_can_delete_from_calendar(admin_client):
    rid = await _create_booking_get_id(admin_client, responsible="Zoe")
    resp = await admin_client.post(
        f"/calendar/reservation/{rid}/delete?room_id=1&week=2026-06-08"
    )
    # returns the refreshed calendar partial with the booking gone
    assert resp.status_code == 200
    assert "Zoe" not in resp.text
    # confirm it is really gone from the calendar
    cal = await admin_client.get("/calendar?room_id=1&week=2026-06-08")
    assert "Zoe" not in cal.text


@pytest.mark.asyncio
async def test_user_cannot_open_or_delete_card(admin_client):
    rid = await _create_booking_get_id(admin_client, responsible="Zoe")
    # become a normal user
    await admin_client.post(
        "/admin/users",
        data={"username": "vivi", "password": "secret1", "role": "user"},
    )
    await admin_client.post("/logout")
    await admin_client.post("/login", data={"username": "vivi", "password": "secret1"})

    card = await admin_client.get(
        f"/calendar/reservation/{rid}?room_id=1&week=2026-06-08",
        follow_redirects=False,
    )
    assert card.status_code == 403

    dele = await admin_client.post(
        f"/calendar/reservation/{rid}/delete?room_id=1&week=2026-06-08",
        follow_redirects=False,
    )
    assert dele.status_code == 403

    # the normal user's calendar cells are not clickable (no detail links)
    cal = await admin_client.get("/calendar?room_id=1&week=2026-06-08")
    assert "/calendar/reservation/" not in cal.text
