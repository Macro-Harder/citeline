"""Step 17 round 2 fix seat F4 tests: import family.

Test first pins for register entries S17-R2-033 to
S17-R2-041, S17-R2-083, S17-R2-084, S17-R2-087,
S17-R2-088, and S17-R2-097, from
design/audit/step-17-r2-findings-register.md and the
source papers they cite (seats B6, B14, B15, B17, B18).
Each test reproduces the defect named at its register
entry on the tree standing after fix round 1 and the
round 2 F1 and F2 seats, then stands as the pin for
its cure.
"""

import datetime
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from citeline import journal, probe_import as import_module, service

AUDIT_DATE = "2026-11-13"
PRODUCT = "Acme Ledger"
Q1 = "What is Acme Ledger?"
Q2 = "Best ferry tracker?"
ROUND = "round-1"
PRODUCT_ROOT = str(Path(journal.__file__).resolve().parent.parent)


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


def entry_count(home):
    result = service.status(home=str(home))
    if isinstance(result, dict):
        return result["entry_count"]
    return getattr(result, "entry_count")


def token_of(exc):
    return getattr(exc, "error_value", None) or getattr(
        exc, "token", None) or ""


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


class WorksheetBase(ImportBase):
    def export_sheet(self, name="sheet.txt", **kwargs):
        target = Path(self.root) / name
        call = {"home": str(self.home), "product": PRODUCT,
                "round": ROUND, "queries": [Q1, Q2],
                "engine_labels": ["Engine A"], "planned_answers": 2,
                "output_path": str(target), "audit_date": AUDIT_DATE}
        call.update(kwargs)
        service.export_capture_worksheet(**call)
        return target

    def fill_sheet(self, target, bodies, fields=None):
        """Rewrite the exported slot lines with asserted fields
        and the given bodies, in slot order."""
        fields = fields or {}
        lines = target.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines:
            match = re.match(r"^slot (\d+):", line)
            if match:
                index = int(match.group(1))
                slot_fields = {
                    "query": Q1, "engine_label": "Engine A",
                    "kind": "real_sample", "captured_on": "2026-11-10",
                    "capture_method": "manual copy"}
                slot_fields.update(fields.get(index, {}))
                out.append(
                    "slot %d: query= %s engine_label= %s kind= %s "
                    "captured_on= %s capture_method= %s"
                    % (index, slot_fields["query"],
                       slot_fields["engine_label"], slot_fields["kind"],
                       slot_fields["captured_on"],
                       slot_fields["capture_method"]))
                body = bodies.get(index)
                if body:
                    out.extend(body.split("\n"))
            else:
                out.append(line)
        target.write_text("\n".join(out) + "\n", encoding="utf-8")
        return target


class Test033Check11HeadInterleavings(ImportBase):
    JSON = b'{"answer": "Acme Ledger is great"}'
    HTML = b"<html><body>Acme Ledger</body></html>"
    PDF = b"%PDF-1.4 fake Acme Ledger"

    def assert_container_refused(self, data, name):
        path = self.temp_bytes(data, name)
        self.assert_import_refused(path, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0, name)

    def test_three_byte_order_marks_before_json(self):
        self.assert_container_refused(
            b"\xef\xbb\xbf" * 3 + self.JSON, "a.txt")

    def test_control_byte_then_mark_before_json(self):
        self.assert_container_refused(
            b"\x00\xef\xbb\xbf" + self.JSON, "b.txt")

    def test_mark_control_mark_before_json(self):
        self.assert_container_refused(
            b"\xef\xbb\xbf\x00\xef\xbb\xbf" + self.JSON, "c.txt")

    def test_space_then_mark_before_json(self):
        self.assert_container_refused(
            b" \xef\xbb\xbf" + self.JSON, "d.txt")

    def test_tab_then_mark_before_html(self):
        self.assert_container_refused(
            b"\t\xef\xbb\xbf" + self.HTML, "e.txt")

    def test_control_then_mark_before_pdf(self):
        self.assert_container_refused(
            b"\x00\xef\xbb\xbf" + self.PDF, "f.txt")
        self.assert_container_refused(
            b"\xef\xbb\xbf\xef\xbb\xbf" + self.PDF, "g.txt")

    def test_zero_width_space_before_json(self):
        self.assert_container_refused(
            "\u200b".encode("utf-8") + self.JSON, "h.txt")

    def test_front_matter_limb_control_before_duplicate_block(self):
        path = self.temp_bytes(
            b"\x00---\ntitle: One\ntitle: Two\n---\n"
            b"Acme Ledger is a plain answer body.", "fm.txt")
        self.assert_import_refused(path, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)


