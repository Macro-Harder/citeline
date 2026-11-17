"""Step 17 round 13 fix seat F6 tests: guide and reporting.

Verdict pins only: this seat charges no cure of its own
and edits no product module. The pins stand on the
guide and reporting seams in the standing form (the
failure line seam at entry S17-R9-015, the longer
compound seam at entry S17-R9-016, and the list branch
seam at entry S17-R9-018, as the round 9 F6 fix paper
states them and the round 13 guide paper rejudged
them on new forms), on the collector kind discrepancy
in its sustained recorded form at register Section 3,
record 4 of the round 12 register, extended on the new
forms the round 13 guide paper runs, and on the
standing watch figures and the methods note version
stamp in their exact forms. Each pin was written
before the verdict it records and stands passing on
the tree the verdicts judge.
Oracle: the round 13 findings register and
disposition, ruling (n) and Section 3 seat F6.

Copyright: J.P. Picard aka Macro-Harder.
"""

import inspect
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from citeline import errors, install as install_module
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
    "percent_high_value", "share_interval_value",
    "gross_score_value", "net_pct_value",
    "score_rate_value", "pct_share_value",
    "share_percent_value", "gross_net_value",
    "net_gross_value")
VALUE_HEADED_KEYS = (
    "value_high_value", "value_interval_value",
    "value_score_value", "value_rate_value",
    "value_pct_value")
NEW_LIST_KEYS = (
    "percent_high_value", "share_interval_value",
    "Percent High Value", "percentHighValue",
    "value_rate_value")
BOUND_KEYS = (
    "alpha_high_value", "omega_interval_value",
    "percent_high_net_value", "gross_mean_net_value",
    "percent_omega_value", "percent_alpha_value",
    "Percent_Omega_Value", "percent_high_amount",
    "percent_high_total", "percent_high_value_extra",
    "percent_high_values")
PAYLOAD = {"operation": "op-a", "error_value": "E1",
           "subject_identity": "s"}


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


class SeededBase(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)
        seed(self, self.home)


