"""Core row-building and Flag-threshold logic for the per-property tabs.

Excel-native formulas (Market Percentile lookup, +20% Threshold, Flag) are
written verbatim in workbook_build.py so they match the hand-built prototype
and keep recalculating if a user edits Current Price by hand; this module
computes everything those formulas read (the hidden aggregate columns) plus
the plain-value columns.

Aggregate note: the spec defines All-Time/This-Month Max & Floor as maxima
over "best known booked price" (current price if booked, else LY ADR, else
2LY ADR) across every date in a category, ever. Since LY/2LY ADR for any
historical date is itself sourced from that date's actual booked-night ADR,
using the reservation-derived nightly ADR series directly as the aggregate
population is equivalent for historical dates and also correctly captures
already-booked future nights -- see bookings.nightly_adr_series. This
avoids a circular definition and is the actual population used below.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .calendar import CalendarDay
from .dates import category as classify_category
from .dates import day_name
from .market import MarketDay, market_percentile_bucket
from .overrides import OverrideRow

PERCENTILE_FLOOR = 0.25


@dataclass
class DateRow:
    date: dt.date
    day: str
    category: str
    current_price: float | None
    ly_adr: float | None
    ly2_adr: float | None
    ly_market_occ: float | None
    price_override: str
    override_reason: str
    airbnb_promo_price: float | None
    discount_pct: float | None
    note_date: object = None
    note: str = ""

    holiday_name: str = ""
    market_p25: float | None = None
    market_p50: float | None = None
    market_p75: float | None = None
    market_p90: float | None = None
    weekday_max_all_time: float | None = None
    weekday_max_this_month: float | None = None
    weekday_floor_this_month: float | None = None
    weekend_max_all_time: float | None = None
    weekend_max_this_month: float | None = None
    weekend_floor_this_month: float | None = None
    booked: str = "No"


def _percentile(sorted_values: list[float], q: float) -> float:
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    idx = q * (n - 1)
    lo, hi = int(idx), min(int(idx) + 1, n - 1)
    frac = idx - lo
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * frac


@dataclass
class CategoryAggregates:
    all_time_max: float | None = None
    this_month_max: dict[int, float] = field(default_factory=dict)
    this_month_floor: dict[int, float] = field(default_factory=dict)


def compute_category_aggregates(
    nightly_adr: dict[dt.date, float], holidays: dict[str, str]
) -> dict[str, CategoryAggregates]:
    by_category: dict[str, list[tuple[int, float]]] = {
        "Weekday (Sun-Thu)": [],
        "Weekend (Fri/Sat)": [],
    }
    for d, adr in nightly_adr.items():
        cat = classify_category(d, holidays)
        if cat == "Holiday/Event":
            continue
        by_category[cat].append((d.month, adr))

    result = {}
    for cat, points in by_category.items():
        agg = CategoryAggregates()
        values = [v for _, v in points]
        if values:
            agg.all_time_max = max(values)

        by_month: dict[int, list[float]] = {}
        for month, v in points:
            by_month.setdefault(month, []).append(v)
        for month, vals in by_month.items():
            if len(vals) >= 3:
                agg.this_month_max[month] = max(vals)
                agg.this_month_floor[month] = _percentile(sorted(vals), PERCENTILE_FLOOR)
        result[cat] = agg
    return result


def flag_for_row(row: DateRow) -> str:
    if row.booked == "Yes":
        return ""
    if row.category == "Holiday/Event":
        return ""

    threshold_base = (
        row.weekday_max_this_month if row.category == "Weekday (Sun-Thu)" else row.weekend_max_this_month
    )
    if threshold_base is None:
        threshold_base = (
            row.weekday_max_all_time if row.category == "Weekday (Sun-Thu)" else row.weekend_max_all_time
        )
    if threshold_base is not None and row.current_price is not None:
        if row.current_price > threshold_base * 1.2:
            return "ABOVE +20% CAP"

    floor = row.weekday_floor_this_month if row.category == "Weekday (Sun-Thu)" else row.weekend_floor_this_month
    if floor is not None and row.current_price is not None and row.current_price < floor:
        return "BELOW TYPICAL"

    return ""


def build_date_rows(
    dates: list[dt.date],
    calendar: dict[dt.date, CalendarDay],
    market: dict[dt.date, MarketDay],
    ly_series: dict[dt.date, float],
    ly2_series: dict[dt.date, float],
    holidays: dict[str, str],
    overrides: dict[dt.date, OverrideRow],
    promo_lookup: dict[dt.date, tuple[float | None, float | None]],
    aggregates: dict[str, CategoryAggregates],
) -> list[DateRow]:
    rows = []
    for d in dates:
        cal = calendar.get(d)
        mkt = market.get(d)
        cat = classify_category(d, holidays)
        booked = "Yes" if cal and cal.booked else "No"
        current_price = cal.price if cal else None

        override = overrides.get(d)
        promo_price, promo_discount = promo_lookup.get(d, (None, None))

        weekday_max_this_month = None
        weekday_floor_this_month = None
        weekend_max_this_month = None
        weekend_floor_this_month = None
        weekday_agg = aggregates.get("Weekday (Sun-Thu)")
        weekend_agg = aggregates.get("Weekend (Fri/Sat)")
        if weekday_agg:
            weekday_max_this_month = weekday_agg.this_month_max.get(d.month)
            weekday_floor_this_month = weekday_agg.this_month_floor.get(d.month)
        if weekend_agg:
            weekend_max_this_month = weekend_agg.this_month_max.get(d.month)
            weekend_floor_this_month = weekend_agg.this_month_floor.get(d.month)

        row = DateRow(
            date=d,
            day=day_name(d),
            category=cat,
            current_price=current_price,
            ly_adr=ly_series.get(d),
            ly2_adr=ly2_series.get(d),
            ly_market_occ=mkt.occupancy_stly if mkt else None,
            price_override=override.price_override_display if override else "",
            override_reason=override.reason if override else "",
            airbnb_promo_price=promo_price,
            discount_pct=promo_discount,
            holiday_name=holidays.get(d.isoformat(), ""),
            market_p25=mkt.p25 if mkt else None,
            market_p50=mkt.p50 if mkt else None,
            market_p75=mkt.p75 if mkt else None,
            market_p90=mkt.p90 if mkt else None,
            weekday_max_all_time=weekday_agg.all_time_max if weekday_agg else None,
            weekday_max_this_month=weekday_max_this_month,
            weekday_floor_this_month=weekday_floor_this_month,
            weekend_max_all_time=weekend_agg.all_time_max if weekend_agg else None,
            weekend_max_this_month=weekend_max_this_month,
            weekend_floor_this_month=weekend_floor_this_month,
            booked=booked,
        )
        rows.append(row)
    return rows


def ly_ly2_series(nightly_adr: dict[dt.date, float], dates: list[dt.date]) -> tuple[dict, dict]:
    ly = {}
    ly2 = {}
    for d in dates:
        one_year_ago = d.replace(year=d.year - 1) if not (d.month == 2 and d.day == 29) else dt.date(d.year - 1, 2, 28)
        two_years_ago = d.replace(year=d.year - 2) if not (d.month == 2 and d.day == 29) else dt.date(d.year - 2, 2, 28)
        if one_year_ago in nightly_adr:
            ly[d] = nightly_adr[one_year_ago]
        if two_years_ago in nightly_adr:
            ly2[d] = nightly_adr[two_years_ago]
    return ly, ly2
