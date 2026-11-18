"""Import family, verdict form.

No entry stands charged in the repair: Section 3 of
the settled record enters no entry at the repair and no import side
limb of any entry, at the settled rule. These pins stand in the standing
verdict pin form: they pin the standings of the repair at this
repair as verified first hand on the cured tree, the import side
limbs of in citeline/probe_import.py at its position scan, in the
F2 rule exact form, over the charged forms and past them in the
broadened forms of the earlier round import paper, and the key
judgements of standing alike between the modules and inside each
module. The two F4 category count pins of test_step17_r13_f4.py
stand outside this file in their the settled rule form and no pin here
rests on them. Every pin runs in memory, so no pin stands on a
temporary directory."""

import json
import random
import unicodedata
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

PREFIXES = ("x.", "x ", ".", " ")

PAIRS = ("&&", "**", "%%", "!!", "&*", "*&", "%!",
         "!%")

BOUNDED_HEAD = ("\u200b", "\u00ad", "\u061c", "\u2060",
                "\U000e0041")

SOLE_009 = ".\u0026\u200b\u115f"
PAIR_010_A = "/*&\u2060\u20dd?"
PAIR_010_B = ";&\u00a0%\u00ad\u0903*"

BROAD_GAPS = (
    "\u200b", "\u00ad", "\u061c", "\u2060", "\u2061",
    "\U000e0041", "\ufeff",
    "\x00", "\x07", "\x0e", "\x1f", "\x7f", "\x86",
    "\x9f",
    "\u200c", "\u200d", "\u2062", "\u2063", "\u2064",
    "\u2066", "\u206a", "\u206f", "\u180e",
    "\U000e0001", "\U000e0020", "\U000e007f",
    "\ufff0", "\ufff8", "\U0001d173", "\U0001d17d",
    "\u180f", "\u180b", "\u034f", "\u0610", "\u17b4",
    "\U000e0100",
    "\u00a0", "\u202f", "\u3000", "\u2007", "\u2028",
    "\x0b", "\x1c")

BROAD_FOLLOWERS = SWEEP_FOLLOWERS + (
    "\uffa0", "a", "1", "-", "?", "_", "\u203f",
    "\U0001f600", "#", "}", '"', " ")

RUN_GAPS = ("\u200b", "\u00ad", "\x00", "\u200c",
            "\U000e0020", "\u2060", "\ufeff", "\u2063")


def _token(exc):
    return getattr(exc, "token", None) or getattr(
        exc, "error_value", None)


def _page_line_key_holds(key):
    return acquisition._fm_holds_tag_construct(
        acquisition._fm_judged_key(key)) or \
        acquisition._fm_holds_tag_construct(
            acquisition._fm_strip_head(key))


def _import_line_key_holds(key):
    return import_module._holds_tag_construct(
        import_module._judged_key(key)) or \
        import_module._holds_tag_construct(
            import_module._strip_head(key))


def _page_json_key_holds(key):
    return acquisition._fm_holds_tag_construct(
        acquisition._fm_strip_head(str(key).strip()))


def _import_json_key_holds(key):
    return import_module._holds_tag_construct(
        import_module._strip_head(str(key).strip()))


class Base(unittest.TestCase):
    def assert_page_refuses(self, block):
        text = "---\n" + block + "\n---\n" + BODY + "\n"
        notes = []
        with self.assertRaises(
                acquisition.AcquisitionError) as caught:
            acquisition._front_matter(text, "markdown", notes)
        self.assertEqual(_token(caught.exception),
                         "PAGE_EXTRACTION_FAILED")

    def assert_import_refuses(self, block):
        text = "---\n" + block + "\n---\n" + BODY + "\n"
        with self.assertRaises(Exception) as caught:
            import_module.extract_front_matter(text)
        self.assertEqual(_token(caught.exception),
                         "IMPORT_VALIDATION_FAILED")

    def assert_both_pass_value(self, block):
        text = "---\n" + block + "\n---\n" + BODY + "\n"
        notes = []
        self.assertEqual(
            acquisition._front_matter(text, "markdown", notes),
            BODY)
        body, had = import_module.extract_front_matter(text)
        self.assertTrue(had)
        self.assertEqual(body, BODY)


