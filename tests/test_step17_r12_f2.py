"""Registry and acquisition.

Test first pins for register, merged from registry, seams, and
red, with the page side limb of inside the same cure. Each
defect test reproduces the defect named at that entry: the page
side construct judgement in acquisition.py reads the follower of
the construct character as any word character or a hyphen alone,
while the import side reading judges any word character or a
hyphen beside the twelve widened openings, a full stop, a plus
sign, a dollar sign, a tilde, a semicolon, a slash, an equals
sign, an at sign, a caret, a backtick, a combining mark, and an
undertie, so a construct whose name opens on one of those
openings passes the page reading whole where the import reading
refuses it. The page side limb of stands on the six further
openings that entry names, a question mark, a backslash, an
opening parenthesis, a closing parenthesis, a less than sign,
and a colon, which pass both readings on the uncured tree and
stand refused at the page reading on the cured tree, their
import side limb standing charged to the repair. The pins stand at
every judged position, in the line form and in the JSON form, at
the value position and at the key position alike, in plain form
and standing behind interior head material alike."""

import json
import os
import tempfile
import unittest

from citeline import acquisition
from citeline import probe_import as import_module

AUDIT_DATE = "2026-11-15"
BODY = "body text"

CONSTRUCTS = ("&", "*", "%", "!")

WIDENED = (
    ".", "+", "$", "~", ";", "/", "=", "@", "^", "`",
    "\u0301", "\u203f",
)

FURTHER = ("?", "\\", "(", ")", "<", ":")

HEAD = "\u200b"


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

    def assert_page_passes(self, block):
        self.assertEqual(self.page_front_matter(block), BODY)

    def assert_both_pass(self, block):
        self.assert_page_passes(block)
        body, had = import_module.extract_front_matter(
            "---\n" + block + "\n---\n" + BODY + "\n")
        self.assertTrue(had)
        self.assertEqual(body, BODY)


class TestR12_001WidenedOpenings(Base):
    def test_line_value_widened_refuse_at_both_readings(self):
        for construct in CONSTRUCTS:
            for opening in WIDENED:
                with self.subTest(construct=construct, opening=repr(opening)):
                    self.assert_both_refuse(
                        "title: x." + construct + opening + "a")

    def test_json_value_widened_refuse_at_both_readings(self):
        for construct in CONSTRUCTS:
            for opening in WIDENED:
                with self.subTest(construct=construct, opening=repr(opening)):
                    block = json.dumps(
                        {"title": "x." + construct + opening + "a"},
                        ensure_ascii=False)
                    self.assert_both_refuse(block)

    def test_line_key_widened_refuse_at_both_readings(self):
        for construct in CONSTRUCTS:
            for opening in WIDENED:
                with self.subTest(construct=construct, opening=repr(opening)):
                    self.assert_both_refuse(
                        "x." + construct + opening + "a: abc")

    def test_json_key_widened_refuse_at_both_readings(self):
        for construct in CONSTRUCTS:
            for opening in WIDENED:
                with self.subTest(construct=construct, opening=repr(opening)):
                    block = json.dumps(
                        {"x." + construct + opening + "a": "v"},
                        ensure_ascii=False)
                    self.assert_both_refuse(block)

    def test_json_nested_widened_refuse_at_both_readings(self):
        for opening in (".", "+", "\u203f", "\u0301"):
            with self.subTest(opening=repr(opening)):
                block = json.dumps(
                    {"outer": ["x.&" + opening + "a"]},
                    ensure_ascii=False)
                self.assert_both_refuse(block)
                block = json.dumps(
                    {"outer": {"x.&" + opening + "a": "v"}},
                    ensure_ascii=False)
                self.assert_both_refuse(block)

    def test_continuation_line_widened_refuse_at_page(self):
        for opening in (".", "+", "$", "\u203f"):
            with self.subTest(opening=repr(opening)):
                self.assert_page_refuses(
                    "title: first line\n x.&" + opening + "a continued")

    def test_widened_behind_interior_head_between_position_and_construct(self):
        for opening in (".", "+", "\u203f"):
            with self.subTest(opening=repr(opening)):
                self.assert_both_refuse(
                    "title: x=" + HEAD + "&" + opening + "a rest")
                block = json.dumps(
                    {"title": "x=" + HEAD + "&" + opening + "a"},
                    ensure_ascii=False)
                self.assert_both_refuse(block)

    def test_widened_behind_interior_head_between_construct_and_opening(self):
        for opening in (".", "+", "\u203f"):
            with self.subTest(opening=repr(opening)):
                self.assert_both_refuse(
                    "title: x.&" + HEAD + opening + "a rest")
                block = json.dumps(
                    {"x.&" + HEAD + opening + "a": "v"},
                    ensure_ascii=False)
                self.assert_both_refuse(block)

    def test_widened_at_own_word_flow_and_separator_positions(self):
        for opening in (".", "+", "\u203f"):
            with self.subTest(opening=repr(opening)):
                self.assert_both_refuse(
                    "title: word &" + opening + "a rest")
                self.assert_both_refuse(
                    "title: x[&" + opening + "a]")
                self.assert_both_refuse(
                    "title: x,&" + opening + "a")

    def test_end_to_end_widened_refuse_at_page(self):
        for opening in (".", "+", "\u203f"):
            with self.subTest(opening=repr(opening)):
                path = os.path.join(self.tmp.name, "page.md")
                with open(path, "w", encoding="utf-8",
                          newline="") as handle:
                    handle.write(
                        "---\ntitle: x.&" + opening + "a"
                        + "\n---\nbody text\n")
                with self.assertRaises(
                        acquisition.AcquisitionError) as caught:
                    acquisition.extract_page(
                        self.home, product_id="p-example",
                        page_path=path, audit_date=AUDIT_DATE)
                self.assertEqual(_token(caught.exception),
                                 "PAGE_EXTRACTION_FAILED")


