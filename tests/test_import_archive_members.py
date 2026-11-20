"""Import family.

Test first pins for register, and, from the register
and the source papers the register paper and the
register paper, as dispositioned in the register
paper Section 3 and rulings (h) and (i)."""

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


class Test005OdcMemberName(ImportBase):
    def test_name_size_zero_with_prose_behind_reads_as_text(self):
        raw = odc_header(0, 0) + b"plain prose standing behind it"
        self.assertIsNone(self.form(raw))

    def test_name_size_zero_imports_whole_at_the_route(self):
        raw = odc_header(0, 0) + b"plain prose standing behind it"
        path = self.temp_file(raw)
        record = self.prepare_file(path)
        self.assertEqual(record["answer_text"], raw.decode("utf-8"))

    def test_name_size_zero_at_exactly_76_bytes_reads_as_text(self):
        self.assertIsNone(self.form(odc_header(0, 0)))

    def test_name_size_one_holding_terminator_alone_reads_as_text(
            self):
        raw = odc_header(1, 0) + b"\x00" \
            + b"plain prose standing behind it"
        self.assertIsNone(self.form(raw))

    def test_name_size_one_holding_terminator_alone_imports_at_route(
            self):
        raw = odc_header(1, 0) + b"\x00" \
            + b"plain prose standing behind it"
        path = self.temp_file(raw)
        record = self.prepare_file(path)
        self.assertEqual(record["answer_text"], raw.decode("utf-8"))

    def test_name_size_one_holding_a_letter_reads_as_text(self):
        raw = odc_header(1, 0) + b"x" \
            + b"plain prose standing behind it"
        self.assertIsNone(self.form(raw))

    def test_name_size_five_prose_holding_no_nul_reads_as_text(self):
        raw = odc_header(5, 0) + b"prose" \
            + b" and further plain prose standing behind it"
        self.assertIsNone(self.form(raw))

    def test_name_size_five_prose_imports_whole_at_the_route(self):
        raw = odc_header(5, 0) + b"prose" \
            + b" and further plain prose standing behind it"
        path = self.temp_file(raw)
        record = self.prepare_file(path)
        self.assertEqual(record["answer_text"], raw.decode("utf-8"))

    def test_controls_hold(self):
        self.assertEqual(self.form(odc_bytes()), "archive")
        raw = b"070707" + b"\x00" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")
        widths = (6, 6, 6, 6, 6, 6, 6, 11, 6, 11)
        fields = b"".join(
            b" " * (width - 1) + b"\x00" for width in widths)
        raw = b"070707" + fields + b"plain prose standing after it"
        self.assertIsNone(self.form(raw))
        raw = odc_header(0o7777, 0o77777) + b"short prose"
        self.assertIsNone(self.form(raw))


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


