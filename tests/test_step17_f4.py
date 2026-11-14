"""Step 17 fix seat F4 tests: import family and worksheet surface.

Pins the register entries charged to F4 in the combined fix
wave: S17-R1-032, S17-R1-033, S17-R1-034, S17-R1-035,
S17-R1-036, S17-R1-037, S17-R1-089, S17-R1-101, S17-R1-105,
S17-R1-106, and S17-R1X-017 to S17-R1X-025 with
S17-R1X-031. Every test was written before its cure and run
failing for the register stated reason. Oracle: the register
entries at design/audit/step-17-r1-findings-register.md and
design/audit/step-17-r1x-findings-register.md, the brief
items they cite, and the combined charge at
design/audit/step-17-r1x-disposition.md.
"""

import hashlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from citeline import journal, probe_import as import_module, service

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
PRODUCT = "Acme Ledger"
Q1 = "What is Acme Ledger?"
Q2 = "Best ferry tracker?"
ROUND = "round-1"
ROUND2 = "round-2"


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


def seed_round2(home):
    service.name_round(
        home=str(home), product=PRODUCT, round_label=ROUND2,
        importer_declaration="all captured",
        supplier_relation="independent party", audit_date=AUDIT_DATE)


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
    found = []
    for entry in journal_entries(home):
        if entry.get("entry_kind") == kind:
            found.append(entry)
        payload = entry.get("payload") or {}
        if isinstance(payload, dict) and payload.get("entry_kind") == kind:
            found.append(entry)
    return found


def payloads_of_kind(home, kind):
    out = []
    for entry in entries_of_kind(home, kind):
        payload = entry.get("payload") or {}
        out.append(payload)
    return out


def entry_count(home):
    result = service.status(home=str(home))
    if isinstance(result, dict):
        return result["entry_count"]
    return getattr(result, "entry_count")


def token_of(exc):
    return getattr(exc, "error_value", None) or getattr(
        exc, "token", None) or ""


def set_journal_length(case, value):
    journal.write_config(
        str(case.home), "journal_length = %d\n" % value)


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


class Test032BomAndControl(ImportBase):
    def test_bom_json_refused(self):
        path = self.temp_bytes(
            b"\xef\xbb\xbf" + b'{"answer": "Acme Ledger is great"}')
        with self.assertRaises(Exception) as caught:
            do_import(self.home, path)
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED")
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 0)

    def test_bom_html_and_pdf_refused(self):
        for name, data in (
                ("h.txt", b"\xef\xbb\xbf<html><body>Acme</body></html>"),
                ("p.txt", b"\xef\xbb\xbf%PDF-1.4 fake Acme Ledger")):
            path = self.temp_bytes(data, name)
            with self.assertRaises(Exception) as caught:
                do_import(self.home, path)
            self.assertEqual(token_of(caught.exception),
                             "IMPORT_VALIDATION_FAILED", name)
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 0)

    def test_leading_control_byte_html_refused(self):
        for name, prefix in (("n.txt", b"\x00"), ("v.txt", b"\x0b")):
            path = self.temp_bytes(
                prefix + b"<html><body>Acme Ledger</body></html>", name)
            with self.assertRaises(Exception) as caught:
                do_import(self.home, path)
            self.assertEqual(token_of(caught.exception),
                             "IMPORT_VALIDATION_FAILED", name)
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 0)

    def test_bom_stripped_from_stored_text(self):
        path = self.temp_bytes(
            b"\xef\xbb\xbf" + "Acme Ledger is a plain answer.".encode())
        record = do_import(self.home, path)
        text = record["answer_text"] if isinstance(record, dict) \
            else record.answer_text
        self.assertFalse(text.startswith("\ufeff"))
        self.assertTrue(text.startswith("Acme Ledger"))


class Test033Recursion(ImportBase):
    def test_deeply_nested_json_refused_in_vocabulary(self):
        path = self.temp_bytes(b"[" * 12000 + b"]" * 12000)
        with self.assertRaises(Exception) as caught:
            do_import(self.home, path)
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED")
        self.assertNotIsInstance(caught.exception, RecursionError)
        records = payloads_of_kind(self.home, "failure_record")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].get("error_value"),
                         "IMPORT_VALIDATION_FAILED")


