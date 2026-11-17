"""Import family.

Test first pins for register to and, from the
register and the source papers the register paper and
the register paper (entry 064, Red RED-02). Each test
reproduces the defect named at its register entry on
the tree standing after fix round 3 and the round 4
F1 and F2 seats, then stands as the pin for its cure."""

import io
import json
import tarfile
import tempfile
import time
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

    def prepare_sheet(self, path, **extra):
        kwargs = {
            "answer_file": str(path), "product": PRODUCT,
            "round": ROUND, "engine_label": "Engine A", "query": Q1,
            "kind": "real_sample", "captured_on": "2026-11-10",
            "capture_method": "manual copy", "audit_date": AUDIT_DATE,
            "query_set": [Q1, Q2],
        }
        kwargs.update(extra)
        return import_module.prepare_worksheet_import(**kwargs)


class Test026SpaceSeparatorHead(ImportBase):
    PDF = b"%PDF-1.4 fake Acme Ledger content"
    ZIP = bytes.fromhex("504B0304") + b" Acme Ledger words"
    HTML = b"<html><body>Acme Ledger</body></html>"
    SPACE_SEPARATORS = ("\u00a0", "\u1680", "\u2002", "\u2007", "\u202f", "\u205f", "\u3000")

    def form_of(self, data):
        return import_module.check11_form(data, data.decode("utf-8"))

    def test_space_separators_shield_nothing(self):
        for char in self.SPACE_SEPARATORS:
            encoded = char.encode("utf-8")
            self.assertEqual(self.form_of(encoded + self.PDF), "pdf",
                             repr(char))
            self.assertEqual(self.form_of(encoded + self.ZIP),
                             "archive", repr(char))
            self.assertEqual(self.form_of(encoded + self.HTML), "html",
                             repr(char))

    def test_space_separator_stacks_shield_nothing(self):
        nbsp = "\u00a0".encode("utf-8")
        bom = b"\xef\xbb\xbf"
        zwsp = "\u200b".encode("utf-8")
        self.assertEqual(self.form_of(nbsp + bom + self.PDF), "pdf")
        self.assertEqual(self.form_of(bom + nbsp + self.ZIP), "archive")
        self.assertEqual(self.form_of(zwsp + nbsp + self.PDF), "pdf")
        self.assertEqual(self.form_of(b"\x01" + nbsp + self.ZIP),
                         "archive")

    def test_space_separator_line_before_header_reads_as_sheet(self):
        text = sheet_text({1: "First filled answer."})
        for char in ("\u00a0", "\u3000"):
            self.assertTrue(
                import_module.is_worksheet_text(char + "\n" + text),
                repr(char))

    def test_service_import_refuses_pdf_behind_no_break_space(self):
        data = "\u00a0".encode("utf-8") + self.PDF
        path = self.temp_bytes(data, "shielded.txt")
        self.assert_import_refused(path, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)


class Test027DefaultIgnorableHead(ImportBase):
    PDF = b"%PDF-1.4 fake Acme Ledger content"
    ZIP = bytes.fromhex("504B0304") + b" Acme Ledger words"
    HTML = b"<html><body>Acme Ledger</body></html>"
    JSON = b'{"answer": "Acme Ledger"}'

    def form_of(self, data):
        return import_module.check11_form(data, data.decode("utf-8"))

    def test_default_ignorables_shield_nothing(self):
        for char in ("\ufe0f", "\u034f"):
            encoded = char.encode("utf-8")
            self.assertEqual(self.form_of(encoded + self.PDF), "pdf",
                             repr(char))
            self.assertEqual(self.form_of(encoded + self.ZIP),
                             "archive", repr(char))
            self.assertEqual(self.form_of(encoded + self.HTML), "html",
                             repr(char))
            self.assertEqual(self.form_of(encoded + self.JSON), "json",
                             repr(char))

    def test_arabic_sign_shields_nothing(self):
        encoded = "\u0610".encode("utf-8")
        self.assertEqual(self.form_of(encoded + self.PDF), "pdf")
        self.assertEqual(self.form_of(encoded + self.ZIP), "archive")

    def test_service_import_refuses_zip_behind_variation_selector(self):
        data = "\ufe0f".encode("utf-8") + self.ZIP
        path = self.temp_bytes(data, "shielded.txt")
        self.assert_import_refused(path, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)


