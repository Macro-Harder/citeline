"""Step 17 round 9 fix seat F4 tests: import family.

Test first pins for register entries S17-R9-009 to
S17-R9-013, from design/audit/step-17-r9-findings-register.md
and the source paper step-17-r9-attack-import.md, with the
seams the F2 fix paper of this round states at entries
S17-R9-011 and S17-R9-012.
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

    def form(self, raw):
        return import_module.check11_form(
            raw, raw.decode("utf-8", errors="replace"))


def odc_field(value, width):
    text = "%0*o" % (width - 1, value)
    return text.encode("ascii") + b"\x00"


def odc_bytes():
    name = b"member.txt\x00"
    content = b"hello cpio"
    header = (
        b"070707" + odc_field(0, 6) + odc_field(1, 6)
        + odc_field(0o644, 6) + odc_field(0, 6) + odc_field(0, 6)
        + odc_field(1, 6) + odc_field(0, 6) + odc_field(0, 11)
        + odc_field(len(name), 6) + odc_field(len(content), 11))
    trailer_name = b"TRAILER!!!\x00"
    trailer = (
        b"070707" + odc_field(0, 6) + odc_field(0, 6)
        + odc_field(0, 6) + odc_field(0, 6) + odc_field(0, 6)
        + odc_field(1, 6) + odc_field(0, 6) + odc_field(0, 11)
        + odc_field(len(trailer_name), 6) + odc_field(0, 11))
    return header + name + content + trailer + trailer_name


def odc_space_fields_bytes():
    widths = (6, 6, 6, 6, 6, 6, 6, 11, 6, 11)
    fields = b"".join(b" " * (width - 1) + b"\x00" for width in widths)
    return (b"070707" + fields
            + b"plain prose standing after the header fields here")


def odc_huge_sizes_bytes():
    header = (
        b"070707" + odc_field(0, 6) + odc_field(1, 6)
        + odc_field(0o644, 6) + odc_field(0, 6) + odc_field(0, 6)
        + odc_field(1, 6) + odc_field(0, 6) + odc_field(0, 11)
        + odc_field(0o7777, 6) + odc_field(0o77777, 11))
    return header + b"short prose"


class Test009OdcFieldValues(ImportBase):
    def test_space_fields_hold_no_octal_value_and_read_as_text(self):
        self.assertIsNone(self.form(odc_space_fields_bytes()))

    def test_space_fields_import_whole_at_the_route(self):
        raw = odc_space_fields_bytes()
        path = self.temp_file(raw)
        record = self.prepare_file(path)
        self.assertEqual(
            record["answer_text"], raw.decode("utf-8"))

    def test_stated_sizes_past_the_bytes_standing_read_as_text(self):
        self.assertIsNone(self.form(odc_huge_sizes_bytes()))

    def test_stated_sizes_past_the_bytes_import_at_the_route(self):
        raw = odc_huge_sizes_bytes()
        path = self.temp_file(raw)
        record = self.prepare_file(path)
        self.assertEqual(
            record["answer_text"], raw.decode("utf-8"))

    def test_controls_hold(self):
        self.assertEqual(self.form(odc_bytes()), "archive")
        raw = b"070707" + b"\x00" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")
        raw = "\ufeff".encode("utf-8") + odc_bytes()
        self.assertEqual(self.form(raw), "archive")
        text = ("070707" + "01234567 " * 8
                + "was the code we used that day and this "
                "stands as prose")
        self.assertIsNone(self.form(text.encode("utf-8")))
        text = "070707" + " " * 70 + "plain prose after spaces"
        self.assertIsNone(self.form(text.encode("utf-8")))


def newc_bytes():
    def field(value):
        return ("%08x" % value).encode("ascii")

    name = b"member.txt\x00"
    content = b"hello cpio"
    header = (
        b"070701" + field(1) + field(0o100644) + field(0)
        + field(0) + field(1) + field(0) + field(len(content))
        + field(0) + field(0) + field(0) + field(0)
        + field(len(name)) + field(0))
    return header + name + content


def newc_empty_name_bytes():
    def field(value):
        return ("%08x" % value).encode("ascii")

    header = (
        b"070701" + field(1) + field(0o100644) + field(0)
        + field(0) + field(1) + field(0) + field(0)
        + field(0) + field(0) + field(0) + field(0)
        + field(1) + field(0))
    return (header + b"\x00"
            + b" and this plain answer stands as prose after it")


def cab_prose_tail_bytes():
    raw = bytearray()
    raw += b"MSCF" + b"\x00" * 4
    raw += (60).to_bytes(4, "little")
    raw += b"\x00" * 4
    raw += (36).to_bytes(4, "little")
    raw += b"\x00" * 4
    raw += bytes((3, 1))
    raw += b"plainprose"
    raw += b" and further prose standing here to pass sixty bytes"
    return bytes(raw)


class Test010NewcAndCabHeaderFields(ImportBase):
    def test_newc_empty_member_name_reads_as_text(self):
        self.assertIsNone(self.form(newc_empty_name_bytes()))

    def test_newc_empty_member_name_imports_at_the_route(self):
        raw = newc_empty_name_bytes()
        path = self.temp_file(raw)
        record = self.prepare_file(path)
        self.assertEqual(
            record["answer_text"], raw.decode("utf-8"))

    def test_cab_prose_in_the_tail_header_fields_reads_as_text(self):
        self.assertIsNone(self.form(cab_prose_tail_bytes()))

    def test_cab_prose_in_the_tail_header_fields_imports_at_route(self):
        raw = cab_prose_tail_bytes()
        path = self.temp_file(raw)
        record = self.prepare_file(path)
        self.assertEqual(record["answer_text"], raw.decode("utf-8"))

    def test_controls_hold(self):
        self.assertEqual(self.form(newc_bytes()), "archive")
        raw = b"070701" + b"0" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")
        text = ("070701" + "0" * 104
                + " and this plain answer stands as prose")
        self.assertIsNone(self.form(text.encode("utf-8")))
        raw = b"MSCF" + b"\x00" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")
        raw = (b"MSCF" + b"\x00" * 4 + b"XXXX" + b"\x00" * 4
               + b" and plain prose standing here to sixty bytes..")
        self.assertIsNone(self.form(raw))
        raw = bytearray(
            b"MSCF" + b"\x00" * 4 + (60).to_bytes(4, "little")
            + b"\x00" * 4 + (36).to_bytes(4, "little")
            + b"plain prose standing in the remaining header "
              b"fields to sixty bytes....")
        self.assertIsNone(self.form(bytes(raw)))


class Test011RemainingPunctuationPositions(ImportBase):
    def test_line_form_twenty_one_characters_refused(self):
        characters = ("!", "#", "$", "%", "&", "*", "+", "-", ".",
                      "/", "<", "=", ">", "?", "@", "\\", "^", "_",
                      "`", "|", "~")
        self.assertEqual(len(characters), 21)
        for char in characters:
            with self.subTest(char=char):
                self.assert_front_refused(
                    "---\ntitle: x" + char + "&a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_json_form_sampled_characters_refused(self):
        for char in (".", "/", "=", ">", "#", "|", "-", "_"):
            with self.subTest(char=char):
                block = json.dumps({"title": "x" + char + "&a"})
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_construct_characters_beyond_the_anchor_refused(self):
        for punct in (".", "/", "=", ">"):
            for construct in ("!", "*", "%"):
                with self.subTest(punct=punct, construct=construct):
                    self.assert_front_refused(
                        "---\ntitle: x" + punct + construct
                        + "a\n---\n" + BODY,
                        "IMPORT_VALIDATION_FAILED")

    def test_line_form_key_position_refused(self):
        self.assert_front_refused(
            "---\nx.&a: abc\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")

    def test_json_form_key_position_refused(self):
        block = json.dumps({"x.&a": "v"})
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")

    def test_controls_hold(self):
        for value in ("[[x]&a]", "{k:{x}&a}", "[x]&a", "x)&a",
                      "x]&a", "x}&a", "[[x],&a]", "<tag>"):
            self.assert_front_refused(
                "---\ntitle: " + value + "\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")
        body, had = import_module.extract_front_matter(
            "---\ntitle: plain text here\n---\n" + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)


class Test012TopLevelKeyMeasure(ImportBase):
    def test_top_level_key_of_5000_refused(self):
        block = json.dumps({"k" * 5000: "short"})
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY, "LIMIT_EXCEEDED")

    def test_top_level_key_of_4097_refused(self):
        block = json.dumps({"k" * 4097: "short"})
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY, "LIMIT_EXCEEDED")

    def test_top_level_key_of_5000_holding_a_mapping_refused(self):
        block = json.dumps({"k" * 5000: {"a": "short"}})
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY, "LIMIT_EXCEEDED")

    def test_controls_hold(self):
        block = json.dumps({"outer": {"k" * 5000: "short"}})
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY, "LIMIT_EXCEEDED")
        block = json.dumps({"k": ["x" * 5000]})
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY, "LIMIT_EXCEEDED")
        block = json.dumps({"k" * 4000: "short"})
        body, had = import_module.extract_front_matter(
            "---\n" + block + "\n---\n" + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)


class EqStr:
    __hash__ = None

    def __init__(self, target):
        self.target = target

    def __eq__(self, other):
        return other == self.target or (
            isinstance(other, EqStr) and other.target == self.target)

    def __repr__(self):
        return "EqStr(%r)" % (self.target,)


class UnhashableStr(str):
    __hash__ = None


class HashApart:
    """Equal to one candidate string, with a hash standing
    apart from the hash of that string."""

    def __init__(self, target):
        self.target = target

    def __eq__(self, other):
        return other == self.target or (
            isinstance(other, HashApart)
            and other.target == self.target)

    def __hash__(self):
        return hash("citeline-hash-apart-sentinel")

    def __repr__(self):
        return "HashApart(%r)" % (self.target,)


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


class Test013HashApartAndBadHashDuplicates(ImportBase):
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

    def test_each_bucket_field_hash_apart_form_refused(self):
        body_text = "First answer text."
        cases = (
            ("kind", "real_sample"),
            ("engine_label_normalised", "engine a"),
            ("query", Q1),
        )
        for field, value in cases:
            self.assert_duplicate(field, HashApart(value), body_text)

    def test_content_hash_hash_apart_form_refused(self):
        body_text = "First answer text."
        body_hash = hashlib.sha256(
            body_text.encode("utf-8")).hexdigest()
        self.assert_duplicate(
            "content_hash", HashApart(body_hash), body_text)

    def test_bucket_field_bad_hash_answered_in_vocabulary(self):
        body_text = "First answer text."
        self.assert_duplicate(
            "kind", BadHash("real_sample"), body_text)

    def test_content_hash_bad_hash_answered_in_vocabulary(self):
        body_text = "First answer text."
        body_hash = hashlib.sha256(
            body_text.encode("utf-8")).hexdigest()
        self.assert_duplicate(
            "content_hash", BadHash(body_hash), body_text)

    def test_whole_list_comparison_reads_duplicate(self):
        body_text = "First answer text."
        record = self.standing(
            "kind", HashApart("real_sample"), body_text)[0]
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
        self.assert_duplicate(
            "kind", EqStr("real_sample"), body_text)
        self.assert_duplicate(
            "kind", UnhashableStr("real_sample"), body_text)
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


if __name__ == "__main__":
    unittest.main()
