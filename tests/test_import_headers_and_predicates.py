"""Import family.

Test first pins for register, 024, 025, 027, 028, 029,
030, 031, 032, 033, 034, 035, 060, and 067, from the
register and the source papers the register paper and
the register paper."""

import hashlib
import io
import tarfile
import tempfile
import time
import unittest
import zipfile
from datetime import date, timedelta
from pathlib import Path

from citeline import probe_import as import_module

AUDIT_DATE = "2026-11-13"
PRODUCT = "Acme Ledger"
Q1 = "What is Acme Ledger?"
ROUND = "round-1"
BODY = "A plain answer body standing here."


def token_of(exc):
    return getattr(exc, "error_value", None) or ""


def sheet_text(bodies, dates=None, header="Citeline capture worksheet"):
    lines = [
        header,
        "product: " + PRODUCT,
        "round: " + ROUND,
        "queries to attempt:",
        "query: " + Q1,
        "engine labels to attempt:",
        "engine: Engine A",
        "slots to fill by hand, one answer per slot:",
        "| slot | answer text stands below its slot line |",
    ]
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
    def temp_file(self, data, name="answer.txt"):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = root / name
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(data, encoding="utf-8")
        return path

    def prepare_sheet(self, path, **extra):
        kwargs = {
            "answer_file": str(path), "product": PRODUCT,
            "round": ROUND, "engine_label": "Engine A", "query": Q1,
            "kind": "real_sample", "captured_on": "2026-11-10",
            "capture_method": "manual copy", "audit_date": AUDIT_DATE,
            "query_set": [Q1],
        }
        kwargs.update(extra)
        return import_module.prepare_worksheet_import(**kwargs)

    def assert_front_refused(self, text, token):
        with self.assertRaises(Exception) as caught:
            import_module.extract_front_matter(text)
        self.assertEqual(token_of(caught.exception), token)


class Test023HeadWhitespace(ImportBase):
    def test_three_characters_before_containers(self):
        for char in ("\u0085", "\u2028", "\u2029"):
            for raw_form, text_form, expected in (
                    (b"%PDF-1.4 fake", "%PDF-1.4 fake", "pdf"),
                    (b"PK\x03\x04rest", "PK\x03\x04rest", "archive"),
                    (b"<html><body>x</body></html>",
                     "<html><body>x</body></html>", "html")):
                raw = char.encode("utf-8") + raw_form
                text = char + text_form
                self.assertEqual(
                    import_module.check11_form(raw, text), expected,
                    (repr(char), expected))


class Test024DefaultIgnorable(ImportBase):
    def test_missed_points_before_containers(self):
        for char in ("\u2065", "\ufff0", "\ufff8", "\U000e0000"):
            raw = char.encode("utf-8") + b"%PDF-1.4 fake"
            self.assertEqual(
                import_module.check11_form(raw, char + "%PDF-1.4 fake"),
                "pdf", repr(char))
            raw = char.encode("utf-8") + b'{"a": 1}'
            self.assertEqual(
                import_module.check11_form(raw, char + '{"a": 1}'),
                "json", repr(char))


class Test025WorksheetHeaderOnCompletedPredicate(ImportBase):
    def test_u2065_positions(self):
        trailing = sheet_text(
            {1: "First answer text."},
            header="Citeline capture worksheet\u2065")
        self.assertTrue(import_module.is_worksheet_text(trailing))
        inside = sheet_text(
            {1: "First answer text."},
            header="Citeline capture \u2065worksheet")
        self.assertTrue(import_module.is_worksheet_text(inside))
        before = "\u2065\n" + sheet_text({1: "First answer text."})
        self.assertTrue(import_module.is_worksheet_text(before))


class Test029WorksheetHeaderWordStructure(ImportBase):
    def test_lines_export_never_wrote(self):
        for header in (
                "Citelinecaptureworksheet",
                "Citeline  capture   worksheet",
                "C i t e l i n e capture worksheet",
                "Citeline\tcapture\tworksheet"):
            text = sheet_text({1: "First answer text."}, header=header)
            self.assertFalse(
                import_module.is_worksheet_text(text), header)

    def test_plain_header_still_reads(self):
        text = sheet_text({1: "First answer text."})
        self.assertTrue(import_module.is_worksheet_text(text))