class Test034And037CapPreflight(ImportBase):
    def test_first_import_at_one_slot_headroom_stores_nothing(self):
        set_journal_length(self, entry_count(self.home) + 1)
        path = self.temp_answer("Acme Ledger is a plain answer.")
        with self.assertRaises(Exception) as caught:
            do_import(self.home, path)
        self.assertEqual(token_of(caught.exception),
                         "JOURNAL_CAP_EXCEEDED")
        self.assertEqual(getattr(caught.exception, "refusal_context",
                                 None), "import_preflight")
        self.assertEqual(getattr(caught.exception, "limit_number",
                                 None), 39)
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 0)
        rounds = payloads_of_kind(self.home, "round_named")
        self.assertIsNone(
            rounds[-1].get("registry_version_at_first_import"))

    def test_at_cap_import_refused_before_file_is_read(self):
        set_journal_length(self, entry_count(self.home))
        transcript = self.temp_answer(
            "# Transcript\nUser: hello there\nAssistant: general reply\n",
            "t.md")
        bad = self.temp_bytes(b"\xff\xfe not utf8", "bad.bin")
        for path in (transcript, bad):
            with self.assertRaises(Exception) as caught:
                do_import(self.home, path)
            self.assertEqual(token_of(caught.exception),
                             "JOURNAL_CAP_EXCEEDED", str(path))
            self.assertEqual(
                getattr(caught.exception, "refusal_context", None),
                "import_preflight", str(path))
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 0)


class Test035FrontMatter(ImportBase):
    BODY = "Acme Ledger is a plain answer body."

    def test_duplicate_key_front_matter_refused(self):
        path = self.temp_answer(
            "---\ntitle: One\ntitle: Two\n---\n" + self.BODY, "fm.md")
        with self.assertRaises(Exception) as caught:
            do_import(self.home, path)
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED")
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 0)

    def test_unclosed_front_matter_refused(self):
        path = self.temp_answer(
            "---\ntitle: Never closed\n" + self.BODY, "fm.md")
        with self.assertRaises(Exception) as caught:
            do_import(self.home, path)
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED")
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 0)

    def test_json_front_matter_duplicate_key_refused(self):
        path = self.temp_answer(
            '---\n{"title": "a", "title": "b"}\n---\n' + self.BODY,
            "fm.md")
        with self.assertRaises(Exception) as caught:
            do_import(self.home, path)
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED")
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 0)

    def test_malformed_front_matter_refused(self):
        path = self.temp_answer("---\n: : : [\n---\n" + self.BODY,
                                "fm.md")
        with self.assertRaises(Exception) as caught:
            do_import(self.home, path)
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED")
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 0)

    def test_tag_front_matter_refused(self):
        path = self.temp_answer(
            "---\ntitle: !tag value\n---\n" + self.BODY, "fm.md")
        with self.assertRaises(Exception) as caught:
            do_import(self.home, path)
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED")

    def test_passing_front_matter_excluded_from_answer_text(self):
        text = ("---\ntitle: Acme Ledger Official Guide\n---\n"
                "Nothing relevant is discussed in this body text.")
        path = self.temp_answer(text, "fm.md")
        record = do_import(self.home, path)
        stored = record["answer_text"]
        self.assertNotIn("Official Guide", stored)
        self.assertNotIn("title:", stored)
        self.assertIn("Nothing relevant", stored)
        self.assertEqual(
            record["content_hash"],
            hashlib.sha256(path.read_bytes()).hexdigest())


