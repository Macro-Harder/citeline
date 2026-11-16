"""Step 17 round 11 fix seat F4 tests: import family.

Test first pins for register entries S17-R11-006,
S17-R11-007, S17-R11-008, S17-R11-009, S17-R11-010,
S17-R11-011, and S17-R11-014, from
design/audit/step-17-r11-findings-register.md, as
dispositioned in design/audit/step-17-r11-disposition.md
Section 3 and ruling (e).
"""

import hashlib
import json
import tempfile
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


def odc_field(value, width):
    text = "%0*o" % (width - 1, value)
    return text.encode("ascii") + b"\x00"


def odc_header(name_size, file_size):
    return (
        b"070707" + odc_field(0, 6) + odc_field(1, 6)
        + odc_field(0o644, 6) + odc_field(0, 6) + odc_field(0, 6)
        + odc_field(1, 6) + odc_field(0, 6) + odc_field(0, 11)
        + odc_field(name_size, 6) + odc_field(file_size, 11))


def odc_bytes():
    name = b"member.txt\x00"
    content = b"hello cpio"
    return odc_header(len(name), len(content)) + name + content


def odc_with_name(name_bytes, file_size=0):
    return odc_header(len(name_bytes), file_size) + name_bytes \
        + b"plain prose standing behind it"


class Test006OdcNameClosedByFirstNul(ImportBase):
    def test_name_size_two_two_nul_bytes_reads_as_text(self):
        self.assertIsNone(self.form(odc_with_name(b"\x00\x00")))

    def test_name_size_two_two_nul_bytes_imports_at_route(self):
        self.assert_route_imports(odc_with_name(b"\x00\x00"))

    def test_name_size_three_opening_nul_then_letter_reads_as_text(
            self):
        self.assertIsNone(self.form(odc_with_name(b"\x00x\x00")))

    def test_name_size_four_letter_past_first_nul_reads_as_text(self):
        self.assertIsNone(self.form(odc_with_name(b"a\x00b\x00")))

    def test_name_size_four_letter_past_first_nul_imports_at_route(
            self):
        self.assert_route_imports(odc_with_name(b"a\x00b\x00"))

    def test_name_size_five_letter_past_first_nul_reads_as_text(self):
        self.assertIsNone(self.form(odc_with_name(b"ab\x00c\x00")))

    def test_controls_hold(self):
        self.assertEqual(self.form(odc_bytes()), "archive")
        raw = b"070707" + b"\x00" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")
        self.assertEqual(
            self.form(odc_with_name(b"ab\x00\x00")), "archive")
        self.assertIsNone(self.form(odc_header(0, 0)))
        self.assertIsNone(self.form(odc_with_name(b"prose")))


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


class Test007NewcNamePastFirstTerminator(ImportBase):
    def test_name_letter_past_first_nul_reads_as_text(self):
        raw = newc_bytes(name=b"a\x00b\x00") \
            + b"plain prose standing behind the header"
        self.assertIsNone(self.form(raw))

    def test_name_letter_past_first_nul_imports_at_route(self):
        raw = newc_bytes(name=b"a\x00b\x00") \
            + b"plain prose standing behind the header"
        self.assert_route_imports(raw)

    def test_name_size_five_letter_past_first_nul_reads_as_text(self):
        raw = newc_bytes(name=b"ab\x00c\x00") \
            + b"plain prose standing behind the header"
        self.assertIsNone(self.form(raw))

    def test_controls_hold(self):
        self.assertEqual(self.form(newc_bytes()), "archive")
        self.assertEqual(
            self.form(newc_bytes(name=b"ab\x00\x00")), "archive")
        raw = newc_bytes(name=b"\x00x\x00") \
            + b"plain prose standing behind the header"
        self.assertIsNone(self.form(raw))
        raw = b"070701" + b"0" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")


def cab_bytes(cabinet_size, first_file_offset=0, folder_count=0,
              file_count=0, flags=0, tail=b""):
    raw = bytearray()
    raw += b"MSCF" + b"\x00" * 4
    raw += cabinet_size.to_bytes(4, "little")
    raw += b"\x00" * 4
    raw += first_file_offset.to_bytes(4, "little")
    raw += b"\x00" * 4
    raw += bytes((3, 1))
    raw += folder_count.to_bytes(2, "little")
    raw += file_count.to_bytes(2, "little")
    raw += flags.to_bytes(2, "little")
    raw += (0).to_bytes(2, "little")
    raw += (0).to_bytes(2, "little")
    raw += tail
    return bytes(raw)


def format_folder_entry():
    return (
        (36).to_bytes(4, "little") + (1).to_bytes(2, "little")
        + (0).to_bytes(2, "little"))


def format_file_entry():
    return (
        (4).to_bytes(4, "little") + (0).to_bytes(4, "little")
        + (0).to_bytes(2, "little") + (0).to_bytes(2, "little")
        + (0).to_bytes(2, "little") + (0).to_bytes(2, "little"))


def genuine_cab():
    return cab_bytes(
        68, first_file_offset=44, folder_count=1, file_count=1,
        tail=format_folder_entry() + format_file_entry()
        + b"datahere")


