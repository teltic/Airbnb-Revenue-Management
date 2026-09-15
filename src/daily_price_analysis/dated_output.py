"""Dated daily-snapshot output: one file per day in a folder, each new run
reading the most recent prior day's file to carry forward Notes and the
Promo Tracker tabs -- an archive-friendly alternative to always overwriting
one fixed file in place.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

FILENAME_STEM = "Daily Low & High Price Analysis"
_DATED_FILENAME_RE = re.compile(re.escape(FILENAME_STEM) + r" - (\d{4}-\d{2}-\d{2})\.xlsx$")


def dated_filename(date: dt.date) -> str:
    return f"{FILENAME_STEM} - {date.isoformat()}.xlsx"


def resolve_output_paths(
    output_dir: Path | None, output_path: Path, today: dt.date
) -> tuple[Path, Path | None]:
    """Decide where to write today's workbook and where to read prior
    Notes/Promo data from.

    Without `output_dir`, both are the same fixed `output_path` --
    matching the original "overwrite one file in place" behavior. With
    `output_dir`, writes go to a new dated file each day and Notes/Promo
    are carried forward from the most recent dated file already present in
    that directory whose date is today or earlier (never a future-dated
    file). Preferring *today's own* file when one already exists (rather
    than always the latest strictly-earlier one) matters for a same-day
    rerun: if you've already generated today's file and typed Notes or
    Promo rows into it, rerunning the script the same day must read those
    back rather than silently discarding them.
    """
    if output_dir is None:
        return output_path, output_path

    output_dir.mkdir(parents=True, exist_ok=True)
    write_path = output_dir / dated_filename(today)

    latest: tuple[dt.date, Path] | None = None
    for candidate in output_dir.glob(f"{FILENAME_STEM} - *.xlsx"):
        match = _DATED_FILENAME_RE.search(candidate.name)
        if not match:
            continue
        file_date = dt.date.fromisoformat(match.group(1))
        if file_date <= today and (latest is None or file_date > latest[0]):
            latest = (file_date, candidate)

    preserve_source_path = latest[1] if latest else None
    return write_path, preserve_source_path
