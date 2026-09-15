"""Build the "Daily Low & High Price Analysis" workbook with openpyxl.

Sheet layout and per-property column order/formulas/conditional-formatting
colors are reproduced from the hand-built prototype workbook, not just the
original prose spec -- where the two disagreed (a few "hidden" columns that
the prototype actually left visible), the prototype wins, since the ask was
to reproduce that exact design.
"""

from __future__ import annotations

import datetime as dt

from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .compute import DateRow
from .market import CompsetInfo
from .overrides import OverrideRow

# openpyxl colors are 8-digit ARGB; the leading 2 digits are alpha
# (opacity), NOT decoration -- a plain 6-digit RGB string silently becomes
# "00" (fully transparent) alpha rather than opaque, which is why an
# earlier version of this file's colors were all invisible despite the
# conditional formatting and cell values being completely correct. Always
# use the "FF" (opaque) prefix here.
FILL_BOOKED = PatternFill("solid", fgColor="FF404040")
FONT_BOOKED = Font(color="FFFFFFFF")
FILL_ABOVE_CAP = PatternFill("solid", fgColor="FFC6E0B4")
FILL_BELOW_TYPICAL = PatternFill("solid", fgColor="FFF8CBAD")
FILL_WEEKEND = PatternFill("solid", fgColor="FFDDEBF7")
FILL_OVERRIDE_POSITIVE = PatternFill("solid", fgColor="FFC6E0B4")
FILL_OVERRIDE_NEGATIVE = PatternFill("solid", fgColor="FFF8CBAD")
FILL_OVERRIDE_NEUTRAL = PatternFill("solid", fgColor="FFD9D9D9")
FILL_NOTE = PatternFill("solid", fgColor="FFFFFF00")
FILL_HEADER = PatternFill("solid", fgColor="FFD9E1F2")
BOLD = Font(bold=True)

MAIN_HEADERS = [
    "Date", "Day", "Category", "Current Price", "LY ADR (blended)",
    "2LY ADR (blended)", "Market Percentile", "LY Market Occ %",
    "Price Override (PriceLabs)", "Override Reason", "Airbnb Promotion Price",
    "Discount %", "Note Date", "Note", "Holiday/Event", "Market 25th %ile",
    "Market 50th %ile", "Market 75th %ile", "Market 90th %ile",
    "Weekday Max (All-Time)", "Weekday Max (This Month)",
    "Weekday Typical Floor (P25, This Month)", "Weekend Max (All-Time)",
    "Weekend Max (This Month)", "Weekend Typical Floor (P25, This Month)",
    "+20% Threshold", "Booked?", "Flag",
]
HIDDEN_MAIN_COLUMNS = {"O", "P", "T", "V", "W", "Y", "Z", "AA"}

PROMO_HEADERS = [
    "Entered Date", "Date Applied", "Current Pricelabs Price",
    "Airbnb Last Price", "Price Entered", "Discount %", "Notes",
    "Price Override (PriceLabs)", "Override Reason",
]

OVERRIDE_HEADERS = ["Date", "Price Override", "Min Price", "Max Price", "Min Stay", "Reason"]

COMPSET_HEADERS = ["Property", "Compset Type", "Compset Detail", "Listings in Comp", "Notes"]


def _style_header(ws: Worksheet, headers: list[str]) -> None:
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = BOLD
        cell.fill = FILL_HEADER
    ws.freeze_panes = "A2"