class Test006NewcCheckAndNameAndCabSize(ImportBase):
    def test_newc_check_value_one_under_070701_reads_as_text(self):
        raw = newc_bytes(name=b"a\x00", check=b"00000001") \
            + b"plain prose standing behind the header"
        self.assertIsNone(self.form(raw))

    def test_newc_check_deadbeef_under_070701_reads_as_text(self):
        raw = newc_bytes(name=b"a\x00", check=b"deadbeef") \
            + b"plain prose standing behind the header"
        self.assertIsNone(self.form(raw))

    def test_newc_check_apart_from_data_sum_under_070702_reads_as_text(
            self):
        raw = newc_bytes(
            signature=b"070702", content=b"hello cpio",
            check=b"deadbeef")
        self.assertIsNone(self.form(raw))

    def test_newc_check_form_imports_whole_at_the_route(self):
        raw = newc_bytes(name=b"a\x00", check=b"00000001") \
            + b"plain prose standing behind the header"
        path = self.temp_file(raw)
        record = self.prepare_file(path)
        self.assertEqual(record["answer_text"], raw.decode("utf-8"))

    def test_newc_name_opening_on_terminator_size_three_reads_as_text(
            self):
        raw = newc_bytes(name=b"\x00x\x00") \
            + b"plain prose standing behind the header"
        self.assertIsNone(self.form(raw))

    def test_newc_name_opening_on_terminator_size_two_reads_as_text(
            self):
        raw = newc_bytes(name=b"\x00\x00") \
            + b"plain prose standing behind the header"
        self.assertIsNone(self.form(raw))

    def test_newc_name_opening_on_terminator_imports_at_route(self):
        raw = newc_bytes(name=b"\x00x\x00") \
            + b"plain prose standing behind the header"
        path = self.temp_file(raw)
        record = self.prepare_file(path)
        self.assertEqual(record["answer_text"], raw.decode("utf-8"))

    def test_cab_cabinet_size_below_its_header_reads_as_text(self):
        for size in (20, 34, 35):
            with self.subTest(size=size):
                raw = cab_bytes(size) + (
                    b"plain prose standing behind the header "
                    b"to pass the size the header states here")
                self.assertIsNone(self.form(raw))

    def test_cab_cabinet_size_below_its_header_imports_at_route(self):
        raw = cab_bytes(20) + (
            b"plain prose standing behind the header "
            b"to pass the size the header states here")
        path = self.temp_file(raw)
        record = self.prepare_file(path)
        self.assertEqual(record["answer_text"], raw.decode("utf-8"))

    def test_controls_hold(self):
        content = b"hello cpio"
        raw = newc_bytes(content=content)
        self.assertEqual(self.form(raw), "archive")
        raw = newc_bytes(
            signature=b"070702", content=content,
            check=("%08x" % sum(content)).encode("ascii"))
        self.assertEqual(self.form(raw), "archive")
        raw = b"070701" + b"0" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")
        raw = b"MSCF" + b"\x00" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")
        raw = newc_bytes(name=b"\x00") \
            + b" and this plain answer stands as prose after it"
        self.assertIsNone(self.form(raw))
        raw = cab_bytes(60, first_file_offset=20) + (
            b"plain prose standing behind the header "
            b"to pass the size the header states here")
        self.assertIsNone(self.form(raw))


class Test014CabEntries(ImportBase):
    def prose_entries_bytes(self):
        return cab_bytes(
            60, first_file_offset=44, folder_count=1, file_count=1,
            tail=b"folderx!" + b"fileentryprose16")

    def test_folder_and_file_entries_as_prose_read_as_text(self):
        self.assertIsNone(self.form(self.prose_entries_bytes()))

    def test_folder_and_file_entries_as_prose_import_at_route(self):
        raw = self.prose_entries_bytes()
        path = self.temp_file(raw)
        record = self.prepare_file(path)
        self.assertEqual(record["answer_text"], raw.decode("utf-8"))

    def test_folder_entry_as_prose_alone_reads_as_text(self):
        raw = cab_bytes(
            44, first_file_offset=44, folder_count=1, file_count=0,
            tail=b"folderx!")
        self.assertIsNone(self.form(raw))

    def test_folder_entry_as_prose_alone_imports_at_route(self):
        raw = cab_bytes(
            44, first_file_offset=44, folder_count=1, file_count=0,
            tail=b"folderx!")
        path = self.temp_file(raw)
        record = self.prepare_file(path)
        self.assertEqual(record["answer_text"], raw.decode("utf-8"))

    def test_controls_hold(self):
        raw = b"MSCF" + b"\x00" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")
        raw = cab_bytes(60, first_file_offset=44, folder_count=1,
                        file_count=1, flags=8,
                        tail=b"folderx!" + b"fileentryprose16")
        self.assertIsNone(self.form(raw))
        folder_entry = (
            (60).to_bytes(4, "little") + (1).to_bytes(2, "little")
            + (0).to_bytes(2, "little"))
        file_entry = (
            (4).to_bytes(4, "little") + (0).to_bytes(4, "little")
            + (0).to_bytes(2, "little") + (0).to_bytes(2, "little")
            + (0).to_bytes(2, "little") + (0).to_bytes(2, "little"))
        raw = cab_bytes(
            68, first_file_offset=44, folder_count=1, file_count=1,
            tail=folder_entry + file_entry + b"datahere")
        self.assertEqual(self.form(raw), "archive")


