"""Step 17 round 14 fix seat F6 tests: guide and reporting.

Verdict pins only: this seat charges no cure of its own
and edits no product module. The pins stand on the
guide and reporting seams in the standing verdict form
(the failure line seam at entry S17-R9-015, the longer
compound seam at entry S17-R9-016 in its stated bound,
and the list branch seam at entry S17-R9-018, as the
fix round 13 F6 paper states them and the round 14
guide paper rejudged them on new forms), on the guide
selection readings in their standing forms as the
round 14 guide paper judges them as their own scope,
on the collector kind discrepancy in its sustained
recorded form, extended on the new forms the round 14
guide paper runs, and on the standing watch figures
and the methods note version stamp in their exact
forms. Each pin was written before the verdict it
records and stands passing on the tree the verdicts
judge.
Oracle: the round 14 findings register and
disposition, ruling (j) and Section 3 seat F6, and
the round 14 guide attack paper.

Copyright: J.P. Picard aka Macro-Harder.
"""

import inspect
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from citeline import errors, guide, install as install_module
from citeline import reporting, service, watch

AUDIT_DATE = "2026-11-14"
PRODUCT = "Acme Ledger"
Q1 = "What is Acme Ledger?"
Q2 = "Best ferry tracker?"
ROUND = "round-1"
ROUND0 = "round-0"
FIG = 0.123456789
FIG_TEXT = "0.1235"
ALL_BREAKS = ("\n", "\r", "\x0b", "\x0c", "\x1c", "\x1d",
              "\x1e", "\x85", "\u2028", "\u2029")
NEW_SCALAR_KEYS = (
    "pct_confidence_value", "score_basis_value",
    "pct_band_value", "score_delta_value",
    "pct_range_value", "share_confidence_value",
    "gross_basis_value", "net_band_value",
    "value_confidence_value", "value_basis_value",
    "value_band_value", "value_delta_value")
NEW_LIST_KEYS = (
    "pct_confidence_value", "score_basis_value",
    "Pct Confidence Value", "pctConfidenceValue",
    "value_band_value")
BOUND_KEYS = (
    "alpha_confidence_value", "omega_basis_value",
    "pct_confidence_net_value", "pct_omega_value",
    "pct_confidence_amount", "pct_confidence_total",
    "score_basis_total", "pct_confidence_value_extra",
    "pct_confidence_values")
PAYLOAD = {"operation": "op", "error_value": "E",
           "subject_identity": "S"}
CANON = "Example Product answers questions."
NAMING = ("Example Product recorded 42 percent faster "
          "retrieval in testing.")
PLAIN = ("Independent testing recorded 42 percent faster "
         "retrieval across trials.")
GUIDE_NOTICE = ("a control in this round failed, and no "
                "action stands produced from this round")


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def seed(case, home):
    service.add_product(
        home=str(home), name=PRODUCT,
        canonical_line="Acme Ledger helps teams track citations.",
        domain="acme.example", audit_date=AUDIT_DATE)
    service.set_query_set(
        home=str(home), product=PRODUCT, query_set=[Q1, Q2],
        audit_date=AUDIT_DATE)
    service.name_round(
        home=str(home), product=PRODUCT, round_label=ROUND,
        importer_declaration="all captured",
        supplier_relation="independent party", audit_date=AUDIT_DATE)
    return home


def temp_file(case, content, name="file.txt"):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    path = root / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def token_of(exc):
    return getattr(exc, "token", None) or getattr(
        exc, "error_value", None)


def simple(record):
    return reporting.render(record, form="simple")


def line_for(key, value):
    text = simple({"obj": {key: value}})
    for line in text.splitlines():
        if key in line:
            return line
    return text


def guide_record(**kw):
    record = {"opening_text": "Line. Sentence.",
              "actions": [], "refused": False}
    record.update(kw)
    return record


def statement_of(record, form="advanced"):
    out = reporting.render(record, form=form)
    if form == "advanced":
        return out.get("selection_statement")
    if form == "agentic":
        return out["report"].get("selection_statement")
    if reporting.PREFERENCE_STATEMENT in out:
        return reporting.PREFERENCE_STATEMENT
    if reporting.FALLBACK_STATEMENT in out:
        return reporting.FALLBACK_STATEMENT
    return None


class SeededBase(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)
        seed(self, self.home)


# ----------------------------------------------------------------
# Seam 1, entry S17-R9-015: the failure line seam. The
# judged set stands at ten characters, equal to the
# whole line boundary set under the standard reading,
# judged exhaustively, and the round 14 forms plant
# breaks in further partial fields, at a subject
# standing as a bare break, and at an operation
# standing as a doubled break.
# ----------------------------------------------------------------

