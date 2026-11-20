"""Checks entries.

Each test pins one settled rule on the behaviour the register states, written before its cure. Entries:
and."""

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


class Test002CompanionOwnAttribution(unittest.TestCase):

    def test_002_tail_attribution_six_followers(self):
        for punct in (",", ";", ":", ".", "!", "?"):
            for first in (
                "It is the results",
                "The results are the figures",
            ):
                text = (
                    "The note reads " + O + first + C + punct
                    + " she called " + SECOND
                    + " said Priya Nair in the review today.")
                self.assertEqual(span_total(text), 2, text)
                self.assertEqual(excerpts_for(text), [
                    O + first + C,
                    SECOND,
                ], text)

    def test_002_tail_attribution_verbs_in_turn(self):
        for tail in (
            "said Priya Nair",
            "says Priya Nair",
            "wrote Ana Lee",
            "asked Tom Ray",
            "added Ana Lee",
            "noted Priya Nair",
            "called Priya Nair",
        ):
            text = (
                "The note reads " + O + "It is the results" + C
                + ", she called " + SECOND + " " + tail
                + " in the review today.")
            self.assertEqual(span_total(text), 2, text)

    def test_002_further_first_spans_both_marks(self):
        firsts = [
            "The results are the figures",
            "The winner was the teams",
            "It was the results",
            "The prize was the dogs",
            "It has been the results",
        ]
        for first in firsts:
            text = (
                "The note reads " + O + first + C
                + ", she called " + SECOND
                + " said Priya Nair in the review today.")
            self.assertEqual(span_total(text), 2, text)
            text = (
                "The note reads " + O + first + C
                + ", as she called " + SECOND
                + " in the review today.")
            self.assertEqual(span_total(text), 2, text)


class Test002CompanionSubordinatedIntroduction(
        unittest.TestCase):

    def test_002_subordinated_introductions_in_turn(self):
        for intro in (
            "as she called",
            "as he said",
            "as they noted",
            "as we quoted",
            "as it added",
            "as she wrote",
            "as he asked",
        ):
            text = (
                "The note reads " + O + "It is the results" + C
                + ", " + intro + " " + SECOND
                + " in the review today.")
            self.assertEqual(span_total(text), 2, text)
            self.assertEqual(excerpts_for(text), [
                O + "It is the results" + C,
                SECOND,
            ], text)

    def test_002_subordinated_six_followers(self):
        for punct in (",", ";", ":", ".", "!", "?"):
            text = (
                "The note reads " + O + "It is the results" + C
                + punct + " as she called " + SECOND
                + " in the review today.")
            self.assertEqual(span_total(text), 2, text)


class Test002StatisticsAndThreeSpanForms(unittest.TestCase):

    def test_002_statistics_outer_mark_form_counts(self):
        text = (
            "The note reads " + O + "It is the results" + C
            + ", she noted 42 percent growth and then "
            "quoted " + O
            + "Second quoted span stands here too" + C
            + " said Priya Nair in the review today.")
        self.assertEqual(stat_count(text), 1, text)
        self.assertEqual(span_total(text), 2, text)

    def test_002_statistics_subordinated_form_counts(self):
        text = (
            "The note reads " + O + "It is the results" + C
            + "; growth hit 42 percent as she called " + O
            + "best plan this week and more words follow"
            + C + " in the margin today.")
        self.assertEqual(stat_count(text), 1, text)
        self.assertEqual(span_total(text), 2, text)

    def test_002_three_spans_tail_after_third(self):
        text = (
            "The note reads " + O + "It is the results" + C
            + ", she called " + O + "He shared the figures"
            + C + ", and " + O + "They filed the items" + C
            + " said Priya Nair in the review today.")
        self.assertEqual(span_total(text), 3)
        self.assertEqual(excerpts_for(text), [
            O + "It is the results" + C,
            O + "He shared the figures" + C,
            O + "They filed the items" + C,
        ])


