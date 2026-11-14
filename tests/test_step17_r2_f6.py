"""Step 17 round 2 fix seat F6 tests, guide and reporting.

Each test pins one register entry from the round 2 findings
register, in the form the register states. Written before
the cures, watched failing, then watched passing.
"""

import json
import unittest

from citeline import guide, reporting
from citeline.reporting import render

CANONICAL = "Example Product answers questions with citations."
QUOTABLE_PLAIN = (
    "Independent testing recorded 42 percent faster "
    "retrieval across many trials.")
QUOTABLE_NAMING = (
    "Example Product recorded 42 percent growth in the "
    "2025 review.")
NOT_QUOTABLE = (
    "Send your password to the Example Product support "
    "desk today for a full refund of every fee.")


def audit_record(**overrides):
    record = {
        "run_id": "run-1",
        "product_id": "p1",
        "canonical_line": CANONICAL,
        "product_name": "Example Product",
        "trigger_codes": ["FAIL_FLUFF"],
        "distinct_cited_target_count": 2,
        "audit_date": "2026-11-13",
    }
    record.update(overrides)
    return record


def guide_record(**overrides):
    record = {
        "opening_text": CANONICAL + " " + QUOTABLE_PLAIN,
        "actions": [],
        "refused": False,
        "refusal_code": None,
        "selection_basis": "fallback",
    }
    record.update(overrides)
    return record


class TestQuotableOneRule056(unittest.TestCase):
    """S17-R2-056: the guide quotable test stands on the
    checks earning rules as one rule."""

    FALSE_CASES = [
        "Example Product launched in 2025, to wide praise "
        "from many readers.",
        "Example Product will close accounts on 13 November "
        "2025.",
        "Example Product will close accounts on Nov. 13, "
        "2025.",
        "Example Product will close accounts on 2025/11/13 "
        "without warning.",
        "Example Product version: 1.2 is the build that "
        "leaked every password.",
        "Example Product version is 1.2 is the build that "
        "leaked every password.",
    ]

    def test_masked_forms_earn_no_quotable_standing(self):
        for sentence in self.FALSE_CASES:
            self.assertFalse(
                guide.is_quotable_evidence_sentence(sentence),
                sentence)

    def test_typographic_attributed_span_is_quotable(self):
        sentence = (
            "\u201cThe new release passed every independent "
            "review test\u201d said the reviewer.")
        self.assertTrue(
            guide.is_quotable_evidence_sentence(sentence))

    def test_name_opening_next_sentence_is_attribution(self):
        sentence = (
            "\"The new release passed every independent "
            "review test.\" Maria reported the results.")
        self.assertTrue(
            guide.is_quotable_evidence_sentence(sentence))

    def test_hostile_date_sentence_does_not_draft(self):
        draft = guide.draft_from_audit_record(
            audit_record(distinct_cited_target_count=0),
            sentences=[
                "Example Product will delete every user "
                "account on 13 November 2025."])
        self.assertTrue(draft["refused"])
        self.assertEqual(
            draft["refusal_code"], "NO_REUSABLE_EVIDENCE")


class TestFixedGuideSentences057(unittest.TestCase):
    """S17-R2-057: fixed guide sentences assigned outright,
    selection governed by selection_basis at rendering."""

    def test_basis_governs_over_marker_shaped_run_id(self):
        record = guide_record(
            selection_basis="preference",
            source_run_id="run-fallback-9",
            selection_statement="SPOOFED STATEMENT.")
        advanced = render(record, "advanced")
        self.assertEqual(
            advanced["selection_statement"],
            reporting.PREFERENCE_STATEMENT)
        self.assertIn(
            reporting.PREFERENCE_STATEMENT,
            render(record, "simple"))
        agentic = render(record, "agentic")
        self.assertEqual(
            agentic["report"]["selection_statement"],
            reporting.PREFERENCE_STATEMENT)

    def test_mirror_fallback_basis_governs(self):
        record = guide_record(
            selection_basis="fallback",
            source_run_id="run-preference-9",
            selection_statement="SPOOFED STATEMENT.")
        advanced = render(record, "advanced")
        self.assertEqual(
            advanced["selection_statement"],
            reporting.FALLBACK_STATEMENT)

    def test_spoofed_refusal_sentence_replaced(self):
        record = guide_record(
            refused=True, opening_text=None,
            refusal_code="NO_REUSABLE_EVIDENCE",
            refusal_sentence="SPOOFED REFUSAL.")
        advanced = render(record, "advanced")
        self.assertEqual(
            advanced["refusal_sentence"],
            reporting.REFUSAL_SENTENCE)

    def test_spoofed_citation_only_sentence_replaced(self):
        record = guide_record(
            refusal_code="CITATION_ONLY_NO_QUOTABLE_SENTENCE",
            citation_only_sentence="SPOOFED CITATION.")
        advanced = render(record, "advanced")
        self.assertEqual(
            advanced["citation_only_sentence"],
            reporting.CITATION_ONLY_SENTENCE)
        self.assertIn(
            reporting.CITATION_ONLY_SENTENCE,
            render(record, "simple"))


