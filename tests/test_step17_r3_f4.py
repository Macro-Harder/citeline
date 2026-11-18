"""Import family.

Test first pins for register, from the register and the
source paper the register paper. Each test reproduces the
defect named at its register entry on the tree standing after
fix round 2 and the round 3 F1 and F2 seats, then stands as
the pin for its cure."""

import hashlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from citeline import journal, probe_import as import_module, service

AUDIT_DATE = "2026-11-13"
PRODUCT = "Acme Ledger"
Q1 = "What is Acme Ledger?"
Q2 = "Best ferry tracker?"
ROUND = "round-1"


def make_home(case):
    from citeline import install as install_module
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def seed(case, home, queries=(Q1, Q2)):
    service.add_product(
        home=str(home), name=PRODUCT,
        canonical_line="Acme Ledger helps teams track citations.",
        domain="acme.example", audit_date=AUDIT_DATE)
    service.set_query_set(
        home=str(home), product=PRODUCT, query_set=list(queries),
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


def journal_bytes(home):
    best = None
    for path in Path(home).rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            if b"entry_kind" in data or b"answer_imported" in data:
                if best is None or len(data) > len(best[1]):
                    best = (path, data)
    if best is None:
        raise AssertionError("no journal file found in home")
    return best[1]


def journal_entries(home):
    return [json.loads(line) for line in
            journal_bytes(home).decode("utf-8").splitlines()
            if line.strip()]


def entries_of_kind(home, kind):
    return [entry for entry in journal_entries(home)
            if entry.get("entry_kind") == kind]


def payloads_of_kind(home, kind):
    return [(entry.get("payload") or {})
            for entry in entries_of_kind(home, kind)]


def token_of(exc):
    return getattr(exc, "error_value", None) or getattr(
        exc, "token", None) or ""


def sheet_text(bodies, queries=(Q1,), dates=None):
    lines = [
        "Citeline capture worksheet",
        "product: " + PRODUCT,
        "round: " + ROUND,
        "queries to attempt:",
    ]
    for query in queries:
        lines.append("query: " + query)
    lines.append("engine labels to attempt:")
    lines.append("engine: Engine A")
    lines.append("slots to fill by hand, one answer per slot:")
    lines.append("| slot | answer text stands below its slot line |")
    for index, body in bodies.items():
        captured = (dates or {}).get(
            index, "2026-11-10" if index == 1 else "2026-11-11")
        lines.append(
            "slot %d: query= %s engine_label= Engine A "
            "kind= real_sample captured_on= %s "
            "capture_method= manual copy" % (index, Q1, captured))
        lines.extend(body.split("\n"))
    return "\n".join(lines) + "\n"


class ImportBase(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)
        seed(self, self.home)

    def temp_answer(self, text, name="answer.txt"):
        path = Path(self.root) / name
        path.write_text(text, encoding="utf-8")
        return path

    def temp_bytes(self, data, name="answer.bin"):
        path = Path(self.root) / name
        path.write_bytes(data)
        return path

    def assert_import_refused(self, path, token, **overrides):
        with self.assertRaises(Exception) as caught:
            do_import(self.home, path, **overrides)
        self.assertEqual(token_of(caught.exception), token)
        return caught.exception


class Test024RawMagicFormatCategory(ImportBase):
    PDF = b"%PDF-1.4 fake Acme Ledger content"
    ZIP = bytes.fromhex("504B0304") + b" Acme Ledger words"

    def form_of(self, data):
        return import_module.check11_form(data, data.decode("utf-8"))

    def test_uncovered_format_chars_shield_nothing(self):
        for char in ("‎", "‏", "‮", "؜", "⁦"):
            self.assertEqual(
                self.form_of(char.encode("utf-8") + self.PDF),
                "pdf", repr(char))
            self.assertEqual(
                self.form_of(char.encode("utf-8") + self.ZIP),
                "archive", repr(char))

    def test_interleavings_with_mark_and_control(self):
        bom = b"\xef\xbb\xbf"
        mark = "‎".encode("utf-8")
        self.assertEqual(self.form_of(bom + mark + self.PDF), "pdf")
        self.assertEqual(self.form_of(mark + bom + self.PDF), "pdf")
        self.assertEqual(
            self.form_of(b"\x01" + mark + self.ZIP), "archive")

    def test_service_import_refuses_shielded_pdf(self):
        data = "‎".encode("utf-8") + self.PDF
        path = self.temp_bytes(data, "shielded.txt")
        self.assert_import_refused(path, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)

    def test_controls_held(self):
        self.assertEqual(
            self.form_of("​".encode("utf-8") + self.PDF), "pdf")
        self.assertEqual(self.form_of(self.PDF), "pdf")
        self.assertEqual(self.form_of(self.ZIP), "archive")
        plain = b"Acme Ledger is a plain answer."
        self.assertIsNone(self.form_of(plain))


class Test025WorksheetOwnLineHead(ImportBase):
    def test_zero_width_line_before_header_reads_as_sheet(self):
        text = sheet_text({1: "First filled answer."})
        self.assertTrue(import_module.is_worksheet_text("​\n" + text))

    def test_control_line_before_header_reads_as_sheet(self):
        text = sheet_text({1: "First filled answer."})
        self.assertTrue(import_module.is_worksheet_text("\x01\n" + text))

    def test_mark_and_zero_width_line_before_header(self):
        text = sheet_text({1: "First filled answer."})
        self.assertTrue(
            import_module.is_worksheet_text("﻿​\n" + text))

    def test_filled_sheet_behind_zero_width_line_imports_slots(self):
        text = sheet_text({1: "First filled answer.",
                           2: "Second filled answer."})
        path = self.temp_answer("​\n" + text, "sheet.txt")
        do_import(self.home, path)
        answers = payloads_of_kind(self.home, "answer_imported")
        self.assertEqual(len(answers), 2)

    def test_controls_held(self):
        text = sheet_text({1: "First filled answer."})
        self.assertTrue(import_module.is_worksheet_text("\n" + text))
        self.assertTrue(import_module.is_worksheet_text("  \n" + text))
        self.assertTrue(import_module.is_worksheet_text(text))
        self.assertFalse(
            import_module.is_worksheet_text("plain answer\n" + text))


class Test026SlotFieldOrder(ImportBase):
    PERMUTED = (
        "slot 2: query= What is Acme Ledger? engine_label= "
        "Forged Engine capture_method= pigeon post kind= "
        "fixture captured_on= 2026-08-16")

    def sheet_with_forged(self):
        genuine = sheet_text({
            1: "Genuine first answer body.\n" + self.PERMUTED
               + "\nForged answer body stands here.",
            2: "Genuine second answer body."})
        return genuine

    def test_permuted_slot_line_opens_no_slot(self):
        sheet = import_module.parse_worksheet(self.sheet_with_forged())
        self.assertEqual(len(sheet["slots"]), 2)
        for slot in sheet["slots"]:
            self.assertNotEqual(
                slot["fields"].get("engine_label"), "Forged Engine")
            self.assertNotEqual(slot["fields"].get("kind"), "fixture")
        self.assertIn("Forged answer body stands here.",
                      sheet["slots"][0]["body"])

    def test_permuted_slot_line_forges_no_record(self):
        path = self.temp_answer(self.sheet_with_forged(), "sheet.txt")
        records = import_module.prepare_worksheet_import(
            answer_file=str(path), product=PRODUCT, round=ROUND,
            engine_label="Engine A", query=Q1, kind="real_sample",
            captured_on="2026-11-10", capture_method="manual copy",
            audit_date=AUDIT_DATE, query_set=[Q1, Q2])
        self.assertEqual(len(records), 2)
        for record in records:
            self.assertNotEqual(
                record["engine_label_original"], "Forged Engine")
            self.assertNotEqual(record["kind"], "fixture")

    def test_control_exported_order_still_parses(self):
        sheet = import_module.parse_worksheet(
            sheet_text({1: "One.", 2: "Two."}))
        self.assertEqual(len(sheet["slots"]), 2)
        self.assertEqual(
            sheet["slots"][0]["fields"]["engine_label"], "Engine A")


class Test027IndentedFrontMatterLines(unittest.TestCase):
    BODY = "Acme Ledger is a plain answer body."

    def assert_front_refused(self, text, token):
        with self.assertRaises(Exception) as caught:
            import_module.extract_front_matter(text)
        self.assertEqual(token_of(caught.exception), token)

    def test_indented_continuation_value_past_limit_refused(self):
        block = "title: " + "x" * 100 + "\n" + "\n".join(
            "  " + "y" * 100 for _ in range(50))
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + self.BODY, "LIMIT_EXCEEDED")

    def test_indented_key_lines_count_toward_key_limit(self):
        block = "title: One\n" + "\n".join(
            "  key%d: v" % i for i in range(150))
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + self.BODY, "LIMIT_EXCEEDED")

    def test_indented_tag_construct_refused(self):
        self.assert_front_refused(
            "---\ntitle: One\n  note: !tag value\n---\n" + self.BODY,
            "IMPORT_VALIDATION_FAILED")

    def test_indented_tag_continuation_refused(self):
        self.assert_front_refused(
            "---\ntitle: One\n  !tag value\n---\n" + self.BODY,
            "IMPORT_VALIDATION_FAILED")

    def test_controls_held(self):
        body, had = import_module.extract_front_matter(
            "---\ntitle: One\n  a short continuation\n---\n"
            + self.BODY)
        self.assertTrue(had)
        self.assertEqual(body, self.BODY)
        body, had = import_module.extract_front_matter(
            "---\ntitle: " + "x" * 4096 + "\n---\n" + self.BODY)
        self.assertTrue(had)