# ----------------------------------------------------------------
# Seam 1, entry S17-R9-015: the failure line seam. The
# judged set stands at ten characters, equal to the
# whole line boundary set under the standard reading,
# judged exhaustively, and the round 13 forms plant
# breaks at the subject position, in all three complete
# fields at once, and in further partial field names.
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

    def test_break_in_subject_with_forged_segment_all_ten(self):
        for br in ALL_BREAKS:
            with self.subTest(brk=repr(br)):
                line = reporting._failure_record_line({
                    "operation": "op-a", "error_value": "E1",
                    "subject_identity": (
                        "s" + br
                        + "forged failed with X, subject Y")})
                self.assertEqual(len(line.splitlines()), 1)
                self.assertNotIn(br, line)

    def test_break_in_all_three_complete_fields_all_ten(self):
        for br in ALL_BREAKS:
            with self.subTest(brk=repr(br)):
                line = reporting._failure_record_line({
                    "operation": "o" + br + "a",
                    "error_value": "e" + br + "b",
                    "subject_identity": "s" + br + "c"})
                self.assertEqual(len(line.splitlines()), 1)
                self.assertNotIn(br, line)

    def test_break_in_further_partial_fields(self):
        for field in ("operator_note", "source_ref", "retry_count"):
            for br in ("\n", "\x1e", "\u2029"):
                with self.subTest(field=field, brk=repr(br)):
                    line = reporting._failure_record_line({
                        "operation": "op-a",
                        field: "x" + br + "forged failed with X"})
                    self.assertEqual(len(line.splitlines()), 1)
                    self.assertNotIn(br, line)

    def test_new_stress_combinations_stand_as_one_line(self):
        for value in ("\n", "\r\n\r\n", "a\u2028\u2029b",
                      "x\r\ry", "\x1c\x1c\x1c"):
            with self.subTest(value=repr(value)):
                line = reporting._failure_record_line({
                    "operation": "op-a", "error_value": value,
                    "subject_identity": "s"})
                self.assertEqual(len(line.splitlines()), 1)

    def test_two_failure_records_in_new_positions_two_lines(self):
        first = {"operation": "op-a", "error_value": "E1",
                 "subject_identity": "s\u2029tail"}
        second = {"operation": "o\x0bp", "error_value": "E2",
                  "subject_identity": "t"}
        text = simple({"failure_records": [first, second]})
        section = text.split("Failure records", 1)[1]
        lines = [ln for ln in section.splitlines()
                 if "failed with" in ln]
        self.assertEqual(len(lines), 2)

    def test_new_non_string_values_in_partial_payload_one_line(self):
        for value in ([], {}, 0, -1.5):
            with self.subTest(value=repr(value)):
                line = reporting._failure_record_line({
                    "operation": "op-a", "extra_field": value})
                self.assertEqual(len(line.splitlines()), 1)

    def test_literal_escape_text_renders_unchanged(self):
        for value in (r"a\nb", r"a\u001cb"):
            with self.subTest(value=value):
                line = reporting._failure_record_line({
                    "operation": "op-a", "error_value": value})
                self.assertEqual(len(line.splitlines()), 1)
                self.assertIn(value, line)

    def test_unit_separator_and_companions_in_subject_raw_one_line(self):
        for value in ("a\x1fb", "a\u200bb", "a\ufeffb",
                      "a\x00\x07b", "a\xa0b", "a\u180eb"):
            with self.subTest(value=repr(value)):
                line = reporting._failure_record_line({
                    "operation": "op-a", "error_value": "E1",
                    "subject_identity": value})
                self.assertEqual(len(line.splitlines()), 1)
        line = reporting._failure_record_line({
            "operation": "op-a", "error_value": "E1",
            "subject_identity": "a\x1fb"})
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
# new middle components of round 13: high, interval,
# score, pct, rate, value, gross, net, share, percent.
# ----------------------------------------------------------------

class Test016LongerCompoundSeamVerdict(unittest.TestCase):

    def check_keys(self, keys, fig, fig_text):
        for key in keys:
            for value in (fig, str(fig)):
                with self.subTest(key=key, value=repr(value)):
                    line = line_for(key, value)
                    self.assertIn(fig_text, line)
                    self.assertNotIn(str(fig), line)

    def test_new_middle_compounds_print_at_four_places(self):
        self.check_keys(NEW_SCALAR_KEYS, FIG, FIG_TEXT)

    def test_value_headed_compounds_on_new_middles(self):
        self.check_keys(VALUE_HEADED_KEYS, FIG, FIG_TEXT)

    def test_middle_standing_as_value_itself(self):
        self.check_keys(("percent_value_value",), FIG, FIG_TEXT)

    def test_new_middle_dressings_print_at_four_places(self):
        self.check_keys(
            ("Percent High Value", "percent/high/value",
             "percent+high+value", "PERCENT.HIGH.VALUE",
             "percentHighValue", "share-high-value",
             "Share_Interval_Value", "VALUE RATE VALUE",
             "valueRateValue"),
            FIG, FIG_TEXT)

    def test_new_figure_value_forms_under_the_new_key(self):
        key = "percent_high_value"
        for value, shown in (
                (-0.123456789, "-0.1235"),
                (123.456789, "123.4568"),
                ("0.123456789e0", "0.1235"),
                (" 0.123456789 ", "0.1235"),
                ("+.123456789", "0.1235"),
                (Decimal("-0.123456789"), "-0.1235")):
            with self.subTest(value=repr(value)):
                self.assertIn(shown, line_for(key, value))
        self.assertIn("7", line_for(key, 7))
        self.assertNotIn(FIG_TEXT, line_for(key, 7))

    def test_bounds_of_the_limb_stand_outside_it_scalar(self):
        for key in BOUND_KEYS:
            with self.subTest(key=key):
                line = line_for(key, FIG)
                self.assertIn(str(FIG), line)

    def test_rate_digit_forms_stand_on_their_own_limb(self):
        self.check_keys(
            ("percent_high_rate2", "share_interval_rate9"),
            FIG, FIG_TEXT)

    def test_new_key_at_top_level_and_two_levels_deep(self):
        # Repair pin added by the reseat: the inherited file
        # pinned the new scalar keys only under one record
        # level, and the guide paper names the judgement
        # standing at the top level and at depth as carried
        # in pins.
        text = simple({"percent_high_value": FIG})
        self.assertIn(FIG_TEXT, text)
        self.assertNotIn(str(FIG), text)
        text = simple({"outer": {"inner": {
            "percent_high_value": FIG}}})
        self.assertIn(FIG_TEXT, text)
        self.assertNotIn(str(FIG), text)

    def test_simple_form_only_advanced_carries_as_stored(self):
        body = reporting.render(
            {"obj": {"percent_high_value": FIG}}, form="advanced")
        self.assertEqual(body["obj"]["percent_high_value"], FIG)

    def test_no_emitter_or_key_reading_of_its_own_in_family(self):
        for module in (service, watch):
            source = inspect.getsource(module)
            self.assertNotIn("def _emit", source)
            self.assertNotIn("_key_names_figure", source)
            self.assertNotIn("claim_type", source)


