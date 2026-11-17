"""Service, watch, seams.

Seat F7 carries one entry TO FIX in this round, Medium: the
audit preflight key count counter in citeline/service.py,
_front_matter_key_count, parses the JSON front matter block
of a page inside a try that catches ValueError alone, so a
block nesting past the parser standing escapes service.audit
as a raw RecursionError with no token and no failure record,
on a road the cure at did not reach. The defect pins below
stand on that entry: the counter parse stands judged in the
recorded vocabulary, catching RecursionError beside
ValueError and converting it to a refusal with
LIMIT_EXCEEDED, so no nesting form escapes the audit route as
a raw RecursionError at any depth, in list shape and in
record shape alike, at the counter directly, at the audit
preflight, and through service.audit whole, with no
failure record appended for the governed refusal of the
route (restated for Step 19 register item R19-041: a cap
refusal stores nothing on every route), while the forms at and below the depth limit stand as
they stood and the cure at stands whole at its seam. The flip
depths stand stated honestly per runtime, as the round 15
papers measure them: on this machine, Python 3.12.3, the
counter returns its count at list depth 8000 and raises a raw
RecursionError at list depths 10000 and past, the flip
standing between 8000 and 10000; on the bp runtime, Python
3.14.4, the counter returns its count at list depth 50000 and
raises a raw RecursionError at list depths 60000 and past,
the flip standing between 50000 and 60000, and in record
shape the counter raises a raw RecursionError at depth 100000
on that runtime. The discriminating pins therefore stand at
depth 100000 in both shapes, a depth past the flip on both
runtimes, beside a list pin at depth 20000 that stands
discriminating on this machine and stands refused with
LIMIT_EXCEEDED on the bp runtime on the cured tree through
the extraction depth judgement, as the papers record for the
uncured tree at that depth. Beside the defect pins, this file
carries the standing forms of this family judged first hand:
the counter returning its count on shallow JSON forms and on
the line form, a page nesting at depth 99 standing whole at
the audit route, the seam cure at standing whole in its
standing form, and the three container measures agreeing on
the worked forms of. Oracle: the round 15 disposition,
Section 3 seat F7 and ruling (d), the round 15 register, and
the round 15 service, red, and yellow attack papers, filings,
and R15-Y-06.

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
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
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


def journal_entries(home):
    path = Path(home) / "journal.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def failure_record_count(home):
    return len([entry for entry in journal_entries(home)
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

    def audit_refuses_limit(self, page):
        with self.assertRaises(errors.CitelineError) as caught:
            self.audit(page)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")


# ----------------------------------------------------------------
# Entry at the counter directly: a block nesting past the parser
# standing on either runtime refuses with LIMIT_EXCEEDED at the
# counter, in list shape and in record shape alike, and no form
# stands returned as a count and no raw RecursionError stands
# raised.
# ----------------------------------------------------------------

class TestCounterDirectDeep(unittest.TestCase):

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

    def test_counter_list_past_both_flips_refuses_limit(self):
        for depth in (60000, 100000):
            with self.subTest(depth=depth):
                self.counter_refuses_limit(
                    block_with(nest_list(depth)))

    def test_counter_record_past_both_flips_refuses_limit(self):
        self.counter_refuses_limit(
            block_with(nest_record(100000)))

    def test_counter_shallow_list_returns_its_count(self):
        for depth in (50, 99):
            with self.subTest(depth=depth):
                self.assertEqual(
                    self.counter(block_with(nest_list(depth))), 1)

    def test_counter_at_depth_99_returns_its_count(self):
        self.assertEqual(
            self.counter(block_with(nest_list(99))), 1)

    def test_counter_plain_json_block_counts_its_keys(self):
        self.assertEqual(self.counter('{"a": 1, "b": 2}'), 2)

    def test_counter_line_form_block_counts_its_keys(self):
        root = Path(self.enterContext(
            tempfile.TemporaryDirectory()))
        page = root / "page.md"
        page.write_text(
            "---\ntitle: Hello\nauthor: A Person\n---\n"
            "Body text.\n", encoding="utf-8")
        self.assertEqual(
            service._front_matter_key_count(str(page)), 2)


# ----------------------------------------------------------------
# Entry at the audit preflight: the counter stands called from
# _audit_preflight_limits ahead of any extraction, and a past flip
# form refuses there with LIMIT_EXCEEDED in both shapes.
# ----------------------------------------------------------------

class TestPreflightDeep(SeededBase):

    def preflight(self, page):
        start_limits = {"by_limit": {
            "page_file_size": {"value": 1},
            "front_matter_key_count": {"value": 100}}}
        return service._audit_preflight_limits(
            str(self.home), str(page), start_limits)

    def preflight_refuses_limit(self, block):
        page = self.page(block)
        with self.assertRaises(errors.CitelineError) as caught:
            self.preflight(page)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_preflight_list_past_flip_refuses_limit(self):
        self.preflight_refuses_limit(
            block_with(nest_list(100000)))

    def test_preflight_record_past_flip_refuses_limit(self):
        self.preflight_refuses_limit(
            block_with(nest_record(100000)))


# ----------------------------------------------------------------
# Entry through service.audit whole: a past flip form refuses with
# LIMIT_EXCEEDED and appends no failure record, in list shape
# and in record shape alike, and the standing forms of the
# route hold whole. Restated for Step 19 register item
# R19-041: a cap refusal stores nothing on every route, so
# the record count stands unchanged beside the refusal.
# ----------------------------------------------------------------

class TestAuditRouteDeep(SeededBase):

    def test_audit_list_past_flip_refuses_with_failure_record(self):
        # Restated for Step 19 register item R19-041: a cap
        # refusal stores nothing on every route, under the
        # cure in citeline/service.py where
        # _append_failure_record returns without storing
        # on a LIMIT_EXCEEDED refusal. The refusal and its
        # token stand at full strength; the record limb
        # now pins that the count stands unchanged.
        page = self.page(block_with(nest_list(100000)))
        before = failure_record_count(self.home)
        self.audit_refuses_limit(page)
        self.assertEqual(
            failure_record_count(self.home), before)

    def test_audit_record_past_flip_refuses_with_failure_record(self):
        # Restated for Step 19 register item R19-041: a cap
        # refusal stores nothing on every route, under the
        # cure in citeline/service.py where
        # _append_failure_record returns without storing
        # on a LIMIT_EXCEEDED refusal. The refusal and its
        # token stand at full strength; the record limb
        # now pins that the count stands unchanged.
        page = self.page(block_with(nest_record(100000)))
        before = failure_record_count(self.home)
        self.audit_refuses_limit(page)
        self.assertEqual(
            failure_record_count(self.home), before)

    def test_audit_list_at_20000_refuses_limit(self):
        self.audit_refuses_limit(
            self.page(block_with(nest_list(20000))))

    def test_audit_list_at_1000_refuses_limit(self):
        self.audit_refuses_limit(
            self.page(block_with(nest_list(1000))))

    def test_audit_at_depth_99_runs_whole(self):
        result = self.audit(self.page(block_with(nest_list(99))))
        self.assertIsInstance(result, dict)

    def test_audit_plain_page_runs_whole(self):
        result = self.audit(self.page('{"note": "plain"}'))
        self.assertIsInstance(result, dict)


# ----------------------------------------------------------------
# The standing forms this cure holds: the seam cure at in its
# standing form, and the container measures of agreeing on their
# worked forms.
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


if __name__ == "__main__":
    unittest.main()
