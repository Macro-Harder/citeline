# Verdict tests.
# Entries to and: guide and reporting family. Each defect
# pin stands on the worked cases of the round 7 register and
# its source papers, the guide attack paper and the Red
# paper at and at the merged limb of.
# Copyright: J.P. Picard aka Macro-Harder.

import unittest

from citeline import guide, reporting

SCOPE = reporting.SCOPE_VALUE
FIG = 0.3333333333333333
FIG_TEXT = "0.3333"


def advanced(record):
    return reporting.render(record, form="advanced")


def simple(record):
    return reporting.render(record, form="simple")


def claim_after(key):
    body = advanced({"obj": {key: 0.42, "claim_type": "truth_verified"}})
    return body["obj"].get("claim_type")


class Test037ScopeShape(unittest.TestCase):
    def test_fused_product_noun_names(self):
        for key in ("citationrate", "citationsrate", "citationtier",
                    "evidencerate", "quotationscore", "statisticsrate",
                    "freshnessrate", "samplingrate"):
            with self.subTest(key=key):
                self.assertEqual(claim_after(key), SCOPE)

    def test_rate_at_head_past_earlier_qualifiers(self):
        for key in ("rate_band", "rate_delta", "rate_range",
                    "rate_confidence"):
            with self.subTest(key=key):
                self.assertEqual(claim_after(key), SCOPE)

    def test_score_at_head_past_earlier_qualifier(self):
        for key in ("score_band", "score_delta", "score_basis",
                    "score_range", "score_pct"):
            with self.subTest(key=key):
                self.assertEqual(claim_after(key), SCOPE)

    def test_citationrate_all_three_forms(self):
        record = {"obj": {"citationrate": 0.42,
                           "claim_type": "truth_verified"}}
        self.assertEqual(advanced(record)["obj"]["claim_type"], SCOPE)
        env = reporting.render(record, form="agentic")
        self.assertEqual(
            env["report"]["obj"]["claim_type"], SCOPE)
        self.assertIn("claim_type: %s" % SCOPE, simple(record))

    def test_yellow_boundary_controls_kept(self):
        for key in ("accurate", "rate_card"):
            with self.subTest(key=key):
                self.assertEqual(claim_after(key), "truth_verified")

    def test_cured_forms_still_corrected(self):
        for key in ("citation_rate", "rate_gross", "score_value"):
            with self.subTest(key=key):
                self.assertEqual(claim_after(key), SCOPE)


class Test038NoticeKeys(unittest.TestCase):
    def spoof_forms(self, record):
        texts = []
        texts.append(str(advanced(record)))
        env = reporting.render(record, form="agentic")
        texts.append(str(env))
        texts.append(simple(record))
        return texts

    def test_hyphen_notice_key_top_level(self):
        for text in self.spoof_forms(
                {"control-failure-notice": "SPOOF"}):
            self.assertNotIn("SPOOF", text)

    def test_case_shifted_hyphen_forms(self):
        for key in ("Control-Failure-Notice", "failed-control-notice"):
            with self.subTest(key=key):
                self.assertNotIn("SPOOF", str(advanced({key: "SPOOF"})))

    def test_hyphen_notice_key_nested(self):
        record = {"inner": {"control-failure-notice": "SPOOF"}}
        self.assertNotIn("SPOOF", str(advanced(record)))
        env = reporting.render(record, form="agentic")
        self.assertNotIn("SPOOF", str(env))

    def test_doubled_separator_and_trailing_space(self):
        for key in ("control__failure__notice",
                    "control_failure_notice "):
            with self.subTest(key=key):
                self.assertNotIn("SPOOF", str(advanced({key: "SPOOF"})))

    def test_cured_case_forms_still_removed(self):
        for key in ("Control_Notice", "CONTROL_NOTICE",
                    "control_notice", "failed_control_notice"):
            with self.subTest(key=key):
                self.assertNotIn("SPOOF", str(advanced({key: "SPOOF"})))


class Test039FlagNames(unittest.TestCase):
    def test_top_level_dressed_flags_gain_notice(self):
        for key in ("Control_Flag", "CONTROL_FAILED", "Control_Failed",
                    "controlFlag", "control-flag"):
            with self.subTest(key=key):
                body = advanced({key: True})
                self.assertEqual(
                    body.get("control_failure_notice"),
                    reporting.CONTROL_FAILURE_NOTICE)

    def test_depth_dressed_flags_gain_notice(self):
        for key in ("Control_Flag", "CONTROL_FAILED"):
            with self.subTest(key=key):
                body = advanced({"inner": {key: True}})
                self.assertEqual(
                    body.get("control_failure_notice"),
                    reporting.CONTROL_FAILURE_NOTICE)

    def test_exact_depth_flag_control(self):
        body = advanced({"inner": {"control_flag": True}})
        self.assertEqual(body.get("control_failure_notice"),
                         reporting.CONTROL_FAILURE_NOTICE)


