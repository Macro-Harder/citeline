"""Step 17 round 7 fix seat F7 tests: service, watch, seams.

Pins the register entries charged to F7 in fix round 7:
S17-R7-045, S17-R7-046, S17-R7-047, and S17-R7-052, and
the seam positions the F2, F4, and F6 papers of this
round state for this seat. Every defect test was written
before its cure and run failing for the register stated
reason, except the controls named as controls.
Oracle: the round 7 findings register and disposition.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from citeline import errors, install as install_module
from citeline import journal, registry, service, watch

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = FIXTURES / "w7-page.md"
AUDIT_DATE = "2026-11-14"
PRODUCT = "Acme Ledger"
Q1 = "What is Acme Ledger?"
Q2 = "Best ferry tracker?"
ROUND = "round-1"
ROUND0 = "round-0"


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


def journal_entries(home):
    path = Path(home) / "journal.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def entries_of_kind(home, kind):
    return [entry for entry in journal_entries(home)
            if entry.get("entry_kind") == kind]


def payloads_of_kind(home, kind):
    return [entry.get("payload") or {}
            for entry in entries_of_kind(home, kind)]


def token_of(exc):
    return getattr(exc, "token", None) or getattr(
        exc, "error_value", None)


def temp_file(case, content, name="file.txt"):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    path = root / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def correct_entry(home, entry, **changes):
    corrected = dict(entry.get("payload") or {})
    corrected.update(changes)
    journal.append_entry(
        str(home), "correction",
        {"supersedes_sequence": entry["sequence"],
         "corrected_record": corrected},
        audit_date=AUDIT_DATE)
    return corrected


class SeededBase(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)
        seed(self, self.home)

    def import_one(self):
        answer = temp_file(
            self, "Acme Ledger is a ledger tool.\n", "answer.txt")
        return do_import(self.home, answer)


# ----------------------------------------------------------------
# S17-R7-045: the round version stamps stand judged against
# the counter form the first import stamps, a whole number
# no counter stands below, at both stamp positions.
# ----------------------------------------------------------------

class Test045StampsCounterForm(SeededBase):

    def setUp(self):
        super().setUp()
        self.import_one()
        self.round_entry = entries_of_kind(
            self.home, "round_named")[-1]

    def report(self, home=None):
        return service.probe_report(
            home=str(home or self.home), product=PRODUCT,
            round=ROUND, audit_date=AUDIT_DATE)

    def fresh_home_with_stamp(self, field, value):
        root, home = make_home(self)
        seed(self, home)
        answer = temp_file(
            self, "Acme Ledger is a ledger tool.\n", "answer.txt")
        do_import(home, answer)
        entry = entries_of_kind(home, "round_named")[-1]
        correct_entry(home, entry, **{field: value})
        return home

    def test_negative_registry_stamp_refuses(self):
        correct_entry(
            self.home, self.round_entry,
            registry_version_at_first_import=-7)
        with self.assertRaises(errors.CitelineError) as caught:
            self.report()
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        self.assertIn(
            "registry_version_at_first_import",
            str(caught.exception))

    def test_negative_detector_stamp_refuses(self):
        correct_entry(
            self.home, self.round_entry,
            detector_version_at_first_import=-1)
        with self.assertRaises(errors.CitelineError) as caught:
            self.report()
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        self.assertIn(
            "detector_version_at_first_import",
            str(caught.exception))

    def test_zero_stamp_surfaces_control(self):
        home = self.fresh_home_with_stamp(
            "registry_version_at_first_import", 0)
        report = self.report(home)
        self.assertEqual(
            report["registry_version_at_first_import"], 0)

    def test_large_stamp_surfaces_control(self):
        home = self.fresh_home_with_stamp(
            "registry_version_at_first_import", 10 ** 30)
        report = self.report(home)
        self.assertEqual(
            report["registry_version_at_first_import"], 10 ** 30)


# ----------------------------------------------------------------
# S17-R7-046: the audit form request reader stands validated
# on the audit date, the date defaulted flag, and the
# methods note version beside the fields its validator
# names today, the methods note version standing judged as
# the integer 1 under the Manager ruling.
# ----------------------------------------------------------------

class Test046AuditFieldsValidated(SeededBase):

    def audit_one(self, home=None):
        return service.audit(
            home=str(home or self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)

    def fresh_home_with_swap(self, **changes):
        root, home = make_home(self)
        seed(self, home)
        record = self.audit_one(home)
        entry = entries_of_kind(home, "audit_record")[-1]
        correct_entry(home, entry, **changes)
        return home, record["run_id"]

    def form_request(self, home, run_id):
        return service.audit(home=str(home), run_id=run_id)

    def test_swapped_audit_date_number_refuses(self):
        home, run_id = self.fresh_home_with_swap(audit_date=123)
        with self.assertRaises(errors.CitelineError) as caught:
            self.form_request(home, run_id)
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        self.assertIn("audit_date", str(caught.exception))

    def test_non_iso_audit_date_text_refuses(self):
        home, run_id = self.fresh_home_with_swap(
            audit_date="not a date")
        with self.assertRaises(errors.CitelineError) as caught:
            self.form_request(home, run_id)
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        self.assertIn("audit_date", str(caught.exception))

    def test_swapped_date_defaulted_flag_refuses(self):
        home, run_id = self.fresh_home_with_swap(
            audit_date_defaulted="false")
        with self.assertRaises(errors.CitelineError) as caught:
            self.form_request(home, run_id)
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        self.assertIn(
            "audit_date_defaulted", str(caught.exception))

    def test_swapped_methods_note_version_refuses(self):
        for bad in (["x"], 2, "1", True, 0):
            with self.subTest(bad=repr(bad)):
                home, run_id = self.fresh_home_with_swap(
                    methods_note_version=bad)
                with self.assertRaises(
                        errors.CitelineError) as caught:
                    self.form_request(home, run_id)
                self.assertEqual(
                    token_of(caught.exception), "VALIDATION_FAILED")
                self.assertIn(
                    "methods_note_version", str(caught.exception))

    def test_genuine_record_still_returns_control(self):
        record = self.audit_one()
        standing = self.form_request(self.home, record["run_id"])
        self.assertEqual(standing["audit_date"], AUDIT_DATE)
        self.assertIs(standing["audit_date_defaulted"], False)
        self.assertEqual(standing["methods_note_version"], 1)


# ----------------------------------------------------------------
# S17-R7-047: a second_rounds record on an estate plan
# stands warned in the open, never disregarded in silence.
# ----------------------------------------------------------------

class Test047EstateSecondRoundsWarned(SeededBase):

    def two_round_home(self):
        root, home = make_home(self)
        service.add_product(
            home=str(home), name=PRODUCT,
            canonical_line="Acme Ledger helps teams track citations.",
            domain="acme.example", audit_date=AUDIT_DATE)
        service.set_query_set(
            home=str(home), product=PRODUCT, query_set=[Q1, Q2],
            audit_date=AUDIT_DATE)
        service.name_round(
            home=str(home), product=PRODUCT, round_label=ROUND0,
            importer_declaration="all captured",
            supplier_relation="independent party",
            audit_date=AUDIT_DATE)
        answer = temp_file(
            self, "Acme Ledger is a ledger tool.\n", "answer.txt")
        do_import(home, answer, round=ROUND0)
        service.name_round(
            home=str(home), product=PRODUCT, round_label=ROUND,
            importer_declaration="all captured",
            supplier_relation="independent party",
            audit_date=AUDIT_DATE)
        answer = temp_file(
            self, "Acme Ledger is a ledger tool.\n", "answer.txt")
        do_import(home, answer, round=ROUND)
        return home

    def run_estate_plan(self, home, **plan_fields):
        plan = {"home": str(home), "scope": "estate",
                "audit_date": AUDIT_DATE}
        plan.update(plan_fields)
        plan_file = temp_file(
            self, json.dumps(plan), "plan.json")
        return watch.run_watch(plan_file=str(plan_file))

    def test_estate_record_key_naming_no_product_stands_warned(self):
        home = self.two_round_home()
        result = self.run_estate_plan(
            home, second_rounds={"No Such Product": ROUND0})
        warnings = result.get("plan_warnings") or []
        self.assertTrue(
            any("No Such Product" in warning
                for warning in warnings),
            "no warning names the disregarded key: %r" % (warnings,))

    def test_estate_record_key_naming_a_held_product_stands_warned(self):
        home = self.two_round_home()
        result = self.run_estate_plan(
            home, second_rounds={PRODUCT: ROUND0})
        warnings = result.get("plan_warnings") or []
        self.assertTrue(
            any(PRODUCT in warning and "second_rounds" in warning
                for warning in warnings),
            "no warning names the disregarded key: %r" % (warnings,))

    def test_estate_second_rounds_list_stands_warned(self):
        home = self.two_round_home()
        result = self.run_estate_plan(
            home, second_rounds=[ROUND0])
        warnings = result.get("plan_warnings") or []
        self.assertTrue(
            any("second_rounds" in warning
                for warning in warnings),
            "no warning names the disregarded record: %r"
            % (warnings,))

    def test_estate_plan_without_the_record_warns_nothing_control(self):
        home = self.two_round_home()
        result = self.run_estate_plan(home)
        warnings = result.get("plan_warnings") or []
        self.assertFalse(
            any("second_rounds" in warning
                for warning in warnings))

    def test_plan_warnings_unit_estate_form(self):
        plan = {"home": str(self.home), "scope": "estate",
                "second_rounds": {"No Such Product": ROUND0}}
        warnings = watch._plan_warnings(plan, [])
        self.assertTrue(
            any("No Such Product" in warning
                for warning in warnings))


# ----------------------------------------------------------------
# S17-R7-052: the service product listing stands judged
# against the F2 registry fold judgement as the reference
# reading.
# ----------------------------------------------------------------

class Test052ServiceListingJudgesIdentity(SeededBase):

    def plant_product(self, product_id, name="Ghost"):
        journal.append_entry(
            str(self.home), "product_registered",
            {"product_id": product_id, "name": name,
             "canonical_line": "Ghost line.",
             "domain": "ghost.example"},
            audit_date=AUDIT_DATE)

    def test_integer_identity_refuses_at_the_listing(self):
        self.plant_product(7)
        with self.assertRaises(errors.CitelineError) as caught:
            registry.list_products(str(self.home))
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        with self.assertRaises(errors.CitelineError) as caught:
            service.list_products(home=str(self.home))
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        self.assertIn("product_id", str(caught.exception))

    def test_boolean_identity_refuses_at_the_listing(self):
        self.plant_product(True)
        with self.assertRaises(errors.CitelineError) as caught:
            service.list_products(home=str(self.home))
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        self.assertIn("product_id", str(caught.exception))

    def test_genuine_listing_still_stands_control(self):
        records = service.list_products(home=str(self.home))
        self.assertEqual(
            [record.get("name") for record in records], [PRODUCT])
        self.assertIsInstance(records[0].get("product_id"), str)


# ----------------------------------------------------------------
# F4 seams in service.py: the block size measured on the
# block as it stands in the file (S17-R7-033), container
# values measured through _container_value_measure
# (S17-R7-032), and fences judged on the completed head
# predicate (S17-R7-031).
# ----------------------------------------------------------------

class TestF4SeamsServiceReading(SeededBase):

    def test_block_size_measured_as_the_block_stands_in_the_file(self):
        journal.write_config(
            str(self.home), "front_matter_block_size = 1\n")
        block = "#c\r\n" * 300
        answer = temp_file(
            self, "---\r\n" + block + "---\r\n"
            "Acme Ledger is a ledger tool.\r\n", "answer.txt")
        with self.assertRaises(errors.CitelineError) as caught:
            do_import(self.home, answer)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_container_string_measured_by_its_characters(self):
        journal.write_config(
            str(self.home),
            "front_matter_value_length_per_key = 100\n")
        block = '{"note": ["%s"]}' % ("v" * 99)
        answer = temp_file(
            self, "---\n" + block + "\n---\n"
            "Acme Ledger is a ledger tool.\n", "answer.txt")
        result = do_import(self.home, answer)
        self.assertIsNotNone(result)

    def test_container_string_past_the_limit_still_refuses_control(self):
        journal.write_config(
            str(self.home),
            "front_matter_value_length_per_key = 100\n")
        block = '{"note": ["%s"]}' % ("v" * 101)
        answer = temp_file(
            self, "---\n" + block + "\n---\n"
            "Acme Ledger is a ledger tool.\n", "answer.txt")
        with self.assertRaises(errors.CitelineError) as caught:
            do_import(self.home, answer)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_opening_fence_dressed_with_head_material_reads(self):
        journal.write_config(
            str(self.home), "front_matter_key_count = 1\n")
        answer = temp_file(
            self, "---\u200b\ntitle: T\nother: U\n---\n"
            "Acme Ledger is a ledger tool.\n", "answer.txt")
        with self.assertRaises(errors.CitelineError) as caught:
            do_import(self.home, answer)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_closing_fence_dressed_with_head_material_reads(self):
        journal.write_config(
            str(self.home), "front_matter_key_count = 1\n")
        answer = temp_file(
            self, "---\ntitle: T\nother: U\n---\u200b\n"
            "Acme Ledger is a ledger tool.\n", "answer.txt")
        with self.assertRaises(errors.CitelineError) as caught:
            do_import(self.home, answer)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_key_count_fence_with_head_material_between_dashes(self):
        page = temp_file(
            self, "-\u200b--\ntitle: T\n---\n"
            "Acme Ledger helps teams track citations.\n", "page.md")
        self.assertEqual(service._front_matter_key_count(page), 1)


# ----------------------------------------------------------------
# F2 seams consumed at the service surfaces: the page side
# forms as cured at entries S17-R7-009 to S17-R7-014 and
# the round label forms as cured at entries S17-R7-016 and
# S17-R7-017. Controls: these forms stand landed by seat
# F2 and the service surfaces consume them as they stand.
# ----------------------------------------------------------------

class TestF2SeamsConsumedForms(SeededBase):

    def test_round_label_stored_in_its_nfc_form_control(self):
        service.name_round(
            home=str(self.home), product=PRODUCT,
            round_label="Cafe\u0301",
            importer_declaration="all captured",
            supplier_relation="independent party",
            audit_date=AUDIT_DATE)
        labels = [payload.get("round_label")
                  for payload in payloads_of_kind(
                      self.home, "round_named")]
        self.assertIn("Caf\u00e9", labels)
        self.assertNotIn("Cafe\u0301", labels)

    def test_round_label_with_a_control_character_refuses_control(self):
        with self.assertRaises(errors.CitelineError) as caught:
            service.name_round(
                home=str(self.home), product=PRODUCT,
                round_label="round\nx",
                importer_declaration="all captured",
                supplier_relation="independent party",
                audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")

    def test_page_fence_dressed_at_its_edge_reads_as_a_block_control(self):
        page = temp_file(
            self, "---\u200b\ntitle: T\n---\n"
            "Acme Ledger helps teams track citations.\n", "page.md")
        record = service.audit(
            home=str(self.home), page_file=str(page),
            audit_date=AUDIT_DATE)
        self.assertIsNotNone(record.get("run_id"))


if __name__ == "__main__":
    unittest.main()
