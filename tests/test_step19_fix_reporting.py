"""Step 19 repair tests, fix seat 7 (reporting, metrics, guide, README).

Each test pins one repair queue item's stated cure. The tests
stand written before the cures they pin.
"""
import os
import unittest
from pathlib import Path

from citeline import reporting

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def readme_text():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as handle:
        return " ".join(handle.read().split())


class TestR19056CountOnlyRateLine(unittest.TestCase):
    """R19-056: the count only branch of the Simple probe report
    rate line carries the small sample warning the stored record
    holds, never states that no rate is given while showing an
    interval, and counts one answer in the singular."""

    def test_count_only_line_at_n1(self):
        node = {
            "rate": 1.0, "wilson_low": 0.21, "wilson_high": 1.0,
            "tier": "count only", "count": 1, "n": 1,
            "small_sample_warning": True,
        }
        line = reporting._rate_line("named", node)
        self.assertIn("Small sample warning", line)
        self.assertNotIn("no rate is given", line)
        self.assertIn("1 answer,", line)
        self.assertNotIn("1 answers", line)


class TestR19055SimpleOpensWithProseSummary(unittest.TestCase):
    """R19-055: a Simple artefact on the generic surfaces opens
    with a prose summary sentence, not with a raw field name."""

    def test_status_simple_opens_with_prose(self):
        body = {
            "head_hash": "abc123", "entry_count": 3,
            "home_size": 1200, "home_path": "/tmp/home",
            "chain_result": "chain verifies",
        }
        text = reporting.render(body, "simple")
        first = text.splitlines()[0]
        self.assertNotIn("head_hash", first)
        self.assertIn("journal", first)

    def test_verify_simple_opens_with_prose(self):
        body = {"passed": True, "entry_count": 2,
                "chain_result": "chain verifies"}
        text = reporting.render(body, "simple")
        first = text.splitlines()[0]
        self.assertNotIn("passed:", first)
        self.assertIn("verifies", first)


class TestR19054FirstRoundWorkflow(unittest.TestCase):
    """R19-054: the README states the first round workflow in
    work order, with values."""

    def test_workflow_stated_in_order(self):
        text = readme_text()
        audit_at = text.find("creates the snapshot")
        register_at = text.find("register-page takes that snapshot")
        round_at = text.find("must be named before")
        guide_at = text.find("guide identity")
        for position in (audit_at, register_at, round_at, guide_at):
            self.assertGreaterEqual(position, 0)
        self.assertLess(audit_at, register_at)
        self.assertLess(register_at, round_at)

    def test_snapshot_identifier_not_a_file(self):
        text = readme_text()
        self.assertIn("snapshot identifier and not a file", text)


class TestR19090WatchBound(unittest.TestCase):
    """R19-090: the README states the product schedules nothing,
    an external scheduler runs the watch command, one invocation
    is one round only, and cadence is an operator statement."""

    def test_bound_stated(self):
        text = readme_text()
        self.assertIn("schedules nothing", text)
        self.assertIn("external scheduler", text)
        self.assertIn("one invocation is one round only", text)
        self.assertIn("not a product promise", text)
        self.assertNotIn("Runs scheduled watch rounds", text)


if __name__ == "__main__":
    unittest.main()


class TestU08SelectionStatementsEveryForm(unittest.TestCase):
    """U-08: where a selection basis stands recorded, the fixed
    selection statement for that basis stands verbatim in every
    form of the guide artefact, the Simple form included."""

    def _draft_and_forms(self, page_name):
        import json

        import test_s09_reporting as shipped

        root, home = shipped.make_home(self)
        shipped.seed_product(home)
        page = Path(ROOT) / "tests" / "fixtures" / page_name
        record = shipped.audit_page(home, page)
        draft = service_guide(home, record["run_id"])
        if draft["selection_basis"] == "fallback":
            statement = reporting.FALLBACK_STATEMENT
        else:
            statement = reporting.PREFERENCE_STATEMENT
        forms = {}
        for form in ("simple", "advanced", "agentic"):
            rendered = reporting.render(draft, form)
            if isinstance(rendered, dict):
                rendered = rendered.get("report", rendered)
                forms[form] = json.dumps(rendered)
            else:
                forms[form] = rendered
        return statement, forms

    def test_preference_statement_verbatim_everywhere(self):
        statement, forms = self._draft_and_forms(
            "w6-page-preference.md")
        for form, text in forms.items():
            self.assertIn(statement, text, form)

    def test_fallback_statement_verbatim_everywhere(self):
        statement, forms = self._draft_and_forms(
            "w6-page-fallback.md")
        for form, text in forms.items():
            self.assertIn(statement, text, form)


