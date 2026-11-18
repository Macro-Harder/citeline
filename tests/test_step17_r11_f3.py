"""Checks entries.

Each test pins one settled rule on the behaviour the register states, written before its cure. Entries:
and."""

import unittest

from citeline import checks

AUDIT_DATE = "2026-11-15"


def make_page(text, sentences=None, links=()):
    if sentences is None:
        sentences = [text] if text else []
    return {
        "running_text": text,
        "sentences": list(sentences),
        "paragraphs": [text],
        "headings": [],
        "sections": [{
            "heading_text": None, "start": 0, "end": len(text),
            "references_section": False,
        }],
        "links": list(links),
        "blockquotes": [],
        "lists": [],
        "tables": [],
        "word_count": len(text.split()),
    }


def result_of(results, check_id):
    for result in results:
        if result["check_id"] == check_id:
            return result
    raise AssertionError(check_id)


def statistics_for(text):
    page = make_page(text)
    return result_of(
        checks.run_checks(page, {}, audit_date=AUDIT_DATE),
        "statistics")


def quotations_for(text):
    page = make_page(text)
    return result_of(
        checks.run_checks(page, {}, audit_date=AUDIT_DATE),
        "quotations")


def stat_count(text):
    return statistics_for(text)["detail_counts"][
        "statistic_token_count"]


def excerpts_for(text):
    result = quotations_for(text)
    return [span["excerpt"] for span in result["evidence_spans"]]


def span_total(text):
    counts = quotations_for(text)["detail_counts"]
    return (
        counts["attributed_span_count"]
        + counts["unattributed_span_count"])


O = "\u2018"
C = "\u2019"
SECOND = (
    O + "best plan this week and more words follow" + C)


class Test002TrueClosingBeforePlainProse(unittest.TestCase):

    def test_002_six_followers_three_introductions(self):
        for punct in (",", ";", ":", ".", "!", "?"):
            for intro in (
                "she called",
                "said Priya Nair",
                "the editor added",
            ):
                text = (
                    "The note reads " + O
                    + "She published the results" + C + punct
                    + " " + intro + " " + SECOND
                    + " in the review today.")
                self.assertEqual(span_total(text), 2, text)
                self.assertEqual(excerpts_for(text), [
                    O + "She published the results" + C,
                    SECOND,
                ], text)

    def test_002_further_final_words(self):
        cases = [
            ("He shared the figures", ",", "the editor added"),
            ("He read the news", ".", "She then quoted"),
            ("She thanked the class", ":", "the teacher quoted"),
            ("She published the RESULTS", ",", "the editor added"),
            ("He shared the figures", ";", "the editor added"),
        ]
        for first, punct, intro in cases:
            text = (
                "The note reads " + O + first + C + punct
                + " " + intro + " " + SECOND
                + " in the review today.")
            self.assertEqual(span_total(text), 2, text)
            self.assertEqual(excerpts_for(text), [
                O + first + C,
                SECOND,
            ], text)

    def test_002_introduction_variants(self):
        for intro in (
            "the well known editor added",
            "the editor of the weekly review later added",
        ):
            text = (
                "The note reads " + O
                + "She published the results" + C + ", "
                + intro + " " + SECOND
                + " in the review today.")
            self.assertEqual(span_total(text), 2, text)
            self.assertEqual(excerpts_for(text), [
                O + "She published the results" + C,
                SECOND,
            ], text)

    def test_002_red_s_ending_last_words(self):
        for word in (
            "news", "business", "glass", "status", "analysis",
            "series", "means", "innings", "chaos", "species",
            "press", "loss", "gas", "yes",
        ):
            text = (
                "The note reads " + O + "we read the " + word
                + C + ", and the editor then quoted " + O
                + "go now at once today" + C
                + " in the log today.")
            self.assertEqual(span_total(text), 2, text)
            self.assertEqual(excerpts_for(text), [
                O + "we read the " + word + C,
                O + "go now at once today" + C,
            ], text)

    def test_002_red_go_now_form_at_span_reading(self):
        text = (
            "The note reads " + O + "we read the news" + C
            + ", and the editor then quoted " + O + "go now"
            + C + " in the log today.")
        self.assertEqual(checks._quoted_spans(text), [
            (len("The note reads "),
             len("The note reads " + O + "we read the news" + C)),
            (text.index(O + "go now"),
             text.index(O + "go now") + len(O + "go now" + C)),
        ])

    def test_002_three_spans_plain_prose_first(self):
        text = (
            "The note reads " + O
            + "She published the results" + C
            + ", she called " + O + "He shared the figures"
            + C + ", and " + O + "They filed the items" + C
            + " in the review today.")
        self.assertEqual(span_total(text), 3)
        self.assertEqual(excerpts_for(text), [
            O + "She published the results" + C,
            O + "He shared the figures" + C,
            O + "They filed the items" + C,
        ])

    def test_002_statistics_figure_between_spans_counts(self):
        for punct in (",", ":", "!", "?"):
            text = (
                "The note reads " + O
                + "She published the results" + C + punct
                + " she noted 42 percent growth and then "
                "quoted " + O
                + "Second quoted span stands here too" + C
                + " in the review today.")
            self.assertEqual(stat_count(text), 1, text)
            self.assertEqual(span_total(text), 2, text)

    def test_002_possessive_six_followers_control(self):
        for punct in (",", ";", "!", ".", "?", ":"):
            text = (
                "The note reads " + O + "It is the dogs" + C
                + punct + " she called " + O
                + "best plan this week and more words "
                "follow" + C
                + " as one outer span, said Priya Nair in "
                "the review today.")
            self.assertEqual(span_total(text), 1, punct)
            self.assertEqual(excerpts_for(text), [
                O + "It is the dogs" + C + punct
                + " she called " + O
                + "best plan this week and more words "
                "follow" + C,
            ], punct)

    def test_002_possessive_own_closing_control(self):
        text = (
            "The note reads " + O + "It is the dogs" + C
            + ", she called " + O
            + "best plan this week and more words follow"
            + C + " as one outer span, " + O
            + "Further quoted span stands here now" + C
            + " said Priya Nair in the review today.")
        self.assertEqual(span_total(text), 2)
        self.assertEqual(excerpts_for(text), [
            O + "It is the dogs" + C + ", she called " + O
            + "best plan this week and more words follow"
            + C,
            O + "Further quoted span stands here now" + C,
        ])

    def test_002_possessive_statistics_control(self):
        text = (
            "The note reads " + O + "It is the dogs" + C
            + "; growth hit 42 percent as she called " + O
            + "best plan this week and more words follow"
            + C + " in the margin today.")
        self.assertEqual(stat_count(text), 0)
        self.assertEqual(span_total(text), 1)

    def test_002_cured_composition_controls(self):
        text = (
            "The note reads " + O
            + "She published the results" + C + ", "
            + O + "Second quoted span stands here too" + C
            + " in the review today.")
        self.assertEqual(span_total(text), 2)
        text = (
            "The note reads " + O
            + "She published the results" + C
            + ", said Priya Nair, " + O
            + "Second quoted span stands here too" + C
            + " in the review today.")
        self.assertEqual(span_total(text), 2)
        text = (
            "The note reads " + O
            + "She published the results" + C
            + ". The review ended. " + O
            + "Second quoted span stands here too" + C
            + " in the review today.")
        self.assertEqual(span_total(text), 2)
        text = (
            "The note reads " + O
            + "She published the outcome" + C
            + ", she called " + O
            + "best plan this week and more words follow"
            + C + " in the review today.")
        self.assertEqual(span_total(text), 2)


