"""The ruled mapping from an earned value to a check status.

An applicable check stores a real status from STATUS_VALUES,
derived from its earned value: a check that earns its full
weight stands pass, a check that earns part of its weight
stands warn, and a check that earns none of its weight
stands fail. The ruling covers the two outputs that read
the status: the audit record's top adverse reasons section
names the checks carrying fail or warn, and the service's
guide trigger build fires a WARN_ code for a partially
earning check, so the guide artefact gains the warning
entry. not_applicable stands as it stood, an applicability
outcome that carries no earned value and derives from no
earned value. The headline score reads status only to set
not_applicable aside, so status assignment leaves it
unchanged.
"""

import tempfile
import unittest
from pathlib import Path

from citeline import checks, reporting, service
from citeline import install as install_module

AUDIT_DATE = "2026-11-14"
SERVICE_AUDIT_DATE = "2026-11-13"


def make_page(paragraphs=None, raw_text=None, sentences=None,
              links=(), headings=(), sections=None, lists=(),
              tables=(), blockquotes=(), word_count=None):
    """Build an ExtractedPage input in the field form the
    checks tests state, as test_s03_checks states it."""
    if raw_text is not None:
        running_text = raw_text
        flat = list(sentences or [])
        paras = [[s] for s in flat]
    else:
        paras = [list(p) for p in (paragraphs or [])]
        flat = [s for p in paras for s in p]
        running_text = "\n\n".join(" ".join(p) for p in paras)
    if word_count is None:
        word_count = sum(len(s.split()) for s in flat)
    if sections is None:
        sections = [{
            "heading_text": None,
            "start": 0,
            "end": len(running_text),
            "references_section": False,
        }]
    return {
        "running_text": running_text,
        "sentences": flat,
        "paragraphs": [" ".join(p) for p in paras],
        "headings": list(headings),
        "sections": sections,
        "links": list(links),
        "blockquotes": list(blockquotes),
        "lists": list(lists),
        "tables": list(tables),
        "date_strings": [],
        "canonical_link_element": None,
        "meta_robots": None,
        "word_count": word_count,
        "extracted_text_length": len(running_text),
        "extraction_notes": [],
    }


def make_facts(**overrides):
    facts = {
        "product_name": "Macroforge",
        "aliases": ["Macroforge"],
        "category_terms": ["workbench"],
        "canonical_line":
            "Macroforge is a campaign workbench for agent teams.",
        "is_product_page": True,
        "domain": "macroforge.example",
        "competitors": [
            {"name": "Rivalforge", "aliases": ["Rivalforge"]}],
    }
    facts.update(overrides)
    return facts


def link(target, text, start):
    return {"text": text, "target": target, "start": start,
            "end": start + len(text)}


def filler_sentences(count, words_per=10):
    """Distinct filler sentences holding no statistic token,
    no date, no quotation, no superlative, and no registry
    term, as test_s03_checks builds them."""
    bank = ["alpha", "bravo", "charlie", "delta", "echo",
            "foxtrot", "golf", "hotel", "india"]
    out = []
    for i in range(count):
        words = ["Filler%02d" % i] + [
            bank[(i + j) % len(bank)]
            for j in range(words_per - 1)]
        out.append(" ".join(words) + ".")
    return out


# The shared scored page of test_s03_checks, with its hand
# computed earned fractions: answer_first 1.0, citations 1.0,
# statistics 0.5, quotations 0.5, comparison 0.6, freshness
# 1.0, description_consistency 1.0, keyword_stuffing 1.0,
# fluff 1.0, unproven_superlatives 1.0.
SCORE_A_SENTENCES = [
    "Macroforge is a campaign workbench for agent teams.",
    "See https://example.org/a and https://example.org/b and "
    "https://example.org/c for details.",
    "Adoption reached 42% across 10 regions.",
    '"Teams plan better together" said Priya Nair.',
    "Versus Rivalforge for planning work.",
    "Updated: 2026-08-16",
]


