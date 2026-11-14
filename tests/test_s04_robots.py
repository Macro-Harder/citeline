"""Slice S4 tests: robots evaluation, Step 13, Citeline.

Written before the product exists. Every test imports the product
package named citeline and calls the operation signatures the plan
states (plan Section 1.3 slice S4; module robots in the plan
Section 5.3 boundary table; the service layer operations robots and
robots_preview on the brief Section 5.4 surface list). Import or
attribute failure is the expected red state (R-20). No stub and no
mock of the product stands in this file.

Dates are call inputs in every test, never clock reads (plan
Section 1.5 date handling). The timing bound for this slice stands
stated in the plan at Section 1.5: robots evaluation over one
supplied robots file, 5 seconds. No scale statement is owed for
this slice.

The shipped crawler table stands at 25 rows, 25 directly verified,
version value 1, snapshot date 2026-11-12, with the purpose prose
caveat for rows 12 to 14 kept in every restatement in this file:
rows 12 to 14 stand directly verified on token, operator, source,
and page date, and their purpose prose keeps its secondary label,
resting on the vendor text as transcribed.

No test in this file stands claimed for a robots group naming an
agent with no row in the shipped table: such a group stands
outside the report scope, with no finding row and no blocked row,
on the rule stated at plan Section 1.3 slice S4. The version
suffix token outcome stands stated as the plan's one stated
exception to that rule. The named Step 13 size case stands
outside that rule and is no exception to it, on its table row
ground: its subject crawler holds a table row. Any
likeness judgement in robots host handling carries no test in
this slice (plan Part B entry B3). No test in this file expects a
stored preview or a preview fold: that limb stands blocked at
plan Part B entry B8 and stands in blocked-w4.md. No test in this
file refreshes the crawler table: the O5-9 re verification due
2027-02-10 is a dated obligation, not a test.
"""

import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from citeline import service

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
PAGE = FIXTURES / "w7-page.md"

TABLE_TOKENS = [
    "GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot",
    "Claude-SearchBot", "Claude-User", "Googlebot", "Google-Extended",
    "Bingbot", "PerplexityBot", "Perplexity-User", "meta-externalagent",
    "meta-webindexer", "meta-externalfetcher", "Applebot",
    "Applebot-Extended", "Amazonbot", "Amzn-SearchBot", "Amzn-User",
    "MistralAI-Training", "MistralAI-Index", "MistralAI-User",
    "DuckAssistBot", "YouBot", "CCBot",
]

# Coined field names, stated in this module on the convention the
# writer used for the other unstated field names in this set, for
# the two stated list fields the passages name in prose only: the
# anchor limit field is anchor_limit, the name writer 5's S9 module
# already uses on the audit artefact, and the robots snapshot
# asserted capture date field is robots_snapshot_asserted_capture_date.
ANCHOR_LIMIT_FIELD = "anchor_limit"
ASSERTED_CAPTURE_DATE_FIELD = "robots_snapshot_asserted_capture_date"

ROBOTS_REPORT_FIELDS = {
    "findings", "evaluated_page_path", "path_defaulted",
    "honesty_sentence", ANCHOR_LIMIT_FIELD, "next_refresh_due_date",
    "robots_snapshot_sha256", ASSERTED_CAPTURE_DATE_FIELD,
    "table_version", "table_snapshot_date",
    "robots_ruleset_version", "crawl_delay_observation",
    "sitemap_line_presence_count", "non_protocol_line_count",
    "unknown_token_count", "finding_count",
}


def report_field_names(record):
    """Field names of a report, keys for a dict form and
    attributes for an object form."""
    if isinstance(record, dict):
        return set(record.keys())
    if hasattr(record, "__dict__"):
        return {name for name in vars(record)
                if not name.startswith("_")}
    return {name for name in dir(record)
            if not name.startswith("_")
            and not callable(getattr(record, name))}