def build_property_sheet(wb: Workbook, tab_name: str, rows: list[DateRow]) -> None:
    ws = wb.create_sheet(tab_name)
    _style_header(ws, MAIN_HEADERS)

    for r, row in enumerate(rows, start=2):
        ws.cell(row=r, column=1, value=dt.datetime.combine(row.date, dt.time()))
        ws.cell(row=r, column=1).number_format = "m/d/yyyy"
        ws.cell(row=r, column=2, value=row.day)
        ws.cell(row=r, column=3, value=row.category)
        ws.cell(row=r, column=4, value=row.current_price)
        ws.cell(row=r, column=5, value=row.ly_adr)
        ws.cell(row=r, column=6, value=row.ly2_adr)
        ws.cell(
            row=r,
            column=7,
            value=(
                f'=IF(D{r}="","",IF(P{r}="","",IF(D{r}<P{r},"<25th",'
                f'IF(D{r}<Q{r},"25th-50th",IF(D{r}<R{r},"50th-75th",'
                f'IF(D{r}<S{r},"75th-90th",">90th"))))))'
            ),
        )
        ws.cell(row=r, column=8, value=row.ly_market_occ)
        ws.cell(row=r, column=9, value=row.price_override)
        ws.cell(row=r, column=10, value=row.override_reason)
        ws.cell(row=r, column=11, value=row.airbnb_promo_price)
        ws.cell(row=r, column=12, value=row.discount_pct)
        ws.cell(row=r, column=13, value=row.note_date)
        ws.cell(row=r, column=14, value=row.note)
        ws.cell(row=r, column=13).fill = FILL_NOTE
        ws.cell(row=r, column=14).fill = FILL_NOTE
        ws.cell(row=r, column=15, value=row.holiday_name)
        ws.cell(row=r, column=16, value=row.market_p25)
        ws.cell(row=r, column=17, value=row.market_p50)
        ws.cell(row=r, column=18, value=row.market_p75)
        ws.cell(row=r, column=19, value=row.market_p90)
        ws.cell(row=r, column=20, value=row.weekday_max_all_time)
        ws.cell(row=r, column=21, value=row.weekday_max_this_month)
        ws.cell(row=r, column=22, value=row.weekday_floor_this_month)
        ws.cell(row=r, column=23, value=row.weekend_max_all_time)
        ws.cell(row=r, column=24, value=row.weekend_max_this_month)
        ws.cell(row=r, column=25, value=row.weekend_floor_this_month)
        ws.cell(
            row=r,
            column=26,
            value=(
                f'=IFERROR(IF($C{r}="Weekday (Sun-Thu)",IF($U{r}<>"",$U{r},$T{r}),'
                f'IF($C{r}="Weekend (Fri/Sat)",IF($X{r}<>"",$X{r},$W{r}),""))*1.2,"")'
            ),
        )
        ws.cell(row=r, column=27, value=row.booked)
        ws.cell(
            row=r,
            column=28,
            value=(
                f'=IF(AA{r}="Yes","",IF(AND(Z{r}<>"",D{r}>Z{r}),"ABOVE +20% CAP",'
                f'IF($C{r}="Weekday (Sun-Thu)",IF(AND($V{r}<>"",D{r}<$V{r}),"BELOW TYPICAL",""),'
                f'IF($C{r}="Weekend (Fri/Sat)",IF(AND($Y{r}<>"",D{r}<$Y{r}),"BELOW TYPICAL",""),""))))'
            ),
        )

    last_row = len(rows) + 1
    for col_letter in HIDDEN_MAIN_COLUMNS:
        ws.column_dimensions[col_letter].hidden = True
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["J"].width = 30
    ws.column_dimensions["N"].width = 30

    if last_row >= 2:
        an_range = f"A2:N{last_row}"
        ab_range = f"AB2:AB{last_row}"
        ws.conditional_formatting.add(
            an_range,
            FormulaRule(formula=['$AA2="Yes"'], fill=FILL_BOOKED, font=FONT_BOOKED),
        )
        ws.conditional_formatting.add(
            ab_range,
            FormulaRule(formula=['$AA2="Yes"'], fill=FILL_BOOKED, font=FONT_BOOKED),
        )
        ws.conditional_formatting.add(
            an_range, FormulaRule(formula=['$AB2="ABOVE +20% CAP"'], fill=FILL_ABOVE_CAP)
        )
        ws.conditional_formatting.add(
            ab_range, FormulaRule(formula=['$AB2="ABOVE +20% CAP"'], fill=FILL_ABOVE_CAP)
        )
        ws.conditional_formatting.add(
            an_range, FormulaRule(formula=['$AB2="BELOW TYPICAL"'], fill=FILL_BELOW_TYPICAL)
        )
        ws.conditional_formatting.add(
            ab_range, FormulaRule(formula=['$AB2="BELOW TYPICAL"'], fill=FILL_BELOW_TYPICAL)
        )
        ws.conditional_formatting.add(
            f"A2:B{last_row}",
            FormulaRule(formula=['OR($B2="Friday",$B2="Saturday")'], fill=FILL_WEEKEND),
        )


def build_promo_sheet(wb: Workbook, tab_name: str, raw_rows: list[list]) -> None:
    ws = wb.create_sheet(tab_name)
    _style_header(ws, PROMO_HEADERS)
    for r, values in enumerate(raw_rows, start=2):
        for c, value in enumerate(values[: len(PROMO_HEADERS)], start=1):
            ws.cell(row=r, column=c, value=value)
    ws.column_dimensions["G"].width = 30


def build_overrides_sheet(wb: Workbook, tab_name: str, overrides: dict[dt.date, OverrideRow]) -> None:
    ws = wb.create_sheet(tab_name)
    _style_header(ws, OVERRIDE_HEADERS)
    for r, d in enumerate(sorted(overrides), start=2):
        o = overrides[d]
        ws.cell(row=r, column=1, value=dt.datetime.combine(d, dt.time()))
        ws.cell(row=r, column=1).number_format = "m/d/yyyy"
        ws.cell(row=r, column=2, value=o.price_override_display)
        ws.cell(row=r, column=3, value=o.min_price)
        ws.cell(row=r, column=4, value=o.max_price)
        ws.cell(row=r, column=5, value=o.min_stay)
        ws.cell(row=r, column=6, value=o.reason)

        if o.price_sign == "positive":
            fill = FILL_OVERRIDE_POSITIVE
        elif o.price_sign == "negative":
            fill = FILL_OVERRIDE_NEGATIVE
        else:
            fill = FILL_OVERRIDE_NEUTRAL
        for c in range(1, 7):
            ws.cell(row=r, column=c).fill = fill
    ws.column_dimensions["F"].width = 40


