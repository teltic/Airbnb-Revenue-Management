import datetime as dt

from daily_price_analysis.compute import (
    DEFAULT_BOOKING_WINDOW_DAYS,
    DateRow,
    build_date_rows,
    flag_for_row,
    in_booking_window,
    ly_series_for_dates,
)


def _base_row(**overrides) -> DateRow:
    defaults = dict(
        date=dt.date(2026, 9, 14),
        day="Monday",
        category="Weekday (Sun-Thu)",
        current_price=300.0,
        ly_market_occ=None,
        market_occupancy_pct=None,
        in_booking_window="Yes",
        price_override="",
        override_reason="",
        airbnb_promo_price=None,
        discount_pct=None,
        market_p25=200.0,
        market_p50=250.0,
        market_p75=300.0,
        market_p90=350.0,
        ly_price=None,
        booked="No",
    )
    defaults.update(overrides)
    return DateRow(**defaults)


def test_in_booking_window_uses_property_specific_window():
    today = dt.date(2026, 9, 14)
    assert in_booking_window(today + dt.timedelta(days=10), today, 20) == "Yes"
    assert in_booking_window(today + dt.timedelta(days=30), today, 20) == "No"


def test_in_booking_window_falls_back_to_default_when_unavailable():
    today = dt.date(2026, 9, 14)
    within_default = today + dt.timedelta(days=DEFAULT_BOOKING_WINDOW_DAYS - 1)
    beyond_default = today + dt.timedelta(days=DEFAULT_BOOKING_WINDOW_DAYS + 1)
    assert in_booking_window(within_default, today, None) == "Yes"
    assert in_booking_window(beyond_default, today, None) == "No"


def test_flag_blank_when_booked():
    row = _base_row(booked="Yes", market_occupancy_pct=95, current_price=1000.0)
    assert flag_for_row(row) == ("", "")


def test_flag_blank_on_holiday_even_with_extreme_occupancy():
    row = _base_row(category="Holiday/Event", market_occupancy_pct=95, current_price=1000.0)
    assert flag_for_row(row) == ("", "")


def test_weekday_low_occupancy_and_price_above_25th_flags_above_target():
    # occ 20% < 30% threshold, price 300 sits above the 25th percentile (200)
    row = _base_row(category="Weekday (Sun-Thu)", market_occupancy_pct=20, current_price=300.0)
    text, color = flag_for_row(row)
    assert text == "ABOVE TARGET (weak weekday demand)"
    assert color == "salmon"


def test_weekday_low_occupancy_but_price_already_at_bottom_bucket_no_flag():
    # price 150 is below the 25th percentile (200) -- already at/below target.
    row = _base_row(category="Weekday (Sun-Thu)", market_occupancy_pct=20, current_price=150.0)
    assert flag_for_row(row) == ("", "")


def test_weekend_uses_its_own_40pct_threshold():
    row = _base_row(category="Weekend (Fri/Sat)", market_occupancy_pct=35, current_price=300.0)
    text, color = flag_for_row(row)
    assert text == "ABOVE TARGET (weak weekend demand)"
    assert color == "salmon"

    # 35% occupancy would NOT trigger the weekday rule (needs < 30%).
    weekday_row = _base_row(category="Weekday (Sun-Thu)", market_occupancy_pct=35, current_price=300.0)
    assert flag_for_row(weekday_row) == ("", "")


def test_high_occupancy_and_price_below_90th_flags_below_target():
    # occ 85% >= 80% threshold, price 300 sits below the 90th percentile (350)
    row = _base_row(market_occupancy_pct=85, current_price=300.0)
    text, color = flag_for_row(row)
    assert text == "BELOW TARGET (strong demand, price too low)"
    assert color == "green"


def test_high_occupancy_but_already_above_90th_no_flag():
    row = _base_row(market_occupancy_pct=85, current_price=400.0)  # above p90=350
    assert flag_for_row(row) == ("", "")


def test_moderate_occupancy_no_primary_flag():
    row = _base_row(market_occupancy_pct=50, current_price=300.0)
    assert flag_for_row(row) == ("", "")


def test_occupancy_rule_gated_by_booking_window():
    row = _base_row(in_booking_window="No", market_occupancy_pct=90, current_price=200.0)
    assert flag_for_row(row) == ("", "")


def test_ly_mismatch_flags_when_price_much_higher():
    row = _base_row(
        market_occupancy_pct=50,  # no primary flag
        current_price=300.0,
        ly_price=200.0,  # +50%, past the 20% threshold
    )
    text, color = flag_for_row(row)
    assert text == "LY MISMATCH (was $200, now $300)"
    assert color == "green"


def test_ly_mismatch_flags_when_price_much_lower():
    row = _base_row(market_occupancy_pct=50, current_price=150.0, ly_price=250.0)
    text, color = flag_for_row(row)
    assert text == "LY MISMATCH (was $250, now $150)"
    assert color == "salmon"


def test_ly_mismatch_within_threshold_no_flag():
    row = _base_row(market_occupancy_pct=50, current_price=210.0, ly_price=200.0)  # +5%
    assert flag_for_row(row) == ("", "")


def test_ly_mismatch_runs_even_outside_booking_window():
    row = _base_row(
        in_booking_window="No",
        market_occupancy_pct=90,  # would flag BELOW TARGET if the gate didn't apply
        current_price=300.0,
        ly_price=200.0,
    )
    text, color = flag_for_row(row)
    assert text == "LY MISMATCH (was $200, now $300)"
    assert color == "green"


def test_primary_flag_takes_priority_over_ly_mismatch():
    row = _base_row(market_occupancy_pct=20, current_price=300.0, ly_price=100.0)
    text, _color = flag_for_row(row)
    assert text == "ABOVE TARGET (weak weekday demand)"


def test_ly_series_for_dates_maps_same_calendar_date_last_year():
    nightly = {dt.date(2025, 9, 14): 275.0}
    dates = [dt.date(2026, 9, 14), dt.date(2026, 9, 15)]
    ly = ly_series_for_dates(nightly, dates)
    assert ly == {dt.date(2026, 9, 14): 275.0}


def test_build_date_rows_end_to_end_smoke():
    from daily_price_analysis.calendar import CalendarDay

    today = dt.date(2026, 9, 14)
    dates = [today, today + dt.timedelta(days=1)]
    calendar = {
        today: CalendarDay(price=300.0, min_stay=1, booked=False),
        dates[1]: CalendarDay(price=300.0, min_stay=1, booked=True),
    }
    rows = build_date_rows(
        dates,
        today,
        calendar,
        market={},
        ly_series={},
        booking_window_days=45,
        holidays={},
        overrides={},
        promo_lookup={},
    )
    assert len(rows) == 2
    assert rows[0].booked == "No"
    assert rows[1].booked == "Yes"
    assert rows[1].flag == ""  # booked rows never flag
