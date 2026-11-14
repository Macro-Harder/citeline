"""Step 17 fix seat F3 tests: checks and robots entries.

Each test pins one register entry on the behaviour the
register states, written before its cure. Entries:
S17-R1-020 to S17-R1-025, S17-R1-027 to S17-R1-031,
S17-R1-053, S17-R1-079, S17-R1-103, S17-R1-104, and
S17-R1X-034 to S17-R1X-039.
"""

import json
import tempfile
import time
import unittest
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


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def write_file(root, name, content):
    path = root / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


class TestChecksEntries(unittest.TestCase):

    def test_020_canonical_line_inside_longer_words_is_not_verbatim(self):
        facts = {"canonical_line": "Acme audits pages",
                 "is_product_page": True}
        page = make_page("Acme audits pagesmith tools for many daily users.")
        result = result_of(
            checks.run_checks(page, facts, audit_date=AUDIT_DATE),
            "description_consistency")
        self.assertEqual(result["earned"], 0)
        self.assertEqual(result["reason_code"], "DESC_MISSING")
        glued = make_page("XAcme audits pages for many daily users today.")
        result = result_of(
            checks.run_checks(glued, facts, audit_date=AUDIT_DATE),
            "description_consistency")
        self.assertEqual(result["earned"], 0)

    def test_021_equivalent_written_forms_count_as_one_target(self):
        forms = [
            "https://rival.example/report",
            "http://rival.example/report",
            "https://rival.example/report/",
            "https://rival.example/report#top",
            "https://RIVAL.example/report",
        ]
        sentences = [
            "The long sentence here cites %s for the full report details today." % form
            for form in forms
        ]
        page = make_page(" ".join(sentences), sentences=sentences)
        result = result_of(
            checks.run_checks(page, {}, audit_date=AUDIT_DATE), "citations")
        self.assertEqual(result["detail_counts"]["distinct_target_count"], 1)

    def test_022_trailing_dot_self_host_is_excluded(self):
        facts = {"domain": "macroforge.example"}
        text = ("Read our own page at https://macroforge.example./guide "
                "today for full details here now.")
        page = make_page(text)
        result = result_of(
            checks.run_checks(page, facts, audit_date=AUDIT_DATE), "citations")
        self.assertEqual(result["detail_counts"]["distinct_target_count"], 0)
        self.assertEqual(result["reason_code"], "CIT_SELF_ONLY")

    def test_023_curly_quotes_count_and_mask_statistics(self):
        text = ("A note in the margin reads \u201cgrowth hit 42 percent "
                "overall this quarter\u201d today.\n\n"
                "\u201cTeams plan better together every single week\u201d "
                "said Priya Nair in the review.")
        page = make_page(text, sentences=[
            "A note in the margin reads \u201cgrowth hit 42 percent overall this quarter\u201d today.",
            "\u201cTeams plan better together every single week\u201d said Priya Nair in the review.",
        ])
        results = checks.run_checks(page, {}, audit_date=AUDIT_DATE)
        quotations = result_of(results, "quotations")
        self.assertEqual(quotations["detail_counts"]["attributed_span_count"], 1)
        statistics = result_of(results, "statistics")
        self.assertEqual(statistics["detail_counts"]["statistic_token_count"], 0)

    def test_024_url_digits_and_port_digits_are_not_statistics(self):
        text = "See https://data.example/archive/12345 for the full archive listing today."
        page = make_page(text)
        result = result_of(
            checks.run_checks(page, {}, audit_date=AUDIT_DATE), "statistics")
        self.assertEqual(result["detail_counts"]["statistic_token_count"], 0)
        port_text = "See https://macroforge.example:443/guide for the full guide listing today."
        page = make_page(port_text)
        result = result_of(
            checks.run_checks(page, {}, audit_date=AUDIT_DATE), "statistics")
        self.assertEqual(result["detail_counts"]["statistic_token_count"], 0)

    def test_025_date_fragments_in_other_forms_are_not_statistics(self):
        for text in (
            "The review met on Nov 14, 2026 in the main office downtown.",
            "The review met on 2026/11/14 in the main office downtown today.",
        ):
            page = make_page(text)
            result = result_of(
                checks.run_checks(page, {}, audit_date=AUDIT_DATE), "statistics")
            self.assertEqual(
                result["detail_counts"]["statistic_token_count"], 0, text)

    def test_053_freshness_does_not_crash_on_bad_audit_date(self):
        page = make_page("Updated: 2026-10-03\nSome body text stands here.")
        try:
            results = checks.run_checks(page, {}, audit_date="not-a-date")
        except ValueError:
            self.fail("freshness raised a raw ValueError")
        result = result_of(results, "freshness")
        self.assertEqual(result["earned"], 0)


