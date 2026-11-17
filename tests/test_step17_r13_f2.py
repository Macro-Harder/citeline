"""Registry and acquisition.

Test first pins for register, merged from registry and red, with
the page side limb of inside the same cure. Entry reproduces the
defect named at that entry: the import side cure at judges a
combining mark by general category Mn at any code point, while
the page side limb of _fm_holds_tag_construct in acquisition.py
stands in the landed range form U+0300 to U+036F alone, so a
construct whose name opens on a category Mn mark standing
outside that range and outside the word character set passes the
page reading whole at its judged positions, in the line form and
in the JSON form, at the value position and at the key position
alike, where the import reading refuses the same block. The page
side limb of stands on ruling (c) of the round 13 disposition:
the generic combining mark term of stands as the union of the
mark categories Mn, Mc, and Me, so a construct whose name opens
on a mark of category Mc or of category Me stands refused at the
page reading at the judged positions, the import side of that
entry standing charged to seat F4 as lead and landing after this
seat in the dependency order. The Mc and Me pins therefore
assert the page reading alone. The pins stand at every judged
position the entries name, in plain form, in JSON escape form,
and standing behind interior head material alike, beside sweeps
of the page side helper over every code point of the three mark
categories."""

import json
import os
import tempfile
import unicodedata
import unittest

from citeline import acquisition
from citeline import probe_import as import_module

AUDIT_DATE = "2026-11-15"
BODY = "body text"

CONSTRUCTS = ("&", "*", "%", "!")

MN_MARKS = (
    "\u0483", "\u0591", "\u064b", "\u0670", "\u06d6",
    "\u20d0", "\u3099", "\ufe20", "\U00001ab0", "\u1dc0",
)

MC_MARKS = (
    "\u0903", "\u093b", "\u0bbe", "\U0001d165", "\u093e",
)

ME_MARKS = (
    "\u20dd", "\u20e3", "\ua670", "\u0488",
)

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

    def assert_end_to_end_page_refuses(self, block):
        path = os.path.join(self.tmp.name, "page.md")
        with open(path, "w", encoding="utf-8",
                  newline="") as handle:
            handle.write(
                "---\n" + block + "\n---\nbody text\n")
        with self.assertRaises(
                acquisition.AcquisitionError) as caught:
            acquisition.extract_page(
                self.home, product_id="p-example",
                page_path=path, audit_date=AUDIT_DATE)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")


