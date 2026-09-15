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
from .bookings import fetch_reservations_verified, nightly_adr_series
from .compute import build_date_rows, compute_category_aggregates, ly_ly2_series
from .calendar import parse_calendar
from .dated_output import resolve_output_paths
from .market import parse_market_data
from .overrides import parse_overrides
from .pricelabs_client import PriceLabsAPIError, PriceLabsClient
from .promo import PromoRow, build_promo_lookup
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


def _promo_rows_from_raw(raw_rows: list[list]) -> list[PromoRow]:
    parsed = []
    for values in raw_rows:
        values = list(values) + [None] * (9 - len(values))
        parsed.append(
            PromoRow(
                entered_date=values[0].date() if isinstance(values[0], dt.datetime) else values[0],
                date_applied_raw=values[1],
                discount_pct=values[5],
                price_entered_raw=values[4],
            )
        )
    return parsed


def _recompute_promo_override_lookup(raw_rows: list[list], overrides: dict) -> list[list]:
    updated = []
    for values in raw_rows:
        values = list(values) + [None] * (9 - len(values))
        date_applied = values[1]
        single_date = date_applied.date() if isinstance(date_applied, dt.datetime) else (
            date_applied if isinstance(date_applied, dt.date) else None
        )
        override = overrides.get(single_date) if single_date else None
        values[7] = override.price_override_display if override else None
        values[8] = override.reason if override else None
        updated.append(values)
    return updated


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
        aggregates = compute_category_aggregates(nightly_adr, holidays)
        ly_series, ly2_series = ly_ly2_series(nightly_adr, display_dates)

        calendar = _fetch_full_calendar(client, listing, days)
        raw_market = client.get_neighborhood_data(listing.listing_id, listing.pms)
        market, compset = parse_market_data(raw_market)
        raw_overrides = client.get_overrides(listing.listing_id, listing.pms)
        overrides = parse_overrides(raw_overrides)

        promo_rows = _promo_rows_from_raw(preserved_promo_rows)
        promo_lookup = build_promo_lookup(promo_rows)

        rows = build_date_rows(
            display_dates,
            calendar,
            market,
            ly_series,
            ly2_series,
            holidays,
            overrides,
            promo_lookup,
            aggregates,
        )

        for row in rows:
            if row.date in preserved_notes:
                row.note_date, row.note = preserved_notes[row.date]

        updated_promo_rows = _recompute_promo_override_lookup(preserved_promo_rows, overrides)

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