class Test028HeaderLineHeadMaterial(ImportBase):
    def sheet_with_header(self, header_line):
        text = sheet_text({1: "First filled answer.",
                           2: "Second filled answer."})
        lines = text.split("\n")
        lines[0] = header_line
        return "\n".join(lines)

    def test_header_line_forms_read_as_sheet(self):
        header = "Citeline capture worksheet"
        forms = (
            header + "\u200b",
            header + "\ufeff",
            header + "\x01",
            header + "\x7f",
            "Citeline capture\u200b worksheet",
            "Citeline capture \u200bworksheet",
        )
        for form in forms:
            self.assertTrue(
                import_module.is_worksheet_text(
                    self.sheet_with_header(form)), repr(form))

    def test_filled_sheet_with_trailing_zero_width_header_imports(self):
        path = self.temp_answer(
            self.sheet_with_header(
                "Citeline capture worksheet\u200b"), "sheet.txt")
        do_import(self.home, path)
        answers = payloads_of_kind(self.home, "answer_imported")
        self.assertEqual(len(answers), 2)

    def test_control_plain_header_still_reads_as_sheet(self):
        text = sheet_text({1: "First filled answer."})
        self.assertTrue(import_module.is_worksheet_text(text))
        self.assertFalse(
            import_module.is_worksheet_text("plain answer\n" + text))


class Test029SlotIndexForm(ImportBase):
    FORGED = (
        ("\u0662", "Forged Engine"),
        ("\uff12", "Forged Engine"),
        ("02", "Zero Engine"),
    )

    def sheet_with_forged(self, digits, engine):
        forged = (
            "slot %s: query= What is Acme Ledger? engine_label= %s "
            "kind= fixture captured_on= 2026-08-16 "
            "capture_method= manual copy" % (digits, engine))
        return sheet_text({
            1: "Genuine first answer body.\n" + forged
               + "\nForged answer body stands here.",
            2: "Genuine second answer body."})

    def test_non_export_index_forms_open_no_slot(self):
        for digits, engine in self.FORGED:
            sheet = import_module.parse_worksheet(
                self.sheet_with_forged(digits, engine))
            self.assertEqual(len(sheet["slots"]), 2, repr(digits))
            for slot in sheet["slots"]:
                self.assertNotEqual(
                    slot["fields"].get("engine_label"), engine)
                self.assertNotEqual(slot["fields"].get("kind"),
                                    "fixture")
            self.assertIn("Forged answer body stands here.",
                          sheet["slots"][0]["body"])

    def test_non_export_index_forms_forge_no_record(self):
        for digits, engine in (("\u0662", "Forged Engine"),
                               ("02", "Zero Engine")):
            path = self.temp_answer(
                self.sheet_with_forged(digits, engine), "sheet.txt")
            records = self.prepare_sheet(path)
            self.assertEqual(len(records), 2, repr(digits))
            for record in records:
                self.assertNotEqual(
                    record["engine_label_original"], engine)
                self.assertNotEqual(record["kind"], "fixture")


