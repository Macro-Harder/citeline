"""Step 17 round 16 fix seat F4 tests, import family.

Test first pins for the import side limbs of register
entries S17-R16-009 and S17-R16-010, each Low, each
counted at its lead seat F2, cured at the import side
helper _holds_tag_construct in probe_import.py, at its
position scan _position_scan_holds, in the form the F2
cure rule states for this seat. Entry S17-R16-009: a
sole category Lo follower separated from its construct
by one head gap character passes at both readings, the
follower judgement of the position scan standing on
the character immediately after the construct
character while the older readings remove the gap and
the follower together. Entry S17-R16-010: pair forms
with a head gap character in front of a mark follower
pass at both readings, the scan unable to reach the
mark past the gap and the older readings consuming
the second construct judged position at the first
finditer match. No limb of entry S17-R16-011 stands
inside this charge: its cure stands at the page key
judgement alone and the import judgement stands as
the form that cure matches.

The defect pins assert the import reading and the
import side helper alone, in the form the import side
limb pins of the earlier rounds took: the page side
limbs of the two entries stand cured at seat F2 in
this wave ahead of this seat in the dependency order.
The controls assert both readings where the standing
the control names already stands at both. Every pin
runs in memory at the readings and at the helpers, so
no pin stands on a temporary directory.
"""

import json
import unittest

from citeline import acquisition
from citeline import probe_import as import_module

BODY = "body text"

GAPS = ("\u200b", "\u00ad", "\u061c", "\u2060",
        "\u2061", "\U000e0041", "\ufeff", "\u180f")

HEAD_NON_MARK_GAPS = ("\u200b", "\u00ad", "\u061c",
                      "\u2060", "\u2061",
                      "\U000e0041", "\ufeff")

SWEEP_FOLLOWERS = ("\u0301", "\u0483", "\u0903",
                   "\u20dd", "\ufe0f", "\u034f",
                   "\u115f", "\u3164")

LO_FOLLOWERS = ("\u115f", "\u3164")

PREFIXES = ("x.", "x ", ".", " ")

PAIRS = ("&&", "**", "%%", "!!", "&*", "*&", "%!",
         "!%")

BOUNDED_HEAD = ("\u200b", "\u00ad", "\u061c", "\u2060",
                "\U000e0041")

SOLE_009 = ".\u0026\u200b\u115f"

PAIR_010_A = "/*&\u2060\u20dd?"
PAIR_010_B = ";&\u00a0%\u00ad\u0903*"


def _token(exc):
    return getattr(exc, "token", None) or getattr(
        exc, "error_value", None)


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

    def assert_page_passes(self, block):
        self.assertEqual(self.page_front_matter(block), BODY)

    def assert_import_passes(self, block):
        body, had = import_module.extract_front_matter(
            "---\n" + block + "\n---\n" + BODY + "\n")
        self.assertTrue(had)
        self.assertEqual(body, BODY)

    def assert_both_pass(self, block):
        self.assert_page_passes(block)
        self.assert_import_passes(block)

    def assert_helper_holds(self, text):
        self.assertTrue(
            import_module._holds_tag_construct(text),
            "helper passes %r" % (text,))

    def assert_helper_passes(self, text):
        self.assertFalse(
            import_module._holds_tag_construct(text),
            "helper holds %r" % (text,))


class TestR16_009SoleFollowerPastGapImport(Base):
    def test_worked_form_holds_at_import_helper(self):
        self.assert_helper_holds(SOLE_009)
        self.assert_helper_holds(SOLE_009 + " rest")
        self.assert_helper_holds(SOLE_009 + " ")
        self.assert_helper_holds("x.&\u200b\u2060\u115f")

    def test_single_construct_sweep_holds_whole_at_import(self):
        passing = []
        for prefix in PREFIXES:
            for gap in GAPS:
                for follower in SWEEP_FOLLOWERS:
                    text = prefix + "&" + gap + follower
                    if not import_module._holds_tag_construct(
                            text):
                        passing.append(text)
        self.assertEqual(passing, [])

    def test_every_gap_and_lo_follower_form_holds_at_import(self):
        for gap in HEAD_NON_MARK_GAPS:
            for follower in LO_FOLLOWERS:
                for construct in ("&", "*", "%", "!"):
                    with self.subTest(
                            gap=hex(ord(gap)),
                            follower=hex(ord(follower)),
                            construct=construct):
                        self.assert_helper_holds(
                            "x." + construct + gap + follower)

    def test_worked_form_refuses_at_import_readings(self):
        self.assert_import_refuses("title: " + SOLE_009 + " rest")
        self.assert_import_refuses(SOLE_009 + ": abc")
        block = json.dumps({"title": SOLE_009},
                           ensure_ascii=False)
        self.assert_import_refuses(block)

    def test_worked_form_json_escape_refuses_at_import(self):
        self.assert_import_refuses(
            '{"title": ".&\\u200b\\u115f"}')
        self.assert_import_refuses(
            '{"title": ".&\\u2060\\u3164"}')

    def test_bounded_set_sole_followers_still_pass(self):
        for char in BOUNDED_HEAD:
            with self.subTest(char=hex(ord(char))):
                self.assert_helper_passes("x &" + char)
                self.assert_import_passes("title: x &" + char)
                self.assert_import_passes(
                    "title: x &" + char + " rest")

    def test_bounded_follower_behind_a_gap_still_passes(self):
        for char in BOUNDED_HEAD:
            with self.subTest(char=hex(ord(char))):
                self.assert_helper_passes(
                    "x &\u200b" + char)
                self.assert_helper_passes(
                    "x &\u200b" + char + " rest")
        self.assert_helper_passes("x &\u200b\u200b")

    def test_gap_controls_stand_as_they_stood(self):
        self.assert_helper_holds("x.&\u200b\u0301")
        self.assert_helper_holds("x.&\u200b\u20dd")
        self.assert_helper_passes("x.&\u00a0\u20dd")
        self.assert_helper_passes("x.&\u00a0\u115f")


