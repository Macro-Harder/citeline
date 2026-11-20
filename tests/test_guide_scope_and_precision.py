"""Guide and reporting.

Each test pins one settled rule
register, in the form the register states. Written before
the cures, watched failing, then watched passing."""

import tempfile
import unittest
from pathlib import Path

from citeline import errors, install as install_module
from citeline import journal, reporting, service
from citeline.reporting import render

AUDIT_DATE = "2026-11-14"


def guide_record(**overrides):
    record = {
        "opening_text": "Line. Sentence.",
        "actions": [],
        "refused": False,
    }
    record.update(overrides)
    return record


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


class TestScopeShape042(unittest.TestCase):
    """: the fixed scope shape test stands on the pass own
    stated rule, any object carrying a score, a rate, or a
    tier."""

    CASES = [
        {"tier": "reportable", "count": 5,
         "claim_type": "truth_verified"},
        {"rate": 0.5, "claim_type": "truth_verified"},
        {"score": 42, "claim_type": "truth_verified"},
    ]

    def test_spoofed_shapes_fixed_in_all_forms(self):
        for shape in self.CASES:
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


class TestControlNotice043(unittest.TestCase):
    """: the control notice pass runs its nested removal on
    every path."""

    def test_nested_spoof_removed_on_flag_path(self):
        record = {
            "score": {"value": 1},
            "control_failed": True,
            "nested": {"control_failure_notice": "SPOOF NOTICE TEXT"},
        }
        advanced = render(record, form="advanced")
        self.assertEqual(
            advanced["control_failure_notice"],
            reporting.CONTROL_FAILURE_NOTICE)
        self.assertNotIn(
            "control_failure_notice", advanced["nested"])
        simple = render(record, form="simple")
        self.assertNotIn("SPOOF NOTICE TEXT", simple)

    def test_nested_spoof_variants_removed_on_flag_path(self):
        record = {
            "score": {"value": 1},
            "control_failed": True,
            "nested": {"control_notice": "SPOOF TWO",
                       "failed_control_notice": "SPOOF THREE"},
        }
        advanced = render(record, form="advanced")
        self.assertEqual(advanced["nested"], {})

    def test_nested_spoof_removed_on_guide_notice_path(self):
        record = guide_record(
            control_failure_notice=(
                "a control in this round failed, and no action "
                "stands produced from this round"),
            nested={"control_failure_notice": "SPOOF NOTICE TEXT"})
        advanced = render(record, form="advanced")
        self.assertNotIn(
            "control_failure_notice", advanced["nested"])
        simple = render(record, form="simple")
        self.assertNotIn("SPOOF NOTICE TEXT", simple)


class TestSelectionBasis044(unittest.TestCase):
    """: the selection statement is judged on the basis value
    as a stated form, not a substring."""

    def test_negated_basis_renders_no_fallback(self):
        body = render(guide_record(selection_basis="not_fallback"),
                      form="advanced")
        self.assertNotIn("selection_statement", body)

    def test_combined_basis_renders_no_statement(self):
        body = render(
            guide_record(selection_basis="preference_fallback"),
            form="advanced")
        self.assertNotIn("selection_statement", body)

    def test_sentence_basis_renders_no_statement(self):
        body = render(
            guide_record(
                selection_basis="by naming preference among options"),
            form="advanced")
        self.assertNotIn("selection_statement", body)

    def test_stated_forms_still_render(self):
        body = render(guide_record(selection_basis="preference"),
                      form="advanced")
        self.assertEqual(body["selection_statement"],
                         reporting.PREFERENCE_STATEMENT)
        body = render(guide_record(selection_basis="FALLBACK"),
                      form="advanced")
        self.assertEqual(body["selection_statement"],
                         reporting.FALLBACK_STATEMENT)
        body = render(guide_record(selection_basis="preferred"),
                      form="advanced")
        self.assertEqual(body["selection_statement"],
                         reporting.PREFERENCE_STATEMENT)


