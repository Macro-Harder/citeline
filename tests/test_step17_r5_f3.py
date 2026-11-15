"""Step 17 round 5 fix seat F3 tests: checks and robots entries.

Each test pins one register entry on the behaviour the
register states, written before its cure. Entries:
S17-R5-012 to S17-R5-022.
"""

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


def stat_count(text):
    return statistics_for(text)["detail_counts"][
        "statistic_token_count"]


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def write_file(root, name, content):
    path = root / name
    path.write_text(content, encoding="utf-8")
    return path


class Test012QuotedSpanCost(unittest.TestCase):

    def test_012_curly_double_pairs_inside_bound(self):
        text = "\u201cfour word span here\u201d " * 4000
        page = make_page(text)
        start = time.monotonic()
        result = checks._statistic_analysis(page)
        elapsed = time.monotonic() - start
        self.assertEqual(result["count"], 0)
        self.assertLess(elapsed, 4.0,
                        "statistics on quotation dense text took "
                        "%.2fs" % elapsed)

    def test_012_unmatched_curly_single_inside_bound(self):
        text = "\u2018word " * 4800
        page = make_page(text)
        start = time.monotonic()
        result = checks._statistic_analysis(page)
        elapsed = time.monotonic() - start
        self.assertEqual(result["count"], 0)
        self.assertLess(elapsed, 4.0,
                        "statistics on unmatched openings took "
                        "%.2fs" % elapsed)


class Test013EntityStepOver(unittest.TestCase):

    def test_013_padded_numeric_entities_read_self(self):
        frame = ("The long sentence here cites %s for the full "
                 "report details today.")
        facts = {"domain": "macroforge.example"}
        for target in (
            "https://macroforge.example&#0000000047;guide",
            "https://macroforge&#0000000046;example/guide",
            "https://macroforge.example&#x000000002F;guide",
        ):
            result = citations_for([frame % target], facts)
            self.assertEqual(
                result["detail_counts"]["distinct_target_count"],
                0, target)
            self.assertEqual(result["reason_code"], "CIT_SELF_ONLY",
                             target)

    def test_013_unterminated_numeric_entities_read_self(self):
        frame = ("The long sentence here cites %s for the full "
                 "report details today.")
        facts = {"domain": "macroforge.example"}
        for target in (
            "https://macroforge.example&#47guide/report",
            "https://macroforge&#46example/guide",
        ):
            result = citations_for([frame % target], facts)
            self.assertEqual(
                result["detail_counts"]["distinct_target_count"],
                0, target)


class Test014CanonicalPort(unittest.TestCase):

    def test_014_non_numeric_port_stands_in_key(self):
        pairs = [
            ("https://rival.example/guide",
             "https://rival.example:abc/guide"),
            ("https://rival.example:443:8080/guide",
             "https://rival.example:9999:1111/guide"),
            ("https://rival.example/guide",
             "https://rival.example%3A443%3A8080/guide"),
        ]
        for first, second in pairs:
            links = [
                {"target": first, "text": "x",
                 "start": None, "end": None},
                {"target": second, "text": "y",
                 "start": None, "end": None},
            ]
            page = make_page(
                "The long sentence here cites links for the "
                "full report details today.", links=links)
            result = result_of(
                checks.run_checks(page, {}, audit_date=AUDIT_DATE),
                "citations")
            self.assertEqual(
                result["detail_counts"]["distinct_target_count"],
                2, (first, second))


class Test015NestedQuotations(unittest.TestCase):

    def test_015_curly_double_inside_curly_double(self):
        text = ("The note reads \u201cOuter words \u201cinner "
                "quoted words stand here\u201d and more outer "
                "words follow\u201d said Priya Nair in the review "
                "today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"], 1)
        self.assertEqual(
            result["evidence_spans"][0]["excerpt"],
            "\u201cOuter words \u201cinner quoted words stand "
            "here\u201d and more outer words follow\u201d")
        stats = statistics_for(
            "The note reads \u201cOuter words \u201cinner words "
            "stand\u201d growth hit 42 percent overall\u201d in "
            "the margin today.")
        self.assertEqual(
            stats["detail_counts"]["statistic_token_count"], 0)

    def test_015_guillemet_inside_guillemet(self):
        text = ("The note reads \u00abOuter words \u00abinner "
                "quoted words stand here\u00bb and more outer "
                "words follow\u00bb said Priya Nair in the review "
                "today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"], 1)
        self.assertEqual(
            result["evidence_spans"][0]["excerpt"],
            "\u00abOuter words \u00abinner quoted words stand "
            "here\u00bb and more outer words follow\u00bb")

    def test_015_straight_double_inside_curly_double(self):
        text = ("The note reads \u201cOuter words \"inner quoted "
                "words stand here\" and more outer words "
                "follow\u201d said Priya Nair in the review today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"], 1)
        self.assertEqual(
            result["evidence_spans"][0]["excerpt"],
            "\u201cOuter words \"inner quoted words stand here\" "
            "and more outer words follow\u201d")


class Test016PossessivePunctuation(unittest.TestCase):

    def test_016_possessive_before_punctuation(self):
        for mark in (",", ";", "!"):
            text = ("The note reads \u2018It is the dogs\u2019%s "
                    "best plan this week\u2019 said Priya Nair in "
                    "the review today." % mark)
            result = quotations_for(text)
            self.assertEqual(
                result["detail_counts"]["attributed_span_count"],
                1, text)
            self.assertEqual(
                result["evidence_spans"][0]["excerpt"],
                "\u2018It is the dogs\u2019%s best plan this "
                "week\u2019" % mark, text)

    def test_016_possessive_at_sentence_crossing(self):
        text = ("The note reads \u2018The first prize was the "
                "dogs\u2019. The second prize came later\u2019 "
                "said Priya Nair in the review today.")
        result = quotations_for(text)
        self.assertEqual(
            result["detail_counts"]["attributed_span_count"], 1)
        self.assertEqual(
            result["evidence_spans"][0]["excerpt"],
            "\u2018The first prize was the dogs\u2019. The second "
            "prize came later\u2019")
        stats = statistics_for(
            "The note reads \u2018Growth of dogs\u2019, sales "
            "hit 42 percent this quarter\u2019 in the margin "
            "today.")
        self.assertEqual(
            stats["detail_counts"]["statistic_token_count"], 0)


