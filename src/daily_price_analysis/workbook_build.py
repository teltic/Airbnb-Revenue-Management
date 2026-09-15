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
# "00" (fully transparent) alpha rather than opaque. Always use the "FF"
# (opaque) prefix.
#
# Separately -- and this is NOT the same bug -- Excel has an undocumented
# quirk specific to conditional-formatting fills (dxfs): a normal cell
# fill uses `PatternFill("solid", fgColor=...)`, but a fill used inside a
# FormulaRule (i.e. serialized into <dxfs> rather than a plain cell style)
# needs `PatternFill(bgColor=...)` with NO patternType instead -- Excel
# reads the swatch from bgColor there, not fgColor, regardless of alpha
# being correct. Confirmed against the original hand-built prototype's own
# dxf XML, which uses exactly this bgColor-only, no-patternType form.
# Mixing the two up is exactly why real Excel still showed nothing for the
# booked/flag/weekend colors even after the alpha fix -- FILL_BOOKED,
# FILL_ABOVE_CAP, FILL_BELOW_TYPICAL, and FILL_WEEKEND are only ever used
# inside FormulaRule() below, so they use the dxf/bgColor form; the rest
# are assigned directly as `cell.fill = ...` (a plain cell style), so they
# correctly use "solid" + fgColor.
FILL_BOOKED = PatternFill(bgColor="FF404040")
FONT_BOOKED = Font(color="FFFFFFFF")
FILL_ABOVE_CAP = PatternFill(bgColor="FFC6E0B4")
FILL_BELOW_TYPICAL = PatternFill(bgColor="FFF8CBAD")
FILL_WEEKEND = PatternFill(bgColor="FFDDEBF7")
FILL_OVERRIDE_POSITIVE = PatternFill("solid", fgColor="FFC6E0B4")
FILL_OVERRIDE_NEGATIVE = PatternFill("solid", fgColor="FFF8CBAD")
FILL_OVERRIDE_NEUTRAL = PatternFill("solid", fgColor="FFD9D9D9")
FILL_NOTE = PatternFill("solid", fgColor="FFFFFF00")
FILL_HEADER = PatternFill("solid", fgColor="FFD9E1F2")
BOLD = Font(bold=True)

MAIN_HEADERS = [
    "Date", "Day", "Category", "Current Price", "Market Percentile",
    "Market Occupancy %", "LY Market Occ %", "In Booking Window?",
    "Price Override (PriceLabs)", "Override Reason", "Airbnb Promotion Price",
    "Discount %", "Note Date", "Note", "Holiday/Event", "Market 25th %ile",
    "Market 50th %ile", "Market 75th %ile", "Market 90th %ile",
    "LY Price (blended)", "Booked?", "Flag Color", "Flag",
]
HIDDEN_MAIN_COLUMNS = {"O", "P", "T", "U", "V"}

