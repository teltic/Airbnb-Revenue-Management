"""Core row-building and Flag logic for the per-property tabs.

Flag design (replaces an earlier history-based version): rather than
inferring "typical" price from this property's own past booked prices --
which just launders forward whatever pricing mistakes already happened --
the Flag is driven by actual market occupancy for that date, gated by
whether the date is close enough to check-in that still being unbooked is
a meaningful signal at all. Market Percentile (Current Price vs. the
comp-set's own percentile columns) is still computed as a Excel-native
formula in workbook_build.py for live display; the same bucket is computed
here in Python (via market.market_percentile_bucket) purely to drive Flag,
since Flag itself is now too branchy (two independent gates, dynamic
dollar-formatted text) to keep as a maintainable single Excel formula the
way the old design did.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .calendar import CalendarDay
from .dates import category as classify_category
from .dates import day_name
from .market import MarketDay, market_percentile_bucket
from .overrides import OverrideRow

# Every threshold below is deliberately a bare module constant, not buried
# in a formula, so it's a one-line change to retune.
WEEKDAY_LOW_OCCUPANCY_PCT = 30
WEEKEND_LOW_OCCUPANCY_PCT = 40
HIGH_OCCUPANCY_PCT = 80
LY_MISMATCH_THRESHOLD_PCT = 0.20
DEFAULT_BOOKING_WINDOW_DAYS = 45


@dataclass
class DateRow:
    date: dt.date
    day: str
    category: str
    current_price: float | None
    ly_market_occ: float | None
    market_occupancy_pct: float | None
    in_booking_window: str
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
    ly_price: float | None = None
    booked: str = "No"
    flag: str = ""
    flag_color: str = ""


def in_booking_window(
    date: dt.date, today: dt.date, booking_window_days: float | None
) -> str:
    window = booking_window_days if booking_window_days is not None else DEFAULT_BOOKING_WINDOW_DAYS
    return "Yes" if 0 <= (date - today).days <= window else "No"


def flag_for_row(row: DateRow) -> tuple[str, str]:
    """Returns (flag_text, flag_color) where flag_color is "green",
    "salmon", or "" -- a hidden column drives row coloring directly rather
    than the coloring rules trying to pattern-match the flag text (which
    now includes dynamic dollar amounts for LY MISMATCH and so can't be
    matched with a simple equality check the way the old fixed-text flags
    could).
    """
    if row.booked == "Yes":
        return "", ""
    if row.category == "Holiday/Event":
        return "", ""

    # Primary: occupancy-tier, only meaningful once we're close enough to
    # check-in that still being unbooked actually signals something.
    if row.in_booking_window == "Yes" and row.market_occupancy_pct is not None:
        occ = row.market_occupancy_pct
        pct = market_percentile_bucket(
            row.current_price,
            MarketDay(p25=row.market_p25, p50=row.market_p50, p75=row.market_p75, p90=row.market_p90, occupancy_stly=None),
        )
        if pct:
            if row.category == "Weekday (Sun-Thu)" and occ < WEEKDAY_LOW_OCCUPANCY_PCT and pct != "<25th":
                return "ABOVE TARGET (weak weekday demand)", "salmon"
            if row.category == "Weekend (Fri/Sat)" and occ < WEEKEND_LOW_OCCUPANCY_PCT and pct != "<25th":
                return "ABOVE TARGET (weak weekend demand)", "salmon"
            if occ >= HIGH_OCCUPANCY_PCT and pct != ">90th":
                return "BELOW TARGET (strong demand, price too low)", "green"

    # Secondary: LY mismatch -- only checked if the occupancy-tier rule
    # above didn't already flag the row (whether because it evaluated and
    # found nothing, or because the booking-window gate skipped it
    # entirely). Independent of the booking-window gate on purpose: a
    # price drift vs. last year is worth surfacing even well before
    # check-in, not just once we're close to it.
    if row.current_price is not None and row.ly_price:
        pct_diff = (row.current_price - row.ly_price) / row.ly_price
        if abs(pct_diff) > LY_MISMATCH_THRESHOLD_PCT:
            # LY price is blended/stay-level (see nightly_adr_series), not
            # guaranteed a true per-night rate for that exact date.
            color = "green" if pct_diff > 0 else "salmon"
            return f"LY MISMATCH (was ${row.ly_price:,.0f}, now ${row.current_price:,.0f})", color

    return "", ""


def ly_series_for_dates(
    nightly_adr: dict[dt.date, float], dates: list[dt.date]
) -> dict[dt.date, float]:
    ly = {}
    for d in dates:
        one_year_ago = d.replace(year=d.year - 1) if not (d.month == 2 and d.day == 29) else dt.date(d.year - 1, 2, 28)
        if one_year_ago in nightly_adr:
            ly[d] = nightly_adr[one_year_ago]
    return ly


def build_date_rows(
    dates: list[dt.date],
    today: dt.date,
    calendar: dict[dt.date, CalendarDay],
    market: dict[dt.date, MarketDay],
    ly_series: dict[dt.date, float],
    booking_window_days: float | None,
    holidays: dict[str, str],
    overrides: dict[dt.date, OverrideRow],
    promo_lookup: dict[dt.date, tuple[float | None, float | None]],
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

        row = DateRow(
            date=d,
            day=day_name(d),
            category=cat,
            current_price=current_price,
            ly_market_occ=mkt.occupancy_stly if mkt else None,
            market_occupancy_pct=mkt.occupancy if mkt else None,
            in_booking_window=in_booking_window(d, today, booking_window_days),
            price_override=override.price_override_display if override else "",
            override_reason=override.reason if override else "",
            airbnb_promo_price=promo_price,
            discount_pct=promo_discount,
            holiday_name=holidays.get(d.isoformat(), ""),
            market_p25=mkt.p25 if mkt else None,
            market_p50=mkt.p50 if mkt else None,
            market_p75=mkt.p75 if mkt else None,
            market_p90=mkt.p90 if mkt else None,
            ly_price=ly_series.get(d),
            booked=booked,
        )
        row.flag, row.flag_color = flag_for_row(row)
        rows.append(row)
    return rows
