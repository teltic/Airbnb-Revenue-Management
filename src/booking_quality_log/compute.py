"""Core row-building logic: one row per confirmed booking, with the gap,
target-ADR, demand-tier, booking-window and stay-pattern signals described
in the spreadsheet's "Read Me" tab.

Fixed date filter: only bookings with check-in on/after START_DATE are
shown, per Thomas's explicit instruction to keep this a fixed cutoff
rather than a rolling "today onward" window.
"""

from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass

from daily_price_analysis.market import MarketDay

from .reservations import Reservation, nightly_adr_series

START_DATE = dt.date(2026, 9, 1)

WEEKEND_DAYS = {4, 5}  # Friday=4, Saturday=5 (Monday=0)

NO_DATA = "no data"
NOT_APPLICABLE = "n/a"


@dataclass
class BookingRow:
    property_name: str
    check_in: dt.date
    check_out: dt.date
    nights: int
    stay_pattern: str
    one_night_stay: bool
    booked_date: dt.date | None
    booking_window_days: int | None
    bw_vs_median: str
    my_adr: float
    my_revenue: float
    source: str
    target_adr_p75: float | str | None
    vs_target_dollar: float | str | None
    vs_target_pct: float | str | None
    market_p25: float | None
    market_p90: float | None
    stly_adr: float | str
    demand_tier: str
    gap_before_days: int | str | None
    gap_before_signal: str | None
    gap_after_days: int | str | None
    gap_after_signal: str | None
    reservation_id: str


def _stay_dates(check_in: dt.date, check_out: dt.date) -> list[dt.date]:
    out = []
    d = check_in
    while d < check_out:
        out.append(d)
        d += dt.timedelta(days=1)
    return out


def _stay_pattern(check_in: dt.date, check_out: dt.date) -> str:
    for d in _stay_dates(check_in, check_out):
        if d.weekday() in WEEKEND_DAYS:
            return "Weekend-anchored"
    return "Midweek"


def _average_market(
    dates: list[dt.date], market: dict[dt.date, MarketDay], attr: str
) -> float | None:
    values = [
        getattr(market[d], attr)
        for d in dates
        if d in market and getattr(market[d], attr) is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)


def demand_tier_bucket(avg_occupancy: float | None) -> str:
    if avg_occupancy is None:
        return ""
    if avg_occupancy < 30:
        return "Low"
    if avg_occupancy < 60:
        return "Mid"
    return "High"


def fill_difficulty_note(avg_occupancy: float | None) -> str:
    if avg_occupancy is None:
        return ""
    if avg_occupancy < 30:
        return "rarely fills alone"
    if avg_occupancy < 60:
        return "sometimes fills alone"
    return "usually fills alone"


def _gap_signal(gap_days: int | None, fill_note: str) -> str | None:
    if gap_days == 1:
        label = "Upsell candidate"
    elif gap_days == 2:
        label = "LOS-discount candidate"
    else:
        return None
    return f"{label} ({fill_note})" if fill_note else label


def _bw_vs_median(bw_days: int | None, median_bw: float | None) -> str:
    if bw_days is None or median_bw is None or median_bw <= 0:
        return ""
    ratio = bw_days / median_bw
    if ratio > 1.25:
        return "Far out"
    if ratio < 0.6:
        return "Last-minute"
    return "Typical"


def _stly_adr(stay_dates: list[dt.date], nightly_adr: dict[dt.date, float]) -> float | str:
    matched = []
    for d in stay_dates:
        try:
            last_year = d.replace(year=d.year - 1)
        except ValueError:
            last_year = d.replace(year=d.year - 1, day=28)  # Feb 29 -> Feb 28
        if last_year in nightly_adr:
            matched.append(nightly_adr[last_year])
    if not matched:
        return NO_DATA
    return round(sum(matched) / len(matched), 2)


