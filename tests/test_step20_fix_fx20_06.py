"""Step 20 fix tests for seat FX20-06: watch and reporting items.

Items covered: S20-18, S20-20, S20-23, S20-24, S20-25, S20-26,
S20-34, S20-35. Each test was written before its cure and run red
on the PC bench, then green after the cure.

Copyright: J.P. Picard aka Macro-Harder.
"""

import datetime
import json
import tempfile
import unittest
from pathlib import Path

from citeline import reporting, watch

ROOT = Path(__file__).parent.parent
AUDIT_DATE = "2026-11-14"
OLD_DATE = datetime.date(2020, 1, 1)
AUDIT_DAY = datetime.date(2026, 11, 14)


def audit_record(checks, score_extra=None, **extra):
    score = {"value": 50.0, "band": "middle"}
    if score_extra:
        score.update(score_extra)
    record = {
        "run_id": "run-1",
        "checks": checks,
        "score": score,
        "sentences": [],
    }
    record.update(extra)
    return record


class TestS2018PageAgeUsesExtractedText(unittest.TestCase):
    """S20-18: the watch page age stands on the extracted text
    itself, never on the record sentences joined back together."""

    def test_labelled_line_in_extracted_text_governs(self):
        text = ("Released 2026-08-16 for review\n"
                "Updated: 2020-01-01\n"
                "Body sentence.")
        record = {
            "sentences": [
                "Released 2026-08-16 for review "
                "Updated: 2020-01-01 Body sentence."],
            "running_text": text,
            "audit_date": AUDIT_DATE,
        }
        self.assertEqual(
            watch._page_age_days(record, AUDIT_DATE),
            (AUDIT_DAY - OLD_DATE).days)

    def test_date_past_twenty_lines_of_extracted_text_stands_absent(self):
        lines = ["Heading %d" % index for index in range(21)]
        lines.append("2026-08-16")
        lines.append("Body sentence.")
        record = {
            "sentences": [" ".join(lines)],
            "running_text": "\n".join(lines),
            "audit_date": AUDIT_DATE,
        }
        self.assertIsNone(watch._page_age_days(record, AUDIT_DATE))

    def test_sentences_alone_carry_no_age(self):
        record = {
            "sentences": ["Updated: 2020-01-01 in a sentence."],
            "audit_date": AUDIT_DATE,
        }
        self.assertIsNone(watch._page_age_days(record, AUDIT_DATE))


class TestS2034PageAgeReadsRecordAuditDate(unittest.TestCase):
    """S20-34: where the plan names no audit date, the record's
    own audit date governs the page age."""

    def test_record_audit_date_used_when_plan_date_absent(self):
        record = {
            "sentences": [],
            "running_text": "Body dated 2026-08-16 in the text.\nMore.",
            "audit_date": AUDIT_DATE,
        }
        self.assertEqual(watch._page_age_days(record, None), 90)


class TestS2035ProbeTargetDisregardedFieldsNamed(unittest.TestCase):
    """S20-35: a picked probe target's guide flag and audit limb
    fields stand named as disregarded in the plan warnings."""

    def warnings_for(self, target):
        plan = {"scope": "picked", "form": "simple"}
        return watch._plan_warnings(plan, [target])

    def test_probe_target_fields_named(self):
        warnings = self.warnings_for({
            "product": "p-alpha", "round": "round-1", "guide": True,
            "robots_file": "robots.txt",
            "evaluated_page_path": "/page"})
        joined = "\n".join(warnings)
        for field in ("guide", "robots_file", "evaluated_page_path"):
            self.assertIn(field, joined)
        self.assertIn("disregarded", joined)

    def test_audit_target_fields_not_named(self):
        warnings = self.warnings_for({
            "product": "p-alpha", "page_file": "page.txt",
            "guide": True, "robots_file": "robots.txt",
            "evaluated_page_path": "/page"})
        self.assertNotIn("disregarded", "\n".join(warnings))

    def test_probe_target_without_those_fields_not_named(self):
        warnings = self.warnings_for({
            "product": "p-alpha", "round": "round-1", "guide": False})
        self.assertNotIn("disregarded", "\n".join(warnings))


class TestS2023SecondaryFigureNonNumeric(unittest.TestCase):
    """S20-23: a non numeric stored earned or weight stands as no
    figure to the secondary figure recompute, never a crash."""

    def render_with(self, earned, weight):
        checks = [
            {"check_id": "comparison", "status": "not_applicable",
             "earned": 0, "weight": 10},
            {"check_id": "citations", "status": "fail",
             "earned": earned, "weight": weight},
        ]
        return reporting.render(audit_record(checks), "advanced")

    def test_non_numeric_earned_renders_without_figure(self):
        body = self.render_with("abc", 10)
        self.assertIsNone(body["score"].get("secondary_figure"))

    def test_non_numeric_weight_renders_without_figure(self):
        body = self.render_with(0.5, "xyz")
        self.assertIsNone(body["score"].get("secondary_figure"))

    def test_bool_earned_renders_without_figure(self):
        body = self.render_with(True, 10)
        self.assertIsNone(body["score"].get("secondary_figure"))

    def test_numeric_earned_still_recomputes(self):
        body = self.render_with(0.5, 100)
        figure = body["score"].get("secondary_figure")
        self.assertIsNotNone(figure)
        self.assertEqual(figure["value"], 50.0)


