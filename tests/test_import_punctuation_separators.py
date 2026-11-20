"""Import family.

Test first pins for register, from the register and the
source papers the settled record and the settled record
(finding, merged), with the seam positions the F2 repair record
of the round states at."""

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


class Test012RemainingPunctuationSeparators(ImportBase):
    def forged_line(self, separator):
        return (
            "slot 2: query= %s engine_label= Forged Engine%s"
            "capture_method= manual copy kind= real_sample "
            "captured_on= 2026-11-11 capture_method= manual copy"
            % (Q1, separator))

    def test_remaining_punctuation_separators_count_the_marker(self):
        separators = (")", "'", "]", "}", "?", "!", "@", "#", "$",
                      "%", "^", "&", "*", "+", "~", "`", "\\", "<",
                      ">", "[", "{")
        self.assertEqual(len(separators), 21)
        for separator in separators:
            line = self.forged_line(separator)
            text = sheet_text({1: "First answer text.\n" + line})
            sheet = import_module.parse_worksheet(text)
            self.assertEqual(len(sheet["slots"]), 1, repr(separator))

    def test_route_stores_one_record_on_three_dressings(self):
        for separator in (")", "'", "]"):
            line = self.forged_line(separator)
            path = self.temp_file(sheet_text(
                {1: "First answer text.\n" + line
                 + "\nForged slot body standing here."}))
            records = self.prepare_sheet(path)
            self.assertEqual(len(records), 1, repr(separator))

    def test_cured_dressings_and_space_control_hold(self):
        for separator in (";", ",", "(", '"', "_", "-", "/", "|",
                          ":", "=", ".", " "):
            line = self.forged_line(separator)
            text = sheet_text({1: "First answer text.\n" + line})
            sheet = import_module.parse_worksheet(text)
            self.assertEqual(len(sheet["slots"]), 1, repr(separator))


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


class Test013OdcFieldStructure(ImportBase):
    def test_digit_and_space_prose_is_text(self):
        text = ("070707" + "01234567 " * 8
                + "was the code we used that day and this "
                "stands as prose")
        self.assertIsNone(self.form(text.encode("utf-8")))

    def test_space_run_prose_is_text(self):
        text = ("070707" + " " * 70
                + "plain prose after a long run of spaces")
        self.assertIsNone(self.form(text.encode("utf-8")))

    def test_numeric_table_prose_is_text_at_module_level(self):
        text = ("070707" + "12345670 " * 8
                + "the cohort table we kept that term")
        self.assertIsNone(self.form(text.encode("utf-8")))

    def test_numeric_table_prose_imports_at_the_route(self):
        text = ("070707" + "12345670 " * 8
                + "the cohort table we kept that term")
        path = self.temp_file(text)
        record = self.prepare_file(path)
        self.assertEqual(record["answer_text"], text)

    def test_digit_and_space_prose_imports_at_the_route(self):
        text = ("070707" + "01234567 " * 8
                + "was the code we used that day and this "
                "stands as prose")
        path = self.temp_file(text)
        record = self.prepare_file(path)
        self.assertEqual(record["answer_text"], text)

    def test_controls_hold(self):
        prose = ("070707 was the code we used that day, and this "
                 "plain answer stands as prose from there on.")
        self.assertIsNone(self.form(prose.encode("utf-8")))
        self.assertEqual(self.form(odc_bytes()), "archive")
        raw = b"070707" + b"\x00" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")
        raw = "\ufeff".encode("utf-8") + odc_bytes()
        self.assertEqual(self.form(raw), "archive")


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


class Test014HeaderJudgementsReadMore(ImportBase):
    def test_newc_zero_hex_run_is_text(self):
        text = ("070701" + "0" * 104
                + " and this plain answer stands as prose "
                "after a run of zeros")
        self.assertIsNone(self.form(text.encode("utf-8")))

    def test_newc_zero_hex_run_imports_at_the_route(self):
        text = ("070701" + "0" * 104
                + " and this plain answer stands as prose "
                "after a run of zeros")
        path = self.temp_file(text)
        record = self.prepare_file(path)
        self.assertEqual(record["answer_text"], text)

    def test_newc_name_without_terminator_is_text(self):
        crafted = list("070701" + "a" * 100 + "x" * 30)
        crafted[94:102] = list("00000001")
        crafted[54:62] = list("00000000")
        self.assertIsNone(self.form("".join(crafted).encode("utf-8")))

    def test_newc_controls_hold(self):
        raw = b"070701" + b"0" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")
        self.assertEqual(self.form(newc_bytes()), "archive")

    def test_cab_prose_in_remaining_header_fields_is_text(self):
        raw = bytearray(
            b"MSCF" + b"\x00" * 4 + (60).to_bytes(4, "little")
            + b"\x00" * 4 + (36).to_bytes(4, "little")
            + b"plain prose standing in the remaining header "
              b"fields to sixty bytes....")
        self.assertGreaterEqual(len(raw), 60)
        self.assertIsNone(self.form(bytes(raw)))

    def test_cab_controls_hold(self):
        raw = b"MSCF" + b"\x00" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")
        raw = (b"MSCF" + b"\x00" * 4 + b"XXXX" + b"\x00" * 4
               + b" and plain prose standing here to sixty bytes..")
        self.assertIsNone(self.form(raw))

    def v7_block(self, tail):
        header = bytearray(tail * 512)
        name = b"member.txt"
        header[0:len(name)] = name
        header[len(name):100] = b"\x00" * (100 - len(name))
        header[100:108] = b"000644 \x00"
        header[108:116] = b"000000 \x00"
        header[116:124] = b"000000 \x00"
        header[124:136] = b"00000000012\x00"
        header[136:148] = b"00000000000\x00"
        header[148:156] = b"        "
        header[156:157] = b"0"
        header[157:512] = b"\x00" * (512 - 157)
        checksum = sum(header)
        header[148:156] = ("%06o\x00 " % checksum).encode("ascii")
        return bytes(header)

    def test_v7_genuine_block_control_holds(self):
        self.assertEqual(self.form(self.v7_block(b"\x00")), "archive")

    @unittest.expectedFailure
    def test_v7_letter_padding_form_is_text(self):
        # Refusal pin for the V7 limb, recorded in exact form
        # in the F4 repair record of the round: the worked form
        # stands byte for byte as the archive control form the
        # round 7 cure tests pin, a 512 byte block of letter A
        # characters with its mode, size, mtime, uid, and gid
        # fields in octal form, its type flag as the digit 0,
        # and its checksum field as the octal sum of the
        # block, so no header reading refuses the worked form
        # while the control stands.
        header = bytearray(b"A" * 512)
        header[100:108] = b"000644 \x00"
        header[108:116] = b"000000 \x00"
        header[116:124] = b"000000 \x00"
        header[124:136] = b"00000000012\x00"
        header[136:148] = b"00000000000\x00"
        header[148:156] = b"        "
        header[156:157] = b"0"
        checksum = sum(header)
        header[148:156] = ("%06o\x00 " % checksum).encode("ascii")
        self.assertIsNone(self.form(bytes(header)))


