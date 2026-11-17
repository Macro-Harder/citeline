"""Checks entries.

Each test pins one register entry on the behaviour the
register states, written before its cure. Entries:
and, curing in that order."""

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


def companion_form(sep, tail):
    return (
        "The note reads " + O + "The report is the findings"
        + C + ", she called " + SECOND + sep + " " + tail
        + " in the review today.")


class Test004ModifierBetweenDeterminerAndNoun(
        unittest.TestCase):

    def test_004_winning_six_followers(self):
        for punct in (",", ";", ":", ".", "!", "?"):
            text = plain_form("It is the winning cats", punct)
            self.assertEqual(span_total(text), 1, text)

    def test_004_modifier_wordings_comma(self):
        for first in (
            "It is the house cats",
            "It is the very best cats",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)


class Test004AdverbBetweenCopulaAndDeterminer(
        unittest.TestCase):

    def test_004_really_six_followers(self):
        for punct in (",", ";", ":", ".", "!", "?"):
            text = plain_form("It is really the cats", punct)
            self.assertEqual(span_total(text), 1, text)

    def test_004_adverb_wordings_comma_semicolon(self):
        for first in (
            "It was still the dogs",
            "It is also the cats",
            "It is just the cats",
            "It is not the dogs",
            "It was never the dogs",
            "It is still the cats",
            "The prize was really the dogs",
        ):
            for punct in (",", ";"):
                text = plain_form(first, punct)
                self.assertEqual(span_total(text), 1, text)


class Test004CopulaAndDeterminerPastTheLists(
        unittest.TestCase):

    def test_004_remains_six_followers(self):
        for punct in (",", ";", ":", ".", "!", "?"):
            text = plain_form("It remains the cats", punct)
            self.assertEqual(span_total(text), 1, text)

    def test_004_copula_wordings_comma(self):
        for first in (
            "It became the cats",
            "The prize became the cats",
            "It has become the cats",
            "The winner remains the dogs",
            "The results became the dogs",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)

    def test_004_those_and_my_six_followers(self):
        for first in ("It is those cats", "It is my cats"):
            for punct in (",", ";", ":", ".", "!", "?"):
                text = plain_form(first, punct)
                self.assertEqual(span_total(text), 1, text)

    def test_004_determiner_wordings_comma(self):
        for first in (
            "It is these cats",
            "It is my dogs",
            "They are these dogs",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)

    def test_004_statistics_form(self):
        text = (
            "The note reads " + O + "It is the winning cats"
            + C + "; growth hit 42 percent and she called "
            + O + "best plan this week and more words follow"
            + C + " in the margin today.")
        self.assertEqual(stat_count(text), 0, text)
        self.assertEqual(span_total(text), 1, text)


class Test004PinnedControls(unittest.TestCase):

    def test_004_pinned_possessive_controls(self):
        for first in (
            "It is the dogs",
            "The first prize was the dogs",
            "It is the cats",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)

    def test_004_true_closing_controls(self):
        for first in (
            "It is the results",
            "The results are the figures",
            "The prize was the dogs",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 2, text)


class Test011CompanionAttributionPastTheCure(
        unittest.TestCase):

    def test_011_said_control_separators(self):
        for sep in (",", ";", ":", "!", "?"):
            text = companion_form(sep, "said Priya Nair")
            self.assertEqual(span_total(text), 2, text)

    def test_011_verb_forms_semicolon(self):
        for verb in (
            "replied", "remarked", "observed", "stated",
            "declared", "explained", "continued",
            "insisted", "reported", "whispered",
        ):
            text = companion_form(
                ";", verb + " Priya Nair")
            self.assertEqual(span_total(text), 2, text)

    def test_011_subject_forms_semicolon(self):
        for tail in ("said she", "said the chair"):
            text = companion_form(";", tail)
            self.assertEqual(span_total(text), 2, text)

    def test_011_statistics_form(self):
        text = (
            "The note reads " + O
            + "The report is the findings" + C
            + ", growth hit 42 percent and she called " + O
            + "best plan this week and more words follow"
            + C + "; replied Priya Nair in the review "
            "today.")
        self.assertEqual(stat_count(text), 1, text)
        self.assertEqual(span_total(text), 2, text)

    def test_011_pinned_true_closing_control(self):
        text = (
            "The note reads " + O + "It is the results" + C
            + ", she called " + SECOND
            + "; replied Priya Nair in the review today.")
        self.assertEqual(span_total(text), 2, text)


class Test005DateFirstJoinerForms(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_005_charged_joiner_forms(self):
        self.check_forms([
            "14 November 2026 at 10:30 PM",
            "14 November 2026, at 10:30 PM",
            "14 November 2026 on 10:30 PM",
            "14 November 2026; 10:30 PM",
        ])

    def test_005_joiner_dressings(self):
        self.check_forms([
            "14 November 2026 at 10:30 P.M.",
            "14 Nov 2026 at 9:30 AM",
            "14 November 2026: 10:30 PM",
            "14 November 2026 | 10:30 PM",
            "14 November 2026 - 10:30 PM",
        ])

    def test_005_controls(self):
        self.check_forms([
            "14 November 2026, 10:30 PM",
            "14 November 2026 10:30 PM",
            "14 November 2026, 10:30 P.M.",
            "14 November 2026",
        ])


class Test006TimeFirstJoinerForms(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_006_charged_joiner_forms(self):
        self.check_forms([
            "10:30 on 14 November, 2026",
            "10:30 at 14 November, 2026",
            "10:30 on 14 Nov, 2026",
            "10:30, on 14 November, 2026",
        ])

    def test_006_joiner_dressings(self):
        self.check_forms([
            "9:05 at 14 November, 2026",
            "10:30:45 on 14 November, 2026",
            "10:30; 14 November, 2026",
            "10:30 - 14 November, 2026",
        ])

    def test_006_controls(self):
        self.check_forms([
            "10:30 14 November, 2026",
            "10:30, 14 November, 2026",
            "10:30 PM 14 November, 2026",
            "14 November, 2026",
        ])
        self.assertEqual(
            stat_count(self.FRAME % "10:30"), 1)


class TestSpanBatteryCost(unittest.TestCase):

    UNIT = (
        "The note reads " + O + "It is the dogs" + C
        + ", she called " + O + "best plan" + C
        + " this week" + C
        + " said Priya Nair in the review today. ")

    def test_battery_at_200_inside_bound(self):
        self.assertEqual(
            len(checks._quoted_spans(self.UNIT)), 1)
        text = self.UNIT * 200
        start = time.process_time()
        quotations_for(text)
        cpu = time.process_time() - start
        self.assertLess(cpu, 4.0)


if __name__ == "__main__":
    unittest.main()
