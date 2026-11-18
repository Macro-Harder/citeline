"""Service, watch, seams.

The repair carries no repair entry. This file
pins the sustained verdict standings of the repair in their
charged forms, judged on the current tree: the cure at
standing sustained whole, the audit preflight counter depth
judgement in citeline/service.py judging a front matter block
on its bracket nesting depth ahead of its parse, in list
shape and in record shape alike, at the limit of 100 and past
it, counting brackets standing outside string literals alone,
with no raw RecursionError standing raised at any depth and
no failure record standing appended for a refusal on
the audit route (restated for The settled rule: a cap refusal stores nothing on every route); and the container seam verdict at standing
sustained whole in its standing form, the three container
measures agreeing on their worked forms. The seam cure at
stands pinned in its standing form beside them. Oracle:
Section 3 of the settled disposition, the repair paragraph,
with the settled rule, point 4, the F7 paragraph of the fix charge
section in the settled record, and the repair F7 paper
in the register.

Copyright: J.P. Picard aka Macro-Harder."""

import json
import tempfile
import unittest
from pathlib import Path

from citeline import acquisition, errors
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

    def audit_refuses_limit_no_record(self, page):
        # Restated for the settled rule: a cap
        # refusal stores nothing on every route, under the
        # cure in citeline/service.py where
        # _append_failure_record returns without storing
        # on a LIMIT_EXCEEDED refusal. The refusal and its
        # token stand at full strength; the record limb
        # now pins that the count stands unchanged.
        before = failure_record_count(self.home)
        with self.assertRaises(errors.CitelineError) as caught:
            self.audit(page)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")
        self.assertEqual(
            failure_record_count(self.home), before)


# ----------------------------------------------------------------
# The depth helper of the cure at: the bracket count stands string
# aware, escapes inside a string standing skipped, and real
# nesting standing counted whole in list shape and in record
# shape.
# ----------------------------------------------------------------

class TestDepthHelperStringAware(unittest.TestCase):

    def depth(self, block):
        return service._front_matter_block_depth(block)

    def test_plain_block_depth_is_one(self):
        self.assertEqual(self.depth('{"note": "x"}'), 1)

    def test_real_nesting_counts_in_both_shapes(self):
        self.assertEqual(self.depth(block_with(nest_list(5))), 6)
        self.assertEqual(self.depth(block_with(nest_record(5))), 6)

    def test_brackets_inside_a_string_do_not_count(self):
        block = '{"note": "' + "[" * 200 + "{" * 200 + '"}'
        self.assertEqual(self.depth(block), 1)

    def test_escaped_quote_keeps_following_brackets_in_string(self):
        block = '{"note": "a \\" ' + "[" * 150 + '"}'
        self.assertEqual(self.depth(block), 1)

    def test_escaped_backslash_lets_the_quote_close_the_string(self):
        block = '{"note": "a\\\\", "k": [1]}'
        self.assertEqual(self.depth(block), 2)


# ----------------------------------------------------------------
# Entry at the counter directly, at and past the limit of 100: a
# list nesting of depth 99 stands at bracket depth 100 and returns
# its count, a list nesting of depth 100 stands at bracket depth
# 101 and refuses, and the record shape stands the same, at the
# boundary and past the parser flip of either runtime alike, with
# no raw RecursionError.
# ----------------------------------------------------------------

class TestCounterBoundary(unittest.TestCase):

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

    def test_counter_list_at_the_limit_returns_its_count(self):
        self.assertEqual(
            self.counter(block_with(nest_list(99))), 1)

    def test_counter_list_past_the_limit_refuses(self):
        for depth in (100, 101):
            with self.subTest(depth=depth):
                self.counter_refuses_limit(
                    block_with(nest_list(depth)))

    def test_counter_record_at_the_limit_returns_its_count(self):
        self.assertEqual(
            self.counter(block_with(nest_record(99))), 1)

    def test_counter_record_past_the_limit_refuses(self):
        for depth in (100, 101):
            with self.subTest(depth=depth):
                self.counter_refuses_limit(
                    block_with(nest_record(depth)))

    def test_counter_list_past_the_parser_flip_refuses(self):
        self.counter_refuses_limit(block_with(nest_list(100000)))

    def test_counter_record_past_the_parser_flip_refuses(self):
        self.counter_refuses_limit(
            block_with(nest_record(100000)))

    def test_counter_deep_brackets_inside_a_string_return_count(self):
        block = '{"note": "' + "[" * 500 + '", "other": 1}'
        self.assertEqual(self.counter(block), 2)

    def test_counter_escaped_quote_form_returns_its_count(self):
        block = '{"note": "a \\" ' + "[" * 500 + '"}'
        self.assertEqual(self.counter(block), 1)

    def test_counter_plain_json_block_counts_its_keys(self):
        self.assertEqual(self.counter('{"a": 1, "b": 2}'), 2)