def build_booking_rows(
    property_name: str,
    all_confirmed: list[Reservation],
    market: dict[dt.date, MarketDay],
    target_percentile_attr: str = "p75",
) -> list[BookingRow]:
    """Build one row per confirmed booking with check-in >= START_DATE,
    sorted by check-in. `all_confirmed` should include bookings well
    outside that window too -- they're used as gap/STLY/median context,
    just not turned into their own rows.
    """
    ordered = sorted(all_confirmed, key=lambda r: r.check_in)
    nightly_adr = nightly_adr_series(ordered)

    booking_windows = [
        (r.check_in - r.booked_date).days for r in ordered if r.booked_date is not None
    ]
    median_bw = statistics.median(booking_windows) if booking_windows else None

    rows: list[BookingRow] = []
    for i, r in enumerate(ordered):
        if r.check_in < START_DATE:
            continue

        stay_dates = _stay_dates(r.check_in, r.check_out)

        prev = ordered[i - 1] if i > 0 else None
        nxt = ordered[i + 1] if i + 1 < len(ordered) else None

        if prev is not None:
            gap_before_days = (r.check_in - prev.check_out).days
            gap_before_dates = _stay_dates(prev.check_out, r.check_in)
            gap_before_occ = _average_market(gap_before_dates, market, "occupancy")
            gap_before_signal = _gap_signal(gap_before_days, fill_difficulty_note(gap_before_occ))
        else:
            gap_before_days = "first known booking in window"
            gap_before_signal = None

        if nxt is not None:
            gap_after_days = (nxt.check_in - r.check_out).days
            gap_after_dates = _stay_dates(r.check_out, nxt.check_in)
            gap_after_occ = _average_market(gap_after_dates, market, "occupancy")
            gap_after_signal = _gap_signal(gap_after_days, fill_difficulty_note(gap_after_occ))
        else:
            gap_after_days = "last known booking in window"
            gap_after_signal = None

        target_p75 = _average_market(stay_dates, market, target_percentile_attr)
        market_p25 = _average_market(stay_dates, market, "p25")
        market_p90 = _average_market(stay_dates, market, "p90")
        if target_p75 is None:
            vs_target_dollar: float | str | None = NOT_APPLICABLE
            vs_target_pct: float | str | None = NOT_APPLICABLE
            target_p75_display: float | str | None = None
        else:
            vs_target_dollar = round(r.adr - target_p75, 2)
            vs_target_pct = round((r.adr - target_p75) / target_p75, 4) if target_p75 else NOT_APPLICABLE
            target_p75_display = round(target_p75, 2)

        avg_occupancy = _average_market(stay_dates, market, "occupancy")
        booking_window_days = (r.check_in - r.booked_date).days if r.booked_date else None

        rows.append(
            BookingRow(
                property_name=property_name,
                check_in=r.check_in,
                check_out=r.check_out,
                nights=r.nights,
                stay_pattern=_stay_pattern(r.check_in, r.check_out),
                one_night_stay=r.nights == 1,
                booked_date=r.booked_date,
                booking_window_days=booking_window_days,
                bw_vs_median=_bw_vs_median(booking_window_days, median_bw),
                my_adr=round(r.adr, 2),
                my_revenue=round(r.revenue, 2),
                source=r.booking_channel,
                target_adr_p75=target_p75_display,
                vs_target_dollar=vs_target_dollar,
                vs_target_pct=vs_target_pct,
                market_p25=round(market_p25, 2) if market_p25 is not None else None,
                market_p90=round(market_p90, 2) if market_p90 is not None else None,
                stly_adr=_stly_adr(stay_dates, nightly_adr),
                demand_tier=demand_tier_bucket(avg_occupancy),
                gap_before_days=gap_before_days,
                gap_before_signal=gap_before_signal,
                gap_after_days=gap_after_days,
                gap_after_signal=gap_after_signal,
                reservation_id=r.display_id,
            )
        )
    return rows