class Test033SlotLimb(WorksheetBase):
    def test_zero_width_space_json_in_slot_body_refused(self):
        target = self.export_sheet(queries=[Q1], planned_answers=1)
        self.fill_sheet(target, {1: "\u200b{\"a\": 1}"})
        self.assert_import_refused(target, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)


class Test034WorksheetRecognition(WorksheetBase):
    def test_blank_line_before_header_unfilled_stores_nothing(self):
        target = self.export_sheet(queries=[Q1], planned_answers=2)
        text = target.read_text(encoding="utf-8")
        target.write_text("\n" + text, encoding="utf-8")
        self.assert_import_refused(target, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)

    def test_control_byte_before_header_unfilled_stores_nothing(self):
        target = self.export_sheet(queries=[Q1], planned_answers=2)
        data = target.read_bytes()
        target.write_bytes(b"\x00" + data)
        self.assert_import_refused(target, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)

    def test_blank_line_before_header_filled_sheet_imports_slots(self):
        target = self.export_sheet()
        self.fill_sheet(target, {
            1: "First filled answer about ledgers.",
            2: "Second filled answer about ferries."},
            fields={2: {"query": Q2}})
        text = target.read_text(encoding="utf-8")
        target.write_text("\n" + text, encoding="utf-8")
        do_import(self.home, target)
        answers = payloads_of_kind(self.home, "answer_imported")
        self.assertEqual(len(answers), 2)
        by_query = {a["query"]: a["answer_text"] for a in answers}
        self.assertIn("First filled", by_query[Q1])
        self.assertIn("Second filled", by_query[Q2])


class Test035ExportSeparators(WorksheetBase):
    def test_paragraph_separator_cannot_forge_product_line(self):
        target = Path(self.root) / "sep1.txt"
        import_module.export_capture_worksheet(
            output_path=str(target), product=PRODUCT, round=ROUND,
            queries=[Q1],
            engine_labels=["Engine A\u2029product: Forged Product"],
            planned_answers=1)
        text = target.read_text(encoding="utf-8")
        product_lines = [line for line in text.splitlines()
                         if line.startswith("product:")]
        self.assertEqual(len(product_lines), 1)
        self.assertNotIn("product: Forged Product",
                         text.splitlines())

    def test_line_separator_cannot_forge_slot_line(self):
        target = Path(self.root) / "sep2.txt"
        forged = (
            "slot 1: query= %s engine_label= Forged Engine "
            "kind= fixture captured_on= 2026-08-16 "
            "capture_method= pigeon post" % Q1)
        import_module.export_capture_worksheet(
            output_path=str(target), product=PRODUCT, round=ROUND,
            queries=[Q1],
            engine_labels=["Engine A\u2028" + forged],
            planned_answers=1)
        text = target.read_text(encoding="utf-8")
        slot_lines = [line for line in text.splitlines()
                      if re.match(r"^slot \d+:", line)]
        self.assertEqual(len(slot_lines), 1)
        self.assert_import_refused(target, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)