class Test003DottedMarker(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_003_time_first_month_name_forms(self):
        self.check_forms([
            "10:30 P.M., November 14, 2026",
            "10:30 P.M. November 14, 2026",
            "10:30 P.M., 14 November 2026",
            "10:30 p.m., November 14, 2026",
            "10:30 A.M., November 14, 2026",
            "10:30P.M., November 14, 2026",
        ])

    def test_003_parent_full_date_forms(self):
        self.check_forms([
            "10:30 p.m., 2026-11-14",
            "10:30 P.M., 2026/11/14",
        ])

    def test_003_fragment_first_glued_dotted_forms(self):
        self.check_forms([
            "2026-11, 10:30P.M.",
            "2026.11, 10:30P.M.",
            "11-2026, 10:30P.M.",
        ])

    def test_003_fragment_time_first_forms(self):
        self.check_forms([
            "10:30 P.M., 2026-11",
            "10:30 P.M., 2026/11",
            "10:30P.M. 2026/11",
        ])

    def test_003_controls(self):
        self.check_forms([
            "10:30 PM, November 14, 2026",
            "10:30PM, November 14, 2026",
            "2026-11, 10:30 P.M.",
            "2026-11, 10:30PM",
        ])


class Test004MonthNameFragmentCommaGlued(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_004_glued_marker_forms(self):
        self.check_forms([
            "November 2026, 10:30pm",
            "Nov 2026, 10:30pm",
            "Sept 2026, 10:30pm",
            "Sep 2026, 10:30pm",
            "November 2026, 9:30am",
        ])

    def test_004_controls(self):
        self.check_forms([
            "Nov 2026, 10:30",
            "Nov 2026, 10:30 PM",
            "2026 Nov, 10:30pm",
            "November 2026",
        ])


class Test005MonthNameFragmentTimeFirstAndSpace(
        unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_005_time_first_comma_forms(self):
        self.check_forms([
            "10:30, Nov 2026",
            "10:30, November 2026",
        ])

    def test_005_time_first_marker_forms(self):
        self.check_forms([
            "10:30 PM, Nov 2026",
            "10:30 PM Nov 2026",
            "10:30PM, Nov 2026",
        ])

    def test_005_time_first_space_plain_form(self):
        self.check_forms([
            "10:30 November 2026",
        ])

    def test_005_fragment_first_space_glued_forms(self):
        self.check_forms([
            "November 2026 10:30pm",
            "Nov 2026 10:30pm",
        ])

    def test_005_controls(self):
        self.check_forms([
            "Nov 2026 10:30 PM",
            "10:30, 2026/11",
            "2026/11 10:30pm",
            "10:30, November 14, 2026",
        ])


if __name__ == "__main__":
    unittest.main()