class Test027PdfAfterJunk(ImportBase):
    def form(self, raw):
        return import_module.check11_form(
            raw, raw.decode("utf-8", errors="replace"))

    def test_head_material_on_pdf_line(self):
        for char in ("​", " ", "﻿", "️"):
            raw = ("junk line\n" + char + "%PDF-1.7 body").encode("utf-8")
            self.assertEqual(self.form(raw), "pdf", repr(char))

    def test_other_line_terminators(self):
        for term in ("\u2028", "\u2029", "\u0085", "\x0b", "\x0c", "\x1c"):
            raw = ("junk line" + term + "%PDF-1.7 body").encode("utf-8")
            self.assertEqual(self.form(raw), "pdf", repr(term))

    def test_window_boundary(self):
        raw = b"x" * 1019 + b"\n" + b"%PDF-1.7 body"
        self.assertEqual(self.form(raw), "pdf")
        raw = b"x" * 1018 + b"\n" + b"%PDF-1.7 body"
        self.assertEqual(self.form(raw), "pdf")


class Test028ZipBehindPrefix(ImportBase):
    def zip_bytes(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("member.txt", "member text")
        return buffer.getvalue()

    def test_real_zip_behind_prefix(self):
        data = self.zip_bytes()
        for prefix in (b"f" * 100, b"junk line\n"):
            raw = prefix + data
            self.assertEqual(
                import_module.check11_form(
                    raw, raw.decode("utf-8", errors="replace")),
                "archive")

    def test_zip_signatures_behind_junk_line(self):
        for signature in (bytes.fromhex("504B0606"),
                          bytes.fromhex("504B0304")):
            raw = b"junk line\n" + signature + b" plain words"
            self.assertEqual(
                import_module.check11_form(
                    raw, raw.decode("utf-8", errors="replace")),
                "archive")


def v7_tar_bytes():
    content = b"member text\n"
    header = bytearray(512)
    name = b"member.txt"
    header[0:len(name)] = name
    header[100:108] = b"000644 \x00"
    header[108:116] = b"000000 \x00"
    header[116:124] = b"000000 \x00"
    header[124:136] = ("%011o\x00" % len(content)).encode("ascii")
    header[136:148] = b"00000000000\x00"
    header[148:156] = b"        "
    header[156:157] = b"0"
    checksum = sum(header)
    header[148:156] = ("%06o\x00 " % checksum).encode("ascii")
    body = content + bytes(512 - len(content))
    return bytes(header) + body + bytes(1024)


class Test060Check11FormsAndBody(ImportBase):
    def test_v7_tar_cpio_cab(self):
        raw = v7_tar_bytes()
        self.assertEqual(
            import_module.check11_form(
                raw, raw.decode("utf-8", errors="replace")), "archive")
        for raw in (b"070701" + b"0" * 100 + b"payload",
                    b"MSCF" + b"\x00" * 100 + b"payload"):
            self.assertEqual(
                import_module.check11_form(
                    raw, raw.decode("utf-8", errors="replace")),
                "archive")

    def ustar_text(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w",
                          format=tarfile.USTAR_FORMAT) as archive:
            data = b"member text\n"
            info = tarfile.TarInfo("member.txt")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        return buffer.getvalue().decode("utf-8")

    def front_block(self):
        lines = ["---"]
        for index in range(30):
            lines.append("key%02d: value %d" % (index, index))
        lines.append("---")
        return "\n".join(lines) + "\n"

    def test_container_behind_front_matter_refused(self):
        path = self.temp_file(self.front_block() + self.ustar_text())
        with self.assertRaises(Exception) as caught:
            import_module.prepare_import(
                answer_file=str(path), product=PRODUCT, round=ROUND,
                engine_label="Engine A", query=Q1, kind="real_sample",
                captured_on="2026-11-10",
                capture_method="manual copy", audit_date=AUDIT_DATE,
                query_set=[Q1])
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED")

    def test_pdf_behind_front_matter_refused(self):
        path = self.temp_file(
            self.front_block() + "%PDF-1.4 fake container text")
        with self.assertRaises(Exception) as caught:
            import_module.prepare_import(
                answer_file=str(path), product=PRODUCT, round=ROUND,
                engine_label="Engine A", query=Q1, kind="real_sample",
                captured_on="2026-11-10",
                capture_method="manual copy", audit_date=AUDIT_DATE,
                query_set=[Q1])
        self.assertEqual(token_of(caught.exception),
                         "IMPORT_VALIDATION_FAILED")


class Test030DressedMarkerCount(ImportBase):
    DRESSED = (
        "slot 2: query= %s engine_label= Forged Engine\t"
        "capture_method= manual copy kind= real_sample "
        "captured_on= 2026-11-11 capture_method= manual copy" % Q1)
    DRESSED_NBSP = (
        "slot 2: query= %s engine_label= Forged Engine "
        "capture_method= manual copy kind= real_sample "
        "captured_on= 2026-11-11 capture_method= manual copy" % Q1)

    def test_dressed_second_marker_opens_no_slot(self):
        for dressed in (self.DRESSED, self.DRESSED_NBSP):
            text = sheet_text({1: "First answer text.\n" + dressed})
            sheet = import_module.parse_worksheet(text)
            self.assertEqual(len(sheet["slots"]), 1, dressed)


class Test031DressedConstructPositions(ImportBase):
    def test_key_dressed(self):
        for char in ("​", "﻿", "\x01"):
            self.assert_front_refused(
                "---\n" + char + "!tag: value\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")

    def test_value_dressed(self):
        for char in ("​", "﻿", "\x01"):
            self.assert_front_refused(
                "---\ntitle: " + char + "!tag value\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")

    def test_quoted_key_with_space_before_construct(self):
        self.assert_front_refused(
            '---\n" !tag title": value\n---\n' + BODY,
            "IMPORT_VALIDATION_FAILED")


class Test032BracketAtKey(ImportBase):
    def test_key_positions(self):
        for block in (
                "[abc title: value",
                "title: fine\n[abc other: value",
                "title: fine\n{abc other: value",
                '"[abc": value',
                "title: fine\n  [def: ghi"):
            self.assert_front_refused(
                "---\n" + block + "\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")


class Test033NumericWrittenFormInContainers(ImportBase):
    def test_container_positions(self):
        for block in (
                '{"k": [1.' + "0" * 4196 + "]}",
                '{"k": [1e' + "9" * 4196 + "]}",
                '{"k": {"n": 2.' + "5" * 4196 + "}}",
                '{"k": {"n": ' + "9" * 5000 + "}}",
                '{"k": [' + "9" * 5000 + "]}"):
            self.assert_front_refused(
                "---\n" + block + "\n---\n" + BODY, "LIMIT_EXCEEDED")


class Test034ResolverPreparedSet(ImportBase):
    def batch_a(self):
        path = self.temp_file(sheet_text({
            1: "Batch A first answer text.",
            2: "Batch A second answer text."}), "a.txt")
        return self.prepare_sheet(
            path, answer_id_prefix="ans-{sequence}",
            answer_sequence_base=41)

    def test_later_batch_admits_distinct_answer_on_supplied_standing_combination(self):
        """Contract C2 as relaxed under the settled rule, on the
        worksheet preparation surface; a later batch slot
        holding a distinct answer for the same round, same
        normalised engine label, same query, and same
        captured_on as a supplied standing record prepared
        by an earlier batch is admitted as a new record
        under its own identity, at the one worksheet import
        call for the sheet, and the supplied standing
        records stand unchanged. This method stood as the
        later batch pin for the settled detection rule, whose refusal
        message supplied identity pin lapses with the
        refusal itself under the ruling."""
        records_a = self.batch_a()
        standing_before = [dict(record) for record in records_a]
        path = self.temp_file(sheet_text({
            1: "Batch B first answer text.",
            2: "Batch B second answer text.",
            3: "Batch B conflicting answer text."},
            dates={1: "2026-11-08", 2: "2026-11-09",
                   3: "2026-11-10"}), "b.txt")
        records = self.prepare_sheet(
            path, standing_records=records_a,
            answer_id_prefix="ans-{sequence}",
            answer_sequence_base=100)
        self.assertIsInstance(records, list)
        self.assertEqual(len(records), 3)
        third = records[2]
        self.assertEqual(third["answer_text"],
                         "Batch B conflicting answer text.")
        self.assertEqual(third["captured_on"], "2026-11-10")
        expected_hash = hashlib.sha256(
            "Batch B conflicting answer text.".encode(
                "utf-8")).hexdigest()
        self.assertEqual(third["content_hash"], expected_hash)
        self.assertNotEqual(third["content_hash"],
                            records_a[0]["content_hash"])
        self.assertEqual(third["product"], "Acme Ledger")
        self.assertEqual(third["round"], "round-1")
        self.assertEqual(third["query"], Q1)
        self.assertEqual(third["kind"], "real_sample")
        self.assertEqual(third["captured_on"],
                         records_a[0]["captured_on"])
        self.assertEqual(third["engine_label_normalised"],
                         "engine a")
        self.assertEqual(third["answer_id"], "ans-{sequence}-3")
        self.assertEqual(len(records_a), 2)
        for standing, before in zip(records_a, standing_before):
            for field in ("answer_id", "captured_on",
                          "answer_text", "content_hash"):
                self.assertEqual(standing[field], before[field])

    def test_own_batch_admits_second_distinct_answer(self):
        """The settled detection rule own batch control as superseded under
        the settled rule; a second filled slot holding a distinct
        answer for the same round, same engine label, same
        query, and same captured_on as an earlier slot this
        same preparation itself prepared is admitted as a
        new record under its own identity, and the earlier
        slot's record stands beside it unchanged. The
        identities the module surface returns carry the
        marker form itself, so no resolved identity stands
        for this shape, and no refusal stands either. This
        method stood as the own batch control for
        the settled detection rule, whose refusal and resolved identity
        pins lapse with the refusal itself under the
        ruling."""
        path = self.temp_file(sheet_text({
            1: "First worksheet answer text.",
            2: "Second conflicting worksheet answer."},
            dates={1: "2026-11-10", 2: "2026-11-10"}), "own.txt")
        records = self.prepare_sheet(
            path, answer_id_prefix="ans-{sequence}",
            answer_sequence_base=41)
        self.assertIsInstance(records, list)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["answer_text"],
                         "First worksheet answer text.")
        self.assertEqual(records[1]["answer_text"],
                         "Second conflicting worksheet answer.")
        first_hash = hashlib.sha256(
            "First worksheet answer text.".encode(
                "utf-8")).hexdigest()
        second_hash = hashlib.sha256(
            "Second conflicting worksheet answer.".encode(
                "utf-8")).hexdigest()
        self.assertNotEqual(records[0]["content_hash"],
                            records[1]["content_hash"])
        self.assertEqual(records[0]["content_hash"], first_hash)
        self.assertEqual(records[1]["content_hash"], second_hash)
        self.assertNotEqual(records[0]["answer_id"],
                            records[1]["answer_id"])
        self.assertEqual(records[0]["answer_id"],
                         "ans-{sequence}-1")
        self.assertEqual(records[1]["answer_id"],
                         "ans-{sequence}-2")


