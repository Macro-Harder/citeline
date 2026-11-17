"""Checks entries.

Each test pins one register entry on the behaviour the
register states, written before its cure. Entries:
and, curing in that order."""

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


def statistics_companion_form(tail):
    return (
        "The note reads " + O
        + "The report is the findings" + C
        + ", growth hit 42 percent and she called " + O
        + "best plan this week and more words follow"
        + C + "; " + tail + " in the review today.")


EN = "\u2013"
EM = "\u2014"


class Test002AdverbPlacePastTheSets(unittest.TestCase):

    def test_002_adverbs_six_followers(self):
        for first in (
            "It is perhaps the cats",
            "It is maybe the cats",
            "It is triple the cats",
        ):
            for punct in (",", ";", ":", ".", "!", "?"):
                text = plain_form(first, punct)
                self.assertEqual(span_total(text), 1, text)

    def test_002_checks_adverb_wordings(self):
        for first in (
            "It is perhaps the cats",
            "It is maybe the cats",
            "It is in fact the cats",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)

    def test_002_red_adverb_wordings(self):
        for adverb in (
            "already", "often", "sometimes", "soon", "once",
            "again", "instead", "thus", "hence", "anyway",
            "ever",
        ):
            text = plain_form(
                "It is " + adverb + " the cats", ",")
            self.assertEqual(span_total(text), 1, text)

    def test_002_red_adverb_phrase_wordings(self):
        for first in (
            "It is of course the cats",
            "It is very much the cats",
            "It is no longer the cats",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)

    def test_002_yellow_adverb_wordings(self):
        for first in (
            "It is often the cats",
            "It is sometimes the cats",
        ):
            for punct in (",", ";"):
                text = plain_form(first, punct)
                self.assertEqual(span_total(text), 1, text)


class Test002DeterminerAndPredeterminerPlaces(
        unittest.TestCase):

    def test_002_checks_determiner_wordings(self):
        for first in (
            "It is many cats",
            "It is few cats",
            "It is several cats",
            "It is most cats",
            "It is other cats",
            "It is enough cats",
            "It is all cats",
            "It is both cats",
            "It is such cats",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)

    def test_002_red_determiner_wordings(self):
        for first in (
            "It is certain cats",
            "It is various cats",
            "It is numerous cats",
            "It is countless cats",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)

    def test_002_predeterminer_wordings(self):
        for first in (
            "It is triple the cats",
            "It is quadruple the cats",
            "It is just over half the cats",
            "It is three times the cats",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)


class Test002CopulaPlaceAndStatistics(unittest.TestCase):

    def test_002_copula_wordings(self):
        for first in (
            "It sounds the cats",
            "It smells the cats",
            "The winner sounds the dogs",
        ):
            for punct in (",", ";"):
                text = plain_form(first, punct)
                self.assertEqual(span_total(text), 1, text)

    def test_002_statistics_forms(self):
        for first in (
            "It is many cats",
            "It is perhaps the cats",
            "It is often the cats",
            "It is several cats",
            "It sounds the cats",
        ):
            text = statistics_span_form(first)
            self.assertEqual(span_total(text), 1, text)
            self.assertEqual(stat_count(text), 0, text)

    def test_002_controls(self):
        for first in (
            "It is the dogs",
            "The first prize was the dogs",
            "It is the cats",
            "It is actually the cats",
            "It is some cats",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 1, text)
        for first in (
            "It is the results",
            "The results are the figures",
            "The prize was the dogs",
        ):
            text = plain_form(first, ",")
            self.assertEqual(span_total(text), 2, text)


class Test003CompanionVerbsPastTheStemList(
        unittest.TestCase):

    def test_003_checks_verb_battery(self):
        for verb in (
            "acknowledged", "asserted", "complained",
            "confessed", "conceded", "cautioned",
            "disclosed", "emphasized", "emphasised",
            "hinted", "implied", "maintained", "revealed",
            "testified", "quipped", "interjected",
            "lamented", "opined", "speculated", "stressed",
            "highlighted", "underlined", "voiced", "vowed",
            "swore", "recounted", "reiterated", "boasted",
            "countered", "endorsed", "forecast", "joked",
            "pleaded", "pronounced",
        ):
            text = companion_form(
                ";", verb + " Priya Nair")
            self.assertEqual(span_total(text), 2, text)

    def test_003_verb_forms(self):
        for tail in (
            "acknowledges Priya Nair",
            "acknowledging Priya Nair",
            "asserts Priya Nair",
            "maintains Priya Nair",
            "revealing Priya Nair",
        ):
            text = companion_form(";", tail)
            self.assertEqual(span_total(text), 2, text)

    def test_003_red_verb_battery(self):
        for verb in (
            "affirmed", "alleged", "professed", "assured",
            "advised", "implored", "volunteered",
            "retorted", "rejoined", "recalled",
        ):
            text = companion_form(
                ";", verb + " Priya Nair")
            self.assertEqual(span_total(text), 2, text)

    def test_003_yellow_verb_battery(self):
        for verb in (
            "acknowledged", "asserted", "maintained",
            "emphasized", "recalled", "revealed",
        ):
            text = companion_form(
                ";", verb + " Priya Nair")
            self.assertEqual(span_total(text), 2, text)

    def test_003_every_separator(self):
        for sep in (";", ":", ",", ".", "!", "?", ""):
            text = companion_form(
                sep, "acknowledged Priya Nair")
            self.assertEqual(span_total(text), 2, text)

    def test_003_statistics_form(self):
        for tail in (
            "acknowledged Priya Nair",
            "revealed Priya Nair",
        ):
            text = statistics_companion_form(tail)
            self.assertEqual(span_total(text), 2, text)
            self.assertEqual(stat_count(text), 1, text)

    def test_003_controls(self):
        for tail in (
            "said Priya Nair",
            "answered Priya Nair",
            "pointed out Priya Nair",
        ):
            text = companion_form(";", tail)
            self.assertEqual(span_total(text), 2, text)
        text = companion_form("", "said Priya Nair")
        self.assertEqual(span_total(text), 2, text)


