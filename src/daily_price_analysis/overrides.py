"""Parse PriceLabs' date-overrides response into display rows."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class OverrideRow:
    date: dt.date
    price_override_display: str  # "+10%" / "-10%" / "$300 fixed" / ""
    price_sign: str  # "positive" / "negative" / "fixed" / "none"
    min_price: float | None
    max_price: float | None
    min_stay: int | None
    reason: str


def _format_price_override(raw: dict) -> tuple[str, str]:
    price = raw.get("price")
    if price in (None, ""):
        return "", "none"
    price_type = raw.get("price_type", "")
    try:
        value = float(price)
    except ValueError:
        return "", "none"
    if price_type == "percent":
        sign = "positive" if value >= 0 else "negative"
        display = f"{'+' if value >= 0 else ''}{value:g}%"
        return display, sign
    if price_type == "fixed":
        return f"${value:g} fixed", "fixed"
    return "", "none"


def parse_overrides(raw_rows: list[dict]) -> dict[dt.date, OverrideRow]:
    result = {}
    for row in raw_rows:
        try:
            d = dt.date.fromisoformat(row["date"])
        except (KeyError, ValueError):
            continue
        display, sign = _format_price_override(row)
        result[d] = OverrideRow(
            date=d,
            price_override_display=display,
            price_sign=sign,
            min_price=row.get("min_price"),
            max_price=row.get("max_price"),
            min_stay=row.get("min_stay"),
            reason=row.get("reason", "") or "",
        )
    return result
