"""Registry and acquisition.

Test first pins for register. Each defect test reproduces the
defect named at that entry, a construct standing behind interior
head material at a judged position passing the page reading,
then stands as the pin for its cure. The head characters stand
as the eight characters the Red filing names: a zero width
space, a byte order mark, a combining grapheme joiner, a word
joiner, a variation selector, a zero width non joiner, a zero
width joiner, and a control character at code point 1."""

import os
import tempfile
import unittest

from citeline import acquisition

AUDIT_DATE = "2026-11-15"

HEAD_CHARACTERS = {
    "zero_width_space": "​",
    "byte_order_mark": "﻿",
    "combining_grapheme_joiner": "͏",
    "word_joiner": "⁠",
    "variation_selector": "️",
    "zero_width_non_joiner": "‌",
    "zero_width_joiner": "‍",
    "control_character_1": "\x01",
}

FIRST_FOUR = (
    "zero_width_space",
    "byte_order_mark",
    "combining_grapheme_joiner",
    "word_joiner",
)


def _token(exc):
    return getattr(exc, "token", None) or getattr(
        exc, "error_value", None)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def page_front_matter(self, block):
        text = "---\n" + block + "\n---\nbody text\n"
        notes = []
        return acquisition._front_matter(text, "markdown", notes)

    def assert_page_refuses(self, block):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.page_front_matter(block)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")


class TestR10_012InteriorHeadConstruct(Base):
    def test_line_value_behind_each_head_character_refuses(self):
        for name, head in HEAD_CHARACTERS.items():
            with self.subTest(head=name):
                self.assert_page_refuses(
                    "title: x=" + head + "&tag rest")

    def test_json_value_behind_head_material_refuses(self):
        for name, head in HEAD_CHARACTERS.items():
            if name == "control_character_1":
                continue
            with self.subTest(head=name):
                self.assert_page_refuses(
                    '{"title": "x=' + head + '&tag"}')

    def test_json_key_behind_head_material_refuses(self):
        for name, head in HEAD_CHARACTERS.items():
            if name == "control_character_1":
                continue
            with self.subTest(head=name):
                self.assert_page_refuses(
                    '{"x=' + head + '&tag": "v"}')

    def test_line_key_behind_each_head_character_refuses(self):
        for name, head in HEAD_CHARACTERS.items():
            with self.subTest(head=name):
                self.assert_page_refuses(
                    "x=" + head + "&tag: abc")

    def test_construct_character_split_from_its_letter_refuses(self):
        for name in FIRST_FOUR:
            with self.subTest(head=name):
                self.assert_page_refuses(
                    "title: see &" + HEAD_CHARACTERS[name]
                    + "tag rest")

    def test_angle_bracket_split_from_its_opening_letter_refuses(self):
        for name in FIRST_FOUR:
            with self.subTest(head=name):
                self.assert_page_refuses(
                    "title: <" + HEAD_CHARACTERS[name]
                    + "tag> rest")

    def test_end_to_end_extract_page_refuses(self):
        path = os.path.join(self.tmp.name, "page.md")
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(
                "---\ntitle: x=" + HEAD_CHARACTERS["zero_width_space"]
                + "&tag rest\n---\nbody text\n")
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            acquisition.extract_page(
                self.home, product_id="p-example", page_path=path,
                audit_date=AUDIT_DATE)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")


class TestR10_012Controls(Base):
    def test_plain_form_refuses(self):
        self.assert_page_refuses("title: x=&tag rest")

    def test_head_character_at_head_of_value_refuses(self):
        self.assert_page_refuses(
            "title: " + HEAD_CHARACTERS["zero_width_space"]
            + "&tag rest")

    def test_no_break_space_at_interior_position_refuses(self):
        self.assert_page_refuses("title: x= &tag rest")

    def test_json_raw_control_character_refuses(self):
        self.assert_page_refuses(
            '{"title": "x=' + HEAD_CHARACTERS["control_character_1"]
            + '&tag"}')

    def test_benign_interior_head_material_passes(self):
        block = ("title: x=" + HEAD_CHARACTERS["zero_width_space"]
                 + "plain words")
        self.assertEqual(self.page_front_matter(block), "body text")
        block = "title: a" + HEAD_CHARACTERS["zero_width_space"] + "b"
        self.assertEqual(self.page_front_matter(block), "body text")


if __name__ == "__main__":
    unittest.main()
