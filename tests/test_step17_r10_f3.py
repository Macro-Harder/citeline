"""Step 17 round 10 fix seat F3 tests: checks entries.

Each test pins one register entry on the behaviour the
register states, written before its cure. Entries:
S17-R10-002, S17-R10-003, S17-R10-004, and
S17-R10-015.
"""

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
    O + "Second quoted span stands here too" + C)


class Test002TrueClosingOnSEndingWord(unittest.TestCase):

    def test_002_six_followers_direct(self):
        for punct in (",", ";", ":", ".", "!", "?"):
            text = (
                "The note reads " + O
                + "She published the results" + C + punct
                + " " + SECOND + " in the review today.")
            self.assertEqual(span_total(text), 2, punct)
            self.assertEqual(excerpts_for(text), [
                O + "She published the results" + C,
                SECOND,
            ], punct)

    def test_002_further_final_words(self):
        for first in (
            "He shared the figures",
            "He read the news",
            "She thanked the class",
            "She published the RESULTS",
        ):
            for punct in (",", ";"):
                text = (
                    "The note reads " + O + first + C + punct
                    + " " + SECOND + " in the review today.")
                self.assertEqual(span_total(text), 2, text)
                self.assertEqual(excerpts_for(text), [
                    O + first + C,
                    SECOND,
                ], text)

    def test_002_three_spans_list_form(self):
        text = (
            "The note reads " + O
            + "She published the results" + C + ", " + O
            + "He shared the figures" + C + ", " + O
            + "They filed the items" + C
            + " in the review today.")
        self.assertEqual(span_total(text), 3)
        self.assertEqual(excerpts_for(text), [
            O + "She published the results" + C,
            O + "He shared the figures" + C,
            O + "They filed the items" + C,
        ])

    def test_002_attribution_between_spans(self):
        text = (
            "The note reads " + O
            + "She published the results" + C
            + ", said Priya Nair, " + SECOND
            + " in the review today.")
        self.assertEqual(span_total(text), 2)
        self.assertEqual(excerpts_for(text), [
            O + "She published the results" + C,
            SECOND,
        ])

    def test_002_statistics_figure_between_spans_counts(self):
        text = (
            "The note reads " + O
            + "She published the results" + C
            + "; growth hit 42 percent in the margin. "
            + SECOND + " said Tom Reed today.")
        self.assertEqual(stat_count(text), 1)

    def test_002_red_yes_comma_form(self):
        text = (
            "The clerk answered " + O
            + "She said the answer was yes" + C
            + ", she noted, " + O
            + "Second quoted span stands here too" + C
            + " in the log today.")
        self.assertEqual(span_total(text), 2)
        self.assertEqual(excerpts_for(text), [
            O + "She said the answer was yes" + C,
            SECOND,
        ])

    def test_002_short_first_span_form(self):
        text = (
            "The note reads " + O + "The results" + C
            + ", " + SECOND + " in the review today.")
        self.assertEqual(excerpts_for(text), [SECOND])

    def test_002_plain_final_word_control(self):
        for punct in (",", ";", ":", ".", "!", "?"):
            text = (
                "The note reads " + O
                + "She published the outcome" + C + punct
                + " " + SECOND + " in the review today.")
            self.assertEqual(span_total(text), 2, punct)
            self.assertEqual(excerpts_for(text), [
                O + "She published the outcome" + C,
                SECOND,
            ], punct)

    def test_002_space_follower_control(self):
        text = (
            "The note reads " + O
            + "She published the results" + C
            + " said Priya Nair, " + SECOND
            + " in the review today.")
        self.assertEqual(span_total(text), 2)
        self.assertEqual(excerpts_for(text), [
            O + "She published the results" + C,
            SECOND,
        ])

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

    def test_002_possessive_matched_pair_controls(self):
        text = (
            "The note reads " + O + "It is the dogs" + C
            + ", she called " + O + "best plan" + C
            + " this week" + C
            + " said Priya Nair in the review today.")
        self.assertEqual(span_total(text), 1)
        self.assertEqual(excerpts_for(text), [
            O + "It is the dogs" + C + ", she called " + O
            + "best plan" + C + " this week" + C,
        ])
        text = (
            "The note reads " + O + "It is the dogs" + C
            + " she called " + O + "best plan" + C
            + " this week" + C
            + " said Priya Nair in the review today.")
        self.assertEqual(span_total(text), 1)
        self.assertEqual(excerpts_for(text), [
            O + "It is the dogs" + C + " she called " + O
            + "best plan" + C + " this week" + C,
        ])

    def test_002_possessive_outer_closing_controls(self):
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
        text = (
            "The note reads " + O + "It is the dogs" + C
            + " she called " + O + "best plan" + C
            + " for all the results" + C
            + " said Priya Nair in the review today.")
        self.assertEqual(span_total(text), 1)
        self.assertEqual(excerpts_for(text), [
            O + "It is the dogs" + C + " she called " + O
            + "best plan" + C + " for all the results" + C,
        ])


class Test003TimeFirstMarkerBeforeMonthNameDate(
        unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_003_spaced_marker_month_first(self):
        self.check_forms([
            "10:30 PM, November 14, 2026",
            "10:30 PM November 14, 2026",
        ])

    def test_003_spaced_marker_day_first(self):
        self.check_forms([
            "10:30 PM, 14 November 2026",
            "10:30 PM, 14 Nov 2026",
        ])

    def test_003_remaining_dressings(self):
        self.check_forms([
            "10:30PM, November 14, 2026",
            "10:30 PM, Nov 14, 2026",
            "10:30 PM, November 14th, 2026",
            "10:30 pm, November 14, 2026",
            "10:30 PM, 14th November 2026",
            "10:30PM November 14 2026",
        ])

    def test_003_controls(self):
        self.check_forms([
            "10:30 PM, 14.11.2026",
            "10:30 PM, 2026/11/14",
            "10:30 PM, 2026-11-14",
            "November 14, 2026 10:30 PM",
            "10:30, November 14, 2026",
        ])


class Test004FragmentFirstCommaGluedMarker(
        unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_004_glued_marker_forms(self):
        self.check_forms([
            "2026-11, 10:30pm",
            "2026.11, 10:30pm",
            "11-2026, 10:30pm",
            "11.2026, 10:30pm",
            "2026-11, 10:30PM",
            "2026-11, 10:30am",
        ])

    def test_004_controls(self):
        self.check_forms([
            "2026-11, 10:30 PM",
            "2026-11, 10:30",
            "2026-11 10:30pm",
            "2026.11, 10:30 PM",
        ])


class Test015SlashFragment(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_015_fragment_alone(self):
        self.check_forms([
            "2026/11",
            "11/2026",
        ])

    def test_015_time_first_comma(self):
        self.check_forms([
            "10:30, 2026/11",
            "10:30, 11/2026",
            "10:30 2026/11",
        ])

    def test_015_time_first_marker_compositions(self):
        self.check_forms([
            "10:30 PM 2026/11",
            "10:30 PM, 2026/11",
            "10:30 PM, 11/2026",
            "10:30PM 11/2026",
        ])

    def test_015_fragment_first_compositions(self):
        self.check_forms([
            "2026/11, 10:30",
            "2026/11 10:30pm",
            "11/2026, 10:30 PM",
        ])

    def test_015_controls(self):
        self.check_forms([
            "2026-11",
            "2026.11",
            "2026/11/14",
            "14/11/2026, 10:30",
        ])
        self.assertEqual(
            stat_count(self.FRAME % "10:30"), 1)


if __name__ == "__main__":
    unittest.main()