FOLLOWERS = (
    "&1", "&9a", "&_a", "&-a", "!9", "*2", "%0",
    "&é", "&üa", "*ß", "&Ω",
)


class Test007ConstructFollowerSet(ImportBase):
    def test_line_form_value_followers_refused(self):
        for follower in FOLLOWERS:
            with self.subTest(follower=follower):
                self.assert_front_refused(
                    "---\ntitle: x." + follower + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_json_form_value_followers_refused(self):
        for follower in FOLLOWERS:
            with self.subTest(follower=follower):
                block = json.dumps({"title": "x." + follower})
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_line_form_key_followers_refused(self):
        for follower in ("&1", "&_a"):
            with self.subTest(follower=follower):
                self.assert_front_refused(
                    "---\nx." + follower + ": abc\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_json_form_key_followers_refused(self):
        for follower in ("&1", "&_a"):
            with self.subTest(follower=follower):
                block = json.dumps({"x." + follower: "v"})
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_controls_hold(self):
        self.assert_front_refused(
            "---\ntitle: x.&a\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        self.assert_front_refused(
            "---\ntitle: &1abc\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        body, had = import_module.extract_front_matter(
            "---\ntitle: plain text here\n---\n" + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)


HEAD_CHARS = (
    "​", "﻿", "͏", "⁠",
    "️", "‌", "‍", "\x01",
)
HEAD_CHARS_FIRST_FOUR = HEAD_CHARS[:4]


class Test013InteriorHeadMaterial(ImportBase):
    def test_line_form_value_behind_interior_head_refused(self):
        for head in HEAD_CHARS:
            with self.subTest(head=repr(head)):
                self.assert_front_refused(
                    "---\ntitle: x=" + head + "&a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_json_form_value_behind_interior_head_refused(self):
        for head in HEAD_CHARS_FIRST_FOUR:
            with self.subTest(head=repr(head)):
                block = json.dumps({"title": "x=" + head + "&a"})
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_json_form_key_behind_interior_head_refused(self):
        for head in HEAD_CHARS_FIRST_FOUR:
            with self.subTest(head=repr(head)):
                block = json.dumps({"x=" + head + "&a": "v"})
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_construct_letter_behind_interior_head_refused(self):
        for head in HEAD_CHARS_FIRST_FOUR:
            with self.subTest(head=repr(head)):
                self.assert_front_refused(
                    "---\ntitle: x &" + head + "a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_angle_spelling_behind_interior_head_refused(self):
        for head in HEAD_CHARS_FIRST_FOUR:
            with self.subTest(head=repr(head)):
                self.assert_front_refused(
                    "---\ntitle: x <" + head + "tag> y\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_controls_hold(self):
        self.assert_front_refused(
            "---\ntitle: x=&a\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        self.assert_front_refused(
            "---\ntitle: ​&a\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        self.assert_front_refused(
            "---\ntitle: x= &a\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        self.assert_front_refused(
            "---\nx=​&a: v\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        body, had = import_module.extract_front_matter(
            "---\ntitle: plain text here\n---\n" + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)


class EqAsTargetStr(str):
    """A string form whose characters stand as one sentinel
    string and whose equality answers as one target string,
    its hash standing as the hash of its characters."""

    def __new__(cls, characters, target):
        instance = str.__new__(cls, characters)
        instance.target = target
        return instance

    def __eq__(self, other):
        return other == self.target

    def __ne__(self, other):
        return not (other == self.target)

    def __hash__(self):
        return hash(str(self))


class EqTrueAgainstAnyStr(str):
    """A string form whose equality answers true against
    any candidate, its hash standing as the hash of the
    characters it carries."""

    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False

    def __hash__(self):
        return hash(str(self))


class EqRaisesStr(str):
    """A string form whose equality test raises a
    ValueError."""

    def __eq__(self, other):
        raise ValueError("equality raises")

    def __ne__(self, other):
        raise ValueError("equality raises")

    def __hash__(self):
        return hash(str(self))


class EqRaisesValue:
    """A hashable form in no string form whose equality
    test raises a ValueError."""

    def __init__(self, target):
        self.target = target

    def __eq__(self, other):
        raise ValueError("equality raises")

    def __ne__(self, other):
        raise ValueError("equality raises")

    def __hash__(self):
        return hash("citeline-eq-raises-sentinel")

    def __repr__(self):
        return "EqRaisesValue(%r)" % (self.target,)


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


class Test008StringFormDuplicates(WorksheetBase):
    def test_each_bucket_field_string_form_apart_refused(self):
        body_text = "First answer text."
        cases = (
            ("kind", "real_sample"),
            ("engine_label_normalised", "engine a"),
            ("query", Q1),
        )
        for field, target in cases:
            with self.subTest(field=field):
                self.assert_duplicate(
                    field,
                    EqAsTargetStr("sentinel-chars", target),
                    body_text)

    def test_content_hash_string_form_apart_refused(self):
        body_text = "First answer text."
        body_hash = hashlib.sha256(
            body_text.encode("utf-8")).hexdigest()
        self.assert_duplicate(
            "content_hash",
            EqAsTargetStr("sentinel-chars", body_hash),
            body_text)

    def test_kind_answering_true_against_any_candidate_refused(self):
        body_text = "First answer text."
        self.assert_duplicate(
            "kind", EqTrueAgainstAnyStr("other_kind"), body_text)

    def test_whole_list_comparison_reads_duplicate(self):
        body_text = "First answer text."
        record = self.standing(
            "kind", EqAsTargetStr("sentinel-chars", "real_sample"),
            body_text)[0]
        candidate = {
            "kind": "real_sample",
            "engine_label_normalised": "engine a",
            "query": Q1,
            "content_hash": record["content_hash"],
            "captured_on": "2026-11-10",
        }
        self.assertEqual(
            import_module.compare_standing([record], candidate),
            "duplicate")

    def test_controls_hold(self):
        body_text = "First answer text."
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
        list_record = dict(record)
        list_record["kind"] = ["real_sample"]
        path = self.temp_file(sheet_text({1: body_text}))
        records = self.prepare_sheet(
            path, standing_records=[list_record])
        self.assertEqual(len(records), 1)


class Test009EqualityRaisingAnswered(WorksheetBase):
    def test_bucket_field_equality_raising_answered_in_vocabulary(
            self):
        body_text = "First answer text."
        self.assert_duplicate(
            "kind", EqRaisesValue("real_sample"), body_text)

    def test_content_hash_equality_raising_value_answered(self):
        body_text = "First answer text."
        body_hash = hashlib.sha256(
            body_text.encode("utf-8")).hexdigest()
        self.assert_duplicate(
            "content_hash", EqRaisesValue(body_hash), body_text)

    def test_content_hash_equality_raising_string_form_answered(
            self):
        body_text = "First answer text."
        body_hash = hashlib.sha256(
            body_text.encode("utf-8")).hexdigest()
        self.assert_duplicate(
            "content_hash", EqRaisesStr(body_hash), body_text)

    def test_bucket_field_equality_raising_string_form_answered(
            self):
        body_text = "First answer text."
        self.assert_duplicate(
            "kind", EqRaisesStr("real_sample"), body_text)

    def test_controls_hold(self):
        body_text = "First answer text."
        self.assert_duplicate(
            "kind", BadHash("real_sample"), body_text)
        body_hash = hashlib.sha256(
            body_text.encode("utf-8")).hexdigest()
        self.assert_duplicate(
            "content_hash", BadHash(body_hash), body_text)


if __name__ == "__main__":
    unittest.main()
