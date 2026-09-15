"""Historical bookings/reservations: fetch via API, verify it's not
truncated, and fall back to a manually-exported CSV if it is.

Known gotcha (from the original hand-built version of this tool): a
reservations API call with explicit date-range filters returned only ~18
recent rows while the equivalent unfiltered CSV export from the PriceLabs
web dashboard returned 340 rows going back to 2024. Re-tested live against
the directly-authenticated v1 API on 2026-09-14/15 across two real
listings: one returned full multi-year history correctly; the other
("Sauna Cold Plunge 5BR") looked identically thin via both the API *and*
a manually-exported CSV covering the same window -- meaning that listing
is just young, not hitting the truncation bug.

Given that, `fetch_reservations_verified` can't reliably tell "genuinely
new listing" apart from "API silently truncated" using row count/date
span alone. Since this script is meant to run unattended on a daily
schedule, it no longer hard-stops on suspiciously thin data when no CSV
fallback is configured -- it logs a clear warning and proceeds with
whatever the API returned (the LY price lookup and this property's own
booking-window figure may just be incomplete, which is expected for a
young listing). A `--bookings-csv` fallback is still fully supported and
used automatically if you do have a fuller manual export to backfill with.
"""

from __future__ import annotations

import csv
import datetime as dt
import logging
import statistics
from dataclasses import dataclass

from .pricelabs_client import PriceLabsClient

logger = logging.getLogger(__name__)

CSV_COLUMNS = [
    "Listing Name",
    "Check-in Date",
    "Check-out Date",
    "Booked Date",
    "Average Daily Rate",
    "Rental Revenue",
    "Total Revenue",
    "Currency",
    "Booking Source",
    "Booking Status",
]

CANCELLED_STATUSES = {"cancelled", "canceled"}


@dataclass(frozen=True)
class Reservation:
    listing_name: str
    check_in: dt.date
    check_out: dt.date
    adr: float
    booking_status: str
    booked_date: dt.date | None = None

    @property
    def is_booked(self) -> bool:
        return self.booking_status.strip().lower() not in CANCELLED_STATUSES


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


def _parse_optional_date(s: str | None) -> dt.date | None:
    if not s or s == "-1":
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except ValueError:
        return None


def _from_api_rows(rows: list[dict]) -> list[Reservation]:
    out = []
    for row in rows:
        try:
            no_of_days = float(row.get("no_of_days") or 0)
            revenue = float(row.get("rental_revenue") or 0)
            adr = revenue / no_of_days if no_of_days > 0 else 0.0
            out.append(
                Reservation(
                    listing_name=row.get("listing_name", ""),
                    check_in=_parse_date(row["check_in"]),
                    check_out=_parse_date(row["check_out"]),
                    adr=adr,
                    booking_status=row.get("booking_status", ""),
                    booked_date=_parse_optional_date(row.get("booked_date")),
                )
            )
        except (KeyError, ValueError, TypeError) as exc:
            logger.warning("Skipping malformed reservation row %r: %s", row, exc)
    return out


def _normalize_listing_name(name: str) -> str:
    # Strip ALL whitespace, not just collapse repeats: real PMS-sourced
    # names have been observed with inconsistent spacing around the same
    # words (e.g. "Sauna  Cold Plunge  5 BR" vs. a config name of "Sauna
    # Cold Plunge 5BR") -- word-boundary differences like "5BR" vs "5 BR"
    # are formatting noise here, not a meaningful distinction.
    return "".join(name.split()).lower()


def load_reservations_csv(path: str, listing_name: str | None = None) -> list[Reservation]:
    """Load reservations from a manually-exported CSV.

    If `listing_name` is given, only rows for that property are returned --
    a portfolio-wide export covers every listing in one file, and without
    this filter one property's bookings would leak into another's LY price
    lookup and booking-window figure. Matching is whitespace/case-normalized
    since PMS-sourced listing names can have inconsistent spacing (e.g.
    "Sauna  Cold Plunge  5 BR" vs. a config name of "Sauna Cold Plunge 5BR").
    """
    out = []
    all_listing_names: set[str] = set()
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = set(CSV_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"Bookings CSV at {path} is missing expected columns: "
                f"{sorted(missing)}. Expected columns: {CSV_COLUMNS}"
            )
        for row in reader:
            try:
                row_listing_name = row["Listing Name"]
                all_listing_names.add(row_listing_name)
                out.append(
                    Reservation(
                        listing_name=row_listing_name,
                        check_in=_parse_date(row["Check-in Date"]),
                        check_out=_parse_date(row["Check-out Date"]),
                        adr=float(row["Average Daily Rate"]),
                        booking_status=row["Booking Status"],
                        booked_date=_parse_optional_date(row.get("Booked Date")),
                    )
                )
            except (KeyError, ValueError) as exc:
                logger.warning("Skipping malformed CSV row %r: %s", row, exc)

    if listing_name is None:
        return out

    target = _normalize_listing_name(listing_name)
    filtered = [r for r in out if _normalize_listing_name(r.listing_name) == target]
    if not filtered:
        raise ValueError(
            f"No rows in {path} matched listing name '{listing_name}' "
            f"(normalized: '{target}'). Listing names found in the CSV: "
            f"{sorted(all_listing_names)}. Check config/listings.yaml's "
            f"`name` field against the CSV's Listing Name column."
        )
    return filtered