def score_a_page():
    paragraphs = [[s] for s in SCORE_A_SENTENCES]
    running = "\n\n".join(SCORE_A_SENTENCES)
    links = []
    for target in ("https://example.org/a",
                   "https://example.org/b",
                   "https://example.org/c"):
        links.append(link(target, target, running.index(target)))
    return make_page(paragraphs=paragraphs, links=links)


def run_named(page, facts=None):
    results = checks.run_checks(
        page, facts or make_facts(), audit_date=AUDIT_DATE)
    return {r["check_id"]: r for r in results}, results


class SeamMappingTests(unittest.TestCase):
    """The assign_status seam under the ruled mapping, pinned
    at the seam itself."""

    def test_full_weight_is_pass(self):
        self.assertEqual(
            checks.assign_status(
                "statistics", earned=1.0, weight=13), "pass")

    def test_part_of_the_weight_is_warn(self):
        self.assertEqual(
            checks.assign_status(
                "statistics", earned=0.5, weight=13), "warn")

    def test_none_of_the_weight_is_fail(self):
        self.assertEqual(
            checks.assign_status(
                "statistics", earned=0.0, weight=13), "fail")

    def test_fraction_alone_carries_the_mapping(self):
        self.assertEqual(
            checks.assign_status("statistics", earned=0.5),
            "warn")

    def test_applicable_without_an_earned_value_is_none(self):
        self.assertIsNone(
            checks.assign_status(
                "statistics", earned=None, weight=13))

    def test_applicability_takes_precedence(self):
        self.assertEqual(
            checks.assign_status(
                "comparison", applicable=False, earned=0.6,
                weight=10),
            "not_applicable")
        self.assertEqual(
            checks.assign_status(
                "statistics", empty=True, earned=0.0,
                weight=13),
            "not_applicable")


class RunChecksStatusTests(unittest.TestCase):
    """Statuses on the records run_checks returns."""

    def test_scored_page_statuses_follow_the_earned_values(self):
        named, _ = run_named(score_a_page())
        expected = {
            "answer_first": "pass",
            "citations": "pass",
            "statistics": "warn",
            "quotations": "warn",
            "comparison": "warn",
            "freshness": "pass",
            "description_consistency": "pass",
            "keyword_stuffing": "pass",
            "fluff": "pass",
            "unproven_superlatives": "pass",
        }
        for check_id, status in expected.items():
            self.assertEqual(
                named[check_id]["status"], status, check_id)
        self.assertEqual(named["statistics"]["earned"], 0.5)
        self.assertEqual(named["quotations"]["earned"], 0.5)
        self.assertEqual(named["comparison"]["earned"], 0.6)
        self.assertEqual(named["answer_first"]["earned"], 1.0)

    def test_zero_earning_checks_fail(self):
        page = make_page(
            paragraphs=[[s] for s in filler_sentences(6)])
        named, _ = run_named(page)
        for check_id in ("statistics", "citations", "freshness"):
            self.assertEqual(named[check_id]["earned"], 0.0,
                             check_id)
            self.assertEqual(named[check_id]["status"], "fail",
                             check_id)
        self.assertEqual(
            named["keyword_stuffing"]["status"], "pass")
        self.assertEqual(
            named["unproven_superlatives"]["status"], "pass")

    def test_every_status_stands_inside_the_value_set(self):
        for page in (score_a_page(), make_page(
                paragraphs=[[s] for s in filler_sentences(6)])):
            _, results = run_named(page)
            for record in results:
                self.assertIn(
                    record["status"], checks.STATUS_VALUES,
                    record["check_id"])

    def test_not_applicable_stands_as_it_stood(self):
        named, _ = run_named(
            score_a_page(), make_facts(category_terms=[]))
        comparison = named["comparison"]
        self.assertEqual(comparison["status"], "not_applicable")
        self.assertIsNone(comparison["earned"])

    def test_empty_page_stands_wholly_not_applicable(self):
        _, results = run_named(make_page())
        self.assertEqual(len(results), 10)
        for record in results:
            self.assertEqual(
                record["status"], "not_applicable",
                record["check_id"])
            self.assertIsNone(record["earned"],
                              record["check_id"])