class Test017DateOrders(unittest.TestCase):

    def test_017_date_with_time_in_further_orders(self):
        forms = [
            "11/14/2026 10:30:45",
            "14/11/2026 10:30",
            "11/14/2026, 10:30",
            "14 November 2026 10:30:45",
            "14 Nov 2026 10:30",
            "November 14 2026 10:30:45",
            "November 14th, 2026 10:30:45",
            "11/14/26 10:30",
            "2026-11-14 9:30:45",
            "2026-11-14T9:30",
            "14 11 2026 10:30",
            "14 11 2026 10:30:45",
            "2026 11 14 10:30",
        ]
        for form in forms:
            self.assertEqual(
                stat_count(
                    "The review met on %s in the main office "
                    "downtown today." % form),
                0, form)

    def test_017_time_first_datetimes(self):
        for form in (
            "10:30 November 14, 2026",
            "10:30:45, 14 November 2026",
        ):
            self.assertEqual(
                stat_count(
                    "The review met on %s in the main office "
                    "downtown today." % form),
                0, form)

    def test_017_two_digit_year_numeric_dates(self):
        for form in (
            "26-11-14",
            "14-11-26",
            "26 11 14",
            "14 11 26",
            "Nov 14th, 26",
        ):
            self.assertEqual(
                stat_count(
                    "The review met on %s in the main office "
                    "downtown today." % form),
                0, form)


class Test018IdentifierDates(unittest.TestCase):

    def test_018_date_inside_identifier_counts_nothing(self):
        for form in (
            "2026-11-14_report",
            "file_2026_11_14_v2",
            "report2026-11-14final",
            "abc-2026-11-14",
            "id20261114x",
        ):
            self.assertEqual(
                stat_count(
                    "The review met on %s in the main office "
                    "downtown today." % form),
                0, form)


class Test019VersionReverse(unittest.TestCase):

    def test_019_reverse_composition_of_connectors(self):
        for text in (
            "Now on version: is 2 the tool brings many daily "
            "users together.",
            "Now on version:is 2 the tool brings many daily "
            "users together.",
            "Now on version : is 2 the tool brings many daily "
            "users together.",
            "Now on version: is 2.5 the tool brings many daily "
            "users together.",
        ):
            self.assertEqual(stat_count(text), 0, text)


class Test020UrlApostrophes(unittest.TestCase):

    def test_020_two_apostrophes_in_sequence_mask_digits(self):
        self.assertEqual(
            stat_count(
                "See https://data.example/a''12345 for the full "
                "archive listing today."),
            0)


class Test021PreviewPairing(unittest.TestCase):

    def preview(self, home, first, second):
        return service.robots_preview(
            home=str(home), first_robots_file=str(first),
            second_robots_file=str(second),
            audit_date=AUDIT_DATE, evaluated_page_path="/bbx")

    def test_021_winning_text_twice_reserved_at_each_standing(self):
        root, home = make_home(self)
        second = write_file(
            root, "b.txt",
            "User-agent: GPTBot\nDisallow: /c\nDisallow: /ee\n")
        first_a = write_file(
            root, "a.txt",
            "User-agent: GPTBot\nDisallow: /bb\n"
            "User-agent: GPTBot\nDisallow: /bb\nDisallow: /a\n")
        first_b = write_file(
            root, "c.txt",
            "User-agent: GPTBot\nDisallow: /bb\nDisallow: /a\n"
            "User-agent: GPTBot\nDisallow: /bb\n")
        for first in (first_a, first_b):
            result = self.preview(home, first, second)
            rows = result["changed_rows"]
            self.assertEqual(len(rows), 3, rows)
            for row in rows:
                if row["second_finding"] is None:
                    self.assertEqual(
                        row["first_finding"], "Disallow: /bb", rows)
                else:
                    self.assertNotEqual(
                        row["first_finding"], "Disallow: /bb", rows)

    def test_021_winning_text_three_times(self):
        root, home = make_home(self)
        second = write_file(
            root, "b.txt",
            "User-agent: GPTBot\nDisallow: /c\nDisallow: /ee\n"
            "Disallow: /ff\n")
        first = write_file(
            root, "a.txt",
            "User-agent: GPTBot\nDisallow: /bb\n"
            "User-agent: GPTBot\nDisallow: /bb\n"
            "User-agent: GPTBot\nDisallow: /bb\n")
        result = self.preview(home, first, second)
        rows = result["changed_rows"]
        self.assertEqual(len(rows), 4, rows)
        for row in rows:
            if row["second_finding"] is None:
                self.assertEqual(
                    row["first_finding"], "Disallow: /bb", rows)
            else:
                self.assertNotEqual(
                    row["first_finding"], "Disallow: /bb", rows)


class Test022RobotsFileSurrogate(unittest.TestCase):

    def test_022_file_route_lone_surrogate_in_path(self):
        path = "/tmp/nope\ud800robots.txt"
        with self.assertRaises(robots.RobotsError) as caught:
            robots.evaluate_robots_file(path, "/a")
        self.assertEqual(caught.exception.token,
                         "ROBOTS_DECODING_FAILED")


if __name__ == "__main__":
    unittest.main()
