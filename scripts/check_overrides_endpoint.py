"""One-off diagnostic: find the real path for reading date-level overrides.

push.py assumed GET /v1/listing_data/{listing_id}/overrides (mirroring the
internal MCP tool's own routing path), which turned out to 404 against the
live account. This tries several plausible alternatives -- all read-only
GETs, safe to run -- and reports which one (if any) returns real data.

Run from the project root:
    python -m scripts.check_overrides_endpoint
"""

from pacing_tracker import config
from pacing_tracker.api_client import PriceLabsAPIError, PriceLabsClient

LISTING_ID = config.LISTINGS[0]["listing_id"]
PMS = config.LISTINGS[0]["pms"]

CANDIDATES = [
    ("listing_data/{listing_id}/overrides", {"pms": PMS}),
    ("overrides", {"listing_id": LISTING_ID, "pms": PMS}),
    ("listings/overrides", {"listing_id": LISTING_ID, "pms": PMS}),
    ("listings/{listing_id}/overrides", {"pms": PMS}),
    ("listing_prices/overrides", {"listing_id": LISTING_ID, "pms": PMS}),
    ("date_overrides", {"listing_id": LISTING_ID, "pms": PMS}),
    ("listing_overrides", {"listing_id": LISTING_ID, "pms": PMS}),
]


def main():
    client = PriceLabsClient()
    for path_template, params in CANDIDATES:
        path = path_template.format(listing_id=LISTING_ID)
        try:
            resp = client._get(path, params=params)
            print(f"SUCCESS: GET {path} params={params}")
            print(f"  Response (first 500 chars): {str(resp)[:500]}")
        except PriceLabsAPIError as exc:
            print(f"FAILED:  GET {path} params={params}\n  {exc}")
        print()


if __name__ == "__main__":
    main()
