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


def plain_form(first, punct):
    return (
        "The note reads " + O + first + C + punct
        + " she called " + SECOND
        + " in the review today.")


class Test002PossessiveFormHeldWhole(unittest.TestCase):

    def test_002_cats_six_followers(self):
        for punct in (",", ";", ":", ".", "!", "?"):
            text = plain_form("It is the cats", punct)
            self.assertEqual(span_total(text), 1, text)
            self.assertEqual(excerpts_for(text), [
                O + "It is the cats" + C + punct
                + " she called " + SECOND,
            ], text)

    def test_002_further_wordings_comma_semicolon(self):
        for first in (
            "It is the birds",
            "It is the horses",
            "The first prize was the cats",
            "The top prize was the dogs",
            "The winner was the dogs",
            "It was the dogs",
        ):
            for punct in (",", ";"):
                text = plain_form(first, punct)
                self.assertEqual(span_total(text), 1, text)

    def test_002_yellow_wordings_comma(self):
        for first in (
            "It is the winners",
            "It is the players",
            "It is the authors",
            "It is the markets",
            "The results are the dogs",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)
        for first in ("It is the crews", "It is the hounds"):
            for punct in (",", ";", ":", ".", "!", "?"):
                text = plain_form(first, punct)
                self.assertEqual(span_total(text), 1, text)

    def test_002_wordings_past_the_papers(self):
        for first, punct in (
            ("It is the otters", ","),
            ("The award was the hounds", ";"),
            ("She said it is the cats", ","),
        ):
            text = plain_form(first, punct)
            self.assertEqual(span_total(text), 1, text)

    def test_002_statistics_forms(self):
        text = (
            "The note reads " + O + "It is the cats" + C
            + "; growth hit 42 percent and she called " + O
            + "best plan this week and more words follow"
            + C + " in the margin today.")
        self.assertEqual(stat_count(text), 0, text)
        self.assertEqual(span_total(text), 1, text)
        text = (
            "The note reads " + O + "It is the birds" + C
            + "; growth hit 42 percent when she called " + O
            + "best plan this week and more words follow"
            + C + " in the margin today.")
        self.assertEqual(stat_count(text), 0, text)
        self.assertEqual(span_total(text), 1, text)


class Test002CompanionSeparatorSplit(unittest.TestCase):

    def test_002_separator_forms_split(self):
        for sep in (";", ":", "!", "?"):
            text = (
                "The note reads " + O + "It is the results" + C
                + ", she called " + SECOND + sep
                + " said Priya Nair in the review today.")
            self.assertEqual(span_total(text), 2, text)
            self.assertEqual(excerpts_for(text), [
                O + "It is the results" + C,
                SECOND,
            ], text)

    def test_002_separator_statistics_forms(self):
        for sep in (";", ":"):
            text = (
                "The note reads " + O + "It is the results" + C
                + ", growth hit 42 percent and she called " + O
                + "best plan this week and more words follow"
                + C + sep
                + " said Priya Nair in the review today.")
            self.assertEqual(stat_count(text), 1, text)
            self.assertEqual(span_total(text), 2, text)


class Test002PinnedControls(unittest.TestCase):

    def test_002_pinned_possessive_controls(self):
        for first in (
            "It is the dogs",
            "The first prize was the dogs",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)

    def test_002_true_closing_controls(self):
        for first in (
            "It is the results",
            "The results are the figures",
            "The prize was the dogs",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 2, text)
            self.assertEqual(excerpts_for(text), [
                O + first + C,
                SECOND,
            ], text)

    def test_002_outer_attribution_wording_control(self):
        text = (
            "The note reads " + O + "It is the cats" + C
            + ", she called " + SECOND
            + " as one outer span, said Priya Nair in "
            "the review today.")
        self.assertEqual(span_total(text), 1, text)

    def test_002_separator_controls(self):
        for tail in (
            ", said Priya Nair in the review today.",
            " said Priya Nair in the review today.",
            ". Said Priya Nair in the review today.",
        ):
            text = (
                "The note reads " + O + "It is the results" + C
                + ", she called " + SECOND + tail)
            self.assertEqual(span_total(text), 2, text)


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


class Test003DayFirstSpacedMarker(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_003_undotted_spaced_forms(self):
        self.check_forms([
            "14 November 2026, 10:30 PM",
            "14 November 2026 10:30 PM",
            "14 Nov 2026, 10:30 PM",
            "4 November 2026, 10:30 PM",
            "14 november 2026, 10:30 PM",
            "14 September 2026, 10:30 PM",
            "14 Nov. 2026, 10:30 PM",
        ])

    def test_003_marker_dressings(self):
        self.check_forms([
            "14 November 2026, 9:30 PM",
            "14 November 2026, 10:30:15 PM",
            "14 November 2026, 10:30 AM",
            "14 November 2026, 10:30 pm",
            "14 November 2026, 10:30 Pm",
        ])

    def test_003_dotted_spaced_forms(self):
        self.check_forms([
            "14 November 2026, 10:30 P.M.",
            "14 November 2026 10:30 P.M.",
            "14 Nov 2026, 10:30 P.M.",
            "14 November 2026, 10:30 A.M.",
            "14 November 2026, 10:30 p.m.",
        ])

    def test_003_controls(self):
        self.check_forms([
            "14 November 2026, 10:30pm",
            "14 November 2026, 10:30P.M.",
            "14 November 2026, 10:30",
            "14th November 2026, 10:30 PM",
            "November 14, 2026, 10:30 PM",
            "November 14 2026, 10:30 PM",
            "10:30 PM, 14 November 2026",
            "10:30 P.M., 14 November 2026",
            "14 November 2026",
            "14 Nov 2026",
        ])


class Test005PlainTimeFirstCommaDayFirst(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_005_space_composition_forms(self):
        self.check_forms([
            "10:30 14 November, 2026",
            "9:05 14 November, 2026",
            "10:30 14 Nov, 2026",
            "10:30 14 Sept, 2026",
            "10:30:45 14 November, 2026",
        ])

    def test_005_comma_composition_forms(self):
        self.check_forms([
            "10:30, 14 November, 2026",
            "9:05, 14 November, 2026",
            "10:30, 14 Nov, 2026",
            "10:30:45, 14 November, 2026",
        ])

    def test_005_controls(self):
        self.check_forms([
            "10:30 PM 14 November, 2026",
            "10:30pm 14 November, 2026",
            "10:30 P.M. 14 November, 2026",
            "10:30P.M. 14 November, 2026",
            "10:30pm, 14 November, 2026",
            "14 November, 2026",
            "14 November, 2026, 10:30",
            "14 November, 2026, 10:30pm",
            "14 November, 2026, 10:30 PM",
            "10:30 14 November 2026",
            "10:30 November 14, 2026",
        ])
        self.assertEqual(
            stat_count(self.FRAME % "10:30"), 1)


if __name__ == "__main__":
    unittest.main()
