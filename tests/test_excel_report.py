import unittest
from datetime import date

from pacing_tracker import config
from pacing_tracker.excel_report import (
    _days_out_formula,
    _median_booking_window_formula,
    _new_since_last_review_formula,
    _override_status_formula,
    _signal_formula,
    _suggested_bump_formula,
    _suggested_note_formula,
    build_workbook,
)

# Extracted verbatim from the user's reference workbook
# (Daily_Pacing_Pickup_9.11.26.xlsx, row 2) -- these are regression anchors,
# not formulas we designed independently, so a match here means we've
# reproduced their actual working logic, not just something equivalent.
REFERENCE_SUGGESTED_BUMP_ROW2 = (
    '=IF(C2=100,"",IF(AND(F2<IF(OR(ISNUMBER(SEARCH("Fri",B2)),ISNUMBER(SEARCH("Sat",B2))),'
    '$AA$24,$AA$23),G2<$AA$25),"-10%",IF(AND(F2>=$AA$28,IFERROR(T2>=$AA$29*U2,FALSE()),'
    'G2<-$AA$2,G2>=-$AA$30),"Hold - high LY, outside window",IF(AND(G2<-$AA$2,N2>1),'
    '"⚠ Mixed – review",IF(G2<-$AA$2,"-"&IF(M2>2.5,20,IF(M2>1.5,10,5))&"%",'
    'IF(AND(N2>1,G2<=$AA$2,T2<=U2),"Hold - within booking window",'
    'IF(OR(G2>$AA$2,N2>1),"+"&IF(MAX(M2,N2)>IF(F2>=$AA$26,$AA$27,2.5),20,'
    'IF(MAX(M2,N2)>1.5,10,5))&"%",IF(OR(K2>$AA$6,L2>$AA$7),"+5% (watch)",""))))))))'
)
REFERENCE_SIGNAL_ROW2 = (
    '=IF(C2=100,"✓ Booked",TRIM(IF(G2>$AA$2,"▲ Ahead ","")&IF(G2<-$AA$2,"▼ Behind ","")&'
    'IF(OR(H2>$AA$3,I2>$AA$4,J2>$AA$5),"⚡ Spike ","")&IF(AND(OR(K2>$AA$6,L2>$AA$7),'
    'NOT(OR(H2>$AA$3,I2>$AA$4,J2>$AA$5))),"● Elevated 30/60d","")))'
)
REFERENCE_SUGGESTED_NOTE_ROW2 = (
    '=IF(G2<-$AA$2,"9/11 - Pacing behind by "&TEXT(G2,"0.00")&"%",'
    'IF(G2>$AA$2,"9/11 - Pacing ahead by "&TEXT(G2,"0.00")&"%",'
    'IF(N2>1,"9/11 - Pickup demand spike","")))'
)
REFERENCE_DAYS_OUT_ROW2 = "=A2-TODAY()"
REFERENCE_MEDIAN_BOOKING_WINDOW_ROW2 = "=IFERROR(VLOOKUP(MONTH(A2),'Booking Window'!A:C,3,FALSE()),\"\")"
REFERENCE_OVERRIDE_STATUS_ROW2 = (
    '=IF(ISBLANK(Q2),"",IF(AND(IF(ISNUMBER(Q2),Q2<0,LEFT(Q2,1)="-")=FALSE(),'
    'NOT(OR(ISNUMBER(SEARCH("Ahead",P2)),ISNUMBER(SEARCH("Spike",P2)),'
    'ISNUMBER(SEARCH("Elevated",P2))))),"Review - pace normalized",""))'
)
REFERENCE_NEW_SINCE_LAST_REVIEW_ROW2 = (
    '=IF(OR(AND(ISNUMBER(SEARCH("Ahead",P2)),NOT(ISNUMBER(SEARCH("Ahead","▼ Behind ⚡ Spike")))),'
    'AND(ISNUMBER(SEARCH("Spike",P2)),NOT(ISNUMBER(SEARCH("Spike","▼ Behind ⚡ Spike")))),'
    'AND(ISNUMBER(SEARCH("Elevated",P2)),NOT(ISNUMBER(SEARCH("Elevated","▼ Behind ⚡ Spike"))))),"NEW","")'
)


class FormulaMatchesReferenceFileTest(unittest.TestCase):
    def test_suggested_bump(self):
        self.assertEqual(_suggested_bump_formula(2), REFERENCE_SUGGESTED_BUMP_ROW2)

    def test_signal(self):
        self.assertEqual(_signal_formula(2), REFERENCE_SIGNAL_ROW2)

    def test_suggested_note(self):
        self.assertEqual(_suggested_note_formula(2, "9/11"), REFERENCE_SUGGESTED_NOTE_ROW2)

    def test_days_out(self):
        self.assertEqual(_days_out_formula(2), REFERENCE_DAYS_OUT_ROW2)

    def test_median_booking_window(self):
        self.assertEqual(_median_booking_window_formula(2), REFERENCE_MEDIAN_BOOKING_WINDOW_ROW2)

    def test_override_status(self):
        self.assertEqual(_override_status_formula(2), REFERENCE_OVERRIDE_STATUS_ROW2)

    def test_new_since_last_review_with_previous_signal(self):
        self.assertEqual(
            _new_since_last_review_formula(2, "▼ Behind ⚡ Spike"),
            REFERENCE_NEW_SINCE_LAST_REVIEW_ROW2,
        )

    def test_new_since_last_review_with_no_previous_signal(self):
        # matches reference row 3's formula, generated for a date that
        # wasn't in the prior file (previous_signal is None -> "")
        result = _new_since_last_review_formula(2, None)
        self.assertIn('SEARCH("Ahead","")', result)
        self.assertIn('SEARCH("Spike","")', result)
        self.assertIn('SEARCH("Elevated","")', result)