class TestMirrorForm(Base):
    def test_cure_sets_stand_equal_across_the_modules(self):
        self.assertEqual(
            import_module._JUDGED_POSITION_CHARS,
            acquisition._FM_JUDGED_POSITION_CHARS)
        self.assertEqual(
            import_module._WIDENED_FOLLOWER_CHARS,
            acquisition._FM_WIDENED_FOLLOWER_CHARS)
        self.assertEqual(
            import_module._DEFAULT_IGNORABLE_RANGES,
            acquisition._FM_DEFAULT_IGNORABLE_RANGES)

    def test_head_predicates_agree_on_the_whole_space(self):
        divergent = []
        for point in range(0x110000):
            if 0xD800 <= point <= 0xDFFF:
                continue
            char = chr(point)
            if import_module._is_head_char(char) != \
                    acquisition._fm_is_head_char(char):
                divergent.append(point)
        self.assertEqual(divergent, [])


class TestR16009Standing(Base):
    def test_worked_form_holds_at_both_helpers(self):
        for text in (SOLE_009, SOLE_009 + " rest",
                     SOLE_009 + " ",
                     "x.&\u200b\u2060\u115f"):
            with self.subTest(text=repr(text)):
                self.assertTrue(
                    import_module._holds_tag_construct(text))
                self.assertTrue(
                    acquisition._fm_holds_tag_construct(text))

    def test_single_construct_sweep_holds_whole(self):
        passing = []
        divergent = []
        for prefix in PREFIXES:
            for gap in GAPS:
                for follower in SWEEP_FOLLOWERS:
                    text = prefix + "&" + gap + follower
                    imp = import_module._holds_tag_construct(
                        text)
                    page = acquisition._fm_holds_tag_construct(
                        text)
                    if not imp:
                        passing.append(text)
                    if imp != page:
                        divergent.append(text)
        self.assertEqual(passing, [])
        self.assertEqual(divergent, [])

    def test_every_gap_and_lo_follower_form_holds(self):
        for gap in HEAD_NON_MARK_GAPS:
            for follower in ("\u115f", "\u3164"):
                for construct in ("&", "*", "%", "!"):
                    with self.subTest(
                            gap=hex(ord(gap)),
                            follower=hex(ord(follower)),
                            construct=construct):
                        text = "x." + construct + gap + follower
                        self.assertTrue(
                            import_module._holds_tag_construct(
                                text))
                        self.assertTrue(
                            acquisition._fm_holds_tag_construct(
                                text))

    def test_worked_form_refuses_at_the_readings(self):
        self.assert_import_refuses("title: " + SOLE_009 + " rest")
        self.assert_page_refuses("title: " + SOLE_009 + " rest")
        self.assert_import_refuses(SOLE_009 + ": abc")
        self.assert_page_refuses(SOLE_009 + ": abc")
        block = json.dumps({"title": SOLE_009},
                           ensure_ascii=False)
        self.assert_import_refuses(block)
        self.assert_page_refuses(block)
        self.assert_import_refuses(
            '{"title": ".&\\u200b\\u115f"}')
        self.assert_page_refuses(
            '{"title": ".&\\u200b\\u115f"}')


class TestR16010Standing(Base):
    def test_worked_forms_hold_at_both_helpers(self):
        for text in (PAIR_010_A, PAIR_010_B):
            with self.subTest(text=repr(text)):
                self.assertTrue(
                    import_module._holds_tag_construct(text))
                self.assertTrue(
                    acquisition._fm_holds_tag_construct(text))

    def test_pair_sweep_holds_whole(self):
        passing = []
        divergent = []
        for prefix in PREFIXES:
            for pair in PAIRS:
                for gap in GAPS:
                    for follower in SWEEP_FOLLOWERS:
                        text = prefix + pair + gap + follower
                        imp = import_module._holds_tag_construct(
                            text)
                        page = \
                            acquisition._fm_holds_tag_construct(
                                text)
                        if not imp:
                            passing.append(text)
                        if imp != page:
                            divergent.append(text)
        self.assertEqual(passing, [])
        self.assertEqual(divergent, [])

    def test_apart_pair_forms_hold_at_both_helpers(self):
        for separator in ("\u00a0", " "):
            for gap in HEAD_NON_MARK_GAPS:
                for follower in ("\u0903", "\u20dd",
                                 "\u0301"):
                    with self.subTest(
                            separator=repr(separator),
                            gap=hex(ord(gap)),
                            follower=hex(ord(follower))):
                        text = "x;&" + separator + "%" + gap \
                            + follower + "*"
                        self.assertTrue(
                            import_module._holds_tag_construct(
                                text))
                        self.assertTrue(
                            acquisition._fm_holds_tag_construct(
                                text))

    def test_worked_forms_refuse_at_the_readings(self):
        for text in (PAIR_010_A, PAIR_010_B):
            with self.subTest(text=repr(text)):
                for block in (
                        "title: " + text,
                        "title: [" + text + "]",
                        "title: first line\n " + text):
                    self.assert_import_refuses(block)
                    self.assert_page_refuses(block)
                for value in (
                        {"title": text}, {text: "v"},
                        {"outer": {"k": text}},
                        {"outer": [text]}):
                    block = json.dumps(value,
                                       ensure_ascii=False)
                    self.assert_import_refuses(block)
                    self.assert_page_refuses(block)


