"""Step 16 fix wave, builder F1: reporting rendering defects.

Each test pins one defect from the Step 16 round 1 fix register
(design/steps/step-16-record.md, defects D-01, D-06, D-19,
D-26, D-27, D-28) at its Simple rendering surface in
citeline/reporting.py. Every test was written before its cure
and watched failing on the shipped code.
"""

import tempfile
import unittest
from pathlib import Path

from citeline import reporting, service
from citeline import install as install_module

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
PRODUCT = "Example Product"
QUERY = "What is Example Product?"
CANONICAL = "Example Product answers questions with citations."

PAGE_STRONG = FIXTURES / "w6-page-strong.md"
PAGE_ONE_CITATION = FIXTURES / "w6-page-one-citation.md"
ROBOTS_A = FIXTURES / "w6-robots-a.txt"
ANSWER_NAMED_CITED = FIXTURES / "w6-answer-named-cited.txt"
ANSWER_NAMED = FIXTURES / "w6-answer-named.txt"
ANSWER_PLAIN = FIXTURES / "w6-answer-plain.txt"

EMPTY_WARNING = (
    "Empty answer warning: %d answers in this round are "
    "empty, with no answer text."
)

CAP_LABEL = (
    "First: actions on citations, statistics, or quotations, "
    "while the evidence cap holds the score at 39. This is an "
    "order of work, not a promised result."
)
SCORE_LABEL = (
    "Next: actions on the checks that earn the score, where "
    "the evidence cap does not hold. This is an order of work, "
    "not a promised result."
)
DEFECT_LABEL = (
    "Separate: actions on a defect that is not a score "
    "matter. This is an order of work, not a promised result."
)
NO_ACTION_LINE = "No action stands in this group for this run."


def rate_block(count, n, low=0.2077, high=0.9385):
    return {
        "rate": (count / n) if n else None,
        "wilson_low": low,
        "wilson_high": high,
        "n": n,
        "tier": "count only",
        "small_sample_warning": True,
        "count": count,
    }


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def seed_product(home):
    service.add_product(
        home=str(home), name=PRODUCT, canonical_line=CANONICAL,
        domain="example.com", audit_date=AUDIT_DATE)
    service.set_aliases(
        home=str(home), product=PRODUCT, aliases=["Example Prod"],
        audit_date=AUDIT_DATE)
    service.set_category(
        home=str(home), product=PRODUCT,
        category_terms=["citation software"], audit_date=AUDIT_DATE)
    service.set_competitors(
        home=str(home), product=PRODUCT,
        competitors=[{"name": "Rival", "domain": "rival.example",
                      "aliases": []}],
        audit_date=AUDIT_DATE)
    service.set_query_set(
        home=str(home), product=PRODUCT, query_set=[QUERY],
        audit_date=AUDIT_DATE)


def seed_round(home, label="round-1"):
    service.name_round(
        home=str(home), product=PRODUCT, round_label=label,
        importer_declaration="operator",
        supplier_relation="first party", audit_date=AUDIT_DATE)
    rows = (
        (ANSWER_NAMED_CITED, "2026-11-10", "engine-a", "manual copy"),
        (ANSWER_NAMED, "2026-11-11", "engine-b", "manual copy"),
        (ANSWER_PLAIN, "2026-11-12", "engine-a", "export file"),
    )
    for answer, captured, engine, method in rows:
        service.probe_import(
            home=str(home), answer_file=str(answer), product=PRODUCT,
            round=label, engine_label=engine, query=QUERY,
            kind="real_sample", captured_on=captured,
            capture_method=method, audit_date=AUDIT_DATE)
    return label


class F1Base(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)
        seed_product(self.home)


class TestD01CountOnlyHeadline(unittest.TestCase):
    """D-01: the count only branch prints the stored count per
    outcome, not the round size n."""

    def test_count_only_line_prints_stored_count_per_outcome(self):
        record = {"rates": {
            "named": rate_block(2, 3),
            "named_early": rate_block(2, 3),
            "cited": rate_block(1, 3, low=0.0615, high=0.7923),
        }}
        text = reporting.render(record, form="simple")
        self.assertIn("named: 2 answers", text)
        self.assertIn("named_early: 2 answers", text)
        self.assertIn("cited: 1 answers", text)
        self.assertNotIn("named: 3 answers", text)
        self.assertNotIn("cited: 3 answers", text)

    def test_count_only_line_prints_zero_count(self):
        record = {"rates": {"cited": rate_block(0, 1, low=0.0,
                                                high=0.7935)}}
        text = reporting.render(record, form="simple")
        self.assertIn("cited: 0 answers", text)
        self.assertNotIn("cited: 1 answers", text)


