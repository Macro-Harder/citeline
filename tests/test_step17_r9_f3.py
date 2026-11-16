"""Step 17 round 9 fix seat F3 tests: checks and robots entries.

Each test pins one register entry on the behaviour the
register states, written before its cure. Entries:
S17-R9-004 to S17-R9-008.
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


class Test004TrueClosingOnPunctuationFollower(unittest.TestCase):

    def test_004_list_form_three_spans(self):
        text = (
            "The note reads \u2018First quoted span stands "
            "here now\u2019, \u2018Second quoted span stands "
            "here too\u2019, \u2018Third quoted span stands "
            "here as well\u2019 in the review today.")
        self.assertEqual(span_total(text), 3)
        self.assertEqual(excerpts_for(text), [
            "\u2018First quoted span stands here now\u2019",
            "\u2018Second quoted span stands here too\u2019",
            "\u2018Third quoted span stands here as well\u2019",
        ])

    def test_004_comma_follower_with_attribution(self):
        text = (
            "The note reads \u2018First quoted span stands "
            "here now\u2019, said Priya Nair, \u2018Second "
            "quoted span stands here too\u2019 in the review "
            "today.")
        self.assertEqual(span_total(text), 2)
        self.assertEqual(excerpts_for(text), [
            "\u2018First quoted span stands here now\u2019",
            "\u2018Second quoted span stands here too\u2019",
        ])

    def test_004_remaining_followers(self):
        for punct in (";", ":", ".", "!", "?"):
            text = (
                "The note reads \u2018First quoted span "
                "stands here now\u2019" + punct
                + " \u2018Second quoted span stands here "
                "too\u2019 in the review today.")
            self.assertEqual(span_total(text), 2, punct)
            self.assertEqual(excerpts_for(text), [
                "\u2018First quoted span stands here now\u2019",
                "\u2018Second quoted span stands here too\u2019",
            ], punct)

    def test_004_statistics_figure_between_spans_counts(self):
        text = (
            "The note reads \u2018First quoted span stands "
            "here now\u2019; growth hit 42 percent in the "
            "margin. \u2018Second quoted span stands here "
            "too\u2019 said Tom Reed in the review today.")
        self.assertEqual(stat_count(text), 1)

    def test_004_possessive_composition_own_closing_closes(self):
        text = (
            "The note reads \u2018It is the dogs\u2019, she "
            "called \u2018best plan this week and more words "
            "follow\u2019 as one outer span, \u2018Further "
            "quoted span stands here now\u2019 said Priya "
            "Nair in the review today.")
        self.assertEqual(span_total(text), 2)
        self.assertEqual(excerpts_for(text), [
            "\u2018It is the dogs\u2019, she called \u2018best "
            "plan this week and more words follow\u2019",
            "\u2018Further quoted span stands here now\u2019",
        ])

    def test_004_space_follower_control(self):
        text = (
            "The note reads \u2018First quoted span stands "
            "here now\u2019 said Priya Nair in the review. "
            "\u2018Second quoted span stands here too\u2019 "
            "said Tom Reed in the review.")
        self.assertEqual(span_total(text), 2)
        self.assertEqual(excerpts_for(text), [
            "\u2018First quoted span stands here now\u2019",
            "\u2018Second quoted span stands here too\u2019",
        ])

    def test_004_punctuation_follower_no_further_pair_control(self):
        text = (
            "The note reads \u2018It is the dogs\u2019, she "
            "called \u2018best plan\u2019 this week\u2019 "
            "said Priya Nair in the review today.")
        self.assertEqual(span_total(text), 1)
        self.assertEqual(excerpts_for(text), [
            "\u2018It is the dogs\u2019, she called \u2018best "
            "plan\u2019 this week\u2019",
        ])


class Test005PossessiveAfterSpanIsNoClosing(unittest.TestCase):

    FIRST = (
        "The note reads \u2018First quoted span stands here "
        "now\u2019 said Priya Nair. \u2018Second quoted span "
        "stands here too\u2019 said Tom Reed, ")

    def check_two_spans(self, text):
        self.assertEqual(span_total(text), 2)
        self.assertEqual(excerpts_for(text), [
            "\u2018First quoted span stands here now\u2019",
            "\u2018Second quoted span stands here too\u2019",
        ])

    def test_005_coordinated_possessive(self):
        self.check_two_spans(
            self.FIRST
            + "reviewing the dogs\u2019 and the cats\u2019 "
            "toys in the park today.")

    def test_005_predicate_possessive_at_sentence_end(self):
        text = (
            "The note reads \u2018First quoted span stands "
            "here now\u2019 said Priya Nair. \u2018Second "
            "quoted span stands here too\u2019 said Tom Reed; "
            "the fault in the end was the dogs\u2019.")
        self.check_two_spans(text)

    def test_005_possessive_before_preposition(self):
        for tail in (
            "reviewing the teams\u2019 per game figures in "
            "the park today.",
            "reviewing the dogs\u2019 with the cats in the "
            "park today.",
            "reviewing the dogs\u2019 in the park today.",
        ):
            self.check_two_spans(self.FIRST + tail)

    def test_005_content_word_control(self):
        text = (
            "The note reads \u2018First quoted span stands "
            "here now\u2019 said Priya Nair. \u2018Second "
            "quoted span stands here too\u2019 said Tom Reed, "
            "reviewing the dogs\u2019 form today.")
        self.check_two_spans(text)

    def test_005_adjective_follower_control(self):
        self.check_two_spans(
            self.FIRST
            + "reviewing the dogs\u2019 old toys in the "
            "park today.")


class Test006SpacePossessiveBeforeMatchedPair(unittest.TestCase):

    def test_006_matched_nested_pair_after_space_possessive(self):
        text = (
            "The note reads \u2018It is the dogs\u2019 she "
            "called \u2018best plan\u2019 this week\u2019 "
            "said Priya Nair in the review today.")
        self.assertEqual(span_total(text), 1)
        self.assertEqual(excerpts_for(text), [
            "\u2018It is the dogs\u2019 she called \u2018best "
            "plan\u2019 this week\u2019",
        ])

    def test_006_longer_outer_tail(self):
        text = (
            "The note reads \u2018It is the dogs\u2019 she "
            "called \u2018best plan this week\u2019 and more "
            "words follow here\u2019 said Priya Nair in the "
            "review today.")
        self.assertEqual(span_total(text), 1)
        self.assertEqual(excerpts_for(text), [
            "\u2018It is the dogs\u2019 she called \u2018best "
            "plan this week\u2019 and more words follow "
            "here\u2019",
        ])

    def test_006_space_possessive_no_pair_control(self):
        text = (
            "The note reads \u2018It is the dogs\u2019 and "
            "more words follow here today\u2019 said Priya "
            "Nair in the review today.")
        self.assertEqual(span_total(text), 1)
        self.assertEqual(excerpts_for(text), [
            "\u2018It is the dogs\u2019 and more words follow "
            "here today\u2019",
        ])

    def test_006_punctuation_matched_control(self):
        text = (
            "The note reads \u2018It is the dogs\u2019, she "
            "called \u2018best plan\u2019 this week\u2019 "
            "said Priya Nair in the review today.")
        self.assertEqual(span_total(text), 1)
        self.assertEqual(excerpts_for(text), [
            "\u2018It is the dogs\u2019, she called \u2018best "
            "plan\u2019 this week\u2019",
        ])


class Test007FragmentTimeFirstCompositions(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_007_time_first_comma_before_fragment(self):
        self.check_forms([
            "10:30, 2026-11",
            "10:30, 11.2026",
            "10:30, 2026.11",
        ])

    def test_007_time_first_spaced_marker_before_fragment(self):
        self.check_forms([
            "10:30 PM 2026.11",
            "10:30 PM 2026-11",
            "10:30 PM 11-2026",
            "10:30 PM, 2026-11",
        ])

    def test_007_fragment_with_glued_marker_time(self):
        self.check_forms([
            "2026-11 10:30pm",
            "2026.11 10:30pm",
            "2026.11 10:30AM",
        ])

    def test_007_controls(self):
        self.check_forms([
            "10:30, 2026-11-14",
            "10:30 2026-11",
            "2026-11 10:30",
            "2026.11 10:30",
        ])


class Test008TimeFirstMarkerBeforeFullDate(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_008_dotted_date_after_marker(self):
        self.check_forms([
            "10:30 PM, 14.11.2026",
            "10:30 PM 14.11.2026",
            "10:30 AM 2026.11.14",
            "10:30 AM, 2026.11.14",
        ])

    def test_008_slash_date_after_marker(self):
        self.check_forms([
            "10:30 PM, 2026/11/14",
            "10:30 PM, 14/11/2026",
        ])

    def test_008_hyphen_controls(self):
        self.check_forms([
            "10:30 PM, 2026-11-14",
            "10:30 PM 14-11-2026",
            "10:30PM, 2026-11-14",
        ])


if __name__ == "__main__":
    unittest.main()