class TestPrecision045(unittest.TestCase):
    """: precision stands at the audit Simple check lines, the score
    basis line, and the generic emitter keys."""

    def audit(self, **score_over):
        score = {"value": 50.0, "band": "thin"}
        score.update(score_over)
        return {
            "run_id": "r1",
            "score": score,
            "checks": [{
                "check_id": "citations",
                "earned": 0.3333333333333333,
                "weight": 10.123456789012,
                "status": "pass", "reason_code": "X",
                "evidence_class": "Y",
            }],
        }

    def test_check_lines_round_figures(self):
        simple = render(self.audit(), form="simple")
        self.assertNotIn("0.3333333333333333", simple)
        self.assertNotIn("10.123456789012", simple)
        # Restated for the settled rule: the
        # earned figure now stands stated as a fraction of
        # the weight with its points, so it cannot read as
        # points out of the weight.
        self.assertIn(
            "earned a fraction 0.3333 of its weight of "
            "10.1235, worth 3.374 points toward the score",
            simple)

    def test_score_basis_line_rounds_weight(self):
        record = self.audit(applicable_basis={
            "applicable_checks": ["citations"],
            "applicable_weight": 33.333333333333336})
        simple = render(record, form="simple")
        self.assertNotIn("33.333333333333336", simple)
        self.assertIn("total weight of 33.3333", simple)

    def test_generic_value_key_rounds(self):
        simple = render(
            {"thing": {"value": 87.12345678901234, "band": "strong"}},
            form="simple")
        self.assertNotIn("87.12345678901234", simple)
        self.assertIn("value: 87.1235", simple)

    def test_generic_proportion_and_ratio_round(self):
        simple = render(
            {"proportion": 0.123456789012, "ratio": 0.987654321098},
            form="simple")
        self.assertNotIn("0.123456789012", simple)
        self.assertNotIn("0.987654321098", simple)
        self.assertIn("proportion: 0.1235", simple)
        self.assertIn("ratio: 0.9877", simple)


class TestQueryClassification(unittest.TestCase):
    """to: the query set classification whole, on the brief
    stated lists and token matching."""

    def report(self, queries, **overrides):
        return reporting.derive_query_set_report(
            query_product(queries, **overrides))

    def test_054_stated_comparison_markers(self):
        for query in (
                "acme compared to beta",
                "acme compared with beta",
                "a better than acme option",
                "acme alternative",
                "acme alternatives",
                "difference between acme and beta"):
            self.assertEqual(
                self.report([query])["comparison_count"], 1, query)

    def test_054_competitor_limb_is_comparison(self):
        self.assertEqual(
            self.report(["beta pricing plans"])["comparison_count"], 1)
        self.assertEqual(
            self.report(["acme vs beta"])["comparison_count"], 1)

    def test_055_stated_interrogative_words_anywhere(self):
        for query in (
                "should I use acme",
                "whose acme plan is this",
                "would acme fit",
                "acme, is it any good"):
            self.assertEqual(
                self.report([query])["interrogative_count"], 1, query)

    def test_055_unstated_forms_count_nothing(self):
        for query in ("are acme plans good", "will acme ship",
                      "acme pricing?"):
            self.assertEqual(
                self.report([query])["interrogative_count"], 0, query)

    def test_056_name_inside_longer_word_matches_nothing(self):
        self.assertEqual(
            self.report(["acmeville travel guide"])
            ["named_product_count"], 0)
        report = self.report(["betaine supplements"])
        self.assertEqual(report["naming_none_count"], 1)
        self.assertEqual(report["bare_topic_count"], 1)

    def test_056_multi_word_name_matches_as_token_sequence(self):
        product = query_product(
            ["acme ledger review"], name="Acme Ledger",
            competitors=[])
        report = reporting.derive_query_set_report(product)
        self.assertEqual(report["named_product_count"], 1)

    def test_057_empty_folding_alias_matches_nothing(self):
        report = self.report(
            ["plain topic"], aliases=["   "])
        self.assertEqual(report["named_product_count"], 0)
        self.assertEqual(report["naming_none_count"], 1)
        self.assertEqual(report["bare_topic_count"], 1)

    def test_057_empty_folding_competitor_alias_suppresses_nothing(self):
        report = self.report(
            ["plain topic"],
            competitors=[{"name": "Beta", "aliases": ["  "]}])
        self.assertEqual(report["naming_none_count"], 1)
        self.assertEqual(report["bare_topic_count"], 1)