class Test035SingleBucketCost(ImportBase):
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
        base = date(2020, 1, 1)
        for index in range(1, count + 1):
            captured = (base + timedelta(days=index)).isoformat()
            lines.append(
                "slot %d: query= %s engine_label= Engine A "
                "kind= real_sample captured_on= %s "
                "capture_method= manual copy" % (index, Q1, captured))
            lines.append("Answer body number %d standing here." % index)
        return "\n".join(lines) + "\n"

    def test_single_bucket_inside_backstop_shape(self):
        path = self.temp_file(self.big_sheet(1500), "big.txt")
        start = time.monotonic()
        records = self.prepare_sheet(path)
        elapsed = time.monotonic() - start
        self.assertEqual(len(records), 1500)
        self.assertLess(elapsed, 6.0)

    def test_same_bucket_judgements_hold(self):
        """The settled detection rule judgements companion, as ruled in part
        under the settled rule; inside one comparison bucket on the
        worksheet route, an equal content slot stands refused
        as a duplicate whatever its capture date does, and a
        distinct content slot for the same round, same
        normalised engine label, same query, and same
        captured_on as an earlier slot of the same sheet is
        admitted as a second record beside the first, at the
        one worksheet call for the sheet."""
        path = self.temp_file(sheet_text({
            1: "Same answer text standing here.",
            2: "Same answer text standing here."},
            dates={1: "2026-11-10", 2: "2026-11-11"}), "dup.txt")
        with self.assertRaises(Exception) as caught:
            self.prepare_sheet(path)
        self.assertEqual(token_of(caught.exception), "DUPLICATE_IMPORT")
        path = self.temp_file(sheet_text({
            1: "First answer text standing here.",
            2: "Second answer text standing here."},
            dates={1: "2026-11-10", 2: "2026-11-10"}), "con.txt")
        records = self.prepare_sheet(path)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["answer_text"],
                         "First answer text standing here.")
        self.assertEqual(records[1]["answer_text"],
                         "Second answer text standing here.")
        first_hash = hashlib.sha256(
            "First answer text standing here.".encode(
                "utf-8")).hexdigest()
        second_hash = hashlib.sha256(
            "Second answer text standing here.".encode(
                "utf-8")).hexdigest()
        self.assertNotEqual(records[0]["content_hash"],
                            records[1]["content_hash"])
        self.assertEqual(records[0]["content_hash"], first_hash)
        self.assertEqual(records[1]["content_hash"], second_hash)


class Test067TagConstructWhole(ImportBase):
    def test_line_form_positions(self):
        for block in (
                "title: hello &anchor",
                "title: hello *alias",
                "title: hello %YAML",
                "title: |\n  folded body line",
                "title: >\n  folded body line",
                "title &anchor: value"):
            self.assert_front_refused(
                "---\n" + block + "\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")

    def test_json_form_whole(self):
        for block in (
                '{"title": "&anchor hello"}',
                '{"&anchor title": "x"}',
                '{"title": "!tag hello"}',
                '{"title": "*alias"}',
                '{"title": "%directive"}',
                '{"outer": {"inner": "&anchor"}}'):
            self.assert_front_refused(
                "---\n" + block + "\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")

    def test_plain_forms_hold(self):
        body, had = import_module.extract_front_matter(
            "---\ntitle: Fish and Chips\n---\n" + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)
        body, had = import_module.extract_front_matter(
            '---\n{"title": "Fish and Chips"}\n---\n' + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)


if __name__ == "__main__":
    unittest.main()
