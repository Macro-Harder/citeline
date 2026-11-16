"""Step 17 round 12 fix seat F3 tests: checks entries.

Each test pins one register entry on the behaviour the
register states, written before its cure. Entries:
S17-R12-002, S17-R12-003, S17-R12-004, and
S17-R12-005.
"""

import time
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


class Test002PredicateTrueClosing(unittest.TestCase):

    def test_002_six_followers_two_first_spans(self):
        for punct in (",", ";", ":", ".", "!", "?"):
            for first in (
                "It is the results",
                "The results are the figures",
            ):
                for intro in ("she called", "the editor added"):
                    text = (
                        "The note reads " + O + first + C + punct
                        + " " + intro + " " + SECOND
                        + " in the review today.")
                    self.assertEqual(span_total(text), 2, text)
                    self.assertEqual(excerpts_for(text), [
                        O + first + C,
                        SECOND,
                    ], text)

    def test_002_further_first_spans(self):
        firsts = [
            "It was the results",
            "The winner was the teams",
            "The answer is the news",
            "It is the teams",
            "The prize was the dogs",
            "It seems the results",
            "The theme is the class",
            "It is their results",
            "It was our teams",
            "The outcome was the figures",
            "She said it is the results",
            "The report says the winner was the teams",
            "Results are the news",
            "Those were the teams",
            "The winners were their teams",
            "It has been the results",
            "The answer has been the news",
        ]
        for first in firsts:
            for punct in (",", ".", ";"):
                text = (
                    "The note reads " + O + first + C + punct
                    + " she called " + SECOND
                    + " in the review today.")
                self.assertEqual(span_total(text), 2, text)
                self.assertEqual(excerpts_for(text), [
                    O + first + C,
                    SECOND,
                ], text)

    def test_002_red_forms_at_span_reading(self):
        second = O + "go now" + C
        for first in (
            "it is the results",
            "it was the figures",
            "this is the news",
            "the winner is the class",
            "it seems the results",
            "it is their results",
            "she said it is the results",
            "the answer was the figures",
        ):
            for punct in (",", ".", ";", ":", "!", "?"):
                text = (
                    "The note reads " + O + first + C + punct
                    + " and the editor then quoted " + second
                    + " in the log today.")
                self.assertEqual(
                    len(checks._quoted_spans(text)), 2, text)

    def test_002_three_spans_predicate_first(self):
        text = (
            "The note reads " + O
            + "It is the results" + C
            + ", she called " + O + "He shared the figures"
            + C + ", and " + O + "They filed the items" + C
            + " in the review today.")
        self.assertEqual(span_total(text), 3)
        self.assertEqual(excerpts_for(text), [
            O + "It is the results" + C,
            O + "He shared the figures" + C,
            O + "They filed the items" + C,
        ])
        text = (
            "The note reads " + O + "it is the results" + C
            + ", and the editor then quoted " + O + "go now"
            + C + " and later " + O + "third span here" + C
            + " in the log.")
        self.assertEqual(len(checks._quoted_spans(text)), 3)

    def test_002_statistics_figure_between_spans_counts(self):
        text = (
            "The note reads " + O
            + "It is the results" + C
            + ", she noted 42 percent growth and then "
            "quoted " + O
            + "Second quoted span stands here too" + C
            + " in the review today.")
        self.assertEqual(stat_count(text), 1, text)
        self.assertEqual(span_total(text), 2, text)
        text = (
            "The note reads " + O
            + "The winner was the teams" + C
            + ", she noted 42 percent growth and then "
            "quoted " + O
            + "Second quoted span stands here too" + C
            + " in the review today.")
        self.assertEqual(stat_count(text), 1, text)
        self.assertEqual(span_total(text), 2, text)
        text = (
            "The note reads " + O + "it is the results" + C
            + ", and the editor counted 42 items then "
            "quoted " + O + "go now" + C
            + " in the log today.")
        self.assertEqual(stat_count(text), 1, text)
        self.assertEqual(len(checks._quoted_spans(text)), 2, text)

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

    def test_002_possessive_statistics_control(self):
        text = (
            "The note reads " + O + "It is the dogs" + C
            + "; growth hit 42 percent as she called " + O
            + "best plan this week and more words follow"
            + C + " in the margin today.")
        self.assertEqual(stat_count(text), 0)
        self.assertEqual(span_total(text), 1)

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

    def test_002_cured_true_closing_controls(self):
        text = (
            "The note reads " + O
            + "She published the results" + C + ", "
            + "the editor added " + SECOND
            + " in the review today.")
        self.assertEqual(span_total(text), 2)
        text = (
            "The note reads " + O + "we read the news" + C
            + ", and the editor then quoted " + O + "go now"
            + C + " in the log today.")
        self.assertEqual(len(checks._quoted_spans(text)), 2)


