import datetime as dt

from daily_price_analysis.promo import (
    PromoRow,
    build_promo_lookup,
    compute_airbnb_adjusted_price,
)


def test_single_date_promo():
    rows = [
        PromoRow(
            entered_date=dt.date(2026, 8, 26),
            date_applied_raw=dt.datetime(2026, 8, 26),
            discount_pct=0.52,
            price_entered_raw=181,
        )
    ]
    lookup = build_promo_lookup(rows)
    assert lookup[dt.date(2026, 8, 26)] == (181.0, 0.52)


def test_date_range_promo_uses_flat_discount_and_average_price():
    rows = [
        PromoRow(
            entered_date=dt.date(2026, 9, 10),
            date_applied_raw="9/13 to 9/17",
            discount_pct=0.20,
            price_entered_raw="$210-$301",
        )
    ]
    lookup = build_promo_lookup(rows)
    expected_price = (210 + 301) / 2
    for day in range(13, 18):
        d = dt.date(2026, 9, day)
        assert lookup[d] == (expected_price, 0.20)
    assert dt.date(2026, 9, 12) not in lookup
    assert dt.date(2026, 9, 18) not in lookup


def test_date_range_crossing_year_boundary():
    rows = [
        PromoRow(
            entered_date=dt.date(2026, 12, 28),
            date_applied_raw="12/30 to 1/2",
            discount_pct=0.25,
            price_entered_raw=300,
        )
    ]
    lookup = build_promo_lookup(rows)
    assert dt.date(2026, 12, 30) in lookup
    assert dt.date(2026, 12, 31) in lookup
    assert dt.date(2027, 1, 1) in lookup
    assert dt.date(2027, 1, 2) in lookup


def test_later_row_overrides_earlier_on_overlap():
    rows = [
        PromoRow(dt.date(2026, 9, 1), dt.datetime(2026, 9, 13), 0.10, 200),
        PromoRow(dt.date(2026, 9, 2), dt.datetime(2026, 9, 13), 0.30, 250),
    ]
    lookup = build_promo_lookup(rows)
    assert lookup[dt.date(2026, 9, 13)] == (250.0, 0.30)


def test_hyphen_date_range_matches_same_as_the_word_to():
    """Real-world entry style found in an actual user file: '9/15-9/17'
    instead of '9/13 to 9/17'. Both must expand identically.
    """
    rows = [
        PromoRow(
            entered_date=dt.date(2026, 9, 15),
            date_applied_raw="9/15-9/17",
            discount_pct=0.20,
            price_entered_raw="222-269",
        )
    ]
    lookup = build_promo_lookup(rows)
    expected_price = (222 + 269) / 2
    for day in (15, 16, 17):
        assert lookup[dt.date(2026, 9, day)] == (expected_price, 0.20)


def test_slash_separated_per_night_prices_are_averaged():
    """Real-world entry style: '215/202/281' for a 3-night range, not a
    '$lo-$hi' dash-range.
    """
    rows = [
        PromoRow(
            entered_date=dt.date(2026, 9, 15),
            date_applied_raw="9/15-9/17",
            discount_pct=0.20,
            price_entered_raw="222/269/250",
        )
    ]
    lookup = build_promo_lookup(rows)
    expected_price = (222 + 269 + 250) / 3
    for day in (15, 16, 17):
        assert lookup[dt.date(2026, 9, day)] == (expected_price, 0.20)


def test_airbnb_adjusted_price_handles_slash_separated_current_price():
    adjusted = compute_airbnb_adjusted_price("215/202/281")
    expected = round(((215 + 202 + 281) / 3) * 0.90, 2)
    assert adjusted == expected


def test_airbnb_adjusted_price_handles_plain_number():
    assert compute_airbnb_adjusted_price(280) == round(280 * 0.90, 2)


def test_airbnb_adjusted_price_none_when_unparseable():
    assert compute_airbnb_adjusted_price("?") is None
    assert compute_airbnb_adjusted_price(None) is None