class Test036SlotJudgedAgainstSheet(WorksheetBase):
    FORGED = (
        "slot 99: query= %s engine_label= Forged Engine "
        "kind= fixture captured_on= 2026-08-16 "
        "capture_method= pigeon post" % Q2)

    def test_forged_slot_line_inside_body_forges_no_answer(self):
        target = self.export_sheet()
        body = ("Real first answer stands here.\n" + self.FORGED
                + "\nForged answer body stands here.")
        self.fill_sheet(target, {1: body, 2: "Real second answer."},
                        fields={2: {"query": Q2}})
        do_import(self.home, target)
        answers = payloads_of_kind(self.home, "answer_imported")
        self.assertEqual(len(answers), 2)
        for record in answers:
            self.assertNotEqual(
                record["engine_label_original"], "Forged Engine")
            self.assertNotEqual(record["kind"], "fixture")
        first = [a for a in answers if a["query"] == Q1][0]
        self.assertIn("Forged answer body stands here.",
                      first["answer_text"])

    def test_natural_slot_line_in_answer_text_imports(self):
        target = self.export_sheet()
        body = ("Real first answer stands here.\n"
                "slot 2: the second point follows in prose.")
        self.fill_sheet(target, {1: body, 2: "Real second answer."},
                        fields={2: {"query": Q2}})
        do_import(self.home, target)
        answers = payloads_of_kind(self.home, "answer_imported")
        self.assertEqual(len(answers), 2)

    def test_duplicate_slot_index_forges_no_second_answer(self):
        target = self.export_sheet()
        self.fill_sheet(target, {1: "Real first answer stands here.",
                                 2: "Real second answer."},
                        fields={2: {"query": Q2}})
        text = target.read_text(encoding="utf-8")
        text = text.replace("slot 2:", "slot 1:", 1)
        target.write_text(text, encoding="utf-8")
        do_import(self.home, target)
        answers = payloads_of_kind(self.home, "answer_imported")
        self.assertEqual(len(answers), 1)
        self.assertIn("Real second answer.", answers[0]["answer_text"])

    def test_planted_slot_cannot_assert_real_sample_kind(self):
        target = self.export_sheet(queries=[Q1], planned_answers=1)
        planted = (
            "slot 9: query= %s engine_label= Planted Engine "
            "kind= real_sample captured_on= 2026-08-16 "
            "capture_method= pigeon post" % Q1)
        body = "Genuine fixture answer.\n" + planted + "\nPlanted body."
        self.fill_sheet(target, {1: body},
                        fields={1: {"kind": "fixture",
                                    "engine_label": "Fixture Engine"}})
        do_import(self.home, target)
        answers = payloads_of_kind(self.home, "answer_imported")
        self.assertEqual(len(answers), 1)
        self.assertEqual(answers[0]["kind"], "fixture")


