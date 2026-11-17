"""Step 17 round 16 fix seat F3 tests: checks entries.

Each test pins one register entry on the behaviour the
register states, written before its cure. Entries:
S17-R16-004, S17-R16-005, S17-R16-006, S17-R16-007,
and S17-R16-008, curing in that order.
"""

import time
import unittest

from citeline import checks

AUDIT_DATE = "2026-11-17"


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


def statistics_span_form(first):
    return (
        "The note reads " + O + first + C
        + "; growth hit 42 percent and she called "
        + O + "best plan this week and more words follow"
        + C + " in the margin today.")


class Test004AdverbPastTheList(unittest.TestCase):

    def test_004_actually_six_followers(self):
        for punct in (",", ";", ":", ".", "!", "?"):
            text = plain_form("It is actually the cats", punct)
            self.assertEqual(span_total(text), 1, text)

    def test_004_adverb_wordings_comma(self):
        for adverb in (
            "certainly", "clearly", "obviously", "probably",
            "definitely", "truly", "simply", "merely",
            "indeed", "finally", "essentially",
        ):
            text = plain_form(
                "It is " + adverb + " the cats", ",")
            self.assertEqual(span_total(text), 1, text)

    def test_004_yellow_adverb_wordings(self):
        for first in (
            "It is quite the cats",
            "It is certainly the cats",
            "It is probably the dogs",
            "It is arguably the cats",
            "It is truly the cats",
            "It is indeed the dogs",
            "It is simply the cats",
            "It was actually the dogs",
            "It is largely the cats",
        ):
            for punct in (",", ";"):
                text = plain_form(first, punct)
                self.assertEqual(span_total(text), 1, text)


class Test004PredeterminerAndCopulaAndDeterminer(
        unittest.TestCase):

    def test_004_predeterminer_wordings(self):
        for first in (
            "It is all the cats",
            "They are both the dogs",
            "It is half the cats",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)

    def test_004_copula_wordings(self):
        for first in (
            "It is becoming the cats",
            "It was remaining the cats",
            "It is seeming the cats",
            "It stays the cats",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)

    def test_004_yellow_appears_wordings(self):
        for first in (
            "It appears the cats",
            "The winner appears the dogs",
        ):
            for punct in (",", ";"):
                text = plain_form(first, punct)
                self.assertEqual(span_total(text), 1, text)

    def test_004_determiner_wordings(self):
        for first in (
            "It is some cats",
            "It is no cats",
            "It is any cats",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)

    def test_004_statistics_forms(self):
        for first in (
            "It is actually the cats",
            "It is some cats",
            "It is becoming the cats",
            "It is quite the cats",
            "It appears the cats",
        ):
            text = statistics_span_form(first)
            self.assertEqual(span_total(text), 1, text)
            self.assertEqual(stat_count(text), 0, text)


class Test004And005Controls(unittest.TestCase):

    def test_pinned_possessive_controls(self):
        for first in (
            "It is the dogs",
            "The first prize was the dogs",
            "It is the cats",
            "It is the winning cats",
            "It is really the cats",
            "It remains the cats",
            "It is those cats",
            "It seems the cats",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)

    def test_true_closing_controls(self):
        for first in (
            "It is the results",
            "The results are the figures",
            "The prize was the dogs",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 2, text)


class Test005WindowBound(unittest.TestCase):

    def test_005_six_listed_adverbs(self):
        text = plain_form(
            "It is really still also just even only the cats",
            ",")
        self.assertEqual(span_total(text), 1, text)

    def test_005_six_modifiers(self):
        text = plain_form(
            "It is the big strong fast brave bright winning "
            "cats", ",")
        self.assertEqual(span_total(text), 1, text)

    def test_005_adverb_and_six_modifiers(self):
        text = plain_form(
            "It is really the big strong fast brave bright "
            "winning cats", ",")
        self.assertEqual(span_total(text), 1, text)

    def test_005_five_modifier_boundary_control(self):
        text = plain_form(
            "It is the big strong fast brave winning cats",
            ",")
        self.assertEqual(span_total(text), 1, text)

    def test_005_statistics_form(self):
        text = statistics_span_form(
            "It is the big strong fast brave bright winning "
            "cats")
        self.assertEqual(span_total(text), 1, text)
        self.assertEqual(stat_count(text), 0, text)


