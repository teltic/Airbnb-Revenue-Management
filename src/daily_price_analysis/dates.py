from __future__ import annotations

import datetime as dt

WEEKEND_DAYS = {"Friday", "Saturday"}


def day_name(d: dt.date) -> str:
    return d.strftime("%A")


def category(d: dt.date, holidays: dict[str, str]) -> str:
    """Weekday (Sun-Thu) / Weekend (Fri/Sat) / Holiday/Event.

    A holiday tag overrides weekday/weekend classification, per spec.
    """
    if d.isoformat() in holidays:
        return "Holiday/Event"
    return "Weekend (Fri/Sat)" if day_name(d) in WEEKEND_DAYS else "Weekday (Sun-Thu)"


def daterange(start: dt.date, end: dt.date):
    """Inclusive of start, exclusive of end (like range())."""
    d = start
    while d < end:
        yield d
        d += dt.timedelta(days=1)
