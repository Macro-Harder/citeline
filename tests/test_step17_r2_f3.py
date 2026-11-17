"""Checks and robots entries.

Each test pins one register entry on the behaviour the register
states, written before its cure. Entries: and."""

import datetime
import time
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


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def write_file(root, name, content):
    path = root / name
    path.write_text(content, encoding="utf-8")
    return path


class TestChecksR2(unittest.TestCase):

    def test_020_non_ascii_letter_glue_is_not_verbatim(self):
        facts = {"canonical_line": "Acme audits pages",
                 "is_product_page": True}
        for text in (
            "Acme audits pages\u00e9 tools for many daily users.",
            "\u00e9Acme audits pages for many daily users today.",
            "\u4e2dAcme audits pages for many daily users today.",
        ):
            page = make_page(text)
            result = result_of(
                checks.run_checks(page, facts, audit_date=AUDIT_DATE),
                "description_consistency")
            self.assertEqual(result["earned"], 0, text)
            self.assertEqual(result["reason_code"], "DESC_MISSING", text)

    def test_021_stated_equivalent_forms_count_as_one_target(self):
        pairs = [
            ("https://rival.example:443/report",
             "https://rival.example/report"),
            ("http://rival.example:80/report",
             "https://rival.example/report"),
            ("https://rival.example/report?b=2&a=1",
             "https://rival.example/report?a=1&b=2"),
            ("https://rival.example/report?a",
             "https://rival.example/report?a="),
            ("https://rival.example/a/../report",
             "https://rival.example/report"),
            ("https://rival.example/./report",
             "https://rival.example/report"),
            ("https://rival.example/%2e%2e/report",
             "https://rival.example/report"),
            ("https://rival.example/rep%6frt",
             "https://rival.example/report"),
            ("https://rival.example/a%2fb",
             "https://rival.example/a%2Fb"),
            ("https://rival.example/report//",
             "https://rival.example/report"),
            ("https://rival.example/a//b",
             "https://rival.example/a/b"),
        ]
        frame = ("The long sentence here cites %s for the full "
                 "report details today.")
        for first, second in pairs:
            result = citations_for([frame % first, frame % second])
            self.assertEqual(
                result["detail_counts"]["distinct_target_count"],
                1, (first, second))
        trio = [frame % form for form in (
            "https://rival.example/report",
            "https://rival.example:443/report",
            "http://rival.example:80/report")]
        result = citations_for(trio)
        self.assertEqual(
            result["detail_counts"]["distinct_target_count"], 1)

    def test_022_non_ascii_separators_and_percent_dot_are_self(self):
        facts = {"domain": "macroforge.example"}
        frame = ("Read our own page at %s today for full "
                 "details here now.")
        for target in (
            "https://macroforge\uff0eexample/guide",
            "https://macroforge\u3002example/guide",
            "https://macroforge\uff61example/guide",
            "https://macroforge%2Eexample/guide",
        ):
            result = citations_for([frame % target], facts)
            self.assertEqual(
                result["detail_counts"]["distinct_target_count"],
                0, target)
            self.assertEqual(result["reason_code"], "CIT_SELF_ONLY",
                             target)

    def test_023_empty_label_hosts_count_no_citation(self):
        frame = ("The long sentence here cites %s for the full "
                 "report details today.")
        for target in (
            "https://rival..example/report",
            "https://.rival.example/report",
        ):
            result = citations_for([frame % target])
            self.assertEqual(
                result["detail_counts"]["distinct_target_count"],
                0, target)
        facts = {"domain": "macroforge.example"}
        result = citations_for(
            [frame % "https://macroforge.example../guide"], facts)
        self.assertEqual(
            result["detail_counts"]["distinct_target_count"], 0)

    def test_024_further_quotation_marks_count_and_mask(self):
        spans = [
            "\u00abTeams plan better together every single week\u00bb",
            "\u201eTeams plan better together every single week\u201c",
            "\u2018Teams plan better together every single week\u2019",
            "\u201cTeams plan better together every single week\"",
            "\"Teams plan better together every single week\u201d",
        ]
        for span in spans:
            text = "The note reads %s said Priya Nair in the review." % span
            page = make_page(text)
            result = result_of(
                checks.run_checks(page, {}, audit_date=AUDIT_DATE),
                "quotations")
            self.assertEqual(
                result["detail_counts"]["attributed_span_count"],
                1, span)
        masked = statistics_for(
            "The note reads \u00abgrowth hit 42 percent overall "
            "this quarter\u00bb in the margin today.")
        self.assertEqual(
            masked["detail_counts"]["statistic_token_count"], 0)

    def test_025_date_fragments_in_further_forms_count_nothing(self):
        forms = [
            "november 14, 2026", "NOVEMBER 14, 2026",
            "nov 14, 2026", "NOV 14, 2026",
            "November 14 2026", "Nov 14 2026",
            "2026 November 14", "2026 Nov 14",
            "Nov 14, 26", "14 Nov 26",
            "14-Nov-2026", "Nov-14-2026",
            "2026-11-14T10:30",
        ]
        for form in forms:
            result = statistics_for(
                "The review met on %s in the main office downtown."
                % form)
            self.assertEqual(
                result["detail_counts"]["statistic_token_count"],
                0, form)

    def test_026_any_scheme_url_digits_are_not_statistics(self):
        for target in (
            "ftp://data.example/archive/12345",
            "myapp://data.example/archive/12345",
        ):
            result = statistics_for(
                "See %s for the full archive listing today." % target)
            self.assertEqual(
                result["detail_counts"]["statistic_token_count"],
                0, target)