# ----------------------------------------------------------------
# Seam 3, entry S17-R9-018: the list branch seam. The
# four place set stands stated in one helper shared by
# the scalar and list branches, judged on the new
# compound keys of round 13 at the list branch, nested
# six levels deep, and on the record stop one level
# deeper than the earlier rounds ran it.
# ----------------------------------------------------------------

class Test018ListBranchSeamVerdict(unittest.TestCase):

    def check_list(self, key, value):
        text = simple({"obj": {key: value}})
        self.assertIn(FIG_TEXT, text)
        self.assertNotIn(str(FIG), text)

    def test_new_compound_keys_at_the_list_branch(self):
        for key in NEW_LIST_KEYS:
            with self.subTest(key=key):
                self.check_list(key, [FIG])
                self.check_list(key, [str(FIG)])

    def test_new_compound_keys_nested_six_levels_deep(self):
        for key in NEW_LIST_KEYS:
            with self.subTest(key=key):
                self.check_list(key, [[[[[[FIG]]]]]])

    def test_tuple_and_mixed_items_at_the_list_branch(self):
        self.check_list("percent_high_value", (FIG, str(FIG)))
        text = simple({"obj": {"percent_high_value": [
            Decimal("0.123456789"), 7, False, FIG]}})
        self.assertIn(FIG_TEXT, text)
        self.assertIn("7", text)
        self.assertIn("false", text)

    def test_empty_list_forms_render_no_figure_item(self):
        for value in ([], [[[]]]):
            with self.subTest(value=repr(value)):
                text = simple({"obj": {"percent_high_value": value}})
                self.assertNotIn(FIG_TEXT, text)
                self.assertNotIn(str(FIG), text)

    def test_record_stop_judged_one_level_deeper(self):
        text = simple({"obj": {"plain_outer": [
            [[{"percent_high_value": [FIG]}]]]}})
        self.assertIn(FIG_TEXT, text)
        self.assertNotIn(str(FIG), text)
        text = simple({"obj": {"percent_high_value": [
            [[{"plain_key": [FIG]}]]]}})
        self.assertIn(str(FIG), text)
        text = simple({"obj": {"percent_high_value": [
            {"plain_key": FIG}]}})
        self.assertIn(str(FIG), text)

    def test_bounds_of_the_limb_stand_outside_it_in_lists(self):
        for key in BOUND_KEYS:
            with self.subTest(key=key):
                text = simple({"obj": {key: [FIG]}})
                self.assertIn(str(FIG), text)

    def test_rate_digit_forms_at_the_list_branch(self):
        self.check_list("percent_high_rate2", [FIG])
        self.check_list("share_interval_rate9", [FIG])

    def test_list_controls_print_verbatim(self):
        for key in ("plain_key", "percent_amount"):
            with self.subTest(key=key):
                text = simple({"obj": {key: [FIG]}})
                self.assertIn(str(FIG), text)