# ----------------------------------------------------------------
# Entry at the audit preflight: the past limit forms refuse in
# both shapes, and the form at the limit stands passed by the
# preflight.
# ----------------------------------------------------------------

class TestPreflightBoundary(SeededBase):

    def preflight(self, page):
        start_limits = {"by_limit": {
            "page_file_size": {"value": 1},
            "front_matter_key_count": {"value": 100}}}
        return service._audit_preflight_limits(
            str(self.home), str(page), start_limits)

    def test_preflight_list_past_the_limit_refuses(self):
        page = self.page(block_with(nest_list(100)))
        with self.assertRaises(errors.CitelineError) as caught:
            self.preflight(page)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_preflight_record_past_the_limit_refuses(self):
        page = self.page(block_with(nest_record(100)))
        with self.assertRaises(errors.CitelineError) as caught:
            self.preflight(page)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_preflight_list_at_the_limit_passes(self):
        page = self.page(block_with(nest_list(99)))
        self.assertIsNone(self.preflight(page))


# ----------------------------------------------------------------
# Entry through service.audit whole: each refusal appends no
# failure record, at the boundary depth and past the parser
# flip alike, in list shape and in record shape, and the form at
# the limit runs whole. Restated for The settled the settled rule
# The settled rule: a cap refusal stores nothing on every route, so
# the record count stands unchanged beside the refusal.
# ----------------------------------------------------------------

class TestAuditRouteBoundary(SeededBase):

    def test_audit_list_past_the_limit_one_failure_record(self):
        self.audit_refuses_limit_no_record(
            self.page(block_with(nest_list(100))))

    def test_audit_record_past_the_limit_one_failure_record(self):
        self.audit_refuses_limit_no_record(
            self.page(block_with(nest_record(100))))

    def test_audit_list_past_the_flip_one_failure_record(self):
        self.audit_refuses_limit_no_record(
            self.page(block_with(nest_list(100000))))

    def test_audit_record_past_the_flip_one_failure_record(self):
        self.audit_refuses_limit_no_record(
            self.page(block_with(nest_record(100000))))

    def test_audit_list_at_the_limit_runs_whole(self):
        result = self.audit(self.page(block_with(nest_list(99))))
        self.assertIsInstance(result, dict)


# ----------------------------------------------------------------
# The standing forms of the family: the seam cure at in its
# standing form, and the container seam verdict, the three
# measures agreeing alike on their worked forms.
# ----------------------------------------------------------------

class TestStandingFormsHold(SeededBase):

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

    def test_seam_cure_at_entry_r14_004_stands_whole(self):
        self.assertIsNone(self.seam(block_with(nest_list(99))))
        with self.assertRaises(errors.CitelineError) as caught:
            self.seam(block_with(nest_list(100)))
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_container_measures_agree_on_the_worked_forms(self):
        def measures(value):
            return (
                acquisition._fm_container_value_measure(value),
                probe_import._container_value_measure(value),
                service._service_container_value_measure(value))
        self.assertEqual(
            measures({"m": "x" * 4096}), (4097, 4097, 4097))
        self.assertEqual(
            measures({"k" * 4090: "x" * 10}), (4100, 4100, 4100))
        self.assertEqual(
            measures([{"m": "x" * 4096}]), (4097, 4097, 4097))

    def test_container_measures_agree_on_further_forms(self):
        def measures(value):
            return (
                acquisition._fm_container_value_measure(value),
                probe_import._container_value_measure(value),
                service._service_container_value_measure(value))
        for value in ({"a": [1, 2, {"b": "xyz"}]},
                      ["plain", {"k": "v"}, 7],
                      {"outer": {"inner": "text"}}):
            with self.subTest(value=repr(value)[:40]):
                first, second, third = measures(value)
                self.assertEqual(first, second)
                self.assertEqual(second, third)


if __name__ == "__main__":
    unittest.main()