class Test015FailureLineSeamVerdict(unittest.TestCase):

    def test_judged_set_stands_at_ten_characters(self):
        self.assertEqual(len(reporting._LINE_BREAK_CHARS), 10)

    def test_judged_set_equals_the_splitlines_boundary_set(self):
        boundary = set()
        for point in range(0x110000):
            char = chr(point)
            if len(("a" + char + "b").splitlines()) > 1:
                boundary.add(char)
        self.assertEqual(boundary, set(reporting._LINE_BREAK_CHARS))
        self.assertEqual(len(boundary), 10)

    def test_break_in_round14_further_partial_fields(self):
        for field in ("restored_by", "source_run_id",
                      "archive_ref", "note_text"):
            for br in ("\n", "\x1c", "\u2028"):
                with self.subTest(field=field, brk=repr(br)):
                    line = reporting._failure_record_line({
                        "operation": "op",
                        field: "x" + br + "forged failed with X"})
                    self.assertEqual(len(line.splitlines()), 1)
                    self.assertNotIn(br, line)

    def test_subject_standing_as_a_bare_break_all_ten(self):
        for br in ALL_BREAKS:
            with self.subTest(brk=repr(br)):
                line = reporting._failure_record_line({
                    "operation": "op", "error_value": "E1",
                    "subject_identity": br})
                self.assertEqual(len(line.splitlines()), 1)
                self.assertNotIn(br, line)

    def test_operation_standing_as_a_doubled_break_all_ten(self):
        for br in ALL_BREAKS:
            with self.subTest(brk=repr(br)):
                line = reporting._failure_record_line({
                    "operation": br + br, "error_value": "E1"})
                self.assertEqual(len(line.splitlines()), 1)
                self.assertNotIn(br, line)

    def test_round14_stress_combinations_stand_as_one_line(self):
        for value in ("\r\n", "\x85\x85", "a\u2029\r\nb",
                      "\x1c\x1d\x1e"):
            with self.subTest(value=repr(value)):
                line = reporting._failure_record_line({
                    "operation": "op-a", "error_value": value,
                    "subject_identity": "s"})
                self.assertEqual(len(line.splitlines()), 1)

    def test_round14_non_string_values_one_line(self):
        for value in (b"bytes", 3.25, True, ["x"], {"k": 1}):
            with self.subTest(value=repr(value)):
                line = reporting._failure_record_line({
                    "operation": "op-a", "extra_field": value})
                self.assertEqual(len(line.splitlines()), 1)

    def test_two_failure_records_in_round14_positions_two_lines(self):
        first = {"operation": "op-a",
                 "error_value": "E1\u2028tail",
                 "subject_identity": "s"}
        second = {"operation": "op-b", "error_value": "E2",
                  "subject_identity": "t\x1e"}
        text = simple({"failure_records": [first, second]})
        section = text.split("Failure records", 1)[1]
        lines = [ln for ln in section.splitlines()
                 if "failed with" in ln]
        self.assertEqual(len(lines), 2)

    def test_unit_separator_and_companions_at_operation_raw_one_line(self):
        for value in ("a\x1fb", "a\u200bb", "a\ufeffb",
                      "a\xa0b", "a\u180eb", "a\x00\x07b"):
            with self.subTest(value=repr(value)):
                line = reporting._failure_record_line({
                    "operation": value, "error_value": "E1",
                    "subject_identity": "s"})
                self.assertEqual(len(line.splitlines()), 1)
        line = reporting._failure_record_line({
            "operation": "a\x1fb", "error_value": "E1",
            "subject_identity": "s"})
        self.assertIn("\x1f", line)

    def test_no_failure_line_builder_of_its_own_in_family(self):
        for module in (service, watch):
            source = inspect.getsource(module)
            self.assertNotIn("_failure_record_line", source)
            self.assertNotIn("_failure_value_text", source)
            self.assertNotIn("_LINE_BREAK_CHARS", source)
        self.assertIn(
            "reporting.render", inspect.getsource(service))


# ----------------------------------------------------------------
# Seam 2, entry S17-R9-016: the longer compound seam,
# Simple form only, judged at the scalar branch on the
# head and middle pairings of round 14, in plain and
# dressed forms, on its pinned bounds, and on the rate
# digit forms standing on their own limb.
# ----------------------------------------------------------------

