"""Checks and robots entries.

Each test pins one settled rule on the behaviour the register
states, written before its cure. Entries: to and."""

import time
import unittest
import tempfile
from pathlib import Path

from citeline import checks, robots, service
from citeline import install as install_module

AUDIT_DATE = "2026-11-14"


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


def citations_for(sentences, facts=None, links=()):
    page = make_page(
        " ".join(sentences), sentences=sentences, links=links)
    return result_of(
        checks.run_checks(page, facts or {}, audit_date=AUDIT_DATE),
        "citations")


def statistics_for(text, links=()):
    page = make_page(text, links=links)
    return result_of(
        checks.run_checks(page, {}, audit_date=AUDIT_DATE),
        "statistics")


def quotations_for(text):
    page = make_page(text)
    return result_of(
        checks.run_checks(page, {}, audit_date=AUDIT_DATE),
        "quotations")


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def write_file(root, name, content):
    path = root / name
    path.write_text(content, encoding="utf-8")
    return path


class TestChecksR4F3(unittest.TestCase):

    def test_017_decoded_delimiters_make_self_citations(self):
        frame = ("The long sentence here cites %s for the full "
                 "report details today.")
        facts = {"domain": "macroforge.example"}
        for target in (
            "https://macroforge.example%2Fguide/report",
            "https://macroforge.example%3A443/report",
            "https://macroforge.example%3a443/report",
            "https://macroforge.example%23frag/report",
            "https://macroforge.example%3Fq/report",
            "https://macroforge&#46;example/guide",
            "https://macroforge.example&#47;guide",
        ):
            result = citations_for([frame % target], facts)
            self.assertEqual(
                result["detail_counts"]["distinct_target_count"],
                0, target)
            self.assertEqual(result["reason_code"], "CIT_SELF_ONLY",
                             target)

    def test_017_encoded_at_sign_splits_in_both_readings(self):
        links = [
            {"target": "https://macroforge%2Eexample%40rival.example/guide",
             "text": "x", "start": None, "end": None},
            {"target": "https://macroforge.example@rival.example/guide",
             "text": "y", "start": None, "end": None},
        ]
        page = make_page(
            "The long sentence here cites links for the full "
            "report details today.", links=links)
        result = result_of(
            checks.run_checks(page, {}, audit_date=AUDIT_DATE),
            "citations")
        self.assertEqual(
            result["detail_counts"]["distinct_target_count"], 1)
        frame = ("The long sentence here cites %s for the full "
                 "report details today.")
        facts = {"domain": "macroforge.example"}
        result = citations_for(
            [frame % "https://rival.example%40macroforge.example/guide"],
            facts)
        self.assertEqual(
            result["detail_counts"]["distinct_target_count"], 0)

    def test_018_further_quotation_marks_count_and_mask(self):
        words = "Teams plan better together every single week"
        spans = [
            "\u300a" + words + "\u300b",
            "\u3008" + words + "\u3009",
            "\u3010" + words + "\u3011",
            "\u3016" + words + "\u3017",
            "\uff62" + words + "\uff63",
            "\u201e" + words + "\u201d",
        ]
        for span in spans:
            text = ("The note reads %s said Priya Nair in the "
                    "review today." % span)
            result = quotations_for(text)
            self.assertEqual(
                result["detail_counts"]["attributed_span_count"],
                1, span)
            stats = statistics_for(
                "The note reads %s in the margin today."
                % span.replace(words, "growth hit 42 percent "
                                       "overall this quarter"))
            self.assertEqual(
                stats["detail_counts"]["statistic_token_count"],
                0, span)

    def test_019_curly_single_possessive_and_elision(self):
        cases = [
            "The note reads \u2018The dogs\u2019 toys are better "
            "every single week\u2019 said Priya Nair in the "
            "review today.",
            "The note reads \u2018Back in \u201989 we planned "
            "better every week\u2019 said Priya Nair in the "
            "review today.",
            "The note reads \u2018It is the teams\u2019 best "
            "plan this week\u2019 said Priya Nair in the "
            "review today.",
        ]
        for text in cases:
            result = quotations_for(text)
            self.assertEqual(
                result["detail_counts"]["attributed_span_count"],
                1, text)
        result = quotations_for(cases[2])
        self.assertEqual(
            result["evidence_spans"][0]["excerpt"],
            "\u2018It is the teams\u2019 best plan this week\u2019")
        stats = statistics_for(
            "The note reads \u2018Growth of dogs\u2019 sales hit "
            "42 percent this quarter\u2019 in the margin today.")
        self.assertEqual(
            stats["detail_counts"]["statistic_token_count"], 0)

    def test_020_further_date_fragment_forms_count_nothing(self):
        forms = [
            "November 14,2026",
            "Nov 14,2026",
            "November 14 , 2026",
            "2026-11-14T10:30:45+05:00",
            "2026-11-14T10:30:45-05:00",
            "November 14, 2026 10:30:45",
            "2026/11/14 10:30:45",
            "2026-11-14, 10:30",
            "2026 11 14",
            "14 11 2026",
        ]
        for form in forms:
            result = statistics_for(
                "The review met on %s in the main office "
                "downtown today." % form)
            self.assertEqual(
                result["detail_counts"]["statistic_token_count"],
                0, form)

    def test_021_version_naming_composed_connectors(self):
        result = statistics_for(
            "Now on version is: 2 the tool brings many daily "
            "users together.")
        self.assertEqual(
            result["detail_counts"]["statistic_token_count"], 0)

    def test_022_url_path_with_apostrophe_masks_digits(self):
        result = statistics_for(
            "See https://data.example/wiki/John's/12345 for the "
            "full archive listing today.")
        self.assertEqual(
            result["detail_counts"]["statistic_token_count"], 0)

    def test_023_leading_whitespace_target_counts(self):
        for target in (
            " https://rival.example/report",
            "\thttps://rival.example/report",
            "\nhttps://rival.example/report",
        ):
            links = [{"target": target, "text": "x",
                      "start": None, "end": None}]
            page = make_page(
                "The long sentence here cites links for the "
                "full report details today.", links=links)
            result = result_of(
                checks.run_checks(page, {}, audit_date=AUDIT_DATE),
                "citations")
            self.assertEqual(
                result["detail_counts"]["distinct_target_count"],
                1, repr(target))

    def test_025_robots_text_route_lone_surrogate(self):
        text = "User-agent: *\nDisallow: /a\ud800\n"
        for route in (robots.evaluate_robots_text,
                      robots.evaluate_robots):
            with self.assertRaises(robots.RobotsError) as caught:
                route(text, "/a")
            self.assertEqual(caught.exception.token,
                             "ROBOTS_DECODING_FAILED")

    def test_065_long_token_statistics_cost(self):
        text = "Macroforge " + "x" * 50000 + " end today"
        page = make_page(text)
        start = time.monotonic()
        result = checks._statistic_analysis(page)
        elapsed = time.monotonic() - start
        self.assertEqual(result["count"], 0)
        self.assertLess(elapsed, 4.0,
                        "statistics on one long token took %.2fs"
                        % elapsed)

    def test_065_many_links_statistics_cost(self):
        parts = []
        links = []
        cursor = 0
        for index in range(4000):
            piece = ("[item%d](https://data%d.example/a/%d) "
                     % (index, index, 10000 + index))
            start = cursor + piece.index("[") + 1
            links.append({
                "target": "https://data%d.example/a/%d"
                          % (index, 10000 + index),
                "text": "item%d" % index,
                "start": start,
                "end": start + len("item%d" % index),
            })
            parts.append(piece)
            cursor += len(piece)
        text = "".join(parts) + "plain closing words here today"
        page = make_page(text, links=links)
        start = time.monotonic()
        result = checks._statistic_analysis(page)
        elapsed = time.monotonic() - start
        self.assertEqual(result["count"], 0)
        self.assertLess(elapsed, 6.0,
                        "statistics over many links took %.2fs"
                        % elapsed)