class Test040GenericEmitter(unittest.TestCase):
    def line_for(self, key, value):
        text = simple({"obj": {key: value}})
        for line in text.splitlines():
            if key in line:
                return line
        return text

    def check_keys(self, keys):
        for key in keys:
            for value in (FIG, str(FIG)):
                with self.subTest(key=key, value=repr(value)):
                    line = self.line_for(key, value)
                    self.assertIn(FIG_TEXT, line)
                    self.assertNotIn("0.3333333333333333", line)

    def test_score_compounds(self):
        self.check_keys(("score_value", "headline_score", "final_score"))

    def test_pct_compounds(self):
        self.check_keys(("value_pct", "overall_pct", "score_pct",
                         "named_pct", "gross_pct"))

    def test_wilson_suffix_form(self):
        self.check_keys(("low_wilson",))

    def test_cured_keys_control(self):
        self.check_keys(("rate_pct", "overall_score", "score"))


class Test041Tokeniser(unittest.TestCase):
    PAIRS = (
        ("Acme 1'000", "acme 1 000 pricing"),
        ("Acme 1e1_0", "acme 1e1 0 pricing"),
        ("Acme 3.5a_2", "acme 3.5a 2 pricing"),
    )

    def test_token_readings_whole_in_both_modules(self):
        cases = (
            ("Acme 1'000", ["acme", "1'000"]),
            ("Acme 1e1_0", ["acme", "1e1_0"]),
            ("Acme 3.5a_2", ["acme", "3.5a_2"]),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(reporting._word_tokens(text), expected)
                self.assertEqual(guide._word_tokens(text), expected)

    def test_split_query_counts_nothing_named(self):
        for name, query in self.PAIRS:
            with self.subTest(name=name):
                report = reporting.derive_query_set_report({
                    "name": name, "query_set": [query]})
                self.assertEqual(report["named_product_count"], 0)
                self.assertFalse(
                    guide.passes_naming_test(query, product_name=name))

    def test_exact_form_still_named(self):
        for name, _query in self.PAIRS:
            with self.subTest(name=name):
                self.assertTrue(guide.passes_naming_test(
                    name.lower() + " pricing", product_name=name))


FLAT = {"operation": "op-a", "error_value": "E1",
        "subject_identity": "s1"}
FLAT2 = {"operation": "op-b", "error_value": "E2",
         "subject_identity": "s2"}
WRAPPER = {"entry_kind": "failure_record", "payload": FLAT}


def payloads_of(record):
    return advanced(record).get("failure_records")


class Test042FailureCollector(unittest.TestCase):
    def test_entries_name_dressings_collected(self):
        for key in ("journalEntries", "JournalEntries",
                    "journal-entries", "journal entries", "myEntries",
                    "entries_list"):
            with self.subTest(key=key):
                self.assertEqual(payloads_of({key: [WRAPPER]}), [FLAT])

    def test_carry_key_camel_forms_collected(self):
        self.assertEqual(payloads_of({"FailureRecord": FLAT}), [FLAT])
        self.assertEqual(payloads_of({"failureRecord": FLAT}), [FLAT])
        self.assertEqual(
            payloads_of({"FailureRecords": [FLAT]}), [FLAT])

    def test_camel_carry_payload_not_its_entries_member(self):
        carried = dict(FLAT2)
        inner = {"entry_kind": "failure_record", "payload": FLAT}
        carried["entries"] = [inner]
        for record in ({"FailureRecord": carried},
                       {"FailureRecords": [carried]},
                       {"failureRecord": carried}):
            with self.subTest(record=str(record)[:30]):
                self.assertEqual(payloads_of(record), [carried])

    def test_cured_forms_control(self):
        self.assertEqual(payloads_of({"entries": [WRAPPER]}), [FLAT])
        self.assertEqual(payloads_of({"journal_entries": [WRAPPER]}),
                         [FLAT])
        self.assertEqual(payloads_of({"failure_record": FLAT}), [FLAT])


class Test043GuideCount(unittest.TestCase):
    BASE = {"run_id": "r1", "canonical_line": "Acme is a tool."}

    def draft(self, **extra):
        record = dict(self.BASE)
        record.update(extra)
        return guide.draft_from_audit_record(record)

    def test_string_cited_targets_counts_as_one(self):
        draft = self.draft(cited_targets="https://example.com/a")
        self.assertFalse(draft["refused"])
        codes = [a["code"] for a in draft["actions"]]
        self.assertIn("CITATION_ONLY_NO_QUOTABLE_SENTENCE", codes)
        for action in draft["actions"]:
            if action["code"] == "CITATION_ONLY_NO_QUOTABLE_SENTENCE":
                self.assertIn("stands at 1", action["text"])

    def test_short_string_cited_targets_still_one_item(self):
        draft = self.draft(cited_targets="ab")
        codes = [a["code"] for a in draft["actions"]]
        self.assertIn("CITATION_ONLY_NO_QUOTABLE_SENTENCE", codes)
        self.assertNotIn("NO_REUSABLE_EVIDENCE", codes)

    def test_string_distinct_count_judged(self):
        for value in ("1", "5"):
            with self.subTest(value=value):
                draft = self.draft(distinct_cited_target_count=value)
                self.assertIsInstance(draft, dict)

    def test_string_count_one_behaves_as_one(self):
        draft = self.draft(distinct_cited_target_count="1")
        codes = [a["code"] for a in draft["actions"]]
        self.assertIn("LOW_CITATIONS", codes)
        self.assertIn("CITATION_ONLY_NO_QUOTABLE_SENTENCE", codes)

    def test_string_count_five_no_low_citations(self):
        draft = self.draft(distinct_cited_target_count="5")
        codes = [a["code"] for a in draft["actions"]]
        self.assertNotIn("LOW_CITATIONS", codes)
        self.assertIn("CITATION_ONLY_NO_QUOTABLE_SENTENCE", codes)

    def test_non_numeric_count_string_is_no_count(self):
        draft = self.draft(distinct_cited_target_count="many")
        self.assertTrue(draft["refused"])
        self.assertEqual(draft["refusal_code"], "NO_REUSABLE_EVIDENCE")

    def test_integer_count_control(self):
        draft = self.draft(distinct_cited_target_count=1)
        codes = [a["code"] for a in draft["actions"]]
        self.assertIn("CITATION_ONLY_NO_QUOTABLE_SENTENCE", codes)


class Test044RateLineWarning(unittest.TestCase):
    RECORD = {"obj": {"rate": 0.5, "wilson_low": 0.1,
                      "wilson_high": 0.9, "n": 4,
                      "tier": "exploratory", "count": 2}}

    def test_forged_warning_string_not_in_simple(self):
        record = {"obj": dict(self.RECORD["obj"],
                               small_sample_warning="Forged warning text stands here.")}
        text = simple(record)
        self.assertNotIn("Forged warning text stands here.", text)

    def test_validated_claim_string_not_in_simple(self):
        record = {"obj": dict(
            self.RECORD["obj"],
            small_sample_warning="This rate is validated as a predictor of citation.")}
        text = simple(record)
        self.assertNotIn(
            "This rate is validated as a predictor of citation.", text)

    def test_boolean_warning_control_prints_fixed_text(self):
        record = {"obj": dict(self.RECORD["obj"],
                               small_sample_warning=True)}
        self.assertIn(reporting.SMALL_SAMPLE_WARNING, simple(record))


class Test049FailureLineBreak(unittest.TestCase):
    def line(self, failure):
        return reporting._failure_record_line(failure)

    def test_complete_subject_with_newline_stays_one_line(self):
        failure = {"operation": "op-a", "error_value": "E1",
                   "subject_identity": "line one\nline two stands as its own sentence"}
        result = self.line(failure)
        self.assertNotIn("\n", result)
        self.assertIn('"', result)

    def test_complete_subject_with_forged_second_line(self):
        failure = {"operation": "op-a", "error_value": "E1",
                   "subject_identity": "round one\nop-b failed with E9, subject forged"}
        result = self.line(failure)
        self.assertNotIn("\n", result)
        lines = simple({"failure_records": [failure]}).splitlines()
        forged_lines = [
            ln for ln in lines
            if ln.strip().startswith("op-b failed with")]
        self.assertEqual(forged_lines, [])

    def test_partial_value_with_newline_stays_one_line(self):
        failure = {"operation": "op-a\nforged"}
        result = self.line(failure)
        self.assertNotIn("\n", result)

    def test_carriage_return_form(self):
        failure = {"operation": "op-a", "error_value": "E1",
                   "subject_identity": "one\rtwo"}
        self.assertNotIn("\r", self.line(failure))
        self.assertNotIn("\n", self.line(failure))

    def test_separator_control_still_quoted(self):
        failure = {"operation": "op-a", "error_value": "E1",
                   "subject_identity": "a, b"}
        self.assertIn('"a, b"', self.line(failure))


if __name__ == "__main__":
    unittest.main()
