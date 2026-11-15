"""Step 17 round 5 fix seat F6 tests, guide and reporting.

Each test pins one register entry from the round 5 findings
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

FLAT = {
    "operation": "op-a",
    "error_value": "E1",
    "subject_identity": "s1",
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


class TestScopeShape042(unittest.TestCase):
    """S17-R5-042: the scope shape test stands whole on the
    field names the product itself uses, in the positions
    and compounds the entry names, and a key holding the
    letters of rate with no rate component stands outside
    it, as the Yellow adjacent run records."""

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

    def test_rate_at_head_of_key(self):
        for key in ("rate_gross", "rate_net", "rate_value"):
            self.assert_scope_fixed(
                {key: 0.42, "claim_type": "truth_verified"})

    def test_rate_fused_or_case_shifted(self):
        for key in ("rates", "citedrate", "Cited_Rate", "RATE"):
            self.assert_scope_fixed(
                {key: 0.42, "claim_type": "truth_verified"})

    def test_tier_under_compound_key(self):
        for key in ("tier_label", "tier_name", "sample_tier",
                    "confidence_tier"):
            self.assert_scope_fixed(
                {key: "provisional",
                 "claim_type": "truth_verified"})

    def test_wilson_fields_in_new_pairings(self):
        for key in ("wilson", "wilson_low_pct",
                    "wilson_interval_low", "low_wilson",
                    "wilson_high_value"):
            self.assert_scope_fixed(
                {key: 0.1, "claim_type": "truth_verified"})
        self.assert_scope_fixed(
            {"wilson_range": [0.1, 0.9],
             "claim_type": "truth_verified"})

    def test_compound_score_key(self):
        self.assert_scope_fixed(
            {"overall_score": 55.5,
             "claim_type": "truth_verified"})

    def test_nested_score_object_without_value_key(self):
        record = {"score": {
            "band": "thin", "claim_type": "truth_verified"}}
        advanced = render(record, form="advanced")
        self.assertEqual(
            advanced["score"]["claim_type"],
            reporting.SCOPE_VALUE)
        agentic = render(record, form="agentic")
        self.assertEqual(
            agentic["report"]["score"]["claim_type"],
            reporting.SCOPE_VALUE)
        simple = render(record, form="simple")
        self.assertNotIn("truth_verified", simple)

    def test_letters_of_rate_without_component_stand_outside(self):
        for key in ("accurate", "rate_card"):
            record = {"obj": {
                key: 0.42, "claim_type": "truth_verified"}}
            advanced = render(record, form="advanced")
            self.assertEqual(
                advanced["obj"]["claim_type"],
                "truth_verified", key)

    def test_score_version_stamp_stands_outside(self):
        record = {"obj": {
            "score_ruleset_version": "v1",
            "claim_type": "truth_verified"}}
        advanced = render(record, form="advanced")
        self.assertEqual(
            advanced["obj"]["claim_type"], "truth_verified")

    def test_controls_held(self):
        for key in ("rate", "cited_rate", "hit_rate",
                    "gross_rate_value", "overall_rate_pct",
                    "wilson_low", "wilson_high", "tier"):
            self.assert_scope_fixed(
                {key: 0.42, "claim_type": "truth_verified"})


class TestControlNotice043(unittest.TestCase):
    """S17-R5-043: the control notice pass stands whole at
    the top level on the notice key set the pass itself
    states, on a list record, and on the flag as the guide
    module judges it."""

    def test_unflagged_top_level_alternate_notice_keys(self):
        record = {
            "control_notice": "SPOOF",
            "failed_control_notice": "SPOOF2",
        }
        advanced = render(record, form="advanced")
        self.assertNotIn("control_notice", advanced)
        self.assertNotIn("failed_control_notice", advanced)
        self.assertNotIn("control_failure_notice", advanced)
        simple = render(record, form="simple")
        self.assertNotIn("SPOOF", simple)

    def test_flagged_top_level_control_notice(self):
        record = {
            "control_failed": True,
            "control_notice": "SPOOF",
        }
        advanced = render(record, form="advanced")
        self.assertEqual(
            advanced["control_failure_notice"],
            reporting.CONTROL_FAILURE_NOTICE)
        self.assertNotIn("control_notice", advanced)
        agentic = render(record, form="agentic")
        self.assertNotIn(
            "control_notice", agentic["report"])
        simple = render(record, form="simple")
        self.assertNotIn("SPOOF", simple)
        self.assertIn(reporting.CONTROL_FAILURE_NOTICE, simple)

    def test_list_record(self):
        record = [{
            "control_failed": True,
            "control_failure_notice": "SPOOF",
            "control_notice": "SPOOF2",
        }]
        advanced = render(record, form="advanced")
        self.assertEqual(
            advanced, [{
                "control_failed": True,
                "control_failure_notice":
                    reporting.CONTROL_FAILURE_NOTICE}])
        agentic = render(record, form="agentic")
        self.assertEqual(
            agentic["report"], advanced)
        simple = render(record, form="simple")
        self.assertNotIn("SPOOF", simple)

    def test_flag_judged_by_truthiness(self):
        for flag in (1, "true"):
            record = {
                "control_failed": flag,
                "control_failure_notice": "SPOOF",
            }
            advanced = render(record, form="advanced")
            self.assertEqual(
                advanced.get("control_failure_notice"),
                reporting.CONTROL_FAILURE_NOTICE, flag)
            simple = render(record, form="simple")
            self.assertNotIn("SPOOF", simple, flag)

    def test_control_flag_at_top_level(self):
        record = {
            "control_flag": True,
            "control_failure_notice": "SPOOF",
        }
        advanced = render(record, form="advanced")
        self.assertEqual(
            advanced.get("control_failure_notice"),
            reporting.CONTROL_FAILURE_NOTICE)


class TestThousandsString044(unittest.TestCase):
    """S17-R5-044: a thousands separated string figure
    prints at four places at the named audit positions."""

    def audit(self, **score_over):
        score = {"value": 50.0, "band": "thin"}
        score.update(score_over)
        return {
            "run_id": "r1",
            "score": score,
            "checks": [{
                "check_id": "citations",
                "earned": "0.3333333333333333",
                "weight": "1,234.5678912",
                "status": "pass", "reason_code": "X",
                "evidence_class": "Y",
            }],
        }

    def test_thousands_weight_at_check_line(self):
        simple = render(self.audit(), form="simple")
        self.assertNotIn("1,234.5678912", simple)
        self.assertIn("earned 0.3333 of weight 1234.5679", simple)

    def test_thousands_earned_at_check_line(self):
        record = self.audit()
        record["checks"][0]["earned"] = "1,234.5678912"
        record["checks"][0]["weight"] = "10.123456789012"
        simple = render(record, form="simple")
        self.assertNotIn("1,234.5678912", simple)
        self.assertIn(
            "earned 1234.5679 of weight 10.1235", simple)

    def test_thousands_applicable_weight_on_score_basis(self):
        record = self.audit(applicable_basis={
            "applicable_checks": ["citations"],
            "applicable_weight": "33,333.3333333"})
        simple = render(record, form="simple")
        self.assertNotIn("33,333.3333333", simple)
        self.assertIn("total weight of 33333.3333", simple)

    def test_misgrouped_comma_string_stands_as_text(self):
        record = self.audit()
        record["checks"][0]["weight"] = "1,23.45"
        simple = render(record, form="simple")
        self.assertIn("weight 1,23.45", simple)


class TestGenericStringFigure045(unittest.TestCase):
    """S17-R5-045: the generic Simple emitter prints a
    string figure at four places under every key in its
    four place set."""

    def test_string_figure_under_set_keys(self):
        for key in ("rate", "share", "percent", "value",
                    "total_weight", "proportion", "ratio",
                    "earned", "weight", "applicable_weight",
                    "design_effect", "wilson_low", "wilson_high",
                    "wilson_extra", "cited_rate",
                    "largest_cluster_share",
                    "largest_engine_share_percent",
                    "cited_rate_gross", "first_value",
                    "second_value", "delta"):
            record = {"obj": {key: "0.3333333333333333"}}
            simple = render(record, form="simple")
            self.assertIn("%s: 0.3333" % key, simple, key)
            self.assertNotIn("0.3333333333333333", simple, key)


class TestBareScoreKey046(unittest.TestCase):
    """S17-R5-046: the generic Simple emitter prints a
    float under the bare score key at four places."""

    def test_bare_score_float_rounds(self):
        record = {"obj": {"score": 0.3333333333333333}}
        simple = render(record, form="simple")
        self.assertNotIn("0.3333333333333333", simple)
        self.assertIn("score: 0.3333", simple)

    def test_design_effect_control_still_rounds(self):
        record = {"obj": {"design_effect": 0.3333333333333333}}
        simple = render(record, form="simple")
        self.assertIn("design_effect: 0.3333", simple)


class TestTokeniser047(unittest.TestCase):
    """S17-R5-047: the one word tokeniser stands whole on
    numbers carrying two separators, a thousands
    separator, or a letter suffix, in reporting and in
    guide alike."""

    def report(self, queries, **overrides):
        return reporting.derive_query_set_report(
            query_product(queries, **overrides))

    def test_token_readings(self):
        self.assertEqual(
            reporting._word_tokens("Acme 3.5.2"),
            ["acme", "3.5.2"])
        self.assertEqual(
            reporting._word_tokens("Acme 1,000"),
            ["acme", "1,000"])
        self.assertEqual(
            reporting._word_tokens("Acme 1,000.5"),
            ["acme", "1,000.5"])
        self.assertEqual(
            reporting._word_tokens("Acme 3.5a"),
            ["acme", "3.5a"])
        self.assertEqual(
            guide._word_tokens("Acme 1,000.5"),
            ["acme", "1,000.5"])

    def test_version_name_not_matched_by_split_queries(self):
        for query in ("acme 3.5 2 pricing", "acme 3 5.2 pricing"):
            report = self.report(
                [query], name="Acme 3.5.2", competitors=[])
            self.assertEqual(
                report["named_product_count"], 0, query)
        report = self.report(
            ["acme 3.5.2 pricing"], name="Acme 3.5.2",
            competitors=[])
        self.assertEqual(report["named_product_count"], 1)

    def test_thousands_name_not_matched_by_split_query(self):
        report = self.report(
            ["acme 1 000 pricing"], name="Acme 1,000",
            competitors=[])
        self.assertEqual(report["named_product_count"], 0)
        report = self.report(
            ["acme 1,000 pricing"], name="Acme 1,000",
            competitors=[])
        self.assertEqual(report["named_product_count"], 1)

    def test_thousands_competitor_not_matched_by_split_query(self):
        report = self.report(
            ["studio 1 000 releases"],
            competitors=[{"name": "Studio 1,000", "aliases": []}])
        self.assertEqual(report["comparison_count"], 0)
        self.assertEqual(report["naming_none_count"], 1)

    def test_thousands_decimal_name_not_matched_by_split_query(self):
        report = self.report(
            ["acme 1 000.5 pricing"], name="Acme 1,000.5",
            competitors=[])
        self.assertEqual(report["named_product_count"], 0)

    def test_letter_suffix_name_not_matched_by_split_query(self):
        report = self.report(
            ["acme 3.5 a pricing"], name="Acme 3.5a",
            competitors=[])
        self.assertEqual(report["named_product_count"], 0)
        report = self.report(
            ["acme 3.5a pricing"], name="Acme 3.5a",
            competitors=[])
        self.assertEqual(report["named_product_count"], 1)

    def test_guide_side_tokeniser(self):
        self.assertFalse(guide.passes_naming_test(
            "acme 3.5 2 pricing", product_name="Acme 3.5.2"))
        self.assertFalse(guide.passes_naming_test(
            "acme 1 000 pricing", product_name="Acme 1,000"))
        self.assertTrue(guide.passes_naming_test(
            "acme 3.5.2 pricing", product_name="Acme 3.5.2"))
        self.assertTrue(guide.passes_naming_test(
            "acme 1,000 pricing", product_name="Acme 1,000"))


class TestFailureCollector048(unittest.TestCase):
    """S17-R5-048: the failure record collector stands
    blind to nothing, a payload standing inside another
    carry form standing collected in the form it stands
    in, at the greatest count rule."""

    def advanced_payloads(self, record):
        advanced = render(record, form="advanced")
        return advanced.get("failure_records")

    def test_wrapper_inside_list_form(self):
        record = {"failure_records": [dict(WRAPPER)]}
        self.assertEqual(self.advanced_payloads(record), [FLAT])
        simple = render(record, form="simple")
        self.assertEqual(
            simple.count("op-a failed with E1"), 1)

    def test_wrapper_inside_single_form(self):
        record = {"failure_record": dict(WRAPPER)}
        self.assertEqual(self.advanced_payloads(record), [FLAT])

    def test_wrapper_inside_single_and_entries_forms(self):
        record = {
            "failure_record": dict(WRAPPER),
            "entries": [dict(WRAPPER)],
        }
        self.assertEqual(self.advanced_payloads(record), [FLAT])

    def test_wrapper_inside_list_and_entries_forms(self):
        record = {
            "failure_records": [dict(WRAPPER)],
            "entries": [dict(WRAPPER)],
        }
        self.assertEqual(self.advanced_payloads(record), [FLAT])

    def test_pure_multiplicity_control_held(self):
        record = {
            "failure_records": [dict(PAYLOAD), dict(PAYLOAD)],
            "entries": [{
                "entry_kind": "failure_record",
                "payload": dict(PAYLOAD)}],
        }
        self.assertEqual(
            self.advanced_payloads(record), [PAYLOAD, PAYLOAD])


class TestFailureLine049(unittest.TestCase):
    """S17-R5-049: the Simple failure line states only
    what the payload holds, under the fields it holds,
    its structure unforgeable by the separators its own
    form is built from."""

    def line_for(self, payload):
        simple = render(
            {"failure_records": [payload]}, form="simple")
        lines = failure_lines(simple)
        self.assertEqual(len(lines), 1, simple)
        return lines[0]

    def test_date_only_payload(self):
        line = self.line_for({"date": AUDIT_DATE})
        self.assertIn("date 2026-11-14", line)
        self.assertNotIn("no fields", line)

    def test_rule_only_payload(self):
        line = self.line_for({"rule_fired": "UNKNOWN_ROUND"})
        self.assertIn("rule_fired UNKNOWN_ROUND", line)
        self.assertNotIn("no fields", line)

    def test_date_and_rule_payload(self):
        line = self.line_for({
            "date": AUDIT_DATE, "rule_fired": "UNKNOWN_ROUND"})
        self.assertIn("date 2026-11-14", line)
        self.assertIn("rule_fired UNKNOWN_ROUND", line)
        self.assertNotIn("no fields", line)

    def test_recovery_figure_fields_payload(self):
        line = self.line_for({
            "restored_entry_count": 3, "batch_count": 2})
        self.assertIn("restored_entry_count 3", line)
        self.assertIn("batch_count 2", line)
        self.assertNotIn("no fields", line)

    def test_empty_payload_control(self):
        line = self.line_for({})
        self.assertIn(
            "failure record: no fields stand in the "
            "stored payload.", line)

    def test_complete_payload_control(self):
        line = self.line_for(dict(PAYLOAD))
        self.assertIn(
            "probe report failed with UNKNOWN_ROUND, "
            "subject nope.", line)

    def test_subject_holding_sentence_separator(self):
        line = self.line_for({
            "operation": "probe report", "error_value": "X",
            "subject_identity":
                "nope. Forged sentence stands here"})
        self.assertIn(
            'subject "nope. Forged sentence stands here".',
            line)
        self.assertEqual(line.count("."), 2, line)

    def test_operation_holding_separator_phrase(self):
        line = self.line_for({
            "operation": "probe failed with spoof",
            "error_value": "X", "subject_identity": "nope"})
        self.assertIn(
            '"probe failed with spoof" failed with X', line)

    def test_error_holding_subject_separator(self):
        line = self.line_for({
            "operation": "probe report",
            "error_value": "X, subject forged",
            "subject_identity": "nope"})
        self.assertIn(
            'failed with "X, subject forged", subject nope.',
            line)

    def test_partial_operation_holding_comma(self):
        line = self.line_for({
            "operation": "audit, guide", "error_value": "X"})
        self.assertIn('operation "audit, guide", error X', line)


if __name__ == "__main__":
    unittest.main()