class Test003DottedMarkerCompletions(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_003_month_name_fragment_time_first_dotted(self):
        self.check_forms([
            "10:30 P.M., Nov 2026",
            "10:30 P.M. Nov 2026",
            "10:30P.M., Nov 2026",
            "10:30P.M. November 2026",
            "10:30 P.M., November 2026",
            "10:30P.M., November 2026",
            "10:30 A.M., Nov 2026",
            "10:30 a.m., Nov 2026",
            "10:30 P.M., Sept 2026",
            "10:30 P.M., Sep 2026",
        ])

    def test_003_month_name_fragment_first_comma_dotted(self):
        self.check_forms([
            "November 2026, 10:30P.M.",
            "Nov 2026, 10:30P.M.",
            "Sept 2026, 10:30P.M.",
            "Sep 2026, 10:30P.M.",
            "November 2026, 10:30p.m.",
            "November 2026, 9:30P.M.",
        ])

    def test_003_month_name_fragment_first_space_dotted(self):
        self.check_forms([
            "November 2026 10:30P.M.",
            "Nov 2026 10:30P.M.",
        ])

    def test_003_fragment_first_space_numeric_dotted(self):
        self.check_forms([
            "2026-11 10:30P.M.",
            "2026.11 10:30P.M.",
            "11-2026 10:30P.M.",
            "11.2026 10:30P.M.",
            "2026-11 10:30p.m.",
            "2026-11 10:30A.M.",
            "2026-11 9:30P.M.",
        ])

    def test_003_time_first_dotted_full_date_dotted(self):
        self.check_forms([
            "10:30 P.M., 2026.11.14",
            "10:30P.M., 2026.11.14",
            "10:30 P.M., 14.11.2026",
            "10:30P.M., 14.11.2026",
            "10:30 p.m., 14.11.2026",
        ])

    def test_003_controls(self):
        self.check_forms([
            "10:30 PM, Nov 2026",
            "10:30PM, Nov 2026",
            "November 2026, 10:30pm",
            "November 2026, 10:30 P.M.",
            "November 2026 10:30 P.M.",
            "2026/11 10:30P.M.",
            "2026-11, 10:30P.M.",
            "10:30 PM, 14.11.2026",
        ])
        self.assertEqual(
            stat_count(self.FRAME % "14.11.2026"), 1)


class Test004FullDateFirstGluedMarker(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_004_month_name_month_first_glued(self):
        self.check_forms([
            "November 14, 2026, 10:30pm",
            "November 14, 2026 10:30pm",
            "Nov 14, 2026, 10:30pm",
            "November 14th, 2026, 10:30pm",
            "November 14, 2026, 10:30am",
            "November 14, 2026, 9:30pm",
            "November 14, 2026, 10:30P.M.",
            "November 14, 2026 10:30P.M.",
            "November 14, 2026, 10:30p.m.",
        ])

    def test_004_month_name_day_first_glued(self):
        self.check_forms([
            "14 November 2026, 10:30pm",
            "14 November 2026 10:30pm",
            "14 Nov 2026, 10:30pm",
            "14 November 2026, 10:30P.M.",
        ])

    def test_004_numeric_full_date_glued(self):
        self.check_forms([
            "2026-11-14, 10:30pm",
            "2026-11-14, 10:30P.M.",
            "2026-11-14 10:30P.M.",
            "2026/11/14, 10:30pm",
            "2026/11/14 10:30pm",
            "2026/11/14, 10:30P.M.",
            "2026.11.14, 10:30pm",
            "2026.11.14 10:30pm",
            "14.11.2026, 10:30pm",
            "14.11.2026 10:30pm",
        ])

    def test_004_controls(self):
        self.check_forms([
            "November 14, 2026, 10:30 PM",
            "November 14, 2026, 10:30 P.M.",
            "November 14, 2026, 10:30",
            "November 14, 2026, 10:30:45pm",
            "2026-11-14, 10:30:45pm",
            "2026/11/14, 10:30:45pm",
            "2026-11-14 10:30pm",
            "2026/11/14, 10:30 PM",
            "14.11.2026, 10:30 P.M.",
        ])


class Test005MixedPossessiveBatteryCost(unittest.TestCase):

    UNIT = (
        "The note reads " + O + "It is the dogs" + C
        + ", she called " + O + "best plan" + C
        + " this week" + C
        + " said Priya Nair in the review today. ")

    def test_005_battery_at_200_inside_bound(self):
        self.assertEqual(
            len(checks._quoted_spans(self.UNIT)), 1)
        text = self.UNIT * 200
        start = time.process_time()
        quotations_for(text)
        cpu = time.process_time() - start
        self.assertLess(cpu, 4.0)


if __name__ == "__main__":
    unittest.main()
