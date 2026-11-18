"""Import family.

Test first pins for register, 024, 025, 026, 027, 028, 029,
030, 031, 032, and 051, from the register and the source
papers the register paper and the register paper (entry 051
and the merged limbs of entries 024 and 032)."""

import gzip
import hashlib
import io
import json
import tarfile
import tempfile
import time
import unittest
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


def sheet_text(bodies, dates=None):
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

    def form(self, raw):
        return import_module.check11_form(
            raw, raw.decode("utf-8", errors="replace"))


class Test023HeadSetSeparatorDressings(ImportBase):
    def forged_line(self, duplicate_marker):
        return (
            "slot 2: query= %s engine_label= Forged Engine %s "
            "kind= real_sample captured_on= 2026-11-11 "
            "capture_method= manual copy" % (Q1, duplicate_marker))

    def test_head_chars_on_both_sides_of_equals(self):
        for char in ("\u200b", "\ufeff", "\u2065", "\u034f"):
            line = self.forged_line(
                "capture_method" + char + "=" + char + "manual copy")
            text = sheet_text({1: "First answer text.\n" + line})
            sheet = import_module.parse_worksheet(text)
            self.assertEqual(len(sheet["slots"]), 1, repr(char))

    def test_head_char_inside_field_name(self):
        line = self.forged_line("capture_\u200bmethod= manual copy")
        text = sheet_text({1: "First answer text.\n" + line})
        sheet = import_module.parse_worksheet(text)
        self.assertEqual(len(sheet["slots"]), 1)

    def test_tab_and_plain_duplicate_controls_hold(self):
        for marker in ("capture_method= manual copy",
                       "capture_method\t= manual copy"):
            line = self.forged_line(marker)
            text = sheet_text({1: "First answer text.\n" + line})
            sheet = import_module.parse_worksheet(text)
            self.assertEqual(len(sheet["slots"]), 1, marker)


def odc_bytes():
    def field(value, width):
        text = "%0*o" % (width - 1, value)
        return text.encode("ascii") + b"\x00"

    name = b"member.txt\x00"
    content = b"hello cpio"
    header = (
        b"070707" + field(0, 6) + field(1, 6) + field(0o644, 6)
        + field(0, 6) + field(0, 6) + field(1, 6) + field(0, 6)
        + field(0, 11) + field(len(name), 6)
        + field(len(content), 11))
    trailer_name = b"TRAILER!!!\x00"
    trailer = (
        b"070707" + field(0, 6) + field(0, 6) + field(0, 6)
        + field(0, 6) + field(0, 6) + field(1, 6) + field(0, 6)
        + field(0, 11) + field(len(trailer_name), 6) + field(0, 11))
    return header + name + content + trailer + trailer_name


class Test024OlderCpioForms(ImportBase):
    def test_odc_archive_reads_as_archive(self):
        self.assertEqual(self.form(odc_bytes()), "archive")

    def test_odc_signature_form_reads_as_archive(self):
        raw = b"070707" + b"\x00" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")

    def test_binary_cpio_reads_as_archive(self):
        raw = b"\xc7\x71" + b"\x00" * 60 + b"payload"
        self.assertEqual(self.form(raw), "archive")

    def test_newc_control_holds(self):
        raw = b"070701" + b"0" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")


class Test025HeaderJudgementBehindSignatures(ImportBase):
    def test_plain_text_opening_with_newc_signature(self):
        text = ("070701 was the code we used that day, and this "
                "plain answer stands as prose from there on.")
        self.assertIsNone(self.form(text.encode("utf-8")))
        self.assertIsNone(import_module.check11_form(
            text.encode("utf-8"), text))

    def test_plain_text_opening_with_cab_signature(self):
        text = ("MSCF is the heading of this plain answer, and "
                "the prose stands as prose from there on.")
        self.assertIsNone(self.form(text.encode("utf-8")))
        self.assertIsNone(import_module.check11_form(
            text.encode("utf-8"), text))

    def test_round5_signature_forms_still_read_as_archive(self):
        self.assertEqual(
            self.form(b"070701" + b"0" * 100 + b"payload"), "archive")
        self.assertEqual(
            self.form(b"070702" + b"0" * 100 + b"payload"), "archive")
        self.assertEqual(
            self.form(b"MSCF" + b"\x00" * 100 + b"payload"), "archive")


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