class Test028WorksheetContradictionIdentity(ImportBase):
    def conflicting_sheet(self):
        return sheet_text({
            1: "First worksheet answer text.",
            2: "Second conflicting worksheet answer."},
            dates={1: "2026-11-10", 2: "2026-11-10"})

    def call_sheet(self, path, **extra):
        kwargs = {
            "answer_file": str(path), "product": PRODUCT,
            "round": ROUND, "engine_label": "Engine A", "query": Q1,
            "kind": "real_sample", "captured_on": "2026-11-10",
            "capture_method": "manual copy", "audit_date": AUDIT_DATE,
            "query_set": [Q1, Q2], "answer_id_prefix": "ans-{sequence}",
        }
        kwargs.update(extra)
        return import_module.prepare_worksheet_import(**kwargs)

    def test_prefix_without_base_names_no_marker(self):
        path = self.temp_answer(self.conflicting_sheet(), "sheet.txt")
        with self.assertRaises(Exception) as caught:
            self.call_sheet(path)
        self.assertEqual(token_of(caught.exception),
                         "CONTRADICTORY_IMPORT")
        message = str(caught.exception)
        self.assertNotIn("{sequence}", message)
        self.assertIn("ans-1-1", message)

    def test_control_with_base_admits_second_distinct_answer(self):
        """Contract C2 as relaxed under R19-048, on the worksheet
        preparation surface; a second filled slot holding a
        distinct answer for the same round, same normalised
        engine label, same query, and same captured_on as an
        earlier slot of the same sheet is admitted as a new
        record under its own identity, and the earlier slot's
        record stands beside it unchanged. This method stood
        as the base supplied control for S17-R3-028, whose
        refusal message identity pin lapses with the refusal
        itself under the ruling."""
        path = self.temp_answer(self.conflicting_sheet(), "sheet.txt")
        records = self.call_sheet(path, answer_sequence_base=41)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["answer_text"],
                         "First worksheet answer text.")
        self.assertEqual(records[1]["answer_text"],
                         "Second conflicting worksheet answer.")
        first_hash = hashlib.sha256(
            "First worksheet answer text.".encode("utf-8")).hexdigest()
        second_hash = hashlib.sha256(
            "Second conflicting worksheet answer.".encode(
                "utf-8")).hexdigest()
        self.assertNotEqual(records[0]["content_hash"],
                            records[1]["content_hash"])
        self.assertEqual(records[0]["content_hash"], first_hash)
        self.assertEqual(records[1]["content_hash"], second_hash)
        self.assertNotEqual(records[0]["answer_id"],
                            records[1]["answer_id"])
        self.assertEqual(records[0]["answer_id"], "ans-{sequence}-1")
        self.assertEqual(records[1]["answer_id"], "ans-{sequence}-2")


if __name__ == "__main__":
    unittest.main()