class Test030RepeatedFieldMarker(ImportBase):
    PERMUTED = (
        "slot 2: query= What is Acme Ledger? engine_label= "
        "Perm Engine capture_method= pigeon post kind= "
        "fixture captured_on= 2026-08-14 capture_method= "
        "manual copy")

    def sheet_with_forged(self):
        return sheet_text({
            1: "Genuine first answer body.\n" + self.PERMUTED
               + "\nForged answer body stands here.",
            2: "Genuine second answer body."})

    def test_repeated_marker_line_opens_no_slot(self):
        sheet = import_module.parse_worksheet(self.sheet_with_forged())
        self.assertEqual(len(sheet["slots"]), 2)
        for slot in sheet["slots"]:
            self.assertNotEqual(slot["fields"].get("kind"), "fixture")
        self.assertIn("Forged answer body stands here.",
                      sheet["slots"][0]["body"])

    def test_repeated_marker_line_forges_no_record(self):
        path = self.temp_answer(self.sheet_with_forged(), "sheet.txt")
        records = self.prepare_sheet(path)
        self.assertEqual(len(records), 2)
        for record in records:
            self.assertNotEqual(record["kind"], "fixture")
            self.assertNotEqual(
                record["engine_label_original"], "Perm Engine")


class Test031LongDigitIndex(ImportBase):
    LONG_LINE = (
        "slot " + "9" * 5000 + ": query= x engine_label= y "
        "kind= fixture captured_on= 2026-11-10 "
        "capture_method= z")

    def sheet_with_long_line(self):
        return sheet_text({
            1: "Genuine answer body opens here.\n" + self.LONG_LINE
               + "\nBody text after the long line."})

    def test_long_index_line_parses_as_body_text(self):
        sheet = import_module.parse_worksheet(
            self.sheet_with_long_line())
        self.assertEqual(len(sheet["slots"]), 1)
        self.assertIn("Body text after the long line.",
                      sheet["slots"][0]["body"])

    def test_long_index_line_prepares_without_raw_error(self):
        path = self.temp_answer(self.sheet_with_long_line(),
                                "sheet.txt")
        records = self.prepare_sheet(path)
        self.assertEqual(len(records), 1)

    def test_long_index_line_imports_through_service(self):
        path = self.temp_answer(self.sheet_with_long_line(),
                                "sheet.txt")
        do_import(self.home, path)
        answers = payloads_of_kind(self.home, "answer_imported")
        self.assertEqual(len(answers), 1)


class Test032FrontMatterKeyPosition(unittest.TestCase):
    BODY = "Acme Ledger is a plain answer body."

    def assert_front_refused(self, text, token):
        with self.assertRaises(Exception) as caught:
            import_module.extract_front_matter(text)
        self.assertEqual(token_of(caught.exception), token)

    def test_tag_constructs_in_key_position_refused(self):
        for key_line in ("!tag title: value", "&anchor title: value",
                         "*alias title: value",
                         "%directive title: value"):
            self.assert_front_refused(
                "---\n" + key_line + "\n---\n" + self.BODY,
                "IMPORT_VALIDATION_FAILED")

    def test_tag_construct_in_indented_key_refused(self):
        self.assert_front_refused(
            "---\ntitle: One\n  !tag inner: value\n---\n" + self.BODY,
            "IMPORT_VALIDATION_FAILED")

    def test_angle_tag_construct_in_key_refused(self):
        self.assert_front_refused(
            "---\n<tag> title: value\n---\n" + self.BODY,
            "IMPORT_VALIDATION_FAILED")

    def test_control_plain_key_still_passes(self):
        body, had = import_module.extract_front_matter(
            "---\ntitle: One\n---\n" + self.BODY)
        self.assertTrue(had)
        self.assertEqual(body, self.BODY)


class Test033ContinuationBracket(unittest.TestCase):
    BODY = "Acme Ledger is a plain answer body."

    def assert_front_refused(self, text):
        with self.assertRaises(Exception) as caught:
            import_module.extract_front_matter(text)
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED")
        self.assertIn("not closed", str(caught.exception))

    def test_continuation_square_bracket_refused(self):
        self.assert_front_refused(
            "---\ntitle: abc\n  [def\n---\n" + self.BODY)

    def test_continuation_brace_refused(self):
        self.assert_front_refused(
            "---\ntitle: abc\n  {def\n---\n" + self.BODY)

    def test_control_top_level_bracket_still_refused(self):
        self.assert_front_refused("---\ntitle: [abc\n---\n" + self.BODY)

    def test_control_closed_continuation_passes(self):
        body, had = import_module.extract_front_matter(
            "---\ntitle: abc\n  [def]\n---\n" + self.BODY)
        self.assertTrue(had)
        self.assertEqual(body, self.BODY)


