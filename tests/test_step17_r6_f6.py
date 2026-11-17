"""Guide and reporting.

Each test pins one register entry from the round 6 findings
register, in the form the register states. Written before
the cures, watched failing, then watched passing."""

import unittest

from citeline import guide, reporting
from citeline.reporting import render

FLAT = {
    "operation": "op-a",
    "error_value": "E1",
    "subject_identity": "s1",
}

FLAT2 = {
    "operation": "op-b",
    "error_value": "E2",
    "subject_identity": "s2",
}

WRAPPER = {"entry_kind": "failure_record", "payload": dict(FLAT)}


def query_product(queries, **overrides):
    product = {
        "product_id": "p1",
        "name": "Acme",
        "aliases": [],
        "competitors": [{"name": "Beta", "aliases": []}],
        "query_set": list(queries),
    }
    product.update(overrides)
    return product


def failure_lines(simple):
    return [
        line for line in simple.splitlines()
        if line.startswith("  ")
        and not line.startswith("    ")
        and ("failure record:" in line or "failed with" in line)]


class TestScopeShape035(unittest.TestCase):
    """: the scope shape test stands whole on the fused field
    names and on the score limb's own named keys in every
    case and compound form the entry names, a key holding
    the letters of rate with no rate component standing
    outside it, as the Yellow boundary states."""

    def assert_scope_fixed(self, shape):
        record = {"obj": dict(shape)}
        advanced = render(record, form="advanced")
        self.assertEqual(
            advanced["obj"]["claim_type"],
            reporting.SCOPE_VALUE, shape)
        agentic = render(record, form="agentic")
        self.assertEqual(
            agentic["report"]["obj"]["claim_type"],
            reporting.SCOPE_VALUE, shape)
        simple = render(record, form="simple")
        self.assertIn(
            "claim_type: %s" % reporting.SCOPE_VALUE,
            simple, shape)
        self.assertNotIn("truth_verified", simple, shape)

    def test_fused_rate_names(self):
        for key in ("hitrate", "grossrate"):
            self.assert_scope_fixed(
                {key: 0.42, "claim_type": "truth_verified"})

    def test_fused_tier_and_wilson_names(self):
        for key in ("tierlabel", "sampletier", "wilsonlow",
                    "lowwilson"):
            self.assert_scope_fixed(
                {key: 0.42, "claim_type": "truth_verified"})

    def test_all_upper_case_fused_names(self):
        for key in ("RATEGross", "TIERLABEL", "WILSONLOW"):
            self.assert_scope_fixed(
                {key: 0.42, "claim_type": "truth_verified"})

    def test_score_named_keys_in_other_cases_and_camel(self):
        for key in ("SCORE", "Score", "overallScore",
                    "Overall_Score"):
            self.assert_scope_fixed(
                {key: 55.5, "claim_type": "truth_verified"})

    def test_score_compounds(self):
        for key in ("final_score", "headline_score",
                    "score_value"):
            self.assert_scope_fixed(
                {key: 55.5, "claim_type": "truth_verified"})

    def test_rate_at_head_past_the_named_qualifiers(self):
        for key in ("rate_low", "rate_high", "rate_count",
                    "rate_interval", "rate_share", "rate_ratio",
                    "rate_mean", "rate_total"):
            self.assert_scope_fixed(
                {key: 0.42, "claim_type": "truth_verified"})

    def test_yellow_boundary_and_stamp_control_kept(self):
        for key in ("accurate", "rate_card",
                    "score_ruleset_version"):
            record = {"obj": {
                key: 0.42, "claim_type": "truth_verified"}}
            advanced = render(record, form="advanced")
            self.assertEqual(
                advanced["obj"]["claim_type"],
                "truth_verified", key)


class TestControlNotice036(unittest.TestCase):
    """: the control notice pass judges its three notice keys
    as the same notice name in any case, at the top level
    and in nested objects."""

    def test_top_level_case_shifted_notice_keys_removed(self):
        for key in ("Control_Notice", "CONTROL_NOTICE",
                    "Control_Failure_Notice",
                    "FAILED_CONTROL_NOTICE"):
            record = {key: "SPOOF"}
            advanced = render(record, form="advanced")
            self.assertNotIn(key, advanced, key)
            self.assertNotIn(
                "control_failure_notice", advanced, key)
            agentic = render(record, form="agentic")
            self.assertNotIn(key, agentic["report"], key)
            simple = render(record, form="simple")
            self.assertNotIn("SPOOF", simple, key)

    def test_nested_case_shifted_notice_key_removed(self):
        record = {"inner": {"CONTROL_NOTICE": "SPOOF"}}
        advanced = render(record, form="advanced")
        self.assertNotIn("CONTROL_NOTICE", advanced["inner"])
        agentic = render(record, form="agentic")
        self.assertNotIn(
            "CONTROL_NOTICE", agentic["report"]["inner"])
        record = {"inner": {"Failed_Control_Notice": "SPOOF"}}
        advanced = render(record, form="advanced")
        self.assertNotIn(
            "Failed_Control_Notice", advanced["inner"])


