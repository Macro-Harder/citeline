"""the repair Verdict pins, registry and acquisition.

Verdict form only: no entry stands charged in
the repair, in the form the settled rule and Section 3 of the
register paper state. These pins stand written against the
standing behaviour of the cured tree, verifying first hand
that the repair F2 standings hold whole: the gap
cures, and, the position scan gap reach and the page key
judgement in citeline/acquisition.py, over the charged
forms and past them in the registry repair the earlier round sweep
forms of the settled record: structured gap chains, the
whole head set as single gap apart from the whitespace
class, and the sole follower union sweep reproducing the
passing class of exactly 4,023 characters. The bounded
set, the zero width space U+200B, the soft hyphen U+00AD,
the arabic letter mark U+061C, the word joiner U+2060, and
the tag character U+E0041, stands pinned as passing whole
in its bounded form. The whitespace gap class stands
pinned in its bounded form, the 29 whitespace characters
of the head set. The non head union mark blocker form
stands pinned as a bounded observation, outside any cure.
Where a pin asserts a cured form, the revert check form
applies in the repair notes: the cure removed in a scratch
copy, the pin failing in exact form. Every pin runs in
memory at the readings and at the helpers, so no pin
stands on a temporary directory."""

import json
import unicodedata
import unittest

from citeline import acquisition
from citeline import probe_import as import_module

BODY = "body text"

GAPS = ("\u200b", "\u00ad", "\u061c", "\u2060",
        "\u2061", "\U000e0041", "\ufeff", "\u034f")

FOLLOWERS = ("\u0301", "\u0903", "\u20dd", "\u115f",
             "\u3164")

BOUNDED_SET = ("\u200b", "\u00ad", "\u061c", "\u2060",
               "\U000e0041")

WHITESPACE_GAP_CLASS = (
    "\u0009", "\u000a", "\u000b", "\u000c", "\u000d",
    "\u001c", "\u001d", "\u001e", "\u001f", "\u0020",
    "\u0085", "\u00a0", "\u1680", "\u2000", "\u2001",
    "\u2002", "\u2003", "\u2004", "\u2005", "\u2006",
    "\u2007", "\u2008", "\u2009", "\u200a", "\u2028",
    "\u2029", "\u202f", "\u205f", "\u3000")

SOLE_009 = ".\u0026\u200b\u115f"

PAIR_010_A = "/*&\u2060\u20dd?"
PAIR_010_B = ";&\u00a0%\u00ad\u0903*"

HEAD_CHARS = tuple(
    chr(cp) for cp in range(0x110000)
    if acquisition._fm_is_head_char(chr(cp)))

MARK_UNION = tuple(
    chr(cp) for cp in range(0x110000)
    if unicodedata.category(chr(cp)) in ("Mn", "Mc", "Me"))


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

    def assert_both_helpers_hold(self, text):
        self.assertTrue(
            acquisition._fm_holds_tag_construct(text),
            "page helper passes %r" % (text,))
        self.assertTrue(
            import_module._holds_tag_construct(text),
            "import helper passes %r" % (text,))

    def assert_both_helpers_pass(self, text):
        self.assertFalse(
            acquisition._fm_holds_tag_construct(text),
            "page helper holds %r" % (text,))
        self.assertFalse(
            import_module._holds_tag_construct(text),
            "import helper holds %r" % (text,))


