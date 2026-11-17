"""Step 17 round 15 fix seat F6 tests: guide and reporting.

Defect pins for entries S17-R15-007 and S17-R15-008,
written before the cures they pin, beside verdict pins
for the standing seams of this family in their forms:
the failure line seam at entry S17-R9-015, the longer
compound seam at entry S17-R9-016 in its stated bound,
and the list branch seam at entry S17-R9-018, each
judged on the new forms the round 15 guide paper runs,
and the collector kind discrepancy in its sustained
form.
Oracle: the round 15 findings register and
disposition, ruling (f) and Section 3 seat F6, and
the round 15 guide attack paper.

Copyright: J.P. Picard aka Macro-Harder.
"""

import inspect
import unittest
from decimal import Decimal

from citeline import guide, reporting, service

CANON = "Example Product answers questions."
GUIDE_NOTICE = ("a control in this round failed, and no "
                "action stands produced from this round")
ANSWERS = [{"named": False, "named_early": False,
            "cited": False}]
FIG = 0.123456789
FIG_TEXT = "0.1235"
PAYLOAD = {"operation": "op", "error_value": "E",
           "subject_identity": "S"}
SENTENCE = "Other grew 20% in 2025."


def draft_of(record):
    return guide.draft_from_round(
        dict(record), canonical_line=CANON, answers=ANSWERS)


def assert_suppressed(case, draft):
    case.assertEqual(draft["actions"], [])
    case.assertEqual(
        draft.get("control_failure_notice"), GUIDE_NOTICE)


def assert_escaped(case, draft):
    case.assertEqual(
        [action["code"] for action in draft["actions"]],
        ["NOT_NAMED", "NOT_NAMED_EARLY", "NOT_CITED"])
    case.assertNotIn("control_failure_notice", draft)


def simple(record):
    return reporting.render(record, form="simple")


def line_for(key, value):
    text = simple({"obj": {key: value}})
    for line in text.splitlines():
        if key in line:
            return line
    return text


# ----------------------------------------------------------------
# Entry S17-R15-007: the failed control flag forms the
# rendering pass judges escape the guide draft
# suppression. The rendering pass judges three names,
# control_failed, control_failure, and control_flag,
# under the component reading, dressed forms included,
# at the top level and at any depth, by truthiness.
# The draft must stand on the same terms.
# ----------------------------------------------------------------

class Test007FailedControlDraftSuppression(unittest.TestCase):

    def test_exact_control_failed_at_top_level_holds(self):
        assert_suppressed(self, draft_of(
            {"control_failed": True}))

    def test_control_failure_name_at_top_level(self):
        assert_suppressed(self, draft_of(
            {"control_failure": True}))

    def test_dressed_forms_at_top_level(self):
        for key in ("Control_Failed", "control-failed",
                    "CONTROL FAILED", "controlFailed",
                    "control__failed"):
            with self.subTest(key=key):
                assert_suppressed(self, draft_of({key: True}))

    def test_control_flag_name_at_top_level(self):
        assert_suppressed(self, draft_of(
            {"control_flag": True}))

    def test_exact_name_nested_in_a_record_member(self):
        assert_suppressed(self, draft_of(
            {"round": {"control_failed": True}}))

    def test_exact_name_nested_in_a_list_item(self):
        assert_suppressed(self, draft_of(
            {"items": [{"control_failed": True}]}))

    def test_dressed_and_flag_forms_at_depth(self):
        assert_suppressed(self, draft_of(
            {"round": {"Control-Failed": True}}))
        assert_suppressed(self, draft_of(
            {"items": [{"control_flag": True}]}))
        assert_suppressed(self, draft_of(
            {"outer": {"inner": [
                {"control_failure": True}]}}))

    def test_rendering_agreement_on_the_ten_escape_forms(self):
        forms = (
            {"control_failure": True},
            {"Control_Failed": True},
            {"control-failed": True},
            {"CONTROL FAILED": True},
            {"controlFailed": True},
            {"control__failed": True},
            {"control_flag": True},
            {"round": {"control_failed": True}},
            {"items": [{"control_failed": True}]},
            {"round": {"control_failure": True}},
        )
        self.assertEqual(len(forms), 10)
        for record in forms:
            with self.subTest(record=repr(sorted(record))):
                rendered = reporting.render(
                    dict(record, opening_text="Line.",
                         actions=[{"code": "NOT_NAMED"}]),
                    form="advanced")
                self.assertEqual(
                    rendered.get("control_failure_notice"),
                    reporting.CONTROL_FAILURE_NOTICE)
                assert_suppressed(self, draft_of(record))

    def test_false_and_zero_flags_produce_actions(self):
        for record in ({"control_failed": False},
                       {"control_flag": 0},
                       {"Control_Failed": False},
                       {"round": {"control_failure": 0}}):
            with self.subTest(record=repr(sorted(record))):
                assert_escaped(self, draft_of(record))

    def test_truthiness_stands_as_the_rendering_judges_it(self):
        assert_suppressed(self, draft_of(
            {"control-failed": "false"}))
        assert_escaped(self, draft_of(
            {"control-failed": ""}))

    def test_caller_argument_still_suppresses(self):
        draft = guide.draft_from_round(
            {}, canonical_line=CANON, answers=ANSWERS,
            control_failed=True)
        assert_suppressed(self, draft)

    def test_service_route_passes_the_stored_round_record(self):
        source = inspect.getsource(service._guide_impl)
        self.assertIn("guide_module.draft_from_round(", source)
        self.assertIn("round_record,", source)