class Test034JsonNumericValueLength(unittest.TestCase):
    BODY = "Acme Ledger is a plain answer body."

    def assert_front_refused(self, text, token):
        with self.assertRaises(Exception) as caught:
            import_module.extract_front_matter(text)
        self.assertEqual(token_of(caught.exception), token)

    def test_long_integer_value_refused(self):
        block = '{"n": ' + "9" * 4200 + "}"
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + self.BODY, "LIMIT_EXCEEDED")

    def test_integer_value_one_past_limit_refused(self):
        block = '{"n": ' + "9" * 4097 + "}"
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + self.BODY, "LIMIT_EXCEEDED")

    def test_long_float_value_refused(self):
        block = '{"n": ' + "1." + "0" * 4198 + "}"
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + self.BODY, "LIMIT_EXCEEDED")

    def test_controls_held(self):
        body, had = import_module.extract_front_matter(
            '---\n{"n": 4200}\n---\n' + self.BODY)
        self.assertTrue(had)
        self.assertEqual(body, self.BODY)
        block = '{"s": "' + "x" * 4200 + '"}'
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + self.BODY, "LIMIT_EXCEEDED")


class Test035ContradictionIdentitySurfaces(ImportBase):
    STANDING = {
        "kind": "real_sample",
        "product": PRODUCT,
        "round": ROUND,
        "engine_label_normalised": "engine a",
        "query": Q1,
        "content_hash": "a different hash stands here",
        "captured_on": "2026-11-10",
        "answer_id": "ans-{sequence}-3",
    }

    def test_single_import_names_resolved_identity(self):
        path = self.temp_answer("A single plain answer text.")
        with self.assertRaises(Exception) as caught:
            import_module.prepare_import(
                answer_file=str(path), product=PRODUCT, round=ROUND,
                engine_label="Engine A", query=Q1, kind="real_sample",
                captured_on="2026-11-10",
                capture_method="manual copy", audit_date=AUDIT_DATE,
                query_set=[Q1, Q2],
                standing_records=[dict(self.STANDING)])
        self.assertEqual(token_of(caught.exception),
                         "CONTRADICTORY_IMPORT")
        message = str(caught.exception)
        self.assertIn("ans-3-3", message)
        self.assertNotIn("{sequence}", message)

    def test_worksheet_resolver_leaves_supplied_identity_as_supplied(
            self):
        path = self.temp_answer(
            sheet_text({1: "First worksheet answer text."}),
            "sheet.txt")
        with self.assertRaises(Exception) as caught:
            self.prepare_sheet(
                path, standing_records=[dict(self.STANDING)],
                answer_id_prefix="ans-{sequence}",
                answer_sequence_base=41)
        self.assertEqual(token_of(caught.exception),
                         "CONTRADICTORY_IMPORT")
        message = str(caught.exception)
        self.assertIn("ans-{sequence}-3", message)
        self.assertNotIn("ans-43-3", message)

    def test_control_worksheet_batch_identity_still_resolves(self):
        path = self.temp_answer(sheet_text({
            1: "First worksheet answer text.",
            2: "Second conflicting worksheet answer."},
            dates={1: "2026-11-10", 2: "2026-11-10"}), "sheet.txt")
        with self.assertRaises(Exception) as caught:
            self.prepare_sheet(
                path, answer_id_prefix="ans-{sequence}",
                answer_sequence_base=41)
        self.assertEqual(token_of(caught.exception),
                         "CONTRADICTORY_IMPORT")
        self.assertIn("ans-41-1", str(caught.exception))
        self.assertNotIn("{sequence}", str(caught.exception))


