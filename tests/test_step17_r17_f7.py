"""Step 17 round 17 fix seat F7 tests: service, watch, seams.

Seat F7 carries no entry TO FIX in fix round 17. This
file pins the sustained verdict standings of the seat
in the forms the round 17 service and seams papers
verify first hand on the cured tree: the cure at
entry S17-R15-009 standing sustained whole, the
iterative string aware bracket depth helper
_front_matter_block_depth at _front_matter_key_count
in citeline/service.py refusing LIMIT_EXCEEDED ahead
of the parse where depth stands past 100, the parse
catching RecursionError beside ValueError, and
exactly one failure record standing appended for a
refusal on the audit route, at the boundary forms
the round 17 service seat ran, depth 99 of the
nesting passing in list shape and in record shape,
depths 100 to 100000 refusing, mixed nesting standing
exact at bracket depth 100 and refusing at 101, and
brackets inside key strings standing uncounted; and
the seam cure at entry S17-R14-004 standing sustained
whole, depth standing judged at the service seam
ahead of either container measure, _service_json_depth
against _SERVICE_JSON_DEPTH_LIMIT at 100, with no raw
RecursionError at any depth, in the primary form and
in the fallback form alike.
Oracle: Section 3 of the round 17 disposition, seat
F7 paragraph, with ruling (d), the round 17 service
paper at design/audit/step-17-r17-attack-service.md,
the round 17 seams paper at
design/audit/step-17-r17-attack-seams.md, and the fix
round 16 F7 paper at design/audit/step-17-r16-fix-f7.md.

Copyright: J.P. Picard aka Macro-Harder.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from citeline import errors
from citeline import install as install_module
from citeline import journal, probe_import, service

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
    path.write_text(content, encoding="utf-8")
    return path


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


def nest_mixed(depth):
    value = '"x"'
    for index in range(depth):
        if index % 2 == 0:
            value = "[" + value + "]"
        else:
            value = '{"n": ' + value + "}"
    return value


def block_with(value_text):
    return '{"note": ' + value_text + "}"


def page_with_block(block):
    return ("---\n" + block + "\n---\n# Title\n\n"
            "Acme Ledger helps teams track citations. "
            "Body text.\n")


def failure_record_count(home):
    path = Path(home) / "journal.jsonl"
    if not path.exists():
        return 0
    entries = [json.loads(line) for line in
               path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    return len([entry for entry in entries
                if entry.get("entry_kind") == "failure_record"])


class SeededBase(unittest.TestCase):

    def setUp(self):
        self.root, self.home = make_home(self)
        seed(self, self.home)

    def page(self, block, name="page.md"):
        return temp_file(self, page_with_block(block), name)

    def audit(self, page):
        return service.audit(
            home=str(self.home), page_file=str(page),
            audit_date=AUDIT_DATE)

    def audit_refuses_limit_one_record(self, page):
        before = failure_record_count(self.home)
        with self.assertRaises(errors.CitelineError) as caught:
            self.audit(page)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")
        self.assertEqual(
            failure_record_count(self.home), before + 1)


# ----------------------------------------------------------------
# The depth helper of the cure at entry S17-R15-009 on
# the new forms of round 17: mixed nesting standing
# exact at the boundary, the judgement standing on the
# deepest branch and not on any sum, and brackets
# inside key strings standing uncounted.
# ----------------------------------------------------------------

class TestDepthHelperRound17Forms(unittest.TestCase):

    def depth(self, block):
        return service._front_matter_block_depth(block)

    def test_mixed_nesting_depth_stands_exact_at_the_boundary(self):
        self.assertEqual(self.depth(block_with(nest_mixed(98))), 99)
        self.assertEqual(self.depth(block_with(nest_mixed(99))), 100)
        self.assertEqual(self.depth(block_with(nest_mixed(100))), 101)
        self.assertEqual(self.depth(block_with(nest_mixed(101))), 102)

    def test_two_branch_depth_stands_on_the_deepest_branch(self):
        block = ('{"a": ' + nest_list(99) +
                 ', "b": ' + nest_record(99) + "}")
        self.assertEqual(self.depth(block), 100)
        shallow = ('{"a": ' + nest_list(60) +
                   ', "b": ' + nest_record(60) + "}")
        self.assertEqual(self.depth(shallow), 61)

    def test_brackets_inside_a_key_string_do_not_count(self):
        block = '{"' + "[" * 300 + "{" * 300 + '": 1, "note": "x"}'
        self.assertEqual(self.depth(block), 1)

    def test_brackets_inside_a_value_string_do_not_count(self):
        block = '{"note": "' + "[" * 300 + '", "other": 1}'
        self.assertEqual(self.depth(block), 1)


# ----------------------------------------------------------------
# Entry S17-R15-009 at the counter on the round 17
# boundary forms: nesting depth 99 passing in both
# shapes, depths 100 to 100000 refusing, mixed nesting
# exact at bracket depth 100 and refusing at 101, and
# brackets inside a key string standing uncounted, with
# no raw RecursionError standing raised at any depth.
# ----------------------------------------------------------------

class TestCounterRound17Forms(unittest.TestCase):

    def counter(self, block):
        root = Path(self.enterContext(
            tempfile.TemporaryDirectory()))
        page = root / "page.md"
        page.write_text(
            page_with_block(block), encoding="utf-8")
        return service._front_matter_key_count(str(page))

    def counter_refuses_limit(self, block):
        with self.assertRaises(errors.CitelineError) as caught:
            self.counter(block)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_counter_depth_99_passes_in_both_shapes(self):
        self.assertEqual(
            self.counter(block_with(nest_list(99))), 1)
        self.assertEqual(
            self.counter(block_with(nest_record(99))), 1)

    def test_counter_depths_100_to_100000_refuse_in_both_shapes(self):
        for depth in (100, 101, 1000, 100000):
            with self.subTest(shape="list", depth=depth):
                self.counter_refuses_limit(
                    block_with(nest_list(depth)))
        for depth in (100, 101, 100000):
            with self.subTest(shape="record", depth=depth):
                self.counter_refuses_limit(
                    block_with(nest_record(depth)))

    def test_counter_mixed_at_bracket_depth_100_returns_its_count(self):
        self.assertEqual(
            self.counter(block_with(nest_mixed(99))), 1)

    def test_counter_mixed_at_bracket_depth_101_refuses(self):
        self.counter_refuses_limit(block_with(nest_mixed(100)))

    def test_counter_brackets_inside_a_key_string_return_count(self):
        block = '{"' + "[" * 300 + '": 1, "note": "x"}'
        self.assertEqual(self.counter(block), 2)

    def test_counter_two_branches_at_depth_99_each_return_count(self):
        block = ('{"a": ' + nest_list(99) +
                 ', "b": ' + nest_record(99) + "}")
        self.assertEqual(self.counter(block), 2)


# ----------------------------------------------------------------
# Entry S17-R15-009 at the preflight and through
# service.audit whole on the round 17 forms: the mixed
# form at the limit standing passed and running whole,
# the forms past the limit refusing with exactly one
# failure record each, and repeated refusals standing
# at one record each with no compounding.
# ----------------------------------------------------------------

class TestPreflightAndRouteRound17Forms(SeededBase):

    def preflight(self, page):
        start_limits = {"by_limit": {
            "page_file_size": {"value": 1},
            "front_matter_key_count": {"value": 100}}}
        return service._audit_preflight_limits(
            str(self.home), str(page), start_limits)

    def test_preflight_mixed_at_the_limit_passes(self):
        page = self.page(block_with(nest_mixed(99)))
        self.assertIsNone(self.preflight(page))

    def test_preflight_mixed_past_the_limit_refuses(self):
        page = self.page(block_with(nest_mixed(100)))
        with self.assertRaises(errors.CitelineError) as caught:
            self.preflight(page)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_audit_mixed_at_the_limit_runs_whole(self):
        result = self.audit(self.page(block_with(nest_mixed(99))))
        self.assertIsInstance(result, dict)

    def test_audit_mixed_past_the_limit_one_failure_record(self):
        self.audit_refuses_limit_one_record(
            self.page(block_with(nest_mixed(100))))

    def test_audit_list_at_depth_100000_one_failure_record(self):
        self.audit_refuses_limit_one_record(
            self.page(block_with(nest_list(100000))))

    def test_audit_record_at_depth_100_one_failure_record(self):
        self.audit_refuses_limit_one_record(
            self.page(block_with(nest_record(100))))

    def test_audit_repeated_refusals_each_add_one_failure_record(self):
        page = self.page(block_with(nest_list(100)))
        self.audit_refuses_limit_one_record(page)
        self.audit_refuses_limit_one_record(page)


# ----------------------------------------------------------------
# The seam cure at entry S17-R14-004 on the round 17
# forms: _service_json_depth standing exact against
# its limit of 100 on built values, the seam refusing
# past the limit on mixed shapes alike, and the
# refusal standing whole under the fallback forcing,
# with no raw RecursionError at any depth run.
# ----------------------------------------------------------------

class TestSeamCureRound17Forms(SeededBase):

    def setUp(self):
        super().setUp()
        journal.write_config(
            str(self.home),
            "front_matter_value_length_per_key = 100\n")

    def seam(self, block):
        root = Path(self.enterContext(
            tempfile.TemporaryDirectory()))
        answer = root / "answer.txt"
        answer.write_text(
            "---\n" + block + "\n---\n"
            "Acme Ledger is a ledger tool.\n", encoding="utf-8")
        return service._import_front_matter_limits(
            str(self.home), str(answer))

    def seam_refuses_limit(self, block):
        with self.assertRaises(errors.CitelineError) as caught:
            self.seam(block)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_service_json_depth_stands_exact_against_its_limit(self):
        self.assertEqual(service._SERVICE_JSON_DEPTH_LIMIT, 100)
        value = "x"
        for _ in range(99):
            value = [value]
        self.assertEqual(service._service_json_depth({"n": value}), 100)
        deeper = [value]
        self.assertEqual(
            service._service_json_depth({"n": deeper}), 101)

    def test_seam_mixed_at_bracket_depth_100_passes(self):
        self.assertIsNone(self.seam(block_with(nest_mixed(99))))

    def test_seam_mixed_at_bracket_depth_101_refuses(self):
        self.seam_refuses_limit(block_with(nest_mixed(100)))

    def test_seam_list_and_record_past_the_limit_refuse(self):
        self.seam_refuses_limit(block_with(nest_list(100)))
        self.seam_refuses_limit(block_with(nest_record(100)))

    def test_seam_list_at_depth_500_refuses_with_no_raw_recursion(self):
        self.seam_refuses_limit(block_with(nest_list(500)))

    def test_seam_past_the_limit_refuses_on_fallback_patch_forcing(self):
        with mock.patch.object(
                probe_import, "_container_value_measure", None):
            self.seam_refuses_limit(block_with(nest_list(100)))
            self.seam_refuses_limit(block_with(nest_mixed(100)))

    def test_seam_past_the_limit_refuses_on_fallback_deletion_forcing(self):
        original = probe_import._container_value_measure
        del probe_import._container_value_measure
        try:
            self.seam_refuses_limit(block_with(nest_list(500)))
        finally:
            probe_import._container_value_measure = original


if __name__ == "__main__":
    unittest.main()