# ----------------------------------------------------------------
# Entry S17-R15-008: a non string term in a stored alias
# or category list raises a raw TypeError and kills the
# draft. A non string term stands skipped, the naming
# test and the draft standing whole, the whole value
# guard and the absent item standing standing whole.
# ----------------------------------------------------------------

class Test008NonStringTermGuard(unittest.TestCase):

    def test_integer_alias_in_the_naming_test(self):
        self.assertFalse(guide.passes_naming_test(
            SENTENCE, "Citeline", aliases=[7]))

    def test_bytes_alias_in_the_naming_test(self):
        self.assertFalse(guide.passes_naming_test(
            SENTENCE, "Citeline", aliases=[b"other"]))

    def test_float_term_in_the_category_list(self):
        self.assertFalse(guide.passes_naming_test(
            SENTENCE, "Citeline", category_terms=[2.5]))

    def test_record_term_in_the_alias_list(self):
        self.assertFalse(guide.passes_naming_test(
            SENTENCE, "Citeline", aliases=[{"x": 1}]))

    def test_non_string_term_at_the_choosing_reading(self):
        chosen = guide.choose_evidence_sentence(
            [SENTENCE], "Citeline", aliases=[7])
        self.assertEqual(chosen, SENTENCE)

    def audit_draft(self, **record_kw):
        record = {
            "run_id": "r1",
            "evidence_sentences": [SENTENCE],
            "trigger_codes": ["FAIL_CITATIONS"],
        }
        record.update(record_kw)
        return guide.draft_from_audit_record(
            record, product_name="Citeline")

    def test_draft_with_integer_alias_item_stands_produced(self):
        draft = self.audit_draft(aliases=["ok", 7])
        self.assertEqual(
            [action["code"] for action in draft["actions"]],
            ["FAIL_CITATIONS"])
        self.assertIn(SENTENCE, draft["opening_text"])

    def test_draft_with_float_category_item_stands_produced(self):
        draft = self.audit_draft(category_terms=[2.5])
        self.assertEqual(
            [action["code"] for action in draft["actions"]],
            ["FAIL_CITATIONS"])

    def test_draft_with_bytes_alias_item_stands_produced(self):
        draft = self.audit_draft(aliases=[b"other"])
        self.assertEqual(
            [action["code"] for action in draft["actions"]],
            ["FAIL_CITATIONS"])

    def test_masked_form_stands_whole_as_a_control(self):
        self.assertTrue(guide.passes_naming_test(
            "Citeline grew 20% in 2025.", "Citeline",
            aliases=[7]))

    def test_whole_integer_alias_value_stands_guarded(self):
        draft = self.audit_draft(aliases=7)
        self.assertEqual(
            [action["code"] for action in draft["actions"]],
            ["FAIL_CITATIONS"])

    def test_none_item_raises_nothing_as_a_control(self):
        self.assertFalse(guide.passes_naming_test(
            SENTENCE, "Citeline", aliases=[None]))

    def test_string_terms_still_match(self):
        self.assertTrue(guide.passes_naming_test(
            "The Gadget grew 20% in 2025.", "Citeline",
            aliases=["Gadget"]))
        self.assertTrue(guide.passes_naming_test(
            "Citation software grew 20% in 2025.",
            "Citeline", category_terms=["Citation software"]))