class TestRobotsR2(unittest.TestCase):

    def test_027_star_scan_cost_stays_inside_limits_at_file_scale(self):
        rule_path = "/*" + "a" * 500 + "b"
        text = "User-agent: *\n" + "".join(
            "Disallow: %s\n" % rule_path for _ in range(2))
        path = "/" + "a" * 1999
        start = time.monotonic()
        report = robots.evaluate_robots_bytes(
            text.encode("utf-8"), evaluated_page_path=path)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 5.0)
        self.assertEqual(report["finding_count"], 25)

    def test_027_star_matching_semantics_hold(self):
        cases = [
            ("/a*b", "/axxb", True), ("/a*b", "/axxc", False),
            ("/a*b$", "/axxb", True), ("/a*b$", "/axxbc", False),
            ("/*", "/anything", True), ("/x", "/xyz", True),
            ("/x$", "/xyz", False), ("/a**b", "/ab", True),
            ("/*a*b", "/xaab", True), ("/*a*b", "/xbaa", False),
        ]
        for rule, path, expected in cases:
            text = "User-agent: GPTBot\nDisallow: %s\n" % rule
            report = robots.evaluate_robots_text(
                text, evaluated_page_path=path)
            finding = [f for f in report["findings"]
                       if f["token"] == "GPTBot"][0]
            self.assertEqual(
                finding["outcome"],
                "blocked" if expected else "allowed", (rule, path))

    def test_030_empty_agent_group_supplies_no_silent_allow_all(self):
        report = robots.evaluate_robots_text(
            "User-agent: \nDisallow: /\n", evaluated_page_path="/")
        self.assertIn("unparsed_lines_warning", report)
        for finding in report["findings"]:
            self.assertIn(finding["outcome"], ("allowed", None))

    def test_032_path_limit_is_measured_on_the_argument_as_supplied(self):
        text = "User-agent: *\nAllow: /\n"
        for path in ("/x?" + "a" * 5000, "/x#" + "a" * 5000):
            with self.assertRaises(robots.RobotsError) as caught:
                robots.evaluate_robots_text(
                    text, evaluated_page_path=path)
            self.assertEqual(caught.exception.token, "LIMIT_EXCEEDED")
        report = robots.evaluate_robots_text(
            text, evaluated_page_path="/x?short=1")
        self.assertEqual(report["evaluated_page_path"], "/x")

    def test_099_notices_stand_at_the_head_of_the_simple_form(self):
        html = ("<html><head><title>404 Not Found</title></head>"
                "<body><h1>404 Not Found</h1></body></html>\n")
        report = robots.evaluate_robots_text(
            html, evaluated_page_path="/private/")
        keys = list(report.keys())
        self.assertLess(keys.index("directive_notice"),
                        keys.index("findings"))
        simple = reporting.render(report, form="simple")
        self.assertLess(simple.index("No robots directive"),
                        simple.index("GPTBot"))
        orphan = robots.evaluate_robots_text(
            "Useragent: *\nDisallow: /private/\n",
            evaluated_page_path="/private/")
        keys = list(orphan.keys())
        self.assertLess(keys.index("unparsed_lines_warning"),
                        keys.index("findings"))
        simple = reporting.render(orphan, form="simple")
        self.assertLess(simple.index("not understood"),
                        simple.index("GPTBot"))

    def test_100_orphan_only_file_carries_one_account(self):
        report = robots.evaluate_robots_text(
            "Disallow: /private/\nAllow: /public/\n",
            evaluated_page_path="/private/")
        self.assertNotIn("directive_notice", report)
        self.assertIn("unparsed_lines_warning", report)


