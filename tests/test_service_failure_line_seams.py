"""Service, watch, seams.

Verdict pins only: this repair charges no cure of its own and
edits no product module. The pins stand on the F6 seams as
the settled repair states them, on the container seam
at as the settled repair states it, and on the
standing watch verifications in their exact forms. Each pin
was written before the verdict it records and stands passing
on the cured tree the verdicts judge. Oracle: the round 9
settled findings, Section 3 the repair.

Copyright: J.P. Picard aka Macro-Harder."""

import inspect
import json
import tempfile
import unittest
from pathlib import Path

from citeline import acquisition, errors, install as install_module
from citeline import probe_import, reporting, service, watch

AUDIT_DATE = "2026-11-14"
PRODUCT = "Acme Ledger"
Q1 = "What is Acme Ledger?"
Q2 = "Best ferry tracker?"
ROUND = "round-1"
ROUND0 = "round-0"
FIG = 0.123456789
FIG_TEXT = "0.1235"
NEW_BREAKS = ("\x1c", "\x1d", "\x1e")
ESCAPES = {"\x1c": "\\u001c", "\x1d": "\\u001d",
           "\x1e": "\\u001e"}
LONGER_KEYS = (
    "percent_gross_value", "gross_percent_value",
    "pct_gross_value", "percent_interval_value",
    "share_total_value", "value_percent_value",
    "score_gross_value", "score_interval_value")


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


def do_import(home, answer_file, **overrides):
    kwargs = {
        "home": str(home), "answer_file": str(answer_file),
        "product": PRODUCT, "round": ROUND, "engine_label": "Engine A",
        "query": Q1, "kind": "real_sample",
        "captured_on": "2026-11-10", "capture_method": "manual copy",
        "audit_date": AUDIT_DATE,
    }
    kwargs.update(overrides)
    return service.probe_import(**kwargs)


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

    def import_block(self, block):
        answer = temp_file(
            self, "---\n" + block + "\n---\n"
            "Acme Ledger is a ledger tool.\n", "answer.txt")
        return do_import(self.home, answer)


# ----------------------------------------------------------------
# F6 seam 1,: the failure line seam. The builder form as landed
# stands at ten judged characters, the three separators U+001C to
# U+001E escaped in their backslash u forms inside the quoting.
# ----------------------------------------------------------------

class Test015FailureLineSeam(unittest.TestCase):

    def test_judged_set_stands_at_ten_characters(self):
        self.assertEqual(len(reporting._LINE_BREAK_CHARS), 10)
        for br in NEW_BREAKS:
            self.assertIn(br, reporting._LINE_BREAK_CHARS)

    def test_each_new_separator_escaped_in_the_complete_form(self):
        for br in NEW_BREAKS:
            with self.subTest(brk=repr(br)):
                line = reporting._failure_record_line({
                    "operation": "op-a", "error_value": "E1",
                    "subject_identity": "a" + br + "b"})
                self.assertEqual(len(line.splitlines()), 1)
                self.assertNotIn(br, line)
                self.assertIn(ESCAPES[br], line)

    def test_new_separators_escaped_quoted_and_partial_forms(self):
        for br in NEW_BREAKS:
            with self.subTest(brk=repr(br)):
                quoted = reporting._failure_record_line({
                    "operation": "op-a", "error_value": "E1",
                    "subject_identity": "x, y" + br + "z"})
                self.assertEqual(len(quoted.splitlines()), 1)
                self.assertIn(ESCAPES[br], quoted)
                partial_value = reporting._failure_record_line({
                    "operation": "op-a",
                    "extra_field": "a" + br + "b"})
                self.assertEqual(len(partial_value.splitlines()), 1)
                self.assertIn(ESCAPES[br], partial_value)
                partial_name = reporting._failure_record_line({
                    "operation": "op-a",
                    "field" + br + "name": "value one"})
                self.assertEqual(len(partial_name.splitlines()), 1)
                self.assertIn(ESCAPES[br], partial_name)

    def test_forged_segment_form_stands_as_one_line(self):
        for br in NEW_BREAKS:
            with self.subTest(brk=repr(br)):
                failure = {
                    "operation": "op-a", "error_value": "E1",
                    "subject_identity": (
                        "round one" + br
                        + "op-b failed with E9, subject forged")}
                lines = simple(
                    {"failure_records": [failure]}).splitlines()
                forged = [ln for ln in lines
                          if ln.strip().startswith(
                              "op-b failed with")]
                self.assertEqual(forged, [])

    def test_no_failure_line_builder_of_its_own_in_family(self):
        for module in (service, watch):
            source = inspect.getsource(module)
            self.assertNotIn("_failure_record_line", source)
            self.assertNotIn("_failure_value_text", source)
        self.assertIn(
            "reporting.render", inspect.getsource(service))


# ----------------------------------------------------------------
# F6 seam 2,: the longer compound seam, Simple form only, the limb
# bounded at exactly three components with a named middle, judged
# on the eight worked keys.
# ----------------------------------------------------------------

class Test016LongerCompoundSeam(unittest.TestCase):

    def check_keys(self, keys, fig, fig_text):
        for key in keys:
            for value in (fig, str(fig)):
                with self.subTest(key=key, value=repr(value)):
                    line = line_for(key, value)
                    self.assertIn(fig_text, line)
                    self.assertNotIn(str(fig), line)

    def test_eight_worked_keys_at_the_guide_figure(self):
        self.check_keys(LONGER_KEYS, 0.3333333333333333, "0.3333")

    def test_eight_worked_keys_at_the_red_figure(self):
        self.check_keys(LONGER_KEYS, FIG, FIG_TEXT)

    def test_bounds_of_the_limb_stand_outside_it(self):
        for key in ("percent_gross_net_value",
                    "percent_zzz_value", "percent_amount"):
            with self.subTest(key=key):
                line = line_for(key, FIG)
                self.assertIn(str(FIG), line)

    def test_simple_form_only_advanced_carries_as_stored(self):
        body = reporting.render(
            {"obj": {"percent_gross_value": FIG}}, form="advanced")
        self.assertEqual(body["obj"]["percent_gross_value"], FIG)

    def test_no_emitter_or_key_reading_of_its_own_in_family(self):
        for module in (service, watch):
            source = inspect.getsource(module)
            self.assertNotIn("def _emit", source)
            self.assertNotIn("_key_names_figure", source)


