"""Step 17 round 3 fix seat F3 tests: checks and robots entries.

Each test pins one register entry on the behaviour the
register states, written before its cure. Entries:
S17-R3-016 to S17-R3-023.
"""

import unittest
import tempfile
from pathlib import Path

from citeline import checks, reporting, robots, service
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


def citations_for(sentences, facts=None):
    page = make_page(" ".join(sentences), sentences=sentences)
    return result_of(
        checks.run_checks(page, facts or {}, audit_date=AUDIT_DATE),
        "citations")


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


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def write_file(root, name, content):
    path = root / name
    path.write_text(content, encoding="utf-8")
    return path


class TestChecksR3F3(unittest.TestCase):

    def test_016_host_still_holding_percent_counts_no_citation(self):
        frame = ("The long sentence here cites %s for the full "
                 "report details today.")
        for target in (
            "https://rival%252Eexample/report",
            "https://rival%zzexample/report",
            "https://rival%2Gexample/report",
        ):
            result = citations_for([frame % target])
            self.assertEqual(
                result["detail_counts"]["distinct_target_count"],
                0, target)
        facts = {"domain": "macroforge.example"}
        result = citations_for(
            [frame % "https://macroforge%252Eexample/guide"], facts)
        self.assertEqual(
            result["detail_counts"]["distinct_target_count"], 0)

    def test_017_further_quotation_marks_count_and_mask(self):
        words = "Teams plan better together every single week"
        spans = [
            "\u300c" + words + "\u300d",
            "\u300e" + words + "\u300f",
            "\u00bb" + words + "\u00ab",
            "\uff02" + words + "\uff02",
            "\u2039" + words + "\u203a",
            "\u2033" + words + "\u2033",
            "\u201a" + words + "\u2018",
        ]
        for span in spans:
            text = ("The note reads %s said Priya Nair in the "
                    "review today." % span)
            result = quotations_for(text)
            self.assertEqual(
                result["detail_counts"]["attributed_span_count"],
                1, span)
        for span in (
            "\u300cgrowth hit 42 percent overall this quarter\u300d",
            "\u00bbgrowth hit 42 percent overall this quarter\u00ab",
        ):
            result = statistics_for(
                "The note reads %s in the margin today." % span)
            self.assertEqual(
                result["detail_counts"]["statistic_token_count"],
                0, span)

    def test_018_curly_single_span_with_apostrophe_counts(self):
        text = ("The note reads \u2018Teams don\u2019t plan alone "
                "any single week\u2019 said Priya Nair in the "
                "review today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"], 1)

    def test_019_date_fragments_in_comma_and_space_forms(self):
        forms = [
            "14 November, 2026",
            "14 Nov, 2026",
            "3 March, 2025",
            "5 Jan, 99",
            "2026 November, 14",
            "2025, March 3",
            "November, 14 2026",
            "2026-11-14 10:30:45",
            "2026-11",
        ]
        for form in forms:
            result = statistics_for(
                "The review met on %s in the main office "
                "downtown today." % form)
            self.assertEqual(
                result["detail_counts"]["statistic_token_count"],
                0, form)

    def test_020_one_part_named_version_counts_nothing(self):
        for text in (
            "Now on version: 2 the tool brings many daily users "
            "together.",
            "Now on version 2 the tool brings many daily users "
            "together.",
            "The tool is at version: 10 for many daily users "
            "together.",
            "Now on version: 2.0 the tool brings many daily "
            "users together.",
        ):
            result = statistics_for(text)
            self.assertEqual(
                result["detail_counts"]["statistic_token_count"],
                0, text)

    def test_021_bracketed_and_parenthesised_url_digits_masked(self):
        for text in (
            "See http://[::1]:8080/archive/12345 for the full "
            "archive listing today.",
            "See https://data.example/wiki/Foo_(bar)/12345 for "
            "the full archive listing today.",
            "See https://data.example/archive/12345 for the "
            "full archive listing today.",
        ):
            result = statistics_for(text)
            self.assertEqual(
                result["detail_counts"]["statistic_token_count"],
                0, text)

    def test_022_canonical_form_strips_and_reads_ipv6(self):
        frame = ("The long sentence here cites %s for the full "
                 "report details today.")
        links = [
            {"target": "https://rival.example/report",
             "text": "x", "start": None, "end": None},
            {"target": "https://rival.example/report ",
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
        result = citations_for([
            frame % "https://[::1]:8080/report",
            frame % "https://[::2]:9090/report",
        ])
        self.assertEqual(
            result["detail_counts"]["distinct_target_count"], 2)


class TestPreviewR3F3(unittest.TestCase):

    def preview(self, root, home, first, second):
        return service.robots_preview(
            home=str(home), first_robots_file=str(first),
            second_robots_file=str(second),
            audit_date=AUDIT_DATE, evaluated_page_path="/bbx")

    def test_023_preview_diff_same_size_under_either_rule_order(self):
        root, home = make_home(self)
        second = write_file(
            root, "b.txt",
            "User-agent: GPTBot\nDisallow: /c\n")
        first_a = write_file(
            root, "a.txt",
            "User-agent: GPTBot\nDisallow: /a\nDisallow: /bb\n")
        first_b = write_file(
            root, "c.txt",
            "User-agent: GPTBot\nDisallow: /bb\nDisallow: /a\n")
        run_a = self.preview(root, home, first_a, second)
        run_b = self.preview(root, home, first_b, second)
        def row_key(row):
            return (row["token"], row["first_finding"] or "",
                    row["second_finding"] or "")

        rows_a = sorted(row_key(row) for row in run_a["changed_rows"])
        rows_b = sorted(row_key(row) for row in run_b["changed_rows"])
        self.assertEqual(len(run_a["changed_rows"]), 2)
        self.assertEqual(rows_a, rows_b)


if __name__ == "__main__":
    unittest.main()
