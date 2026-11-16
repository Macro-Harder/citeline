"""Step 17 round 11 fix seat F2 tests, registry and acquisition.

Test first pins for register entry S17-R11-001, merged
from registry S17-R11-REG-001, seams
S17-R11-SEAMS-001, and red S17-R11-RED-07. Each defect
test reproduces the defect named at that entry: the
page side construct judgement in acquisition.py reads
the follower of the construct character as a plain
alphabet letter alone at its non start judged
positions, while the import side reading judges any
word character or a hyphen, so a construct whose name
opens on a digit, an underscore, a hyphen, or a letter
outside the plain alphabet passes the page reading
whole where the import reading refuses it. The pins
stand at every judged position, in the line form and
in the JSON form, at the value position and at the
key position alike, in plain form and standing behind
interior head material alike, and each pin asserts the
two readings together, the page reading refusing with
PAGE_EXTRACTION_FAILED and the import reading
refusing with IMPORT_VALIDATION_FAILED.
"""

import json
import os
import tempfile
import unittest

from citeline import acquisition
from citeline import probe_import as import_module

AUDIT_DATE = "2026-11-15"
BODY = "body text"

FOLLOWERS = (
    "&1", "&9a", "&_a", "&-a", "!9", "*2", "%0",
    "&é", "&üa", "*ß", "&Ω",
)

HEAD = "​"


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
        text = "---\n" + block + "\n---\n" + BODY + "\n"
        notes = []
        return acquisition._front_matter(text, "markdown", notes)

    def assert_page_refuses(self, block):
        with self.assertRaises(acquisition.AcquisitionError) as caught:
            self.page_front_matter(block)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def assert_import_refuses(self, block):
        text = "---\n" + block + "\n---\n" + BODY + "\n"
        with self.assertRaises(Exception) as caught:
            import_module.extract_front_matter(text)
        self.assertEqual(_token(caught.exception),
                         "IMPORT_VALIDATION_FAILED")

    def assert_both_refuse(self, block):
        self.assert_page_refuses(block)
        self.assert_import_refuses(block)


class TestR11_001FollowerSet(Base):
    def test_line_value_followers_refuse_at_both_readings(self):
        for follower in FOLLOWERS:
            with self.subTest(follower=follower):
                self.assert_both_refuse("title: x." + follower)

    def test_json_value_followers_refuse_at_both_readings(self):
        for follower in FOLLOWERS:
            with self.subTest(follower=follower):
                block = json.dumps(
                    {"title": "x." + follower}, ensure_ascii=False)
                self.assert_both_refuse(block)

    def test_line_key_followers_refuse_at_both_readings(self):
        for follower in FOLLOWERS:
            with self.subTest(follower=follower):
                self.assert_both_refuse("x." + follower + ": abc")

    def test_json_key_followers_refuse_at_both_readings(self):
        for follower in FOLLOWERS:
            with self.subTest(follower=follower):
                block = json.dumps(
                    {"x." + follower: "v"}, ensure_ascii=False)
                self.assert_both_refuse(block)

    def test_json_nested_value_and_key_followers_refuse(self):
        for follower in ("&1", "&_a", "&é"):
            with self.subTest(follower=follower):
                block = json.dumps(
                    {"outer": ["x." + follower]}, ensure_ascii=False)
                self.assert_both_refuse(block)
                block = json.dumps(
                    {"outer": {"x." + follower: "v"}},
                    ensure_ascii=False)
                self.assert_both_refuse(block)

    def test_continuation_line_followers_refuse_at_page(self):
        for follower in ("&1", "&_a", "&-a", "&é"):
            with self.subTest(follower=follower):
                self.assert_page_refuses(
                    "title: first line\n x." + follower + " continued")

    def test_behind_interior_head_between_position_and_construct(self):
        for follower in ("&1", "&_a", "&é"):
            with self.subTest(follower=follower):
                self.assert_both_refuse(
                    "title: x=" + HEAD + follower + " rest")
                block = json.dumps(
                    {"title": "x=" + HEAD + follower},
                    ensure_ascii=False)
                self.assert_both_refuse(block)

    def test_behind_interior_head_between_construct_and_follower(self):
        for follower in ("1", "_a", "é"):
            with self.subTest(follower=follower):
                self.assert_both_refuse(
                    "title: x.&" + HEAD + follower + " rest")
                block = json.dumps(
                    {"x.&" + HEAD + follower: "v"},
                    ensure_ascii=False)
                self.assert_both_refuse(block)

    def test_end_to_end_extract_page_refuses(self):
        for follower in ("&1", "&_a", "&é"):
            with self.subTest(follower=follower):
                path = os.path.join(self.tmp.name, "page.md")
                with open(path, "w", encoding="utf-8",
                          newline="") as handle:
                    handle.write(
                        "---\ntitle: x." + follower
                        + "\n---\nbody text\n")
                with self.assertRaises(
                        acquisition.AcquisitionError) as caught:
                    acquisition.extract_page(
                        self.home, product_id="p-example",
                        page_path=path, audit_date=AUDIT_DATE)
                self.assertEqual(_token(caught.exception),
                                 "PAGE_EXTRACTION_FAILED")


class TestR11_001Controls(Base):
    def test_plain_letter_follower_refuses_at_both_readings(self):
        self.assert_both_refuse("title: x.&tag rest")

    def test_start_of_value_construct_refuses_on_every_follower(self):
        for follower in FOLLOWERS:
            with self.subTest(follower=follower):
                self.assert_both_refuse("title: " + follower + "abc")

    def test_benign_text_with_wide_characters_passes(self):
        block = "title: plain 1 _ - é words standing here"
        self.assertEqual(self.page_front_matter(block), BODY)
        body, had = import_module.extract_front_matter(
            "---\n" + block + "\n---\n" + BODY + "\n")
        self.assertTrue(had)
        self.assertEqual(body, BODY)

    def test_construct_with_space_follower_passes(self):
        block = "title: x & rest of the words"
        self.assertEqual(self.page_front_matter(block), BODY)

    def test_interior_head_benign_form_passes(self):
        block = "title: x=" + HEAD + "plain words"
        self.assertEqual(self.page_front_matter(block), BODY)


if __name__ == "__main__":
    unittest.main()
