"""Thin wrapper around the PriceLabs Customer API.

NOTE: the exact base URL and auth header are our best-known default and have
not yet been smoke-tested against a live key from this account (see
README "Verifying API access" section). If a call fails with 401/404, check
those two things first via PRICELABS_API_BASE_URL and PRICELABS_API_KEY.
"""

import os
import time

import requests

from . import config


class PriceLabsAPIError(RuntimeError):
    pass


class PriceLabsClient:
    def __init__(self, api_key=None, base_url=None, session=None, max_retries=3, backoff_seconds=2):
        self.api_key = api_key or os.environ.get(config.PRICELABS_API_KEY_ENV_VAR)
        if not self.api_key:
            raise PriceLabsAPIError(
                f"No API key found. Looked for a {config.PRICELABS_API_KEY_ENV_VAR} line in a "
                f".env file in the current folder ({os.getcwd()}) or a matching environment "
                "variable, and found neither. Create a .env file right next to this script "
                f"containing exactly one line: {config.PRICELABS_API_KEY_ENV_VAR}=your-key-here"
            )
        self.base_url = (base_url or config.PRICELABS_API_BASE_URL).rstrip("/")
        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def _headers(self):
        return {"X-API-Key": self.api_key}

    def _request(self, method, path, params=None, json_body=None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        last_error = None
        for attempt in range(self.max_retries):
            try:
                resp = self.session.request(
                    method, url, headers=self._headers(), params=params, json=json_body, timeout=30
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = PriceLabsAPIError(f"{resp.status_code} from {url}: {resp.text[:500]}")
                    time.sleep(self.backoff_seconds * (attempt + 1))
                    continue
                if not resp.ok:
                    raise PriceLabsAPIError(f"{resp.status_code} from {url}: {resp.text[:500]}")
                return resp.json()
            except requests.RequestException as exc:
                last_error = PriceLabsAPIError(f"Request to {url} failed: {exc}")
                time.sleep(self.backoff_seconds * (attempt + 1))
        raise last_error

    def _get(self, path, params=None):
        return self._request("GET", path, params=params)

    def _post(self, path, json_body=None):
        return self._request("POST", path, json_body=json_body)

    def get_neighborhood_data(self, listing_id, pms):
        """Per-listing comp-set market snapshot, including a daily
        Occupancy / Occupancy_LY / Occupancy_STLY curve for future dates.
        """
        return self._get("neighborhood_data", params={"listing_id": listing_id, "pms": pms})

    def get_reservations(self, pms, start_date, end_date, listing_id=None, limit=None, offset=None):
        """Reservations whose stay dates fall in [start_date, end_date)."""
        params = {"pms": pms, "start_date": start_date, "end_date": end_date}
        if listing_id:
            params["listing_id"] = listing_id
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        return self._get("reservation_data", params=params)

    def get_report_builder_templates(self):
        """DIAGNOSTIC ONLY (see scripts/check_report_builder_access.py) --
        this endpoint is only known to exist on PriceLabs' internal/session
        tooling; whether it's also reachable from a plain Customer API key
        is exactly what that script is checking. Not used by data_pull.py.
        """
        return self._get("report_builder/templates")

    def get_report_builder_data(self, template_id):
        return self._post("report_builder/data", json_body={"template_id": template_id})

    def poll_report_builder_data(self, request_id):
        return self._post("report_builder/poll", json_body={"request_id": request_id})
