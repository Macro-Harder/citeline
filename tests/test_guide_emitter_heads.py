# Verdict tests.
# Entries to: guide and reporting family. Each defect
# pin stands on the worked cases of the round 8
# register and its source papers, the guide attack
# paper at GR-1 to GR-4 and the Red paper at RED-07 and
# RED-08, merged into in the register form.
# Copyright: J.P. Picard aka Macro-Harder.

import unittest

from citeline import guide, reporting

SCOPE = reporting.SCOPE_VALUE
FIG = 0.3333333333333333
FIG_TEXT = "0.3333"
RED_FIG = 0.123456789


def advanced(record):
    return reporting.render(record, form="advanced")


def simple(record):
    return reporting.render(record, form="simple")


def claim_after(key):
    body = advanced({"obj": {key: 0.42, "claim_type": "truth_verified"}})
    return body["obj"].get("claim_type")


class Test020ScopeHeadQualifiers(unittest.TestCase):
    def test_score_head_past_six_qualifiers(self):
        for key in ("score_gross", "score_net", "score_low",
                    "score_high", "score_count", "score_total",
                    "score_interval", "score_share", "score_ratio",
                    "score_mean", "score_confidence"):
            with self.subTest(key=key):
                self.assertEqual(claim_after(key), SCOPE)

    def test_rate_basis(self):
        self.assertEqual(claim_after("rate_basis"), SCOPE)

    def test_score_head_on_rate_qualifier_words(self):
        for key in ("score_percent", "score_value"):
            with self.subTest(key=key):
                self.assertEqual(claim_after(key), SCOPE)

    def test_worked_cases_in_agentic_and_simple(self):
        for key in ("score_gross", "score_confidence", "rate_basis"):
            with self.subTest(key=key):
                record = {"obj": {key: 0.42,
                                   "claim_type": "truth_verified"}}
                env = reporting.render(record, form="agentic")
                self.assertEqual(
                    env["report"]["obj"]["claim_type"], SCOPE)
                self.assertIn("claim_type: %s" % SCOPE, simple(record))

    def test_cured_head_forms_still_corrected(self):
        for key in ("score_value", "score_band", "score_delta",
                    "score_basis", "score_range", "score_pct",
                    "rate_band", "rate_delta", "rate_range",
                    "rate_confidence", "rate_gross"):
            with self.subTest(key=key):
                self.assertEqual(claim_after(key), SCOPE)

    def test_yellow_boundary_controls_kept(self):
        for key in ("accurate", "rate_card"):
            with self.subTest(key=key):
                self.assertEqual(claim_after(key), "truth_verified")

    def test_score_head_no_qualifier_control_kept(self):
        self.assertEqual(
            claim_after("score_ruleset_version"), "truth_verified")


class Test021EmitterHeadValue(unittest.TestCase):
    def line_for(self, key, value):
        text = simple({"obj": {key: value}})
        for line in text.splitlines():
            if key in line:
                return line
        return text

    def check_keys(self, keys, fig=FIG, fig_text=FIG_TEXT):
        for key in keys:
            for value in (fig, str(fig)):
                with self.subTest(key=key, value=repr(value)):
                    line = self.line_for(key, value)
                    self.assertIn(fig_text, line)
                    self.assertNotIn(str(fig), line)

    def test_head_value_compounds_float_and_string(self):
        self.check_keys(("percent_value", "pct_value", "share_value",
                         "gross_value", "net_value"))

    def test_head_value_compounds_red_figure(self):
        self.check_keys(("percent_value", "pct_value", "share_value"),
                        fig=RED_FIG, fig_text="0.1235")

    def test_cured_forms_control(self):
        self.check_keys(("score_value", "value_pct", "overall_pct",
                         "score_pct", "named_pct", "gross_pct",
                         "low_wilson", "rate_pct", "overall_score",
                         "score"))


class Test022TokeniserComposedSuffix(unittest.TestCase):
    def test_token_readings_whole_in_both_modules(self):
        cases = (
            ("Acme 3.5a2_3", ["acme", "3.5a2_3"]),
            ("Acme 3.5a_2_3", ["acme", "3.5a_2_3"]),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(reporting._word_tokens(text), expected)
                self.assertEqual(guide._word_tokens(text), expected)

    def test_split_query_counts_nothing_named(self):
        pairs = (
            ("Acme 3.5a2_3", "acme 3.5a2 3 pricing"),
            ("Acme 3.5a_2_3", "acme 3.5a_2 3 pricing"),
        )
        for name, query in pairs:
            with self.subTest(name=name):
                report = reporting.derive_query_set_report({
                    "name": name, "query_set": [query]})
                self.assertEqual(report["named_product_count"], 0)
                self.assertFalse(
                    guide.passes_naming_test(query, product_name=name))

    def test_exact_form_still_named(self):
        for name in ("Acme 3.5a2_3", "Acme 3.5a_2_3"):
            with self.subTest(name=name):
                self.assertTrue(guide.passes_naming_test(
                    name.lower() + " pricing", product_name=name))

    def test_cured_suffix_forms_control(self):
        cases = (
            ("Acme 3.5a_2", ["acme", "3.5a_2"]),
            ("Acme 3.5ab_2", ["acme", "3.5ab_2"]),
            ("Acme 3.5a2", ["acme", "3.5a2"]),
            ("Acme 1e1_0_0", ["acme", "1e1_0_0"]),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(reporting._word_tokens(text), expected)
                self.assertEqual(guide._word_tokens(text), expected)


BREAKS = ("\x0b", "\x0c", "\x85", "\u2028", "\u2029")


class Test023FailureLineBreakSet(unittest.TestCase):
    def line(self, failure):
        return reporting._failure_record_line(failure)

    def test_complete_raw_each_break_stays_one_line(self):
        for br in BREAKS:
            with self.subTest(brk=repr(br)):
                failure = {"operation": "op-a", "error_value": "E1",
                           "subject_identity": "a" + br + "b"}
                result = self.line(failure)
                self.assertEqual(len(result.splitlines()), 1)
                self.assertNotIn(br, result)

    def test_complete_quoted_break_beside_judged_separator(self):
        for br in ("\u2028", "\x0b"):
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

    def test_partial_value_each_break_stays_one_line(self):
        for br in BREAKS:
            with self.subTest(brk=repr(br)):
                failure = {"operation": "op-a",
                           "extra_field": "a" + br + "b"}
                result = self.line(failure)
                self.assertEqual(len(result.splitlines()), 1)
                self.assertNotIn(br, result)

    def test_partial_field_name_with_break_stays_one_line(self):
        failure = {"operation": "op-a",
                   "field\u2028name": "value one"}
        result = self.line(failure)
        self.assertEqual(len(result.splitlines()), 1)
        self.assertNotIn("\u2028", result)

    def test_newline_and_carriage_return_controls(self):
        for br in ("\n", "\r"):
            with self.subTest(brk=repr(br)):
                failure = {"operation": "op-a", "error_value": "E1",
                           "subject_identity": "one" + br + "two"}
                result = self.line(failure)
                self.assertEqual(len(result.splitlines()), 1)
                self.assertNotIn(br, result)


if __name__ == "__main__":
    unittest.main()
