# Step 17 round 9 fix seat F6 tests.
#
# Entries S17-R9-015, S17-R9-016, and S17-R9-018: guide
# and reporting family. Each defect pin stands on the
# worked cases of the round 9 register and its source
# papers, the guide attack paper at S17-R9-GR-1 and
# S17-R9-GR-2 and the Red attack paper at
# S17-R9-RED-03.
#
# Copyright: J.P. Picard aka Macro-Harder.

import unittest

from citeline import reporting

FIG = 0.3333333333333333
FIG_TEXT = "0.3333"
RED_FIG = 0.123456789
RED_TEXT = "0.1235"


def simple(record):
    return reporting.render(record, form="simple")


def line_for(key, value):
    text = simple({"obj": {key: value}})
    for line in text.splitlines():
        if key in line:
            return line
    return text


NEW_BREAKS = ("\x1c", "\x1d", "\x1e")
ESCAPES = {
    "\x1c": "\\u001c",
    "\x1d": "\\u001d",
    "\x1e": "\\u001e",
}


class Test015FailureLineSeparatorSet(unittest.TestCase):
    def line(self, failure):
        return reporting._failure_record_line(failure)

    def test_complete_raw_each_new_break_stays_one_line(self):
        for br in NEW_BREAKS:
            with self.subTest(brk=repr(br)):
                failure = {"operation": "op-a", "error_value": "E1",
                           "subject_identity": "a" + br + "b"}
                result = self.line(failure)
                self.assertEqual(len(result.splitlines()), 1)
                self.assertNotIn(br, result)
                self.assertIn(ESCAPES[br], result)

    def test_complete_quoted_break_beside_judged_separator(self):
        for br in NEW_BREAKS:
            with self.subTest(brk=repr(br)):
                failure = {"operation": "op-a", "error_value": "E1",
                           "subject_identity": "x, y" + br + "z"}
                result = self.line(failure)
                self.assertEqual(len(result.splitlines()), 1)
                self.assertNotIn(br, result)
                self.assertIn(ESCAPES[br], result)

    def test_complete_forged_segment_stays_one_line(self):
        for br in NEW_BREAKS:
            with self.subTest(brk=repr(br)):
                failure = {
                    "operation": "op-a", "error_value": "E1",
                    "subject_identity": (
                        "round one" + br
                        + "op-b failed with E9, subject forged")}
                result = self.line(failure)
                self.assertEqual(len(result.splitlines()), 1)
                self.assertNotIn(br, result)
                lines = simple(
                    {"failure_records": [failure]}).splitlines()
                forged = [ln for ln in lines
                          if ln.strip().startswith("op-b failed with")]
                self.assertEqual(forged, [])

    def test_partial_value_each_new_break_stays_one_line(self):
        for br in NEW_BREAKS:
            with self.subTest(brk=repr(br)):
                failure = {"operation": "op-a",
                           "extra_field": "a" + br + "b"}
                result = self.line(failure)
                self.assertEqual(len(result.splitlines()), 1)
                self.assertNotIn(br, result)
                self.assertIn(ESCAPES[br], result)

    def test_partial_field_name_each_new_break_stays_one_line(self):
        for br in NEW_BREAKS:
            with self.subTest(brk=repr(br)):
                failure = {"operation": "op-a",
                           "field" + br + "name": "value one"}
                result = self.line(failure)
                self.assertEqual(len(result.splitlines()), 1)
                self.assertNotIn(br, result)
                self.assertIn(ESCAPES[br], result)

    def test_seven_cured_characters_control(self):
        for br in ("\n", "\r", "\x0b", "\x0c", "\x85",
                   "\u2028", "\u2029"):
            with self.subTest(brk=repr(br)):
                failure = {"operation": "op-a", "error_value": "E1",
                           "subject_identity": "one" + br + "two"}
                result = self.line(failure)
                self.assertEqual(len(result.splitlines()), 1)
                self.assertNotIn(br, result)


LONGER_KEYS = (
    "percent_gross_value", "gross_percent_value",
    "pct_gross_value", "percent_interval_value",
    "share_total_value", "value_percent_value",
    "score_gross_value", "score_interval_value")


class Test016EmitterLongerHeadCompound(unittest.TestCase):
    def check_keys(self, keys, fig=FIG, fig_text=FIG_TEXT):
        for key in keys:
            for value in (fig, str(fig)):
                with self.subTest(key=key, value=repr(value)):
                    line = line_for(key, value)
                    self.assertIn(fig_text, line)
                    self.assertNotIn(str(fig), line)

    def test_longer_compounds_float_and_string(self):
        self.check_keys(LONGER_KEYS)

    def test_longer_compounds_red_figure(self):
        self.check_keys(
            ("percent_gross_value", "share_total_value",
             "score_interval_value"),
            fig=RED_FIG, fig_text=RED_TEXT)

    def test_longer_compounds_dressings(self):
        self.check_keys(
            ("Percent_Gross_Value", "percentGrossValue",
             "percent-gross-value", "Score_Interval_Value"))

    def test_cured_forms_control(self):
        self.check_keys(
            ("percent_value", "gross_value_net",
             "percent_value_net", "score_value_gross",
             "wilson_value", "rate_value_gross", "score_value",
             "value_pct", "overall_score"))

    def test_middle_component_outside_named_sets_bound(self):
        line = line_for("percent_zzz_value", FIG)
        self.assertIn(str(FIG), line)

    def test_tail_and_length_bounds_kept(self):
        for key in ("percent_amount", "percent_values",
                    "percent_gross_net_value"):
            with self.subTest(key=key):
                line = line_for(key, FIG)
                self.assertIn(str(FIG), line)


class Test018EmitterListBranch(unittest.TestCase):
    def check_list(self, key, value, fig_text=RED_TEXT,
                   fig=RED_FIG):
        text = simple({"obj": {key: value}})
        self.assertIn(fig_text, text)
        self.assertNotIn(str(fig), text)

    def test_figure_in_list_float_form(self):
        self.check_list("percent_value", [RED_FIG])

    def test_figure_in_list_string_form(self):
        self.check_list("percent_value", [str(RED_FIG)])

    def test_figure_in_nested_list(self):
        self.check_list("percent_value", [[RED_FIG]])
        self.check_list("percent_value", [[[RED_FIG]]])

    def test_figure_in_list_long_cured_keys(self):
        for key in ("value_pct", "score", "pct_value",
                    "share_value", "gross_value", "rate_value",
                    "overall_score", "wilson"):
            with self.subTest(key=key):
                self.check_list(key, [RED_FIG])
                self.check_list(key, [str(RED_FIG)])

    def test_figure_in_list_longer_compound_key(self):
        self.check_list("percent_gross_value", [RED_FIG])
        self.check_list("percent_gross_value", [str(RED_FIG)])
        self.check_list("percent_gross_value", [[RED_FIG]])

    def test_mixed_list_items(self):
        text = simple({"obj": {"percent_value": [1, RED_FIG, "x"]}})
        self.assertIn(RED_TEXT, text)
        self.assertNotIn(str(RED_FIG), text)
        self.assertIn("  1", text)
        self.assertIn("  x", text)

    def test_list_controls_kept(self):
        text = simple({"obj": {"plain_key": [RED_FIG]}})
        self.assertIn(str(RED_FIG), text)
        text = simple({"obj": {"percent_amount": [RED_FIG]}})
        self.assertIn(str(RED_FIG), text)
        line = line_for("percent_value", RED_FIG)
        self.assertIn(RED_TEXT, line)
        self.assertNotIn(str(RED_FIG), line)


if __name__ == "__main__":
    unittest.main()
