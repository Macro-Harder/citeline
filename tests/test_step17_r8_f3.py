"""Checks and robots entries.

Each test pins one settled rule on the behaviour the register
states, written before its cure. Entries: to."""

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


class Test008SeparateCurlySingleSpans(unittest.TestCase):

    def test_008_two_spans_read_as_two(self):
        text = (
            "The note reads \u2018First quoted span stands "
            "here now\u2019 said Priya Nair in the review. "
            "\u2018Second quoted span stands here too\u2019 "
            "said Tom Reed in the review.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            2)
        self.assertEqual(excerpts_for(text), [
            "\u2018First quoted span stands here now\u2019",
            "\u2018Second quoted span stands here too\u2019",
        ])

    def test_008_three_spans_read_as_three(self):
        text = (
            "The note reads \u2018First quoted span stands "
            "here now\u2019 said Priya Nair. \u2018Second "
            "quoted span stands here too\u2019 said Tom Reed. "
            "\u2018Third quoted span stands here as well\u2019 "
            "said Ana Ruiz in the review.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            3)
        self.assertEqual(excerpts_for(text), [
            "\u2018First quoted span stands here now\u2019",
            "\u2018Second quoted span stands here too\u2019",
            "\u2018Third quoted span stands here as well\u2019",
        ])

    def test_008_statistics_figure_between_spans_counts(self):
        text = (
            "The note reads \u2018First quoted span stands "
            "here now\u2019 and growth hit 42 percent in the "
            "margin. \u2018Second quoted span stands here "
            "too\u2019 said Tom Reed in the review today.")
        self.assertEqual(stat_count(text), 1)

    def test_008_trailing_apostrophe_form(self):
        text = (
            "The note reads \u2018First quoted span stands "
            "here now\u2019 said Priya Nair. \u2018Second "
            "quoted span stands here too\u2019 said Tom Reed, "
            "reviewing the dogs\u2019 form today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            2)
        self.assertEqual(excerpts_for(text), [
            "\u2018First quoted span stands here now\u2019",
            "\u2018Second quoted span stands here too\u2019",
        ])

    def test_008_newline_separated_control(self):
        text = (
            "The note reads \u2018First quoted span stands "
            "here now\u2019 said Priya Nair in the review.\n"
            "\u2018Second quoted span stands here too\u2019 "
            "said Tom Reed in the review.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            2)

    def test_008_possessive_six_followers_still_hold(self):
        for punct in (",", ";", "!", ".", "?", ":"):
            text = (
                "The note reads \u2018It is the dogs\u2019"
                + punct
                + " she called \u2018best plan this week and "
                "more words follow\u2019 as one outer span, "
                "said Priya Nair in the review today.")
            result = quotations_for(text)
            self.assertEqual(
                result["detail_counts"][
                    "attributed_span_count"],
                1, punct)
            self.assertEqual(excerpts_for(text), [
                "\u2018It is the dogs\u2019" + punct
                + " she called \u2018best plan this week "
                "and more words follow\u2019",
            ], punct)

    def test_008_possessive_two_unmatched_nested_still_hold(self):
        text = (
            "The note reads \u2018It is the dogs\u2019, she "
            "called \u2018best \u2018plan this week and more "
            "words follow\u2019 as one outer span, said "
            "Priya Nair in the review today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            1)
        self.assertEqual(excerpts_for(text), [
            "\u2018It is the dogs\u2019, she called \u2018best "
            "\u2018plan this week and more words follow\u2019",
        ])

    def test_008_possessive_matched_nested_control(self):
        text = (
            "The note reads \u2018It is the dogs\u2019, she "
            "called \u2018best plan\u2019 this week\u2019 said "
            "Priya Nair in the review today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            1)
        self.assertEqual(excerpts_for(text), [
            "\u2018It is the dogs\u2019, she called \u2018best "
            "plan\u2019 this week\u2019",
        ])

    def test_008_possessive_statistics_limb_still_holds(self):
        text = (
            "The note reads \u2018It is the dogs\u2019; "
            "growth hit 42 percent as she called \u2018best "
            "plan this week and more words follow\u2019 in "
            "the margin today.")
        self.assertEqual(stat_count(text), 0)


class Test009DepthThreeSharedClosing(unittest.TestCase):

    def test_009_low_double_intermediate_curly_double_top(self):
        text = (
            "The note reads \u201cOuter words \u201einner "
            "\u201cdeep quoted words stand here and more "
            "words follow\u201d said Priya Nair in the "
            "review today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            1)
        self.assertEqual(excerpts_for(text), [
            "\u201cOuter words \u201einner \u201cdeep quoted "
            "words stand here and more words follow\u201d",
        ])

    def test_009_low_double_intermediate_curly_single_top(self):
        text = (
            "The note reads \u201cOuter words \u201einner "
            "\u2018single quoted words stand here and more "
            "follow\u201d said Priya Nair in the review "
            "today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            1)
        self.assertEqual(excerpts_for(text), [
            "\u201cOuter words \u201einner \u2018single "
            "quoted words stand here and more follow\u201d",
        ])

    def test_009_statistics_limb(self):
        text = (
            "The note reads \u201cGrowth hit 42 percent in "
            "the \u201einner \u2018single quoted words stand "
            "here and more follow\u201d in the margin today.")
        self.assertEqual(stat_count(text), 0)

    def test_009_top_shares_outer_only_control(self):
        text = (
            "The note reads \u201cOuter words \u00abinner "
            "\u201edeep quoted words stand here and more "
            "words follow\u201d said Priya Nair in the "
            "review today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            1)
        self.assertEqual(excerpts_for(text), [
            "\u201cOuter words \u00abinner \u201edeep quoted "
            "words stand here and more words follow\u201d",
        ])

    def test_009_all_curly_double_control(self):
        text = (
            "The note reads \u201cOuter words \u201cinner "
            "\u201cdeep quoted words stand here and more "
            "follow\u201d said Priya Nair in the review "
            "today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            1)
        self.assertEqual(excerpts_for(text), [
            "\u201cOuter words \u201cinner \u201cdeep quoted "
            "words stand here and more follow\u201d",
        ])

    def test_009_depth_two_pins_still_hold(self):
        text = (
            "The note reads \u201cOuter words \u201einner "
            "quoted words stand here and more outer words "
            "follow\u201d said Priya Nair in the review "
            "today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            1)
        self.assertEqual(excerpts_for(text), [
            "\u201cOuter words \u201einner quoted words "
            "stand here and more outer words follow\u201d",
        ])
        text = (
            "The note reads \u201cOuter words \u201einner "
            "quoted words\u201d and more outer words "
            "follow\u201d said Priya Nair in the review "
            "today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            1)
        self.assertEqual(excerpts_for(text), [
            "\u201cOuter words \u201einner quoted words"
            "\u201d and more outer words follow\u201d",
        ])


class Test010FragmentWithTimeDressings(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_010_dotted_fragment_with_time(self):
        self.check_forms([
            "2026.11 10:30",
            "11.2026 10:30",
        ])

    def test_010_fragment_after_time(self):
        self.check_forms([
            "10:30 2026-11",
            "10:30 11-2026",
            "10:30 2026.11",
            "10:30 11.2026",
        ])

    def test_010_fragment_with_comma_before_time(self):
        self.check_forms([
            "11-2026, 10:30",
            "2026-11, 10:30",
            "2026.11, 10:30",
        ])

    def test_010_cured_twins_control(self):
        self.check_forms([
            "11-2026 10:30",
            "2026-11 10:30",
            "2026.11",
            "11.2026",
        ])


class Test011FullDateCompositions(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_011_dotted_date_with_comma_before_time(self):
        self.check_forms([
            "14.11.2026, 10:30",
            "11.14.2026, 10:30",
            "2026.11.14, 10:30",
        ])

    def test_011_year_first_slash_date_with_comma(self):
        self.check_forms([
            "2026/11/14, 10:30",
        ])

    def test_011_year_first_dotted_date_with_time(self):
        self.check_forms([
            "2026.11.14 10:30",
        ])

    def test_011_day_first_hyphen_date_with_time_in_t_form(self):
        self.check_forms([
            "4-1-2026T10:30",
        ])

    def test_011_time_first_with_marker(self):
        self.check_forms([
            "10:30 PM, 2026-11-14",
            "10:30 PM 14-11-2026",
        ])

    def test_011_marker_glued_to_time_of_date_first_form(self):
        self.check_forms([
            "2026-11-14 10:30am",
        ])

    def test_011_cured_twins_control(self):
        self.check_forms([
            "14-11-2026, 10:30",
            "14/11/2026, 10:30",
            "14.11.2026 10:30",
            "2026-11-14 10:30 PM",
            "10:30 2026-11-14",
        ])


if __name__ == "__main__":
    unittest.main()
