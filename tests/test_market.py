import datetime as dt

from daily_price_analysis.market import parse_market_data


def test_single_category_used_directly():
    raw = {
        "Neighborhood Data Source": "Market Dashboard: ABB Comp: Sleep 10 or more with pool",
        "Future Occ/New/Canc": {
            "Category": {
                "Sleep 10 or more with pool": {
                    "Listings Used": 7,
                    "X_values": ["2026-09-14"],
                    "Y_values": [[50], [0], [0], [50], [66.6], [3]],
                }
            }
        },
        "Future Percentile Prices": {
            "Category": {
                "Sleep 10 or more with pool": {
                    "Listings Used": 7,
                    "X_values": ["2026-09-14"],
                    "Y_values": [[200], [250], [300], [225], [350], [7]],
                }
            }
        },
    }
    market, compset = parse_market_data(raw)
    day = market[dt.date(2026, 9, 14)]
    assert (day.p25, day.p50, day.p75, day.p90) == (200, 250, 300, 350)
    assert compset.listings_used == 7
    assert compset.category_name == "Sleep 10 or more with pool"
    assert compset.notes == ""


def test_multi_category_picks_largest_and_sums_total():
    raw = {
        "Neighborhood Data Source": "Nearby Listings",
        "Future Occ/New/Canc": {"Category": {}},
        "Future Percentile Prices": {
            "Category": {
                "3": {
                    "Listings Used": 1,
                    "X_values": ["2026-09-14"],
                    "Y_values": [[400], [400], [400], [400], [400], [1]],
                },
                "5": {
                    "Listings Used": 118,
                    "X_values": ["2026-09-14"],
                    "Y_values": [[200], [250], [300], [225], [350], [50]],
                },
            }
        },
    }
    market, compset = parse_market_data(raw)
    day = market[dt.date(2026, 9, 14)]
    # Must use the 118-listing bucket's real spread, not the 1-listing
    # bucket where every percentile is identical.
    assert (day.p25, day.p50, day.p75, day.p90) == (200, 250, 300, 350)
    assert compset.listings_used == 119
    assert "5" in compset.category_name
    assert "2 bedroom-count segments" in compset.notes


def test_percentiles_rounded_to_avoid_float_noise():
    raw = {
        "Neighborhood Data Source": "x",
        "Future Occ/New/Canc": {"Category": {}},
        "Future Percentile Prices": {
            "Category": {
                "A": {
                    "Listings Used": 1,
                    "X_values": ["2026-09-14"],
                    "Y_values": [[267.5], [340], [368.5], [331.5], [431.80000000000007], [3]],
                }
            }
        },
    }
    market, _ = parse_market_data(raw)
    day = market[dt.date(2026, 9, 14)]
    assert day.p90 == 431.8