class TestPreviewR2(unittest.TestCase):

    def preview(self, root, home, first, second, **extra):
        kwargs = {"home": str(home), "first_robots_file": str(first),
                  "second_robots_file": str(second),
                  "audit_date": AUDIT_DATE}
        kwargs.update(extra)
        return service.robots_preview(**kwargs)

    def test_028_capture_date_objects_face_the_audit_date_check(self):
        root, home = make_home(self)
        a = write_file(root, "a.txt", "User-agent: *\nAllow: /\n")
        b = write_file(root, "b.txt", "User-agent: *\nDisallow: /\n")
        for value in (datetime.date(2027, 1, 1),
                      datetime.datetime(2027, 1, 1, 12, 0)):
            with self.assertRaises(Exception, msg=repr(value)):
                self.preview(root, home, a, b, first_capture_date=value)
            with self.assertRaises(Exception, msg=repr(value)):
                self.preview(root, home, a, b,
                             second_capture_date=value)
        with self.assertRaises(Exception):
            self.preview(root, home, a, b,
                         first_capture_date="2027-01-01")
        ok = self.preview(
            root, home, a, b,
            first_capture_date=datetime.date(2026, 11, 1))
        self.assertEqual(ok["first_capture_date"], "2026-11-01")

    def test_029_rule_text_change_shadowed_by_another_token_reports(self):
        root, home = make_home(self)
        first = write_file(
            root, "a.txt",
            "User-agent: GPTBot\nAllow: /x\n"
            "User-agent: ClaudeBot\nDisallow: /xyz\nAllow: /x\n")
        second = write_file(
            root, "b.txt",
            "User-agent: GPTBot\nDisallow: /x\n"
            "User-agent: ClaudeBot\nDisallow: /xyz\nDisallow: /x\n")
        result = self.preview(root, home, first, second,
                              evaluated_page_path="/xyz")
        tokens = [row["token"] for row in result["changed_rows"]]
        self.assertIn("GPTBot", tokens)
        self.assertIn("ClaudeBot", tokens)

    def test_031_outside_differences_name_any_differing_field(self):
        root, home = make_home(self)
        first = write_file(
            root, "a.txt", "User-agent: GPTBot\nDisallow: /a\n")
        second = write_file(
            root, "b.txt",
            "User-agent: GPTBot\nDisallow: /a\n"
            "User-agent: FooBot\nDisallow: /z\n"
            "plain words with no field form\n")
        result = self.preview(root, home, first, second,
                              evaluated_page_path="/zzz")
        self.assertEqual(result["changed_rows"], [])
        outside = result.get("evaluation_differences_outside_diff")
        self.assertIsNotNone(outside)
        self.assertEqual(outside.get("unknown_token_count"), [0, 1])
        self.assertEqual(
            outside.get("non_protocol_line_count"), [0, 1])
        orphan = write_file(
            root, "c.txt",
            "User-agent: GPTBot\nDisallow: /a\nDisallow: /b\n")
        with_orphan = write_file(
            root, "d.txt",
            "Disallow: /q\nUser-agent: GPTBot\nDisallow: /a\n"
            "Disallow: /b\n")
        result = self.preview(root, home, orphan, with_orphan,
                              evaluated_page_path="/zzz")
        outside = result.get("evaluation_differences_outside_diff")
        self.assertIsNotNone(outside)
        self.assertIn("unparsed_lines_warning", outside)


if __name__ == "__main__":
    unittest.main()
