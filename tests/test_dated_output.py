import datetime as dt
from pathlib import Path

from daily_price_analysis.dated_output import dated_filename, resolve_output_paths


def test_no_output_dir_uses_fixed_path():
    fixed = Path("/tmp/foo.xlsx")
    write_path, preserve_path = resolve_output_paths(None, fixed, dt.date(2026, 9, 15))
    assert write_path == fixed
    assert preserve_path == fixed


def test_output_dir_first_run_has_no_preserve_source(tmp_path):
    write_path, preserve_path = resolve_output_paths(tmp_path, Path("unused"), dt.date(2026, 9, 15))
    assert write_path == tmp_path / dated_filename(dt.date(2026, 9, 15))
    assert preserve_path is None


def test_output_dir_picks_most_recent_earlier_file(tmp_path):
    for d in [dt.date(2026, 9, 10), dt.date(2026, 9, 13), dt.date(2026, 9, 14)]:
        (tmp_path / dated_filename(d)).write_bytes(b"")

    write_path, preserve_path = resolve_output_paths(tmp_path, Path("unused"), dt.date(2026, 9, 15))
    assert write_path == tmp_path / dated_filename(dt.date(2026, 9, 15))
    assert preserve_path == tmp_path / dated_filename(dt.date(2026, 9, 14))


def test_output_dir_prefers_todays_own_file_over_earlier_ones(tmp_path):
    """A same-day rerun (e.g. you already generated today's file and typed
    Notes into it, then reran the script) must read today's own file back,
    not silently fall through to an earlier day and discard those edits.
    """
    for d in [dt.date(2026, 9, 14), dt.date(2026, 9, 15)]:
        (tmp_path / dated_filename(d)).write_bytes(b"")

    write_path, preserve_path = resolve_output_paths(tmp_path, Path("unused"), dt.date(2026, 9, 15))
    assert preserve_path == tmp_path / dated_filename(dt.date(2026, 9, 15))


def test_output_dir_ignores_future_files(tmp_path):
    for d in [dt.date(2026, 9, 14), dt.date(2026, 9, 16)]:
        (tmp_path / dated_filename(d)).write_bytes(b"")

    write_path, preserve_path = resolve_output_paths(tmp_path, Path("unused"), dt.date(2026, 9, 15))
    assert preserve_path == tmp_path / dated_filename(dt.date(2026, 9, 14))


def test_output_dir_ignores_unrelated_files(tmp_path):
    (tmp_path / "random.xlsx").write_bytes(b"")
    (tmp_path / dated_filename(dt.date(2026, 9, 10))).write_bytes(b"")

    _write_path, preserve_path = resolve_output_paths(tmp_path, Path("unused"), dt.date(2026, 9, 15))
    assert preserve_path == tmp_path / dated_filename(dt.date(2026, 9, 10))


def test_output_dir_created_if_missing(tmp_path):
    target = tmp_path / "nested" / "dir"
    resolve_output_paths(target, Path("unused"), dt.date(2026, 9, 15))
    assert target.is_dir()