# ----------------------------------------------------------------
# The collector kind discrepancy, in its sustained
# recorded form: the round 8 guide paper NO FINDING 7
# wording stands corrected in effect by the round 9
# register record, and the dressed kind and payload
# forms stand as a bounded observation, extended on
# the new forms the round 13 guide paper runs. These
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

    def test_round13_kind_key_forms_do_not_surface(self):
        for key in ("entryKind ", "Entry-Kind", "entry kind!",
                    "entry__kind__", "ENTRY_KIND ", "entrykind."):
            with self.subTest(key=key):
                wrapper = {key: "failure_record",
                           "payload": PAYLOAD}
                self.assertFalse(self.surfaces(wrapper))

    def test_round13_kind_value_forms_do_not_surface(self):
        for value in ("failure_record\n", "failure_record.",
                      "Failure_Record ", "failure-record ",
                      "FAILURE_RECORD.", "failure record "):
            with self.subTest(value=value):
                wrapper = {"entry_kind": value,
                           "payload": PAYLOAD}
                self.assertFalse(self.surfaces(wrapper))

    def test_round13_payload_member_forms_do_not_surface(self):
        for key in ("payLoads", "PAY-LOAD", "pay__load",
                    "p ayload"):
            with self.subTest(key=key):
                wrapper = {"entry_kind": "failure_record",
                           key: PAYLOAD}
                self.assertFalse(self.surfaces(wrapper))

    def test_round13_combined_dressings_do_not_surface(self):
        for wrapper in (
                {"entryKind ": "Failure-Record",
                 "payload": PAYLOAD},
                {"entry_kind": "failure-record ",
                 "payLoads": PAYLOAD},
                {"ENTRY_KIND ": "FAILURE_RECORD.",
                 "PAY-LOAD": PAYLOAD}):
            with self.subTest(wrapper=repr(sorted(wrapper))):
                self.assertFalse(self.surfaces(wrapper))

    def test_round13_single_word_member_controls_surface(self):
        for key in ("_payload", "payload-", "payload_",
                    "payload.."):
            with self.subTest(key=key):
                wrapper = {"entry_kind": "failure_record",
                           key: PAYLOAD}
                self.assertTrue(self.surfaces(wrapper))

    def test_round13_entries_key_forms_surface_the_payload(self):
        wrapper = {"entry_kind": "failure_record",
                   "payload": PAYLOAD}
        for key in ("ENTRIES", "allEntries", "entries_list",
                    "the-entries"):
            with self.subTest(key=key):
                got = reporting._failure_record_payloads(
                    {key: [wrapper]})
                self.assertEqual(got, [PAYLOAD])
        nested = reporting._failure_record_payloads(
            {"entries": [[[wrapper]]]})
        self.assertEqual(nested, [PAYLOAD])
        self.assertEqual(
            reporting._failure_record_payloads(
                {"entry": [wrapper]}), [])

    def test_round13_list_and_single_form_reach(self):
        dressed = {"entryKind ": "failure_record",
                   "payload": PAYLOAD}
        got = reporting._failure_record_payloads(
            {"failure_records": [dressed]})
        self.assertEqual(got, [dressed])
        dotted = {"entry_kind": "failure_record.",
                  "payload": PAYLOAD}
        got = reporting._failure_record_payloads(
            {"failure_records": [dotted]})
        self.assertEqual(got, [dotted])
        split_member = {"entry_kind": "failure_record",
                        "payLoads": PAYLOAD}
        got = reporting._failure_record_payloads(
            {"failure_record": split_member})
        self.assertEqual(got, [split_member])
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