class Test026V7JudgementBeyondChecksum(ImportBase):
    def test_checksum_only_text_block_is_not_a_tar(self):
        block = bytearray(b"A" * 512)
        total = sum(block[:148]) + 8 * 0x20 + sum(block[156:512])
        block[148:156] = ("%06o\x00 " % total).encode("ascii")
        raw = bytes(block) + b"plain answer prose standing here"
        self.assertIsNone(self.form(raw))

    def test_real_v7_tar_control_holds(self):
        self.assertEqual(self.form(v7_tar_bytes()), "archive")

    def test_tarfile_built_ustar_control_holds(self):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w",
                          format=tarfile.USTAR_FORMAT) as archive:
            data = b"member text\n"
            info = tarfile.TarInfo("member.txt")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        self.assertEqual(self.form(buffer.getvalue()), "archive")


class Test027GzipBehindHeadMaterial(ImportBase):
    def gzip_bytes(self):
        buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as stream:
            stream.write(b"hello gzip")
        return buffer.getvalue()

    def test_plain_gzip_control_holds(self):
        self.assertEqual(self.form(self.gzip_bytes()), "archive")

    def test_gzip_behind_head_material(self):
        data = self.gzip_bytes()
        for char in ("\ufeff", "\u200b", "\u2028", "\u2065", " ", "\n"):
            raw = char.encode("utf-8") + data
            self.assertEqual(self.form(raw), "archive", repr(char))


class Test028DuplicateKeyOnJudgedKey(ImportBase):
    def test_dressed_second_key_refused(self):
        for second in ("\ufefftitle", "\u200btitle", "\u2065title",
                       "title\u200b"):
            self.assert_front_refused(
                "---\ntitle: one\n" + second + ": two\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")

    def test_plain_and_quoted_duplicate_controls_hold(self):
        self.assert_front_refused(
            "---\ntitle: one\ntitle: two\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        self.assert_front_refused(
            '---\ntitle: one\n"title": two\n---\n' + BODY,
            "IMPORT_VALIDATION_FAILED")


class Test029TagConstructSpellings(ImportBase):
    def test_reversed_block_scalar_orders(self):
        for block in ("title: >2-", "title: |9+"):
            self.assert_front_refused(
                "---\n" + block + "\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")

    def test_cured_block_scalar_order_control_holds(self):
        for block in ("title: >-2", "title: |+9"):
            self.assert_front_refused(
                "---\n" + block + "\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")

    def test_angle_spellings_opening_on_uri_characters(self):
        for block in ("title: <1tag>", "title: <-tag>",
                      "title: <_tag>", "<1tag>: value"):
            self.assert_front_refused(
                "---\n" + block + "\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")

    def test_angle_letter_control_holds(self):
        self.assert_front_refused(
            "---\ntitle: <tag>\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")

    def test_json_form_spellings(self):
        for block in ('{"title": "<1tag>"}', '{"title": ">2-"}'):
            self.assert_front_refused(
                "---\n" + block + "\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")


class Test030FenceOnCompletedHeadPredicate(ImportBase):
    def test_opening_fence_with_trailing_head_material(self):
        for fence in ("---\u200b", "---\ufeff"):
            body, had = import_module.extract_front_matter(
                fence + "\ntitle: one\n---\n" + BODY)
            self.assertTrue(had, repr(fence))
            self.assertEqual(body, BODY)

    def test_plain_fence_control_holds(self):
        body, had = import_module.extract_front_matter(
            "---\ntitle: one\n---\n" + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)


class Test031StringInsideContainerMeasure(ImportBase):
    def test_strings_inside_a_list_stand_accepted(self):
        for value in ("\n" * 3000, '"' * 3000, "\x01" * 2000):
            block = json.dumps({"k": [value]})
            body, had = import_module.extract_front_matter(
                "---\n" + block + "\n---\n" + BODY)
            self.assertTrue(had)
            self.assertEqual(body, BODY)

    def test_whole_value_string_control_holds(self):
        block = json.dumps({"k": "\n" * 3000})
        body, had = import_module.extract_front_matter(
            "---\n" + block + "\n---\n" + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)

    def test_number_inside_container_control_holds(self):
        block = '{"k": [1.' + "0" * 4196 + "]}"
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY, "LIMIT_EXCEEDED")

    def test_long_string_inside_container_still_refused(self):
        block = json.dumps({"k": ["x" * 5000]})
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY, "LIMIT_EXCEEDED")


