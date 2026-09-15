import datetime as dt

from booking_quality_log.dated_output import dated_filename, find_most_recent_prior_file


def test_no_folder_yet_returns_none(tmp_path):
    empty_dir = tmp_path / "does-not-exist"
    assert find_most_recent_prior_file(empty_dir, dt.date(2026, 9, 15)) is None


def test_first_run_has_no_prior_file(tmp_path):
    assert find_most_recent_prior_file(tmp_path, dt.date(2026, 9, 15)) is None


def test_picks_most_recent_earlier_file_even_across_a_multi_day_gap(tmp_path):
    # Simulates several days being skipped (no new bookings) -- the most
    # recent file could be a week old, not just yesterday's.
    for d in [dt.date(2026, 9, 5), dt.date(2026, 9, 8)]:
        (tmp_path / dated_filename(d)).write_bytes(b"")

    result = find_most_recent_prior_file(tmp_path, dt.date(2026, 9, 15))
    assert result == tmp_path / dated_filename(dt.date(2026, 9, 8))


def test_ignores_same_day_and_future_files(tmp_path):
    for d in [dt.date(2026, 9, 14), dt.date(2026, 9, 15), dt.date(2026, 9, 16)]:
        (tmp_path / dated_filename(d)).write_bytes(b"")
    result = find_most_recent_prior_file(tmp_path, dt.date(2026, 9, 15))
    assert result == tmp_path / dated_filename(dt.date(2026, 9, 14))


def test_ignores_unrelated_files(tmp_path):
    (tmp_path / "random.xlsx").write_bytes(b"")
    (tmp_path / dated_filename(dt.date(2026, 9, 10))).write_bytes(b"")
    result = find_most_recent_prior_file(tmp_path, dt.date(2026, 9, 15))
    assert result == tmp_path / dated_filename(dt.date(2026, 9, 10))