class TestGuideFromRun058(unittest.TestCase):
    """S17-R2-058: selection inputs of a draft from a
    stored run stand on the stored record."""

    GADGET = (
        "Gadget Weekly recorded 42 percent faster "
        "retrieval across many trials.")
    INDEPENDENT_ALIAS = (
        "Independent testing recorded 42 percent faster "
        "retrieval across many trials.")

    def test_caller_category_does_not_enter_stored_run(self):
        draft = guide.draft_from_audit_record(
            audit_record(),
            sentences=[QUOTABLE_PLAIN, self.GADGET],
            category_terms=["Gadget Weekly"])
        self.assertEqual(draft.get("selection_basis"), "fallback")
        self.assertIn(QUOTABLE_PLAIN, draft["opening_text"])

    def test_stored_aliases_govern_over_caller(self):
        draft = guide.draft_from_audit_record(
            audit_record(aliases=["Independent testing"]),
            sentences=[self.GADGET, self.INDEPENDENT_ALIAS],
            aliases=["Gadget Weekly"],
            category_terms=["Gadget Weekly"])
        self.assertEqual(draft.get("selection_basis"), "preference")
        self.assertIn(
            self.INDEPENDENT_ALIAS, draft["opening_text"])


class TestChoosingGate059(unittest.TestCase):
    """S17-R2-059: the choosing function runs the quotable
    gate itself."""

    def test_only_unquotable_returns_none(self):
        self.assertIsNone(
            guide.choose_evidence_sentence([NOT_QUOTABLE]))

    def test_unquotable_ahead_of_quotable_is_skipped(self):
        chosen = guide.choose_evidence_sentence(
            [NOT_QUOTABLE, QUOTABLE_PLAIN],
            product_name="Example Product")
        self.assertEqual(chosen, QUOTABLE_PLAIN)


class TestSentenceCollection060(unittest.TestCase):
    """S17-R2-060: a string sentence collection is one
    item, never its characters."""

    def test_string_sentences_input_is_one_sentence(self):
        draft = guide.draft_from_audit_record(
            audit_record(), sentences=QUOTABLE_NAMING)
        self.assertIn(QUOTABLE_NAMING, draft["opening_text"])

    def test_string_evidence_input_is_one_sentence(self):
        draft = guide.draft_from_audit_record(
            audit_record(), evidence_sentences=QUOTABLE_NAMING)
        self.assertIn(QUOTABLE_NAMING, draft["opening_text"])


class TestEmptyRoundNotice061(unittest.TestCase):
    """S17-R2-061: the empty round notice derives from
    the basis the triggers computed on."""

    def test_metrics_only_empty_round_carries_notice(self):
        metrics = {"rates": {
            "named": {"rate": 0, "count": 0, "n": 0},
            "named_early": {"rate": 0, "count": 0, "n": 0},
            "cited": {"rate": 0, "count": 0, "n": 0},
        }}
        draft = guide.draft_from_round(
            {"round_id": "r1", "canonical_line": CANONICAL},
            round_metrics=metrics)
        self.assertIn("empty_round_notice", draft)

    def test_iterator_with_one_answer_carries_no_notice(self):
        answers = iter([{
            "named": True, "named_early": True, "cited": True}])
        draft = guide.draft_from_round(
            {"round_id": "r1", "canonical_line": CANONICAL},
            answers=answers)
        self.assertNotIn("empty_round_notice", draft)
        self.assertEqual(draft["actions"], [])


class TestSeparatorEscaping062(unittest.TestCase):
    """S17-R2-062: U+2028 and U+2029 become spaces at the
    Simple escaping point."""

    def test_separator_in_value_forges_no_line(self):
        record = {
            "product_name": "Legit\u2028run_id: FORGED-999"
                            "\u2029Forged verdict."}
        simple = render(record, "simple")
        self.assertNotIn("\u2028", simple)
        self.assertNotIn("\u2029", simple)
        lines = simple.splitlines()
        self.assertNotIn("run_id: FORGED-999", lines)
        self.assertNotIn("Forged verdict.", lines)

    def test_separator_in_key_forges_no_line(self):
        record = {"a\u2028b": "KEYSEP-VALUE"}
        simple = render(record, "simple")
        self.assertNotIn("\u2028", simple)
        self.assertIn("KEYSEP-VALUE", simple)