class ScoreUnchangedTests(unittest.TestCase):
    """Status assignment leaves the headline score as it
    stood: compute_score reads status only to set
    not_applicable aside."""

    def test_score_matches_the_status_free_computation(self):
        _, results = run_named(score_a_page())
        score = checks.compute_score(results)
        status_free = []
        for record in results:
            clone = dict(record)
            if clone["status"] != "not_applicable":
                clone["status"] = None
            status_free.append(clone)
        free_score = checks.compute_score(status_free)
        self.assertEqual(score["value"], 84.0)
        self.assertEqual(score["value"], free_score["value"])
        self.assertEqual(score["band"], free_score["band"])
        self.assertEqual(score["band"], "strong")


class AdverseReasonsTests(unittest.TestCase):
    """The audit record's top adverse reasons section names
    the checks carrying fail or warn on a real run."""

    def render_adverse(self, results):
        record = {
            "run_id": "run-1",
            "snapshot_id": "snap-1",
            "evaluated_page_path": "/",
            "path_defaulted": False,
            "audit_date": AUDIT_DATE,
            "checks": results,
            "score": checks.compute_score(results),
        }
        text = reporting.render(record, form="simple")
        return text.split("Top adverse reasons:")[1].split(
            "Checks:")[0]

    def test_warn_checks_named_on_a_real_run(self):
        _, results = run_named(score_a_page())
        adverse = self.render_adverse(results)
        self.assertIn("statistics: warned", adverse)
        self.assertIn("quotations: warned", adverse)
        self.assertIn("comparison: warned", adverse)
        self.assertNotIn("answer_first", adverse)
        self.assertNotIn("freshness", adverse)

    def test_fail_check_named_on_a_real_run(self):
        page = make_page(
            paragraphs=[[s] for s in filler_sentences(6)])
        _, results = run_named(page)
        adverse = self.render_adverse(results)
        self.assertIn("statistics: failed", adverse)
        self.assertIn("freshness: failed", adverse)


class WarnGuideTriggerTests(unittest.TestCase):
    """A partially earning check fires its WARN_ trigger in
    the service's trigger build, and the guide artefact
    gains the warning entry. The page's date stands 196
    days before the audit date, so freshness earns 0.4 of
    its weight under the freshness bands."""

    PAGE_TEXT = (
        "# Example Product\n\n"
        "Example Product answers questions with citations.\n\n"
        "Updated: 2026-05-01\n")

    def setUp(self):
        root = Path(self.enterContext(
            tempfile.TemporaryDirectory()))
        location = root / "install"
        home = root / "home"
        install_module.install(
            location=str(location), home=str(home))
        self.home = home
        service.add_product(
            home=str(home), name="Example Product",
            canonical_line=(
                "Example Product answers questions with "
                "citations."),
            domain="example.com", audit_date=SERVICE_AUDIT_DATE)
        service.name_round(
            home=str(home), product="Example Product",
            round_label="round-1",
            importer_declaration="operator",
            supplier_relation="first party",
            audit_date=SERVICE_AUDIT_DATE)
        page_file = root / "page.md"
        page_file.write_text(self.PAGE_TEXT, encoding="utf-8")
        self.record = service.audit(
            home=str(home), page_file=str(page_file),
            audit_date=SERVICE_AUDIT_DATE)

    def test_partially_earning_check_carries_warn(self):
        named = {r["check_id"]: r for r in self.record["checks"]}
        freshness = named["freshness"]
        self.assertEqual(freshness["earned"], 0.4)
        self.assertEqual(freshness["status"], "warn")

    def test_warn_trigger_fires_for_the_partial_check(self):
        self.assertIn(
            "WARN_FRESHNESS", self.record["trigger_codes"])

    def test_guide_draft_carries_the_warning_action(self):
        draft = service.guide(
            home=str(self.home), run_id=self.record["run_id"],
            audit_date=SERVICE_AUDIT_DATE)
        actions = {a["code"]: a for a in draft["actions"]}
        self.assertIn("WARN_FRESHNESS", actions)
        self.assertIn(
            "gave a warning", actions["WARN_FRESHNESS"]["text"])


if __name__ == "__main__":
    unittest.main()
