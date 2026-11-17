"""Step 17 round 12 fix seat F7 tests: service, watch, seams.

Seat F7 stands in verdict form only in this round and
carries no entry TO FIX. The pins below stand on the
cured tree as it stands at this run, in the standing
forms the round 12 papers record: the container seam
verdict at entries S17-R9-003 and S17-R9-020, the three
readings agreeing on the worked forms; the top level
key position as cured at entry S17-R10-001 standing in
its cured form at the service seam, in the primary
form and in the fallback form alike; the corrected pin
test_string_of_4096_inside_a_dict_value_refuses passing
in its renamed form; and the watch figures in their
exact forms, the WatchPlan size figure of 1 MiB and
the picked scope bound of 100 targets.
Oracle: the round 12 disposition, Section 3 seat F7,
and register Section 3, record 14, beside the follower
standings the F2 and F4 fix papers of this wave state.

Copyright: J.P. Picard aka Macro-Harder.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from citeline import acquisition, errors
from citeline import install as install_module
from citeline import journal, probe_import, service, watch

AUDIT_DATE = "2026-11-14"
PRODUCT = "Acme Ledger"
Q1 = "What is Acme Ledger?"
Q2 = "Best ferry tracker?"
ROUND = "round-1"


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


class SeededBase(unittest.TestCase):

    def setUp(self):
        self.root, self.home = make_home(self)
        seed(self, self.home)

    def answer_with_block(self, block):
        return temp_file(
            self, "---\n" + block + "\n---\n"
            "Acme Ledger is a ledger tool.\n", "answer.txt")

    def import_block(self, block):
        return do_import(self.home, self.answer_with_block(block))


class LimitedBase(SeededBase):
    """A seeded home carrying the limit in force of 100."""

    def setUp(self):
        super().setUp()
        journal.write_config(
            str(self.home),
            "front_matter_value_length_per_key = 100\n")

    def seam(self, block):
        return service._import_front_matter_limits(
            str(self.home), str(self.answer_with_block(block)))

    def seam_refuses(self, block):
        with self.assertRaises(errors.CitelineError) as caught:
            self.seam(block)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")


# ----------------------------------------------------------------
# The container seam at entries S17-R9-003 and
# S17-R9-020, in its standing form: the three readings
# agree on the worked forms.
# ----------------------------------------------------------------

class TestContainerSeamStandingForm(SeededBase):

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
                with self.assertRaises(
                        errors.CitelineError) as caught:
                    self.import_block(block)
                self.assertEqual(
                    token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_service_route_accepts_the_below_limit_key_control(self):
        self.assertIsNotNone(self.import_block(
            '{"note": {"%s": "s"}}' % ("k" * 4000)))



class TestContainerKeyAtTheSeamBothForms(LimitedBase):

    def test_container_key_of_200_refuses_at_the_seam(self):
        self.seam_refuses('{"note": {"%s": "v"}}' % ("k" * 200))

    def test_container_key_of_200_refuses_on_the_fallback(self):
        with mock.patch.object(
                probe_import, "_container_value_measure", None):
            self.seam_refuses('{"note": {"%s": "v"}}' % ("k" * 200))

    def test_container_key_and_value_summing_past_refuses(self):
        self.seam_refuses(
            '{"note": {"%s": "%s"}}' % ("k" * 90, "v" * 20))


# ----------------------------------------------------------------
# The top level key position as cured at entry
# S17-R10-001, standing in its cured form at the service
# seam, in the primary form and in the fallback form.
# ----------------------------------------------------------------

class TestTopLevelKeyCuredFormPrimary(LimitedBase):

    def test_top_level_key_of_200_refuses_at_the_seam(self):
        self.seam_refuses('{"%s": "v"}' % ("k" * 200))

    def test_top_level_key_of_5000_refuses_at_the_seam(self):
        self.seam_refuses('{"%s": "v"}' % ("k" * 5000))

    def test_top_level_key_of_200_refuses_at_the_route(self):
        answer = self.answer_with_block('{"%s": "v"}' % ("k" * 200))
        with self.assertRaises(errors.CitelineError) as caught:
            do_import(self.home, answer)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_top_level_key_of_90_passes_the_seam(self):
        self.assertIsNone(self.seam('{"%s": "v"}' % ("k" * 90)))

    def test_top_level_key_at_the_limit_passes_the_seam(self):
        self.assertIsNone(self.seam('{"%s": "v"}' % ("k" * 100)))

    def test_top_level_key_of_90_imports_whole_at_the_route(self):
        answer = self.answer_with_block('{"%s": "v"}' % ("k" * 90))
        self.assertIsNotNone(do_import(self.home, answer))


class TestTopLevelKeyCuredFormFallback(LimitedBase):

    def test_top_level_key_of_200_refuses_on_the_fallback(self):
        with mock.patch.object(
                probe_import, "_container_value_measure", None):
            self.seam_refuses('{"%s": "v"}' % ("k" * 200))

    def test_top_level_key_of_5000_refuses_on_the_fallback(self):
        with mock.patch.object(
                probe_import, "_container_value_measure", None):
            self.seam_refuses('{"%s": "v"}' % ("k" * 5000))

    def test_top_level_key_of_200_refuses_at_the_route_fallback(self):
        answer = self.answer_with_block('{"%s": "v"}' % ("k" * 200))
        with mock.patch.object(
                probe_import, "_container_value_measure", None):
            with self.assertRaises(errors.CitelineError) as caught:
                service._import_front_matter_limits(
                    str(self.home), str(answer))
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")


class TestTopLevelKeyBriefValueForms(SeededBase):

    def test_brief_value_forms_still_refuse_at_the_route(self):
        for size in (4097, 5000):
            with self.subTest(size=size):
                answer = self.answer_with_block(
                    '{"%s": "v"}' % ("k" * size))
                with self.assertRaises(Exception) as caught:
                    do_import(self.home, answer)
                self.assertEqual(
                    token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_brief_value_form_at_4096_still_imports_at_the_route(self):
        answer = self.answer_with_block(
            '{"%s": "v"}' % ("k" * 4096))
        self.assertIsNotNone(do_import(self.home, answer))


# ----------------------------------------------------------------
# The corrected pin, standing in its renamed form.
# ----------------------------------------------------------------

class TestCorrectedPinStanding(unittest.TestCase):

    def test_corrected_pin_passes_in_its_renamed_form(self):
        import importlib.util
        import io
        pin_path = (Path(__file__).resolve().parent
                    / "test_step17_r8_f2.py")
        spec = importlib.util.spec_from_file_location(
            "test_step17_r8_f2", pin_path)
        pin_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pin_module)
        suite = unittest.TestSuite()
        suite.addTest(pin_module.TestR8_028ContainerStringCharacterMeasure(
            "test_string_of_4096_inside_a_dict_value_refuses"))
        result = unittest.TextTestRunner(stream=io.StringIO()).run(suite)
        self.assertEqual(result.testsRun, 1)
        self.assertTrue(result.wasSuccessful(), result.failures)

    def test_corrected_pin_old_name_stands_in_no_test_file(self):
        tests_dir = Path(__file__).resolve().parent
        old = "test_string_of_4096_inside_a_dict_value_" + "passes"
        for path in tests_dir.glob("test_*.py"):
            self.assertNotIn(old, path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------
# The watch figures in their exact forms.
# ----------------------------------------------------------------

class TestWatchFiguresExactForms(SeededBase):

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
        self.assertEqual(watch.PLAN_SIZE_BOUND, 1048576)

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

    def test_picked_scope_bound_stands_at_100_targets(self):
        self.assertEqual(watch.TARGET_BOUND, 100)

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


if __name__ == "__main__":
    unittest.main()


# ----------------------------------------------------------------
# The page and import follower readings after the
# cures of this wave, entries S17-R12-001,
# S17-R12-006, and S17-R12-008: the two readings agree
# on the twelve widened openings and on the six
# further openings, and stand in the cured form on
# the combining mark opening, a mark outside the
# landed range refusing at the page reading as at the
# import reading since the union cure at entry
# S17-R13-001 landed, the pin at that opening standing
# corrected in place to its cured form in fix round
# 14 under ruling (f) of the round 14 disposition.
# ----------------------------------------------------------------

WIDENED_OPENINGS = (
    ".", "+", "$", "~", ";", "/", "=", "@", "^", "`",
    "́", "‿")
FURTHER_OPENINGS = ("?", "\\", "(", ")", "<", ":")
CONSTRUCT_CHARS = ("&", "*", "%", "!")


def page_outcome(block):
    text = "---\n" + block + "\n---\nbody text\n"
    try:
        acquisition._front_matter(text, "markdown", [])
        return "pass"
    except Exception as exc:
        return token_of(exc)


def import_outcome(block):
    text = "---\n" + block + "\n---\nbody text\n"
    try:
        probe_import.extract_front_matter(text)
        return "pass"
    except Exception as exc:
        return token_of(exc)


class TestFollowerReadingsAfterThisWave(unittest.TestCase):

    def test_widened_openings_refuse_at_both_readings(self):
        for construct in CONSTRUCT_CHARS:
            for opening in WIDENED_OPENINGS:
                with self.subTest(construct=construct,
                                  opening=repr(opening)):
                    block = "title: x." + construct + opening + "a"
                    self.assertEqual(
                        page_outcome(block), "PAGE_EXTRACTION_FAILED")
                    self.assertEqual(
                        import_outcome(block),
                        "IMPORT_VALIDATION_FAILED")

    def test_further_openings_refuse_at_both_readings(self):
        for construct in CONSTRUCT_CHARS:
            for opening in FURTHER_OPENINGS:
                with self.subTest(construct=construct,
                                  opening=repr(opening)):
                    block = "title: x." + construct + opening + "a"
                    self.assertEqual(
                        page_outcome(block), "PAGE_EXTRACTION_FAILED")
                    self.assertEqual(
                        import_outcome(block),
                        "IMPORT_VALIDATION_FAILED")

    def test_further_openings_refuse_at_the_json_key(self):
        for opening in FURTHER_OPENINGS:
            with self.subTest(opening=repr(opening)):
                block = json.dumps(
                    {"x.&" + opening + "a": "v"}, ensure_ascii=False)
                self.assertEqual(
                    page_outcome(block), "PAGE_EXTRACTION_FAILED")
                self.assertEqual(
                    import_outcome(block), "IMPORT_VALIDATION_FAILED")

    def test_combining_mark_in_the_landed_range_refuses_both(self):
        for opening in ("́", "ˋ"):
            with self.subTest(opening=repr(opening)):
                block = "title: x.&" + opening + "a"
                self.assertEqual(
                    page_outcome(block), "PAGE_EXTRACTION_FAILED")
                self.assertEqual(
                    import_outcome(block), "IMPORT_VALIDATION_FAILED")

    def test_combining_mark_outside_the_range_refuses_at_both_readings(self):
        for mark in ("҃", "⃐", "︠", "゙"):
            with self.subTest(mark=repr(mark)):
                block = "title: x.&" + mark + "a"
                self.assertEqual(
                    import_outcome(block), "IMPORT_VALIDATION_FAILED")
                self.assertEqual(
                    page_outcome(block), "PAGE_EXTRACTION_FAILED")

    def test_colon_on_an_indented_continuation_line_stands_seam_form(self):
        block = "title: first\n  cont x.&:a more"
        self.assertEqual(page_outcome(block), "pass")
        self.assertEqual(import_outcome(block), "pass")
        block = "title: first\n  cont x.&?a more"
        self.assertEqual(
            page_outcome(block), "PAGE_EXTRACTION_FAILED")
        self.assertEqual(
            import_outcome(block), "IMPORT_VALIDATION_FAILED")
