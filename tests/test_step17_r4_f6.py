"""Step 17 round 4 fix seat F6 tests, guide and reporting.

Each test pins one register entry from the round 4 findings
register, in the form the register states. Written before
the cures, watched failing, then watched passing.
"""

import unittest

from citeline import guide, reporting
from citeline.reporting import render

AUDIT_DATE = "2026-11-14"

PAYLOAD = {
    "operation": "probe report",
    "error_value": "UNKNOWN_ROUND",
    "subject_identity": "nope",
    "date": AUDIT_DATE,
    "rule_fired": "UNKNOWN_ROUND",
}


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


class TestScopeShape044(unittest.TestCase):
    """S17-R4-044: the fixed scope shape test stands on the
    pass own stated rule whole, the rate field names the
    product itself uses and the rate interval fields
    among them."""

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

    def test_per_competitor_cited_rate_shape(self):
        record = {"per_competitor": [{
            "name": "Beta", "cited_rate": 0.5,
            "claim_type": "truth_verified"}]}
        advanced = render(record, form="advanced")
        self.assertEqual(
            advanced["per_competitor"][0]["claim_type"],
            reporting.SCOPE_VALUE)
        agentic = render(record, form="agentic")
        self.assertEqual(
            agentic["report"]["per_competitor"][0]["claim_type"],
            reporting.SCOPE_VALUE)
        simple = render(record, form="simple")
        self.assertNotIn("truth_verified", simple)

    def test_probe_report_rate_fields(self):
        self.assert_scope_fixed(
            {"cited_rate_gross": 0.42,
             "claim_type": "truth_verified"})
        self.assert_scope_fixed(
            {"cited_rate_net": 0.42,
             "claim_type": "truth_verified"})
        self.assert_scope_fixed(
            {"cited_rate": 0.42,
             "claim_type": "truth_verified"})

    def test_wilson_interval_fields_without_tier(self):
        self.assert_scope_fixed(
            {"wilson_low": 0.1, "wilson_high": 0.9,
             "claim_type": "truth_verified"})

    def test_wilson_low_alone(self):
        self.assert_scope_fixed(
            {"wilson_low": 0.1,
             "claim_type": "truth_verified"})


class TestControlNotice045(unittest.TestCase):
    """S17-R4-045: the control notice pass stands on every
    record the rendering pipeline hands it, marker or no
    marker."""

    def test_flagged_record_no_marker_top_and_nested(self):
        record = {
            "control_failed": True,
            "control_failure_notice": "SPOOF TOP",
            "nested": {"control_failure_notice": "SPOOF NESTED"},
        }
        advanced = render(record, form="advanced")
        self.assertEqual(
            advanced["control_failure_notice"],
            reporting.CONTROL_FAILURE_NOTICE)
        self.assertNotIn(
            "control_failure_notice", advanced["nested"])
        agentic = render(record, form="agentic")
        self.assertEqual(
            agentic["report"]["control_failure_notice"],
            reporting.CONTROL_FAILURE_NOTICE)
        simple = render(record, form="simple")
        self.assertNotIn("SPOOF TOP", simple)
        self.assertNotIn("SPOOF NESTED", simple)

    def test_flagged_record_no_marker_gains_fixed_notice(self):
        record = {
            "round_id": "r1",
            "control_failed": True,
            "nested": {"control_failure_notice": "SPOOF NESTED"},
        }
        advanced = render(record, form="advanced")
        self.assertEqual(
            advanced.get("control_failure_notice"),
            reporting.CONTROL_FAILURE_NOTICE)
        self.assertNotIn(
            "control_failure_notice", advanced["nested"])
        simple = render(record, form="simple")
        self.assertNotIn("SPOOF NESTED", simple)
        self.assertIn(reporting.CONTROL_FAILURE_NOTICE, simple)

    def test_unflagged_record_no_marker_loses_spoofed_notice(self):
        record = {
            "control_failure_notice": "SPOOF TOP",
            "nested": {"control_notice": "SPOOF NESTED"},
        }
        advanced = render(record, form="advanced")
        self.assertNotIn("control_failure_notice", advanced)
        self.assertNotIn("control_notice", advanced["nested"])

    def test_guide_shaped_record_control(self):
        record = {
            "opening_text": "Line. Sentence.",
            "actions": [],
            "refused": False,
            "control_failed": True,
            "nested": {"control_failure_notice": "SPOOF NESTED"},
        }
        advanced = render(record, form="advanced")
        self.assertEqual(
            advanced["control_failure_notice"],
            reporting.CONTROL_FAILURE_NOTICE)
        self.assertNotIn(
            "control_failure_notice", advanced["nested"])


