"""Pulls occupancy/pace/pickup data for both listings, blends them into one
portfolio-level daily record per the next FORECAST_DAYS days, and writes an
intermediate JSON file that the (separate) Excel-generation stage consumes.

Data sources (PriceLabs Customer API):
  - neighborhood_data: per-listing daily Market Occupancy / LY / STLY curve.
  - reservation_data: per-listing actual reservations, used to derive whether
    a given date is booked for that listing.
  - local snapshot cache (snapshot_cache.py): today's Market Occupancy curve
    is recorded here so pickup (change vs N days ago) can be computed once
    enough history has accumulated.
"""

import argparse
import json
import logging
import os
from datetime import date, datetime, timedelta

from . import config
from .api_client import PriceLabsAPIError, PriceLabsClient
from .snapshot_cache import SnapshotStore

logger = logging.getLogger(__name__)


def _date_range(start, days):
    return [(start + timedelta(days=i)) for i in range(days)]


def _select_category(categories, listing_id):
    """neighborhood_data groups curves under a comp-set "Category" name.
    Most accounts have exactly one auto-selected category; if there's more
    than one we pick the one with the most listings used and warn, since we
    have no per-listing config for which category to prefer.
    """
    if not categories:
        return None, None
    if len(categories) == 1:
        name = next(iter(categories))
        return name, categories[name]
    name = max(categories, key=lambda k: categories[k].get("Listings Used", 0))
    logger.warning(
        "Listing %s has %d neighborhood_data categories (%s); picking %r by Listings Used. "
        "Set a category override in config.py if this is wrong.",
        listing_id,
        len(categories),
        list(categories.keys()),
        name,
    )
    return name, categories[name]


def _parse_occupancy_curve(neighborhood_response):
    """Returns {date_str: {"occ": x, "occ_ly": y, "occ_stly": z}} from a
    neighborhood_data response, or {} if the shape doesn't match.
    """
    payload = neighborhood_response.get("data", neighborhood_response)
    occ_block = payload.get("Future Occ/New/Canc", {})
    categories = occ_block.get("Category", {})
    _, cat = _select_category(categories, payload.get("listing_id", "?"))
    if not cat:
        return {}

    labels = occ_block.get("Labels", [])
    try:
        occ_idx = labels.index("Occupancy")
        occ_ly_idx = labels.index("Occupancy_LY")
        occ_stly_idx = labels.index("Occupancy_STLY")
    except ValueError:
        logger.warning("neighborhood_data Labels missing expected fields: %s", labels)
        return {}

    x_values = cat.get("X_values", [])
    y_values = cat.get("Y_values", [])
    curve = {}
    for i, date_str in enumerate(x_values):
        try:
            curve[date_str] = {
                "occ": y_values[occ_idx][i],
                "occ_ly": y_values[occ_ly_idx][i],
                "occ_stly": y_values[occ_stly_idx][i],
            }
        except IndexError:
            continue
    return curve


def _fetch_all_reservations(client, pms, listing_id, start_date, end_date):
    """reservation_data may be paginated; keep pulling until next_page is
    falsy. We only need check_in/check_out/booking_status.
    """
    all_rows = []
    limit = 500
    offset = 0
    while True:
        resp = client.get_reservations(
            pms=pms,
            start_date=start_date,
            end_date=end_date,
            listing_id=listing_id,
            limit=limit,
            offset=offset,
        )
        rows, next_page = _extract_reservation_rows(resp)
        all_rows.extend(rows)
        if not next_page or not rows:
            break
        offset += limit
    return all_rows


def _extract_reservation_rows(resp):
    """reservation_data's "data" field can apparently be either the row
    list directly (with next_page/pagination info as a sibling of "data"),
    or a nested object like {"data": [...], "next_page": ...} -- handle
    both rather than assuming one.
    """
    data_field = resp.get("data", resp)
    if isinstance(data_field, list):
        return data_field, bool(resp.get("next_page"))
    if isinstance(data_field, dict):
        return data_field.get("data", []), bool(data_field.get("next_page"))
    raise PriceLabsAPIError(f"Unexpected reservation_data response shape: {resp!r}")