class TestS2024ApplicableChecksCountForm(unittest.TestCase):
    """S20-24: applicable_checks standing as a count renders in
    the Simple audit form without a crash."""

    def test_count_form_renders(self):
        record = audit_record([], score_extra={
            "applicable_basis": {
                "applicable_checks": 3, "applicable_weight": 100}})
        text = reporting.render(record, "simple")
        self.assertIn(
            "The score rests on 3 checks, with a total weight "
            "of 100.", text)


class TestS2025PageTextLoopGuards(unittest.TestCase):
    """S20-25: a non record check or section item in the page
    text loop stands skipped, never a crash."""

    def test_non_record_check_item_renders(self):
        record = audit_record(["not-a-dict"])
        text = reporting.render(record, "simple")
        self.assertIn("Audit report.", text)

    def test_non_record_section_item_renders(self):
        record = audit_record([{
            "check_id": "citations", "status": "fail",
            "reason_code": "CIT_COUNT",
            "evidence_class": "tool_defined",
            "section_breakdown": ["not-a-dict"]}])
        text = reporting.render(record, "simple")
        self.assertIn("Audit report.", text)


class TestS2026QuerySetSingularNoun(unittest.TestCase):
    """S20-26: the query set Simple lines print the singular noun
    at a count of one, in the form the rate lines already use."""

    def render_counts(self, total, duplicates, naming_none):
        record = {
            "total_count": total,
            "interrogative_count": 0,
            "duplicate_count": duplicates,
            "naming_none_count": naming_none,
        }
        return reporting.render(record, "simple")

    def test_count_of_one_uses_singular(self):
        text = self.render_counts(1, 1, 1)
        self.assertIn("The set holds 1 query string in total.", text)
        self.assertIn(
            "duplicates: 1 query string stand more than once "
            "in the set.", text)
        self.assertIn(
            "naming none: 1 query string name neither the "
            "product nor a competitor.", text)

    def test_count_of_two_keeps_plural(self):
        text = self.render_counts(2, 2, 2)
        self.assertIn("The set holds 2 query strings in total.", text)


class TestS2020ReportingTextMatchesRecompute(unittest.TestCase):
    """S20-20: the README and the render docstring state the
    governed recompute as it stands, and the recompute itself
    stands unchanged."""

    def test_readme_states_the_recompute(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn(
            "Reporting adds no number to what is stored.", readme)
        self.assertIn("secondary figure", readme)

    def test_render_docstring_states_the_recompute(self):
        doc = reporting.render.__doc__ or ""
        self.assertNotIn("recomputes nothing", doc)
        self.assertIn("secondary figure", doc)


class TestWatchRoundEndToEnd(unittest.TestCase):
    """The watch round as a whole: the page age on a picked audit
    target follows the extracted text the audit itself used, and
    a plan with no audit date still reports the age from the
    record's own audit date."""

    def seed(self, page_text):
        from citeline import install as install_module
        from citeline import service
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        location, home = root / "install", root / "home"
        install_module.install(location=str(location), home=str(home))
        service.add_product(
            home=str(home), name="p-alpha",
            canonical_line="p-alpha line.", domain="example.com",
            audit_date=AUDIT_DATE)
        page = root / "page.txt"
        page.write_text(page_text, encoding="utf-8")
        return root, home, page

    def run_round(self, home, page, with_date=True):
        plan = {"home": str(home), "scope": "picked",
                "form": "simple",
                "targets": [{"product": "p-alpha",
                             "page_file": str(page)}]}
        if with_date:
            plan["audit_date"] = AUDIT_DATE
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = root / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        return watch.run_watch(plan_file=str(path))

    def test_round_page_age_follows_labelled_line(self):
        page_text = ("Released 2026-08-16 for review\n"
                     "Updated: 2020-01-01\n"
                     "Body sentence about p-alpha.\n")
        _, home, page = self.seed(page_text)
        result = self.run_round(home, page)
        entry = result["entries"][0]
        self.assertEqual(entry["outcome"], "completed")
        self.assertEqual(
            entry["page_age_days"], (AUDIT_DAY - OLD_DATE).days)

    def test_round_without_plan_date_reports_age(self):
        page_text = "Body dated 2026-08-16 in the text.\nMore text.\n"
        _, home, page = self.seed(page_text)
        result = self.run_round(home, page, with_date=False)
        entry = result["entries"][0]
        self.assertEqual(entry["outcome"], "completed")
        self.assertIsNotNone(entry["page_age_days"])


if __name__ == "__main__":
    unittest.main()