def service_guide(home, run_id):
    from citeline import service

    return service.guide(home=str(home), run_id=run_id)


def audit_body(checks):
    return {
        "run_id": "run-1", "snapshot_id": "snap-1",
        "evaluated_page_path": "/", "path_defaulted": False,
        "audit_date": "2026-11-13",
        "score": {"value": 34.6, "band": "poor",
                  "cap_status": False,
                  "applicable_basis": {
                      "applicable_checks": ["citations"],
                      "applicable_weight": 92},
                  "secondary_figure": {"value": 31.8,
                                       "total_weight": 100}},
        "checks": checks,
    }


class TestR19057SimpleAuditWordsDefined(unittest.TestCase):
    """R19-057: every reason code, status word, and evidence
    class used in Simple audit lines stands defined in plain
    words on the artefact itself."""

    def test_codes_statuses_and_classes_defined(self):
        body = audit_body([
            {"check_id": "citations", "earned": 0.0, "weight": 16,
             "status": None, "reason_code": "CIT_SELF_ONLY",
             "evidence_class": "paper_tested"},
            {"check_id": "description_consistency", "earned": 1.0,
             "weight": 8, "status": "not_applicable",
             "reason_code": "DESC_PRESENT",
             "evidence_class": "post_asserted"},
            {"check_id": "answer_first", "earned": 0.0,
             "weight": 12, "status": None,
             "reason_code": "AF_TERM_NOT_DECLARATIVE",
             "evidence_class": "tool_defined"},
        ])
        text = reporting.render(body, "simple")
        self.assertIn("CIT_SELF_ONLY", text)
        self.assertIn("point only at the page itself", text)
        self.assertIn("paper_tested", text)
        self.assertIn("published paper", text)
        self.assertIn("post_asserted", text)
        self.assertIn("tool_defined", text)
        self.assertIn("not_applicable", text)
        self.assertIn("does not apply", text)


class TestR19058EarnedFigureWording(unittest.TestCase):
    """R19-058: the earned figure in Simple audit lines states
    a fraction of the weight and the points it is worth, so it
    cannot read as points out of the weight, and the head
    lines name the not applicable check whose weight was
    redistributed."""

    def test_earned_line_and_na_head_line(self):
        body = audit_body([
            {"check_id": "statistics", "earned": 0.5,
             "weight": 13, "status": None,
             "reason_code": "STAT_COUNT",
             "evidence_class": "paper_tested"},
            {"check_id": "description_consistency",
             "earned": 1.0, "weight": 8,
             "status": "not_applicable",
             "reason_code": "DESC_PRESENT",
             "evidence_class": "post_asserted"},
        ])
        body["score"]["applicable_basis"] = {
            "applicable_checks": ["statistics"],
            "applicable_weight": 92}
        text = reporting.render(body, "simple")
        self.assertNotIn("earned 0.5 of weight 13", text)
        self.assertIn("fraction 0.5 of its weight of 13", text)
        self.assertIn("worth 6.5 points", text)
        self.assertIn("description_consistency does not apply",
                      text)


class TestR19059HonestySentencePlacement(unittest.TestCase):
    """R19-059: the honesty sentence, which speaks of this
    score, stands only on surfaces that carry a score or a
    report of one; operation results that produce no score do
    not close with it."""

    def test_operation_results_carry_no_honesty_sentence(self):
        status = {"head_hash": "abc123", "entry_count": 3,
                  "home_size": 1200, "home_path": "/tmp/home",
                  "chain_result": "chain verifies"}
        self.assertNotIn("signal index",
                         reporting.render(status, "simple"))
        verify = {"passed": True, "entry_count": 2,
                  "chain_result": "chain verifies"}
        self.assertNotIn("signal index",
                         reporting.render(verify, "simple"))
        added = {"product_id": "p-x", "name": "X"}
        self.assertNotIn("signal index",
                         reporting.render(added, "simple"))

    def test_audit_still_carries_it(self):
        body = audit_body([
            {"check_id": "citations", "earned": 0.0,
             "weight": 16, "status": None,
             "reason_code": "CIT_COUNT",
             "evidence_class": "paper_tested"}])
        self.assertIn("signal index",
                      reporting.render(body, "simple"))


