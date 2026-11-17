"""Step 17 round 15 fix seat F4 tests, import family.

Test first pins for the import side limbs of register
entries S17-R15-002, S17-R15-003, and S17-R15-010, each
Low, each counted at its lead seat F2, cured at the
import side helper _holds_tag_construct in
probe_import.py and at the import reading, in the form
the F2 cure rule states for this seat. Entry
S17-R15-002: a head union mark standing between a
judged position and a construct character blocks the
cure at both readings, the except marks reading
keeping the blocker and the interior head reading
removing blocker and follower together, so no reading
presents the judged position, the construct, and the
mark follower together. Entry S17-R15-003: both
category follower loops run one non overlapping
finditer pass whose match consumes its judged
position, construct, and follower characters, so a
second construct standing directly after a first, or
after a space the first match consumed, is never
judged on the mark ground. Entry S17-R15-010: exactly
four category Lo head material characters, U+115F,
U+1160, U+3164, and U+FFA0, pass both readings whole
as sole follower of a construct character, each one
standing in the follower set through the word
character limb of entry S17-R11-001 with no head
material exception standing in that limb.

The defect pins assert the import reading and the
import side helper alone, in the form the import side
limb pins of fix round 14 took: the page side limbs of
the three entries stand cured at seat F2 in this wave
ahead of this seat in the dependency order. The
controls assert both readings where the standing the
control names already stands at both. Every pin runs
in memory at the readings and at the helpers, so no
pin stands on a temporary directory.
"""

import json
import unicodedata
import unittest

from citeline import acquisition
from citeline import probe_import as import_module

BODY = "body text"

CONSTRUCTS = ("&", "*", "%", "!")

HEAD = "\u200b"
BLOCKER = "\u034f"
FOLLOWER = "\ufe0f"

LO_FOLLOWERS = ("\u115f", "\u1160", "\u3164", "\uffa0")

BOUNDED_HEAD = ("\u200b", "\u00ad", "\u061c", "\u2060",
                "\U000e0041")

LANDED_EXTRA = set("-.+$~;/=@^`?\\()<:") | {"\u203f"}


def _token(exc):
    return getattr(exc, "token", None) or getattr(
        exc, "error_value", None)


def _head_union_code_points():
    return [
        code for code in range(0x110000)
        if unicodedata.category(chr(code)) in (
            "Mn", "Mc", "Me")
        and import_module._is_head_char(chr(code))]


def _union_code_points():
    return [
        code for code in range(0x110000)
        if unicodedata.category(chr(code)) in (
            "Mn", "Mc", "Me")]


def _in_landed_follower_set(char):
    return bool(
        char.isalnum() or char == "_"
        or char in LANDED_EXTRA
        or unicodedata.category(char) in (
            "Mn", "Mc", "Me"))


class Base(unittest.TestCase):
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

    def assert_import_passes(self, block):
        body, had = import_module.extract_front_matter(
            "---\n" + block + "\n---\n" + BODY + "\n")
        self.assertTrue(had)
        self.assertEqual(body, BODY)

    def assert_both_pass(self, block):
        self.assertEqual(self.page_front_matter(block), BODY)
        self.assert_import_passes(block)

    def assert_helper_holds(self, text):
        self.assertTrue(
            import_module._holds_tag_construct(text),
            "helper passes %r" % (text,))

    def assert_helper_passes(self, text):
        self.assertFalse(
            import_module._holds_tag_construct(text),
            "helper holds %r" % (text,))