class TestPrecision046(unittest.TestCase):
    """S17-R4-046: precision stands at the audit Simple
    check lines and the score basis line for figures
    carried as strings as for figures carried as floats."""

    def audit(self, **score_over):
        score = {"value": 50.0, "band": "thin"}
        score.update(score_over)
        return {
            "run_id": "r1",
            "score": score,
            "checks": [{
                "check_id": "citations",
                "earned": "0.3333333333333333",
                "weight": "10.123456789012",
                "status": "pass", "reason_code": "X",
                "evidence_class": "Y",
            }],
        }

    def test_string_check_figures_round(self):
        simple = render(self.audit(), form="simple")
        self.assertNotIn("0.3333333333333333", simple)
        self.assertNotIn("10.123456789012", simple)
        self.assertIn("earned 0.3333 of weight 10.1235", simple)

    def test_string_applicable_weight_rounds(self):
        record = self.audit(applicable_basis={
            "applicable_checks": ["citations"],
            "applicable_weight": "33.333333333333336"})
        simple = render(record, form="simple")
        self.assertNotIn("33.333333333333336", simple)
        self.assertIn("total weight of 33.3333", simple)

    def test_float_check_figures_control(self):
        record = self.audit()
        record["checks"][0]["earned"] = 0.3333333333333333
        record["checks"][0]["weight"] = 10.123456789012
        simple = render(record, form="simple")
        self.assertIn("earned 0.3333 of weight 10.1235", simple)


class TestDesignEffect047(unittest.TestCase):
    """S17-R4-047: the generic emitter four place set
    stands over the design_effect key."""

    def test_design_effect_rounds(self):
        record = {
            "kind": "probe_report", "rates": {},
            "design_effect": 7 / 3, "effective_n": 3,
        }
        simple = render(record, form="simple")
        self.assertNotIn("2.3333333333333335", simple)
        self.assertIn("design_effect: 2.3333", simple)

    def test_share_control_still_rounds(self):
        simple = render(
            {"largest_cluster_share": 1 / 3}, form="simple")
        self.assertIn("largest_cluster_share: 0.3333", simple)


class TestDecimalToken048(unittest.TestCase):
    """S17-R4-048: the tokeniser judges a decimal number
    as one word under brief Section 5.1, on the name side
    and on the query side alike, at the query set
    derivation, and at the guide side tokeniser of the
    same form."""

    def report(self, queries, **overrides):
        return reporting.derive_query_set_report(
            query_product(queries, **overrides))

    def test_decimal_product_name_not_matched_by_split_digits(self):
        report = self.report(
            ["acme 3 5 pricing"], name="Acme 3.5", competitors=[])
        self.assertEqual(report["named_product_count"], 0)
        self.assertEqual(report["bare_topic_count"], 1)

    def test_decimal_competitor_name_not_matched_by_split_digits(self):
        report = self.report(
            ["studio 2 0 releases"],
            competitors=[{"name": "Studio 2.0", "aliases": []}])
        self.assertEqual(report["comparison_count"], 0)
        self.assertEqual(report["naming_none_count"], 1)

    def test_decimal_query_still_matches_decimal_name(self):
        report = self.report(
            ["acme 3.5 pricing"], name="Acme 3.5", competitors=[])
        self.assertEqual(report["named_product_count"], 1)

    def test_guide_side_decimal_tokeniser(self):
        self.assertFalse(guide.passes_naming_test(
            "acme 3 5 pricing", product_name="Acme 3.5"))
        self.assertTrue(guide.passes_naming_test(
            "acme 3.5 pricing", product_name="Acme 3.5"))
        self.assertEqual(
            reporting._word_tokens("Acme 3.5 pricing"),
            ["acme", "3.5", "pricing"])