class TestR16_010PairPastGapImport(Base):
    def test_worked_forms_hold_at_import_helper(self):
        self.assert_helper_holds(PAIR_010_A)
        self.assert_helper_holds(PAIR_010_B)

    def test_pair_sweep_holds_whole_at_import(self):
        passing = []
        for prefix in PREFIXES:
            for pair in PAIRS:
                for gap in GAPS:
                    for follower in SWEEP_FOLLOWERS:
                        text = prefix + pair + gap + follower
                        if not import_module._holds_tag_construct(
                                text):
                            passing.append(text)
        self.assertEqual(passing, [])

    def test_apart_pair_forms_hold_at_import(self):
        for separator in ("\u00a0", " "):
            for gap in HEAD_NON_MARK_GAPS:
                for follower in ("\u0903", "\u20dd",
                                 "\u0301"):
                    with self.subTest(
                            separator=repr(separator),
                            gap=hex(ord(gap)),
                            follower=hex(ord(follower))):
                        self.assert_helper_holds(
                            "x;&" + separator + "%" + gap
                            + follower + "*")

    def test_worked_forms_refuse_at_import_readings(self):
        for text in (PAIR_010_A, PAIR_010_B):
            with self.subTest(text=repr(text)):
                self.assert_import_refuses("title: " + text)
                self.assert_import_refuses(
                    "title: [" + text + "]")
                self.assert_import_refuses(
                    "title: first line\n " + text)
                block = json.dumps({"title": text},
                                   ensure_ascii=False)
                self.assert_import_refuses(block)
                block = json.dumps({text: "v"},
                                   ensure_ascii=False)
                self.assert_import_refuses(block)
                block = json.dumps({"outer": {"k": text}},
                                   ensure_ascii=False)
                self.assert_import_refuses(block)
                block = json.dumps({"outer": [text]},
                                   ensure_ascii=False)
                self.assert_import_refuses(block)

    def test_pair_controls_stand_as_they_stood(self):
        self.assert_helper_holds("/*&\u20dd?")
        self.assert_helper_holds(";&\u00a0%\u0903*")
        self.assert_helper_holds(SOLE_009.replace(
            "\u200b", ""))
        self.assert_both_pass("title: x & rest of the words")


class TestR16AgreementImport(Base):
    def test_helpers_agree_on_the_charged_forms(self):
        divergent = []
        judged = [0]

        def check(text):
            judged[0] += 1
            page = acquisition._fm_holds_tag_construct(text)
            imp = import_module._holds_tag_construct(text)
            if page != imp:
                divergent.append(text)

        for prefix in PREFIXES:
            for gap in GAPS:
                for follower in SWEEP_FOLLOWERS:
                    check(prefix + "&" + gap + follower)
        for prefix in PREFIXES:
            for pair in PAIRS:
                for gap in GAPS:
                    for follower in SWEEP_FOLLOWERS:
                        check(prefix + pair + gap + follower)
        for char in BOUNDED_HEAD:
            check("x &" + char)
            check("x &" + char + " rest")
            check("x &\u200b" + char)
        check(SOLE_009)
        check(PAIR_010_A)
        check(PAIR_010_B)
        check("/*&\u20dd?")
        check(";&\u00a0%\u0903*")
        check("x.&\u00a0\u20dd")
        self.assertEqual(judged[0], 2325)
        self.assertEqual(divergent, [])

    def test_readings_agree_on_the_worked_forms(self):
        for text in (SOLE_009, PAIR_010_A, PAIR_010_B):
            with self.subTest(text=repr(text)):
                self.assert_import_refuses("title: " + text)
                self.assert_page_refuses("title: " + text)
                self.assert_import_refuses(text + ": abc")
                self.assert_page_refuses(text + ": abc")
                block = json.dumps({"title": text},
                                   ensure_ascii=False)
                self.assert_import_refuses(block)
                self.assert_page_refuses(block)


if __name__ == "__main__":
    unittest.main()