class Test015ClosingBracketAndHashAngle(ImportBase):
    def test_closing_bracket_positions_refused_in_line_form(self):
        for value in ("[[x]&a]", "{k:{x}&a}", "[(x)&a]",
                      "{k:[y]&a}", "[x]&a", "x)&a", "x]&a",
                      "x}&a"):
            self.assert_front_refused(
                "---\ntitle: " + value + "\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")

    def test_closing_bracket_position_refused_in_json_form(self):
        block = '{"title": "[[x]&a]"}'
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")

    def test_hash_angle_spelling_refused_in_both_forms(self):
        self.assert_front_refused(
            "---\ntitle: <#tag>\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        block = '{"title": "<#tag>"}'
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")

    def test_controls_hold(self):
        for value in ("[[x],&a]", "<tag>", "<^tag>", "<=tag>"):
            self.assert_front_refused(
                "---\ntitle: " + value + "\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")
        body, had = import_module.extract_front_matter(
            "---\ntitle: plain text here\n---\n" + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)


class Test016ContainerKeyMeasure(ImportBase):
    def test_long_key_inside_a_mapping_value_refused(self):
        block = json.dumps({"outer": {"k" * 5000: "short"}})
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY, "LIMIT_EXCEEDED")

    def test_long_key_inside_a_list_mapping_refused(self):
        block = json.dumps({"outer": [{"k" * 5000: "short"}]})
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY, "LIMIT_EXCEEDED")

    def test_long_key_at_depth_refused(self):
        block = json.dumps({"a": {"b": {"c": {"k" * 5000: 1}}}})
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY, "LIMIT_EXCEEDED")

    def test_controls_hold(self):
        block = json.dumps({"k": ["x" * 5000]})
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY, "LIMIT_EXCEEDED")
        block = json.dumps({"outer": {"k" * 4000: "short"}})
        body, had = import_module.extract_front_matter(
            "---\n" + block + "\n---\n" + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)


class EqStr:
    """A value equal to one string, unhashable, no string
    subclass: the form works."""

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


class Test017UnhashableNonStringEquality(ImportBase):
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

    def test_each_bucket_field_eqstr_form_refused_as_duplicate(self):
        body_text = "First answer text."
        cases = (
            ("kind", "real_sample"),
            ("engine_label_normalised", "engine a"),
            ("query", Q1),
        )
        for field, value in cases:
            path = self.temp_file(sheet_text({1: body_text}))
            with self.assertRaises(Exception) as caught:
                self.prepare_sheet(
                    path, standing_records=self.standing(
                        field, EqStr(value), body_text))
            self.assertEqual(
                token_of(caught.exception), "DUPLICATE_IMPORT", field)

    def test_content_hash_eqstr_form_refused_as_duplicate(self):
        body_text = "First answer text."
        body_hash = hashlib.sha256(
            body_text.encode("utf-8")).hexdigest()
        path = self.temp_file(sheet_text({1: body_text}))
        with self.assertRaises(Exception) as caught:
            self.prepare_sheet(
                path, standing_records=self.standing(
                    "content_hash", EqStr(body_hash), body_text))
        self.assertEqual(token_of(caught.exception), "DUPLICATE_IMPORT")

    def test_whole_list_comparison_reads_duplicate(self):
        body_text = "First answer text."
        record = self.standing("kind", EqStr("real_sample"),
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
        path = self.temp_file(sheet_text({1: body_text}))
        with self.assertRaises(Exception) as caught:
            self.prepare_sheet(
                path, standing_records=self.standing(
                    "kind", UnhashableStr("real_sample"), body_text))
        self.assertEqual(token_of(caught.exception), "DUPLICATE_IMPORT")
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


if __name__ == "__main__":
    unittest.main()