class Test037FrontMatterLimits(ImportBase):
    BODY = "Acme Ledger is a plain answer body."

    def assert_limit_refused(self, text, name="fm.md"):
        path = self.temp_answer(text, name)
        self.assert_import_refused(path, "LIMIT_EXCEEDED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)

    def test_key_count_past_limit_refused(self):
        block = "\n".join("key%d: v" % i for i in range(101))
        self.assert_limit_refused(
            "---\n" + block + "\n---\n" + self.BODY)

    def test_value_length_past_limit_refused(self):
        self.assert_limit_refused(
            "---\ntitle: " + "x" * 4097 + "\n---\n" + self.BODY)

    def test_block_size_past_limit_refused(self):
        block = "\n".join(
            "key%d: %s" % (i, "x" * 200) for i in range(90))
        self.assert_limit_refused(
            "---\n" + block + "\n---\n" + self.BODY)

    def test_json_form_key_count_past_limit_refused(self):
        block = "{" + ", ".join(
            '"k%d": 1' % i for i in range(101)) + "}"
        self.assert_limit_refused(
            "---\n" + block + "\n---\n" + self.BODY)

    def test_json_form_value_length_past_limit_refused(self):
        block = '{"title": "' + "x" * 9000 + '"}'
        self.assert_limit_refused(
            "---\n" + block + "\n---\n" + self.BODY)

    def test_json_form_nesting_past_limit_refused(self):
        nested = "1"
        for _ in range(150):
            nested = "[" + nested + "]"
        block = '{"title": ' + nested + "}"
        self.assert_limit_refused(
            "---\n" + block + "\n---\n" + self.BODY)

    def test_at_limit_front_matter_still_imports(self):
        block = "\n".join("key%d: v" % i for i in range(100))
        path = self.temp_answer(
            "---\n" + block + "\n---\n" + self.BODY, "ok.md")
        record = do_import(self.home, path)
        self.assertIn("plain answer body", record["answer_text"])


class Test037SlotFrontMatterLimits(WorksheetBase):
    def test_slot_body_front_matter_key_count_refused(self):
        target = self.export_sheet(queries=[Q1], planned_answers=1)
        block = "\n".join("key%d: v" % i for i in range(101))
        body = "---\n" + block + "\n---\nSlot answer body stands here."
        self.fill_sheet(target, {1: body})
        self.assert_import_refused(target, "LIMIT_EXCEEDED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)


class Test038SlotCaptureMethodLimit(WorksheetBase):
    def test_slot_asserted_capture_method_past_limit_refused(self):
        target = self.export_sheet(queries=[Q1], planned_answers=1)
        self.fill_sheet(
            target, {1: "A real answer about Acme Ledger."},
            fields={1: {"capture_method": "m" * 2001}})
        self.assert_import_refused(target, "LIMIT_EXCEEDED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)

    def test_slot_asserted_capture_method_at_limit_stores(self):
        target = self.export_sheet(queries=[Q1], planned_answers=1)
        self.fill_sheet(
            target, {1: "A real answer about Acme Ledger."},
            fields={1: {"capture_method": "m" * 2000}})
        do_import(self.home, target)
        answers = payloads_of_kind(self.home, "answer_imported")
        self.assertEqual(len(answers), 1)
        self.assertEqual(len(answers[0]["capture_method"]), 2000)


class Test039WorksheetDestinationResolved(ImportBase):
    def test_destination_through_symlink_into_home_refused(self):
        link = Path(self.root) / "linkhome"
        os.symlink(str(self.home), str(link))
        target = link / "ws-inside.txt"
        with self.assertRaises(Exception) as caught:
            import_module.export_capture_worksheet(
                output_path=str(target), product=PRODUCT, round=ROUND,
                queries=[Q1], engine_labels=[], planned_answers=1,
                home=str(self.home))
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")
        self.assertFalse((Path(self.home) / "ws-inside.txt").exists())


class Test040QuotedFrontMatterKey(ImportBase):
    def test_quoted_and_plain_key_forms_count_as_duplicates(self):
        path = self.temp_answer(
            '---\n"title": One\ntitle: Two\n---\n'
            "Acme Ledger is a plain answer body.", "fm.md")
        self.assert_import_refused(path, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)


class Test041WorksheetDatetimeSeam(WorksheetBase):
    def test_datetime_capture_date_refused_in_vocabulary(self):
        target = self.export_sheet(queries=[Q1], planned_answers=1)
        self.fill_sheet(target, {1: "A real answer about Acme Ledger."})
        before = len(entries_of_kind(self.home, "failure_record"))
        with self.assertRaises(Exception) as caught:
            do_import(
                self.home, target,
                captured_on=datetime.datetime(2026, 11, 10, 12, 0))
        self.assertNotIsInstance(caught.exception, TypeError)
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED")
        records = payloads_of_kind(self.home, "failure_record")
        self.assertEqual(len(records), before + 1)
        self.assertEqual(records[-1].get("error_value"),
                         "IMPORT_VALIDATION_FAILED")
        self.assertEqual(records[-1].get("rule_fired"),
                         "IMPORT_VALIDATION_FAILED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)


KILL_CHILD = r'''
import os
import signal
import sys

sys.path.insert(0, {root!r})
from citeline import journal, service

real_append = journal.append_entry
state = {{"count": 0}}


def killing(home, kind, payload, audit_date=None, run_id=None):
    result = real_append(home, kind, payload,
                         audit_date=audit_date, run_id=run_id)
    state["count"] += 1
    if state["count"] >= 1:
        os.kill(os.getpid(), signal.SIGKILL)
    return result


journal.append_entry = killing
service.probe_import(
    home={home!r}, answer_file={answer_file!r},
    product={product!r}, round={round_label!r},
    engine_label="Engine A", query={query!r}, kind="real_sample",
    captured_on="2026-11-10", capture_method="manual copy",
    audit_date={audit_date!r})
'''

BATCH_KILL_CHILD = r'''
import os
import signal
import sys

sys.path.insert(0, {root!r})
from citeline import journal

real_append = journal.append_entry
state = {{"count": 0}}


def killing(home, kind, payload, audit_date=None, run_id=None):
    result = real_append(home, kind, payload,
                         audit_date=audit_date, run_id=run_id)
    state["count"] += 1
    if state["count"] >= 1:
        os.kill(os.getpid(), signal.SIGKILL)
    return result


journal.append_entry = killing
payload = {{"operation": "probe import",
            "error_value": "IMPORT_VALIDATION_FAILED",
            "subject_identity": "x", "date": {audit_date!r},
            "rule_fired": "IMPORT_VALIDATION_FAILED"}}
journal.append_entries_atomic(
    {home!r},
    [("failure_record", dict(payload)),
     ("failure_record", dict(payload)),
     ("failure_record", dict(payload))],
    audit_date={audit_date!r})
'''


class KillBase(ImportBase):
    def run_child(self, template, **values):
        script = Path(self.root) / "kill_child.py"
        values.setdefault("root", PRODUCT_ROOT)
        values.setdefault("home", str(self.home))
        values.setdefault("product", PRODUCT)
        values.setdefault("round_label", ROUND)
        values.setdefault("query", Q1)
        values.setdefault("audit_date", AUDIT_DATE)
        script.write_text(template.format(**values), encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = PRODUCT_ROOT
        result = subprocess.run(
            [sys.executable, str(script)], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=120)
        self.assertEqual(result.returncode, -signal.SIGKILL,
                         result.stderr.decode("utf-8", "replace"))


class Test083KillInsideBatch(KillBase):
    def test_killed_single_import_recovers_on_retry(self):
        path = self.temp_answer("Acme Ledger is a plain answer.")
        self.run_child(KILL_CHILD, answer_file=str(path))
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 1)
        rounds = payloads_of_kind(self.home, "round_named")
        self.assertIsNone(
            rounds[-1].get("registry_version_at_first_import"))
        record = do_import(self.home, path)
        self.assertIn("plain answer", record["answer_text"])
        answers = payloads_of_kind(self.home, "answer_imported")
        self.assertEqual(len(answers), 1)
        rounds = payloads_of_kind(self.home, "round_named")
        self.assertIsNotNone(
            rounds[-1].get("registry_version_at_first_import"))
        self.assertTrue(journal.verify_chain(str(self.home))["passed"])

    def test_killed_worksheet_batch_recovers_on_retry(self):
        target = Path(self.root) / "ksheet.txt"
        service.export_capture_worksheet(
            home=str(self.home), product=PRODUCT, round=ROUND,
            queries=[Q1, Q2], engine_labels=["Engine A"],
            planned_answers=3, output_path=str(target),
            audit_date=AUDIT_DATE)
        lines = target.read_text(encoding="utf-8").splitlines()
        out = []
        bodies = {1: "Killed batch answer one.",
                  2: "Killed batch answer two.",
                  3: "Killed batch answer three."}
        queries = {1: Q1, 2: Q2, 3: Q1}
        dates = {1: "2026-11-10", 2: "2026-11-10", 3: "2026-11-11"}
        for line in lines:
            match = re.match(r"^slot (\d+):", line)
            if match:
                index = int(match.group(1))
                out.append(
                    "slot %d: query= %s engine_label= Engine A "
                    "kind= real_sample captured_on= %s "
                    "capture_method= manual copy"
                    % (index, queries[index], dates[index]))
                out.append(bodies[index])
            else:
                out.append(line)
        target.write_text("\n".join(out) + "\n", encoding="utf-8")
        self.run_child(KILL_CHILD, answer_file=str(target))
        partial = len(entries_of_kind(self.home, "answer_imported"))
        self.assertGreaterEqual(partial, 1)
        self.assertLess(partial, 3)
        do_import(self.home, target)
        answers = payloads_of_kind(self.home, "answer_imported")
        self.assertEqual(len(answers), 3)
        rounds = payloads_of_kind(self.home, "round_named")
        self.assertIsNotNone(
            rounds[-1].get("registry_version_at_first_import"))
        self.assertTrue(journal.verify_chain(str(self.home))["passed"])

    def test_killed_direct_batch_rolls_back_on_next_append(self):
        before = entry_count(self.home)
        self.run_child(BATCH_KILL_CHILD)
        self.assertEqual(entry_count(self.home), before + 1)
        payload = {"operation": "probe import",
                   "error_value": "SEED_AFTER_KILL",
                   "subject_identity": "y", "date": AUDIT_DATE,
                   "rule_fired": "SEED_AFTER_KILL"}
        journal.append_entry(str(self.home), "failure_record", payload,
                             audit_date=AUDIT_DATE)
        self.assertEqual(entry_count(self.home), before + 1)
        records = payloads_of_kind(self.home, "failure_record")
        self.assertEqual(
            [r.get("error_value") for r in records], ["SEED_AFTER_KILL"])
        self.assertTrue(journal.verify_chain(str(self.home))["passed"])


class Test084WorksheetLimitsInForce(ImportBase):
    def test_lowered_answers_limit_governs_export(self):
        journal.write_config(str(self.home), "answers_per_round = 3\n")
        target = Path(self.root) / "lowered.txt"
        with self.assertRaises(Exception) as caught:
            service.export_capture_worksheet(
                home=str(self.home), product=PRODUCT, round=ROUND,
                queries=[Q1], engine_labels=["Engine A"],
                planned_answers=4, output_path=str(target),
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")
        self.assertFalse(target.exists())

    def test_raised_answers_limit_governs_export(self):
        journal.write_config(
            str(self.home), "answers_per_round = 20000\n")
        target = Path(self.root) / "raised.txt"
        text = service.export_capture_worksheet(
            home=str(self.home), product=PRODUCT, round=ROUND,
            queries=[Q1], engine_labels=["Engine A"],
            planned_answers=10001, output_path=str(target),
            audit_date=AUDIT_DATE)
        self.assertEqual(
            len([line for line in text.splitlines()
                 if re.match(r"^slot \d+:", line)]), 10001)

    def test_lowered_query_limit_governs_module_export(self):
        journal.write_config(
            str(self.home), "queries_per_product = 2\n")
        target = Path(self.root) / "qlowered.txt"
        with self.assertRaises(Exception) as caught:
            import_module.export_capture_worksheet(
                output_path=str(target), product=PRODUCT, round=ROUND,
                queries=["one", "two", "three"], engine_labels=[],
                planned_answers=0, home=str(self.home))
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")
        self.assertFalse(target.exists())


class Test087WorksheetPreflightCost(WorksheetBase):
    def test_worksheet_cost_counts_records_it_would_append(self):
        target = self.export_sheet(planned_answers=3)
        self.fill_sheet(target, {
            1: "Preflight answer one.", 2: "Preflight answer two.",
            3: "Preflight answer three."},
            fields={2: {"query": Q2}, 3: {"captured_on": "2026-11-11"}})
        journal.write_config(
            str(self.home),
            "journal_length = %d\n" % (entry_count(self.home) + 2))
        with self.assertRaises(Exception) as caught:
            do_import(self.home, target)
        self.assertEqual(token_of(caught.exception),
                         "JOURNAL_CAP_EXCEEDED")
        self.assertEqual(getattr(caught.exception, "refusal_context",
                                 None), "import_preflight")
        self.assertEqual(getattr(caught.exception, "limit_number",
                                 None), 39)
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)


class Test088RaisedErrorMessageBound(ImportBase):
    def test_raised_message_stands_within_limit_33(self):
        path = self.temp_answer("Acme Ledger is a plain answer.")
        with self.assertRaises(Exception) as caught:
            do_import(self.home, path, query="x" * 2001)
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED")
        self.assertLessEqual(len(str(caught.exception)), 500)


class Test097WorksheetContradictionName(WorksheetBase):
    def test_contradiction_names_resolved_standing_identity(self):
        target = self.export_sheet()
        self.fill_sheet(target, {
            1: "First worksheet answer text.",
            2: "Second conflicting worksheet answer."},
            fields={2: {"query": Q1}})
        expected_sequence = entry_count(self.home) + 1
        expected_id = "ans-%d-1" % expected_sequence
        with self.assertRaises(Exception) as caught:
            do_import(self.home, target)
        self.assertEqual(token_of(caught.exception),
                         "CONTRADICTORY_IMPORT")
        message = str(caught.exception)
        self.assertIn(expected_id, message)
        self.assertNotIn("{sequence}", message)
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)


if __name__ == "__main__":
    unittest.main()