class TestD01ProbeReportIntegration(F1Base):
    def test_probe_simple_headline_counts_match_stored_counts(self):
        label = seed_round(self.home)
        text = service.probe_report(
            home=str(self.home), product=PRODUCT, round=label,
            form="simple", audit_date=AUDIT_DATE)
        self.assertIn("named: 2 answers", text)
        self.assertIn("cited: 0 answers", text)
        self.assertNotIn("named: 3 answers", text)


class TestD06SimpleAuditProse(F1Base):
    """D-06: the Simple audit artefact is a prose artefact with
    a verdict opening, the band at its head, the top adverse
    reasons, the next actions, and a pointer to Advanced."""

    def audit_simple(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE_STRONG),
            robots_file=str(ROBOTS_A), audit_date=AUDIT_DATE)
        return record, reporting.render(record, form="simple")

    def test_verdict_opening_band_reasons_actions_pointer(self):
        record, text = self.audit_simple()
        lines = text.splitlines()
        self.assertEqual(lines[0], "Audit report.")
        self.assertIn(str(record["score"]["value"]), lines[1])
        self.assertIn(record["score"]["band"], lines[1])
        self.assertIn("Top adverse reasons:", text)
        self.assertIn("Next actions:", text)
        self.assertIn(
            "Advanced artefact for the same run", text)
        self.assertIn(record["run_id"], text)
        self.assertIn(record["snapshot_id"], text)

    def test_no_field_dump_and_no_repeated_record(self):
        record, text = self.audit_simple()
        lines = text.splitlines()
        self.assertLess(len(lines), 250)
        self.assertEqual(text.count("answer_first"), 1)
        self.assertEqual(text.count("keyword_stuffing"), 1)
        self.assertNotIn("evidence_spans:", text)
        self.assertNotIn("detail_counts:", text)

    def test_top_adverse_reasons_follow_stored_order(self):
        record = {
            "run_id": "run-1",
            "snapshot_id": "snap-1",
            "evaluated_page_path": "/",
            "path_defaulted": True,
            "audit_date": AUDIT_DATE,
            "checks": [
                {"check_id": "alpha_check", "weight": 10,
                 "earned": 0.5, "status": "warn",
                 "reason_code": "ALPHA_CODE",
                 "evidence_class": "paper_tested"},
                {"check_id": "beta_check", "weight": 10,
                 "earned": 0.0, "status": "fail",
                 "reason_code": "BETA_CODE",
                 "evidence_class": "tool_defined"},
                {"check_id": "gamma_check", "weight": 10,
                 "earned": 1.0, "status": "pass",
                 "reason_code": "GAMMA_CODE",
                 "evidence_class": "post_asserted"},
            ],
            "score": {"value": 50.0, "band": "thin",
                      "cap_status": False,
                      "applicable_basis": {
                          "applicable_checks": [
                              "alpha_check", "beta_check",
                              "gamma_check"],
                          "applicable_weight": 30}},
        }
        text = reporting.render(record, form="simple")
        self.assertIn("Top adverse reasons:", text)
        adverse = text.split("Top adverse reasons:")[1].split(
            "Checks:")[0]
        self.assertIn("alpha_check", adverse)
        self.assertIn("beta_check", adverse)
        self.assertNotIn("gamma_check", adverse)
        self.assertLess(adverse.index("alpha_check"),
                        adverse.index("beta_check"))