# ----------------------------------------------------------------
# Seam verdict pins, in their standing forms, judged on
# the new forms of the round 15 guide paper.
# ----------------------------------------------------------------

class TestSeam015FailureLine(unittest.TestCase):

    def test_literal_escape_sequence_beside_a_separator(self):
        line = reporting._failure_record_line({
            "operation": "op", "error_value": "a\\u2028b, c",
            "subject_identity": "s"})
        self.assertEqual(len(line.splitlines()), 1)

    def test_break_in_a_partial_field_name(self):
        line = reporting._failure_record_line({
            "operation": "op", "field\nname": "v"})
        self.assertEqual(len(line.splitlines()), 1)

    def test_container_values_in_the_partial_form(self):
        line = reporting._failure_record_line({
            "operation": "op",
            "extra_record": {"k\ney": 1},
            "extra_list": ["x", "y"]})
        self.assertEqual(len(line.splitlines()), 1)


class TestSeam016LongerCompoundInItsBound(unittest.TestCase):

    def test_decimal_values_at_the_scalar_branch(self):
        for key in ("pct_confidence_value", "rate", "score"):
            with self.subTest(key=key):
                line = line_for(key, Decimal("0.123456789"))
                self.assertIn(FIG_TEXT, line)
        line = line_for(
            "pct_confidence_value", Decimal("987.654321"))
        self.assertIn("987.6543", line)

    def test_string_figure_forms_at_the_scalar_branch(self):
        for value, shown in (
                ("1,234.56789", "1234.5679"),
                (" 0.123456789 ", FIG_TEXT),
                ("+0.123456789", FIG_TEXT),
                (".123456789", FIG_TEXT),
                ("1.23456789e-1", FIG_TEXT)):
            with self.subTest(value=repr(value)):
                line = line_for("pct_confidence_value", value)
                self.assertIn(shown, line)

    def test_percent_closing_string_prints_verbatim(self):
        line = line_for(
            "pct_confidence_value", "0.123456789%")
        self.assertIn("0.123456789%", line)

    def test_digit_closing_keys_stand_outside_the_limb(self):
        for key in ("pct_confidence_value2", "score_value9",
                    "rate2", "value2"):
            with self.subTest(key=key):
                line = line_for(key, FIG)
                self.assertIn(str(FIG), line)

    def test_tail_word_keys_and_fused_bounds(self):
        for key in ("alpha_score", "alpha_gross",
                    "alpha_net", "alpha_pct", "omega_share"):
            with self.subTest(key=key):
                self.assertIn(FIG_TEXT, line_for(key, FIG))
        for key in ("wilsonx", "xwilson", "ratex"):
            with self.subTest(key=key):
                self.assertIn(str(FIG), line_for(key, FIG))


class TestSeam018ListBranch(unittest.TestCase):

    def test_decimal_items_at_the_list_branch(self):
        for key in ("pct_confidence_value", "rate", "score"):
            with self.subTest(key=key):
                text = simple({"obj": {
                    key: [Decimal("0.123456789")]}})
                self.assertIn(FIG_TEXT, text)

    def test_decimal_exponent_in_both_branches(self):
        text = simple({"obj": {
            "pct_confidence_value": [Decimal("1E+2")]}})
        self.assertIn("100.0", text)
        text = simple({"obj": {
            "pct_confidence_value": Decimal("1E+2")}})
        self.assertIn("100.0", text)

    def test_set_and_record_at_the_figure_position(self):
        text = simple({"obj": {"pct_confidence_value": {FIG}}})
        self.assertIn(str(FIG), text)
        text = simple({"obj": {"pct_confidence_value": {
            "plain_key": FIG}}})
        self.assertIn(str(FIG), text)


class TestCollectorKindDiscrepancyStanding(unittest.TestCase):

    def test_exact_wrapper_surfaces_its_payload(self):
        wrapper = {"entry_kind": "failure_record",
                   "payload": PAYLOAD}
        self.assertEqual(
            reporting._failure_record_payloads(
                {"entries": [wrapper]}),
            [PAYLOAD])

    def test_dressed_wrapper_does_not_surface(self):
        wrapper = {"entry kind ": "failure_record",
                   "payload": PAYLOAD}
        self.assertNotEqual(
            reporting._failure_record_payloads(
                {"entries": [wrapper]}),
            [PAYLOAD])


if __name__ == "__main__":
    unittest.main()