class TestR12_008PageLimb(Base):
    def test_line_value_further_refuse_at_page(self):
        for construct in CONSTRUCTS:
            for opening in FURTHER:
                with self.subTest(construct=construct, opening=repr(opening)):
                    self.assert_page_refuses(
                        "title: x." + construct + opening + "a")

    def test_json_value_further_refuse_at_page(self):
        for construct in CONSTRUCTS:
            for opening in FURTHER:
                with self.subTest(construct=construct, opening=repr(opening)):
                    block = json.dumps(
                        {"title": "x." + construct + opening + "a"},
                        ensure_ascii=False)
                    self.assert_page_refuses(block)

    def test_line_key_further_refuse_at_page(self):
        for opening in ("?", "\\", "(", ")", "<"):
            with self.subTest(opening=repr(opening)):
                self.assert_page_refuses("x.&" + opening + "a: abc")

    def test_json_key_further_refuse_at_page(self):
        for opening in FURTHER:
            with self.subTest(opening=repr(opening)):
                block = json.dumps(
                    {"x.&" + opening + "a": "v"}, ensure_ascii=False)
                self.assert_page_refuses(block)

    def test_json_nested_further_refuse_at_page(self):
        for opening in ("?", "\\", ":"):
            with self.subTest(opening=repr(opening)):
                block = json.dumps(
                    {"outer": ["x.&" + opening + "a"]},
                    ensure_ascii=False)
                self.assert_page_refuses(block)
                block = json.dumps(
                    {"outer": {"x.&" + opening + "a": "v"}},
                    ensure_ascii=False)
                self.assert_page_refuses(block)

    def test_continuation_and_interior_head_further_refuse_at_page(self):
        for opening in ("?", "\\"):
            with self.subTest(opening=repr(opening)):
                self.assert_page_refuses(
                    "title: first line\n x.&" + opening + "a continued")
        for opening in ("?", "\\", ":"):
            with self.subTest(opening=repr(opening)):
                self.assert_page_refuses(
                    "title: x=" + HEAD + "&" + opening + "a rest")
                self.assert_page_refuses(
                    "title: x.&" + HEAD + opening + "a rest")

    def test_end_to_end_further_refuse_at_page(self):
        for opening in ("?", "\\", ":"):
            with self.subTest(opening=repr(opening)):
                path = os.path.join(self.tmp.name, "page.md")
                with open(path, "w", encoding="utf-8",
                          newline="") as handle:
                    handle.write(
                        "---\ntitle: x.&" + opening + "a"
                        + "\n---\nbody text\n")
                with self.assertRaises(
                        acquisition.AcquisitionError) as caught:
                    acquisition.extract_page(
                        self.home, product_id="p-example",
                        page_path=path, audit_date=AUDIT_DATE)
                self.assertEqual(_token(caught.exception),
                                 "PAGE_EXTRACTION_FAILED")


class TestR12Controls(Base):
    def test_plain_letter_follower_refuses_at_both_readings(self):
        self.assert_both_refuse("title: x.&tag rest")

    def test_cured_set_follower_refuses_at_both_readings(self):
        self.assert_both_refuse("title: x.&1 rest")
        self.assert_both_refuse("title: x.&-a rest")

    def test_start_of_value_construct_refuses_on_every_opening(self):
        for opening in WIDENED + FURTHER:
            with self.subTest(opening=repr(opening)):
                self.assert_page_refuses("title: &" + opening + "abc")

    def test_benign_text_with_wide_characters_passes(self):
        block = "title: plain . + $ ~ words standing here"
        self.assert_both_pass(block)

    def test_construct_with_space_follower_passes_at_page(self):
        self.assert_page_passes("title: x & rest of the words")

    def test_interior_head_benign_form_passes_at_page(self):
        self.assert_page_passes("title: x=" + HEAD + "plain words")

    def test_followers_outside_charged_sets_pass_at_both_readings(self):
        for follower in ("'", "#", ",", "|", '"', ">"):
            with self.subTest(follower=follower):
                self.assert_both_pass("title: x.&" + follower + "a rest")


if __name__ == "__main__":
    unittest.main()
