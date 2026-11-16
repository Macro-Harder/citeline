"""Step 17 round 12 fix seat F4 tests: import family.

Test first pins for register entries S17-R12-006,
S17-R12-007, and S17-R12-008, from
design/audit/step-17-r12-findings-register.md, as
dispositioned in design/audit/step-17-r12-disposition.md
Section 3 and ruling (e).
"""

import json
import tempfile
import unicodedata
import unittest
from pathlib import Path

from citeline import probe_import as import_module

AUDIT_DATE = "2026-11-13"
PRODUCT = "Acme Ledger"
Q1 = "What is Acme Ledger?"
ROUND = "round-1"
BODY = "A plain answer body standing here."


def token_of(exc):
    return getattr(exc, "error_value", None) or ""


class ImportBase(unittest.TestCase):
    def temp_file(self, data, name="answer.txt"):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = root / name
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(data, encoding="utf-8")
        return path

    def prepare_file(self, path, **extra):
        kwargs = {
            "answer_file": str(path), "product": PRODUCT,
            "round": ROUND, "engine_label": "Engine A", "query": Q1,
            "kind": "real_sample", "captured_on": "2026-11-10",
            "capture_method": "manual copy", "audit_date": AUDIT_DATE,
            "query_set": [Q1],
        }
        kwargs.update(extra)
        return import_module.prepare_import(**kwargs)

    def assert_front_refused(self, text, token):
        with self.assertRaises(Exception) as caught:
            import_module.extract_front_matter(text)
        self.assertEqual(token_of(caught.exception), token)

    def assert_front_passes(self, text):
        body, had = import_module.extract_front_matter(text)
        self.assertTrue(had)
        self.assertEqual(body, BODY)

    def assert_route_refused_archive(self, raw):
        path = self.temp_file(raw)
        with self.assertRaises(Exception) as caught:
            self.prepare_file(path)
        self.assertEqual(
            token_of(caught.exception), "IMPORT_VALIDATION_FAILED")

    def assert_route_imports(self, raw):
        path = self.temp_file(raw)
        record = self.prepare_file(path)
        self.assertEqual(record["answer_text"], raw.decode("utf-8"))

    def form(self, raw):
        return import_module.check11_form(
            raw, raw.decode("utf-8", errors="replace"))


MN_MARKS = tuple(chr(point) for point in (
    0x0483, 0x0591, 0x064B, 0x0670, 0x06D6,
    0x20D0, 0x3099, 0xFE20, 0x1AB0, 0x1DC0))


