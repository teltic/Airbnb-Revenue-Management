"""CLI entrypoint: pull live PriceLabs data for every configured listing and
(re)generate the "Daily Low & High Price Analysis" workbook.

Usage:
    python -m daily_price_analysis.main [--output PATH | --output-dir DIR]
        [--days N] [--bookings-csv PATH] [--listings-config PATH]

Safe to rerun repeatedly (daily, weekly, whatever cadence you want): Notes
and the Promo Tracker tabs are read back out of a prior output file before
the new one is written, then spliced into the freshly-generated data by
exact date match. Active Overrides tabs are always fully refreshed from
the API.

Two output modes:
- `--output PATH` (default): always overwrite the same fixed file in
  place, reading Notes/Promo back out of that same file first.
- `--output-dir DIR`: write a new dated snapshot into DIR each run
  ('Daily Low & High Price Analysis - YYYY-MM-DD.xlsx'), reading
  Notes/Promo forward from the most recent earlier-dated file already in
  DIR. Use this for a running daily/weekly archive instead of one file
  that keeps getting overwritten.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

from . import config as cfg
from .bookings import (
    fetch_reservations_verified,
    median_booking_window_days,
    nightly_adr_series,
)
from .compute import build_date_rows, ly_series_for_dates
from .calendar import parse_calendar
from .dated_output import resolve_output_paths
from .market import parse_market_data
from .overrides import parse_overrides
from .pricelabs_client import PriceLabsAPIError, PriceLabsClient
from .promo import PromoRow, build_promo_lookup, build_promo_output_rows
from .workbook_build import (
    build_compset_sheet,
    build_how_this_works_sheet,
    build_overrides_sheet,
    build_promo_sheet,
    build_property_sheet,
    new_workbook,
)
from .workbook_state import load_preserved_notes, load_promo_tab_rows

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_OUTPUT = cfg.REPO_ROOT / "output" / "Daily Low & High Price Analysis.xlsx"
CALENDAR_CHUNK_DAYS = 90


def _fetch_full_calendar(client: PriceLabsClient, listing: cfg.Listing, days: int) -> dict:
    today = dt.date.today()
    end = today + dt.timedelta(days=days)
    merged: dict = {}
    chunk_start = today
    while chunk_start < end:
        chunk_end = min(chunk_start + dt.timedelta(days=CALENDAR_CHUNK_DAYS), end)
        rows = client.get_listing_prices(
            listing.listing_id,
            listing.pms,
            chunk_start.isoformat(),
            chunk_end.isoformat(),
        )
        merged.update(parse_calendar(rows))
        chunk_start = chunk_end
    return merged


def _promo_rows_from_raw(raw_rows: list[dict]) -> list[PromoRow]:
    parsed = []
    for row in raw_rows:
        entered_date = row.get("Entered Date")
        parsed.append(
            PromoRow(
                entered_date=entered_date.date() if isinstance(entered_date, dt.datetime) else entered_date,
                date_applied_raw=row.get("Date Applied"),
                discount_pct=row.get("Discount %"),
                price_entered_raw=row.get("Price Entered"),
            )
        )
    return parsed


def run(
    output_path: Path,
    days: int,
    bookings_csv: str | None,
    listings_config: Path | None,
    output_dir: Path | None = None,
) -> None:
    listings = cfg.load_listings(listings_config)
    holidays = cfg.load_holidays()
    api_key = cfg.get_api_key()
    client = PriceLabsClient(api_key)

    today = dt.date.today()
    write_path, preserve_source_path = resolve_output_paths(output_dir, output_path, today)
    if output_dir is not None:
        if preserve_source_path is None:
            logger.info("No prior dated workbook found in %s -- starting fresh.", output_dir)
        else:
            logger.info("Carrying forward Notes/Promo data from %s", preserve_source_path)

    wb = new_workbook()
    compset_entries = []
    per_listing_results = []

    display_dates = [today + dt.timedelta(days=i) for i in range(days)]

    for listing in listings:
        logger.info("Processing %s (%s / %s)", listing.name, listing.pms, listing.listing_id)

        if preserve_source_path is not None:
            preserved_notes = load_preserved_notes(preserve_source_path, listing.tab_name)
            preserved_promo_rows = load_promo_tab_rows(preserve_source_path, listing.promo_tab_name)
        else:
            preserved_notes = {}
            preserved_promo_rows = []

        reservations = fetch_reservations_verified(
            client,
            pms=listing.pms,
            listing_id=listing.listing_id,
            listing_name=listing.name,
            fallback_csv_path=bookings_csv,
        )

        nightly_adr = nightly_adr_series(reservations)
        ly_series = ly_series_for_dates(nightly_adr, display_dates)
        booking_window_days = median_booking_window_days(reservations)
        logger.info(
            "%s: booking window = %s days (%s)",
            listing.name,
            round(booking_window_days) if booking_window_days is not None else "unavailable",
            "this property's own reservation history"
            if booking_window_days is not None
            else "falling back to default",
        )

        calendar = _fetch_full_calendar(client, listing, days)
        raw_market = client.get_neighborhood_data(listing.listing_id, listing.pms)
        market, compset = parse_market_data(raw_market)
        raw_overrides = client.get_overrides(listing.listing_id, listing.pms)
        overrides = parse_overrides(raw_overrides)

        promo_rows = _promo_rows_from_raw(preserved_promo_rows)
        promo_lookup = build_promo_lookup(promo_rows)

        rows = build_date_rows(
            display_dates,
            today,
            calendar,
            market,
            ly_series,
            booking_window_days,
            holidays,
            overrides,
            promo_lookup,
        )

        for row in rows:
            if row.date in preserved_notes:
                row.note_date, row.note = preserved_notes[row.date]

        updated_promo_rows = build_promo_output_rows(preserved_promo_rows, overrides)

        per_listing_results.append((listing, rows, updated_promo_rows, overrides))
        compset_entries.append((listing.name, compset))

    # Tabs are built in three separate passes (rather than interleaved
    # per-listing) so the workbook's sheet order matches the spec: every
    # property tab, then every Promo tab, then every Overrides tab.
    for listing, rows, _promo_rows, _overrides in per_listing_results:
        build_property_sheet(wb, listing.tab_name, rows)
    for listing, _rows, promo_rows, _overrides in per_listing_results:
        build_promo_sheet(wb, listing.promo_tab_name, promo_rows)
    for listing, _rows, _promo_rows, overrides in per_listing_results:
        build_overrides_sheet(wb, listing.overrides_tab_name, overrides)

    build_compset_sheet(wb, compset_entries)
    build_how_this_works_sheet(wb)

    write_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(write_path)
    except PermissionError as exc:
        raise SystemExit(
            f"Could not write {write_path} -- it's most likely open in Excel "
            f"(or another program) right now, which locks the file. Close it "
            f"and run this again."
        ) from exc
    logger.info("Saved %s", write_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Write a dated snapshot ('Daily Low & High Price Analysis - "
        "YYYY-MM-DD.xlsx') into this folder instead of overwriting a single "
        "file. Each run carries Notes/Promo data forward from the most "
        "recent earlier-dated file already in the folder. Overrides --output.",
    )
    parser.add_argument("--days", type=int, default=365, help="Forward window length, in days.")
    parser.add_argument(
        "--bookings-csv",
        type=str,
        default=None,
        help="Manual reservations-history CSV to fall back to if the API "
        "reservation pull looks truncated.",
    )
    parser.add_argument("--listings-config", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        run(args.output, args.days, args.bookings_csv, args.listings_config, args.output_dir)
    except PriceLabsAPIError as exc:
        logger.error(str(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
