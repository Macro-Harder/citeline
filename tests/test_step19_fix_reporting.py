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


class TestR19061StatusUnitsAndSingleFacts(unittest.TestCase):
    """R19-061: status Simple figures carry their units,
    answer_average states what it averages and in what unit,
    and each fact stands once in one vocabulary."""

    def _status(self, **overrides):
        body = {
            "head": "abc123", "head_hash": "abc123",
            "entry_count": 5, "home_path": "/tmp/home",
            "home_size": 2308, "chain_result": "chain verifies",
            "capacity_outlook": {
                "journal_length_remaining": 99995,
                "total_home_size_remaining": 1073739516,
                "entries_remaining": 99995,
                "bytes_remaining": 1073739516,
                "answer_average": {"value": 812.5,
                                   "label": "estimate"},
            },
        }
        body.update(overrides)
        return body

    def test_units_and_single_hash(self):
        text = reporting.render(self._status(), "simple")
        self.assertIn("2308 bytes", text)
        self.assertIn("1073739516 bytes", text)
        self.assertIn("characters", text)
        self.assertIn("average imported answer size", text)
        self.assertEqual(text.count("abc123"), 1)
        self.assertNotIn("\nhead:", text)

    def test_empty_home_absence_stated_once(self):
        body = self._status(head=None, head_hash=None,
                            entry_count=0)
        body["capacity_outlook"]["answer_average"] = (
            "no average stands: no imported answer stands "
            "in this home")
        text = reporting.render(body, "simple")
        self.assertNotIn("head: none", text)
        self.assertNotIn("head_hash: none", text)


class TestR19062RobotsSummaryAndLabels(unittest.TestCase):
    """R19-062: robots Simple output opens with a plain
    summary of the result for the evaluated path, and
    evidence_label, purpose_prose_evidence_label, and
    next_refresh_due_date stand defined on the surface."""

    def test_summary_and_definitions(self):
        body = {
            "evaluated_page_path": "/page",
            "path_defaulted": False,
            "next_refresh_due_date": "2027-02-10",
            "findings": [
                {"token": "A", "outcome": "allowed",
                 "evidence_label": "directly verified",
                 "purpose_prose_evidence_label":
                     "directly verified"},
                {"token": "B", "outcome": "disallowed",
                 "evidence_label": "secondary transcription",
                 "purpose_prose_evidence_label":
                     "secondary transcription"},
                {"token": "C", "outcome": "allowed",
                 "evidence_label": "directly verified",
                 "purpose_prose_evidence_label":
                     "directly verified"},
            ],
        }
        text = reporting.render(body, "simple")
        head = "\n".join(text.splitlines()[:4])
        self.assertIn("/page", head)
        self.assertIn("2 of the 3", text)
        self.assertIn("bars 1", text)
        self.assertIn("evidence_label:", text)
        self.assertIn("purpose_prose_evidence_label:", text)
        self.assertIn("next_refresh_due_date:", text)
        self.assertIn("refresh", text)


class TestR19063QuerySetPlainTail(unittest.TestCase):
    """R19-063: the query set report Simple form ends in
    defined plain names, the total stands with the counts it
    relates to, and naming_none_count is stated in words."""

    def test_plain_tail(self):
        body = {
            "product_id": "p-x", "query_set_version": 2,
            "total_count": 2, "interrogative_count": 1,
            "comparison_count": 0, "named_product_count": 1,
            "bare_topic_count": 0, "duplicate_count": 0,
            "naming_none_count": 1,
            "marker_list_version": None,
        }
        text = reporting.render(body, "simple")
        self.assertIn("name neither the product nor a "
                      "competitor", text)
        self.assertNotIn("naming_none_count: 1", text)
        self.assertNotIn("marker_list_version: not recorded",
                         text)
        self.assertNotIn("duplicate_count: 0", text)
        self.assertNotIn("total_count: 2", text)
        lines = text.splitlines()
        total_at = next(i for i, line in enumerate(lines)
                        if "in total" in line)
        counts_at = next(i for i, line in enumerate(lines)
                         if line.startswith("asks a question"))
        self.assertLess(total_at, counts_at)


class TestR19064ReportableClauseBound(unittest.TestCase):
    """R19-064: the reportable tier clause never says a rate
    may be relied on; it states the presence only bound."""

    def test_clause_bound(self):
        self.assertNotIn("relied on", reporting.TIER_CLAUSES_LINE)
        self.assertNotIn("relied on",
                         reporting.TIER_CLAUSES["reportable"])
        self.assertIn("presence",
                      reporting.TIER_CLAUSES["reportable"])


class TestR19086RoundGuideControlOnlyRound(unittest.TestCase):
    """R19-086: the round guide states the round contents
    from the stored record, counting control answers as
    answers, so a round holding only controls never prints
    that it holds no answers."""

    def test_controls_only_round_states_its_contents(self):
        from citeline import guide as guide_module

        answers = [{
            "answer_id": "ans-6", "control": True,
            "control_kind": "positive", "named": True,
            "cited": True, "named_early": True,
            "citation_instances": [{"target": "example.com"}],
        }]
        draft = guide_module.draft_from_round(
            {"round_id": "p-x:round-1", "product_id": "p-x"},
            canonical_line="Example Product answers "
                           "questions.",
            audit_date="2026-11-13", answers=answers)
        notice = draft.get("empty_round_notice") or ""
        self.assertNotIn("holds no answers", notice)
        self.assertIn("control", notice)
        text = reporting.render(draft, "simple")
        self.assertNotIn("This round holds no answers", text)
        self.assertNotIn("0 of 0 answers in the round", text)


class TestR19003CitedFiguresDefined(unittest.TestCase):
    """R19-003: gross, net, and self citation share stand
    named and defined distinctly in every form of the probe
    report, and the cited rate stands distinguished from
    them."""

    def test_definitions_in_every_form(self):
        import test_s09_reporting as shipped

        root, home = shipped.make_home(self)
        shipped.seed_product(home)
        label = "round-1"
        shipped.name_round(home, label)
        shipped.import_answer(home, label,
                              shipped.ANSWER_NAMED_CITED)
        advanced = shipped.payload(shipped.probe_report(
            home, label, "advanced"))
        definitions = advanced.get("rate_definitions") or {}
        self.assertIn("cited_rate_gross", definitions)
        self.assertIn("any kind", definitions["cited_rate_gross"])
        self.assertIn("cited_rate_net", definitions)
        self.assertIn("not a self citation",
                      definitions["cited_rate_net"])
        self.assertIn("self_citation_share", definitions)
        self.assertIn("citation instances",
                      definitions["self_citation_share"])
        simple = shipped.probe_report(home, label, "simple")
        self.assertIn("at least one citation instance of "
                      "any kind", simple)
        self.assertIn("share of all citation instances",
                      simple)