class Test016LongerCompoundSeamVerdict(unittest.TestCase):

    def check_keys(self, keys, fig, fig_text):
        for key in keys:
            for value in (fig, str(fig)):
                with self.subTest(key=key, value=repr(value)):
                    line = line_for(key, value)
                    self.assertIn(fig_text, line)
                    self.assertNotIn(str(fig), line)

    def test_round14_pairings_print_at_four_places(self):
        self.check_keys(NEW_SCALAR_KEYS, FIG, FIG_TEXT)

    def test_round14_dressings_print_at_four_places(self):
        self.check_keys(
            ("Pct Confidence Value", "pct/confidence/value",
             "pct+confidence+value", "PCT.BASIS.VALUE",
             "pctConfidenceValue", "score-basis-value",
             "Score_Delta_Value", "VALUE BAND VALUE",
             "valueBandValue", "pct__confidence__value",
             "pct--band--value"),
            FIG, FIG_TEXT)

    def test_round14_figure_value_forms_under_the_new_key(self):
        key = "pct_confidence_value"
        for value, shown in (
                ("-0.123456789", "-0.1235"),
                (1.23456789e-1, "0.1235"),
                (Decimal("0.123456789"), "0.1235"),
                ("987.654321", "987.6543")):
            with self.subTest(value=repr(value)):
                self.assertIn(shown, line_for(key, value))
        for value in (7, True, "1/3"):
            with self.subTest(value=repr(value)):
                self.assertNotIn(FIG_TEXT, line_for(key, value))

    def test_bounds_of_the_limb_stand_outside_it_scalar(self):
        for key in BOUND_KEYS:
            with self.subTest(key=key):
                line = line_for(key, FIG)
                self.assertIn(str(FIG), line)

    def test_rate_digit_forms_stand_on_their_own_limb(self):
        self.check_keys(
            ("pct_confidence_rate3", "score_basis_rate7"),
            FIG, FIG_TEXT)

    def test_round14_key_at_top_level_and_at_depth(self):
        text = simple({"pct_confidence_value": FIG})
        self.assertIn(FIG_TEXT, text)
        self.assertNotIn(str(FIG), text)
        text = simple({"outer": {"inner": {
            "pct_confidence_value": FIG}}})
        self.assertIn(FIG_TEXT, text)
        self.assertNotIn(str(FIG), text)

    def test_simple_form_only_advanced_carries_as_stored(self):
        body = reporting.render(
            {"obj": {"pct_confidence_value": FIG}},
            form="advanced")
        self.assertEqual(body["obj"]["pct_confidence_value"], FIG)

    def test_no_emitter_or_key_reading_of_its_own_in_family(self):
        for module in (service, watch):
            source = inspect.getsource(module)
            self.assertNotIn("def _emit", source)
            self.assertNotIn("_key_names_figure", source)
            self.assertNotIn("claim_type", source)


# ----------------------------------------------------------------
# Seam 3, entry S17-R9-018: the list branch seam. The
# four place set stands stated in one helper shared by
# the scalar and list branches, judged on the round 14
# pairing keys at the list branch, nested seven levels
# deep, and on the record stop one level deeper than
# the earlier rounds ran it.
# ----------------------------------------------------------------

class Test018ListBranchSeamVerdict(unittest.TestCase):

    def check_list(self, key, value):
        text = simple({"obj": {key: value}})
        self.assertIn(FIG_TEXT, text)
        self.assertNotIn(str(FIG), text)

    def test_round14_pairing_keys_at_the_list_branch(self):
        for key in NEW_LIST_KEYS:
            with self.subTest(key=key):
                self.check_list(key, [FIG])
                self.check_list(key, [str(FIG)])

    def test_round14_pairing_keys_nested_seven_levels_deep(self):
        for key in NEW_LIST_KEYS:
            with self.subTest(key=key):
                self.check_list(key, [[[[[[[FIG]]]]]]])

    def test_tuple_and_mixed_items_at_the_list_branch(self):
        text = simple({"obj": {
            "pct_confidence_value": (FIG, str(FIG))}})
        self.assertEqual(text.count(FIG_TEXT), 2)
        text = simple({"obj": {"pct_confidence_value": [
            Decimal("0.123456789"), 7, True, FIG]}})
        self.assertIn(FIG_TEXT, text)
        self.assertIn("7", text)
        self.assertNotIn(str(FIG), text)

    def test_record_stop_judged_one_level_deeper(self):
        text = simple({"obj": {"plain_outer": [
            [[[{"pct_confidence_value": [FIG]}]]]]}})
        self.assertIn(FIG_TEXT, text)
        self.assertNotIn(str(FIG), text)
        text = simple({"obj": {"pct_confidence_value": [
            [[[{"plain_key": [FIG]}]]]]}})
        self.assertIn(str(FIG), text)

    def test_bounds_of_the_limb_stand_outside_it_in_lists(self):
        for key in BOUND_KEYS:
            with self.subTest(key=key):
                text = simple({"obj": {key: [FIG]}})
                self.assertIn(str(FIG), text)

    def test_rate_digit_forms_at_the_list_branch(self):
        self.check_list("pct_confidence_rate3", [FIG])
        self.check_list("score_basis_rate7", [FIG])

    def test_list_controls_print_verbatim(self):
        for key in ("plain_key", "percent_amount"):
            with self.subTest(key=key):
                text = simple({"obj": {key: [FIG]}})
                self.assertIn(str(FIG), text)