def _sample_record(d, **overrides):
    record = {
        "date": d, "weekday": "07.Sat", "occupancy_pct": 50.0, "market_occ_pct": 26.38,
        "market_occ_pct_stly": 34.89, "market_occ_pct_ly": 41.21, "pickup_3d": 0.0,
        "pickup_7d": 5.17, "pickup_14d": 13.79, "pickup_30d": 19.83, "pickup_60d": 22.41,
        "events": None,
    }
    record.update(overrides)
    return record


class BuildWorkbookTest(unittest.TestCase):
    def test_header_row(self):
        wb = build_workbook([_sample_record("2026-09-12")], date(2026, 9, 12), {})
        ws = wb["Daily Pacing"]
        self.assertEqual(ws["A1"].value, "Date")
        self.assertEqual(ws["P1"].value, "Signal")
        self.assertEqual(ws["X1"].value, "New Since Last Review")

    def test_writes_raw_values_not_formulas_for_pulled_fields(self):
        wb = build_workbook([_sample_record("2026-09-12")], date(2026, 9, 12), {})
        ws = wb["Daily Pacing"]
        self.assertEqual(ws["D2"].value, 26.38)
        self.assertEqual(ws["C2"].value, 50.0)
        self.assertEqual(ws["C2"].number_format, "0.00\\%")

    def test_date_written_as_real_date_not_string(self):
        wb = build_workbook([_sample_record("2026-09-12")], date(2026, 9, 12), {})
        ws = wb["Daily Pacing"]
        self.assertEqual(ws["A2"].value.strftime("%Y-%m-%d"), "2026-09-12")

    def test_carries_forward_override_request_and_notes(self):
        previous_state = {"2026-09-12": {"override_request": -0.1, "notes": "9/11 - behind", "signal": "▼ Behind"}}
        wb = build_workbook([_sample_record("2026-09-12")], date(2026, 9, 12), previous_state)
        ws = wb["Daily Pacing"]
        self.assertEqual(ws["Q2"].value, -0.1)
        self.assertEqual(ws["R2"].value, "9/11 - behind")

    def test_blank_override_request_when_no_prior_state(self):
        wb = build_workbook([_sample_record("2026-09-12")], date(2026, 9, 12), {})
        ws = wb["Daily Pacing"]
        self.assertIsNone(ws["Q2"].value)
        self.assertIsNone(ws["R2"].value)

    def test_threshold_block_matches_config(self):
        wb = build_workbook([_sample_record("2026-09-12")], date(2026, 9, 12), {})
        ws = wb["Daily Pacing"]
        self.assertEqual(ws["AA2"].value, config.THRESHOLDS["pace_threshold"])
        self.assertEqual(ws["AA8"].value, config.THRESHOLDS["ly_occ_visual_red_below"])
        self.assertEqual(ws["AA30"].value, config.THRESHOLDS["far_out_hold_max_behind_pace"])

    def test_booking_window_sheet_matches_config(self):
        wb = build_workbook([_sample_record("2026-09-12")], date(2026, 9, 12), {})
        ws = wb["Booking Window"]
        self.assertEqual(ws["A2"].value, 1)
        self.assertEqual(ws["B2"].value, "Jan")
        self.assertEqual(ws["C2"].value, config.MEDIAN_BOOKING_WINDOW_BY_MONTH[1])

    def test_conditional_format_fills_use_bgcolor_not_fgcolor(self):
        # Regression test: Excel/Google Sheets read a conditional format's
        # visible color from the dxf's bgColor with patternType unset, NOT
        # fgColor + patternType="solid" (the convention for an ordinary
        # cell fill). Using the wrong convention here previously produced
        # a workbook where every conditional-format color silently failed
        # to render, confirmed against the reference file's actual dxf
        # records.
        wb = build_workbook([_sample_record("2026-09-12")], date(2026, 9, 12), {})
        ws = wb["Daily Pacing"]
        checked_any = False
        for rng, rules in ws.conditional_formatting._cf_rules.items():
            for rule in rules:
                if rule.dxf is None or rule.dxf.fill is None:
                    continue
                checked_any = True
                self.assertIsNotNone(rule.dxf.fill.bgColor.rgb, f"{rng.sqref} has no bgColor set")
                self.assertIsNone(rule.dxf.fill.patternType, f"{rng.sqref} sets patternType, should be unset")
        self.assertTrue(checked_any, "no formula-rule fills found to check")


if __name__ == "__main__":
    unittest.main()
