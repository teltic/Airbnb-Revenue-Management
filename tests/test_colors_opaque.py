"""Regression tests for two real, separate color bugs found across two
live Excel runs:

1. A plain 6-digit RGB string passed to openpyxl's PatternFill/Font
   silently becomes fully TRANSPARENT (00 alpha) rather than opaque.
2. Excel reads a conditional-formatting fill's color from `bgColor` (with
   no `patternType`), not `fgColor` + `patternType="solid"` the way a
   normal cell fill does -- confirmed against the original hand-built
   prototype's own dxf XML. Getting this backwards meant real Excel showed
   nothing for the booked/flag/weekend colors even after the alpha fix,
   despite the data and CF rules being completely correct and openpyxl's
   own read-back of the file looking fine.
"""

from daily_price_analysis import workbook_build as wbb

# Used inside FormulaRule (serialized into <dxfs>) -- must use the
# bgColor-only, no-patternType convention.
DXF_FILL_NAMES = ["FILL_BOOKED", "FILL_ABOVE_CAP", "FILL_BELOW_TYPICAL", "FILL_WEEKEND"]

# Assigned directly as `cell.fill = ...` (a plain cell style) -- must use
# "solid" + fgColor.
PLAIN_FILL_NAMES = [
    "FILL_OVERRIDE_POSITIVE",
    "FILL_OVERRIDE_NEGATIVE",
    "FILL_OVERRIDE_NEUTRAL",
    "FILL_NOTE",
    "FILL_HEADER",
]


def _assert_opaque(rgb: str, label: str) -> None:
    assert isinstance(rgb, str) and len(rgb) == 8, f"{label}={rgb!r} is not 8-digit ARGB"
    assert rgb.startswith("FF"), f"{label}={rgb!r} is not fully opaque (alpha != FF)"


def test_dxf_fills_use_bgcolor_with_no_pattern_type():
    for name in DXF_FILL_NAMES:
        fill = getattr(wbb, name)
        assert fill.patternType is None, f"{name}.patternType should be None for a dxf fill, got {fill.patternType!r}"
        _assert_opaque(fill.bgColor.rgb, f"{name}.bgColor.rgb")


def test_plain_fills_use_solid_fgcolor():
    for name in PLAIN_FILL_NAMES:
        fill = getattr(wbb, name)
        assert fill.patternType == "solid", f"{name}.patternType should be 'solid', got {fill.patternType!r}"
        _assert_opaque(fill.fgColor.rgb, f"{name}.fgColor.rgb")


def test_booked_font_is_opaque():
    _assert_opaque(wbb.FONT_BOOKED.color.rgb, "FONT_BOOKED.color.rgb")