# ----------------------------------------------------------------
# The guide selection readings, in their standing
# forms: the selection statement governed by the
# selection_basis field alone, judged on the round 14
# constructions, stated forms in new dressings, non
# stated forms, non string values, spoofed fields, and
# marker positions.
# ----------------------------------------------------------------

class TestSelectionStatementVerdict(unittest.TestCase):

    def test_stated_forms_in_round14_dressings(self):
        for value, shown in (
                (" fallback ", reporting.FALLBACK_STATEMENT),
                ("\tpreference\n", reporting.PREFERENCE_STATEMENT),
                ("PrEfErEnCe", reporting.PREFERENCE_STATEMENT),
                ("PREFERRED", reporting.PREFERENCE_STATEMENT),
                ("Preferred", reporting.PREFERENCE_STATEMENT),
                (" FallBack ", reporting.FALLBACK_STATEMENT),
                ("\u00a0fallback\u00a0",
                 reporting.FALLBACK_STATEMENT)):
            with self.subTest(value=repr(value)):
                self.assertEqual(
                    statement_of(guide_record(
                        selection_basis=value)), shown)

    def test_round14_non_stated_forms_render_no_statement(self):
        for value in (
                "fallback_preferred", "not preference",
                "preference.", "fallback!", "fall back",
                "prefer", "preferred fallback",
                "preference fallback", "", " ", "fallbacks",
                "preferences", "the preference",
                "fallback\nfallback", "pref\u00e9rence",
                "\uff46allback", "preference\u200b",
                "fall-back", "preference_basis"):
            with self.subTest(value=repr(value)):
                self.assertIsNone(statement_of(guide_record(
                    selection_basis=value)))

    def test_non_string_basis_values_render_no_statement(self):
        for value in (None, 1, 0, True, False, ["fallback"],
                      ("preference",), {"b": "fallback"},
                      b"fallback", 1.5):
            with self.subTest(value=repr(value)):
                self.assertIsNone(statement_of(guide_record(
                    selection_basis=value)))

    def test_spoofed_statement_fields_in_every_form(self):
        for form in ("advanced", "agentic", "simple"):
            with self.subTest(form=form):
                self.assertIsNone(statement_of(guide_record(
                    selection_statement="SPOOFED STATEMENT."),
                    form))
                self.assertEqual(
                    statement_of(guide_record(
                        selection_basis="fallback",
                        selection_statement=(
                            reporting.PREFERENCE_STATEMENT)),
                        form),
                    reporting.FALLBACK_STATEMENT)
                self.assertEqual(
                    statement_of(guide_record(
                        selection_basis="preference",
                        selection_statement="SPOOFED."), form),
                    reporting.PREFERENCE_STATEMENT)

    def test_marker_spoofs_render_none_and_never_override(self):
        spoofs = (
            {"nested": {"selection_basis": "fallback"}},
            {"nested": [{"selection_basis": "preference"}]},
            {"meta": {"basis": "fallback",
                      "source": "preference"}},
            {"basis": "fallback"},
            {"selection": "preference"},
            {"chosen_by": "fallback"},
            {"source": "preference"},
            {"opening_source": "fallback"},
            {"actions": [{"code": "fallback",
                          "check_or_outcome": "preference"}]},
            {"actions": [{"code": "X",
                          "selection": "fallback",
                          "basis": "preference"}]},
            {"stamps": {"selection_basis": "fallback"}},
            {"selection_basis_x": "fallback"})
        for extra in spoofs:
            with self.subTest(extra=repr(sorted(extra))):
                self.assertIsNone(statement_of(
                    guide_record(**extra)))
                self.assertEqual(
                    statement_of(guide_record(
                        selection_basis="preference", **extra)),
                    reporting.PREFERENCE_STATEMENT)

    def test_dressed_field_names_render_no_statement(self):
        for key in ("Selection_Basis", "selection-basis",
                    "selection basis", "SELECTION_BASIS"):
            with self.subTest(key=key):
                record = guide_record()
                record[key] = "fallback"
                self.assertIsNone(statement_of(record))

    def test_fixed_text_interactions_stand_beside_the_statement(self):
        out = reporting.render(guide_record(
            refused=True, refusal_code="NO_REUSABLE_EVIDENCE",
            selection_basis="fallback"), form="advanced")
        self.assertEqual(out.get("refusal_sentence"),
                         reporting.REFUSAL_SENTENCE)
        self.assertEqual(out.get("selection_statement"),
                         reporting.FALLBACK_STATEMENT)
        out = reporting.render(guide_record(
            actions=[{"code": "CITATION_ONLY_NO_QUOTABLE_SENTENCE"}],
            selection_basis="preference"), form="advanced")
        self.assertEqual(out.get("citation_only_sentence"),
                         reporting.CITATION_ONLY_SENTENCE)
        self.assertEqual(out.get("selection_statement"),
                         reporting.PREFERENCE_STATEMENT)
        out = reporting.render(guide_record(
            control_failure_notice=GUIDE_NOTICE,
            selection_basis="preference"), form="advanced")
        self.assertEqual(out.get("control_failure_notice"),
                         GUIDE_NOTICE)
        self.assertEqual(out.get("selection_statement"),
                         reporting.PREFERENCE_STATEMENT)

    def test_dressed_control_flags_and_false_flag_controls(self):
        for key in ("Control_Failed", "control-failed",
                    "CONTROL FAILED", "controlFailed",
                    "control__failed"):
            with self.subTest(key=key):
                record = guide_record(selection_basis="preference")
                record[key] = True
                out = reporting.render(record, form="advanced")
                self.assertEqual(
                    out.get("control_failure_notice"),
                    reporting.CONTROL_FAILURE_NOTICE)
                self.assertEqual(
                    out.get("selection_statement"),
                    reporting.PREFERENCE_STATEMENT)
        out = reporting.render(guide_record(
            control_failed=False, control_flag=0,
            selection_basis="fallback"), form="advanced")
        self.assertNotIn("control_failure_notice", out)
        self.assertEqual(out.get("selection_statement"),
                         reporting.FALLBACK_STATEMENT)

    def test_top_level_list_items_stand_under_the_same_passes(self):
        out = reporting.render([
            guide_record(selection_basis="fallback"),
            guide_record(selection_basis="preference",
                         control_failed=True)], form="advanced")
        self.assertIsInstance(out, list)
        self.assertEqual(out[0].get("selection_basis"),
                         "fallback")
        self.assertEqual(out[1].get("selection_basis"),
                         "preference")
        self.assertEqual(out[1].get("control_failure_notice"),
                         reporting.CONTROL_FAILURE_NOTICE)
        self.assertNotIn("control_failure_notice", out[0])


