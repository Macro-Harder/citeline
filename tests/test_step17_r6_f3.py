"""Checks and robots entries.

Each test pins one settled rule on the behaviour the register
states, written before its cure. Entries: to."""

import unittest
from pathlib import Path

from citeline import checks, robots

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


def distinct_targets(first, second):
    links = [
        {"target": first, "text": "x", "start": None, "end": None},
        {"target": second, "text": "y", "start": None, "end": None},
    ]
    page = make_page(
        "The long sentence here cites links for the full "
        "report details today.", links=links)
    result = result_of(
        checks.run_checks(page, {}, audit_date=AUDIT_DATE),
        "citations")
    return result["detail_counts"]["distinct_target_count"]


class Test016UnmatchedNestedOpening(unittest.TestCase):

    def test_016_cross_family_unmatched_nested_openings(self):
        cases = [
            (
                "The note reads \u201cOuter words \u00abinner "
                "quoted words stand here and more outer words "
                "follow\u201d said Priya Nair in the review "
                "today.",
                "\u201cOuter words \u00abinner quoted words "
                "stand here and more outer words follow\u201d",
            ),
            (
                "The note reads \u201cOuter words \u2018inner "
                "quoted words stand here and more outer words "
                "follow\u201d said Priya Nair in the review "
                "today.",
                "\u201cOuter words \u2018inner quoted words "
                "stand here and more outer words follow\u201d",
            ),
            (
                "The note reads \u00abOuter words \u201cinner "
                "quoted words stand here and more outer words "
                "follow\u00bb said Priya Nair in the review "
                "today.",
                "\u00abOuter words \u201cinner quoted words "
                "stand here and more outer words follow\u00bb",
            ),
        ]
        for text, span in cases:
            result = quotations_for(text)
            self.assertEqual(
                result["detail_counts"]["attributed_span_count"],
                1, text)
            self.assertEqual(
                result["evidence_spans"][0]["excerpt"], span,
                text)

    def test_016_same_family_second_opening_one_closing(self):
        text = (
            "The note reads \u201cOuter words \u201cinner "
            "quoted words stand here and more outer words "
            "follow\u201d said Priya Nair in the review today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"], 1)
        self.assertEqual(
            result["evidence_spans"][0]["excerpt"],
            "\u201cOuter words \u201cinner quoted words stand "
            "here and more outer words follow\u201d")

    def test_016_statistics_mask_covers_outer_span(self):
        for text in (
            "The note reads \u201cOuter words \u00abinner "
            "words growth hit 42 percent overall\u201d in the "
            "margin today.",
            "The note reads \u201cOuter words \u2018inner "
            "words growth hit 42 percent overall\u201d in the "
            "margin today.",
        ):
            self.assertEqual(stat_count(text), 0, text)


class Test017PossessiveBeforeNestedQuotation(unittest.TestCase):

    def test_017_span_reads_whole_past_possessive(self):
        text = (
            "The note reads \u2018It is the dogs\u2019, she "
            "called \u2018best plan\u2019 this week\u2019 said "
            "Priya Nair in the review today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"], 1)
        self.assertEqual(
            result["evidence_spans"][0]["excerpt"],
            "\u2018It is the dogs\u2019, she called \u2018best "
            "plan\u2019 this week\u2019")

    def test_017_statistics_figure_inside_span_masked(self):
        text = (
            "The note reads \u2018It is the dogs\u2019, growth "
            "hit 42 percent as she called \u2018best plan\u2019 "
            "this week\u2019 in the margin today.")
        self.assertEqual(stat_count(text), 0)


class Test018DateOrdersCompleted(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_018_hyphen_dates_with_their_time(self):
        self.check_forms([
            "14-11-26 10:30",
            "26-11-14 10:30:45",
            "11-14-26 10:30",
            "14-11-2026 10:30",
        ])

    def test_018_time_first_and_dotted_with_time(self):
        self.check_forms([
            "10:30 2026-11-14",
            "10:30:45 2026-11-14",
            "10:30 14.11.2026",
            "14.11.2026 10:30",
        ])

    def test_018_comma_positions_month_name(self):
        self.check_forms([
            "14 November 2026, 10:30",
            "November 14 2026, 10:30",
            "14 November, 2026 10:30",
            "14 Nov, 2026 10:30",
            "2026, November 14 10:30",
            "2026 Nov 14 10:30",
        ])

    def test_018_single_digit_iso_parts(self):
        self.check_forms([
            "2026-1-4",
            "2026-1-4 9:30",
            "2026-11-4 10:30",
        ])

    def test_018_reverse_month_and_year(self):
        self.check_forms(["11-2026"])


class Test019IdentifierPositions(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_019_underscore_identifier_iso_datetime(self):
        self.check_forms(["report_2026-11-14T10:30"])

    def test_019_glued_time_and_year_month_fragments(self):
        self.check_forms([
            "2026-11-14T1030",
            "file_2026-11_v2",
            "file_2026-11_report",
            "file_2026_11_v2",
        ])

    def test_019_dotted_date_inside_identifier(self):
        self.check_forms(["file_14.11.26_v2"])


class Test020CanonicalPortAsWritten(unittest.TestCase):

    def test_020_non_ascii_digit_ports_stand_in_key(self):
        for port in ("\u0664\u0664\u0663", "\uff14\uff14\uff13"):
            self.assertEqual(
                distinct_targets(
                    "https://rival.example/guide",
                    "https://rival.example:" + port + "/guide"),
                2, port)
            self.assertEqual(
                checks._canonical_target(
                    "https://rival.example:" + port + "/guide"),
                "rival.example:" + port + "/guide", port)

    def test_020_underscore_sign_and_space_ports(self):
        for port in ("8_080", "+8080", " 8080"):
            self.assertEqual(
                distinct_targets(
                    "https://rival.example:8080/guide",
                    "https://rival.example:" + port + "/guide"),
                2, port)
            self.assertEqual(
                checks._canonical_target(
                    "https://rival.example:" + port + "/guide"),
                "rival.example:" + port + "/guide", port)


class Test021VersionDoubledConnectors(unittest.TestCase):

    def test_021_doubled_and_repeated_connectors(self):
        for text in (
            "Now on version: is: 2 the tool brings many daily "
            "users together.",
            "Now on version:: is 2 the tool brings many daily "
            "users together.",
            "Now on version is is 2 the tool brings many daily "
            "users together.",
        ):
            self.assertEqual(stat_count(text), 0, text)


class Test022RobotsFileNulPath(unittest.TestCase):

    def test_022_file_route_nul_in_path_string(self):
        path = "/tmp/nope\x00robots.txt"
        with self.assertRaises(robots.RobotsError) as caught:
            robots.evaluate_robots_file(path, "/a")
        self.assertEqual(caught.exception.token,
                         "ROBOTS_DECODING_FAILED")

    def test_022_file_route_nul_in_path_object(self):
        path = Path("/tmp/nope\x00robots.txt")
        with self.assertRaises(robots.RobotsError) as caught:
            robots.evaluate_robots_file(path, "/a")
        self.assertEqual(caught.exception.token,
                         "ROBOTS_DECODING_FAILED")

    def test_022_dispatch_route_control(self):
        with self.assertRaises(robots.RobotsError) as caught:
            robots.evaluate_robots("/tmp/nope\x00robots.txt", "/a")
        self.assertEqual(caught.exception.token,
                         "ROBOTS_DECODING_FAILED")


if __name__ == "__main__":
    unittest.main()
