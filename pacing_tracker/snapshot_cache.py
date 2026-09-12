"""Local history of daily Market Occupancy curves, used to self-compute pickup.

PriceLabs' own "pickup" = change in Market Occupancy for a given future date,
compared to what that same future date's Market Occupancy read as N days ago.
The public neighborhood_data endpoint only ever returns *today's* curve, so we
have to keep our own rolling history: every day the script runs, it snapshots
today's curve, then looks back at what was snapshotted N days ago for each
pickup window.

This means pickup3d/7d/14d are usable within 2-3 weeks of first running the
script daily; pickup30d/60d need 30-60 days of accumulated history before
they're fully populated. Until then, get_pickup() returns None for that
window and the report should render it blank rather than a false zero.
"""

import json
import os
from datetime import datetime, timedelta

from . import config


def _load(cache_path):
    if not os.path.exists(cache_path):
        return {}
    with open(cache_path, "r") as f:
        return json.load(f)


def _save(cache_path, data):
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    tmp_path = cache_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f)
    os.replace(tmp_path, cache_path)


class SnapshotStore:
    def __init__(self, cache_path=None, max_history_days=None):
        self.cache_path = cache_path or config.SNAPSHOT_CACHE_PATH
        self.max_history_days = max_history_days or (max(config.PICKUP_WINDOWS_DAYS) + 5)
        self._data = _load(self.cache_path)

    @staticmethod
    def _listing_key(listing_id, pms):
        return f"{pms}:{listing_id}"

    def record_snapshot(self, listing_id, pms, pull_date, date_occ_map):
        """Store today's {future_date: occ_pct} curve for this listing.

        pull_date: "YYYY-MM-DD" string for today (the date this pull ran).
        date_occ_map: dict of future_date -> occupancy percentage (float).
        """
        key = self._listing_key(listing_id, pms)
        listing_history = self._data.setdefault(key, {})
        listing_history[pull_date] = date_occ_map
        self._prune(listing_history, pull_date)
        _save(self.cache_path, self._data)

    def _prune(self, listing_history, as_of_date_str):
        as_of = datetime.strptime(as_of_date_str, "%Y-%m-%d").date()
        cutoff = as_of - timedelta(days=self.max_history_days)
        for pull_date_str in list(listing_history.keys()):
            pull_date = datetime.strptime(pull_date_str, "%Y-%m-%d").date()
            if pull_date < cutoff:
                del listing_history[pull_date_str]

    def get_occupancy_as_of(self, listing_id, pms, as_of_date, future_date):
        """Occupancy the given listing's curve showed for future_date, as
        captured on as_of_date's snapshot. Returns None if we don't have a
        snapshot from that exact date (e.g. not enough history yet, or the
        script didn't run that day).
        """
        key = self._listing_key(listing_id, pms)
        listing_history = self._data.get(key, {})
        snapshot = listing_history.get(as_of_date)
        if snapshot is None:
            return None
        return snapshot.get(future_date)

    def get_pickup(self, listing_id, pms, pull_date, future_date, window_days):
        """current_occ - occ_as_of(pull_date - window_days) for future_date.

        Returns None if either value is unavailable (current curve should
        always have it; the historical side is what's commonly missing
        during the bootstrap period).
        """
        current = self.get_occupancy_as_of(listing_id, pms, pull_date, future_date)
        if current is None:
            return None
        pull_dt = datetime.strptime(pull_date, "%Y-%m-%d").date()
        as_of = (pull_dt - timedelta(days=window_days)).strftime("%Y-%m-%d")
        past = self.get_occupancy_as_of(listing_id, pms, as_of, future_date)
        if past is None:
            return None
        return current - past
