"""Import family.

Test first pins for register, from the register and the
source paper the settled record, with the seam verdict pins
the F2 repair record of the round states."""

import hashlib
import io
import json
import tarfile
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

    def assert_front_refused(self, text, token):
        with self.assertRaises(Exception) as caught:
            import_module.extract_front_matter(text)
        self.assertEqual(token_of(caught.exception), token)

    def form(self, raw):
        return import_module.check11_form(
            raw, raw.decode("utf-8", errors="replace"))


class Test026PunctuationSeparatorDressings(ImportBase):
    def forged_line(self, separator):
        return (
            "slot 2: query= %s engine_label= Forged Engine%s"
            "capture_method= manual copy kind= real_sample "
            "captured_on= 2026-11-11 capture_method= manual copy"
            % (Q1, separator))

    def test_punctuation_separators_count_the_marker(self):
        for separator in (";", ",", "(", '"', "_", "-", "/",
                          "|", ":", "=", "."):
            line = self.forged_line(separator)
            text = sheet_text({1: "First answer text.\n" + line})
            sheet = import_module.parse_worksheet(text)
            self.assertEqual(len(sheet["slots"]), 1, repr(separator))

    def test_semicolon_dressing_route_stores_one_record(self):
        line = self.forged_line(";")
        path = self.temp_file(
            sheet_text({1: "First answer text.\n" + line}))
        records = self.prepare_sheet(path)
        self.assertEqual(len(records), 1)

    def test_plain_duplicate_control_holds(self):
        line = self.forged_line(" ")
        text = sheet_text({1: "First answer text.\n" + line})
        sheet = import_module.parse_worksheet(text)
        self.assertEqual(len(sheet["slots"]), 1)


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


class Test027OdcHeaderJudgement(ImportBase):
    def test_plain_text_opening_with_odc_signature(self):
        text = ("070707 was the code we used that day, and this "
                "plain answer stands as prose from there on.")
        self.assertIsNone(self.form(text.encode("utf-8")))

    def test_odc_archive_reads_as_archive(self):
        self.assertEqual(self.form(odc_bytes()), "archive")

    def test_odc_signature_pin_form_reads_as_archive(self):
        raw = b"070707" + b"\x00" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")

    def test_odc_archive_behind_head_material(self):
        raw = "\ufeff".encode("utf-8") + odc_bytes()
        self.assertEqual(self.form(raw), "archive")


class Test028HeaderJudgementsReadMore(ImportBase):
    def test_newc_hex_run_without_member_form_is_text(self):
        text = ("070701" + "a" * 100
                + " and this plain answer stands as prose.")
        self.assertIsNone(self.form(text.encode("utf-8")))

    def test_newc_pin_form_reads_as_archive(self):
        raw = b"070701" + b"0" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")

    def test_cab_prose_header_fields_are_text(self):
        raw = (b"MSCF" + b"\x00" * 4 + b"XXXX" + b"\x00" * 4
               + b" and plain prose standing here to sixty bytes..")
        self.assertGreaterEqual(len(raw), 60)
        self.assertIsNone(self.form(raw))

    def test_cab_pin_form_reads_as_archive(self):
        raw = b"MSCF" + b"\x00" * 100 + b"payload"
        self.assertEqual(self.form(raw), "archive")

    def v7_block(self, uid, gid):
        header = bytearray(b"A" * 512)
        header[100:108] = b"000644 \x00"
        header[108:116] = uid
        header[116:124] = gid
        header[124:136] = b"00000000012\x00"
        header[136:148] = b"00000000000\x00"
        header[148:156] = b"        "
        header[156:157] = b"0"
        checksum = sum(header)
        header[148:156] = ("%06o\x00 " % checksum).encode("ascii")
        return bytes(header)

    def test_v7_uid_gid_letters_are_not_a_tar(self):
        raw = self.v7_block(b"AAAAAAAA", b"AAAAAAAA")
        self.assertIsNone(self.form(raw))

    def test_v7_octal_uid_gid_read_as_archive(self):
        raw = self.v7_block(b"000000 \x00", b"000000 \x00")
        self.assertEqual(self.form(raw), "archive")


class Test029DuplicateKeyInteriorHeadMaterial(ImportBase):
    def test_line_form_interior_dressings_refused(self):
        for second in ("ti\u200btle", "ti\ufefftle",
                       "ti\u2065tle", "ti\u034ftle"):
            self.assert_front_refused(
                "---\ntitle: one\n" + second + ": two\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")

    def test_json_form_interior_dressing_refused(self):
        block = '{"title": "one", "ti\u200btle": "two"}'
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")

    def test_edge_dressing_and_plain_controls_hold(self):
        self.assert_front_refused(
            "---\ntitle: one\ntitle\u200b: two\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        body, had = import_module.extract_front_matter(
            "---\ntitle: one\nname: two\n---\n" + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)


