import datetime as dt

from daily_price_analysis.compute import (
    DateRow,
    compute_category_aggregates,
    flag_for_row,
)


def _weekday_dates_in_month(year: int, month: int, weekday_names: set[str], count: int):
    """Helper: first `count` dates in year/month matching Python weekday names."""
    d = dt.date(year, month, 1)
    out = []
    while len(out) < count:
        if d.strftime("%A") in weekday_names:
            out.append(d)
        d += dt.timedelta(days=1)
        if d.month != month:
            break
    return out


def test_aggregates_require_three_points_for_this_month():
    # Only 2 weekday nights in September -> this-month stats stay blank.
    nightly = {
        dt.date(2026, 9, 7): 100.0,  # Monday
        dt.date(2026, 9, 8): 120.0,  # Tuesday
    }
    aggregates = compute_category_aggregates(nightly, holidays={})
    weekday_agg = aggregates["Weekday (Sun-Thu)"]
    assert weekday_agg.all_time_max == 120.0
    assert 9 not in weekday_agg.this_month_max


def test_aggregates_computed_with_three_or_more_points():
    nightly = {
        dt.date(2026, 9, 7): 100.0,
        dt.date(2026, 9, 8): 150.0,
        dt.date(2026, 9, 9): 200.0,
    }
    aggregates = compute_category_aggregates(nightly, holidays={})
    weekday_agg = aggregates["Weekday (Sun-Thu)"]
    assert weekday_agg.this_month_max[9] == 200.0
    assert weekday_agg.this_month_floor[9] == 100.0 + (150.0 - 100.0) * 0.5  # P25 of 3 pts


def test_holiday_dates_excluded_from_aggregate_population():
    nightly = {
        dt.date(2026, 12, 25): 999.0,  # Christmas -- excluded
        dt.date(2026, 12, 3): 100.0,
        dt.date(2026, 12, 10): 110.0,
        dt.date(2026, 12, 17): 120.0,
    }
    holidays = {"2026-12-25": "Christmas Day"}
    aggregates = compute_category_aggregates(nightly, holidays)
    weekday_agg = aggregates["Weekday (Sun-Thu)"]
    assert weekday_agg.all_time_max == 120.0


def _base_row(**overrides) -> DateRow:
    defaults = dict(
        date=dt.date(2026, 9, 14),
        day="Monday",
        category="Weekday (Sun-Thu)",
        current_price=100.0,
        ly_adr=None,
        ly2_adr=None,
        ly_market_occ=None,
        price_override="",
        override_reason="",
        airbnb_promo_price=None,
        discount_pct=None,
        weekday_max_this_month=200.0,
        weekday_max_all_time=250.0,
        weekday_floor_this_month=90.0,
        booked="No",
    )
    defaults.update(overrides)
    return DateRow(**defaults)


def test_flag_blank_when_booked():
    row = _base_row(booked="Yes", current_price=10000.0)
    assert flag_for_row(row) == ""


def test_flag_above_cap():
    row = _base_row(current_price=250.0)  # > 200 * 1.2 = 240
    assert flag_for_row(row) == "ABOVE +20% CAP"


def test_flag_below_typical():
    row = _base_row(current_price=50.0)  # < floor 90
    assert flag_for_row(row) == "BELOW TYPICAL"


def test_flag_blank_in_normal_range():
    row = _base_row(current_price=150.0)
    assert flag_for_row(row) == ""


def test_holiday_rows_never_flagged():
    row = _base_row(category="Holiday/Event", current_price=999999.0)
    assert flag_for_row(row) == ""
