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

    Each cell is {"res": reservation_or_None, "is_start": bool}. is_start marks
    the slot where the reservation begins (used to print the label once).
    """
    by_date: dict[datetime.date, list] = {d: [] for d in dates}
    for r in reservations:
        if r.res_date in by_date:
            by_date[r.res_date].append(r)

    grid = []
    for slot_start, slot_end in slots:
        cells = []
        for d in dates:
            booked = next(
                (
                    r
                    for r in by_date[d]
                    if reservation_covers_slot(r, slot_start, slot_end)
                ),
                None,
            )
            is_start = bool(booked and slot_start <= booked.start_time < slot_end)
            cells.append({"res": booked, "is_start": is_start})
        grid.append((slot_start, slot_end, cells))
    return grid
