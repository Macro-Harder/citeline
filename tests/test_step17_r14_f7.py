"""Service, watch, seams.

Seat F7 carries one entry TO FIX in this round, Medium: the
service seam container measure in citeline/service.py
recursed with no depth guard, so a JSON front matter block
nesting past the platform recursion standing escaped
service.probe_import as a raw RecursionError with no token,
where the page reading and the import reading each refuse the
same form with LIMIT_EXCEEDED under the JSON nesting depth
limit of 100. The defect pins below stand on that entry: the
nesting depth of the parsed front matter value stands judged
at the seam, in _import_front_matter_limits, ahead of either
container measure, on an iterative count, so a block nesting
past the limit of 100 refuses at the seam and at the service
route with LIMIT_EXCEEDED, in the primary form and in the
fallback form alike, in list shape and in record shape alike,
and no nesting form escapes as a raw RecursionError at any
depth, while nothing stands accepted past the limit and the
forms at and below the limit stand as they stood. Beside the
defect pins, this file carries the standing verdict standings
of this family in the F7 form, judged first hand: the
container seam at standing whole on its worked forms, the
form holding a string of 4096 characters under a key of one
character measuring 4097, the form holding a key of 4090
characters beside a value of 10 characters measuring 4100,
and the list form holding the first form inside it measuring
4097, with the container limb judged under the limit in force
of 100; the top level key position standing cured at at the
service reading, in the primary form and in the fallback form
alike; and the watch figures in their exact forms, the
WatchPlan size figure of 1 MiB and the picked scope bound of
100 targets, with both watch modes standing as options.
Oracle: the round 14 disposition, Section 3 seat F7 and
rulings (d) and (f), the round 14 register, and the round 14
service attack paper, filing.

Copyright: J.P. Picard aka Macro-Harder."""

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


def nest_list(depth):
    value = '"x"'
    for _ in range(depth):
        value = "[" + value + "]"
    return value


def nest_record(depth):
    value = '"x"'
    for _ in range(depth):
        value = '{"n": ' + value + "}"
    return value


def block_with(value_text):
    return '{"note": ' + value_text + "}"


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

    def route_refuses_limit(self, block):
        with self.assertRaises(errors.CitelineError) as caught:
            self.import_block(block)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")


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
# Entry: the depth of the parsed front matter value stands judged
# at the seam ahead of either container measure. At the seam
# alone, under the limit in force of 100, a nesting past the depth
# limit of 100 refuses LIMIT_EXCEEDED, where the uncured seam
# passes the same forms whole on the measure of the centred
# string, standing at 1.
# ----------------------------------------------------------------

class TestDeepNestingAtTheSeamPrimary(LimitedBase):

    def test_list_nesting_at_first_depth_past_limit_refuses(self):
        self.seam_refuses(block_with(nest_list(100)))

    def test_list_nesting_well_past_limit_refuses(self):
        for depth in (150, 300):
            with self.subTest(depth=depth):
                self.seam_refuses(block_with(nest_list(depth)))

    def test_record_nesting_past_limit_refuses(self):
        for depth in (100, 300):
            with self.subTest(depth=depth):
                self.seam_refuses(block_with(nest_record(depth)))

    def test_list_nesting_past_the_recursion_flip_refuses(self):
        for depth in (500, 600):
            with self.subTest(depth=depth):
                self.seam_refuses(block_with(nest_list(depth)))

    def test_record_nesting_past_the_recursion_flip_refuses(self):
        self.seam_refuses(block_with(nest_record(500)))

    def test_list_nesting_at_2000_refuses_with_no_raw_recursion(self):
        self.seam_refuses(block_with(nest_list(2000)))

    def test_list_nesting_at_the_limit_depth_passes_the_seam(self):
        self.assertIsNone(self.seam(block_with(nest_list(99))))

    def test_record_nesting_below_the_limit_passes_the_seam(self):
        self.assertIsNone(self.seam(block_with(nest_record(50))))


class TestDeepNestingAtTheSeamFallback(LimitedBase):

    def test_list_nesting_past_flip_refuses_on_patch_forcing(self):
        with mock.patch.object(
                probe_import, "_container_value_measure", None):
            self.seam_refuses(block_with(nest_list(500)))

    def test_list_nesting_past_flip_refuses_on_deletion_forcing(self):
        original = probe_import._container_value_measure
        del probe_import._container_value_measure
        try:
            self.seam_refuses(block_with(nest_list(500)))
        finally:
            probe_import._container_value_measure = original

    def test_record_nesting_past_limit_refuses_on_patch_forcing(self):
        with mock.patch.object(
                probe_import, "_container_value_measure", None):
            self.seam_refuses(block_with(nest_record(101)))


# ----------------------------------------------------------------
# Entry at the service route: a block nesting past the limit
# refuses LIMIT_EXCEEDED at every depth, in both shapes and under
# the fallback forcing, and nothing past the limit stands
# accepted, while the form at the limit depth imports whole.
# ----------------------------------------------------------------

class TestDeepNestingAtTheRoute(SeededBase):

    def test_list_nesting_at_the_limit_depth_imports_whole(self):
        self.assertIsNotNone(
            self.import_block(block_with(nest_list(99))))

    def test_list_nesting_at_first_depth_past_limit_refuses(self):
        self.route_refuses_limit(block_with(nest_list(100)))

    def test_list_nesting_past_the_recursion_flip_refuses(self):
        for depth in (500, 600):
            with self.subTest(depth=depth):
                self.route_refuses_limit(block_with(nest_list(depth)))

    def test_record_nesting_past_the_recursion_flip_refuses(self):
        self.route_refuses_limit(block_with(nest_record(500)))

    def test_list_nesting_at_1000_refuses_at_the_route(self):
        self.route_refuses_limit(block_with(nest_list(1000)))

    def test_list_nesting_past_flip_refuses_on_fallback_forcing(self):
        answer = self.answer_with_block(block_with(nest_list(500)))
        with mock.patch.object(
                probe_import, "_container_value_measure", None):
            with self.assertRaises(errors.CitelineError) as caught:
                do_import(self.home, answer)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_home_stands_unbricked_after_a_past_flip_refusal(self):
        self.route_refuses_limit(block_with(nest_list(500)))
        self.assertIsNotNone(self.import_block(
            '{"note": "plain"}'))


# ----------------------------------------------------------------
# The container seam, in its standing form: the three readings
# agree on the worked forms, subject to the cure above on the deep
# nesting family past those forms.
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
# The top level key position as cured, standing cured at the
# service reading, in the primary form and in the fallback form
# alike.
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
# The watch figures in their exact forms, and both
# watch modes standing as options.
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
