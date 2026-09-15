import datetime as dt

from daily_price_analysis.compute import DateRow
from daily_price_analysis.market import CompsetInfo
from daily_price_analysis.overrides import OverrideRow
from daily_price_analysis.workbook_build import (
    HIDDEN_MAIN_COLUMNS,
    MAIN_HEADERS,
    build_compset_sheet,
    build_how_this_works_sheet,
    build_overrides_sheet,
    build_promo_sheet,
    build_property_sheet,
    new_workbook,
)


def _sample_row(d: dt.date, booked: str, price: float, flag: str = "", flag_color: str = "") -> DateRow:
    return DateRow(
        date=d,
        day=d.strftime("%A"),
        category="Weekend (Fri/Sat)" if d.strftime("%A") in ("Friday", "Saturday") else "Weekday (Sun-Thu)",
        current_price=price,
        ly_market_occ=71.4,
        market_occupancy_pct=50.0,
        in_booking_window="Yes",
        price_override="-10%",
        override_reason="test reason",
        airbnb_promo_price=None,
        discount_pct=None,
        ly_price=200.0,
        booked=booked,
        flag=flag,
        flag_color=flag_color,
    )


def test_property_sheet_structure_matches_prototype():
    wb = new_workbook()
    rows = [
        _sample_row(dt.date(2026, 9, 11), "Yes", 650),  # Friday, booked
        _sample_row(dt.date(2026, 9, 12), "No", 500, "ABOVE TARGET (weak weekend demand)", "salmon"),
        _sample_row(dt.date(2026, 9, 14), "No", 50, "BELOW TARGET (strong demand, price too low)", "green"),
    ]
    build_property_sheet(wb, "Test Property", rows)
    ws = wb["Test Property"]

    header_values = [c.value for c in ws[1]]
    assert header_values == MAIN_HEADERS
    assert len(MAIN_HEADERS) == 23  # A..W

    for col_letter in HIDDEN_MAIN_COLUMNS:
        assert ws.column_dimensions[col_letter].hidden is True
    for col_letter in ("Q", "R", "S", "W"):
        assert ws.column_dimensions[col_letter].hidden is not True

    assert ws["E2"].value.startswith("=IF(D2=")  # Market Percentile stays a live formula
    assert ws["F2"].value == 50.0  # Market Occupancy %
    assert ws["H2"].value == "Yes"  # In Booking Window?
    assert ws["V3"].value == "salmon"  # Flag Color (hidden)
    assert ws["W3"].value == "ABOVE TARGET (weak weekend demand)"  # Flag (plain value, not a formula)

    rules_ranges = [str(r.sqref) for r in ws.conditional_formatting]
    assert any("A2:N" in r for r in rules_ranges)
    assert any("W2:W" in r for r in rules_ranges)


def test_full_workbook_tab_order():
    wb = new_workbook()
    rows = [_sample_row(dt.date(2026, 9, 11), "No", 300)]
    build_property_sheet(wb, "Prop A", rows)
    build_property_sheet(wb, "Prop B", rows)
    build_promo_sheet(wb, "Promo - A", [])
    build_promo_sheet(wb, "Promo - B", [])
    build_overrides_sheet(wb, "Overrides - A", {})
    build_overrides_sheet(wb, "Overrides - B", {})
    build_compset_sheet(
        wb,
        [
            ("Prop A", CompsetInfo("Market Dashboard: ABB Comp: X", "X", 7)),
            ("Prop B", CompsetInfo("Nearby Listings", "3BR-5BR", 118)),
        ],
    )
    build_how_this_works_sheet(wb)

    assert wb.sheetnames == [
        "Prop A",
        "Prop B",
        "Promo - A",
        "Promo - B",
        "Overrides - A",
        "Overrides - B",
        "Compset Overview",
        "How This Works",
    ]


def test_overrides_sheet_colors_by_sign():
    overrides = {
        dt.date(2026, 9, 12): OverrideRow(
            date=dt.date(2026, 9, 12),
            price_override_display="-10%",
            price_sign="negative",
            min_price=650,
            max_price=None,
            min_stay=2,
            reason="pacing behind",
        ),
        dt.date(2026, 9, 13): OverrideRow(
            date=dt.date(2026, 9, 13),
            price_override_display="",
            price_sign="none",
            min_price=None,
            max_price=None,
            min_stay=2,
            reason="",
        ),
    }
    wb = new_workbook()
    build_overrides_sheet(wb, "Overrides - Test", overrides)
    ws = wb["Overrides - Test"]
    assert ws["A2"].value.date() == dt.date(2026, 9, 12)
    assert ws["B2"].value == "-10%"
    # Must be fully opaque (FF alpha prefix) -- a plain 6-digit RGB string
    # silently becomes fully transparent (00 alpha) in openpyxl, which was
    # a real bug here: every color in the workbook rendered invisibly.
    assert ws["B2"].fill.fgColor.rgb == "FFF8CBAD"
    assert ws["B3"].fill.fgColor.rgb == "FFD9D9D9"
