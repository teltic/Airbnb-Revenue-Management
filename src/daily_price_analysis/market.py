"""Parse PriceLabs' neighborhood/market-data response into a per-date table.

See PriceLabsClient.get_neighborhood_data for the verified raw shape. This
module flattens it into `{date: MarketDay}` plus the comp-set summary used
by the Compset Overview tab.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class MarketDay:
    p25: float | None
    p50: float | None
    p75: float | None
    p90: float | None
    occupancy_stly: float | None


@dataclass(frozen=True)
class CompsetInfo:
    source_label: str
    category_name: str
    listings_used: int | None


OCC_LABELS = [
    "Occupancy",
    "New Bookings",
    "Canceled Bookings",
    "Occupancy_LY",
    "Occupancy_STLY",
    "New_Bookings_STLY",
]
PRICE_LABELS = [
    "25th Percentile",
    "50th Percentile",
    "75th Percentile",
    "Median Booked Price",
    "90th Percentile",
    "N_bookings",
]


def _first_category(section: dict) -> tuple[str, dict] | tuple[None, None]:
    categories = section.get("Category", {})
    if not categories:
        return None, None
    name = next(iter(categories))
    return name, categories[name]


def parse_market_data(raw: dict) -> tuple[dict[dt.date, MarketDay], CompsetInfo]:
    occ_section = raw.get("Future Occ/New/Canc", {})
    price_section = raw.get("Future Percentile Prices", {})

    occ_cat_name, occ_cat = _first_category(occ_section)
    price_cat_name, price_cat = _first_category(price_section)

    occ_by_date: dict[str, float] = {}
    if occ_cat:
        x_values = occ_cat.get("X_values", [])
        y_values = occ_cat.get("Y_values", [])
        stly_idx = OCC_LABELS.index("Occupancy_STLY")
        if len(y_values) > stly_idx:
            occ_by_date = dict(zip(x_values, y_values[stly_idx]))

    price_by_date: dict[str, tuple] = {}
    if price_cat:
        x_values = price_cat.get("X_values", [])
        y_values = price_cat.get("Y_values", [])
        if len(y_values) >= 4:
            p25, p50, p75, _median, p90 = y_values[0], y_values[1], y_values[2], y_values[3], y_values[4]
            for i, date_str in enumerate(x_values):
                price_by_date[date_str] = (p25[i], p50[i], p75[i], p90[i])

    all_dates = set(occ_by_date) | set(price_by_date)
    result: dict[dt.date, MarketDay] = {}
    for date_str in all_dates:
        p25, p50, p75, p90 = price_by_date.get(date_str, (None, None, None, None))
        result[dt.date.fromisoformat(date_str)] = MarketDay(
            p25=p25,
            p50=p50,
            p75=p75,
            p90=p90,
            occupancy_stly=occ_by_date.get(date_str),
        )

    listings_used = None
    if price_cat is not None:
        listings_used = price_cat.get("Listings Used")
    elif occ_cat is not None:
        listings_used = occ_cat.get("Listings Used")

    compset = CompsetInfo(
        source_label=raw.get("Neighborhood Data Source", ""),
        category_name=price_cat_name or occ_cat_name or "",
        listings_used=listings_used,
    )
    return result, compset


def market_percentile_bucket(price: float | None, day: MarketDay | None) -> str:
    if price is None or day is None or day.p25 is None:
        return ""
    if price < day.p25:
        return "<25th"
    if price < day.p50:
        return "25th-50th"
    if price < day.p75:
        return "50th-75th"
    if price < day.p90:
        return "75th-90th"
    return ">90th"