def build_compset_sheet(wb: Workbook, entries: list[tuple[str, CompsetInfo]]) -> None:
    ws = wb.create_sheet("Compset Overview")
    _style_header(ws, COMPSET_HEADERS)
    for r, (property_name, info) in enumerate(entries, start=2):
        ws.cell(row=r, column=1, value=property_name)
        ws.cell(row=r, column=2, value=info.source_label.split(":")[0].strip() if info.source_label else "")
        ws.cell(row=r, column=3, value=info.category_name)
        ws.cell(row=r, column=4, value=info.listings_used)
        ws.cell(row=r, column=5, value=info.notes)
    footer_row = len(entries) + 3
    ws.cell(
        row=footer_row,
        column=1,
        value=(
            "Pulled from PriceLabs' Neighborhood Data config per listing. "
            "Re-check whenever a compset is changed -- different properties in "
            "the same portfolio can silently use different comp-set "
            "methodologies (e.g. a curated amenity-based comp vs. a generic "
            "bedroom-range comp) even when they look similar in the UI."
        ),
    )
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["C"].width = 45
    ws.column_dimensions["E"].width = 50


HOW_THIS_WORKS_LINES = [
    "Daily Low & High Price Analysis -- How To Use",
    "",
    "Visible columns, in order: Date, Day, Category, Current Price, LY ADR, 2LY ADR, "
    "Market Percentile, LY Market Occ %, Price Override, Override Reason, Airbnb "
    "Promotion Price, Discount %, Note Date, Note, [hidden columns], Flag (last column).",
    "",
    "Workflow: filter Booked? = No, scan for orange/green highlights, check LY ADR / "
    "2LY ADR and LY Market Occ % for context, log a note if you investigate.",
    "",
    "Market Percentile shows where Current Price sits vs. the hidden market comp "
    "columns (<25th, 25th-50th, 50th-75th, 75th-90th, >90th).",
    "",
    "Flag: ABOVE +20% CAP (green) or BELOW TYPICAL (orange), computed off that row's "
    "own category (weekday vs weekend; holidays are never flagged) against the hidden "
    "Max/Typical-Floor columns for that category and calendar month.",
    "",
    "Row coloring priority (first match wins): 1) Booked = Yes -> dark fill, done, no "
    "review needed. 2) Flag = ABOVE +20% CAP -> green. 3) Flag = BELOW TYPICAL -> "
    "salmon. 4) Separately, the Date/Day columns get a light-blue Friday/Saturday "
    "marker whenever nothing above already colored those two cells.",
    "",
    "Price Override (PriceLabs) / Override Reason -- a same-date lookup against that "
    "property's own Overrides tab, refreshed live every run.",
    "",
    "Airbnb Promotion Price / Discount % -- a same-date lookup against that property's "
    "Promo Tracker tab, which is hand-maintained and never overwritten by this script.",
    "",
    "CAVEATS:",
    "1. Blended ADR, not per-night. LY/2LY ADR and the promo-range price lookups all "
    "come from stay-level or range-level data, not true per-night rates -- a "
    "multi-night reservation's average rate is applied to every night in that stay.",
    "2. Holiday/Event flagging is deliberately disabled. A single tag lumps very "
    "different occasions together, so holiday-tagged dates get Market Percentile and "
    "LY Market Occ % for context but no ABOVE/BELOW flag.",
    "3. PriceLabs' API has no holiday/event field at all (checked the pricing, "
    "market-data, and overrides endpoints) -- that tagging is UI-only in the PriceLabs "
    "dashboard, so this workbook sources it from config/holidays.yaml, maintained by "
    "hand alongside this script.",
    "4. 'This Month' Max/Floor pools every date in that calendar month across ALL "
    "years of history available (e.g. every September, not just this one) so there's "
    "enough data to be meaningful; it only computes when a month has 3+ data points, "
    "otherwise it's left blank rather than show a number built on noise.",
    "5. Comp-set methodology can differ silently between properties -- always check "
    "the Compset Overview tab before comparing percentile columns across properties.",
    "6. Historical bookings data is fetched from PriceLabs' reservation API with a "
    "sanity check for truncation (a known bug where date-filtered calls silently "
    "returned only recent bookings); if that check trips and no manual CSV fallback "
    "is configured, the script fails loudly rather than showing incomplete history.",
]


def build_how_this_works_sheet(wb: Workbook) -> None:
    ws = wb.create_sheet("How This Works")
    ws.column_dimensions["A"].width = 120
    for r, line in enumerate(HOW_THIS_WORKS_LINES, start=1):
        cell = ws.cell(row=r, column=1, value=line)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        if r == 1:
            cell.font = Font(bold=True, size=14)


def new_workbook() -> Workbook:
    wb = Workbook()
    del wb["Sheet"]
    return wb