class TestR15_002BlockerImport(Base):
    def test_head_union_battery_stands_as_charged(self):
        found = _head_union_code_points()
        self.assertEqual(len(found), 282)
        for code in found:
            with self.subTest(code=hex(code)):
                self.assertEqual(
                    unicodedata.category(chr(code)), "Mn")
                self.assertTrue(
                    import_module._is_head_char(chr(code)))

    def test_helper_misses_no_head_union_mark_as_blocker(self):
        divergent = []
        for code in _head_union_code_points():
            mark = chr(code)
            if not import_module._holds_tag_construct(
                    "x " + mark + "&" + FOLLOWER):
                divergent.append(code)
        self.assertEqual(divergent, [])

    def test_helper_misses_no_head_union_mark_as_follower(self):
        divergent = []
        for code in _head_union_code_points():
            mark = chr(code)
            if not import_module._holds_tag_construct(
                    "x " + BLOCKER + "&" + mark):
                divergent.append(code)
        self.assertEqual(divergent, [])

    def test_line_value_blocker_form_refuses_at_import(self):
        for construct in CONSTRUCTS:
            with self.subTest(construct=construct):
                self.assert_import_refuses(
                    "title: x " + BLOCKER + construct + FOLLOWER)
                self.assert_import_refuses(
                    "title: x." + BLOCKER + construct + FOLLOWER)
        for separator in (".", ",", ":", '"', "[", "]"):
            with self.subTest(separator=separator):
                self.assert_helper_holds(
                    "x" + separator + BLOCKER + "&" + FOLLOWER)
        self.assert_helper_holds(
            "x " + BLOCKER + BLOCKER + "&" + FOLLOWER)
        self.assert_helper_holds(
            "x " + FOLLOWER + "&" + BLOCKER)
        self.assert_helper_holds(
            "x " + HEAD + BLOCKER + "&" + FOLLOWER)

    def test_blocker_form_at_end_and_before_space_refuses(self):
        self.assert_import_refuses(
            "title: x " + BLOCKER + "&" + FOLLOWER)
        self.assert_import_refuses(
            "title: x " + BLOCKER + "&" + FOLLOWER + " rest")
        self.assert_helper_holds(
            "x " + BLOCKER + "&" + FOLLOWER + ", rest")
        self.assert_helper_holds(
            "x " + BLOCKER + "&" + FOLLOWER + HEAD)

    def test_line_key_blocker_form_refuses_at_import(self):
        self.assert_import_refuses(
            "x " + BLOCKER + "&" + FOLLOWER + ": abc")
        self.assert_import_refuses(
            '"x ' + BLOCKER + "&" + FOLLOWER + '": abc')

    def test_json_blocker_forms_refuse_at_import(self):
        block = json.dumps(
            {"title": "x " + BLOCKER + "&" + FOLLOWER},
            ensure_ascii=False)
        self.assert_import_refuses(block)
        block = json.dumps(
            {"x " + BLOCKER + "&" + FOLLOWER: "v"},
            ensure_ascii=False)
        self.assert_import_refuses(block)
        block = json.dumps(
            {"outer": ["x", "x " + BLOCKER + "&" + FOLLOWER]},
            ensure_ascii=False)
        self.assert_import_refuses(block)
        block = json.dumps(
            {"outer": {"x " + BLOCKER + "&" + FOLLOWER: 1}},
            ensure_ascii=False)
        self.assert_import_refuses(block)

    def test_json_escape_and_continuation_blocker_forms(self):
        self.assert_import_refuses(
            '{"title": "x \\u034f&\\ufe0f"}')
        self.assert_import_refuses(
            '{"x \\u034f&\\ufe0f": "v"}')
        self.assert_import_refuses(
            "title: first line\n x " + BLOCKER + "&" + FOLLOWER)