class Test004DateFirstSymbolJoiners(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_004_checks_symbol_joiners(self):
        self.check_forms([
            "14 November 2026 @ 10:30 PM",
            "November 14, 2026 @ 10:30 PM",
            "14 November 2026 " + EN + " 10:30 PM",
            "14 November 2026 " + EM + " 10:30 PM",
        ])

    def test_004_checks_dressing_variants(self):
        self.check_forms([
            "14th November 2026 @ 10:30 PM",
            "14 Nov 2026 @ 10:30 PM",
            "14 November 2026 @ 10:30PM",
            "14 November 2026 @ 10:30 P.M.",
            "14 November 2026 @ 10:30 pm",
        ])

    def test_004_red_symbol_joiners(self):
        self.check_forms([
            "14 November 2026 ~ 10:30 PM",
            "14 November 2026 [10:30 PM]",
            "14 November 2026 {10:30 PM}",
            "14 November 2026 at 10:30 P.M",
            "14 November 2026T10:30 PM",
        ])

    def test_004_yellow_symbol_joiners(self):
        self.check_forms([
            "14 November 2026 = 10:30 PM",
            "14 November 2026 _ 10:30 PM",
            "14 November 2026 . 10:30 PM",
            "14 November 2026 > 10:30 PM",
            "14 November 2026 + 10:30 PM",
            "14 November 2026 * 10:30 PM",
            "14 November 2026 % 10:30 PM",
            "14 November 2026 # 10:30 PM",
            "14 November 2026 \\ 10:30 PM",
            "November 14, 2026 ~ 10:30 PM",
        ])

    def test_004_yellow_word_joiners(self):
        self.check_forms([
            "14 November 2026 during 10:30 PM",
            "14 November 2026 circa 10:30 PM",
        ])

    def test_004_controls(self):
        self.check_forms([
            "14 November 2026 at 10:30 PM",
            "14 November 2026, at 10:30 PM",
            "14 November 2026 on 10:30 PM",
            "14 November 2026; 10:30 PM",
            "14 November 2026 | 10:30 PM",
            "14 November 2026 - 10:30 PM",
            "14 November 2026 (10:30 PM)",
            "14 November 2026, 10:30 PM",
            "14 November 2026 10:30 PM",
            "14 November 2026",
        ])


class Test005TimeFirstLimbs(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_005_charged_spelling_symbol_joiners(self):
        self.check_forms([
            "10:30 @ 14 November, 2026",
            "10:30 " + EN + " 14 November, 2026",
            "10:30 " + EM + " 14 November, 2026",
            "10:30 ~ 14 November, 2026",
        ])

    def test_005_yellow_joiner_limb(self):
        self.check_forms([
            "10:30 = 14 November, 2026",
            "10:30 _ 14 November, 2026",
            "10:30 . 14 November, 2026",
            "10:30 > 14 November, 2026",
            "10:30 + 14 November, 2026",
            "10:30 * 14 November, 2026",
        ])

    def test_005_month_first_order(self):
        self.check_forms([
            "10:30 | November 14, 2026",
            "10:30 & November 14, 2026",
            "10:30 by November 14, 2026",
            "10:30 @ November 14, 2026",
            "10:30 on November 14, 2026",
        ])

    def test_005_no_comma_date_spelling(self):
        self.check_forms([
            "10:30 | 14 November 2026",
            "10:30 & 14 November 2026",
            "10:30 by 14 November 2026",
        ])

    def test_005_marker_time_first(self):
        self.check_forms([
            "10:30 PM | 14 November, 2026",
            "10:30PM | 14 November, 2026",
            "10:30 PM / 14 November, 2026",
            "10:30pm on 14 November, 2026",
            "10:30 p.m. on 14 November, 2026",
        ])

    def test_005_yellow_marker_limb(self):
        self.check_forms([
            "10:30 PM on 14 November, 2026",
            "10:30 PM; 14 November, 2026",
            "10:30 PM and 14 November, 2026",
            "10:30 PM at 14 November, 2026",
            "10:30 PM on November 14, 2026",
        ])

    def test_005_controls(self):
        self.check_forms([
            "10:30 on 14 November, 2026",
            "10:30, 14 November, 2026",
            "10:30; 14 November, 2026",
            "10:30 | 14 November, 2026",
            "10:30 14 November, 2026",
            "10:30 PM 14 November, 2026",
            "10:30:45 | 14 November, 2026",
            "10:30 | 14th November, 2026",
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
