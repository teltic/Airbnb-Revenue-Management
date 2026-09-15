"""Read back a prior "Booking Quality Log" workbook's Reservation IDs and
hand-typed manual columns, so a rerun can:

1. tell whether any brand-new confirmed booking has shown up since that
   run (the daily skip-if-nothing-new check), and
2. carry every still-visible booking's manual notes forward untouched.

Both needs read the same data, so one function serves both.

Columns are located by reading the prior file's OWN header row rather than
hardcoded column numbers: "Reservation ID" is found by its header text,
and the 6 manual columns are read as whatever 6 columns immediately follow
it -- not by matching their header text. This is deliberate: it's what
lets a column be inserted (e.g. the "Status" column) or a manual header be
renamed (e.g. "LY Weekday Occ." -> "LY occ.") in a newer version of this
tool without breaking notes carried forward from a file an older version
wrote, since "Reservation ID" is the one label that never changes.
"""

from __future__ import annotations

from pathlib import Path

import openpyxl

from .workbook_build import HEADER_ROW, MANUAL_COLS_COUNT, SHEET_NAME

RESERVATION_ID_HEADER = "Reservation ID"


def load_prior_reservation_state(path: Path) -> dict[str, tuple]:
    """Returns {reservation_id: (6 manual-column values)} for every row in
    the prior file's "Booking Quality Log" sheet -- including rows where
    all 6 manual values are still blank, since the keys alone are what the
    daily skip check needs.
    """
    if not path.exists():
        return {}
    wb = openpyxl.load_workbook(path, data_only=False)
    if SHEET_NAME not in wb.sheetnames:
        return {}
    ws = wb[SHEET_NAME]

    header_row = ws[HEADER_ROW]
    reservation_id_col = next(
        (i for i, cell in enumerate(header_row) if cell.value == RESERVATION_ID_HEADER), None
    )
    if reservation_id_col is None:
        return {}
    manual_cols_start = reservation_id_col + 1

    result: dict[str, tuple] = {}
    for row in ws.iter_rows(min_row=HEADER_ROW + 1):
        if len(row) <= reservation_id_col:
            continue
        reservation_id = row[reservation_id_col].value
        if not reservation_id:
            continue
        manual_values = tuple(
            row[manual_cols_start + i].value if len(row) > manual_cols_start + i else None
            for i in range(MANUAL_COLS_COUNT)
        )
        result[str(reservation_id)] = manual_values
    return result
