"""Reads Override Request/Notes from a reviewed Daily Pacing workbook and
pushes them to PriceLabs as date-specific percent price overrides.

Spec workflow:
  - skip blank Override Request cells and any date already in the past
  - push price_type "percent" to BOTH listings by default (Pace/Pickup are
    market-level signals shared by both listings, not listing-specific)
  - Notes text becomes the override's `reason` (max 255 chars)
  - dry-run by default: prints every planned change; only pushes for real
    behind an explicit --confirm flag

Safety note: PriceLabs bundles multiple settings (price, min_stay, min/max
price, check-in/out rules) into one override object per date, and the
update endpoint replaces a date's override wholesale rather than merging
field-by-field (confirmed against real account data: e.g. 2026-09-12's
override there carries price + min_stay + min_price together). So this
reads each listing's current override for every target date first and
merges price/price_type/reason on top of whatever's already set, rather
than sending a bare {date, price} object that would silently wipe the
rest. This means even a --dry-run makes read-only GET calls (to compute
an accurate preview) -- never a write.
"""

import argparse
from datetime import date

import openpyxl

from . import config
from .api_client import PriceLabsClient

REASON_MAX_LEN = 255

# 0-based column indices within the Daily Pacing sheet's row tuples.
COL_DATE, COL_OVERRIDE_REQUEST, COL_NOTES = 0, 16, 17


def _format_percent(fraction):
    """-0.1 -> "-10", 0.05 -> "5" -- matches how Override Request is
    entered (a decimal fraction, e.g. -0.1 for -10%) and how PriceLabs'
    own API stores a percent override's price (a plain percentage number,
    confirmed against a real existing override: {"price": "-10",
    "price_type": "percent"}).
    """
    value = round(fraction * 100, 2)
    if value == int(value):
        return str(int(value))
    return str(value)


def read_planned_overrides(workbook_path, as_of=None):
    """[{"date": "YYYY-MM-DD", "price": "-10", "reason": "..."}] for every
    row with a non-blank Override Request whose date is today or later.
    """
    as_of = as_of or date.today()
    wb = openpyxl.load_workbook(workbook_path, data_only=True)
    ws = wb["Daily Pacing"]
    planned = []
    for row in ws.iter_rows(min_row=2):
        override_request = row[COL_OVERRIDE_REQUEST].value
        if override_request in (None, ""):
            continue
        row_date = row[COL_DATE].value
        if row_date is None:
            continue
        row_date = row_date.date() if hasattr(row_date, "date") else row_date
        if row_date < as_of:
            continue
        notes = row[COL_NOTES].value or ""
        planned.append(
            {
                "date": row_date.isoformat(),
                "price": _format_percent(float(override_request)),
                "reason": str(notes)[:REASON_MAX_LEN],
            }
        )
    return planned


def _merge_override(existing, target_date, price, reason):
    """Keeps every field already set on this date's override (min_stay,
    min/max price, check-in/out rules, etc.) and only replaces
    price/price_type/reason.
    """
    merged = dict(existing) if existing else {}
    merged.pop("created_at", None)
    merged.pop("updated_at", None)
    merged["date"] = target_date
    merged["price"] = price
    merged["price_type"] = "percent"
    merged["reason"] = reason
    return merged


def push_overrides(client, planned, listings=None, dry_run=True):
    """Returns [(listing_name, override_dict), ...] -- what was (dry_run)
    or would be (not dry_run) sent, for the caller to print/log. Read-only
    GET calls happen either way, to compute an accurate merge preview;
    the mutating call only happens when dry_run is False.
    """
    listings = listings if listings is not None else config.LISTINGS
    planned_by_date = {p["date"]: p for p in planned}
    results = []

    for listing in listings:
        if not planned_by_date:
            continue

        existing_resp = client.get_listing_date_overrides(listing["listing_id"], listing["pms"])
        existing_payload = existing_resp.get("data", existing_resp)
        existing_by_date = {row["date"]: row for row in existing_payload.get("overrides", [])}

        overrides_to_send = []
        for target_date, plan in planned_by_date.items():
            merged = _merge_override(existing_by_date.get(target_date), target_date, plan["price"], plan["reason"])
            overrides_to_send.append(merged)
            results.append((listing["name"], merged))

        if overrides_to_send and not dry_run:
            client.update_listing_date_overrides(listing["listing_id"], listing["pms"], overrides_to_send)

    return results


def main():
    parser = argparse.ArgumentParser(description="Push reviewed Override Request/Notes to PriceLabs.")
    parser.add_argument("--workbook", required=True, help="Path to the reviewed Daily Pacing xlsx")
    parser.add_argument(
        "--listing-id",
        default=None,
        help="Restrict the push to one configured listing_id (defaults to all listings)",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually call the PriceLabs API. Without this flag, only prints what would be pushed.",
    )
    args = parser.parse_args()

    listings = config.LISTINGS
    if args.listing_id:
        listings = [listing for listing in config.LISTINGS if listing["listing_id"] == args.listing_id]
        if not listings:
            raise SystemExit(f"No configured listing with listing_id={args.listing_id!r}")

    planned = read_planned_overrides(args.workbook)
    if not planned:
        print("No overrides to push (Override Request is blank for every row, or all such dates are in the past).")
        return

    client = PriceLabsClient()
    results = push_overrides(client, planned, listings=listings, dry_run=not args.confirm)

    mode = "LIVE PUSH" if args.confirm else "DRY RUN -- nothing was sent; pass --confirm to push for real"
    print(f"=== {mode}: {len(results)} override(s) across {len(listings)} listing(s) ===")
    for listing_name, override in results:
        print(f"{listing_name} | {override['date']} | price={override['price']}% | reason={override['reason']!r}")


if __name__ == "__main__":
    main()