# Column order here MUST match promo.build_promo_output_rows exactly.
PROMO_HEADERS = [
    "Entered Date", "Date Applied", "Current Pricelabs Price",
    "Current Price (Airbnb-adjusted)", "Airbnb Last Price", "Price Entered",
    "Discount %", "Notes", "Price Override (PriceLabs)", "Override Reason",
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
        # Market Percentile stays a live Excel formula (Current Price vs.
        # the hidden/visible percentile columns to its right) so it keeps
        # recalculating if Current Price is ever hand-edited -- unlike
        # Flag (column W), which is now a plain computed value; see
        # compute.py's module docstring for why Flag couldn't reasonably
        # stay formula-driven once its logic grew branchy dynamic text.
        ws.cell(
            row=r,
            column=5,
            value=(
                f'=IF(D{r}="","",IF(P{r}="","",IF(D{r}<P{r},"<25th",'
                f'IF(D{r}<Q{r},"25th-50th",IF(D{r}<R{r},"50th-75th",'
                f'IF(D{r}<S{r},"75th-90th",">90th"))))))'
            ),
        )
        ws.cell(row=r, column=6, value=row.market_occupancy_pct)
        ws.cell(row=r, column=7, value=row.ly_market_occ)
        ws.cell(row=r, column=8, value=row.in_booking_window)
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
        ws.cell(row=r, column=20, value=row.ly_price)
        ws.cell(row=r, column=21, value=row.booked)
        ws.cell(row=r, column=22, value=row.flag_color)
        ws.cell(row=r, column=23, value=row.flag)

    last_row = len(rows) + 1
    for col_letter in HIDDEN_MAIN_COLUMNS:
        ws.column_dimensions[col_letter].hidden = True
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["J"].width = 30
    ws.column_dimensions["N"].width = 30
    ws.column_dimensions["W"].width = 40

    if last_row >= 2:
        an_range = f"A2:N{last_row}"
        flag_range = f"W2:W{last_row}"
        # Booked ($U="Yes") takes priority over the flag colors below --
        # both target ranges get all rules added in priority order, so a
        # booked+flagged row always shows the dark booked fill, never a
        # flag color underneath it.
        ws.conditional_formatting.add(
            an_range,
            FormulaRule(formula=['$U2="Yes"'], fill=FILL_BOOKED, font=FONT_BOOKED),
        )
        ws.conditional_formatting.add(
            flag_range,
            FormulaRule(formula=['$U2="Yes"'], fill=FILL_BOOKED, font=FONT_BOOKED),
        )
        # Flag Color (hidden column V) drives the fill directly rather than
        # pattern-matching the Flag text itself, since Flag now includes
        # dynamic dollar amounts (LY MISMATCH) that a simple equality
        # check in a CF formula can't match.
        ws.conditional_formatting.add(
            an_range, FormulaRule(formula=['$V2="green"'], fill=FILL_ABOVE_CAP)
        )
        ws.conditional_formatting.add(
            flag_range, FormulaRule(formula=['$V2="green"'], fill=FILL_ABOVE_CAP)
        )
        ws.conditional_formatting.add(
            an_range, FormulaRule(formula=['$V2="salmon"'], fill=FILL_BELOW_TYPICAL)
        )
        ws.conditional_formatting.add(
            flag_range, FormulaRule(formula=['$V2="salmon"'], fill=FILL_BELOW_TYPICAL)
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
    "Visible columns, in order: Date, Day, Category, Current Price, Market Percentile, "
    "Market Occupancy %, LY Market Occ %, In Booking Window?, Price Override, Override "
    "Reason, Airbnb Promotion Price, Discount %, Note Date, Note, [hidden columns], "
    "Flag (last column).",
    "",
    "Workflow: filter Booked? = No, scan for green/salmon highlights, check Market "
    "Occupancy % and LY Market Occ % for context, log a note if you investigate.",
    "",
    "Market Percentile shows where Current Price sits vs. the market comp columns "
    "(<25th, 25th-50th, 50th-75th, 75th-90th, >90th). Market Occupancy % is the "
    "comp-set's current occupancy for that date -- the main demand signal driving Flag.",
    "",
    "FLAG LOGIC -- this is occupancy-driven, not history-driven. An earlier version of "
    "this tool inferred 'typical' price from this property's own past booked prices; "
    "that approach just launders forward whatever pricing mistakes already happened, "
    "so it was replaced with a demand-based rule using actual market occupancy.",
    "",
    "Gate -- In Booking Window?: the Flag rule below only fires when Booked? = No AND "
    "In Booking Window? = Yes. This exists because a date far in the future being "
    "unbooked is normal, not a signal -- it only means something once we're close "
    "enough to check-in that most bookings for that date-type would typically already "
    "exist. 'Close enough' is this property's own median days-between-booking-and-"
    "check-in (from its actual reservation history), or 45 days if there isn't enough "
    "history yet to compute that (config: compute.DEFAULT_BOOKING_WINDOW_DAYS).",
    "",
    "Primary rule (occupancy tier), only when In Booking Window? = Yes:",
    "  - Weekday and Market Occupancy % < 30% (weak demand) and Market Percentile is "
    "above 25th -> ABOVE TARGET (weak weekday demand), salmon -- price is too high "
    "for the demand level.",
    "  - Weekend and Market Occupancy % < 40% (weak demand) and Market Percentile is "
    "above 25th -> ABOVE TARGET (weak weekend demand), salmon.",
    "  - Market Occupancy % >= 80% (either category, strong demand) and Market "
    "Percentile is below 90th -> BELOW TARGET (strong demand, price too low), green "
    "-- an opportunity to raise price.",
    "  - Otherwise: no flag from this rule.",
    "",
    "Secondary rule (LY mismatch), checked only if the primary rule above didn't "
    "already flag the row: if Current Price is more than 20% away from the same "
    "calendar date last year's price (config: compute.LY_MISMATCH_THRESHOLD_PCT) -> "
    "LY MISMATCH (was $X, now $Y). Green if price is now higher than last year, salmon "
    "if lower. Runs regardless of the booking-window gate -- a price drift from last "
    "year is worth surfacing even well before check-in. The LY figure comes from "
    "stay-level reservation data, not a guaranteed true per-night rate for that exact "
    "date (see caveat 1).",
    "",
    "Holiday/Event dates never get a Flag from either rule (unchanged reasoning: a "
    "single tag lumps very different occasions together, e.g. New Year's Eve and an "
    "ordinary pre-Christmas Tuesday, so a blended threshold would be misleading).",
    "",
    "Row coloring priority (first match wins): 1) Booked = Yes -> dark fill, done, no "
    "review needed. 2) Flag color = green (see above). 3) Flag color = salmon. 4) "
    "Separately, the Date/Day columns get a light-blue Friday/Saturday marker whenever "
    "nothing above already colored those two cells.",
    "",
    "Price Override (PriceLabs) / Override Reason -- a same-date lookup against that "
    "property's own Overrides tab, refreshed live every run.",
    "",
    "Airbnb Promotion Price / Discount % -- a same-date lookup against that property's "
    "Promo Tracker tab, which is hand-maintained and never overwritten by this script. "
    "That tab also has a 'Current Price (Airbnb-adjusted)' column: PriceLabs' Current "
    "Price and what Airbnb actually shows guests aren't the same number (Airbnb applies "
    "its own always-on discount plus PMS markup on top of the PriceLabs feed), so "
    "comparing Airbnb Promotion Price against raw Current Price compares two different "
    "reference points. The adjusted column applies a configurable factor (default 0.90 "
    "-- config: promo.AIRBNB_ADJUSTMENT_FACTOR, still being validated against real "
    "numbers) so that comparison is apples-to-apples.",
    "",
    "Promo Tracker entry formats accepted: Date Applied can be a single date, "
    "'M/D to M/D', or 'M/D-M/D' (either separator works). Current Pricelabs Price and "
    "Price Entered can be a single number, a '$lo-$hi' range, or a slash-separated list "
    "like '215/202/281' for a multi-night range -- every number found gets averaged "
    "into one flat figure (not reconstructed per-night; see caveat 1). Anything else "
    "won't be recognized and that row's per-date lookup will silently come up blank on "
    "the main tab, so double-check a new promo shows up there after entering it.",
    "",
    "CAVEATS:",
    "1. Blended, not per-night. LY price and the promo-range price lookups all come "
    "from stay-level or range-level data, not true per-night rates -- a multi-night "
    "reservation's average rate is applied to every night in that stay.",
    "2. PriceLabs' API has no holiday/event field at all (checked the pricing, "
    "market-data, and overrides endpoints) -- that tagging is UI-only in the PriceLabs "
    "dashboard, so this workbook sources it from config/holidays.yaml, maintained by "
    "hand alongside this script.",
    "3. Comp-set methodology can differ silently between properties -- always check "
    "the Compset Overview tab before comparing percentile or occupancy columns across "
    "properties.",
    "4. Historical bookings data is fetched from PriceLabs' reservation API with a "
    "sanity check for suspiciously thin history; if that check trips and no manual CSV "
    "fallback is configured, the run proceeds with a logged warning rather than "
    "stopping (LY price and the booking-window figure for that property may be "
    "incomplete) -- this matters for unattended daily automation.",
    "5. Flag is a plain computed value, not a live Excel formula, unlike Market "
    "Percentile -- it won't recalculate if you hand-edit Current Price. Current Price "
    "is pulled live from PriceLabs each run, so this shouldn't come up in normal use.",
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