# ----------------------------------------------------------------
# The draft selection readings at the guide module, in
# their standing forms: preference and fallback drafts
# with a firing trigger, the stored run discipline,
# the naming test and the quotable gate on the round
# 14 forms, collection forms, and the control
# interaction standings at the round draft.
# ----------------------------------------------------------------

class TestDraftSelectionVerdict(unittest.TestCase):

    def draft(self, sentences, **kw):
        record = {"run_id": "r14-1",
                  "product_name": "Example Product",
                  "canonical_line": CANON,
                  "trigger_codes": ["FAIL_CITATIONS"]}
        return guide.draft_from_audit_record(
            record, sentences=sentences, **kw)

    def test_preference_and_fallback_drafts(self):
        draft = self.draft([PLAIN, NAMING])
        self.assertEqual(draft.get("selection_basis"),
                         "preference")
        self.assertIn(NAMING, draft["opening_text"])
        draft = self.draft([NAMING, PLAIN])
        self.assertEqual(draft.get("selection_basis"),
                         "preference")
        self.assertIn(NAMING, draft["opening_text"])
        draft = self.draft([PLAIN])
        self.assertEqual(draft.get("selection_basis"),
                         "fallback")
        self.assertIn(PLAIN, draft["opening_text"])

    def test_stored_run_discipline_against_caller_terms(self):
        alias_sentence = ("The Gadget recorded 42 percent "
                          "faster retrieval across trials.")
        draft = self.draft([PLAIN, alias_sentence],
                           aliases=["Gadget"])
        self.assertEqual(draft.get("selection_basis"),
                         "fallback")
        self.assertIn(PLAIN, draft["opening_text"])
        category_sentence = ("Citation software recorded 42 "
                             "percent faster retrieval "
                             "across trials.")
        draft = self.draft([category_sentence, PLAIN],
                           category_terms=["Citation software"])
        self.assertEqual(draft.get("selection_basis"),
                         "fallback")

    def test_naming_forms_at_the_choosing_function(self):
        for sentence, kw in (
                ("The Gadget-Pro recorded 42 percent faster "
                 "retrieval.", {"aliases": ["Gadget-Pro"]}),
                ("Gadget Weekly recorded 42 percent faster "
                 "retrieval.", {"aliases": ["Gadget Weekly"]}),
                ("EXAMPLE PRODUCT recorded 42 percent faster "
                 "retrieval.", {}),
                ("Example Product, recorded 42 percent faster "
                 "retrieval.", {})):
            with self.subTest(sentence=sentence):
                self.assertEqual(
                    guide.choose_evidence_sentence(
                        [PLAIN, sentence],
                        product_name="Example Product", **kw),
                    sentence)
        for sentence in (
                "Example Products recorded 42 percent faster "
                "retrieval.",
                "Example Productivity recorded 42 percent "
                "gains in trials."):
            with self.subTest(sentence=sentence):
                self.assertEqual(
                    guide.choose_evidence_sentence(
                        [PLAIN, sentence],
                        product_name="Example Product"),
                    PLAIN)

    def test_quotable_gate_on_round14_sentence_forms(self):
        for sentence, shown in (
                ("See [Example Product](https://example.com/x) "
                 "for the 42 percent figure.", True),
                ("https://example.com/only", False),
                ("Example Product is 42% faster in retrieval "
                 "trials.", True),
                ("Example Product scored 3:2 in retrieval "
                 "trials.", True),
                ("Example Product costs $5 in the trial tier.",
                 True),
                ("Example Product is simply wonderful and "
                 "fast.", False),
                ('The reviewer said "Example Product is fast" '
                 'in the study.', False)):
            with self.subTest(sentence=sentence):
                self.assertEqual(
                    guide.is_quotable_evidence_sentence(sentence),
                    shown)

    def test_collection_forms_at_the_choosing_function(self):
        self.assertEqual(
            guide.choose_evidence_sentence(
                (PLAIN, NAMING), product_name="Example Product"),
            NAMING)
        self.assertEqual(
            guide.choose_evidence_sentence(
                PLAIN, product_name="Example Product"), PLAIN)
        self.assertEqual(
            guide.choose_evidence_sentence(
                [None, 42, PLAIN],
                product_name="Example Product"), PLAIN)
        self.assertIsNone(guide.choose_evidence_sentence(
            [], product_name="Example Product"))
        self.assertIsNone(guide.choose_evidence_sentence(
            None, product_name="Example Product"))

    def test_round_draft_control_interactions(self):
        named = [{"named": True, "named_early": True,
                  "cited": True}]
        control_named = [dict(named[0], control=True)]
        draft = guide.draft_from_round(
            {}, canonical_line=CANON, answers=control_named)
        self.assertEqual(len(draft["actions"]), 3)
        self.assertIn("empty_round_notice", draft)
        draft = guide.draft_from_round(
            {}, canonical_line=CANON,
            answers=named + control_named, control_failed=True)
        self.assertEqual(draft["actions"], [])
        self.assertIn("control_failure_notice", draft)
        draft = guide.draft_from_round(
            {"control_failed": True}, canonical_line=CANON,
            answers=named)
        self.assertEqual(draft["actions"], [])
        self.assertIn("control_failure_notice", draft)
        draft = guide.draft_from_round(
            {}, canonical_line=CANON, answers=[])
        self.assertEqual(len(draft["actions"]), 3)
        self.assertIn("empty_round_notice", draft)

    def test_round_draft_object_and_generator_answers(self):
        class Answer:
            pass
        answer = Answer()
        answer.named = True
        answer.named_early = True
        answer.cited = True
        answer.control_flag = True
        draft = guide.draft_from_round(
            {}, canonical_line=CANON, answers=[answer])
        self.assertEqual(len(draft["actions"]), 3)
        self.assertIn("empty_round_notice", draft)
        named = [{"named": True, "named_early": True,
                  "cited": True}]
        draft = guide.draft_from_round(
            {}, canonical_line=CANON,
            answers=(item for item in named))
        self.assertEqual(draft["actions"], [])

    def test_round_draft_metrics_forms(self):
        zero = {"rates": {
            name: {"rate": 0, "count": 0, "n": 0}
            for name in ("named", "named_early", "cited")}}
        draft = guide.draft_from_round(
            {}, canonical_line=CANON, round_metrics=zero)
        self.assertEqual(len(draft["actions"]), 3)
        self.assertIn("empty_round_notice", draft)
        draft = guide.draft_from_round(
            {}, canonical_line=CANON, round_metrics={})
        self.assertEqual(len(draft["actions"]), 3)
        self.assertNotIn("empty_round_notice", draft)
        partial = {"rates": {"named": {
            "rate": 1.0, "count": 3, "n": 3}}}
        draft = guide.draft_from_round(
            {}, canonical_line=CANON, round_metrics=partial)
        self.assertEqual(
            [action["code"] for action in draft["actions"]],
            ["NOT_NAMED_EARLY", "NOT_CITED"])
        self.assertNotIn("empty_round_notice", draft)

    def test_rendered_control_round_carries_the_notice(self):
        named = [{"named": True, "named_early": True,
                  "cited": True}]
        draft = guide.draft_from_round(
            {}, canonical_line=CANON, answers=named,
            control_failed=True)
        out = reporting.render(draft, form="advanced")
        self.assertEqual(out.get("control_failure_notice"),
                         GUIDE_NOTICE)
        text = reporting.render(draft, form="simple")
        self.assertIn(GUIDE_NOTICE, text)