def _booked_dates(reservations):
    """Set of ISO date strings occupied by a non-cancelled reservation.
    check_out is exclusive (the night of check_out itself is not occupied).
    """
    booked = set()
    for res in reservations:
        if res.get("booking_status") != "booked":
            continue
        check_in = datetime.strptime(res["check_in"], "%Y-%m-%d").date()
        check_out = datetime.strptime(res["check_out"], "%Y-%m-%d").date()
        d = check_in
        while d < check_out:
            booked.add(d.isoformat())
            d += timedelta(days=1)
    return booked


def pull_listing_data(client, snapshot_store, listing, pull_date, window_dates):
    listing_id = listing["listing_id"]
    pms = listing["pms"]
    window_date_strs = [d.isoformat() for d in window_dates]

    neighborhood_resp = client.get_neighborhood_data(listing_id, pms)
    curve = _parse_occupancy_curve(neighborhood_resp)

    reservations = _fetch_all_reservations(
        client, pms, listing_id, window_date_strs[0], window_date_strs[-1]
    )
    booked = _booked_dates(reservations)

    today_snapshot = {d: curve[d]["occ"] for d in window_date_strs if d in curve}
    snapshot_store.record_snapshot(listing_id, pms, pull_date, today_snapshot)

    per_date = {}
    for d in window_date_strs:
        c = curve.get(d, {})
        pickups = {}
        for w in config.PICKUP_WINDOWS_DAYS:
            pickups[w] = snapshot_store.get_pickup(listing_id, pms, pull_date, d, w)
        per_date[d] = {
            "occupancy_pct": 100.0 if d in booked else 0.0,
            "market_occ": c.get("occ"),
            "market_occ_ly": c.get("occ_ly"),
            "market_occ_stly": c.get("occ_stly"),
            "pickup": pickups,
        }
    return per_date


def _avg(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def blend_listings(per_listing_data, window_dates):
    """Average each field across all configured listings for a given date,
    per spec's "portfolio-level, both listings blended" behavior.
    """
    records = []
    for d in window_dates:
        d_str = d.isoformat()
        day_rows = [pl[d_str] for pl in per_listing_data]
        pickup_blended = {}
        for w in config.PICKUP_WINDOWS_DAYS:
            pickup_blended[w] = _avg([row["pickup"][w] for row in day_rows])
        records.append(
            {
                "date": d_str,
                "weekday": d.strftime("%a"),
                "occupancy_pct": _avg([row["occupancy_pct"] for row in day_rows]),
                "market_occ_pct": _avg([row["market_occ"] for row in day_rows]),
                "market_occ_pct_ly": _avg([row["market_occ_ly"] for row in day_rows]),
                "market_occ_pct_stly": _avg([row["market_occ_stly"] for row in day_rows]),
                "pickup_3d": pickup_blended[3],
                "pickup_7d": pickup_blended[7],
                "pickup_14d": pickup_blended[14],
                "pickup_30d": pickup_blended[30],
                "pickup_60d": pickup_blended[60],
            }
        )
    return records


def run_pull(client, snapshot_store, pull_date=None, forecast_days=None, listings=None):
    pull_date = pull_date or date.today().isoformat()
    forecast_days = forecast_days or config.FORECAST_DAYS
    listings = listings or config.LISTINGS

    start = datetime.strptime(pull_date, "%Y-%m-%d").date()
    window_dates = _date_range(start, forecast_days)

    per_listing_data = []
    for listing in listings:
        logger.info("Pulling data for %s (%s/%s)", listing["name"], listing["pms"], listing["listing_id"])
        per_listing_data.append(
            pull_listing_data(client, snapshot_store, listing, pull_date, window_dates)
        )

    return blend_listings(per_listing_data, window_dates)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Pull PriceLabs pacing/pickup data.")
    parser.add_argument("--pull-date", default=None, help="YYYY-MM-DD, defaults to today")
    parser.add_argument("--forecast-days", type=int, default=None)
    parser.add_argument(
        "--out",
        default=None,
        help="Output JSON path; defaults to data/pull_<pull_date>.json",
    )
    args = parser.parse_args()

    client = PriceLabsClient()
    snapshot_store = SnapshotStore()

    records = run_pull(client, snapshot_store, pull_date=args.pull_date, forecast_days=args.forecast_days)

    pull_date = args.pull_date or date.today().isoformat()
    out_path = args.out or os.path.join("data", f"pull_{pull_date}.json")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(records, f, indent=2)
    logger.info("Wrote %d daily records to %s", len(records), out_path)


if __name__ == "__main__":
    main()
