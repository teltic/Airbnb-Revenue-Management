"""Regression test for a real bug: a plain 6-digit RGB string passed to
openpyxl's PatternFill/Font silently becomes fully TRANSPARENT (00 alpha)
rather than opaque, so every color in an earlier version of this workbook
rendered invisibly in real Excel despite the underlying data and
conditional-formatting rules being completely correct. Every fill/font
color used in the workbook must be fully opaque (FF alpha prefix).
"""

from daily_price_analysis import workbook_build as wbb


def _all_color_constants():
    for name in dir(wbb):
        if not (name.startswith("FILL_") or name.startswith("FONT_")):
            continue
        yield name, getattr(wbb, name)


def test_no_color_constant_is_transparent():
    checked = 0
    for name, style in _all_color_constants():
        color = getattr(style, "fgColor", None) or getattr(style, "color", None)
        assert color is not None, f"{name} has no color to check"
        rgb = color.rgb
        assert isinstance(rgb, str) and len(rgb) == 8, f"{name}.rgb={rgb!r} is not 8-digit ARGB"
        assert rgb.startswith("FF"), f"{name}.rgb={rgb!r} is not fully opaque (alpha != FF)"
        checked += 1
    assert checked >= 9, "expected to find all the known color constants"
