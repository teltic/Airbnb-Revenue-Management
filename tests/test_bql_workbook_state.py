import datetime as dt
from pathlib import Path

from booking_quality_log.compute import BookingRow
from booking_quality_log.workbook_build import build_booking_quality_sheet, new_workbook
from booking_quality_log.workbook_state import load_prior_reservation_state


def _row(res_id):
    return BookingRow(
        property_name="Test Property",
        check_in=dt.date(2026, 9, 5),
        check_out=dt.date(2026, 9, 7),
        nights=2,
        stay_pattern="Weekend-anchored",
        one_night_stay=False,
        booked_date=dt.date(2026, 8, 20),
        booking_window_days=16,
        bw_vs_median="Typical",
        my_adr=400.0,
        my_revenue=800.0,
        source="airbnb",
        target_adr_p75=380.0,
        vs_target_dollar=20.0,
        vs_target_pct=0.0526,
        market_p25=250.0,
        market_p90=420.0,
        stly_adr="no data",
        demand_tier="High",
        gap_before_days="first known booking in window",
        gap_before_signal=None,
        gap_after_days=1,
        gap_after_signal="Upsell candidate (rarely fills alone)",
        reservation_id=res_id,
    )


def test_missing_file_returns_empty_dict(tmp_path):
    assert load_prior_reservation_state(tmp_path / "nope.xlsx") == {}


def test_reads_reservation_ids_and_manual_columns(tmp_path):
    wb = new_workbook()
    build_booking_quality_sheet(wb, [_row("AAA111"), _row("BBB222")], dt.date(2026, 9, 1))
    ws = wb["Booking Quality Log"]
    ws.cell(row=5, column=27, value="checked on airbnb")  # Comp Check for AAA111
    ws.cell(row=6, column=32, value="looks great")  # Notes/Verdict for BBB222
    path = tmp_path / "prior.xlsx"
    wb.save(path)

    state = load_prior_reservation_state(path)
    assert set(state.keys()) == {"AAA111", "BBB222"}
    assert state["AAA111"][0] == "checked on airbnb"
    assert state["BBB222"][5] == "looks great"


def test_row_with_all_blank_manual_columns_still_counted_for_skip_check(tmp_path):
    wb = new_workbook()
    build_booking_quality_sheet(wb, [_row("AAA111")], dt.date(2026, 9, 1))
    path = tmp_path / "prior.xlsx"
    wb.save(path)

    state = load_prior_reservation_state(path)
    assert "AAA111" in state
    assert state["AAA111"] == (None, None, None, None, None, None)