class TestR19060SelfCitationReason(unittest.TestCase):
    """R19-060, self citation limb: where the audit record
    citations check reason is CIT_SELF_ONLY, the guide
    citations action states the self citation reason beside
    the distinct cited target count of 0."""

    def test_low_citations_action_states_self_only_reason(self):
        from citeline import guide as guide_module

        record = {
            "run_id": "run-9", "product_id": "p-x",
            "audit_date": "2026-11-13",
            "trigger_codes": ["LOW_CITATIONS"],
            "distinct_cited_target_count": 0,
            "checks": [
                {"check_id": "citations", "earned": 0.0,
                 "weight": 16, "status": None,
                 "reason_code": "CIT_SELF_ONLY",
                 "detail_counts": {"distinct_target_count": 0}},
            ],
            "sentences": ["Example Product answers questions."],
            "score": {"value": 30.0, "band": "poor",
                      "cap_status": False},
        }
        draft = guide_module.draft_from_audit_record(
            record, canonical_line="Example Product answers "
                                   "questions.",
            product_name="Example Product")
        texts = [a.get("text", "") for a in draft["actions"]]
        joined = "\n".join(texts)
        self.assertIn("distinct cited target count stands "
                      "at 0", joined)
        self.assertIn("own domain", joined)


class TestR19096AdvancedCommonFields(unittest.TestCase):
    """R19-096: every Advanced report object carries the
    anchor limit field, and the probe report, guide,
    query-set-report, and staleness-view objects carry the
    honesty sentence field."""

    def test_fields_stand_on_each_report_object(self):
        import test_s09_reporting as shipped
        from citeline import service

        root, home = shipped.make_home(self)
        shipped.seed_product(home)
        record = shipped.audit_page(home, shipped.PAGE_STRONG)
        label = "round-1"
        shipped.name_round(home, label)
        shipped.import_answer(home, label,
                              shipped.ANSWER_NAMED_CITED)
        probe = shipped.payload(shipped.probe_report(
            home, label, "advanced"))
        self.assertIn("anchor_limit", probe)
        self.assertIn("honesty_sentence", probe)
        draft = service.guide(home=str(home),
                              run_id=record["run_id"])
        guide_body = shipped.payload(
            reporting.render(draft, "advanced"))
        self.assertIn("anchor_limit", guide_body)
        self.assertIn("honesty_sentence", guide_body)
        qs = service.query_set_report(
            home=str(home), product=shipped.PRODUCT,
            form="advanced", audit_date=shipped.AUDIT_DATE)
        qs = shipped.payload(qs)
        self.assertIn("anchor_limit", qs)
        self.assertIn("honesty_sentence", qs)
        stale = service.staleness_view(home=str(home))
        stale = shipped.payload(
            reporting.render(stale, "advanced"))
        self.assertIn("anchor_limit", stale)
        self.assertIn("honesty_sentence", stale)


class TestR19097AnchorSentenceClosingBlock(unittest.TestCase):
    """R19-097: the anchor limit sentence stands in the
    closing block of every Simple report artefact, the
    audit, guide, probe report, and query set report
    included, standing once as a closing line."""

    NEEDLE = "Verify proves internal consistency only"

    def test_sentence_in_closing_block(self):
        import test_s09_reporting as shipped
        from citeline import service

        root, home = shipped.make_home(self)
        shipped.seed_product(home)
        record = shipped.audit_page(home, shipped.PAGE_STRONG)
        label = "round-1"
        shipped.name_round(home, label)
        shipped.import_answer(home, label,
                              shipped.ANSWER_NAMED_CITED)
        texts = {}
        texts["audit"] = shipped.render(record, "simple")
        texts["probe"] = shipped.probe_report(
            home, label, "simple")
        draft = service.guide(home=str(home),
                              run_id=record["run_id"])
        texts["guide"] = shipped.render(draft, "simple")
        texts["queryset"] = service.query_set_report(
            home=str(home), product=shipped.PRODUCT,
            form="simple", audit_date=shipped.AUDIT_DATE)
        for kind, text in texts.items():
            self.assertEqual(text.count(self.NEEDLE), 1, kind)
            tail = "\n".join(text.splitlines()[-3:])
            self.assertIn(self.NEEDLE, tail, kind)

