"""Step 17 round 16 fix seat F2 tests, registry and acquisition.

Test first pins for register entries S17-R16-009,
S17-R16-010, and S17-R16-011, each Low. Entry
S17-R16-009: a sole category Lo follower separated
from its construct by one head gap character passes
at both readings, the follower judgement of the
position scan standing on the character immediately
after the construct character while the older
readings remove the gap and the follower together.
Entry S17-R16-010: pair forms with a head gap
character in front of a mark follower pass at both
readings, the scan unable to reach the mark past
the gap and the older readings consuming the second
construct judged position at the first finditer
match. Entry S17-R16-011: the two worked pair forms
of entry S17-R16-010 stand refused at the import
line key position and passed at the page line key
position on the same block text, the import key
judgement running its helper on the judged key and
on the key past its head material and the page key
judgement running its helper on the key past its
head material alone.

The defect pins assert the page side alone, in the
form the page side limb pins of the earlier rounds
took: the import side limbs of entries S17-R16-009
and S17-R16-010 stand inside the F4 charge of this
wave and land after this seat in the dependency
order, by the cure rule this seat states in its
paper. Entry S17-R16-011 stands at the page key
judgement alone, with no F4 limb. The controls
assert both readings where the standing the control
names already stands at both, and assert the page
reading where a control names a page standing the
scan cure moves, in the form the entry states.
Every pin runs in memory at the readings and at the
helpers, so no pin stands on a temporary directory.
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


def _page_key_judgement_holds(key):
    return bool(
        acquisition._fm_holds_tag_construct(
            acquisition._fm_judged_key(key))
        or acquisition._fm_holds_tag_construct(
            acquisition._fm_strip_head(key)))


def _import_key_judgement_holds(key):
    return bool(
        import_module._holds_tag_construct(
            import_module._judged_key(key))
        or import_module._holds_tag_construct(
            import_module._strip_head(key)))


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
            acquisition._fm_holds_tag_construct(text),
            "helper passes %r" % (text,))

    def assert_helper_passes(self, text):
        self.assertFalse(
            acquisition._fm_holds_tag_construct(text),
            "helper holds %r" % (text,))


class TestR16_009SoleFollowerPastGap(Base):
    def test_worked_form_holds_at_page_helper(self):
        self.assert_helper_holds(SOLE_009)
        self.assert_helper_holds(SOLE_009 + " rest")
        self.assert_helper_holds(SOLE_009 + " ")

    def test_single_construct_sweep_holds_whole_at_page(self):
        passing = []
        for prefix in PREFIXES:
            for gap in GAPS:
                for follower in SWEEP_FOLLOWERS:
                    text = prefix + "&" + gap + follower
                    if not acquisition._fm_holds_tag_construct(
                            text):
                        passing.append(text)
        self.assertEqual(passing, [])

    def test_every_gap_and_lo_follower_form_holds_at_page(self):
        for gap in HEAD_NON_MARK_GAPS:
            for follower in LO_FOLLOWERS:
                for construct in ("&", "*", "%", "!"):
                    with self.subTest(
                            gap=hex(ord(gap)),
                            follower=hex(ord(follower)),
                            construct=construct):
                        self.assert_helper_holds(
                            "x." + construct + gap + follower)

    def test_worked_form_refuses_at_page_readings(self):
        self.assert_page_refuses("title: " + SOLE_009 + " rest")
        self.assert_page_refuses(SOLE_009 + ": abc")
        block = json.dumps({"title": SOLE_009},
                           ensure_ascii=False)
        self.assert_page_refuses(block)

    def test_bounded_set_sole_followers_still_pass(self):
        for char in BOUNDED_HEAD:
            with self.subTest(char=hex(ord(char))):
                self.assert_helper_passes("x &" + char)
                self.assert_page_passes("title: x &" + char)
                self.assert_page_passes(
                    "title: x &" + char + " rest")

    def test_bounded_follower_behind_a_gap_still_passes(self):
        for char in BOUNDED_HEAD:
            with self.subTest(char=hex(ord(char))):
                self.assert_helper_passes(
                    "x &\u200b" + char)
                self.assert_helper_passes(
                    "x &\u200b" + char + " rest")
        self.assert_helper_passes("x &\u200b\u200b")


class TestR16_010PairPastGap(Base):
    def test_worked_forms_hold_at_page_helper(self):
        self.assert_helper_holds(PAIR_010_A)
        self.assert_helper_holds(PAIR_010_B)

    def test_pair_sweep_holds_whole_at_page(self):
        passing = []
        for prefix in PREFIXES:
            for pair in PAIRS:
                for gap in GAPS:
                    for follower in SWEEP_FOLLOWERS:
                        text = prefix + pair + gap + follower
                        if not acquisition._fm_holds_tag_construct(
                                text):
                            passing.append(text)
        self.assertEqual(passing, [])

    def test_apart_pair_forms_hold_at_page(self):
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

    def test_worked_forms_refuse_at_page_readings(self):
        for text in (PAIR_010_A, PAIR_010_B):
            with self.subTest(text=repr(text)):
                self.assert_page_refuses("title: " + text)
                self.assert_page_refuses(
                    "title: [" + text + "]")
                self.assert_page_refuses(
                    "title: first line\n " + text)
                block = json.dumps({"title": text},
                                   ensure_ascii=False)
                self.assert_page_refuses(block)
                block = json.dumps({text: "v"},
                                   ensure_ascii=False)
                self.assert_page_refuses(block)
                block = json.dumps({"outer": {"k": text}},
                                   ensure_ascii=False)
                self.assert_page_refuses(block)
                block = json.dumps({"outer": [text]},
                                   ensure_ascii=False)
                self.assert_page_refuses(block)

    def test_pair_controls_stand_as_they_stood(self):
        self.assert_helper_holds("/*&\u20dd?")
        self.assert_helper_holds(";&\u00a0%\u0903*")
        self.assert_helper_holds(SOLE_009.replace(
            "\u200b", ""))
        self.assert_both_pass("title: x & rest of the words")


class TestR16_011LineKeyJudgement(Base):
    def test_worked_pair_keys_refuse_at_both_readings(self):
        for text in (PAIR_010_A, PAIR_010_B):
            with self.subTest(text=repr(text)):
                self.assert_page_refuses(text + ": abc")
                self.assert_import_refuses(text + ": abc")

    def test_key_judgement_forms_stand_in_agreement(self):
        # The agreement stands judged at the extraction
        # readings on every sweep form where the two
        # helpers themselves stand in agreement on both
        # key texts, the judged key and the key past its
        # head material. The forms standing outside that
        # ground stand on the helper divergence alone,
        # the page helper standing cured by this seat
        # and the import helper standing inside the F4
        # charge of this wave, in the form the seat
        # paper states.
        divergent = []
        for prefix in PREFIXES:
            for pair in PAIRS:
                for gap in GAPS:
                    for follower in SWEEP_FOLLOWERS:
                        key = prefix + pair + gap + follower
                        if acquisition._fm_holds_tag_construct(
                                acquisition._fm_judged_key(
                                    key)) != (
                                import_module
                                ._holds_tag_construct(
                                    import_module._judged_key(
                                        key))):
                            continue
                        if acquisition._fm_holds_tag_construct(
                                acquisition._fm_strip_head(
                                    key)) != (
                                import_module
                                ._holds_tag_construct(
                                    import_module._strip_head(
                                        key))):
                            continue
                        try:
                            self.page_front_matter(
                                key + ": abc")
                            page_refuses = False
                        except acquisition.AcquisitionError:
                            page_refuses = True
                        try:
                            self.assert_import_passes(
                                key + ": abc")
                            import_refuses = False
                        except AssertionError:
                            import_refuses = True
                        except Exception:
                            import_refuses = True
                        if page_refuses != import_refuses:
                            divergent.append(key)
        self.assertEqual(divergent, [])

    def test_judged_key_only_forms_refuse_at_page_line_key(self):
        self.assert_page_refuses("x &\u200b\u115f: abc")
        self.assert_page_refuses("x &\u2060\u3164: abc")

    def test_json_key_judgement_form_stands_as_import(self):
        for text in (PAIR_010_A, PAIR_010_B):
            with self.subTest(text=repr(text)):
                block = json.dumps({text: "v"},
                                   ensure_ascii=False)
                self.assert_page_refuses(block)

    def test_benign_keys_still_pass_at_both_readings(self):
        self.assert_both_pass("title: plain value here")
        self.assert_both_pass("x & rest: abc")
        self.assert_page_passes("title: x &\u200b rest")


if __name__ == "__main__":
    unittest.main()