class TestR17F2_009GapChainsAndHeadSweep(Base):
    def test_worked_form_holds_at_both_helpers_and_readings(self):
        self.assert_both_helpers_hold(SOLE_009)
        self.assert_both_helpers_hold(SOLE_009 + " rest")
        self.assert_page_refuses("title: " + SOLE_009 + " rest")
        self.assert_import_refuses("title: " + SOLE_009 + " rest")
        self.assert_page_refuses(SOLE_009 + ": abc")
        self.assert_import_refuses(SOLE_009 + ": abc")

    def test_structured_gap_chains_hold_at_both_helpers(self):
        for chain_length in (1, 2, 3):
            for gap in GAPS:
                for follower in FOLLOWERS:
                    text = "x.&" + gap * chain_length + follower
                    with self.subTest(
                            chain=chain_length,
                            gap=hex(ord(gap)),
                            follower=hex(ord(follower))):
                        self.assert_both_helpers_hold(text)

    def test_mixed_gap_chains_hold_at_both_helpers(self):
        chains = ("\u200b\u2060", "\u00ad\ufeff\u2060",
                  "\u061c\u2061", "\u2060\U000e0041\u200b")
        for chain in chains:
            for follower in FOLLOWERS:
                with self.subTest(chain=repr(chain),
                                  follower=hex(ord(follower))):
                    self.assert_both_helpers_hold(
                        "x.&" + chain + follower)
                    self.assert_both_helpers_hold(
                        ".&" + chain + follower + " rest")

    def test_whole_head_set_single_gap_apart_from_whitespace(self):
        self.assertEqual(len(HEAD_CHARS), 4309)
        for follower in ("\u115f", "\u0301"):
            passing = [
                char for char in HEAD_CHARS
                if not acquisition._fm_holds_tag_construct(
                    "x.&" + char + follower)]
            self.assertEqual(
                passing, list(WHITESPACE_GAP_CLASS),
                "follower %r" % (follower,))
            passing_import = [
                char for char in HEAD_CHARS
                if not import_module._holds_tag_construct(
                    "x.&" + char + follower)]
            self.assertEqual(passing_import, passing)


class TestR17F2_010PairFormsPastTemplates(Base):
    def test_worked_forms_hold_and_refuse_at_both_readings(self):
        for text in (PAIR_010_A, PAIR_010_B):
            with self.subTest(text=repr(text)):
                self.assert_both_helpers_hold(text)
                self.assert_page_refuses("title: " + text)
                self.assert_import_refuses("title: " + text)
                self.assert_page_refuses("title: [" + text + "]")
                self.assert_page_refuses(
                    "title: first line\n " + text)

    def test_whole_head_set_pair_gap_apart_from_whitespace(self):
        passing = [
            char for char in HEAD_CHARS
            if not acquisition._fm_holds_tag_construct(
                "x.&&" + char + "\u20dd")]
        self.assertEqual(passing, list(WHITESPACE_GAP_CLASS))
        passing_lo = [
            char for char in HEAD_CHARS
            if not acquisition._fm_holds_tag_construct(
                "x.&&" + char + "\u115f")]
        self.assertEqual(passing_lo, list(WHITESPACE_GAP_CLASS))

    def test_gap_in_both_pair_slots_holds(self):
        for gap in GAPS:
            for follower in FOLLOWERS:
                with self.subTest(gap=hex(ord(gap)),
                                  follower=hex(ord(follower))):
                    self.assert_both_helpers_hold(
                        "x.&" + gap + "&" + gap + follower)

    def test_triple_construct_and_apart_pairs_hold(self):
        self.assert_both_helpers_hold("x.&&&\u200b\u0301")
        self.assert_both_helpers_hold("x.&&&\u2060\u20dd")
        for punct in (".", ";", ":"):
            with self.subTest(punct=punct):
                self.assert_both_helpers_hold(
                    "x& rest" + punct + "&\u200b\u0301")
        self.assert_both_helpers_hold("x.&*&\u200b\u0301")