def walk_nodes(node):
    """Every node of a report value, the value itself first."""
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from walk_nodes(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from walk_nodes(value)


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def note_of(finding):
    for name in ("control_note", "applicability_note",
                 "mixed_purpose_note", "note"):
        if isinstance(finding, dict) and finding.get(name):
            return finding[name]
        if hasattr(finding, name) and getattr(finding, name):
            return getattr(finding, name)
    return None


def make_home(case):
    from citeline import install as install_module
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return home


def evaluate(case, fixture, path=None, home=None):
    home = home or make_home(case)
    kwargs = {"home": str(home), "robots_file": str(fixture),
              "audit_date": AUDIT_DATE}
    if path is not None:
        kwargs["evaluated_page_path"] = path
    return service.robots(**kwargs)


def finding_for(report, token):
    for finding in field(report, "findings"):
        if field(finding, "token") == token:
            return finding
    raise AssertionError("no finding for token %r" % token)


def outcome_of(finding):
    return field(finding, "outcome")


def is_blocked(finding):
    outcome = outcome_of(finding)
    return outcome == "blocked" or (
        isinstance(outcome, dict) and outcome.get("value") == "blocked")


def is_allowed(finding):
    outcome = outcome_of(finding)
    if outcome == "allowed":
        return True
    return isinstance(outcome, str) and outcome.startswith("allowed")


class TestCrawlerTableAndFindings(unittest.TestCase):
    """Row plan Section 1.3 S4, findings over the shipped crawler
    table. Oracle: brief Sections 5.6 and 5.10 and plan Section 5.1
    RobotsReport entry."""

    def test_one_finding_per_table_row_and_count_is_table_size(self):
        """Pins S4 findings construction. Oracle: brief Section 5.6
        construction rule and Section 5.10 items 93 and 127: exactly
        one finding per table row, finding count is the table size
        by construction, 25 at version value 1."""
        report = evaluate(self, FIXTURES / "w4-robots-basic.txt", "/")
        findings = field(report, "findings")
        self.assertEqual(len(findings), 25)
        self.assertEqual(field(report, "finding_count"), 25)
        self.assertEqual({field(f, "token") for f in findings},
                         set(TABLE_TOKENS))

    def test_table_version_and_snapshot_date_and_refresh_due(self):
        """Pins S4 table stamps. Oracle: brief Section 5.6 (version
        value 1, snapshot date 2026-11-12, 25 rows, 25 directly
        verified, purpose prose caveat for rows 12 to 14 kept) and
        item 82 next refresh due date 2027-02-10 in the window
        between ship and the first post ship refresh."""
        report = evaluate(self, FIXTURES / "w4-robots-basic.txt", "/")
        self.assertEqual(field(report, "table_version"), 1)
        self.assertEqual(str(field(report, "table_snapshot_date")),
                         "2026-11-12")
        self.assertEqual(str(field(report, "next_refresh_due_date")),
                         "2027-02-10")
        self.assertTrue(field(report, "robots_ruleset_version"))

    def test_finding_carries_row_fields_in_operator_spelling(self):
        """Pins S4 per finding field list. Oracle: brief Section
        5.10 items 93 and 127 per finding fields: token in operator
        spelling, operator, purpose class, per row evidence label,
        mixed purpose note or null, outcome, winning rule or null,
        supplying group or null."""
        report = evaluate(self, FIXTURES / "w4-robots-basic.txt", "/")
        finding = finding_for(report, "GPTBot")
        self.assertEqual(field(finding, "operator"), "OpenAI")
        self.assertEqual(field(finding, "purpose_class"), "training")
        self.assertIn(field(finding, "evidence_label"),
                      ("directly verified", "secondary transcription"))

    def test_meta_rows_operator_spelling_and_mixed_purpose_note(self):
        """Pins S4 rows 12 to 14 restatement. Oracle: brief Section
        5.10 items 5 and 17: the Meta count is 3, report output
        prints operator spelling, row 12 keeps its table purpose
        class and carries a mandatory mixed purpose note, and the
        purpose prose for rows 12 to 14 keeps its secondary label,
        resting on the vendor text as transcribed, while the rows
        stand directly verified on token, operator, source, and
        page date."""
        report = evaluate(self, FIXTURES / "w4-robots-basic.txt", "/")
        meta = [f for f in field(report, "findings")
                if field(f, "operator") == "Meta"]
        self.assertEqual(len(meta), 3)
        row12 = finding_for(report, "meta-externalagent")
        self.assertEqual(field(row12, "purpose_class"), "training")
        self.assertIsNotNone(field(row12, "mixed_purpose_note"))

    def test_search_and_training_blocked_outcome_form(self):
        """Pins S4 outcome forms for search and training rows.
        Oracle: brief Section 5.10 items 93 and 127: a fetch
        outcome of blocked or allowed for search and training
        rows."""
        report = evaluate(self, FIXTURES / "w4-robots-basic.txt",
                          "/private/page")
        self.assertTrue(is_blocked(finding_for(report, "GPTBot")))
        self.assertTrue(is_blocked(finding_for(report, "Googlebot")))

    def test_control_row_outcome_is_null_with_control_note(self):
        """Pins S4 control row outcome. Oracle: brief Section 5.10
        item 88 and items 93 and 127: a control row finding carries
        a null outcome plus a control note, and is never worded as
        blocked or allowed for a path in the fetch sense."""
        report = evaluate(self, FIXTURES / "w4-robots-basic.txt", "/")
        finding = finding_for(report, "Google-Extended")
        self.assertIsNone(outcome_of(finding))
        self.assertIsNotNone(note_of(finding))

    def test_user_fetch_outcome_is_computed_with_applicability_note(self):
        """Pins S4 user fetch outcome. Oracle: brief Section 5.10
        item 89: a user fetch blocked value is a computed outcome
        plus an applicability note, never a bare boolean."""
        report = evaluate(self, FIXTURES / "w4-robots-basic.txt",
                          "/private/page")
        finding = finding_for(report, "ChatGPT-User")
        self.assertTrue(is_blocked(finding))
        self.assertIsNotNone(note_of(finding))

    def test_applebot_no_fallback_where_no_group_applies(self):
        """Pins S4 Applebot fallback limb. Oracle: brief Section
        5.10 item 5: no fallback is adopted; where no group names
        Applebot and no wildcard group applies, the Applebot
        finding is allowed because no group applied, and no
        finding is derived from Googlebot rules."""
        report = evaluate(self, FIXTURES / "w4-robots-suffix.txt", "/")
        finding = finding_for(report, "Applebot")
        self.assertTrue(is_allowed(finding))
        self.assertIsNone(field(finding, "winning_rule"))

    def test_defect_flag_only_for_search_purpose_rows(self):
        """Pins S4 defect eligibility. Oracle: brief Section 5.10
        item 87 and grill DQ-3: a block counts as a defect finding
        only where it blocks a search purpose row; control and
        other purpose rows are reported and not defected."""
        report = evaluate(self, FIXTURES / "w4-robots-basic.txt",
                          "/private/page")
        for finding in field(report, "findings"):
            defect = None
            if isinstance(finding, dict):
                defect = finding.get("defect")
            elif hasattr(finding, "defect"):
                defect = finding.defect
            if defect:
                self.assertEqual(field(finding, "purpose_class"),
                                 "search")


class TestPrecedenceAndPaths(unittest.TestCase):
    """Row plan Section 1.3 S4, precedence and path handling.
    Oracle: brief Section 5.10 item 3 (RFC 9309 measure) and item
    92 (path handling specification in full)."""

    def test_most_specific_match_wins(self):
        """Pins S4 precedence, specificity limb. Oracle: brief
        Section 5.10 item 3: the most specific match is the match
        with the most octets, counted in bytes of the path as
        written."""
        report = evaluate(self, FIXTURES / "w4-robots-basic.txt",
                          "/private/public/page")
        finding = finding_for(report, "Googlebot")
        self.assertTrue(is_allowed(finding))
        self.assertEqual(field(finding, "winning_rule"),
                         "Allow: /private/public/")

    def test_allow_wins_on_equivalent_rules(self):
        """Pins S4 precedence, tie limb. Oracle: brief Section
        5.10 item 3: where an allow rule and a disallow rule are
        equivalent, the allow rule is used."""
        report = evaluate(self, FIXTURES / "w4-robots-precedence.txt",
                          "/docs/page")
        finding = finding_for(report, "Bingbot")
        self.assertTrue(is_allowed(finding))
        self.assertTrue(str(field(finding, "winning_rule"))
                        .startswith("Allow"))

    def test_wildcard_rule_octets_counted_as_written(self):
        """Pins S4 precedence over a wildcard rule. Oracle: brief
        Section 5.10 item 3, most octets counted in bytes of the
        path as written: the allow rule for /a/b/ stands longer as
        written than the disallow rule for /a*/ and wins for a
        path under /a/b/."""
        report = evaluate(self, FIXTURES / "w4-robots-precedence.txt",
                          "/a/b/c")
        self.assertTrue(is_allowed(finding_for(report, "ClaudeBot")))
        report2 = evaluate(self, FIXTURES / "w4-robots-precedence.txt",
                           "/a/zzz")
        self.assertTrue(is_blocked(finding_for(report2, "ClaudeBot")))

    def test_group_for_token_beats_wildcard_group(self):
        """Pins S4 group selection. Oracle: brief Section 10.7
        primitive P18: groups listing the crawler token beat the
        star group."""
        report = evaluate(self, FIXTURES / "w4-robots-basic.txt",
                          "/tmp/page")
        self.assertTrue(is_allowed(finding_for(report, "GPTBot")))
        report2 = evaluate(self, FIXTURES / "w4-robots-basic.txt",
                           "/private/page")
        self.assertTrue(is_blocked(finding_for(report2, "GPTBot")))

    def test_percent_encoding_compared_as_written_no_decoding(self):
        """Pins S4 path handling, percent encoding limb. Oracle:
        brief Section 5.10 item 92: percent encoding compared as
        written and no decoding before comparison."""
        report = evaluate(self, FIXTURES / "w4-robots-precedence.txt",
                          "/caf%C3%A9/x")
        self.assertTrue(is_blocked(
            finding_for(report, "PerplexityBot")))
        report2 = evaluate(self, FIXTURES / "w4-robots-precedence.txt",
                           "/café/x")
        self.assertTrue(is_allowed(
            finding_for(report2, "PerplexityBot")))

    def test_trailing_slash_significant_and_root_rule_only(self):
        """Pins S4 path handling, trailing slash and root limbs.
        Oracle: brief Section 5.10 item 92: a trailing slash is
        significant, and the root path matches a root rule only."""
        report = evaluate(self, FIXTURES / "w4-robots-precedence.txt",
                          "/docs")
        self.assertTrue(is_allowed(finding_for(report, "YouBot")))
        report2 = evaluate(self, FIXTURES / "w4-robots-precedence.txt",
                           "/docs/")
        self.assertTrue(is_blocked(finding_for(report2, "YouBot")))
        report3 = evaluate(self, FIXTURES / "w4-robots-basic.txt", "/")
        self.assertTrue(is_allowed(finding_for(report3, "GPTBot")))

    def test_path_defaulted_true_where_no_path_supplied(self):
        """Pins S4 path_defaulted flag, defaulted limb. Oracle:
        brief Section 5.10 IM7-BRK-10 landing: path_defaulted
        stands true where the call supplied no evaluated page
        path and the root default operated."""
        report = evaluate(self, FIXTURES / "w4-robots-basic.txt")
        self.assertEqual(field(report, "evaluated_page_path"), "/")
        self.assertIs(field(report, "path_defaulted"), True)

    def test_path_defaulted_false_where_path_supplied(self):
        """Pins S4 path_defaulted flag, supplied limb. Oracle:
        brief Section 5.10 IM7-BRK-10 landing: the flag stands
        false where the call supplied the path."""
        report = evaluate(self, FIXTURES / "w4-robots-basic.txt", "/x")
        self.assertIs(field(report, "path_defaulted"), False)

    def test_duplicate_groups_combined_and_orphan_rules_ignored(self):
        """Pins S4 parser limbs. Oracle: brief Section 5.10 robots
        parser failure rules: duplicate groups for one token are
        combined into one rule set, and rules before the first
        user agent line are a malformed group whose rules are not
        evaluated."""
        for path in ("/one/", "/two/"):
            report = evaluate(self, FIXTURES / "w4-robots-malformed.txt",
                              path)
            self.assertTrue(is_blocked(finding_for(report, "GPTBot")))
        report = evaluate(self, FIXTURES / "w4-robots-malformed.txt",
                          "/orphan/")
        self.assertTrue(is_allowed(finding_for(report, "GPTBot")))

    def test_empty_allow_and_disallow_count_as_no_rule(self):
        """Pins S4 parser limb. Oracle: brief Section 5.10 robots
        parser failure rules: an empty Allow value and an empty
        Disallow value each count as no rule."""
        report = evaluate(self, FIXTURES / "w4-robots-malformed.txt",
                          "/anything")
        self.assertTrue(is_allowed(finding_for(report, "GPTBot")))

    def test_non_protocol_counts_and_crawl_delay_observation(self):
        """Pins S4 report counts. Oracle: brief Section 5.10 items
        93 and 127 report fields and the parser partition: sitemap
        line presence as a count, the non protocol line count over
        lines that are not a rule, not a group, not a recognised
        non protocol line, and not an empty or comment line, and
        the crawl delay observation present with its value."""
        report = evaluate(self, FIXTURES / "w4-robots-basic.txt", "/")
        self.assertEqual(field(report, "sitemap_line_presence_count"), 1)
        self.assertEqual(field(report, "non_protocol_line_count"), 1)
        self.assertEqual(field(report, "crawl_delay_observation"), 10)

    def test_empty_file_all_allowed_because_no_group_applied(self):
        """Pins S4 empty file limb. Oracle: brief Section 5.10
        items 93 and 127 outcome forms: allowed because no group
        applied, with finding count still the table size."""
        report = evaluate(self, FIXTURES / "w4-robots-empty.txt", "/x")
        self.assertEqual(field(report, "finding_count"), 25)
        self.assertEqual(field(report, "unknown_token_count"), 0)
        for finding in field(report, "findings"):
            if field(finding, "purpose_class") in ("search", "training"):
                self.assertTrue(is_allowed(finding))


class TestVersionSuffixToken(unittest.TestCase):
    """Row plan Section 1.3 S4, the version suffix token outcome.
    Oracle: plan Section 1.3 slice S4 families and the slice
    definition at plan Section 4 S4."""

    def test_suffix_token_selects_no_row_and_generates_no_finding(self):
        """Pins S4 version suffix outcome. Oracle: plan slice S4:
        a user agent token carrying a version suffix (the table
        token, a slash, and a number) is not a table token, selects
        no table row, and generates no finding; the GPTBot finding
        over a file whose only GPTBot group carries the suffix is
        allowed because no group applied."""
        report = evaluate(self, FIXTURES / "w4-robots-suffix.txt", "/")
        tokens = {field(f, "token") for f in field(report, "findings")}
        self.assertNotIn("GPTBot/2.0", tokens)
        self.assertEqual(field(report, "finding_count"), 25)
        finding = finding_for(report, "GPTBot")
        self.assertTrue(is_allowed(finding))
        self.assertIsNone(field(finding, "winning_rule"))
        self.assertIsNone(field(finding, "supplying_group"))

    def test_suffix_token_counts_only_in_unknown_token_disclosure(self):
        """Pins S4 version suffix counting limb. Oracle: plan
        slice S4 and brief Section 5.10 items 93 and 127: the
        suffix token counts only in the unknown token count
        disclosure, a disclosure only and never a finding, with
        the unlisted token named in the spelling the supplied
        file used, marked not in table, and carrying no verdict."""
        report = evaluate(self, FIXTURES / "w4-robots-suffix.txt", "/")
        self.assertEqual(field(report, "unknown_token_count"), 1)
        self.assertIn("GPTBot/2.0", json.dumps(
            report, default=str, ensure_ascii=False))
        marked = []
        for node in walk_nodes(report):
            if not isinstance(node, (dict, list, str)):
                continue
            text = json.dumps(node, default=str, ensure_ascii=False)
            if "GPTBot/2.0" not in text:
                continue
            if "not in table" in text or "not_in_table" in text:
                marked.append(node)
        self.assertTrue(
            marked,
            "no disclosure detail names GPTBot/2.0 marked not in table")
        detail = min(marked, key=lambda node: len(json.dumps(
            node, default=str, ensure_ascii=False)))
        for node in walk_nodes(detail):
            if isinstance(node, dict):
                self.assertNotIn("outcome", node)
                self.assertNotIn("verdict", node)


class TestNamedSizeCase(unittest.TestCase):
    """Row plan Section 1.3 S4, the named Step 13 size case.
    Oracle: plan slice S4 finding claim and brief Section 6.3
    item 118 decision, with brief Section 5.11 limit 34."""

    def test_size_case_fixture_shape(self):
        """Pins the size case fixture itself. Oracle: catalogue
        entry for w4-robots-size-case.txt: the Googlebot group
        carrying the band rule starts at byte 513041, past the
        500 KiB published stop at byte 512000, and the whole file
        stands at 513080 bytes, under the admitted size of
        512 KiB (524288 bytes) at limit 34."""
        data = (FIXTURES / "w4-robots-size-case.txt").read_bytes()
        self.assertEqual(len(data), 513080)
        self.assertEqual(data.index(b"Disallow: /band/"), 513041 + 22)
        self.assertGreater(513041, 500 * 1024)
        self.assertLess(len(data), 512 * 1024)

    def test_rule_in_band_evaluated_by_plan_ruleset(self):
        """Pins the named Step 13 size case. Oracle: plan slice
        S4: a finding for a rule standing past a named crawler
        published reading stop claims only the plan own ruleset
        evaluation of the whole admitted file, and claims nothing
        about that crawler own reading. The subject crawler is
        Googlebot, whose published stop stands at 500 KiB (brief
        Section 6.3 item 118 and the robots semantics evidence:
        Google enforces a file size limit of 500 KiB and ignores
        content after that point), and Googlebot holds table
        row 7. The band rule stands at byte 513041 of a file of
        513080 bytes admitted under limit 34, so the plan ruleset
        evaluation blocks the evaluated path under that rule."""
        report = evaluate(self, FIXTURES / "w4-robots-size-case.txt",
                          "/band/page")
        finding = finding_for(report, "Googlebot")
        self.assertTrue(is_blocked(finding))
        self.assertEqual(field(finding, "winning_rule"),
                         "Disallow: /band/")
        self.assertEqual(field(report, "finding_count"), 25)


class TestStandaloneAndAuditRoutes(unittest.TestCase):
    """Row plan Section 1.3 S4, standalone robots in full, the
    audit side report as robots_summary, and the CQ-D12 fixture.
    Oracle: plan Section 5.2 standalone RobotsReport row."""

    def test_standalone_report_carries_the_fixed_field_list(self):
        """Pins S4 standalone field list. Oracle: brief Section
        5.10 items 93 and 127, no other field ships in a robots
        report, read with plan Section 5.1 RobotsReport entry."""
        report = evaluate(self, FIXTURES / "w4-robots-basic.txt",
                          "/private/page")
        self.assertEqual(report_field_names(report),
                         ROBOTS_REPORT_FIELDS)
        self.assertEqual(
            field(report, "robots_snapshot_sha256"),
            hashlib.sha256((FIXTURES / "w4-robots-basic.txt")
                           .read_bytes()).hexdigest())
        self.assertTrue(field(report, "honesty_sentence"))

    def test_audit_route_and_standalone_route_same_fixed_field_list(self):
        """Pins the CQ-D12 fixture. Oracle: plan Section 5.2: the
        standalone report is an invocation local value produced by
        the same evaluation, not a fold and not a retrieval of the
        audit copy, and the fixture proves both routes produce the
        same fixed field list. The audit here supplies the same
        robots file and the same evaluated page path."""
        home = make_home(self)
        standalone = evaluate(self, FIXTURES / "w4-robots-basic.txt",
                              "/private/page", home=home)
        audit = service.audit(
            home=str(home), page_file=str(PAGE),
            robots_file=str(FIXTURES / "w4-robots-basic.txt"),
            evaluated_page_path="/private/page", audit_date=AUDIT_DATE)
        summary = field(audit, "robots_summary")
        self.assertIsNotNone(summary)
        self.assertEqual(report_field_names(standalone),
                         ROBOTS_REPORT_FIELDS)
        self.assertEqual(report_field_names(summary),
                         ROBOTS_REPORT_FIELDS)
        self.assertEqual(report_field_names(summary),
                         report_field_names(standalone))
        self.assertEqual(field(summary, "finding_count"),
                         field(standalone, "finding_count"))
        self.assertEqual(
            [field(f, "token") for f in field(summary, "findings")],
            [field(f, "token") for f in field(standalone, "findings")])
        self.assertEqual(
            [str(outcome_of(f)) for f in field(summary, "findings")],
            [str(outcome_of(f)) for f in field(standalone, "findings")])

    def test_supplied_robots_file_rejected_fails_whole_audit(self):
        """Pins S4 audit side rejection. Oracle: plan contract C8
        and brief Section 5.2 AuditRun entry: a supplied robots
        file rejected on a limit breach or under boundary B1 fails
        the whole audit with a recorded error and no audit record;
        no audit ships a null robots summary for a supplied
        file."""
        home = make_home(self)
        with self.assertRaises(Exception) as caught:
            service.audit(
                home=str(home), page_file=str(PAGE),
                robots_file=str(FIXTURES / "w4-robots-bad-encoding.bin"),
                audit_date=AUDIT_DATE)
        self.assertIn("ROBOTS_DECODING_FAILED", str(caught.exception))


class TestPreviewEvaluations(unittest.TestCase):
    """Row plan Section 1.3 S4, the two evaluations a preview
    needs. Oracle: plan Section 5.1 RobotsPreview entry and brief
    Section 10.7 primitive P73, severed unstored form. No test in
    this class expects a stored preview or a preview fold."""

    def preview(self, case, first, second, path=None, home=None,
                first_date=None, second_date=None):
        home = home or make_home(case)
        kwargs = {"home": str(home), "first_robots_file": str(first),
                  "second_robots_file": str(second),
                  "audit_date": AUDIT_DATE}
        if path is not None:
            kwargs["evaluated_page_path"] = path
        if first_date is not None:
            kwargs["first_captured_on"] = first_date
        if second_date is not None:
            kwargs["second_captured_on"] = second_date
        return service.robots_preview(**kwargs)

    def test_preview_changed_rows_only_and_side_counts(self):
        """Pins S4 preview evaluations, changed row limb. Oracle:
        plan Section 5.1 RobotsPreview: one entry per changed row
        only, each side finding count the table size by
        construction, both files sha256 values carried."""
        result = self.preview(self, FIXTURES / "w4-robots-basic.txt",
                              FIXTURES / "w4-robots-changed.txt",
                              path="/private/page")
        changed = (field(result, "changed_rows")
                   if not isinstance(result, dict) or "changed_rows" in result
                   else field(result, "changes"))
        tokens = [field(row, "token") for row in changed]
        self.assertEqual(tokens, ["GPTBot"])
        self.assertEqual(field(result, "first_finding_count"), 25)
        self.assertEqual(field(result, "second_finding_count"), 25)
        self.assertEqual(
            field(result, "first_sha256"),
            hashlib.sha256((FIXTURES / "w4-robots-basic.txt")
                           .read_bytes()).hexdigest())
        self.assertEqual(
            field(result, "second_sha256"),
            hashlib.sha256((FIXTURES / "w4-robots-changed.txt")
                           .read_bytes()).hexdigest())

    def test_preview_dates_omitted_stated_and_path_defaulted(self):
        """Pins S4 preview date and path limbs. Oracle: plan
        Section 5.1 RobotsPreview and trade T-11 closed route
        set: each file asserted capture date arrives only as a
        named input of the robots-preview call, or the date field
        stands omitted with the omission stated; path_defaulted
        stands true where the call supplied no path."""
        result = self.preview(self, FIXTURES / "w4-robots-basic.txt",
                              FIXTURES / "w4-robots-changed.txt")
        self.assertIs(field(result, "path_defaulted"), True)
        text = json.dumps(result, default=str, ensure_ascii=False)
        self.assertIn("omitted", text.lower())
        dated = self.preview(self, FIXTURES / "w4-robots-basic.txt",
                             FIXTURES / "w4-robots-changed.txt",
                             path="/private/page",
                             first_date="2026-11-01",
                             second_date="2026-11-12")
        self.assertIs(field(dated, "path_defaulted"), False)
        self.assertIn("2026-11-01", json.dumps(
            dated, default=str, ensure_ascii=False))

    def test_preview_stores_nothing(self):
        """Pins S4 preview unstored limb, decided side only.
        Oracle: plan Section 5.1 RobotsPreview, not stored, and
        plan contract entry N7: a preview stores nothing and
        appends nothing of its own. The journal entry count of
        the home stands unchanged across the call."""
        home = make_home(self)
        before = field(service.status(home=str(home)), "entry_count")
        self.preview(self, FIXTURES / "w4-robots-basic.txt",
                     FIXTURES / "w4-robots-changed.txt",
                     path="/private/page", home=home)
        after = field(service.status(home=str(home)), "entry_count")
        self.assertEqual(before, after)


class TestRobotsFailuresAndTiming(unittest.TestCase):
    """Row plan Section 1.3 S4, failure values and timing. Oracle:
    plan Part 1 entry 13 joined table rows X-3 and X-15, and plan
    Section 1.5 timing bounds."""

    def test_undecodable_robots_file_fails_closed(self):
        """Pins S4 decoding failure. Oracle: entry 13 row X-15,
        token ROBOTS_DECODING_FAILED, usage class: a byte order
        mark other than a single leading UTF-8 mark, a legacy
        encoding, or an undecodable byte fails the call closed
        with a recorded error and no robots evaluation."""
        with self.assertRaises(Exception) as caught:
            evaluate(self, FIXTURES / "w4-robots-bad-encoding.bin", "/")
        self.assertIn("ROBOTS_DECODING_FAILED", str(caught.exception))

    def test_single_leading_bom_stripped_and_evaluated(self):
        """Pins S4 decoding, admitted limb. Oracle: brief Section
        5.10 parser rules: UTF-8 strictly, a single leading UTF-8
        byte order mark stripped once and noted, and the file
        evaluates."""
        report = evaluate(self, FIXTURES / "w4-robots-bom.txt",
                          "/private/page")
        self.assertTrue(is_blocked(finding_for(report, "GPTBot")))

    def test_robots_file_over_admitted_size_rejected(self):
        """Pins S4 limit limb. Oracle: entry 13 row X-3, token
        LIMIT_EXCEEDED, and brief Section 5.11 limit 34, robots
        file total size 512 KiB: a file over the limit fails as a
        rejection with a recorded error and no partial
        record."""
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        big = root / "big-robots.txt"
        big.write_bytes(b"# " + b"x" * (512 * 1024))
        with self.assertRaises(Exception) as caught:
            evaluate(self, big, "/")
        self.assertIn("LIMIT_EXCEEDED", str(caught.exception))

    def test_robots_timing_bound_five_seconds(self):
        """Pins S4 timing bound. Oracle: plan Section 1.5 timing
        bounds: S4, robots evaluation over one supplied robots
        file, 5 seconds, a plan design value at the stated test
        scale of one supplied file."""
        start = time.monotonic()
        report = evaluate(self, FIXTURES / "w4-robots-size-case.txt",
                          "/band/page")
        elapsed = time.monotonic() - start
        self.assertEqual(field(report, "finding_count"), 25)
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