class Test002PossessiveNeitherMarkHeldWhole(
        unittest.TestCase):

    def test_002_possessive_neither_six_followers(self):
        for punct in (",", ";", ":", ".", "!", "?"):
            text = (
                "The note reads " + O + "It is the dogs" + C
                + punct + " she called " + SECOND
                + " in the review today.")
            self.assertEqual(span_total(text), 1, text)
            self.assertEqual(excerpts_for(text), [
                O + "It is the dogs" + C + punct
                + " she called " + SECOND,
            ], text)

    def test_002_possessive_neither_further_first_span(self):
        text = (
            "The note reads " + O
            + "The first prize was the dogs" + C
            + ", she called " + SECOND
            + " in the review today.")
        self.assertEqual(span_total(text), 1, text)

    def test_002_possessive_neither_statistics_forms(self):
        text = (
            "The note reads " + O + "It is the dogs" + C
            + "; growth hit 42 percent and she called " + O
            + "best plan this week and more words follow"
            + C + " in the margin today.")
        self.assertEqual(stat_count(text), 0)
        self.assertEqual(span_total(text), 1)
        text = (
            "The note reads " + O + "It is the dogs" + C
            + "; growth hit 42 percent when she called " + O
            + "best plan this week and more words follow"
            + C + " in the margin today.")
        self.assertEqual(stat_count(text), 0)
        self.assertEqual(span_total(text), 1)


class Test002PinnedControls(unittest.TestCase):

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

    def test_002_true_closing_neither_mark_control(self):
        for first in (
            "It is the results",
            "The results are the figures",
            "The winner was the teams",
            "It is the teams",
        ):
            text = (
                "The note reads " + O + first + C
                + ", she called " + SECOND
                + " in the review today.")
            self.assertEqual(span_total(text), 2, text)


class Test003NoCommaMonthFirstGluedMarker(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_003_no_comma_glued_marker_forms(self):
        self.check_forms([
            "November 14 2026, 10:30pm",
            "November 14 2026 10:30pm",
            "Nov 14 2026, 10:30pm",
            "Nov 14 2026 10:30pm",
            "September 14 2026, 10:30pm",
            "November 14th 2026, 10:30pm",
            "November 14 2026, 10:30am",
            "November 14 2026, 9:30pm",
            "Sept 14 2026, 10:30pm",
            "Sep 14 2026, 10:30pm",
            "November 14 2026, 10:30:15pm",
            "Nov. 14 2026, 10:30pm",
            "November 14 2026, 10:30PM",
        ])

    def test_003_no_comma_glued_dotted_forms(self):
        self.check_forms([
            "November 14 2026, 10:30P.M.",
            "November 14 2026, 10:30p.m.",
        ])

    def test_003_controls(self):
        self.check_forms([
            "November 14 2026, 10:30",
            "November 14 2026, 10:30 PM",
            "November 14 2026, 10:30 P.M.",
            "November 14 2026 10:30 PM",
            "14 November 2026, 10:30pm",
            "14 Nov 2026, 10:30pm",
            "November 14, 2026, 10:30pm",
            "November 14 2026",
            "10:30 PM, November 14 2026",
            "10:30pm, November 14 2026",
        ])


class Test005PlainTimeFirstYearFirst(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_005_plain_time_before_slash_year_first(self):
        self.check_forms([
            "10:30 2026/11/14",
            "10:30, 2026/11/14",
            "9:30 2026/11/14",
            "10:30:15 2026/11/14",
        ])

    def test_005_plain_time_before_dotted_year_first(self):
        self.check_forms([
            "10:30 2026.11.14",
            "10:30, 2026.11.14",
            "9:30, 2026.11.14",
        ])

    def test_005_controls(self):
        self.check_forms([
            "10:30 PM, 2026/11/14",
            "10:30pm, 2026/11/14",
            "10:30 P.M., 2026.11.14",
            "10:30p.m., 2026/11/14",
            "10:30, 2026-11-14",
            "10:30 2026-11-14",
            "10:30, November 14, 2026",
            "10:30, 14/11/2026",
            "10:30 14/11/2026",
        ])
        self.assertEqual(
            stat_count(self.FRAME % "10:30"), 1)
        self.assertEqual(
            stat_count(self.FRAME % "14.11.2026"), 1)
        self.assertEqual(
            stat_count(self.FRAME % "10:30, 14.11.2026"), 2)


class Test002MixedPossessiveBatteryCost(unittest.TestCase):

    UNIT = (
        "The note reads " + O + "It is the dogs" + C
        + ", she called " + O + "best plan" + C
        + " this week" + C
        + " said Priya Nair in the review today. ")

    def test_002_battery_at_200_inside_bound(self):
        self.assertEqual(
            len(checks._quoted_spans(self.UNIT)), 1)
        text = self.UNIT * 200
        start = time.process_time()
        quotations_for(text)
        cpu = time.process_time() - start
        self.assertLess(cpu, 4.0)


if __name__ == "__main__":
    unittest.main()
