"""Parse PriceLabs' listing_prices calendar response into a per-date table."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class CalendarDay:
    price: float
    min_stay: int | None
    booked: bool


def parse_calendar(raw_rows: list[dict]) -> dict[dt.date, CalendarDay]:
    result = {}
    for row in raw_rows:
        try:
            d = dt.date.fromisoformat(row["date"])
        except (KeyError, ValueError):
            continue
        result[d] = CalendarDay(
            price=float(row.get("price", 0) or 0),
            min_stay=row.get("min_stay"),
            booked=bool(row.get("booking_status")),
        )
    return result