class Test006CompanionAttribution(unittest.TestCase):

    def test_006_checks_verb_battery(self):
        for verb in (
            "answered", "responded", "commented", "mentioned",
            "claimed", "announced", "concluded", "suggested",
            "admitted", "warned", "shouted", "murmured",
            "agreed",
        ):
            text = companion_form(
                ";", verb + " Priya Nair")
            self.assertEqual(span_total(text), 2, text)

    def test_006_present_and_two_word_forms(self):
        for tail in (
            "answers Priya Nair",
            "pointed out Priya Nair",
        ):
            text = companion_form(";", tail)
            self.assertEqual(span_total(text), 2, text)

    def test_006_red_verb_battery(self):
        for verb in ("quoted", "argues", "contends", "tells"):
            text = companion_form(
                ";", verb + " Priya Nair")
            self.assertEqual(span_total(text), 2, text)

    def test_006_yellow_verb_battery(self):
        for verb in (
            "claimed", "announced", "argued", "confirmed",
            "concluded", "mentioned", "predicted",
            "suggested", "thought",
        ):
            text = companion_form(
                ";", verb + " Priya Nair")
            self.assertEqual(span_total(text), 2, text)

    def test_006_subject_forms(self):
        for tail in ("claimed she", "announced the chair"):
            text = companion_form(";", tail)
            self.assertEqual(span_total(text), 2, text)

    def test_006_cured_controls(self):
        for tail in (
            "said Priya Nair", "replied Priya Nair",
            "noted the chair", "whispered she",
            "replied the panel of judges",
            "stated Dr Nair", "whispered the chair",
            "said she", "said the chair",
        ):
            text = companion_form(";", tail)
            self.assertEqual(span_total(text), 2, text)

    def test_006_statistics_form(self):
        text = (
            "The note reads " + O
            + "The report is the findings" + C
            + ", growth hit 42 percent and she called " + O
            + "best plan this week and more words follow"
            + C + "; answered Priya Nair in the review "
            "today.")
        self.assertEqual(span_total(text), 2, text)
        self.assertEqual(stat_count(text), 1, text)


class Test007DateFirstJoinerForms(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_007_punctuation_joiners(self):
        self.check_forms([
            "14 November 2026 (10:30 PM)",
            "November 14, 2026 (10:30 PM)",
            "14 November 2026 / 10:30 PM",
            "November 14, 2026 / 10:30 PM",
            "14 November 2026 & 10:30 PM",
            "14 November 2026-10:30 PM",
        ])

    def test_007_glued_marker(self):
        self.check_forms([
            "14 November 2026 at 10:30PM",
        ])

    def test_007_yellow_joiner_forms(self):
        self.check_forms([
            "14 November 2026 and 10:30 PM",
            "14 November 2026 by 10:30 PM",
            "14 November 2026 before 10:30 PM",
            "14 November 2026 -- 10:30 PM",
        ])

    def test_007_controls(self):
        self.check_forms([
            "14 November 2026 at 10:30 PM",
            "14 November 2026, at 10:30 PM",
            "14 November 2026 on 10:30 PM",
            "14 November 2026; 10:30 PM",
            "14 November 2026: 10:30 PM",
            "14 November 2026 | 10:30 PM",
            "14 November 2026 - 10:30 PM",
            "14 November 2026, 10:30 PM",
            "14 November 2026 10:30 PM",
            "14 November 2026",
        ])


class Test008TimeFirstJoinerForms(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_008_checks_joiners(self):
        self.check_forms([
            "10:30 | 14 November, 2026",
            "10:30: 14 November, 2026",
            "10:30 / 14 November, 2026",
            "10:30 (14 November, 2026",
            "10:30 & 14 November, 2026",
            "10:30-14 November, 2026",
        ])

    def test_008_yellow_joiners(self):
        self.check_forms([
            "10:30 and 14 November, 2026",
            "10:30 by 14 November, 2026",
            "10:30 before 14 November, 2026",
        ])

    def test_008_controls(self):
        self.check_forms([
            "10:30 on 14 November, 2026",
            "10:30 at 14 November, 2026",
            "10:30, on 14 November, 2026",
            "10:30; 14 November, 2026",
            "10:30 - 14 November, 2026",
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