# ----------------------------------------------------------------
# The collector kind discrepancy, in its sustained
# recorded form: the round 8 guide paper NO FINDING 7
# wording stands corrected in effect by the round 9
# register record, and the dressed kind and payload
# forms stand as a bounded observation, extended on
# the new forms the round 14 guide paper runs. These
# pins record that standing exactly: the exact forms
# surface their payload in the entries form, and the
# dressed forms do not. Nothing in this class files
# or cures the discrepancy.
# ----------------------------------------------------------------

class TestCollectorKindDiscrepancyStanding(unittest.TestCase):

    def surfaces(self, wrapper):
        got = reporting._failure_record_payloads(
            {"entries": [wrapper]})
        return got == [PAYLOAD]

    def test_exact_wrapper_surfaces_its_payload(self):
        wrapper = {"entry_kind": "failure_record",
                   "payload": PAYLOAD}
        self.assertEqual(
            reporting._failure_record_payloads(
                {"entries": [wrapper]}),
            [PAYLOAD])

    def test_round14_kind_key_forms_do_not_surface(self):
        for key in ("entry kind ", "ENTRY--KIND",
                    "entry.kind.", "Entry_Kind "):
            with self.subTest(key=key):
                wrapper = {key: "failure_record",
                           "payload": PAYLOAD}
                self.assertFalse(self.surfaces(wrapper))

    def test_round14_kind_value_forms_do_not_surface(self):
        for value in ("failure__record", "Failure Record",
                      "\tfailure_record", "failure-record."):
            with self.subTest(value=value):
                wrapper = {"entry_kind": value,
                           "payload": PAYLOAD}
                self.assertFalse(self.surfaces(wrapper))

    def test_round14_payload_member_forms_do_not_surface(self):
        for key in ("pay-loads", "Payloads.", "pay load",
                    "payloads "):
            with self.subTest(key=key):
                wrapper = {"entry_kind": "failure_record",
                           key: PAYLOAD}
                self.assertFalse(self.surfaces(wrapper))

    def test_round14_single_word_member_controls_surface(self):
        for key in ("payload\t", " payload ", "PAYLOAD "):
            with self.subTest(key=key):
                wrapper = {"entry_kind": "failure_record",
                           key: PAYLOAD}
                self.assertTrue(self.surfaces(wrapper))

    def test_round14_combined_dressing_does_not_surface(self):
        wrapper = {"entry kind ": "Failure Record",
                   "pay-loads": PAYLOAD}
        self.assertFalse(self.surfaces(wrapper))

    def test_round14_entries_key_forms_surface_the_payload(self):
        wrapper = {"entry_kind": "failure_record",
                   "payload": PAYLOAD}
        for key in ("ENTRIES ", "my-entries", "EntriesList"):
            with self.subTest(key=key):
                got = reporting._failure_record_payloads(
                    {key: [wrapper]})
                self.assertEqual(got, [PAYLOAD])

    def test_round14_list_and_single_form_reach(self):
        dressed = {"entry kind ": "failure_record",
                   "payload": PAYLOAD}
        got = reporting._failure_record_payloads(
            {"failure_records": [dressed]})
        self.assertEqual(got, [dressed])
        valued = {"entry_kind": "Failure Record",
                  "payload": PAYLOAD}
        got = reporting._failure_record_payloads(
            {"failure_record": valued})
        self.assertEqual(got, [valued])
        exact = {"entry_kind": "failure_record",
                 "payload": PAYLOAD}
        got = reporting._failure_record_payloads(
            {"failure_records": [exact]})
        self.assertEqual(got, [PAYLOAD])