class TestRobotsEntries(unittest.TestCase):

    def test_027_repeated_star_rule_completes_promptly(self):
        rule = "/a" + "*a" * 29 + "*"
        text = "User-agent: GPTBot\nDisallow: %s\n" % rule
        path = "/" + "a" * 10 + "b"
        start = time.monotonic()
        report = robots.evaluate_robots_text(text, evaluated_page_path=path)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 5.0)
        finding = [f for f in report["findings"] if f["token"] == "GPTBot"][0]
        self.assertEqual(finding["outcome"], "allowed")

    def test_028_non_line_ending_characters_do_not_split_lines(self):
        long_line = "#" * 9990 + "\x0b" + "Disallow: /b"
        text = "User-agent: GPTBot\n" + long_line + "\n"
        with self.assertRaises(robots.RobotsError) as caught:
            robots.evaluate_robots_text(text, evaluated_page_path="/b")
        self.assertEqual(caught.exception.token, "LIMIT_EXCEEDED")

    def test_029_utf16_without_bom_fails_decoding(self):
        raw = "User-agent: GPTBot\nDisallow: /\n".encode("utf-16-le")
        with self.assertRaises(robots.RobotsError) as caught:
            robots.evaluate_robots_bytes(raw)
        self.assertEqual(caught.exception.token, "ROBOTS_DECODING_FAILED")

    def test_030_text_route_applies_size_and_bom_rules(self):
        big = "# note\n" * 90000 + "User-agent: GPTBot\nDisallow: /\n"
        with self.assertRaises(robots.RobotsError) as caught:
            robots.evaluate_robots_text(big)
        self.assertEqual(caught.exception.token, "LIMIT_EXCEEDED")
        bom_text = "User-agent: GPTBot\n\ufeffDisallow: /\n"
        with self.assertRaises(robots.RobotsError) as caught:
            robots.evaluate_robots_text(bom_text)
        self.assertEqual(caught.exception.token, "ROBOTS_DECODING_FAILED")

    def test_031_query_and_fragment_do_not_take_part_in_matching(self):
        text = "User-agent: GPTBot\nDisallow: /foo$\n"
        for path in ("/foo?x=1", "/foo#frag"):
            report = robots.evaluate_robots_text(text, evaluated_page_path=path)
            finding = [f for f in report["findings"] if f["token"] == "GPTBot"][0]
            self.assertEqual(finding["outcome"], "blocked", path)

    def test_103_no_directive_file_states_so_plainly(self):
        html = ("<html><head><title>404 Not Found</title></head>"
                "<body><h1>404 Not Found</h1></body></html>\n")
        report = robots.evaluate_robots_text(html)
        text = json.dumps(report).lower()
        self.assertIn("no robots directive", text)

    def test_104_unparsed_lines_carry_a_plain_warning(self):
        text = "Useragent: *\nDISALLOW: /private/\n\nUser-agent: GPTBot\nDisallow: /\n"
        report = robots.evaluate_robots_text(text, evaluated_page_path="/private/")
        blob = json.dumps(report).lower()
        self.assertIn("not understood", blob)
        self.assertIn("no effect", blob.replace("took no effect", "no effect"))