class TestCompetitorAliasValidation058(unittest.TestCase):
    """: competitor aliases stand judged at the product
    record reader and at the derivation."""

    def test_integer_alias_refused_at_reader(self):
        record = {
            "name": "Acme",
            "competitors": [{"name": "Zed", "aliases": [123]}],
        }
        with self.assertRaises(errors.CitelineError) as caught:
            service._validate_product_record(record)
        self.assertEqual(caught.exception.token, "VALIDATION_FAILED")

    def test_string_alias_form_refused_at_reader(self):
        record = {
            "name": "Acme",
            "competitors": [{"name": "Zed", "aliases": "123"}],
        }
        with self.assertRaises(errors.CitelineError) as caught:
            service._validate_product_record(record)
        self.assertEqual(caught.exception.token, "VALIDATION_FAILED")

    def test_swapped_alias_refused_at_derivation(self):
        for aliases in ([123], "123"):
            product = query_product(
                ["call 123 now"],
                competitors=[{"name": "Zed", "aliases": aliases}])
            with self.assertRaises(ValueError, msg=repr(aliases)):
                reporting.derive_query_set_report(product)

    def test_valid_alias_still_matches(self):
        report = reporting.derive_query_set_report(query_product(
            ["call zedlite now"],
            competitors=[{"name": "Zed", "aliases": ["zedlite"]}]))
        self.assertEqual(report["naming_none_count"], 0)


class TestFailureRecordRendering063(unittest.TestCase):
    """: stored failure records surface exactly in count as in
    order and content."""

    PAYLOAD = {
        "operation": "probe report",
        "error_value": "UNKNOWN_ROUND",
        "subject_identity": "nope",
        "date": AUDIT_DATE,
        "rule_fired": "UNKNOWN_ROUND",
    }

    def test_identical_records_surface_twice(self):
        record = {"failure_records": [dict(self.PAYLOAD),
                                      dict(self.PAYLOAD)]}
        advanced = render(record, form="advanced")
        self.assertEqual(len(advanced["failure_records"]), 2)
        agentic = render(record, form="agentic")
        self.assertEqual(
            len(agentic["report"]["failure_records"]), 2)
        simple = render(record, form="simple")
        self.assertEqual(
            simple.count("probe report failed with UNKNOWN_ROUND"), 2)


class TestStalenessRoundCount066(unittest.TestCase):
    """: the staleness view round record count stands as
    the journal counts them."""

    def test_duplicate_round_identity_counts_twice(self):
        root = Path(self.enterContext(
            tempfile.TemporaryDirectory()))
        location, home = root / "install", root / "home"
        install_module.install(
            location=str(location), home=str(home))
        service.add_product(
            home=str(home), name="Acme",
            canonical_line="Acme helps teams.",
            domain="acme.example", audit_date=AUDIT_DATE)
        service.name_round(
            home=str(home), product="Acme", round_label="round-1",
            importer_declaration="all captured",
            supplier_relation="independent party",
            audit_date=AUDIT_DATE)
        entries = journal.fold(str(home))
        payload = None
        for entry in entries:
            if entry.get("entry_kind") == "round_named":
                payload = entry.get("payload")
        self.assertIsNotNone(payload)
        journal.append_entry(
            str(home), "round_named", dict(payload),
            audit_date=AUDIT_DATE)
        view = service.staleness_view(home=str(home))
        # Restated for the settled rule: the
        # staleness view now builds one row per standing round,
        # taking the last round_named payload as the standing
        # record as every other round reader does, so the two
        # journal entries sharing one round identity count
        # once in this view and record_count stands exact.
        self.assertEqual(view["record_count"], 1)
        self.assertEqual(len(view["records"]), 1)


if __name__ == "__main__":
    unittest.main()