class TestR13_001MnOutsideRange(Base):
    def test_mn_battery_stands_as_charged(self):
        for mark in MN_MARKS:
            with self.subTest(mark=repr(mark)):
                self.assertEqual(
                    unicodedata.category(mark), "Mn")
                self.assertFalse(
                    "\u0300" <= mark <= "\u036f")
                self.assertFalse(mark.isalnum())
                self.assertNotEqual(mark, "_")

    def test_line_value_mn_refuse_at_both_readings(self):
        for construct in CONSTRUCTS:
            for mark in MN_MARKS:
                with self.subTest(construct=construct,
                                  mark=repr(mark)):
                    self.assert_both_refuse(
                        "title: x." + construct + mark + "a")

    def test_json_value_mn_refuse_at_both_readings(self):
        for construct in CONSTRUCTS:
            for mark in MN_MARKS:
                with self.subTest(construct=construct,
                                  mark=repr(mark)):
                    block = json.dumps(
                        {"title": "x." + construct + mark + "a"},
                        ensure_ascii=False)
                    self.assert_both_refuse(block)

    def test_line_key_mn_refuse_at_both_readings(self):
        for construct in CONSTRUCTS:
            for mark in MN_MARKS:
                with self.subTest(construct=construct,
                                  mark=repr(mark)):
                    self.assert_both_refuse(
                        "x." + construct + mark + "a: abc")

    def test_json_key_mn_refuse_at_both_readings(self):
        for construct in CONSTRUCTS:
            for mark in MN_MARKS:
                with self.subTest(construct=construct,
                                  mark=repr(mark)):
                    block = json.dumps(
                        {"x." + construct + mark + "a": "v"},
                        ensure_ascii=False)
                    self.assert_both_refuse(block)

    def test_json_nested_mn_refuse_at_page(self):
        for mark in ("\u0483", "\u20d0", "\u3099"):
            with self.subTest(mark=repr(mark)):
                block = json.dumps(
                    {"outer": ["x.&" + mark + "a"]},
                    ensure_ascii=False)
                self.assert_page_refuses(block)
                block = json.dumps(
                    {"outer": {"x.&" + mark + "a": "v"}},
                    ensure_ascii=False)
                self.assert_page_refuses(block)

    def test_continuation_line_mn_refuse_at_page(self):
        for mark in ("\u0483", "\u20d0", "\ufe20", "\u3099"):
            with self.subTest(mark=repr(mark)):
                self.assert_page_refuses(
                    "title: first line\n x.&" + mark
                    + "a continued")

    def test_mn_behind_interior_head_refuse_at_both_readings(self):
        for mark in ("\u0483", "\u20d0", "\u3099"):
            with self.subTest(mark=repr(mark)):
                self.assert_both_refuse(
                    "title: x=" + HEAD + "&" + mark + "a rest")
                self.assert_both_refuse(
                    "title: x.&" + HEAD + mark + "a rest")
                block = json.dumps(
                    {"title": "x.&" + HEAD + mark + "a"},
                    ensure_ascii=False)
                self.assert_both_refuse(block)

    def test_json_escape_mn_refuse_at_both_readings(self):
        block = '{"title": "x.&\\u0483a"}'
        self.assert_both_refuse(block)
        block = '{"x.&\\u20d0a": "v"}'
        self.assert_both_refuse(block)

    def test_end_to_end_mn_refuse_at_page(self):
        for mark in ("\u0483", "\u3099"):
            with self.subTest(mark=repr(mark)):
                self.assert_end_to_end_page_refuses(
                    "title: x.&" + mark + "a")
        block = json.dumps(
            {"x.&" + "\u20d0" + "a": "v"}, ensure_ascii=False)
        self.assert_end_to_end_page_refuses(block)
        self.assert_end_to_end_page_refuses(
            "title: x.&" + HEAD + "\u3099" + "a")

    def test_mn_at_flow_and_own_word_positions_refuse_at_both(self):
        for mark in ("\u0483", "\u20d0"):
            with self.subTest(mark=repr(mark)):
                self.assert_both_refuse(
                    "title: some words &" + mark + "a here")
                self.assert_both_refuse(
                    "title: x [&" + mark + "a, b]")
                self.assert_both_refuse(
                    "title: x,&" + mark + "a")
                self.assert_both_refuse(
                    "title: x:&" + mark + "a rest")
                block = json.dumps(
                    {"title": "x [&" + mark + "a, b]"},
                    ensure_ascii=False)
                self.assert_both_refuse(block)

    def test_page_helper_holds_every_mn_code_point(self):
        divergent = []
        for code in range(0x110000):
            mark = chr(code)
            if unicodedata.category(mark) != "Mn":
                continue
            if not acquisition._fm_holds_tag_construct(
                    "x.&" + mark + "a"):
                divergent.append(code)
        self.assertEqual(divergent, [])

    def test_page_and_import_helpers_agree_on_every_mn_code_point(self):
        divergent = []
        for code in range(0x110000):
            mark = chr(code)
            if unicodedata.category(mark) != "Mn":
                continue
            page = acquisition._fm_holds_tag_construct(
                "x.&" + mark + "a")
            import_side = import_module._holds_tag_construct(
                "x.&" + mark + "a")
            if page != import_side:
                divergent.append(code)
        self.assertEqual(divergent, [])