class TestD19EmptyAnswerWarning(unittest.TestCase):
    """D-19: the Simple probe report carries the stated empty
    answer warning sentence where the count is not zero, and
    no sentence where the count is zero."""

    def test_warning_sentence_prints_where_count_not_zero(self):
        record = {"rates": {"named": rate_block(2, 3)},
                  "empty_answer_count": 2}
        text = reporting.render(record, form="simple")
        self.assertIn(EMPTY_WARNING % 2, text)

    def test_no_warning_sentence_where_count_zero(self):
        record = {"rates": {"named": rate_block(2, 3)},
                  "empty_answer_count": 2}
        text = reporting.render(record, form="simple")
        self.assertIn(EMPTY_WARNING % 2, text)
        zero = {"rates": {"named": rate_block(2, 3)},
                "empty_answer_count": 0}
        zero_text = reporting.render(zero, form="simple")
        self.assertNotIn("Empty answer warning:", zero_text)


class TestD26GuideCapSentence(F1Base):
    """D-26: where the guide record carries no action in the
    cap group, the Simple guide states that no action stands
    in that group for this run, so the pinned group label does
    not stand as a claim about this run. The pinned verbatim
    labels themselves stand untouched and in class order."""

    def guide_simple(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE_ONE_CITATION),
            audit_date=AUDIT_DATE)
        draft = service.guide(
            home=str(self.home), run_id=record["run_id"],
            audit_date=AUDIT_DATE)
        return reporting.render(draft, form="simple")

    def test_empty_groups_state_no_action_for_this_run(self):
        text = self.guide_simple()
        self.assertIn(CAP_LABEL, text)
        self.assertIn(SCORE_LABEL, text)
        self.assertIn(DEFECT_LABEL, text)
        self.assertLess(text.index(CAP_LABEL),
                        text.index(SCORE_LABEL))
        cap_block = text.split(CAP_LABEL)[1].split(
            SCORE_LABEL)[0]
        self.assertIn(NO_ACTION_LINE, cap_block)
        defect_block = text.split(DEFECT_LABEL)[1]
        self.assertIn(NO_ACTION_LINE, defect_block)
        score_block = text.split(SCORE_LABEL)[1].split(
            DEFECT_LABEL)[0]
        self.assertNotIn(NO_ACTION_LINE, score_block)

    def test_group_holding_an_action_states_no_absence(self):
        draft = {
            "opening_text": "Example Product answers questions.",
            "actions": [
                {"code": "CITATIONS", "text": "Add citations.",
                 "worklist_class": "cap_first"},
            ],
        }
        text = reporting.render(draft, form="simple")
        cap_block = text.split(CAP_LABEL)[1].split(
            SCORE_LABEL)[0]
        self.assertIn("Add citations.", cap_block)
        self.assertNotIn(NO_ACTION_LINE, cap_block)


class TestD27RobotsPathAtHead(F1Base):
    """D-27: the Simple standalone robots report opens with
    the evaluated page path line and its defaulted line."""

    def test_path_lines_stand_at_the_head(self):
        text = service.robots(
            home=str(self.home), robots_file=str(ROBOTS_A),
            form="simple", audit_date=AUDIT_DATE)
        lines = text.splitlines()
        self.assertEqual(lines[0], "evaluated_page_path: /")
        self.assertEqual(
            lines[1], "The evaluated page path was defaulted.")
        self.assertLess(text.index("evaluated_page_path:"),
                        text.index("findings:"))


class TestD28TrendSimpleLimbs(unittest.TestCase):
    """D-28: on the Simple probe trend, a rate does not print
    at sixteen decimal places, and the none values of
    honesty_line and no_delta_statement do not print as field
    values."""

    def trend_text(self):
        record = {
            "delta": None,
            "series_break": True,
            "series_break_reasons": ["registry_version changed"],
            "first_value": 0.6666666666666666,
            "second_value": 1.0,
            "honesty_line": None,
            "no_delta_statement": None,
        }
        return reporting.render(record, form="simple")

    def test_rate_prints_at_rounded_precision(self):
        text = self.trend_text()
        self.assertNotIn("0.6666666666666666", text)
        self.assertIn("first_value: 0.6667", text)
        self.assertIn("second_value: 1.0", text)

    def test_none_fields_do_not_print_as_field_values(self):
        text = self.trend_text()
        self.assertNotIn("honesty_line: none", text)
        self.assertNotIn("no_delta_statement: none", text)
        self.assertIn("registry_version changed", text)


if __name__ == "__main__":
    unittest.main()
