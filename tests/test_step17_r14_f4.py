"""Import family.

Test first pins for the import side limb of register,
from the register, as dispositioned in the register
paper ruling (c) and Section 3, this seat standing
charged with the import side limb at the lead of seat
F2."""

import json
import unicodedata
import unittest

from citeline import probe_import as import_module

BODY = "A plain answer body standing here."
ZWSP = "​"


def token_of(exc):
    return getattr(exc, "error_value", None) or ""


HEAD_MARKS = tuple(chr(point) for point in (
    0x034F, 0x0610, 0x0615, 0x061A, 0x17B4, 0x17B5,
    0x180B, 0x180D, 0x180F, 0xFE00, 0xFE08, 0xFE0F,
    0x1D17B, 0x1D182, 0xE0100, 0xE01EF))
NON_HEAD_UNION = tuple(chr(point) for point in (
    0x0483, 0x0301, 0x0903, 0x093B, 0x20DD, 0x0488))


class ImportBase(unittest.TestCase):
    def assert_front_refused(self, text, token):
        with self.assertRaises(Exception) as caught:
            import_module.extract_front_matter(text)
        self.assertEqual(token_of(caught.exception), token)

    def assert_front_passes(self, text):
        body, had = import_module.extract_front_matter(text)
        self.assertTrue(had)
        self.assertEqual(body, BODY)


class Test001SoleFollowerHeadMarks(ImportBase):
    def test_head_marks_stand_in_head_set_and_category_mn(self):
        for mark in HEAD_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                self.assertEqual(unicodedata.category(mark), "Mn")
                self.assertTrue(import_module._is_head_char(mark))

    def test_every_union_mark_refused_at_helper_sole_follower(self):
        refused = 0
        total = 0
        head_refused = 0
        head_total = 0
        for point in range(0x110000):
            mark = chr(point)
            if unicodedata.category(mark) not in ("Mn", "Mc", "Me"):
                continue
            total += 1
            if import_module._is_head_char(mark):
                head_total += 1
            if import_module._holds_tag_construct("x &" + mark):
                refused += 1
                if import_module._is_head_char(mark):
                    head_refused += 1
        self.assertGreater(head_total, 0)
        self.assertEqual(refused, total)
        self.assertEqual(head_refused, head_total)

    def test_line_form_value_sole_follower_at_end_refused(self):
        for mark in HEAD_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                self.assert_front_refused(
                    "---\ntitle: x &" + mark + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_line_form_value_sole_follower_other_constructs(self):
        for construct in ("!", "*", "%"):
            for mark in HEAD_MARKS[:8]:
                with self.subTest(
                        construct=construct, mark=hex(ord(mark))):
                    self.assert_front_refused(
                        "---\ntitle: x " + construct + mark
                        + "\n---\n" + BODY,
                        "IMPORT_VALIDATION_FAILED")

    def test_line_form_value_sole_follower_before_space_refused(self):
        for mark in HEAD_MARKS:
            with self.subTest(mark=hex(ord(mark)), form="space_word"):
                self.assert_front_refused(
                    "---\ntitle: x &" + mark + " word\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")
            with self.subTest(mark=hex(ord(mark)), form="space_end"):
                self.assert_front_refused(
                    "---\ntitle: x &" + mark + " \n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_line_form_value_two_head_marks_and_head_trailing(self):
        self.assert_front_refused(
            "---\ntitle: x &" + HEAD_MARKS[9] + HEAD_MARKS[11]
            + "\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        self.assert_front_refused(
            "---\ntitle: x &" + HEAD_MARKS[11] + ZWSP
            + "\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        self.assert_front_refused(
            "---\ntitle: x &" + HEAD_MARKS[0] + ZWSP
            + "\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")

    def test_json_form_value_sole_follower_refused(self):
        for mark in HEAD_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                block = json.dumps({"title": "x &" + mark})
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_json_escape_form_value_sole_follower_refused(self):
        for mark in HEAD_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                block = json.dumps(
                    {"title": "x &" + mark}, ensure_ascii=True)
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_line_form_key_sole_follower_refused(self):
        for mark in HEAD_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                self.assert_front_refused(
                    "---\nx &" + mark + ": abc\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_json_form_key_sole_follower_refused(self):
        for mark in HEAD_MARKS:
            with self.subTest(mark=hex(ord(mark)), form="plain"):
                block = json.dumps({"x &" + mark: "v"})
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")
            with self.subTest(mark=hex(ord(mark)), form="escape"):
                block = json.dumps(
                    {"x &" + mark: "v"}, ensure_ascii=True)
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_head_material_around_construct_sole_follower(self):
        mark = HEAD_MARKS[11]
        self.assert_front_refused(
            "---\ntitle: x." + ZWSP + "&" + mark + "\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        self.assert_front_refused(
            "---\ntitle: x &" + ZWSP + mark + "\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")

    def test_non_head_union_sole_followers_refused(self):
        for mark in NON_HEAD_UNION:
            with self.subTest(mark=hex(ord(mark))):
                self.assert_front_refused(
                    "---\ntitle: x &" + mark + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_controls_hold(self):
        for mark in HEAD_MARKS[:4]:
            with self.subTest(mark=hex(ord(mark)), form="letter"):
                self.assert_front_refused(
                    "---\ntitle: x &" + mark + "a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")
            with self.subTest(mark=hex(ord(mark)), form="full_stop"):
                self.assert_front_refused(
                    "---\ntitle: x &" + mark + ".\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")
        for follower in ("'", "#", ",", "|", '"'):
            with self.subTest(follower=repr(follower)):
                self.assert_front_passes(
                    "---\ntitle: x &" + follower + "a\n---\n" + BODY)
        self.assert_front_passes(
            "---\ntitle: x &" + ZWSP + "\n---\n" + BODY)
        self.assert_front_passes(
            "---\ntitle: a & b\n---\n" + BODY)
        self.assert_front_passes(
            "---\ntitle: plain text here\n---\n" + BODY)


if __name__ == "__main__":
    unittest.main()