# ----------------------------------------------------------------
# The standing watch verifications, in their exact
# forms: the WatchPlan size figure of 1 MiB and the
# picked scope bound of 100 targets, both watch modes
# standing as options chosen per round.
# ----------------------------------------------------------------

class TestWatchFiguresVerdict(SeededBase):

    def test_both_watch_modes_stand_as_options(self):
        estate = {"home": str(self.home), "scope": "estate",
                  "audit_date": AUDIT_DATE}
        self.assertEqual(watch._validate_plan(estate), [])
        picked = {"home": str(self.home), "scope": "picked",
                  "audit_date": AUDIT_DATE,
                  "targets": [{"product": PRODUCT,
                               "round": ROUND}]}
        self.assertEqual(len(watch._validate_plan(picked)), 1)

    def test_watchplan_size_figure_stands_at_one_mib(self):
        self.assertEqual(watch.PLAN_SIZE_BOUND, 1048576)
        self.assertEqual(watch.PLAN_SIZE_BOUND, 1024 * 1024)

    def test_watchplan_of_exactly_one_mib_runs(self):
        plan = {"home": str(self.home), "scope": "estate",
                "audit_date": AUDIT_DATE}
        raw = json.dumps(plan)
        raw = raw + " " * (1024 * 1024 - len(raw))
        self.assertEqual(len(raw.encode("utf-8")), 1024 * 1024)
        plan_file = temp_file(self, raw, "plan.json")
        result = watch.run_watch(plan_file=str(plan_file))
        self.assertIn("entries", result)

    def test_watchplan_one_byte_over_one_mib_refused(self):
        plan = {"home": str(self.home), "scope": "estate",
                "audit_date": AUDIT_DATE}
        raw = json.dumps(plan)
        raw = raw + " " * (1024 * 1024 + 1 - len(raw))
        plan_file = temp_file(self, raw, "plan.json")
        with self.assertRaises(errors.CitelineError) as caught:
            watch.run_watch(plan_file=str(plan_file))
        self.assertEqual(
            token_of(caught.exception), "WATCHPLAN_SIZE_EXCEEDED")

    def test_picked_scope_bound_at_100_targets(self):
        self.assertEqual(watch.TARGET_BOUND, 100)

        def plan_with(count):
            return {
                "home": str(self.home), "scope": "picked",
                "audit_date": AUDIT_DATE,
                "targets": [
                    {"product": "p-%03d" % index,
                     "round": ROUND}
                    for index in range(count)]}
        self.assertEqual(
            len(watch._validate_plan(plan_with(100))), 100)
        with self.assertRaises(errors.CitelineError) as caught:
            watch._validate_plan(plan_with(101))
        self.assertEqual(
            token_of(caught.exception),
            "WATCH_TARGET_COUNT_EXCEEDED")

    def test_singular_second_round_field_stands_warned_on_estate(self):
        plan = {"home": str(self.home), "scope": "estate",
                "second_round": ROUND0}
        warnings = watch._plan_warnings(plan, [])
        self.assertTrue(
            any("second_round" in warning and ROUND0 in warning
                for warning in warnings),
            "no warning names the singular field: %r" % (warnings,))

    def test_singular_second_round_field_controls_stand(self):
        picked = {"home": str(self.home), "scope": "picked",
                  "second_round": ROUND0}
        self.assertFalse(any(
            "second_round" in warning
            for warning in watch._plan_warnings(picked, [])))
        estate = {"home": str(self.home), "scope": "estate"}
        self.assertFalse(any(
            "second_round" in warning
            for warning in watch._plan_warnings(estate, [])))


# ----------------------------------------------------------------
# The methods note version stamp, in its exact form:
# the integer 1 standing in the methods_note_version
# stamp field under the Manager ruling.
# ----------------------------------------------------------------

class TestMethodsNoteVersionVerdict(unittest.TestCase):

    def test_stamp_constant_stands_as_the_integer_one(self):
        self.assertEqual(service.METHODS_NOTE_VERSION, 1)
        self.assertIs(type(service.METHODS_NOTE_VERSION), int)

    def test_nested_stamp_surfaces_at_the_top_level_as_one(self):
        body = reporting.render(
            {"obj": {"stamps": {"methods_note_version": 1}}},
            form="advanced")
        self.assertEqual(body["methods_note_version"], 1)
        self.assertIs(type(body["methods_note_version"]), int)

    def test_no_version_stands_invented_where_none_is_carried(self):
        body = reporting.render(
            {"obj": {"x": 1}}, form="advanced")
        self.assertNotIn("methods_note_version", body)


if __name__ == "__main__":
    unittest.main()
