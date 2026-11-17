"""Step 17 round 13 fix seat F4 tests: import family.

Test first pins for register entry S17-R13-004, from
design/audit/step-17-r13-findings-register.md, as
dispositioned in design/audit/step-17-r13-disposition.md
ruling (c) and Section 3.
"""

import json
import unicodedata
import unittest

from citeline import probe_import as import_module

BODY = "A plain answer body standing here."


def token_of(exc):
    return getattr(exc, "error_value", None) or ""


MC_MARKS = tuple(chr(point) for point in (
    0x0903, 0x093B, 0x093E, 0x0BBE, 0x1D165))
ME_MARKS = tuple(chr(point) for point in (
    0x20DD, 0x20E3, 0xA670, 0x0488))
ALL_NEW_MARKS = MC_MARKS + ME_MARKS
MN_MARKS = tuple(chr(point) for point in (
    0x0483, 0x0591, 0x064B, 0x0670, 0x06D6,
    0x20D0, 0x3099, 0xFE20, 0x1AB0, 0x1DC0))


class ImportBase(unittest.TestCase):
    def assert_front_refused(self, text, token):
        with self.assertRaises(Exception) as caught:
            import_module.extract_front_matter(text)
        self.assertEqual(token_of(caught.exception), token)

    def assert_front_passes(self, text):
        body, had = import_module.extract_front_matter(text)
        self.assertTrue(had)
        self.assertEqual(body, BODY)


class Test004MarkCategoriesPastMn(ImportBase):
    def test_marks_stand_as_categories_mc_and_me(self):
        for mark in MC_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                self.assertEqual(unicodedata.category(mark), "Mc")
        for mark in ME_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                self.assertEqual(unicodedata.category(mark), "Me")

    # The category counts below pin a Unicode data
    # version, stated in the open beside the counts, as
    # Step 19 entry U-12 directs: the product helper
    # judges by unicodedata.category at run time, so its
    # refusal set follows the runtime Unicode data, and a
    # count pin stands read against the version it names.
    # On a runtime whose version stands in neither row
    # the pin does not stand read and the test skips,
    # naming the version, in the sibling runtime form
    # test form.
    CATEGORY_COUNTS_BY_UNIDATA_VERSION = {
        "15.0.0": {"Mn": 1985, "Mc": 452, "Me": 13},
        "16.0.0": {"Mn": 2020, "Mc": 468, "Me": 13},
    }

    def test_mark_category_counts_stand_as_stated(self):
        expected = self.CATEGORY_COUNTS_BY_UNIDATA_VERSION.get(
            unicodedata.unidata_version)
        if expected is None:
            self.skipTest(
                "category counts pinned for Unicode "
                + " and ".join(sorted(
                    self.CATEGORY_COUNTS_BY_UNIDATA_VERSION))
                + " only; this runtime carries "
                + unicodedata.unidata_version)
        counts = {"Mn": 0, "Mc": 0, "Me": 0}
        for point in range(0x110000):
            category = unicodedata.category(chr(point))
            if category in counts:
                counts[category] += 1
        self.assertEqual(counts, expected)

    def test_line_form_value_ampersand_marks_refused(self):
        for mark in ALL_NEW_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                self.assert_front_refused(
                    "---\ntitle: x.&" + mark + "a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_line_form_value_other_constructs_marks_refused(self):
        for construct in ("!", "*", "%"):
            for mark in ALL_NEW_MARKS:
                with self.subTest(
                        construct=construct, mark=hex(ord(mark))):
                    self.assert_front_refused(
                        "---\ntitle: x." + construct + mark
                        + "a\n---\n" + BODY,
                        "IMPORT_VALIDATION_FAILED")

    def test_json_form_value_marks_refused(self):
        for mark in ALL_NEW_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                block = json.dumps({"title": "x.&" + mark + "a"})
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_json_escape_form_value_marks_refused(self):
        for mark in ALL_NEW_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                block = json.dumps(
                    {"title": "x.&" + mark + "a"}, ensure_ascii=True)
                self.assertIn("\\u", block)
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_line_form_key_marks_refused(self):
        for mark in ALL_NEW_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                self.assert_front_refused(
                    "---\nx.&" + mark + "a: abc\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_json_form_key_marks_refused(self):
        for mark in ALL_NEW_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                block = json.dumps({"x.&" + mark + "a": "v"})
                self.assert_front_refused(
                    "---\n" + block + "\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")

    def test_every_mc_and_me_mark_refused_at_helper(self):
        refused = 0
        total = 0
        for point in range(0x110000):
            mark = chr(point)
            if unicodedata.category(mark) not in ("Mc", "Me"):
                continue
            total += 1
            if import_module._holds_tag_construct("x.&" + mark + "a"):
                refused += 1
        # The total is the runtime own Mc plus Me count,
        # derived from the runtime unicodedata at run time
        # and cross read against the version pin in the
        # counts test above, per Step 19 entry U-12; the
        # refusal pin itself stands unchanged: every Mc
        # and Me mark the runtime holds stands refused.
        pinned = self.CATEGORY_COUNTS_BY_UNIDATA_VERSION.get(
            unicodedata.unidata_version)
        if pinned is not None:
            self.assertEqual(total, pinned["Mc"] + pinned["Me"])
        self.assertEqual(refused, total)

    def test_controls_hold(self):
        for mark in MN_MARKS:
            with self.subTest(mark=hex(ord(mark))):
                self.assert_front_refused(
                    "---\ntitle: x.&" + mark + "a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")
        self.assert_front_refused(
            "---\ntitle: x.&́a\n---\n" + BODY,
            "IMPORT_VALIDATION_FAILED")
        for mark in ("ؐ", "︀"):
            with self.subTest(mark=hex(ord(mark))):
                self.assert_front_refused(
                    "---\ntitle: x.&" + mark + "a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")
        for follower in (".", "+", "$", "~", ";", "/", "=", "@",
                         "^", "`", "‿", "?", "\\", "(", ")",
                         "<", ":"):
            with self.subTest(follower=repr(follower)):
                self.assert_front_refused(
                    "---\ntitle: x.&" + follower + "a\n---\n" + BODY,
                    "IMPORT_VALIDATION_FAILED")
        for follower in ("'", "#", ",", "|", '"'):
            with self.subTest(follower=repr(follower)):
                self.assert_front_passes(
                    "---\ntitle: x.&" + follower + "a\n---\n" + BODY)
        self.assert_front_passes(
            "---\ntitle: plain text here\n---\n" + BODY)


if __name__ == "__main__":
    unittest.main()