class TestPreviewR4F3(unittest.TestCase):

    def preview(self, root, home, first, second):
        return service.robots_preview(
            home=str(home), first_robots_file=str(first),
            second_robots_file=str(second),
            audit_date=AUDIT_DATE, evaluated_page_path="/bbx")

    def test_024_winning_text_not_both_removed_and_changed(self):
        root, home = make_home(self)
        second = write_file(
            root, "b.txt",
            "User-agent: GPTBot\nDisallow: /c\nDisallow: /ee\n")
        first_a = write_file(
            root, "a.txt",
            "User-agent: GPTBot\nDisallow: /a\nDisallow: /bb\n"
            "Disallow: /dd\n")
        first_b = write_file(
            root, "c.txt",
            "User-agent: GPTBot\nDisallow: /dd\nDisallow: /bb\n"
            "Disallow: /a\n")
        for first in (first_a, first_b):
            result = self.preview(root, home, first, second)
            rows = result["changed_rows"]
            self.assertEqual(len(rows), 3, rows)
            others = [
                row for row in rows
                if not (row["first_finding"] == "Disallow: /bb"
                        and row["second_finding"] is None)
            ]
            self.assertEqual(len(others), len(rows) - 1, rows)
            for row in others:
                self.assertNotEqual(
                    row["first_finding"], "Disallow: /bb", rows)


if __name__ == "__main__":
    unittest.main()
