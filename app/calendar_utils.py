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

    Each cell is a dict:
      - "res":      the covering reservation, or None if the slot is free.
      - "is_start": True on the first covered slot of a reservation (where the
                    single merged block is rendered).
      - "skip":     True for later slots covered by a reservation whose block
                    started above (the template renders no <td> for these,
                    because the start cell spans them via rowspan).
      - "rowspan":  on a start cell, how many slots the block spans (>=1).

    Each reservation therefore renders as ONE clickable cell spanning its whole
    duration, rather than one cell per 30-minute slot.
    """
    by_date: dict[datetime.date, list] = {d: [] for d in dates}
    for r in reservations:
        if r.res_date in by_date:
            by_date[r.res_date].append(r)

    n = len(slots)
    # For each day, map slot index -> the reservation covering it (or None).
    covering: dict[datetime.date, list] = {d: [None] * n for d in dates}
    for d in dates:
        for r in by_date[d]:
            for i, (slot_start, slot_end) in enumerate(slots):
                if reservation_covers_slot(r, slot_start, slot_end):
                    covering[d][i] = r

    grid = []
    for i, (slot_start, slot_end) in enumerate(slots):
        cells = []
        for d in dates:
            res = covering[d][i]
            if res is None:
                cells.append(
                    {"res": None, "is_start": False, "skip": False, "rowspan": 1}
                )
                continue
            is_first = i == 0 or covering[d][i - 1] is not res
            if is_first:
                span = 0
                j = i
                while j < n and covering[d][j] is res:
                    span += 1
                    j += 1
                cells.append(
                    {"res": res, "is_start": True, "skip": False, "rowspan": span}
                )
            else:
                cells.append(
                    {"res": res, "is_start": False, "skip": True, "rowspan": 0}
                )
        grid.append((slot_start, slot_end, cells))
    return grid