class Test036AdapterTypes(ImportBase):
    PLAIN = "Acme Ledger is a plain answer."

    def assert_refused_with_one_failure_record(self, **overrides):
        before = len(entries_of_kind(self.home, "failure_record"))
        path = self.temp_answer(self.PLAIN)
        with self.assertRaises(Exception) as caught:
            do_import(self.home, path, **overrides)
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED", repr(overrides))
        self.assertNotIsInstance(caught.exception, TypeError)
        records = entries_of_kind(self.home, "failure_record")
        self.assertEqual(len(records), before + 1, repr(overrides))
        payload = (records[-1].get("payload") or {})
        self.assertEqual(payload.get("error_value"),
                         "IMPORT_VALIDATION_FAILED")
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 0)

    def test_bytes_engine_label_refused(self):
        self.assert_refused_with_one_failure_record(
            engine_label=b"Engine A")

    def test_bytes_capture_method_refused(self):
        self.assert_refused_with_one_failure_record(
            capture_method=b"manual copy")

    def test_int_and_list_and_dict_engine_label_refused(self):
        self.assert_refused_with_one_failure_record(engine_label=12345)
        self.assert_refused_with_one_failure_record(
            engine_label=["Engine", "A"])
        self.assert_refused_with_one_failure_record(
            engine_label={"label": "Engine A"})

    def test_int_capture_method_refused(self):
        self.assert_refused_with_one_failure_record(capture_method=12345)

    def test_int_captured_on_refused(self):
        self.assert_refused_with_one_failure_record(captured_on=20261110)

    def test_adapter_module_refuses_int_engine_and_method(self):
        path = self.temp_answer(self.PLAIN)
        for overrides in ({"engine_label": 123},
                          {"capture_method": 123}):
            kwargs = {
                "answer_file": str(path), "product": PRODUCT,
                "round": ROUND, "engine_label": "Engine A",
                "query": Q1, "kind": "real_sample",
                "captured_on": "2026-11-10",
                "capture_method": "manual copy",
                "audit_date": AUDIT_DATE,
            }
            kwargs.update(overrides)
            with self.assertRaises(Exception) as caught:
                import_module.probe_import(**kwargs)
            self.assertEqual(token_of(caught.exception),
                             "IMPORT_VALIDATION_FAILED",
                             repr(overrides))


class Test089MultiAppend(ImportBase):
    def test_second_append_failure_cannot_split_import(self):
        real_append = journal.append_entry

        def flaky(home, kind, payload, audit_date=None, run_id=None):
            if kind == "round_named" and payload.get(
                    "registry_version_at_first_import") is not None:
                raise journal.JournalError(
                    "a writing invocation already holds this home",
                    row="X-10", token="WRITE_CONTENDED")
            return real_append(home, kind, payload,
                               audit_date=audit_date, run_id=run_id)

        path = self.temp_answer("Acme Ledger is a plain answer.")
        with mock.patch.object(journal, "append_entry", flaky):
            with self.assertRaises(Exception) as caught:
                do_import(self.home, path)
        self.assertEqual(token_of(caught.exception),
                         "WRITE_CONTENDED")
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 0)
        rounds = payloads_of_kind(self.home, "round_named")
        self.assertIsNone(
            rounds[-1].get("registry_version_at_first_import"))

    def test_atomic_batch_appends_all_or_nothing(self):
        batch = getattr(journal, "append_entries_atomic", None)
        self.assertIsNotNone(batch)
        payload = {"operation": "probe import",
                   "error_value": "IMPORT_VALIDATION_FAILED",
                   "subject_identity": "x", "date": AUDIT_DATE,
                   "rule_fired": "IMPORT_VALIDATION_FAILED"}
        before = entry_count(self.home)
        with self.assertRaises(Exception):
            batch(str(self.home),
                  [("failure_record", dict(payload)),
                   ("no_such_kind", dict(payload))],
                  audit_date=AUDIT_DATE)
        self.assertEqual(entry_count(self.home), before)
        batch(str(self.home),
              [("failure_record", dict(payload)),
               ("failure_record", dict(payload))],
              audit_date=AUDIT_DATE)
        self.assertEqual(entry_count(self.home), before + 2)

    def test_audit_at_one_slot_headroom_stores_no_snapshot(self):
        set_journal_length(self, entry_count(self.home) + 1)
        with self.assertRaises(Exception) as caught:
            service.audit(home=str(self.home),
                          page_file=str(FIXTURES / "w7-page.md"),
                          audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception),
                         "JOURNAL_CAP_EXCEEDED")
        self.assertEqual(len(entries_of_kind(
            self.home, "snapshot_registered")), 0)
        self.assertEqual(len(entries_of_kind(self.home,
                                             "audit_record")), 0)


class Test101ContradictionSurface(ImportBase):
    def test_contradiction_message_names_answer_and_remedy(self):
        first = do_import(
            self.home, self.temp_answer("First answer text.", "a.txt"))
        standing_id = first["answer_id"]
        with self.assertRaises(Exception) as caught:
            do_import(self.home,
                      self.temp_answer("Second different answer.", "b.txt"))
        self.assertEqual(token_of(caught.exception),
                         "CONTRADICTORY_IMPORT")
        message = str(caught.exception)
        self.assertIn(standing_id, message)
        self.assertNotIn("normalised", message)
        self.assertNotIn("content hash", message)
        self.assertIn("capture date", message)