class TestR13_004PageLimb(Base):
    def test_mc_me_battery_stands_as_charged(self):
        for mark in MC_MARKS:
            with self.subTest(mark=repr(mark)):
                self.assertEqual(
                    unicodedata.category(mark), "Mc")
        for mark in ME_MARKS:
            with self.subTest(mark=repr(mark)):
                self.assertEqual(
                    unicodedata.category(mark), "Me")

    def test_line_value_mc_me_refuse_at_page(self):
        for construct in CONSTRUCTS:
            for mark in MC_MARKS + ME_MARKS:
                with self.subTest(construct=construct,
                                  mark=repr(mark)):
                    self.assert_page_refuses(
                        "title: x." + construct + mark + "a")

    def test_json_value_mc_me_refuse_at_page(self):
        for construct in CONSTRUCTS:
            for mark in MC_MARKS + ME_MARKS:
                with self.subTest(construct=construct,
                                  mark=repr(mark)):
                    block = json.dumps(
                        {"title": "x." + construct + mark + "a"},
                        ensure_ascii=False)
                    self.assert_page_refuses(block)

    def test_line_key_mc_me_refuse_at_page(self):
        for construct in CONSTRUCTS:
            for mark in MC_MARKS + ME_MARKS:
                with self.subTest(construct=construct,
                                  mark=repr(mark)):
                    self.assert_page_refuses(
                        "x." + construct + mark + "a: abc")

    def test_json_key_mc_me_refuse_at_page(self):
        for construct in CONSTRUCTS:
            for mark in MC_MARKS + ME_MARKS:
                with self.subTest(construct=construct,
                                  mark=repr(mark)):
                    block = json.dumps(
                        {"x." + construct + mark + "a": "v"},
                        ensure_ascii=False)
                    self.assert_page_refuses(block)

    def test_json_nested_mc_me_refuse_at_page(self):
        for mark in ("\u0903", "\u20dd", "\u0488"):
            with self.subTest(mark=repr(mark)):
                block = json.dumps(
                    {"outer": ["x.&" + mark + "a"]},
                    ensure_ascii=False)
                self.assert_page_refuses(block)
                block = json.dumps(
                    {"outer": {"x.&" + mark + "a": "v"}},
                    ensure_ascii=False)
                self.assert_page_refuses(block)

    def test_continuation_line_mc_me_refuse_at_page(self):
        for mark in ("\u0903", "\u093e", "\u20dd"):
            with self.subTest(mark=repr(mark)):
                self.assert_page_refuses(
                    "title: first line\n x.&" + mark
                    + "a continued")

    def test_mc_me_behind_interior_head_refuse_at_page(self):
        for mark in ("\u0903", "\u20dd", "\u0488"):
            with self.subTest(mark=repr(mark)):
                self.assert_page_refuses(
                    "title: x=" + HEAD + "&" + mark + "a rest")
                self.assert_page_refuses(
                    "title: x.&" + HEAD + mark + "a rest")
                block = json.dumps(
                    {"x.&" + HEAD + mark + "a": "v"},
                    ensure_ascii=False)
                self.assert_page_refuses(block)

    def test_json_escape_mc_me_refuse_at_page(self):
        block = '{"title": "x.&\\u0903a"}'
        self.assert_page_refuses(block)
        block = '{"x.&\\u20dda": "v"}'
        self.assert_page_refuses(block)

    def test_end_to_end_mc_me_refuse_at_page(self):
        for mark in ("\u0903", "\u20dd"):
            with self.subTest(mark=repr(mark)):
                self.assert_end_to_end_page_refuses(
                    "title: x.&" + mark + "a")

    def test_mc_me_at_flow_and_own_word_positions_refuse_at_page(self):
        for mark in ("\u0903", "\u20dd"):
            with self.subTest(mark=repr(mark)):
                self.assert_page_refuses(
                    "title: some words &" + mark + "a here")
                self.assert_page_refuses(
                    "title: x [&" + mark + "a, b]")
                self.assert_page_refuses(
                    "title: x,&" + mark + "a")
                self.assert_page_refuses(
                    "title: x:&" + mark + "a rest")
                block = json.dumps(
                    {"title": "x [&" + mark + "a, b]"},
                    ensure_ascii=False)
                self.assert_page_refuses(block)

    def test_page_helper_holds_every_mc_and_me_code_point(self):
        divergent = []
        for code in range(0x110000):
            mark = chr(code)
            if unicodedata.category(mark) not in ("Mc", "Me"):
                continue
            if not acquisition._fm_holds_tag_construct(
                    "x.&" + mark + "a"):
                divergent.append(code)
        self.assertEqual(divergent, [])


class TestR13Controls(Base):
    def test_range_marks_still_refuse_at_both_readings(self):
        for mark in ("\u0301", "\u036f"):
            with self.subTest(mark=repr(mark)):
                self.assert_both_refuse("title: x.&" + mark + "a")

    def test_word_covered_marks_still_refuse_at_both_readings(self):
        for mark in ("\u0610", "\ufe00"):
            with self.subTest(mark=repr(mark)):
                self.assert_both_refuse("title: x.&" + mark + "a")

    def test_cured_sets_stand_whole_at_page(self):
        for opening in (".", "+", "$", "~", ";", "/", "=",
                        "@", "^", "`", "\u203f"):
            with self.subTest(opening=repr(opening)):
                self.assert_page_refuses(
                    "title: x.&" + opening + "a")
        for opening in ("?", "\\", "(", ")", "<", ":"):
            with self.subTest(opening=repr(opening)):
                self.assert_page_refuses(
                    "title: x.&" + opening + "a")
        self.assert_both_refuse("title: x.&tag rest")
        self.assert_both_refuse("title: x.&1 rest")

    def test_start_of_value_construct_refuses_on_mark_openings(self):
        for mark in ("\u0483", "\u0903", "\u20dd"):
            with self.subTest(mark=repr(mark)):
                self.assert_page_refuses(
                    "title: &" + mark + "abc")

    def test_benign_forms_still_pass(self):
        self.assert_both_pass(
            "title: plain . + $ ~ words standing here")
        self.assert_page_passes("title: x & rest of the words")
        self.assert_page_passes(
            "title: x=" + HEAD + "plain words")
        for follower in ("'", "#", ",", "|", '"', ">"):
            with self.subTest(follower=follower):
                self.assert_both_pass(
                    "title: x.&" + follower + "a rest")


if __name__ == "__main__":
    unittest.main()