class Test008PinAllowancesPastPinForms(ImportBase):
    def test_newc_complete_header_check_letters_read_as_text(self):
        raw = newc_bytes(name=b"a\x00", check=b"zzzzzzzz") \
            + b"plain prose standing behind the header"
        self.assertIsNone(self.form(raw))

    def test_newc_complete_header_check_mixed_read_as_text(self):
        raw = newc_bytes(name=b"a\x00", check=b"0000000g") \
            + b"plain prose standing behind the header"
        self.assertIsNone(self.form(raw))

    def test_newc_complete_header_check_letters_import_at_route(self):
        raw = newc_bytes(name=b"a\x00", check=b"zzzzzzzz") \
            + b"plain prose standing behind the header"
        self.assert_route_imports(raw)

    def test_cab_size_zero_with_counts_prose_entries_read_as_text(
            self):
        raw = cab_bytes(
            0, first_file_offset=44, folder_count=1, file_count=1,
            tail=b"folderx!" + b"fileentryprose16")
        self.assertIsNone(self.form(raw))

    def test_cab_size_zero_with_counts_format_entries_read_as_text(
            self):
        raw = cab_bytes(
            0, first_file_offset=44, folder_count=1, file_count=1,
            tail=format_folder_entry() + format_file_entry())
        self.assertIsNone(self.form(raw))

    def test_cab_size_zero_folder_only_reads_as_text(self):
        raw = cab_bytes(
            0, first_file_offset=44, folder_count=1, file_count=0,
            tail=b"folderx!")
        self.assertIsNone(self.form(raw))

    def test_cab_size_zero_file_only_reads_as_text(self):
        raw = cab_bytes(
            0, first_file_offset=36, folder_count=0, file_count=1,
            tail=b"fileentryprose16")
        self.assertIsNone(self.form(raw))

    def test_cab_size_zero_with_counts_imports_at_route(self):
        raw = cab_bytes(
            0, first_file_offset=44, folder_count=1, file_count=1,
            tail=b"folderx!" + b"fileentryprose16")
        self.assert_route_imports(raw)

    def test_controls_hold(self):
        raw = b"070701" + b"0" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")
        raw = b"MSCF" + b"\x00" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")
        raw = newc_bytes(name=b"a\x00", check=b"DEADBEEF") \
            + b"plain prose standing behind the header"
        self.assertIsNone(self.form(raw))
        for size in (20, 34, 35):
            with self.subTest(size=size):
                raw = cab_bytes(size) + (
                    b"plain prose standing behind the header "
                    b"to pass the size the header states here")
                self.assertIsNone(self.form(raw))
        self.assertEqual(self.form(genuine_cab()), "archive")


class Test009CabFolderEntryPastCabinetSize(ImportBase):
    def test_folder_entry_partly_past_stated_size_reads_as_text(self):
        raw = cab_bytes(
            40, first_file_offset=44, folder_count=1, file_count=0,
            tail=format_folder_entry())
        self.assertIsNone(self.form(raw))

    def test_folder_entry_partly_past_stated_size_imports_at_route(
            self):
        raw = cab_bytes(
            40, first_file_offset=44, folder_count=1, file_count=0,
            tail=format_folder_entry())
        self.assert_route_imports(raw)

    def test_controls_hold(self):
        self.assertEqual(self.form(genuine_cab()), "archive")
        raw = b"MSCF" + b"\x00" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")
        raw = cab_bytes(
            60, first_file_offset=44, folder_count=1, file_count=1,
            tail=b"folderx!" + b"fileentryprose16")
        self.assertIsNone(self.form(raw))


NEW_FOLLOWERS = (
    ".", "+", "$", "~", ";", "/", "=", "@", "^", "`",
    "́", "‿",
)