class Test105EmptySurface(ImportBase):
    def test_empty_import_success_surface_states_emptiness(self):
        record = do_import(self.home,
                           self.temp_bytes(b"", "empty.txt"))
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 1)
        texts = []
        if isinstance(record, dict):
            texts = [str(v) for v in record.values()]
        self.assertTrue(
            any("empty" in t.casefold() and "no answer text" in t
                for t in texts),
            "no plain empty warning on the success surface: %r"
            % (record,))


class Test106JsonSurface(ImportBase):
    def test_json_refusal_is_plain_and_actionable(self):
        path = self.temp_answer(
            '{"role": "assistant", "content": "Acme Ledger text"}')
        with self.assertRaises(Exception) as caught:
            do_import(self.home, path)
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED")
        message = str(caught.exception)
        self.assertNotIn("validation check 11", message)
        self.assertIn("JSON", message)
        self.assertIn("on its own", message)


class WorksheetBase(ImportBase):
    def setUp(self):
        super().setUp()
        seed_round2(self.home)

    def export_sheet(self, name="sheet.txt", **kwargs):
        target = Path(self.root) / name
        call = {"home": str(self.home), "product": PRODUCT,
                "round": ROUND, "queries": [Q1, Q2],
                "engine_labels": ["Engine A"], "planned_answers": 2,
                "output_path": str(target), "audit_date": AUDIT_DATE}
        call.update(kwargs)
        service.export_capture_worksheet(**call)
        return target

    def slot_lines(self, text):
        return [line for line in text.splitlines()
                if re.match(r"^slot \d+:", line)]


class TestWorksheetRoundTrip(WorksheetBase):
    def test_x017_slots_import_as_separate_answers(self):
        target = self.export_sheet()
        lines = target.read_text(encoding="utf-8").splitlines()
        out = []
        bodies = {1: "ANSWER-ONE about ledgers for query one.",
                  2: "ANSWER-TWO about ferries for query two."}
        queries = {1: Q1, 2: Q2}
        for line in lines:
            match = re.match(r"^slot (\d+):", line)
            if match:
                index = int(match.group(1))
                out.append(
                    "slot %d: query= %s engine_label= Engine A "
                    "kind= real_sample captured_on= 2026-11-10 "
                    "capture_method= manual copy"
                    % (index, queries[index]))
                out.append(bodies[index])
            else:
                out.append(line)
        target.write_text("\n".join(out) + "\n", encoding="utf-8")
        do_import(self.home, target)
        answers = payloads_of_kind(self.home, "answer_imported")
        self.assertEqual(len(answers), 2)
        by_query = {a["query"]: a["answer_text"] for a in answers}
        self.assertIn("ANSWER-ONE", by_query[Q1])
        self.assertNotIn("ANSWER-TWO", by_query[Q1])
        self.assertIn("ANSWER-TWO", by_query[Q2])
        self.assertNotIn("Citeline capture worksheet", by_query[Q1])

    def test_x018_slot_contents_face_check11_and_uncovered_rule(self):
        hostile = {
            "json_lines": '{"a": 1}\n{"b": 2}',
            "delimited": "a,b,c\nd,e,f\ng,h,i",
            "transcript": "User: hello there\nAssistant: general reply",
            "html": "<html><body>Acme Ledger</body></html>",
        }
        for name, body in hostile.items():
            target = self.export_sheet(
                name="sheet-%s.txt" % name, queries=[Q1],
                planned_answers=1)
            text = target.read_text(encoding="utf-8")
            target.write_text(text.rstrip() + "\n" + body + "\n",
                              encoding="utf-8")
            with self.assertRaises(Exception) as caught:
                do_import(self.home, target)
            self.assertIn(token_of(caught.exception),
                          ("IMPORT_VALIDATION_FAILED",
                           "UNCOVERED_IMPORT_FORM"), name)
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 0)

    def test_x019_unfilled_sheet_stores_nothing(self):
        target = self.export_sheet(queries=[Q1], planned_answers=2)
        for round_name in (ROUND, ROUND2):
            with self.assertRaises(Exception) as caught:
                do_import(self.home, target, round=round_name)
            self.assertEqual(token_of(caught.exception),
                             "IMPORT_VALIDATION_FAILED", round_name)
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 0)

    def test_x019_filled_sheet_refused_into_other_round(self):
        target = self.export_sheet(queries=[Q1], planned_answers=1)
        text = target.read_text(encoding="utf-8")
        target.write_text(
            text.rstrip() + "\nA real answer about Acme Ledger.\n",
            encoding="utf-8")
        with self.assertRaises(Exception) as caught:
            do_import(self.home, target, round=ROUND2)
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED")
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 0)

    def test_x020_sheet_query_binds_the_import(self):
        target = self.export_sheet(queries=[Q1], planned_answers=1)
        lines = target.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines:
            if re.match(r"^slot \d+:", line):
                out.append(
                    "slot 1: query= %s engine_label= Engine A "
                    "kind= real_sample captured_on= 2026-11-10 "
                    "capture_method= manual copy" % Q1)
                out.append("A real answer about Acme Ledger.")
            else:
                out.append(line)
        target.write_text("\n".join(out) + "\n", encoding="utf-8")
        do_import(self.home, target)
        with self.assertRaises(Exception) as caught:
            do_import(self.home, target, query=Q2,
                      captured_on="2026-11-11")
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED")
        self.assertEqual(len(entries_of_kind(self.home,
                                             "answer_imported")), 1)

    def test_x020_slot_metadata_governs_the_record(self):
        target = self.export_sheet(queries=[Q1], planned_answers=1)
        lines = target.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines:
            if re.match(r"^slot \d+:", line):
                out.append(
                    "slot 1: query= %s engine_label= Fixture Engine "
                    "kind= fixture captured_on= 2026-08-16 "
                    "capture_method= pigeon post" % Q1)
                out.append("A real answer about Acme Ledger.")
            else:
                out.append(line)
        target.write_text("\n".join(out) + "\n", encoding="utf-8")
        do_import(self.home, target)
        answers = payloads_of_kind(self.home, "answer_imported")
        self.assertEqual(len(answers), 1)
        record = answers[0]
        self.assertEqual(record["engine_label_original"],
                         "Fixture Engine")
        self.assertEqual(record["kind"], "fixture")
        self.assertEqual(record["captured_on"], "2026-08-16")
        self.assertEqual(record["capture_method"], "pigeon post")


