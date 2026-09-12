"""Pulls the daily pacing/pickup report for both listings (already blended
portfolio-wide by PriceLabs) and writes an intermediate JSON file that the
(separate) Excel-generation stage consumes.

Data source: PriceLabs' Report Builder ("Master Sheet - TB" template),
confirmed reachable from a plain Customer API key (see
scripts/check_report_builder_access.py). It returns, pre-computed and
already blended across both listings: Occupancy, Market Occupancy, LY,
STLY, and Pickup 3/7/14/30/60d -- so unlike an earlier version of this
script, nothing here is self-computed or estimated.
"""

import argparse
import json
import logging
import os
import time
from datetime import date, datetime, timedelta

from . import config
from .api_client import PriceLabsAPIError, PriceLabsClient

logger = logging.getLogger(__name__)

ROW_FIELD_MAP = {
    "occupancy_pct": "Occupancy",
    "market_occ_pct": "Average Market Occupancy",
    "market_occ_pct_ly": "Average Market Occupancy LY",
    "market_occ_pct_stly": "Average Market Occupancy STLY",
    "pickup_3d": "Average Market Occupancy Pickup 3",
    "pickup_7d": "Average Market Occupancy Pickup 7",
    "pickup_14d": "Average Market Occupancy Pickup 14",
    "pickup_30d": "Average Market Occupancy Pickup 30",
    "pickup_60d": "Average Market Occupancy Pickup 60",
    "events": "Events",
}


def _find_template_id(client, template_name):
    resp = client.get_report_builder_templates()
    payload = resp.get("data", resp)
    templates = payload.get("templates", []) if isinstance(payload, dict) else payload
    for template in templates:
        if template.get("name") == template_name:
            return template.get("templateId") or template.get("id")
    raise PriceLabsAPIError(
        f"No Report Builder template named {template_name!r} found for this account. "
        f"Available: {[t.get('name') for t in templates]}"
    )


def fetch_report_rows(client, template_name=None, poll_interval_seconds=3, max_poll_seconds=60):
    """Returns the raw list of per-date report rows from Report Builder,
    polling if the account needs the report computed asynchronously.
    """
    template_id = _find_template_id(client, template_name or config.REPORT_BUILDER_TEMPLATE_NAME)

    resp = client.get_report_builder_data(template_id)
    payload = resp.get("data", resp)
    if isinstance(payload, dict) and payload.get("report_data") is not None:
        return payload["report_data"]

    request_id = payload.get("request_id") if isinstance(payload, dict) else None
    if not request_id:
        raise PriceLabsAPIError(f"Unexpected report_builder/data response: {resp!r}")

    waited = 0
    while waited < max_poll_seconds:
        time.sleep(poll_interval_seconds)
        waited += poll_interval_seconds
        poll_resp = client.poll_report_builder_data(request_id)
        poll_payload = poll_resp.get("data", poll_resp)
        if isinstance(poll_payload, dict):
            if poll_payload.get("report_data") is not None:
                return poll_payload["report_data"]
            if poll_payload.get("status") == "STATUS_NOT_FOUND":
                raise PriceLabsAPIError(f"Report Builder request {request_id} expired or was invalid.")
    raise PriceLabsAPIError(f"Timed out after {max_poll_seconds}s waiting for Report Builder (request_id={request_id}).")


def _parse_row(row):
    # Pass PriceLabs' own Weekday string through as-is (e.g. "05.Fri") rather
    # than deriving our own -- matches the reference workbook, and the Excel
    # formulas that check for weekends just SEARCH() for "Fri"/"Sat" as a
    # substring, so either format would work; no reason to diverge.
    record = {"date": row["Date"], "weekday": row.get("Weekday")}
    for out_field, source_field in ROW_FIELD_MAP.items():
        record[out_field] = row.get(source_field)
    return record


def run_pull(client, pull_date=None, forecast_days=None, template_name=None):
    pull_date = pull_date or date.today().isoformat()
    forecast_days = forecast_days or config.FORECAST_DAYS
    start = datetime.strptime(pull_date, "%Y-%m-%d").date()
    end = start + timedelta(days=forecast_days - 1)

    raw_rows = fetch_report_rows(client, template_name=template_name)

    records = []
    for row in raw_rows:
        try:
            row_date = datetime.strptime(row["Date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        if start <= row_date <= end:
            records.append(_parse_row(row))
    records.sort(key=lambda r: r["date"])

    if len(records) < forecast_days:
        logger.warning(
            "Requested %d days starting %s but Report Builder only returned %d in range "
            "(%s to %s). This is expected near the far edge of the report's own horizon.",
            forecast_days,
            pull_date,
            len(records),
            start,
            end,
        )
    return records


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
    records = run_pull(client, pull_date=args.pull_date, forecast_days=args.forecast_days)

    pull_date = args.pull_date or date.today().isoformat()
    out_path = args.out or os.path.join("data", f"pull_{pull_date}.json")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(records, f, indent=2)
    logger.info("Wrote %d daily records to %s", len(records), out_path)


if __name__ == "__main__":
    main()
