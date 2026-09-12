import os
import tempfile
import unittest
from unittest import mock

from pacing_tracker import config
from pacing_tracker.data_pull import _booked_dates, _extract_reservation_rows, _parse_occupancy_curve, run_pull
from pacing_tracker.snapshot_cache import SnapshotStore


def _category_block(dates, occ, occ_ly, occ_stly, listings_used=5):
    return {
        "Listings Used": listings_used,
        "X_values": dates,
        "Y_values": [occ, [0] * len(dates), [0] * len(dates), occ_ly, occ_stly, [0] * len(dates)],
    }


def _neighborhood_response(dates, occ, occ_ly, occ_stly, category="Comp Set A"):
    return _neighborhood_response_multi(
        {category: _category_block(dates, occ, occ_ly, occ_stly)}
    )


def _neighborhood_response_multi(categories):
    return {
        "data": {
            "Future Occ/New/Canc": {
                "Labels": [
                    "Occupancy",
                    "New Bookings",
                    "Canceled Bookings",
                    "Occupancy_LY",
                    "Occupancy_STLY",
                    "New_Bookings_STLY",
                ],
                "Category": categories,
            }
        },
        "status": "Success",
    }


def _reservation_response(rows):
    return {"data": {"pms_name": "smartbnb", "next_page": False, "data": rows}}


class FakeClient:
    def __init__(self, neighborhood_by_listing, reservations_by_listing):
        self.neighborhood_by_listing = neighborhood_by_listing
        self.reservations_by_listing = reservations_by_listing

    def get_neighborhood_data(self, listing_id, pms):
        return self.neighborhood_by_listing[listing_id]

    def get_reservations(self, pms, start_date, end_date, listing_id=None, limit=None, offset=None):
        return self.reservations_by_listing[listing_id]


class ParseOccupancyCurveTest(unittest.TestCase):
    def test_parses_single_category(self):
        dates = ["2026-09-12", "2026-09-13"]
        resp = _neighborhood_response(dates, [50, 60], [40, 50], [45, 55])
        curve = _parse_occupancy_curve(resp, "L1")
        self.assertEqual(curve["2026-09-12"], {"occ": 50, "occ_ly": 40, "occ_stly": 45})
        self.assertEqual(curve["2026-09-13"], {"occ": 60, "occ_ly": 50, "occ_stly": 55})

    def test_missing_block_returns_empty(self):
        self.assertEqual(_parse_occupancy_curve({"data": {}}, "L1"), {})

    def test_multiple_categories_uses_configured_override(self):
        dates = ["2026-09-12"]
        resp = _neighborhood_response_multi(
            {
                "3": _category_block(dates, [10], [10], [10], listings_used=50),  # most used
                "5": _category_block(dates, [70], [60], [65], listings_used=2),  # the real comp set
            }
        )
        with mock.patch.dict(
            config.NEIGHBORHOOD_CATEGORY_OVERRIDES, {"game-room": "5"}, clear=True
        ):
            curve = _parse_occupancy_curve(resp, "game-room")
        self.assertEqual(curve["2026-09-12"], {"occ": 70, "occ_ly": 60, "occ_stly": 65})

    def test_multiple_categories_falls_back_to_most_used_without_override(self):
        dates = ["2026-09-12"]
        resp = _neighborhood_response_multi(
            {
                "3": _category_block(dates, [10], [10], [10], listings_used=50),
                "5": _category_block(dates, [70], [60], [65], listings_used=2),
            }
        )
        with mock.patch.dict(config.NEIGHBORHOOD_CATEGORY_OVERRIDES, {}, clear=True):
            curve = _parse_occupancy_curve(resp, "unmapped-listing")
        self.assertEqual(curve["2026-09-12"], {"occ": 10, "occ_ly": 10, "occ_stly": 10})


class ExtractReservationRowsTest(unittest.TestCase):
    def test_flat_shape_data_is_the_row_list(self):
        # what the live Customer API actually returns: "data" IS the array,
        # with next_page as a sibling of "data" rather than nested under it.
        resp = {"data": [{"reservation_id": "R1"}], "next_page": True}
        rows, next_page = _extract_reservation_rows(resp)
        self.assertEqual(rows, [{"reservation_id": "R1"}])
        self.assertTrue(next_page)

    def test_nested_shape_data_wraps_rows_and_next_page(self):
        resp = {"data": {"data": [{"reservation_id": "R1"}], "next_page": False}}
        rows, next_page = _extract_reservation_rows(resp)
        self.assertEqual(rows, [{"reservation_id": "R1"}])
        self.assertFalse(next_page)