class TestWorksheetExport(WorksheetBase):
    def export_call(self, **kwargs):
        call = {"home": str(self.home), "product": PRODUCT,
                "round": ROUND, "queries": [Q1],
                "engine_labels": ["Engine A"], "planned_answers": 1,
                "output_path": str(Path(self.root) / "out.txt"),
                "audit_date": AUDIT_DATE}
        call.update(kwargs)
        return service.export_capture_worksheet(**call)

    def test_x021_default_queries_come_from_round_definition(self):
        target = Path(self.root) / "default.txt"
        service.export_capture_worksheet(
            home=str(self.home), product=PRODUCT, round=ROUND,
            queries=None, engine_labels=["Engine A"],
            planned_answers=1, output_path=str(target),
            audit_date=AUDIT_DATE)
        text = target.read_text(encoding="utf-8")
        self.assertIn(Q1, text)
        self.assertIn(Q2, text)

    def test_x021_invented_query_refused(self):
        target = Path(self.root) / "invented.txt"
        with self.assertRaises(Exception) as caught:
            self.export_call(queries=["Totally unregistered query?"],
                             output_path=str(target))
        self.assertEqual(token_of(caught.exception),
                         "VALIDATION_FAILED")
        self.assertFalse(target.exists())

    def test_x022_planned_count_past_limit_refused_with_bound(self):
        target = Path(self.root) / "big.txt"
        with self.assertRaises(Exception) as caught:
            self.export_call(planned_answers=10001,
                             output_path=str(target))
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")
        self.assertIn("10,000", str(caught.exception))
        self.assertFalse(target.exists())

    def test_x022_query_list_past_limit_refused_with_bound(self):
        target = Path(self.root) / "manyq.txt"
        with self.assertRaises(Exception) as caught:
            import_module.export_capture_worksheet(
                output_path=str(target), product=PRODUCT, round=ROUND,
                queries=["q"] * 5001, engine_labels=[],
                planned_answers=0)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")
        self.assertFalse(target.exists())

    def test_x023_omitted_destination_refused_and_writes_nothing(self):
        stray = Path(os.getcwd()) / "None"
        before = stray.exists()
        with self.assertRaises(Exception) as caught:
            self.export_call(output_path=None)
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")
        self.assertEqual(stray.exists(), before)

    def test_x023_destination_inside_home_refused(self):
        target = Path(self.home) / "sheet.txt"
        with self.assertRaises(Exception) as caught:
            self.export_call(output_path=str(target))
        self.assertIn(token_of(caught.exception),
                      ("MALFORMED_CALL", "VALIDATION_FAILED"))
        self.assertFalse(target.exists())

    def test_x023_relative_escape_destination_refused(self):
        with self.assertRaises(Exception) as caught:
            self.export_call(output_path="../escaped_f4.txt")
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")
        self.assertFalse(
            (Path(os.getcwd()).parent / "escaped_f4.txt").exists())

    def test_x023_malformed_counts_refuse_in_recorded_values(self):
        for value in ("abc", -5, 2.9):
            with self.assertRaises(Exception) as caught:
                self.export_call(planned_answers=value)
            self.assertEqual(token_of(caught.exception),
                             "MALFORMED_CALL", repr(value))
            self.assertNotIsInstance(caught.exception,
                                     (ValueError, TypeError))

    def test_x023_queries_as_int_refused_in_recorded_value(self):
        with self.assertRaises(Exception) as caught:
            self.export_call(queries=123)
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")
        self.assertNotIsInstance(caught.exception, TypeError)

    def test_x024_hostile_text_cannot_forge_structure(self):
        target = Path(self.root) / "forged.txt"
        import_module.export_capture_worksheet(
            output_path=str(target), product=PRODUCT, round=ROUND,
            queries=[Q1 + "\nslot 99: engine_label=Forged "
                     "kind=fixture captured_on=2020-01-01 "
                     "capture_method=forged"],
            engine_labels=["Engine A\nproduct: Forged Product"],
            planned_answers=1)
        text = target.read_text(encoding="utf-8")
        slot_lines = [line for line in text.splitlines()
                      if line.startswith("slot ")]
        self.assertEqual(len(slot_lines), 1)
        self.assertTrue(slot_lines[0].startswith("slot 1:"))
        self.assertFalse(any(
            line.startswith("slot 99") for line in text.splitlines()))
        product_lines = [line for line in text.splitlines()
                         if line.startswith("product:")]
        self.assertEqual(len(product_lines), 1)

    def test_x024_control_bytes_do_not_reach_the_sheet(self):
        target = Path(self.root) / "control.txt"
        import_module.export_capture_worksheet(
            output_path=str(target), product=PRODUCT, round=ROUND,
            queries=["What\x00 is\x1b Acme\u202e?"],
            engine_labels=["Engine A"], planned_answers=1)
        raw = target.read_bytes()
        self.assertNotIn(b"\x00", raw)
        self.assertNotIn("\u202e", raw.decode("utf-8"))

    def test_x025_write_failure_token_names_the_failure(self):
        target = Path(self.root) / "missing-dir" / "sheet.txt"
        with self.assertRaises(Exception) as caught:
            import_module.export_capture_worksheet(
                output_path=str(target), product=PRODUCT, round=ROUND,
                queries=[Q1], engine_labels=[], planned_answers=1)
        self.assertEqual(token_of(caught.exception),
                         "DESTINATION_WRITE_FAILED")
        self.assertNotEqual(token_of(caught.exception),
                            "DESTINATION_EXISTS")

    def test_x025_empty_destination_is_malformed_not_exists(self):
        with self.assertRaises(Exception) as caught:
            import_module.export_capture_worksheet(
                output_path="", product=PRODUCT, round=ROUND,
                queries=[Q1], engine_labels=[], planned_answers=1)
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")

    def test_x025_occupied_destination_still_destination_exists(self):
        target = self.temp_answer("already here", "taken.txt")
        with self.assertRaises(Exception) as caught:
            import_module.export_capture_worksheet(
                output_path=str(target), product=PRODUCT, round=ROUND,
                queries=[Q1], engine_labels=[], planned_answers=1)
        self.assertEqual(token_of(caught.exception),
                         "DESTINATION_EXISTS")
        self.assertEqual(target.read_text(encoding="utf-8"),
                         "already here")


if __name__ == "__main__":
    unittest.main()