class Test010ConstructFollowersPastCuredSet(ImportBase):
    def test_line_form_value_ampersand_followers_refused(self):
        for follower in NEW_FOLLOWERS:
            with self.subTest(follower=repr(follower)):
                self.assert_front_refused(
                    "---\ntitle: x.&" + follower + "a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_line_form_value_other_constructs_refused(self):
        for construct in ("!.", "!+", "*.", "*+", "%+", "%‿"):
            with self.subTest(construct=construct):
                self.assert_front_refused(
                    "---\ntitle: x." + construct + "a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_json_form_value_followers_refused(self):
        for follower in NEW_FOLLOWERS:
            with self.subTest(follower=repr(follower)):
                block = json.dumps({"title": "x.&" + follower + "a"})
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_line_form_key_followers_refused(self):
        for follower in (".", "+"):
            with self.subTest(follower=follower):
                self.assert_front_refused(
                    "---\nx.&" + follower + "a: abc\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_json_form_key_followers_refused(self):
        for follower in (".", "+"):
            with self.subTest(follower=follower):
                block = json.dumps({"x.&" + follower + "a": "v"})
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_controls_hold(self):
        self.assert_front_refused(
            "---\ntitle: x.&1\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        self.assert_front_refused(
            "---\ntitle: &.a\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        body, had = import_module.extract_front_matter(
            "---\ntitle: plain text here\n---\n" + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)


class HashAndReprRaise:
    """A form whose hash test raises a ValueError and whose
    repr raises a ValueError, its equality answering as one
    target value."""

    def __init__(self, target):
        self.target = target

    def __eq__(self, other):
        return other == self.target or (
            isinstance(other, HashAndReprRaise)
            and other.target == self.target)

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        raise ValueError("hash raises")

    def __repr__(self):
        raise ValueError("repr raises")


class StrReadingRaises(str):
    """A string form whose string reading raises a
    ValueError, its characters standing as the value it
    carries."""

    def __str__(self):
        raise ValueError("string reading raises")


class DateReprRaises:
    """A capture date form whose repr raises a ValueError,
    its equality answering false and its hash standing
    fixed."""

    def __eq__(self, other):
        return False

    def __ne__(self, other):
        return True

    def __hash__(self):
        return hash("citeline-date-repr-raises")

    def __repr__(self):
        raise ValueError("repr raises")


class BadHash:
    """Equal to one candidate string, with a hash raising
    a ValueError."""

    def __init__(self, target):
        self.target = target

    def __eq__(self, other):
        return other == self.target or (
            isinstance(other, BadHash)
            and other.target == self.target)

    def __hash__(self):
        raise ValueError("bad hash")

    def __repr__(self):
        return "BadHash(%r)" % (self.target,)


class WorksheetBase(ImportBase):
    def standing(self, field, value, body_text):
        record = {
            "kind": "real_sample",
            "engine_label_normalised": "engine a",
            "query": Q1,
            "content_hash": hashlib.sha256(
                body_text.encode("utf-8")).hexdigest(),
            "captured_on": "2026-11-09",
        }
        record[field] = value
        return [record]

    def assert_duplicate(self, field, value, body_text):
        path = self.temp_file(sheet_text({1: body_text}))
        with self.assertRaises(Exception) as caught:
            self.prepare_sheet(
                path, standing_records=self.standing(
                    field, value, body_text))
        self.assertEqual(
            token_of(caught.exception), "DUPLICATE_IMPORT", field)


class Test011KeyingReadingsAnswered(WorksheetBase):
    def test_kind_hash_and_repr_raising_answered(self):
        self.assert_duplicate(
            "kind", HashAndReprRaise("real_sample"),
            "First answer text.")

    def test_content_hash_hash_and_repr_raising_answered(self):
        body_text = "First answer text."
        body_hash = hashlib.sha256(
            body_text.encode("utf-8")).hexdigest()
        self.assert_duplicate(
            "content_hash", HashAndReprRaise(body_hash), body_text)

    def test_kind_string_reading_raising_answered(self):
        self.assert_duplicate(
            "kind", StrReadingRaises("real_sample"),
            "First answer text.")

    def test_capture_date_repr_raising_answered(self):
        self.assert_duplicate(
            "captured_on", DateReprRaises(), "First answer text.")

    def test_controls_hold(self):
        body_text = "First answer text."
        self.assert_duplicate(
            "kind", BadHash("real_sample"), body_text)
        record = {
            "kind": "real_sample",
            "engine_label_normalised": "engine a",
            "query": Q1,
            "content_hash": hashlib.sha256(
                body_text.encode("utf-8")).hexdigest(),
            "captured_on": "2026-11-09",
        }
        path = self.temp_file(sheet_text({1: body_text}))
        with self.assertRaises(Exception) as caught:
            self.prepare_sheet(path, standing_records=[record])
        self.assertEqual(token_of(caught.exception), "DUPLICATE_IMPORT")


class Test014PaddedGenuineNewcStreams(ImportBase):
    def test_padded_070702_reads_as_archive_at_every_residue(self):
        content = b"hello cpio"
        for name_text in (b"a", b"xy", b"xyz", b"wxyz",
                          b"member.txt"):
            with self.subTest(name=name_text):
                raw = padded_newc(name_text, content)
                self.assertEqual(self.form(raw), "archive")

    def test_padded_070702_at_name_size_three_refused_at_route(self):
        raw = padded_newc(b"xy", b"hello cpio")
        self.assert_route_refused_archive(raw)

    def test_padded_070702_at_name_size_eleven_refused_at_route(self):
        raw = padded_newc(b"member.txt", b"hello cpio")
        self.assert_route_refused_archive(raw)

    def test_controls_hold(self):
        content = b"hello cpio"
        raw = newc_bytes(
            signature=b"070702", content=content,
            check=("%08x" % sum(content)).encode("ascii"))
        self.assertEqual(self.form(raw), "archive")
        raw = padded_newc(b"xy", content, signature=b"070701")
        self.assertEqual(self.form(raw), "archive")
        raw = padded_newc(b"xy", content, check=b"deadbeef")
        self.assertIsNone(self.form(raw))
        raw = padded_newc(b"a", content, check=b"DEADBEEF")
        self.assertIsNone(self.form(raw))


if __name__ == "__main__":
    unittest.main()