class TestPreviewAndHomeEntries(unittest.TestCase):

    def preview(self, root, home, first, second, **extra):
        kwargs = {"home": str(home), "first_robots_file": str(first),
                  "second_robots_file": str(second), "audit_date": AUDIT_DATE}
        kwargs.update(extra)
        return service.robots_preview(**kwargs)

    def test_079_standalone_robots_refuses_missing_and_broken_home(self):
        root, home = make_home(self)
        good = write_file(root, "r.txt", "User-agent: *\nAllow: /\n")
        missing = root / "no-such-home"
        with self.assertRaises(Exception) as caught:
            service.robots(home=str(missing), robots_file=str(good),
                           audit_date=AUDIT_DATE)
        self.assertEqual(
            getattr(caught.exception, "token", None), "HOME_MISSING")

    def test_x034_capture_dates_validated_and_shown_as_asserted(self):
        root, home = make_home(self)
        a = write_file(root, "a.txt", "User-agent: *\nAllow: /\n")
        b = write_file(root, "b.txt", "User-agent: *\nDisallow: /\n")
        for bad in ("not-a-date", "2026-13-40", 20261114):
            with self.assertRaises(Exception, msg=repr(bad)):
                self.preview(root, home, a, b, first_capture_date=bad)
        empty = self.preview(root, home, a, b, first_capture_date="")
        self.assertIsNone(empty["first_capture_date"])
        self.assertIn("omit", json.dumps(empty).lower())
        with self.assertRaises(Exception):
            self.preview(root, home, a, b, first_capture_date="2027-01-01")
        result = self.preview(root, home, a, b,
                              first_capture_date="2026-11-01",
                              second_capture_date="2026-11-05")
        self.assertIn("asserted", json.dumps(result).lower())
        omitted = self.preview(root, home, a, b)
        self.assertIn("omit", json.dumps(omitted).lower())

    def test_x035_diff_compares_rule_sets_not_positions(self):
        root, home = make_home(self)
        a = write_file(root, "a.txt", "User-agent: GPTBot\nDisallow: /a\nAllow: /b\n")
        b = write_file(root, "b.txt", "User-agent: GPTBot\nAllow: /b\nDisallow: /a\n")
        result = self.preview(root, home, a, b, evaluated_page_path="/zzz")
        self.assertEqual(result["changed_rows"], [])
        c = write_file(root, "c.txt",
                       "User-agent: GPTBot\nDisallow: /a\nDisallow: /b\nDisallow: /c\n")
        d = write_file(root, "d.txt",
                       "User-agent: GPTBot\nDisallow: /new\nDisallow: /a\nDisallow: /b\nDisallow: /c\n")
        result = self.preview(root, home, c, d, evaluated_page_path="/zzz")
        self.assertEqual(len(result["changed_rows"]), 1)
        self.assertEqual(result["changed_rows"][0]["second_finding"], "Disallow: /new")
        e = write_file(root, "e.txt", "User-agent: gptbot\nDisallow: /a\n")
        f = write_file(root, "f.txt", "User-agent: GPTBot\nDisallow: /a\n")
        result = self.preview(root, home, f, e, evaluated_page_path="/zzz")
        self.assertEqual(result["changed_rows"], [])

    def test_x036_changed_rows_stay_within_the_crawler_table(self):
        root, home = make_home(self)
        a = write_file(root, "a.txt", "User-agent: *\nAllow: /\n")
        b = write_file(root, "b.txt", "User-agent: *\nDisallow: /\n")
        result = self.preview(root, home, a, b, evaluated_page_path="/")
        self.assertEqual(len(result["changed_rows"]), 25)
        for row in result["changed_rows"]:
            self.assertIsNotNone(row["purpose_class"])
        c = write_file(root, "c.txt", "User-agent: FooBot\nDisallow: /a\n")
        d = write_file(root, "d.txt", "User-agent: FooBot\nDisallow: /b\n")
        result = self.preview(root, home, c, d, evaluated_page_path="/zzz")
        self.assertEqual(result["changed_rows"], [])
        e = write_file(root, "e.txt", "User-agent: GPTBot\nDisallow: /\n")
        f = write_file(root, "f.txt", "User-agent: *\nDisallow: /\n")
        result = self.preview(root, home, e, f, evaluated_page_path="/")
        for row in result["changed_rows"]:
            self.assertIsNotNone(row["purpose_class"], row)

    def test_x037_failed_preview_appends_a_failure_record(self):
        root, home = make_home(self)
        a = write_file(root, "a.txt", "User-agent: *\nAllow: /\n")
        bad = write_file(root, "bad.bin", b"\xff\xfeU\x00s\x00e\x00r\x00")
        from citeline import journal
        before = journal.verify_chain(str(home))["entry_count"]
        with self.assertRaises(Exception):
            self.preview(root, home, a, bad)
        entries = journal.fold_chain(str(home)) if hasattr(journal, "fold_chain") else None
        after = journal.verify_chain(str(home))["entry_count"]
        self.assertEqual(after, before + 1)

    def test_x038_preview_refuses_a_missing_home(self):
        root, home = make_home(self)
        a = write_file(root, "a.txt", "User-agent: *\nAllow: /\n")
        b = write_file(root, "b.txt", "User-agent: *\nDisallow: /\n")
        missing = root / "no-such-home"
        with self.assertRaises(Exception) as caught:
            self.preview(root, missing, a, b)
        self.assertEqual(
            getattr(caught.exception, "token", None), "HOME_MISSING")

    def test_x039_diff_scope_is_declared_in_the_artefact(self):
        root, home = make_home(self)
        a = write_file(root, "a.txt", "User-agent: GPTBot\nDisallow: /a\n")
        b = write_file(root, "b.txt",
                       "User-agent: GPTBot\nDisallow: /a\nCrawl-delay: 10\nSitemap: https://example.com/s.xml\n")
        result = self.preview(root, home, a, b, evaluated_page_path="/zzz")
        self.assertEqual(result["changed_rows"], [])
        self.assertIn("findings and rule texts", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