class TestR17F2_011PageKeyJudgement(Base):
    def test_worked_pair_keys_refuse_at_both_readings(self):
        for text in (PAIR_010_A, PAIR_010_B):
            with self.subTest(text=repr(text)):
                self.assert_page_refuses(text + ": abc")
                self.assert_import_refuses(text + ": abc")

    def test_judged_key_only_forms_refuse_at_both_readings(self):
        self.assert_page_refuses("x &\u200b\u115f: abc")
        self.assert_import_refuses("x &\u200b\u115f: abc")
        self.assert_page_refuses("x &\u2060\u3164: abc")
        self.assert_import_refuses("x &\u2060\u3164: abc")

    def test_quoted_key_forms_refuse_at_both_readings(self):
        for quoted in ('"' + PAIR_010_A + '"',
                       "'" + PAIR_010_A + "'"):
            with self.subTest(quoted=quoted):
                self.assert_page_refuses(quoted + ": abc")
                self.assert_import_refuses(quoted + ": abc")

    def test_escaped_json_forms_refuse_at_both_readings(self):
        for obj in ({PAIR_010_A: "v"}, {"title": PAIR_010_A},
                    {"title": SOLE_009}):
            block = json.dumps(obj, ensure_ascii=True)
            with self.subTest(block=block):
                self.assert_page_refuses(block)
                self.assert_import_refuses(block)


class TestR17F2BoundedStandings(Base):
    def test_bounded_set_passes_whole_as_sole_follower(self):
        for char in BOUNDED_SET:
            with self.subTest(char=hex(ord(char))):
                self.assert_both_helpers_pass("x &" + char)
                self.assert_both_pass("title: x &" + char)
                self.assert_both_pass(
                    "title: x &" + char + " rest")

    def test_bounded_set_passes_as_pair_follower_and_behind_blocker(self):
        for char in BOUNDED_SET:
            with self.subTest(char=hex(ord(char))):
                self.assert_both_helpers_pass("x.&&" + char)
        self.assert_both_helpers_pass("x.\u034f&\u200b")
        self.assert_both_pass("title: x.\u034f&\u200b")

    def test_sole_follower_union_sweep_passing_class_exact(self):
        union = sorted(set(HEAD_CHARS) | set(MARK_UNION))
        passing = []
        divergent = []
        for char in union:
            text = "x.&" + char
            page_holds = acquisition._fm_holds_tag_construct(text)
            import_holds = import_module._holds_tag_construct(text)
            if page_holds != import_holds:
                divergent.append(char)
            if not page_holds:
                passing.append(char)
        self.assertEqual(divergent, [])
        self.assertEqual(len(passing), 4023)
        for char in BOUNDED_SET:
            self.assertIn(char, passing)
        counts = {}
        for char in passing:
            category = unicodedata.category(char)
            counts[category] = counts.get(category, 0) + 1
        self.assertEqual(counts, {"Cn": 3769, "Cf": 170,
                                  "Cc": 65, "Zs": 17,
                                  "Zl": 1, "Zp": 1})

    def test_whitespace_gap_class_passes_at_readings_in_bounded_form(self):
        self.assertEqual(len(WHITESPACE_GAP_CLASS), 29)
        for char in WHITESPACE_GAP_CLASS:
            self.assertIn(char, HEAD_CHARS)
            self.assertTrue(char.isspace())
        for gap in ("\u0020", "\u00a0", "\u2003", "\u202f",
                    "\u3000"):
            with self.subTest(gap=hex(ord(gap))):
                self.assert_both_helpers_pass(
                    "x.&" + gap + "\u115f")
                self.assert_both_pass(
                    "title: .&" + gap + "\u115f")
                self.assert_both_pass(".&" + gap + "\u115f: abc")

    def test_non_head_union_mark_blocker_bounded_observation(self):
        for blocker in ("\u0301", "\u0903", "\u20dd"):
            self.assertFalse(
                acquisition._fm_is_head_char(blocker))
            for follower in ("\u0301", "\u0903", "\u20dd",
                             "\u115f"):
                text = "." + blocker + "&" + follower
                with self.subTest(
                        blocker=hex(ord(blocker)),
                        follower=hex(ord(follower))):
                    self.assert_both_helpers_pass(text)
                    self.assert_both_pass("title: " + text)

    def test_benign_forms_still_pass_at_both_readings(self):
        self.assert_both_pass("title: plain value here")
        self.assert_both_pass("x & rest: abc")
        self.assert_both_pass("title: x & rest of the words")


if __name__ == "__main__":
    unittest.main()
