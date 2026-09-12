"""Expand hand-maintained Promo Tracker rows into a per-date lookup.

The Promo Tracker tab is entered by hand (Airbnb custom-price promotions the
owner applies directly in Airbnb, separate from PriceLabs overrides) and is
preserved verbatim across reruns -- this module only builds the derived
per-date "Airbnb Promotion Price" / "Discount %" lookup used on the main
tabs; it never writes back to the tracker itself.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

_RANGE_RE = re.compile(r"(\d{1,2})/(\d{1,2})\s*to\s*(\d{1,2})/(\d{1,2})", re.IGNORECASE)
_DOLLAR_RANGE_RE = re.compile(r"\$?\s*([\d.]+)\s*-\s*\$?\s*([\d.]+)")


@dataclass(frozen=True)
class PromoRow:
    entered_date: dt.date | None
    date_applied_raw: object  # datetime.date or str
    discount_pct: float | None
    price_entered_raw: object  # number or "$210-$301" string


def _as_date(value) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return None


def _expand_date_applied(date_applied, reference_year: int) -> list[dt.date]:
    single = _as_date(date_applied)
    if single is not None:
        return [single]

    if not isinstance(date_applied, str):
        return []

    match = _RANGE_RE.search(date_applied)
    if not match:
        return []
    m1, d1, m2, d2 = (int(x) for x in match.groups())
    start = dt.date(reference_year, m1, d1)
    end_year = reference_year
    if (m2, d2) < (m1, d1):
        end_year += 1
    end = dt.date(end_year, m2, d2)

    dates = []
    d = start
    while d <= end:
        dates.append(d)
        d += dt.timedelta(days=1)
    return dates


def _average_price(price_entered) -> float | None:
    if isinstance(price_entered, (int, float)):
        return float(price_entered)
    if isinstance(price_entered, str):
        match = _DOLLAR_RANGE_RE.search(price_entered)
        if match:
            lo, hi = (float(x) for x in match.groups())
            return (lo + hi) / 2
        try:
            return float(price_entered.replace("$", "").strip())
        except ValueError:
            return None
    return None


def build_promo_lookup(promo_rows: list[PromoRow]) -> dict[dt.date, tuple[float | None, float | None]]:
    """Returns {date: (airbnb_promotion_price, discount_pct)}.

    Later rows in the tracker win on overlapping dates (last-applied wins),
    matching how a human re-reads the tracker top-to-bottom.
    """
    lookup: dict[dt.date, tuple[float | None, float | None]] = {}
    for row in promo_rows:
        reference_year = (row.entered_date or dt.date.today()).year
        dates = _expand_date_applied(row.date_applied_raw, reference_year)
        price = _average_price(row.price_entered_raw)
        for d in dates:
            lookup[d] = (price, row.discount_pct)
    return lookup