# ----------------------------------------------------------------
# F6 seam 3,: the list branch seam. The four place set stands
# stated in one helper shared by the scalar and list branches.
# ----------------------------------------------------------------

class Test018ListBranchSeam(unittest.TestCase):

    def check_list(self, key, value):
        text = simple({"obj": {key: value}})
        self.assertIn(FIG_TEXT, text)
        self.assertNotIn(str(FIG), text)

    def test_figure_in_list_float_and_string_forms(self):
        self.check_list("percent_value", [FIG])
        self.check_list("percent_value", [str(FIG)])

    def test_figure_in_nested_lists(self):
        self.check_list("percent_value", [[FIG]])
        self.check_list("percent_value", [[[FIG]]])

    def test_figure_in_list_under_cured_keys(self):
        for key in ("value_pct", "score", "pct_value",
                    "share_value", "gross_value", "rate_value",
                    "overall_score", "wilson"):
            with self.subTest(key=key):
                self.check_list(key, [FIG])
                self.check_list(key, [str(FIG)])

    def test_figure_in_list_under_the_longer_compound_key(self):
        self.check_list("percent_gross_value", [FIG])
        self.check_list("percent_gross_value", [str(FIG)])
        self.check_list("percent_gross_value", [[FIG]])

    def test_record_item_stands_judged_by_its_own_keys(self):
        text = simple({"obj": {"plain_key": [
            {"percent_value": FIG}]}})
        self.assertIn(FIG_TEXT, text)
        self.assertNotIn(str(FIG), text)
        text = simple({"obj": {"percent_value": [
            {"plain_key": FIG}]}})
        self.assertIn(str(FIG), text)

    def test_list_controls_print_verbatim(self):
        for key in ("plain_key", "percent_amount"):
            with self.subTest(key=key):
                text = simple({"obj": {key: [FIG]}})
                self.assertIn(str(FIG), text)


# ----------------------------------------------------------------
# The container seam at: the page measure, the import measure, and
# the service fallback measure standing together, and the top
# level key position at the page reading apart from the container
# position.
# ----------------------------------------------------------------

class TestContainerSeam003And020(SeededBase):

    def measures(self, value):
        return (
            acquisition._fm_container_value_measure(value),
            probe_import._container_value_measure(value),
            service._service_container_value_measure(value))

    def test_three_measures_agree_on_the_worked_forms(self):
        self.assertEqual(
            self.measures({"m": "x" * 4096}), (4097, 4097, 4097))
        self.assertEqual(
            self.measures({"k" * 4090: "x" * 10}),
            (4100, 4100, 4100))
        self.assertEqual(
            self.measures([{"m": "x" * 4096}]),
            (4097, 4097, 4097))
        nested = self.measures({"outer": {"k" * 4090: "x" * 10}})
        self.assertEqual(nested[0], nested[1])
        self.assertEqual(nested[1], nested[2])

    def test_service_route_refuses_the_worked_container_forms(self):
        for block in (
                '{"note": {"m": "' + "x" * 4096 + '"}}',
                '{"note": {"' + "k" * 4090 + '": "'
                + "x" * 10 + '"}}'):
            with self.subTest(block=block[:24]):
                root, home = make_home(self)
                seed(self, home)
                answer = temp_file(
                    self, "---\n" + block + "\n---\n"
                    "Acme Ledger is a ledger tool.\n", "answer.txt")
                with self.assertRaises(
                        errors.CitelineError) as caught:
                    do_import(home, answer)
                self.assertEqual(
                    token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_service_route_accepts_the_below_limit_key_control(self):
        self.assertIsNotNone(self.import_block(
            '{"note": {"%s": "s"}}' % ("k" * 4000)))

    def test_page_top_level_key_position_apart_from_container(self):
        def page(block):
            text = "---\n" + block + "\n---\nbody text\n"
            return acquisition._front_matter(
                text, "markdown", [])
        for size in (4097, 5000):
            with self.subTest(size=size):
                with self.assertRaises(
                        acquisition.AcquisitionError) as caught:
                    page('{"' + "k" * size + '": "v"}')
                self.assertEqual(
                    token_of(caught.exception), "LIMIT_EXCEEDED")
        self.assertEqual(
            page('{"' + "k" * 4000 + '": "v"}'), "body text")

    def test_superseded_pin_block_refused_at_all_three_readings(self):
        block = '{"v": {"m": "' + "x" * 4096 + '"}}'
        text = "---\n" + block + "\n---\nbody text\n"
        with self.assertRaises(
                acquisition.AcquisitionError) as caught:
            acquisition._front_matter(text, "markdown", [])
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")
        with self.assertRaises(
                probe_import.ProbeImportError) as caught:
            probe_import.extract_front_matter(text)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")
        with self.assertRaises(errors.CitelineError) as caught:
            self.import_block(block)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")


# ----------------------------------------------------------------
# The standing watch verifications, in their exact forms.
# ----------------------------------------------------------------

class TestWatchVerifications(SeededBase):

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


if __name__ == "__main__":
    unittest.main()