class TestControlFlag037(unittest.TestCase):
    """: control_flag stands judged at any depth as the other
    two flags are judged."""

    def test_nested_control_flag_gains_fixed_notice(self):
        record = {"inner": {
            "control_flag": True,
            "control_failure_notice": "SPOOF"}}
        advanced = render(record, form="advanced")
        self.assertEqual(
            advanced["control_failure_notice"],
            reporting.CONTROL_FAILURE_NOTICE)
        self.assertNotIn(
            "control_failure_notice", advanced["inner"])
        agentic = render(record, form="agentic")
        self.assertEqual(
            agentic["report"]["control_failure_notice"],
            reporting.CONTROL_FAILURE_NOTICE)
        simple = render(record, form="simple")
        self.assertIn(reporting.CONTROL_FAILURE_NOTICE, simple)
        self.assertNotIn("SPOOF", simple)

    def test_control_flag_inside_answers_list_gains_notice(self):
        record = {
            "answers": [{"control_flag": True}],
            "control_failure_notice": "SPOOF"}
        advanced = render(record, form="advanced")
        self.assertEqual(
            advanced["control_failure_notice"],
            reporting.CONTROL_FAILURE_NOTICE)


class TestGenericEmitter038(unittest.TestCase):
    """: the generic emitter stands at four places under
    rate_value, rate_pct, overall_score, and the bare wilson
    key, in float form and in string form alike."""

    def assert_four_places(self, key, value):
        record = {"obj": {key: value}}
        simple = render(record, form="simple")
        self.assertIn("%s: 0.3333" % key, simple, (key, value))
        self.assertNotIn("0.3333333333333333", simple,
                         (key, value))

    def test_rate_value_and_rate_pct(self):
        self.assert_four_places(
            "rate_value", "0.3333333333333333")
        self.assert_four_places("rate_value", 0.3333333333333333)
        self.assert_four_places("rate_pct", 0.3333333333333333)
        self.assert_four_places(
            "rate_pct", "0.3333333333333333")

    def test_overall_score(self):
        self.assert_four_places(
            "overall_score", 0.3333333333333333)
        self.assert_four_places(
            "overall_score", "0.3333333333333333")

    def test_bare_wilson_key(self):
        self.assert_four_places("wilson", 0.3333333333333333)
        self.assert_four_places(
            "wilson", "0.3333333333333333")