class TestPastTheChargedForms(Base):
    def test_broadened_gap_sweep_agrees_whole(self):
        divergent = []
        judged = 0
        for prefix in PREFIXES:
            for gap in BROAD_GAPS:
                for follower in BROAD_FOLLOWERS:
                    text = prefix + "&" + gap + follower
                    judged += 1
                    if import_module._holds_tag_construct(
                            text) != \
                            acquisition._fm_holds_tag_construct(
                                text):
                        divergent.append(text)
        self.assertEqual(judged, 3440)
        self.assertEqual(divergent, [])

    def test_gap_runs_agree_whole(self):
        divergent = []
        judged = 0
        for prefix in ("x.", "."):
            for first in RUN_GAPS:
                for second in RUN_GAPS:
                    for follower in SWEEP_FOLLOWERS[:6]:
                        text = prefix + "&" + first + second \
                            + follower
                        judged += 1
                        if import_module._holds_tag_construct(
                                text) != \
                                acquisition._fm_holds_tag_construct(
                                    text):
                            divergent.append(text)
        self.assertEqual(judged, 768)
        self.assertEqual(divergent, [])

    def test_template_gap_slot_scans_agree_on_whole_space(self):
        divergent = []
        for point in range(0x110000):
            if 0xD800 <= point <= 0xDFFF:
                continue
            text = ".&" + chr(point) + "\u115f"
            if import_module._position_scan_holds(text) != \
                    acquisition._fm_position_scan_holds(text):
                divergent.append(point)
        self.assertEqual(divergent, [])

    def test_template_follower_slot_scans_agree_on_space(self):
        divergent = []
        for point in range(0x110000):
            if 0xD800 <= point <= 0xDFFF:
                continue
            text = ".&\u200b" + chr(point)
            if import_module._position_scan_holds(text) != \
                    acquisition._fm_position_scan_holds(text):
                divergent.append(point)
        self.assertEqual(divergent, [])


class TestR16011KeyJudgements(Base):
    def _key_texts(self):
        texts = []
        for prefix in PREFIXES:
            for gap in GAPS:
                for follower in SWEEP_FOLLOWERS:
                    texts.append(prefix + "&" + gap + follower)
        for prefix in PREFIXES:
            for pair in PAIRS:
                for gap in GAPS:
                    for follower in SWEEP_FOLLOWERS:
                        texts.append(
                            prefix + pair + gap + follower)
        for gap in ("\u200c", "\u2063", "\x00", "\x07",
                    "\U000e0020", "\ufff0", "\U0001d173"):
            texts.append(".&" + gap + "\u115f")
            texts.append(".&&" + gap + "\u20dd")
            texts.append(".&" + gap + gap + "\u115f")
        rng = random.Random(1717)
        alphabet = list("&*%!.,:;-/+ $~=@^`?\\()<>") \
            + list(GAPS) + list(SWEEP_FOLLOWERS) \
            + ["a", "1", " ", "\u200c", "\x00",
               "\U000e0020", "\u00a0"]
        for _ in range(2000):
            size = rng.randint(1, 12)
            texts.append("".join(
                rng.choice(alphabet) for _ in range(size)))
        return texts

    def test_key_judgements_agree_between_the_modules(self):
        divergent = []
        for key in self._key_texts():
            if _import_line_key_holds(key) != \
                    _page_line_key_holds(key):
                divergent.append(("line", key))
            if _import_json_key_holds(key) != \
                    _page_json_key_holds(key):
                divergent.append(("json", key))
        self.assertEqual(divergent, [])

    def test_key_judgements_agree_inside_each_module(self):
        divergent = []
        for key in self._key_texts():
            if _import_line_key_holds(key) != \
                    _import_json_key_holds(key):
                divergent.append(("import", key))
            if _page_line_key_holds(key) != \
                    _page_json_key_holds(key):
                divergent.append(("page", key))
        self.assertEqual(divergent, [])

    def test_key_forms_refuse_and_pass_at_the_readings(self):
        for text in (SOLE_009, PAIR_010_A, PAIR_010_B,
                     ".&\u200c\u115f", ".&\x00\u115f",
                     ".&\U000e0020\u115f"):
            with self.subTest(text=repr(text)):
                self.assert_import_refuses(text + ": abc")
                self.assert_page_refuses(text + ": abc")
                block = json.dumps({text: "v"},
                                   ensure_ascii=False)
                self.assert_import_refuses(block)
                self.assert_page_refuses(block)
        self.assert_both_pass_value("title: x & rest")