class TestR15_003ConsumedPositionImport(Base):
    def test_helper_misses_no_union_mark_on_together(self):
        divergent = []
        for code in _union_code_points():
            mark = chr(code)
            if not import_module._holds_tag_construct(
                    "x.&&" + mark):
                divergent.append(code)
        self.assertEqual(divergent, [])

    def test_helper_misses_no_union_mark_on_apart(self):
        divergent = []
        for code in _union_code_points():
            mark = chr(code)
            if not import_module._holds_tag_construct(
                    "x & &" + mark):
                divergent.append(code)
        self.assertEqual(divergent, [])

    def test_pair_forms_refuse_at_helper(self):
        for follower in ("\ufe0f", "\u0483", "\u0903",
                         "\u20dd"):
            with self.subTest(follower=repr(follower)):
                self.assert_helper_holds("x.&&" + follower)
                self.assert_helper_holds("x & &" + follower)
        for pair in ("&&", "**", "%%", "!!", "&*", "%!"):
            with self.subTest(pair=pair):
                self.assert_helper_holds("x." + pair + FOLLOWER)
        self.assert_helper_holds("x & &\u034f")
        self.assert_helper_holds("x.&&\u034f")

    def test_line_pair_forms_refuse_at_import(self):
        self.assert_import_refuses("title: x.&&" + FOLLOWER)
        self.assert_import_refuses("title: x & &" + FOLLOWER)
        self.assert_import_refuses("title: x.&&\u0903")
        self.assert_import_refuses("x.&&" + FOLLOWER + ": abc")

    def test_json_pair_forms_refuse_at_import(self):
        block = json.dumps(
            {"title": "x.&&" + FOLLOWER}, ensure_ascii=False)
        self.assert_import_refuses(block)
        block = json.dumps(
            {"x.&&" + FOLLOWER: "v"}, ensure_ascii=False)
        self.assert_import_refuses(block)
        block = json.dumps(
            {"title": "x & &" + FOLLOWER}, ensure_ascii=False)
        self.assert_import_refuses(block)


class TestR15_010LoFollowersImport(Base):
    def test_lo_head_follower_set_stands_at_exactly_four(self):
        found = []
        for code in range(0x110000):
            char = chr(code)
            if not import_module._is_head_char(char):
                continue
            if unicodedata.category(char) in (
                    "Mn", "Mc", "Me"):
                continue
            if _in_landed_follower_set(char):
                found.append(code)
        self.assertEqual(
            found, [0x115F, 0x1160, 0x3164, 0xFFA0])
        for char in LO_FOLLOWERS:
            with self.subTest(char=hex(ord(char))):
                self.assertEqual(
                    unicodedata.category(char), "Lo")
                self.assertTrue(
                    import_module._is_head_char(char))

    def test_helper_holds_every_lo_follower_form(self):
        for char in LO_FOLLOWERS:
            with self.subTest(char=hex(ord(char))):
                self.assert_helper_holds("x &" + char)
                self.assert_helper_holds("x &" + char + " rest")
                self.assert_helper_holds("x &" + char + HEAD)
                self.assert_helper_holds("x.&" + char)

    def test_line_lo_follower_forms_refuse_at_import(self):
        for char in LO_FOLLOWERS:
            with self.subTest(char=hex(ord(char))):
                self.assert_import_refuses("title: x &" + char)
                self.assert_import_refuses(
                    "title: x &" + char + " rest")
                self.assert_import_refuses("x &" + char + ": abc")

    def test_json_lo_follower_forms_refuse_at_import(self):
        for char in LO_FOLLOWERS:
            with self.subTest(char=hex(ord(char))):
                block = json.dumps(
                    {"title": "x &" + char},
                    ensure_ascii=False)
                self.assert_import_refuses(block)
                block = json.dumps(
                    {"x &" + char: "v"}, ensure_ascii=False)
                self.assert_import_refuses(block)
        self.assert_import_refuses(
            '{"title": "x &\\u115f"}')
        self.assert_import_refuses(
            '{"title": "x &\\u3164"}')

    def test_flow_list_lo_follower_refuses_at_import(self):
        for char in LO_FOLLOWERS:
            with self.subTest(char=hex(ord(char))):
                self.assert_import_refuses(
                    "title: [a, &" + char + "]")