class BookedDatesTest(unittest.TestCase):
    def test_check_out_is_exclusive_and_cancelled_ignored(self):
        rows = [
            {"check_in": "2026-09-13", "check_out": "2026-09-15", "booking_status": "booked"},
            {"check_in": "2026-09-20", "check_out": "2026-09-22", "booking_status": "cancelled"},
        ]
        booked = _booked_dates(rows)
        self.assertEqual(booked, {"2026-09-13", "2026-09-14"})


class RunPullBlendTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.snapshot_store = SnapshotStore(cache_path=os.path.join(self.tmpdir.name, "cache.json"))
        self.dates = ["2026-09-12", "2026-09-13", "2026-09-14"]
        self.listings = [
            {"listing_id": "L1", "pms": "smartbnb", "name": "A"},
            {"listing_id": "L2", "pms": "smartbnb", "name": "B"},
        ]
        self.client = FakeClient(
            neighborhood_by_listing={
                "L1": _neighborhood_response(self.dates, [50, 60, 70], [40, 50, 60], [45, 55, 65]),
                "L2": _neighborhood_response(self.dates, [30, 40, 50], [20, 30, 40], [25, 35, 45]),
            },
            reservations_by_listing={
                "L1": _reservation_response(
                    [{"check_in": "2026-09-13", "check_out": "2026-09-14", "booking_status": "booked"}]
                ),
                "L2": _reservation_response([]),
            },
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_blends_occupancy_and_market_metrics_across_listings(self):
        records = run_pull(
            self.client,
            self.snapshot_store,
            pull_date="2026-09-12",
            forecast_days=3,
            listings=self.listings,
        )
        by_date = {r["date"]: r for r in records}

        self.assertEqual(by_date["2026-09-12"]["occupancy_pct"], 0.0)
        self.assertEqual(by_date["2026-09-13"]["occupancy_pct"], 50.0)  # L1 booked, L2 not
        self.assertEqual(by_date["2026-09-14"]["occupancy_pct"], 0.0)

        self.assertEqual(by_date["2026-09-12"]["market_occ_pct"], 40.0)  # avg(50, 30)
        self.assertEqual(by_date["2026-09-12"]["market_occ_pct_ly"], 30.0)  # avg(40, 20)
        self.assertEqual(by_date["2026-09-12"]["market_occ_pct_stly"], 35.0)  # avg(45, 25)

        self.assertEqual(by_date["2026-09-12"]["weekday"], "Sat")

    def test_pickup_is_none_before_history_accumulates(self):
        records = run_pull(
            self.client,
            self.snapshot_store,
            pull_date="2026-09-12",
            forecast_days=3,
            listings=self.listings,
        )
        self.assertIsNone(records[0]["pickup_7d"])

    def test_pickup_populates_after_a_second_pull(self):
        # First pull happens 7 days earlier, with a window wide enough to
        # still cover 2026-09-12 so that date gets a snapshot recorded.
        wide_dates = [f"2026-09-{d:02d}" for d in range(5, 15)]  # 09-05 .. 09-14
        self.client.neighborhood_by_listing["L1"] = _neighborhood_response(
            wide_dates, [50] * len(wide_dates), [40] * len(wide_dates), [45] * len(wide_dates)
        )
        self.client.neighborhood_by_listing["L2"] = _neighborhood_response(
            wide_dates, [30] * len(wide_dates), [20] * len(wide_dates), [25] * len(wide_dates)
        )
        run_pull(self.client, self.snapshot_store, pull_date="2026-09-05", forecast_days=10, listings=self.listings)

        # Second pull, a week later: the market for 2026-09-12 has firmed up.
        self.client.neighborhood_by_listing["L1"] = _neighborhood_response(
            self.dates, [60, 70, 80], [40, 50, 60], [45, 55, 65]
        )
        self.client.neighborhood_by_listing["L2"] = _neighborhood_response(
            self.dates, [40, 50, 60], [20, 30, 40], [25, 35, 45]
        )
        records = run_pull(
            self.client,
            self.snapshot_store,
            pull_date="2026-09-12",
            forecast_days=3,
            listings=self.listings,
        )
        # L1: 60-50=10, L2: 40-30=10 -> blended 10
        self.assertAlmostEqual(records[0]["pickup_7d"], 10.0)


if __name__ == "__main__":
    unittest.main()
