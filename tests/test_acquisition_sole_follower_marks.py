"""Registry and acquisition.

Test first pins for register. The entry reproduces the defect
named at that entry, filed as registry: a mark of the union of
general category Mn, Mc, or Me that also stands as head material
passes the page reading whole where it stands as the sole
follower of a construct character, with nothing judged standing
after it, because the interior head reading
_fm_remove_interior_head in acquisition.py removes the mark
before the follower judgement of _fm_holds_tag_construct runs,
so the category reading the repair cures land never
reaches it. On this machine Unicode 15.0.0 tables the head set
holds 282 marks of the union, every one of category Mn, standing
in eight ranges: U+034F alone, U+0610 to U+061A, U+17B4 to
U+17B5, U+180B to U+180D, U+180F alone, U+FE00 to U+FE0F,
U+1D17B to U+1D182, and U+E0100 to U+E01EF. The pins stand at
the page reading and at the page side helper, in the line form
and in the JSON form, at the value position and at the key
position alike, in plain form and in JSON escape form alike,
beside sweeps of the page side helper over every code point of
the union at the sole follower positions. The import side limb
of the entry stands inside the F4 charge of this repair wave and lands
after this repair in the dependency order, so the defect pins
assert the page reading alone, in the form the page side limb
pins of the repair took. The controls assert both readings
where the standing the control names already stands at both."""

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

HEAD_MARKS = (
    "\u034f", "\u0610", "\u061a", "\u17b4", "\u17b5",
    "\u180b", "\u180d", "\u180f", "\ufe00", "\ufe0f",
    "\U0001d17b", "\U0001d182", "\U000e0100",
    "\U000e01ef",
)

HEAD_RANGES = (
    (0x034F, 0x034F), (0x0610, 0x061A),
    (0x17B4, 0x17B5), (0x180B, 0x180D),
    (0x180F, 0x180F), (0xFE00, 0xFE0F),
    (0x1D17B, 0x1D182), (0xE0100, 0xE01EF),
)

HEAD = "\u200b"


def _token(exc):
    return getattr(exc, "token", None) or getattr(
        exc, "error_value", None)


def _head_union_code_points():
    return [
        code for code in range(0x110000)
        if unicodedata.category(chr(code)) in (
            "Mn", "Mc", "Me")
        and acquisition._fm_is_head_char(chr(code))]


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


