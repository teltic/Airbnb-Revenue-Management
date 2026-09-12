import os
import tempfile
import unittest

from pacing_tracker.snapshot_cache import SnapshotStore


class SnapshotStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.cache_path = os.path.join(self.tmpdir.name, "cache.json")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_no_history_returns_none(self):
        store = SnapshotStore(cache_path=self.cache_path)
        store.record_snapshot("L1", "smartbnb", "2026-09-12", {"2026-10-01": 40.0})
        pickup = store.get_pickup("L1", "smartbnb", "2026-09-12", "2026-10-01", 7)
        self.assertIsNone(pickup)

    def test_pickup_after_history_accumulates(self):
        store = SnapshotStore(cache_path=self.cache_path)
        store.record_snapshot("L1", "smartbnb", "2026-09-01", {"2026-10-01": 30.0})
        store.record_snapshot("L1", "smartbnb", "2026-09-08", {"2026-10-01": 45.0})
        pickup_7d = store.get_pickup("L1", "smartbnb", "2026-09-08", "2026-10-01", 7)
        self.assertAlmostEqual(pickup_7d, 15.0)

    def test_persists_across_instances(self):
        store = SnapshotStore(cache_path=self.cache_path)
        store.record_snapshot("L1", "smartbnb", "2026-09-01", {"2026-10-01": 30.0})
        store2 = SnapshotStore(cache_path=self.cache_path)
        store2.record_snapshot("L1", "smartbnb", "2026-09-08", {"2026-10-01": 45.0})
        pickup_7d = store2.get_pickup("L1", "smartbnb", "2026-09-08", "2026-10-01", 7)
        self.assertAlmostEqual(pickup_7d, 15.0)

    def test_prunes_old_snapshots_beyond_max_window(self):
        store = SnapshotStore(cache_path=self.cache_path, max_history_days=10)
        store.record_snapshot("L1", "smartbnb", "2026-01-01", {"2026-02-01": 10.0})
        store.record_snapshot("L1", "smartbnb", "2026-02-01", {"2026-02-01": 20.0})
        # the Jan 1 snapshot is now far outside the 10-day retention window
        pickup = store.get_occupancy_as_of("L1", "smartbnb", "2026-01-01", "2026-02-01")
        self.assertIsNone(pickup)


if __name__ == "__main__":
    unittest.main()