class Test006CombiningMarksOutsideCuredRange(ImportBase):
    def test_marks_stand_as_category_mn(self):
        for mark in MN_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                self.assertEqual(unicodedata.category(mark), "Mn")

    def test_line_form_value_ampersand_marks_refused(self):
        for mark in MN_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                self.assert_front_refused(
                    "---\ntitle: x.&" + mark + "a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_line_form_value_other_constructs_marks_refused(self):
        for construct in ("!", "*", "%"):
            for mark in MN_MARKS:
                with self.subTest(
                        construct=construct, mark=hex(ord(mark))):
                    self.assert_front_refused(
                        "---\ntitle: x." + construct + mark
                        + "a\n---\n" + BODY,
                        "IMPORT_VALIDATION_FAILED")

    def test_json_form_value_marks_refused(self):
        for mark in MN_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                block = json.dumps({"title": "x.&" + mark + "a"})
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_line_form_key_marks_refused(self):
        for mark in MN_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                self.assert_front_refused(
                    "---\nx.&" + mark + "a: abc\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_json_form_key_marks_refused(self):
        for mark in MN_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                block = json.dumps({"x.&" + mark + "a": "v"})
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_controls_hold(self):
        self.assert_front_refused(
            "---\ntitle: x.&́a\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        for mark in ("ؐ", "︀"):
            with self.subTest(mark=hex(ord(mark))):
                self.assert_front_refused(
                    "---\ntitle: x.&" + mark + "a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")
        for follower in (".", "+", "$", "~", ";", "/", "=", "@",
                         "^", "`", "‿"):
            with self.subTest(follower=repr(follower)):
                self.assert_front_refused(
                    "---\ntitle: x.&" + follower + "a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")
        self.assert_front_passes(
            "---\ntitle: plain text here\n---\n" + BODY)


def newc_field(value):
    return ("%08x" % value).encode("ascii")


def newc_bytes(signature=b"070701", name=b"member.txt\x00",
               content=b"", check=b"00000000"):
    header = (
        signature + newc_field(1) + newc_field(0o100644)
        + newc_field(0) + newc_field(0) + newc_field(1)
        + newc_field(0) + newc_field(len(content))
        + newc_field(0) + newc_field(0) + newc_field(0)
        + newc_field(0) + newc_field(len(name)) + check)
    return header + name + content


def padded_newc(name_text, content, signature=b"070702",
                check=None):
    name = name_text + b"\x00"
    if check is None:
        if signature == b"070702":
            check = ("%08x" % sum(content)).encode("ascii")
        else:
            check = b"00000000"
    header = (
        signature + newc_field(1) + newc_field(0o100644)
        + newc_field(0) + newc_field(0) + newc_field(1)
        + newc_field(0) + newc_field(len(content))
        + newc_field(0) + newc_field(0) + newc_field(0)
        + newc_field(0) + newc_field(len(name)) + check)
    pad = (-(110 + len(name))) % 4
    return header + name + b"\x00" * pad + content


def truncated_newc(name_text, direct_bytes, check_value,
                   file_size=4):
    name = name_text + b"\x00"
    check = ("%08x" % check_value).encode("ascii")
    header = (
        b"070702" + newc_field(1) + newc_field(0o100644)
        + newc_field(0) + newc_field(0) + newc_field(1)
        + newc_field(0) + newc_field(file_size)
        + newc_field(0) + newc_field(0) + newc_field(0)
        + newc_field(0) + newc_field(len(name)) + check)
    return header + name + direct_bytes


class Test007TruncatedPaddedCheckSum(ImportBase):
    def test_name_size_three_check_zero_reads_as_text(self):
        raw = truncated_newc(b"ab", bytes((10, 20, 30, 0)), 0)
        self.assertEqual(len(raw), 117)
        self.assertIsNone(self.form(raw))

    def test_name_size_three_check_zero_imports_at_route(self):
        raw = truncated_newc(b"ab", bytes((10, 20, 30, 0)), 0)
        self.assert_route_imports(raw)

    def test_name_size_three_check_seven_reads_as_text(self):
        raw = truncated_newc(b"ab", bytes((10, 20, 30, 7)), 7)
        self.assertIsNone(self.form(raw))

    def test_name_size_three_check_seven_imports_at_route(self):
        raw = truncated_newc(b"ab", bytes((10, 20, 30, 7)), 7)
        self.assert_route_imports(raw)

    def test_name_size_five_check_ninety_reads_as_text(self):
        raw = truncated_newc(b"abcd", bytes((10, 20, 30, 40)), 90)
        self.assertIsNone(self.form(raw))

    def test_name_size_four_truncated_sum_reads_as_text(self):
        raw = truncated_newc(b"xyz", bytes((1, 2, 3, 4)), 7)
        self.assertIsNone(self.form(raw))

    def test_controls_hold(self):
        content = b"hello cpio"
        for name_text in (b"a", b"xy", b"xyz", b"wxyz", b"abcde",
                          b"abcdef", b"member.txt"):
            with self.subTest(name=name_text):
                raw = padded_newc(name_text, content)
                self.assertEqual(self.form(raw), "archive")
        raw = newc_bytes(
            signature=b"070702", content=content,
            check=("%08x" % sum(content)).encode("ascii"))
        self.assertEqual(self.form(raw), "archive")
        raw = padded_newc(b"xy", content, signature=b"070701")
        self.assertEqual(self.form(raw), "archive")
        raw = padded_newc(b"xy", content, check=b"deadbeef")
        self.assertIsNone(self.form(raw))
        whole = truncated_newc(b"ab", bytes((10, 20, 30, 7)), 67)
        whole = whole[:113] + b"\x00" * 3 + bytes((10, 20, 30, 7))
        self.assertEqual(len(whole), 120)
        self.assertEqual(self.form(whole), "archive")
        self.assert_route_refused_archive(whole)


FURTHER_OPENINGS = ("?", "\\", "(", ")", "<", ":")


class Test008OpeningsPastCuredSet(ImportBase):
    def test_line_form_value_ampersand_openings_refused(self):
        for opening in FURTHER_OPENINGS:
            with self.subTest(opening=repr(opening)):
                self.assert_front_refused(
                    "---\ntitle: x.&" + opening + "a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_line_form_value_other_constructs_refused(self):
        for construct in ("!?", "!\\", "!<", "*?", "*(", "%:",
                          "%\\"):
            with self.subTest(construct=construct):
                self.assert_front_refused(
                    "---\ntitle: x." + construct + "a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_json_form_value_openings_refused(self):
        for opening in FURTHER_OPENINGS:
            with self.subTest(opening=repr(opening)):
                block = json.dumps({"title": "x.&" + opening + "a"})
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_line_form_key_openings_refused(self):
        for opening in ("?", "\\", "(", ")", "<"):
            with self.subTest(opening=repr(opening)):
                self.assert_front_refused(
                    "---\nx.&" + opening + "a: abc\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_json_form_key_openings_refused(self):
        for opening in FURTHER_OPENINGS:
            with self.subTest(opening=repr(opening)):
                block = json.dumps({"x.&" + opening + "a": "v"})
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_controls_hold(self):
        for follower in (".", "+", "$", "~", ";", "/", "=", "@",
                         "^", "`", "́", "‿"):
            with self.subTest(follower=repr(follower)):
                self.assert_front_refused(
                    "---\ntitle: x.&" + follower + "a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")
        self.assert_front_refused(
            "---\ntitle: x.&1\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        for follower in ("'", "#", ",", "|", '"'):
            with self.subTest(follower=repr(follower)):
                self.assert_front_passes(
                    "---\ntitle: x.&" + follower + "a\n---\n" + BODY)
        self.assert_front_passes(
            "---\ntitle: plain text here\n---\n" + BODY)


if __name__ == "__main__":
    unittest.main()