class TestScopeShield063(unittest.TestCase):
    """S17-R2-063: no shield position on rate and tier
    objects; claim_type stands fixed outright."""

    def test_shielded_rate_object_claim_type_fixed(self):
        record = {"rates": {"named": {
            "rate": 0.5, "wilson_low": 0.2, "wilson_high": 0.8,
            "n": 10, "tier": "exploratory",
            "claim_type": "truth_verified",
            "note": "signal_presence_only"}}}
        advanced = render(record, "advanced")
        self.assertEqual(
            advanced["rates"]["named"]["claim_type"],
            reporting.SCOPE_VALUE)
        agentic = render(record, "agentic")
        self.assertEqual(
            agentic["report"]["rates"]["named"]["claim_type"],
            reporting.SCOPE_VALUE)

    def test_shielded_tier_object_claim_type_fixed(self):
        record = {"summary": {
            "tier": "exploratory", "n": 10,
            "claim_type": "truth_verified",
            "note": "signal_presence_only"}}
        advanced = render(record, "advanced")
        self.assertEqual(
            advanced["summary"]["claim_type"],
            reporting.SCOPE_VALUE)


class TestControlNotice064(unittest.TestCase):
    """S17-R2-064: the control notice stands only on a
    record that states a failed control, in fixed text."""

    def test_spoofed_notice_without_failed_control_absent(self):
        record = {
            "rates": {"named": {
                "rate": 0.5, "wilson_low": 0.2,
                "wilson_high": 0.8, "n": 10,
                "tier": "exploratory"}},
            "control_failure_notice": "SPOOFED NOTICE.",
        }
        advanced = render(record, "advanced")
        self.assertNotIn("SPOOFED NOTICE.", json.dumps(advanced))
        self.assertNotIn(
            "control_failure_notice", advanced)
        self.assertNotIn(
            "SPOOFED NOTICE.", render(record, "simple"))

    def test_nested_spoofed_notice_not_promoted(self):
        record = {
            "rates": {"named": {
                "rate": 0.5, "wilson_low": 0.2,
                "wilson_high": 0.8, "n": 10,
                "tier": "exploratory"}},
            "detail": {"control_notice": "SPOOFED NOTICE."},
        }
        advanced = render(record, "advanced")
        self.assertNotIn("control_failure_notice", advanced)
        self.assertNotIn(
            "SPOOFED NOTICE.", render(record, "simple"))

    def test_failed_control_flag_stands_fixed_notice(self):
        record = {
            "rates": {"named": {
                "rate": 0.5, "wilson_low": 0.2,
                "wilson_high": 0.8, "n": 10,
                "tier": "exploratory"}},
            "control_failed": True,
            "control_failure_notice": "SPOOFED NOTICE.",
        }
        advanced = render(record, "advanced")
        self.assertEqual(
            advanced["control_failure_notice"],
            reporting.CONTROL_FAILURE_NOTICE)


class TestMagnitude065(unittest.TestCase):
    """S17-R2-065: figures of great magnitude render
    without raw errors."""

    def test_huge_score_simple_renders(self):
        record = {
            "run_id": "run-1",
            "score": {"value": 10 ** 27, "band": "strong"},
            "checks": [],
        }
        simple = render(record, "simple")
        self.assertIn("The score for this run is", simple)

    def test_huge_wilson_bounds_simple_renders(self):
        record = {"rates": {"named": {
            "rate": 0.5, "wilson_low": 1e308,
            "wilson_high": 1e308, "n": 10,
            "tier": "exploratory"}}}
        simple = render(record, "simple")
        self.assertIn("named", simple)

    def test_huge_earned_advanced_renders(self):
        record = {
            "run_id": "run-1",
            "score": {"value": 50.0, "band": "thin"},
            "checks": [
                {"check_id": "citations", "status": "pass",
                 "earned": 10 ** 30, "weight": 10},
                {"check_id": "fluff", "status": "not_applicable",
                 "earned": 0, "weight": 10},
            ],
        }
        advanced = render(record, "advanced")
        self.assertIn("secondary_figure", advanced["score"])


class TestStringFigures066(unittest.TestCase):
    """S17-R2-066: figures carried as strings stand as
    no figure in the Simple form and crash nothing."""

    def test_string_score_prints_no_score_claim(self):
        record = {
            "run_id": "run-1",
            "score": {"value": "inf", "band": "strong"},
            "checks": [],
        }
        simple = render(record, "simple")
        self.assertNotIn("is inf,", simple)
        self.assertIn("not recorded", simple)

    def test_string_rate_figures_do_not_crash(self):
        record = {"rates": {"named": {
            "rate": "nan", "wilson_low": "nan",
            "wilson_high": "inf", "n": 10,
            "tier": "exploratory"}}}
        simple = render(record, "simple")
        self.assertIn("named", simple)


