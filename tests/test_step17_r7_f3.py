"""Checks and robots entries.

Each test pins one register entry on the behaviour the register
states, written before its cure. Entries: to."""

import subprocess
import sys
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


def finding_for(report, token):
    for finding in report["findings"]:
        if finding["token"] == token:
            return finding
    raise AssertionError(token)


class Test019SharedClosingNestedFamily(unittest.TestCase):

    def test_019_outer_span_reads_whole(self):
        text = (
            "The note reads \u201cOuter words \u201einner "
            "quoted words stand here and more outer words "
            "follow\u201d said Priya Nair in the review "
            "today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            1)
        self.assertEqual(
            result["evidence_spans"][0]["excerpt"],
            "\u201cOuter words \u201einner quoted words "
            "stand here and more outer words follow\u201d")

    def test_019_statistics_mask_covers_outer_span(self):
        text = (
            "The note reads \u201cGrowth hit 42 percent in "
            "the \u201einner quoted words stand here and "
            "more words follow\u201d in the margin today.")
        self.assertEqual(stat_count(text), 0)

    def test_019_second_shared_closing_control(self):
        text = (
            "The note reads \u201cOuter words \u201einner "
            "quoted words\u201d and more outer words "
            "follow\u201d said Priya Nair in the review "
            "today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            1)
        self.assertEqual(
            result["evidence_spans"][0]["excerpt"],
            "\u201cOuter words \u201einner quoted words"
            "\u201d and more outer words follow\u201d")


class Test020PossessiveBeforeUnmatchedNested(unittest.TestCase):

    def test_020_span_reads_whole_past_possessive(self):
        text = (
            "The note reads \u2018It is the dogs\u2019, she "
            "called \u2018best plan this week and more "
            "words follow\u2019 as one outer span, said "
            "Priya Nair in the review today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            1)
        self.assertEqual(
            result["evidence_spans"][0]["excerpt"],
            "\u2018It is the dogs\u2019, she called \u2018best "
            "plan this week and more words follow\u2019")

    def test_020_statistics_figure_inside_span_masked(self):
        text = (
            "The note reads \u2018It is the dogs\u2019, "
            "growth hit 42 percent as she called \u2018best "
            "plan this week and more words follow\u2019 in "
            "the margin today.")
        self.assertEqual(stat_count(text), 0)

    def test_020_matched_nested_control(self):
        text = (
            "The note reads \u2018It is the dogs\u2019, she "
            "called \u2018best plan\u2019 this week\u2019 said "
            "Priya Nair in the review today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"],
            1)
        self.assertEqual(
            result["evidence_spans"][0]["excerpt"],
            "\u2018It is the dogs\u2019, she called \u2018best "
            "plan\u2019 this week\u2019")


class Test021DateFragmentCompositions(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def check_forms(self, forms):
        for form in forms:
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)

    def test_021_comma_before_time_of_hyphen_date(self):
        self.check_forms([
            "14-11-2026, 10:30",
            "2026-1-4, 10:30",
        ])

    def test_021_single_digit_iso_with_time_in_t_form(self):
        self.check_forms([
            "2026-1-4T10:30",
            "2026-1-4T9:30",
        ])

    def test_021_time_first_with_comma_or_hyphen_date(self):
        self.check_forms([
            "10:30, 2026-11-14",
            "10:30 14-11-2026",
            "10:30 11-14-2026",
        ])

    def test_021_year_month_fragment_with_time(self):
        self.check_forms([
            "11-2026 10:30",
            "2026-11 10:30",
        ])

    def test_021_year_month_fragment_dotted(self):
        self.check_forms([
            "2026.11",
            "11.2026",
        ])


class Test022IdentifierFragmentPositions(unittest.TestCase):

    FRAME = ("The review met on %s in the main office "
             "downtown today.")

    def test_022_fragment_forms_inside_identifiers(self):
        for form in (
            "file_11-2026_v2",
            "file_2026.11_v2",
            "file_11.2026_v2",
        ):
            self.assertEqual(
                stat_count(self.FRAME % form), 0, form)


class Test023VersionMaskCost(unittest.TestCase):

    def test_023_repeated_connectors_with_figure(self):
        for text in (
            "Now on version is is 2 the tool brings many "
            "daily users together.",
            "Now on version: is: 2 the tool brings many "
            "daily users together.",
            "Now on version:: is 2 the tool brings many "
            "daily users together.",
        ):
            self.assertEqual(stat_count(text), 0, text)

    def test_023_repeated_connectors_no_figure_returns(self):
        product_root = str(Path(__file__).resolve().parent.parent)
        child = (
            "import sys\n"
            "sys.path.insert(0, " + repr(product_root) + ")\n"
            "sys.path.insert(0, " + repr(
                str(Path(__file__).resolve().parent)) + ")\n"
            "from test_step17_r7_f3 import stat_count\n"
            "frames = [\n"
            "    'Now on version ' + 'is ' * 30 + 'the tool "
            "brings many daily users together today.',\n"
            "    'Now on version ' + ': is ' * 20 + 'the "
            "tool brings many daily users together "
            "today.',\n"
            "    'Now on version ' + 'is : ' * 20 + 'the "
            "tool brings many daily users together "
            "today.',\n"
            "]\n"
            "print([stat_count(frame) for frame in frames])\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", child],
            capture_output=True, text=True, timeout=20,
            cwd=product_root,
        )
        self.assertEqual(completed.returncode, 0,
                         completed.stderr)
        self.assertEqual(completed.stdout.strip(), "[0, 0, 0]")


class Test024RobotsTrailingComment(unittest.TestCase):

    def test_024_comment_after_agent_name(self):
        text = ("User-agent: GPTBot # training bot\n"
                "Disallow: /private\n")
        report = robots.evaluate_robots_text(
            text, evaluated_page_path="/private")
        self.assertEqual(
            finding_for(report, "GPTBot")["outcome"],
            "blocked")
        self.assertEqual(report["unknown_token_count"], 0)

    def test_024_comment_after_rule_path(self):
        for line in ("Disallow: /private # keep out",
                     "Disallow: /private# keep out"):
            text = "User-agent: GPTBot\n" + line + "\n"
            report = robots.evaluate_robots_text(
                text, evaluated_page_path="/private")
            self.assertEqual(
                finding_for(report, "GPTBot")["outcome"],
                "blocked", line)

    def test_024_plain_control_blocked(self):
        text = "User-agent: GPTBot\nDisallow: /private\n"
        report = robots.evaluate_robots_text(
            text, evaluated_page_path="/private")
        self.assertEqual(
            finding_for(report, "GPTBot")["outcome"],
            "blocked")


class Test025RobotsRouteValueTypes(unittest.TestCase):

    def test_025_bytes_route_on_text_string(self):
        with self.assertRaises(robots.RobotsError) as caught:
            robots.evaluate_robots_bytes(
                "User-agent: *\n", "/a")
        self.assertEqual(caught.exception.token,
                         "ROBOTS_DECODING_FAILED")

    def test_025_bytes_route_on_none(self):
        with self.assertRaises(robots.RobotsError) as caught:
            robots.evaluate_robots_bytes(None, "/a")
        self.assertEqual(caught.exception.token,
                         "ROBOTS_DECODING_FAILED")

    def test_025_text_route_on_bytes(self):
        with self.assertRaises(robots.RobotsError) as caught:
            robots.evaluate_robots_text(
                b"User-agent: *\n", "/a")
        self.assertEqual(caught.exception.token,
                         "ROBOTS_DECODING_FAILED")

    def test_025_text_route_on_none(self):
        with self.assertRaises(robots.RobotsError) as caught:
            robots.evaluate_robots_text(None, "/a")
        self.assertEqual(caught.exception.token,
                         "ROBOTS_DECODING_FAILED")

    def test_025_dispatch_route_control(self):
        report = robots.evaluate_robots(
            b"User-agent: *\nDisallow: /a\n", "/a")
        self.assertIn("findings", report)
        report = robots.evaluate_robots(
            "User-agent: *\nDisallow: /a\n", "/a")
        self.assertIn("findings", report)


if __name__ == "__main__":
    unittest.main()