def fetch_reservations_verified(
    client: PriceLabsClient,
    pms: str,
    listing_id: str,
    listing_name: str,
    years_back: int = 2,
    fallback_csv_path: str | None = None,
) -> list[Reservation]:
    """Fetch reservation history via the API and verify it isn't truncated.

    Returns CSV-sourced reservations instead of the API result if a
    fallback path is given and the API result looks truncated; otherwise
    logs a warning and returns the (possibly incomplete) API result.
    """
    today = dt.date.today()
    start = today - dt.timedelta(days=365 * years_back)
    end = today + dt.timedelta(days=1)

    rows = client.get_reservations(
        pms=pms,
        listing_id=listing_id,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
    )
    reservations = _from_api_rows(rows)

    earliest = min((r.check_in for r in reservations), default=None)
    # Allow ~60 days of slack: a brand-new listing legitimately has no old
    # bookings, but if we asked for `years_back` years and got data that
    # only reaches back a few weeks, that's the truncation bug resurfacing.
    looks_truncated = earliest is None or (earliest - start).days > 60

    if not looks_truncated:
        logger.info(
            "Reservation API returned %d rows for listing %s, earliest "
            "check-in %s (requested back to %s) -- looks complete.",
            len(reservations),
            listing_id,
            earliest,
            start,
        )
        return reservations

    if fallback_csv_path:
        logger.warning(
            "Reservation API for listing %s looks truncated (earliest "
            "check-in %s vs requested %s, %d rows) -- falling back to CSV "
            "at %s.",
            listing_id,
            earliest,
            start,
            len(reservations),
            fallback_csv_path,
        )
        return load_reservations_csv(fallback_csv_path, listing_name=listing_name)

    logger.warning(
        "Reservation history for listing %s looks thin: got %d rows, "
        "earliest check-in %s, requested back to %s, and no --bookings-csv "
        "fallback was given. Proceeding with this partial history anyway "
        "-- the LY price lookup and this property's own booking-window "
        "figure may be incomplete. This is expected for a genuinely new listing; if you "
        "suspect this is the known PriceLabs truncation bug instead, export "
        "the full history CSV from the PriceLabs dashboard (columns: %s) "
        "and rerun with --bookings-csv to backfill it.",
        listing_id,
        len(reservations),
        earliest,
        start,
        CSV_COLUMNS,
    )
    return reservations


def median_booking_window_days(reservations: list[Reservation]) -> float | None:
    """Median days between when a booking was made and its check-in date,
    across this property's own actual confirmed reservations -- used to
    decide whether an unbooked date is "close enough" to check-in that
    still-being-unbooked is a meaningful demand signal (see
    compute.in_booking_window). Grounded in this specific property's own
    booking pattern rather than a market-wide average, matching how the
    sibling booking_quality_log tool computes the same concept. Returns
    None if there's no reservation with a usable booked_date, in which
    case the caller falls back to a fixed-day default.
    """
    windows = [
        (r.check_in - r.booked_date).days
        for r in reservations
        if r.is_booked and r.booked_date is not None and r.check_in >= r.booked_date
    ]
    if not windows:
        return None
    return statistics.median(windows)


def nightly_adr_series(reservations: list[Reservation]) -> dict[dt.date, float]:
    """Expand each booked reservation into one ADR value per night stayed.

    A multi-night stay's blended rate gets applied to every night in the
    stay (see the "blended ADR, not per-night" caveat) -- this is a
    simplification, not a true per-night rate.
    """
    series: dict[dt.date, float] = {}
    for r in reservations:
        if not r.is_booked:
            continue
        d = r.check_in
        while d < r.check_out:
            series[d] = r.adr
            d += dt.timedelta(days=1)
    return series