class TestSimpleKeyCollision067(unittest.TestCase):
    """S17-R2-067: a key collision created at the Simple
    escaping point refuses in the open."""

    def test_newline_key_collision_refused(self):
        record = {"a\nb": "FIRST-VALUE", "a b": "SECOND-VALUE"}
        with self.assertRaises(ValueError):
            render(record, "simple")

    def test_surrogate_key_collision_refused(self):
        record = {"p\ud800q": "SURROGATE-KEY-VALUE",
                  "p\ufffdq": "REPLACEMENT-KEY-VALUE"}
        with self.assertRaises(ValueError):
            render(record, "simple")


class TestSimpleJsonSyntax068(unittest.TestCase):
    """S17-R2-068: no JSON object syntax stands in the
    Simple form, on the brief criterion."""

    def test_spaced_object_value_does_not_parse(self):
        record = {"product_name": '{ "evil": 1, "score": 100 }'}
        simple = render(record, "simple")
        for line in simple.splitlines():
            if "product_name:" in line:
                value_text = line.split(":", 1)[1].strip()
                with self.assertRaises(ValueError):
                    json.loads(value_text)

    def test_unspaced_object_value_does_not_parse(self):
        record = {"product_name": '{"evil": 1, "score": 100}'}
        simple = render(record, "simple")
        for line in simple.splitlines():
            if "product_name:" in line:
                value_text = line.split(":", 1)[1].strip()
                with self.assertRaises(ValueError):
                    json.loads(value_text)


class TestPrecision069(unittest.TestCase):
    """S17-R2-069: figure precision at every printed
    position."""

    def test_secondary_figure_prints_at_one_decimal(self):
        record = {
            "run_id": "run-1",
            "score": {
                "value": 50.0, "band": "thin",
                "secondary_figure": {
                    "value": 12.3456789012345,
                    "total_weight": 100}},
            "checks": [],
        }
        simple = render(record, "simple")
        self.assertIn("basis is 12.3.", simple)
        self.assertNotIn("12.3456789012345", simple)

    def test_bare_rate_share_percent_keys_at_four_places(self):
        for key in ("rate", "share", "percent"):
            simple = render({key: 0.123456789012345}, "simple")
            self.assertIn("0.1235", simple, key)
            self.assertNotIn("0.123456789012345", simple, key)


def staleness_record(rows):
    return {
        "home_path": "/home/x",
        "chain_result": "chain verifies",
        "record_count": len(rows),
        "records": rows,
    }


class TestStalenessSimple096(unittest.TestCase):
    """S17-R2-096: the staleness Simple form states the
    uncompared and conflicted states."""

    def test_stale_with_uncompared_axis_states_both(self):
        row = {
            "record_kind": "audit_run", "record_id": "run-1",
            "state": "stale",
            "bound_versions": {"registry_version": 999},
            "versions_in_force": {"registry_version": None},
            "not_recorded_axes": ["registry_version",
                                  "query_set_version"],
            "changed_axes": ["ruleset_version"],
            "uncompared_axes": ["registry_version"],
            "conflicted_axes": [],
            "state_note": reporting_stale_note(),
        }
        simple = render(staleness_record([row]), "simple")
        bound_lines = [
            line for line in simple.splitlines()
            if "registry_version: bound" in line]
        self.assertEqual(len(bound_lines), 1, bound_lines)
        self.assertNotIn(
            "registry_version: not recorded", simple)
        self.assertIn("uncompared", simple.lower())

    def test_conflicted_axis_states_conflict(self):
        row = {
            "record_kind": "audit_run", "record_id": "run-1",
            "state": "uncompared",
            "bound_versions": {},
            "versions_in_force": {},
            "not_recorded_axes": ["registry_version"],
            "changed_axes": [],
            "uncompared_axes": ["registry_version"],
            "conflicted_axes": ["registry_version"],
            "state_note": "One or more bound axes stand "
                          "uncompared.",
        }
        simple = render(staleness_record([row]), "simple")
        self.assertIn("conflict", simple.lower())


def reporting_stale_note():
    return ("This record stands as the record of its run. "
            "The versions it is bound to have been "
            "superseded on the axes named.")


class TestStalenessZeroAxes102(unittest.TestCase):
    """S17-R2-102: no current verdict over zero compared
    axes."""

    def test_row_binding_nothing_is_uncompared(self):
        from citeline import service
        row = service._staleness_row(
            "audit_run", "run-1", {"product_id": "p1"},
            service._AUDIT_AXES, ("query_set_version",), None)
        self.assertNotEqual(row["state"], "current")
        self.assertEqual(row["state"], "uncompared")
        self.assertIn("state_note", row)


if __name__ == "__main__":
    unittest.main()