class TestBoundedAndControls(Base):
    def test_bounded_set_sole_followers_still_pass(self):
        for char in BOUNDED_HEAD:
            with self.subTest(char=hex(ord(char))):
                self.assertFalse(
                    import_module._holds_tag_construct(
                        "x &" + char))
                self.assertFalse(
                    acquisition._fm_holds_tag_construct(
                        "x &" + char))
                self.assert_both_pass_value(
                    "title: x &" + char)

    def test_bounded_follower_behind_a_gap_still_passes(self):
        for char in BOUNDED_HEAD:
            with self.subTest(char=hex(ord(char))):
                self.assertFalse(
                    import_module._holds_tag_construct(
                        "x &\u200b" + char))
                self.assertFalse(
                    acquisition._fm_holds_tag_construct(
                        "x &\u200b" + char))

    def test_gap_controls_stand_as_they_stood(self):
        for helper in (import_module._holds_tag_construct,
                       acquisition._fm_holds_tag_construct):
            self.assertTrue(helper("x.&\u200b\u0301"))
            self.assertTrue(helper("x.&\u200b\u20dd"))
            self.assertFalse(helper("x.&\u00a0\u20dd"))
            self.assertFalse(helper("x.&\u00a0\u115f"))
            self.assertTrue(helper("/*&\u20dd?"))
            self.assertTrue(helper(";&\u00a0%\u0903*"))

    def test_category_counts_stand_on_this_runtime_form(self):
        # A runtime ground check in the ruling (h) form of
        # the two count pins: the totals below stand as
        # the Unicode 15 totals of this machine runtime.
        # This pin states no defect on any other runtime.
        if unicodedata.unidata_version != "15.0.0":
            self.skipTest(
                "Unicode 15 runtime form only")
        counts = {"Mn": 0, "Mc": 0, "Me": 0}
        for point in range(0x110000):
            category = unicodedata.category(chr(point))
            if category in counts:
                counts[category] += 1
        self.assertEqual(
            counts, {"Mn": 1985, "Mc": 452, "Me": 13})


class TestOwnAgreementSweep(Base):
    def test_page_and_import_agreement_on_own_forms(self):
        divergent = []
        judged = [0]

        def check(text):
            judged[0] += 1
            if import_module._holds_tag_construct(text) != \
                    acquisition._fm_holds_tag_construct(text):
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
        for prefix in PREFIXES:
            for gap in BROAD_GAPS:
                for follower in BROAD_FOLLOWERS:
                    check(prefix + "&" + gap + follower)
        for prefix in ("x.", "."):
            for first in RUN_GAPS:
                for second in RUN_GAPS:
                    for follower in SWEEP_FOLLOWERS[:6]:
                        check(prefix + "&" + first + second
                              + follower)
        for char in BOUNDED_HEAD:
            check("x &" + char)
            check("x &" + char + " rest")
            check("x &\u200b" + char)
        check(SOLE_009)
        check(PAIR_010_A)
        check(PAIR_010_B)
        rng = random.Random(2411)
        alphabet = list("&*%!.,:;-/+ $~=@^`?\\()<>") \
            + list(GAPS) + list(SWEEP_FOLLOWERS) \
            + list(BROAD_GAPS) + ["a", "1", " ", "\u00a0"]
        for _ in range(5000):
            size = rng.randint(1, 14)
            check("".join(
                rng.choice(alphabet) for _ in range(size)))
        self.assertEqual(judged[0], 11530)
        self.assertEqual(divergent, [])


if __name__ == "__main__":
    unittest.main()