class Test032WorksheetOverflowCost(ImportBase):
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

    def test_overflow_shape_inside_backstop(self):
        standing = [{
            "kind": ["real_sample"],
            "engine_label_normalised": "engine a",
            "query": Q1,
            "content_hash": "hash-%d" % index,
            "captured_on": "2026-11-10",
        } for index in range(4000)]
        path = self.temp_file(self.big_sheet(800), "big.txt")
        start = time.monotonic()
        records = self.prepare_sheet(path, standing_records=standing)
        elapsed = time.monotonic() - start
        self.assertEqual(len(records), 800)
        self.assertLess(elapsed, 3.0)

    def test_unhashable_kind_records_never_match(self):
        standing = [{
            "kind": ["real_sample"],
            "engine_label_normalised": "engine a",
            "query": Q1,
            "content_hash": "unused",
            "captured_on": "2026-11-10",
        }]
        path = self.temp_file(sheet_text({1: "First answer text."}))
        records = self.prepare_sheet(path, standing_records=standing)
        self.assertEqual(len(records), 1)

    def test_second_answer_by_date_with_unhashable_hash_admitted(self):
        """Contract C2 as relaxed under R19-048, on the worksheet
        preparation route; a slot holding a distinct answer for
        the same round, same normalised engine label, same query,
        and same captured_on as a standing record whose content
        hash stands in an unhashable form is admitted as a new
        record, at one import call for the sheet, the standing
        record stands neither matched as a duplicate nor
        overwritten, and no error of any kind stands raised on
        the unhashable form. This method stood as the date index
        correctness control of S17-R6-032, whose contradiction
        outcome lapses under the ruling while its no crash, no
        false match substance stands re-pinned here in admitted
        form."""
        body_text = "First answer text."
        standing = [{
            "kind": "real_sample",
            "engine_label_normalised": "engine a",
            "query": Q1,
            "content_hash": ["unhashable"],
            "captured_on": "2026-11-10",
            "answer_id": "ans-standing-1",
        }]
        path = self.temp_file(sheet_text({1: body_text}))
        records = self.prepare_sheet(path, standing_records=standing)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["answer_text"], "First answer text.")
        self.assertEqual(
            record["content_hash"],
            hashlib.sha256(body_text.encode("utf-8")).hexdigest())
        self.assertNotEqual(record["content_hash"], ["unhashable"])
        self.assertEqual(record["product"], "Acme Ledger")
        self.assertEqual(record["round"], "round-1")
        self.assertEqual(record["query"], Q1)
        self.assertEqual(record["kind"], "real_sample")
        self.assertEqual(record["captured_on"], "2026-11-10")
        self.assertEqual(record["engine_label_normalised"], "engine a")
        self.assertEqual(standing[0]["kind"], "real_sample")
        self.assertEqual(standing[0]["engine_label_normalised"],
                         "engine a")
        self.assertEqual(standing[0]["query"], Q1)
        self.assertEqual(standing[0]["content_hash"], ["unhashable"])
        self.assertEqual(standing[0]["captured_on"], "2026-11-10")
        self.assertEqual(standing[0]["answer_id"], "ans-standing-1")
        self.assertEqual(standing, [{
            "kind": "real_sample",
            "engine_label_normalised": "engine a",
            "query": Q1,
            "content_hash": ["unhashable"],
            "captured_on": "2026-11-10",
            "answer_id": "ans-standing-1",
        }])

    def test_duplicate_and_contradiction_controls_hold(self):
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
        with self.assertRaises(Exception) as caught:
            self.prepare_sheet(path)
        self.assertEqual(token_of(caught.exception),
                         "CONTRADICTORY_IMPORT")


class Test051FlowPositions(ImportBase):
    def test_helper_flow_positions(self):
        for text in ("[&a, x]", "[*a]", "value [&anchor rest]",
                     "[!tag, x]"):
            self.assertTrue(
                import_module._holds_tag_construct(text), text)

    def test_helper_plain_controls_hold(self):
        self.assertFalse(
            import_module._holds_tag_construct("[plain, list]"))
        self.assertTrue(import_module._holds_tag_construct("&b"))
        self.assertTrue(import_module._holds_tag_construct("{k: &a}"))

    def test_line_and_json_forms_refuse_flow_constructs(self):
        self.assert_front_refused(
            "---\ntitle: [&a, x]\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        self.assert_front_refused(
            '---\n{"title": "[&a, x]"}\n---\n' + BODY,
            "IMPORT_VALIDATION_FAILED")


if __name__ == "__main__":
    unittest.main()