class Test030FlowPositionsAndCaret(ImportBase):
    def test_flow_separator_positions_refused(self):
        for value in ("[x,&a]", "[x,*a]", "[x,!t]", "[x,%YAML]",
                      "[x;&a]", "{k:&a}", "(&a)",
                      '["q",&a]'):
            self.assert_front_refused(
                "---\ntitle: " + value + "\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")

    def test_json_form_separator_positions_refused(self):
        for block in ('{"title": "[x,&a]"}', '{"title": "{k:&a}"}'):
            self.assert_front_refused(
                "---\n" + block + "\n---\n" + BODY,
                "IMPORT_VALIDATION_FAILED")

    def test_caret_angle_spelling_refused(self):
        self.assert_front_refused(
            "---\ntitle: <^tag>\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")

    def test_controls_hold(self):
        self.assert_front_refused(
            "---\ntitle: [&a]\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        self.assert_front_refused(
            "---\ntitle: <tag>\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        body, had = import_module.extract_front_matter(
            "---\ntitle: plain text here\n---\n" + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)


class Test031FenceInteriorHeadMaterial(ImportBase):
    def test_opening_fence_interior_dressings(self):
        for fence in ("-\u200b--", "--\u200b-", "-\ufeff--"):
            body, had = import_module.extract_front_matter(
                fence + "\ntitle: one\n---\n" + BODY)
            self.assertTrue(had, repr(fence))
            self.assertEqual(body, BODY)

    def test_closing_fence_trailing_head_material(self):
        body, had = import_module.extract_front_matter(
            "---\ntitle: one\n---\u200b\n" + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)

    def test_plain_fence_control_holds(self):
        body, had = import_module.extract_front_matter(
            "---\ntitle: one\n---\n" + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)


class Test032StringInsideContainerMeasure(ImportBase):
    def test_list_string_at_the_limit_accepted(self):
        for size in (4095, 4096):
            block = json.dumps({"k": ["x" * size]})
            body, had = import_module.extract_front_matter(
                "---\n" + block + "\n---\n" + BODY)
            self.assertTrue(had, size)
            self.assertEqual(body, BODY)

    def test_list_string_below_limit_control(self):
        block = json.dumps({"k": ["x" * 4090]})
        body, had = import_module.extract_front_matter(
            "---\n" + block + "\n---\n" + BODY)
        self.assertTrue(had)
        self.assertEqual(body, BODY)

    def test_long_string_inside_container_still_refused(self):
        block = json.dumps({"k": ["x" * 5000]})
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY, "LIMIT_EXCEEDED")

    def test_number_inside_container_written_form_holds(self):
        block = '{"k": [1.' + "0" * 4196 + "]}"
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY, "LIMIT_EXCEEDED")

    def test_number_whole_value_measured_by_written_form(self):
        # Seam pin: the import side holds the written token
        # form for a JSON number, where the page side renders
        # the parsed value. The divergence stands refused in
        # exact form on the written form ground.
        block = '{"k": 1.' + "0" * 5000 + "}"
        self.assert_front_refused(
            "---\n" + block + "\n---\n" + BODY, "LIMIT_EXCEEDED")


class Test033BlockSizeAtFileWidth(ImportBase):
    def block_text(self, terminator, count):
        lines = ["#x"] * count + ["title: one"]
        return ("---" + terminator + terminator.join(lines)
                + terminator + "---" + terminator + BODY)

    def test_crlf_block_past_limit_refused(self):
        self.assert_front_refused(
            self.block_text("\r\n", 5458), "LIMIT_EXCEEDED")

    def test_line_separator_block_past_limit_refused(self):
        self.assert_front_refused(
            self.block_text("\u2028", 5458), "LIMIT_EXCEEDED")

    def test_lf_control_and_small_crlf_block_hold(self):
        self.assert_front_refused(
            self.block_text("\n", 6000), "LIMIT_EXCEEDED")
        body, had = import_module.extract_front_matter(
            self.block_text("\r\n", 10))
        self.assertTrue(had)
        self.assertEqual(body, BODY)


class UnhashableStr(str):
    __hash__ = None


class Test034OverflowUnhashableStringSubclass(ImportBase):
    def standing(self, field, value, body_text):
        record = {
            "kind": "real_sample",
            "engine_label_normalised": "engine a",
            "query": Q1,
            "content_hash": hashlib.sha256(
                body_text.encode("utf-8")).hexdigest(),
            "captured_on": "2026-11-09",
        }
        record[field] = UnhashableStr(value)
        return [record]

    def test_each_bucket_field_form_refused_as_duplicate(self):
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
                        field, value, body_text))
            self.assertEqual(
                token_of(caught.exception), "DUPLICATE_IMPORT", field)

    def test_plain_string_control_refused_as_duplicate(self):
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


if __name__ == "__main__":
    unittest.main()