class TestR14_001SoleFollowerHeadMarks(Base):
    def test_head_union_battery_stands_as_charged(self):
        found = _head_union_code_points()
        self.assertEqual(len(found), 282)
        for code in found:
            with self.subTest(code=hex(code)):
                self.assertEqual(
                    unicodedata.category(chr(code)), "Mn")
                self.assertTrue(any(
                    low <= code <= high
                    for low, high in HEAD_RANGES))
        for mark in HEAD_MARKS:
            with self.subTest(mark=repr(mark)):
                self.assertEqual(
                    unicodedata.category(mark), "Mn")
                self.assertTrue(
                    acquisition._fm_is_head_char(mark))

    def test_line_value_sole_follower_at_end_refuses_at_page(self):
        for construct in CONSTRUCTS:
            for mark in HEAD_MARKS:
                with self.subTest(construct=construct,
                                  mark=repr(mark)):
                    self.assert_page_refuses(
                        "title: x." + construct + mark)

    def test_line_value_sole_follower_before_space_refuses_at_page(self):
        for construct in CONSTRUCTS:
            for mark in HEAD_MARKS:
                with self.subTest(construct=construct,
                                  mark=repr(mark)):
                    self.assert_page_refuses(
                        "title: x." + construct + mark
                        + " rest")

    def test_line_key_sole_follower_refuses_at_page(self):
        for construct in CONSTRUCTS:
            for mark in HEAD_MARKS:
                with self.subTest(construct=construct,
                                  mark=repr(mark)):
                    self.assert_page_refuses(
                        "x." + construct + mark + ": abc")

    def test_json_value_sole_follower_refuses_at_page(self):
        for construct in CONSTRUCTS:
            for mark in HEAD_MARKS:
                with self.subTest(construct=construct,
                                  mark=repr(mark)):
                    block = json.dumps(
                        {"title": "x." + construct + mark},
                        ensure_ascii=False)
                    self.assert_page_refuses(block)
                    block = json.dumps(
                        {"title": "x." + construct + mark
                         + " rest"},
                        ensure_ascii=False)
                    self.assert_page_refuses(block)

    def test_json_key_sole_follower_refuses_at_page(self):
        for construct in CONSTRUCTS:
            for mark in HEAD_MARKS:
                with self.subTest(construct=construct,
                                  mark=repr(mark)):
                    block = json.dumps(
                        {"x." + construct + mark: "v"},
                        ensure_ascii=False)
                    self.assert_page_refuses(block)

    def test_json_nested_sole_follower_refuses_at_page(self):
        for mark in ("\u034f", "\ufe0f", "\U000e0100"):
            with self.subTest(mark=repr(mark)):
                block = json.dumps(
                    {"outer": ["x.&" + mark]},
                    ensure_ascii=False)
                self.assert_page_refuses(block)
                block = json.dumps(
                    {"outer": {"x.&" + mark: "v"}},
                    ensure_ascii=False)
                self.assert_page_refuses(block)

    def test_continuation_line_sole_follower_refuses_at_page(self):
        for mark in ("\u034f", "\u17b4", "\ufe0f",
                     "\U000e0100"):
            with self.subTest(mark=repr(mark)):
                self.assert_page_refuses(
                    "title: first line\n x.&" + mark)

    def test_json_escape_sole_follower_refuses_at_page(self):
        self.assert_page_refuses(
            '{"title": "x.&\\ufe0f"}')
        self.assert_page_refuses(
            '{"x.&\\ufe0f": "v"}')
        self.assert_page_refuses(
            '{"title": "x.&\\u034f"}')

    def test_doubled_and_head_dressed_sole_followers_refuse_at_page(self):
        mark = "\ufe0f"
        self.assert_page_refuses("title: x.&" + mark + mark)
        self.assert_page_refuses(
            "title: x.&" + mark + HEAD)
        self.assert_page_refuses(
            "title: x.&" + HEAD + mark)
        self.assert_page_refuses(
            "title: x=" + HEAD + "&" + mark)
        block = json.dumps(
            {"title": "x.&" + mark + HEAD},
            ensure_ascii=False)
        self.assert_page_refuses(block)

    def test_sole_follower_at_flow_and_own_word_positions_refuses(self):
        mark = "\ufe0f"
        self.assert_page_refuses(
            "title: some words &" + mark)
        self.assert_page_refuses(
            "title: x [&" + mark + ", b]")
        self.assert_page_refuses("title: x,&" + mark)
        self.assert_page_refuses(
            "title: x:&" + mark + " rest")
        block = json.dumps(
            {"title": "x [&" + mark + ", b]"},
            ensure_ascii=False)
        self.assert_page_refuses(block)

    def test_end_to_end_sole_follower_refuses_at_page(self):
        for mark in ("\u034f", "\ufe0f", "\U000e0100"):
            with self.subTest(mark=repr(mark)):
                self.assert_end_to_end_page_refuses(
                    "title: x.&" + mark)
        self.assert_end_to_end_page_refuses(
            "title: x.&" + "\ufe0f" + " rest")

    def test_page_helper_holds_every_union_mark_at_end(self):
        divergent = []
        for code in range(0x110000):
            mark = chr(code)
            if unicodedata.category(mark) not in (
                    "Mn", "Mc", "Me"):
                continue
            if not acquisition._fm_holds_tag_construct(
                    "x.&" + mark):
                divergent.append(code)
        self.assertEqual(divergent, [])

    def test_page_helper_holds_every_union_mark_before_space(self):
        divergent = []
        for code in range(0x110000):
            mark = chr(code)
            if unicodedata.category(mark) not in (
                    "Mn", "Mc", "Me"):
                continue
            if not acquisition._fm_holds_tag_construct(
                    "x.&" + mark + " rest"):
                divergent.append(code)
        self.assertEqual(divergent, [])

    def test_page_helper_holds_the_head_set_at_sole_follower(self):
        divergent = []
        for code in _head_union_code_points():
            mark = chr(code)
            for text in ("x.&" + mark,
                         "x.&" + mark + " rest",
                         "x.&" + mark + HEAD):
                if not acquisition._fm_holds_tag_construct(
                        text):
                    divergent.append((code, repr(text)))
        self.assertEqual(divergent, [])


