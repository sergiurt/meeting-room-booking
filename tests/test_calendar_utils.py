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