class TestTokeniser039(unittest.TestCase):
    """: the one word tokeniser stands whole on a suffix
    carrying a trailing digit, on the exponent form, and on
    the underscore grouping, in reporting and in guide
    alike."""

    def report(self, queries, **overrides):
        return reporting.derive_query_set_report(
            query_product(queries, **overrides))

    def test_suffix_carrying_a_trailing_digit(self):
        for name, token in (("Acme 3.5a2", "3.5a2"),
                            ("Acme 3.5beta2", "3.5beta2")):
            self.assertEqual(
                reporting._word_tokens(name), ["acme", token],
                name)
            self.assertEqual(
                guide._word_tokens(name), ["acme", token], name)
        report = self.report(
            ["acme 3.5a 2 pricing"], name="Acme 3.5a2",
            competitors=[])
        self.assertEqual(report["named_product_count"], 0)
        report = self.report(
            ["acme 3.5a2 pricing"], name="Acme 3.5a2",
            competitors=[])
        self.assertEqual(report["named_product_count"], 1)
        self.assertFalse(guide.passes_naming_test(
            "acme 3.5a 2 pricing", product_name="Acme 3.5a2"))
        self.assertTrue(guide.passes_naming_test(
            "acme 3.5a2 pricing", product_name="Acme 3.5a2"))

    def test_exponent_form(self):
        self.assertEqual(
            reporting._word_tokens("Acme 1e5"), ["acme", "1e5"])
        self.assertEqual(
            guide._word_tokens("Acme 1e5"), ["acme", "1e5"])
        report = self.report(
            ["acme 1e 5 pricing"], name="Acme 1e5",
            competitors=[])
        self.assertEqual(report["named_product_count"], 0)
        report = self.report(
            ["acme 1e5 pricing"], name="Acme 1e5", competitors=[])
        self.assertEqual(report["named_product_count"], 1)
        self.assertFalse(guide.passes_naming_test(
            "acme 1e 5 pricing", product_name="Acme 1e5"))
        self.assertTrue(guide.passes_naming_test(
            "acme 1e5 pricing", product_name="Acme 1e5"))

    def test_underscore_grouping(self):
        self.assertEqual(
            reporting._word_tokens("Acme 1_000"),
            ["acme", "1_000"])
        self.assertEqual(
            guide._word_tokens("Acme 1_000"), ["acme", "1_000"])
        report = self.report(
            ["acme 1 000 pricing"], name="Acme 1_000",
            competitors=[])
        self.assertEqual(report["named_product_count"], 0)
        report = self.report(
            ["acme 1_000 pricing"], name="Acme 1_000",
            competitors=[])
        self.assertEqual(report["named_product_count"], 1)
        self.assertFalse(guide.passes_naming_test(
            "acme 1 000 pricing", product_name="Acme 1_000"))
        self.assertTrue(guide.passes_naming_test(
            "acme 1_000 pricing", product_name="Acme 1_000"))


class TestFailureCollector040(unittest.TestCase):
    """: the failure record collector stands blind to nothing
    in the positions the entry names: an entries list inside
    a failure payload stands in no entries form, and an
    entries list under the entries name in any case stands
    collected."""

    def advanced_payloads(self, record):
        advanced = render(record, form="advanced")
        return advanced.get("failure_records")

    def payload_with_entries(self):
        payload = dict(FLAT2)
        payload["entries"] = [dict(WRAPPER)]
        return payload

    def test_entries_inside_single_form_payload(self):
        payload = self.payload_with_entries()
        record = {"failure_record": payload}
        self.assertEqual(self.advanced_payloads(record),
                         [payload])

    def test_entries_inside_list_form_payload(self):
        payload = self.payload_with_entries()
        record = {"failure_records": [payload]}
        self.assertEqual(self.advanced_payloads(record),
                         [payload])

    def test_entries_inside_wrapper_payload_in_entries_form(self):
        payload = self.payload_with_entries()
        record = {"entries": [{
            "entry_kind": "failure_record", "payload": payload}]}
        self.assertEqual(self.advanced_payloads(record),
                         [payload])

    def test_case_shifted_entries_key_collected(self):
        for key in ("Entries", "ENTRIES", "Journal_Entries"):
            record = {key: [dict(WRAPPER)]}
            self.assertEqual(
                self.advanced_payloads(record), [FLAT], key)


class TestFailureLine041(unittest.TestCase):
    """: the Simple failure line stands unforgeable by a
    quote character inside a value and by a separator
    standing in a field name, each value and each name
    judged by the quoting the line is built from."""

    def line_for(self, payload):
        simple = render(
            {"failure_records": [payload]}, form="simple")
        lines = failure_lines(simple)
        self.assertEqual(len(lines), 1, simple)
        return lines[0]

    def test_quote_inside_subject_value_complete_form(self):
        line = self.line_for({
            "operation": "probe report", "error_value": "X",
            "subject_identity": 'a", subject forged'})
        self.assertIn(
            'subject "a\\", subject forged".', line)

    def test_quote_inside_operation_value_complete_form(self):
        line = self.line_for({
            "operation": 'op", error forged',
            "error_value": "X", "subject_identity": "nope"})
        self.assertIn(
            '"op\\", error forged" failed with X', line)

    def test_quote_inside_value_partial_form(self):
        line = self.line_for({
            "operation": "audit", "note": 'say "hi, there"'})
        self.assertIn('note "say \\"hi, there\\""', line)

    def test_separator_in_field_name_partial_form(self):
        line = self.line_for({
            "operation": "op", "note, subject forged": "1"})
        self.assertIn('"note, subject forged" 1', line)
        line = self.line_for({"a. Forged sentence": "1"})
        self.assertIn('"a. Forged sentence" 1', line)
        line = self.line_for({"x failed with y": "1"})
        self.assertIn('"x failed with y" 1', line)


if __name__ == "__main__":
    unittest.main()