class Test036WorksheetPreparationCost(ImportBase):
    def big_sheet(self, count):
        lines = [
            "Citeline capture worksheet",
            "product: " + PRODUCT,
            "round: " + ROUND,
            "queries to attempt:",
            "query: " + Q1,
            "engine labels to attempt:",
            "engine: Engine A",
            "slots to fill by hand, one answer per slot:",
            "| slot | answer text stands below its slot line |",
        ]
        for index in range(1, count + 1):
            lines.append(
                "slot %d: query= %s engine_label= Engine %d "
                "kind= real_sample captured_on= 2026-11-10 "
                "capture_method= manual copy" % (index, Q1, index))
            lines.append("Answer body number %d stands here." % index)
        return "\n".join(lines) + "\n"

    def test_preparation_cost_stays_near_linear(self):
        path = self.temp_answer(self.big_sheet(2000), "sheet.txt")
        started = time.monotonic()
        records = self.prepare_sheet(path)
        elapsed = time.monotonic() - started
        self.assertEqual(len(records), 2000)
        self.assertLess(elapsed, 10.0)

    def test_same_engine_contradiction_still_refused(self):
        path = self.temp_answer(sheet_text({
            1: "First worksheet answer text.",
            2: "Second conflicting worksheet answer."},
            dates={1: "2026-11-10", 2: "2026-11-10"}), "sheet.txt")
        with self.assertRaises(Exception) as caught:
            self.prepare_sheet(path)
        self.assertEqual(token_of(caught.exception),
                         "CONTRADICTORY_IMPORT")

    def test_same_engine_duplicate_still_refused(self):
        path = self.temp_answer(sheet_text({
            1: "One shared worksheet answer text.",
            2: "One shared worksheet answer text."},
            dates={1: "2026-11-10", 2: "2026-11-11"}), "sheet.txt")
        with self.assertRaises(Exception) as caught:
            self.prepare_sheet(path)
        self.assertEqual(token_of(caught.exception),
                         "DUPLICATE_IMPORT")


class Test064Check11ContainerForms(ImportBase):
    def form_of(self, data):
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = ""
        return import_module.check11_form(data, text)

    def tar_bytes(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            payload = b"Acme Ledger answer text inside a tar member."
            info = tarfile.TarInfo("answer.txt")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        return buffer.getvalue()

    def test_tar_archive_detected(self):
        self.assertEqual(self.form_of(self.tar_bytes()), "archive")

    def test_zip_spanning_empty_and_zip64_detected(self):
        self.assertEqual(
            self.form_of(bytes.fromhex("504B0708") + b" Acme words"),
            "archive")
        self.assertEqual(
            self.form_of(bytes.fromhex("504B0506") + b"\x00" * 18),
            "archive")
        self.assertEqual(
            self.form_of(bytes.fromhex("504B0606") + b"\x00" * 52),
            "archive")

    def test_ar_archive_detected(self):
        data = b"!<arch>\nanswer.txt/   0           0     0     0     "
        self.assertEqual(self.form_of(data), "archive")

    def test_pdf_header_after_junk_first_line_detected(self):
        data = b"a junk first line stands here\n%PDF-1.7 fake content"
        self.assertEqual(self.form_of(data), "pdf")

    def test_service_import_refuses_tar_archive(self):
        path = self.temp_bytes(self.tar_bytes(), "archive.txt")
        self.assert_import_refused(path, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)

    def test_service_import_refuses_pdf_after_junk_line(self):
        path = self.temp_bytes(
            b"a junk first line stands here\n%PDF-1.7 fake content",
            "junkpdf.txt")
        self.assert_import_refused(path, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)

    def test_controls_held(self):
        plain = b"Acme Ledger is a plain answer."
        self.assertIsNone(self.form_of(plain))
        self.assertEqual(
            self.form_of(b"%PDF-1.4 fake Acme Ledger content"), "pdf")
        self.assertEqual(
            self.form_of(bytes.fromhex("504B0304") + b" Acme words"),
            "archive")


if __name__ == "__main__":
    unittest.main()