class TestR15AgreementSweep(Base):
    def test_helpers_agree_on_charged_templates_whole_union(self):
        divergent = []

        def check(text):
            page = acquisition._fm_holds_tag_construct(text)
            imp = import_module._holds_tag_construct(text)
            if page != imp:
                divergent.append(text)

        for code in _union_code_points():
            mark = chr(code)
            check("x.&" + mark)
            check("x.&&" + mark)
            check("x & &" + mark)
            check("x " + BLOCKER + "&" + mark)
        for code in _head_union_code_points():
            mark = chr(code)
            check("x " + mark + "&" + FOLLOWER)
        for char in LO_FOLLOWERS:
            check("x &" + char)
            check("x &" + char + " rest")
            check("x.&" + char)
        for char in BOUNDED_HEAD:
            check("x &" + char)
            check("x &" + char + " rest")
        self.assertEqual(divergent, [])


class TestR15ControlsImport(Base):
    def test_002_controls_refuse_at_both_readings(self):
        self.assert_both_refuse(
            "title: x " + HEAD + "&" + FOLLOWER)
        self.assert_both_refuse(
            "title: x " + BLOCKER + "&a")
        self.assert_both_refuse(
            "title: x " + BLOCKER + "&\u0483")
        self.assert_both_refuse(
            "title: x " + BLOCKER + "&\u0301")
        self.assert_both_refuse("title: x.&" + FOLLOWER + ".")
        self.assert_import_refuses(
            "title: " + BLOCKER + "&" + FOLLOWER)

    def test_003_controls_stand_as_they_stood(self):
        self.assert_both_refuse("title: x.&&a")
        self.assert_import_refuses("title: x.&" + FOLLOWER)
        self.assert_helper_holds("x.&&\u0301")
        self.assert_both_pass("title: x & rest of the words")

    def test_010_name_and_union_controls_refuse_at_both(self):
        for char in LO_FOLLOWERS:
            with self.subTest(char=hex(ord(char))):
                self.assert_both_refuse("title: x &" + char + "a")
        self.assert_both_refuse("title: x &" + FOLLOWER)
        self.assert_both_refuse("title: x &\u0483")

    def test_bounded_head_sole_followers_still_pass(self):
        for char in BOUNDED_HEAD:
            with self.subTest(char=hex(ord(char))):
                self.assert_helper_passes("x &" + char)
                self.assert_import_passes("title: x &" + char)
                self.assert_import_passes(
                    "title: x &" + char + " rest")

    def test_benign_and_non_union_followers_unchanged(self):
        self.assert_both_pass(
            "title: plain . + $ ~ words standing here")
        self.assert_import_passes("title: x & rest of the words")
        for follower in ("'", "#", ",", "|", '"', ">"):
            with self.subTest(follower=follower):
                self.assert_both_pass(
                    "title: x.&" + follower + "a rest")
                self.assert_import_passes(
                    "title: x.&" + follower)
        self.assert_import_passes("title: x.&" + HEAD)
        self.assert_import_passes(
            "title: x.&" + HEAD + " rest")

    def test_landed_range_and_charged_templates_still_refuse(self):
        for mark in ("\u0300", "\u0301", "\u034f", "\u036f"):
            with self.subTest(mark=repr(mark)):
                self.assert_import_refuses("title: x.&" + mark)
        self.assert_import_refuses("title: x.&&\u0301")
        divergent = []
        for code in _union_code_points():
            mark = chr(code)
            if not import_module._holds_tag_construct(
                    "x.&" + mark):
                divergent.append(code)
        self.assertEqual(divergent, [])
        self.assert_import_refuses(
            "title: x.&" + FOLLOWER + " rest")

    def test_letter_position_with_head_between_still_passes(self):
        self.assert_helper_passes("xa" + HEAD + "&" + FOLLOWER)
        self.assert_import_passes(
            "title: xa" + HEAD + "&" + FOLLOWER)
        self.assert_helper_passes("xa" + BLOCKER + "&" + FOLLOWER)


if __name__ == "__main__":
    unittest.main()