class TestR14Controls(Base):
    def test_page_helper_holds_every_union_mark_in_name_form(self):
        divergent = []
        for code in range(0x110000):
            mark = chr(code)
            if unicodedata.category(mark) not in (
                    "Mn", "Mc", "Me"):
                continue
            if not acquisition._fm_holds_tag_construct(
                    "x.&" + mark + "a"):
                divergent.append(code)
        self.assertEqual(divergent, [])

    def test_page_helper_refuses_no_follower_outside_the_sets(self):
        landed = set("-.+$~;/=@^`?\\()<:") | {"\u203f"}
        divergent = []
        for code in range(0x110000):
            char = chr(code)
            if acquisition._fm_is_head_char(char):
                continue
            expected = bool(
                char.isalnum() or char == "_"
                or char in landed
                or unicodedata.category(char) in (
                    "Mn", "Mc", "Me"))
            held = acquisition._fm_holds_tag_construct(
                "x.&" + char)
            if held != expected:
                divergent.append(code)
        self.assertEqual(divergent, [])

    def test_non_head_sole_followers_refuse_at_both_readings(self):
        for mark in ("\u0483", "\u0903", "\u20dd"):
            with self.subTest(mark=repr(mark)):
                self.assert_both_refuse("title: x.&" + mark)
                self.assert_both_refuse(
                    "title: x.&" + mark + " rest")

    def test_head_marks_in_name_form_refuse_at_both_readings(self):
        for mark in ("\u034f", "\u0610", "\ufe0f",
                     "\U000e0100"):
            with self.subTest(mark=repr(mark)):
                self.assert_both_refuse(
                    "title: x.&" + mark + "a")

    def test_head_mark_before_full_stop_refuses_at_both(self):
        self.assert_both_refuse("title: x.&" + "\ufe0f" + ".")
        self.assert_both_refuse("title: x.&" + "\u034f" + ".")

    def test_start_of_value_head_mark_sole_follower_refuses(self):
        for mark in ("\u034f", "\ufe0f"):
            with self.subTest(mark=repr(mark)):
                self.assert_page_refuses("title: &" + mark)

    def test_cured_sets_stand_whole_at_page(self):
        for opening in (".", "+", "$", "~", ";", "/", "=",
                        "@", "^", "`", "\u0301", "\u203f"):
            with self.subTest(opening=repr(opening)):
                self.assert_page_refuses(
                    "title: x.&" + opening + "a")
        for opening in ("?", "\\", "(", ")", "<", ":"):
            with self.subTest(opening=repr(opening)):
                self.assert_page_refuses(
                    "title: x.&" + opening + "a")
        self.assert_both_refuse("title: x.&tag rest")
        self.assert_both_refuse("title: x.&1 rest")

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
                self.assert_page_passes(
                    "title: x.&" + follower)

    def test_non_union_head_sole_follower_still_passes_at_page(self):
        self.assert_page_passes("title: x.&" + HEAD)
        self.assert_page_passes(
            "title: x.&" + HEAD + " rest")


if __name__ == "__main__":
    unittest.main()