class TestFailureCollector049(unittest.TestCase):
    """S17-R4-049: a payload standing in two carry forms
    at once surfaces as one stored record, exactly in
    count as in order and content on every composition
    of its forms."""

    def advanced_payloads(self, record):
        advanced = render(record, form="advanced")
        return advanced.get("failure_records")

    def test_list_and_entry_pairing(self):
        record = {
            "failure_records": [dict(PAYLOAD)],
            "entries": [{
                "entry_kind": "failure_record",
                "payload": dict(PAYLOAD)}],
        }
        self.assertEqual(
            self.advanced_payloads(record), [PAYLOAD])
        simple = render(record, form="simple")
        self.assertEqual(
            simple.count("probe report failed with UNKNOWN_ROUND"), 1)

    def test_list_and_single_pairing(self):
        record = {
            "failure_records": [dict(PAYLOAD)],
            "failure_record": dict(PAYLOAD),
        }
        self.assertEqual(
            self.advanced_payloads(record), [PAYLOAD])
        agentic = render(record, form="agentic")
        self.assertEqual(
            agentic["report"]["failure_records"], [PAYLOAD])

    def test_single_and_entry_pairing(self):
        record = {
            "failure_record": dict(PAYLOAD),
            "entries": [{
                "entry_kind": "failure_record",
                "payload": dict(PAYLOAD)}],
        }
        self.assertEqual(
            self.advanced_payloads(record), [PAYLOAD])

    def test_two_identical_in_list_and_entries(self):
        record = {
            "failure_records": [dict(PAYLOAD), dict(PAYLOAD)],
            "entries": [
                {"entry_kind": "failure_record",
                 "payload": dict(PAYLOAD)},
                {"entry_kind": "failure_record",
                 "payload": dict(PAYLOAD)}],
        }
        self.assertEqual(
            self.advanced_payloads(record), [PAYLOAD, PAYLOAD])

    def test_distinct_payloads_split_across_forms_control(self):
        other = dict(PAYLOAD, operation="audit",
                     error_value="UNKNOWN_PRODUCT",
                     rule_fired="UNKNOWN_PRODUCT")
        record = {
            "failure_records": [dict(PAYLOAD)],
            "entries": [{
                "entry_kind": "failure_record",
                "payload": dict(other)}],
        }
        self.assertEqual(
            self.advanced_payloads(record), [PAYLOAD, other])

    def test_duplicates_inside_one_form_control(self):
        record = {"failure_records": [dict(PAYLOAD), dict(PAYLOAD)]}
        self.assertEqual(
            self.advanced_payloads(record), [PAYLOAD, PAYLOAD])


class TestFailureSimple074(unittest.TestCase):
    """S17-R4-074: the Simple form of a stored failure
    record states the stored payload as stored, no value
    standing in the line that the store does not hold."""

    def test_empty_payload_states_no_invented_values(self):
        simple = render({"failure_records": [{}]}, form="simple")
        self.assertNotIn("none failed with none", simple)
        self.assertNotIn("subject none", simple)
        self.assertIn("Failure records.", simple)
        self.assertIn(
            "failure record: no fields stand in the stored "
            "payload.", simple)

    def test_partial_payload_states_only_stored_fields(self):
        record = {"failure_records": [{"operation": "probe report"}]}
        simple = render(record, form="simple")
        self.assertNotIn("failed with none", simple)
        self.assertNotIn("subject none", simple)
        self.assertIn("operation probe report", simple)

    def test_complete_payload_line_control(self):
        simple = render(
            {"failure_records": [dict(PAYLOAD)]}, form="simple")
        self.assertIn(
            "probe report failed with UNKNOWN_ROUND, "
            "subject nope.", simple)


if __name__ == "__main__":
    unittest.main()
