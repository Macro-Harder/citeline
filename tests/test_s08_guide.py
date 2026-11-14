"""Slice S8 tests: guide.

Written before the product exists. Every test imports the product
package named citeline and calls the operations under the names the
plan states: module guide for the slice (plan Section 5.3 module
boundary row for S8), and the service layer operation guide (brief
Section 5.4 surface list, brief Section 5.12 inputs: exactly one of
run_id, or product with round label). Import or attribute failure is
the expected red state. No stub and no mock of the product stands in
this file. Dates are call inputs in every test; no test reads a date
from a clock.

Every test method docstring names the matrix row it pins by section
qualified identifier and the oracle passage. Rows whose expectation
is that a named check fires a FAIL_ or WARN_ trigger stand blocked
on CL-16 at plan Part B entry B1 and stand filed in blocked-w6.md,
not written here.
"""

import tempfile
import time
import unittest
from pathlib import Path

from citeline import guide, service
from citeline import install as install_module

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
CANONICAL = "Example Product answers questions with citations."
PRODUCT = "Example Product"
QUERY = "What is Example Product?"

PAGE_PREFERENCE = FIXTURES / "w6-page-preference.md"
PAGE_FALLBACK = FIXTURES / "w6-page-fallback.md"
PAGE_CATEGORY_ONLY = FIXTURES / "w6-page-category-only.md"
PAGE_CITATION_ONLY = FIXTURES / "w6-page-citation-only.md"
PAGE_NO_EVIDENCE = FIXTURES / "w6-page-no-evidence.md"
PAGE_ONE_CITATION = FIXTURES / "w6-page-one-citation.md"
PAGE_STRONG = FIXTURES / "w6-page-strong.md"
ROBOTS_A = FIXTURES / "w6-robots-a.txt"
ANSWER_NAMED_CITED = FIXTURES / "w6-answer-named-cited.txt"
ANSWER_PLAIN = FIXTURES / "w6-answer-plain.txt"
ANSWER_CONTROL_PASS = FIXTURES / "w6-answer-control-pass.txt"
ANSWER_CONTROL_FAIL = FIXTURES / "w6-answer-control-fail.txt"

FAIL_CODES = [
    "FAIL_CITATIONS", "FAIL_STATISTICS", "FAIL_QUOTATIONS",
    "FAIL_COMPARISON", "FAIL_FRESHNESS", "FAIL_DESCRIPTION",
    "FAIL_KEYWORD", "FAIL_FLUFF", "FAIL_SUPERLATIVES",
    "FAIL_ANSWER_FIRST",
]
WARN_CODES = ["WARN_" + code[len("FAIL_"):] for code in FAIL_CODES]
CLOSED_TRIGGER_CODES = set(FAIL_CODES) | set(WARN_CODES) | {
    "LOW_CITATIONS", "NO_REUSABLE_EVIDENCE",
    "CITATION_ONLY_NO_QUOTABLE_SENTENCE",
    "NOT_NAMED", "NOT_NAMED_EARLY", "NOT_CITED",
}
ROUND_TRIGGER_CODES = {"NOT_NAMED", "NOT_NAMED_EARLY", "NOT_CITED"}


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def action_codes(draft):
    return [field(a, "code") for a in field(draft, "actions")]


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def seed_product(case, home, category=("citation software",)):
    service.add_product(
        home=str(home), name=PRODUCT, canonical_line=CANONICAL,
        domain="example.com", audit_date=AUDIT_DATE)
    service.set_aliases(
        home=str(home), product=PRODUCT, aliases=["Example Prod"],
        audit_date=AUDIT_DATE)
    service.set_category(
        home=str(home), product=PRODUCT, category_terms=list(category),
        audit_date=AUDIT_DATE)
    service.set_competitors(
        home=str(home), product=PRODUCT,
        competitors=[{"name": "Rival", "domain": "rival.example",
                      "aliases": []}],
        audit_date=AUDIT_DATE)
    return home


def audit_page(home, page, **extra):
    return service.audit(
        home=str(home), page_file=str(page), audit_date=AUDIT_DATE,
        **extra)


def guide_for_run(home, run_id):
    return service.guide(home=str(home), run_id=run_id,
                         audit_date=AUDIT_DATE)


def guide_for_round(home, label):
    return service.guide(home=str(home), product=PRODUCT,
                         round_label=label, audit_date=AUDIT_DATE)


def name_round(home, label):
    service.name_round(
        home=str(home), product=PRODUCT, round_label=label,
        importer_declaration="operator", supplier_relation="first party",
        audit_date=AUDIT_DATE)


def import_answer(home, label, answer, captured_on="2026-11-10",
                  engine="engine-a", method="manual copy", **extra):
    return service.probe_import(
        home=str(home), answer_file=str(answer), product=PRODUCT,
        round=label, engine_label=engine, query=QUERY,
        kind="real_sample", captured_on=captured_on,
        capture_method=method, audit_date=AUDIT_DATE, **extra)


class GuideBase(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)
        seed_product(self, self.home)


class TestGuideDraftShape(GuideBase):
    """Row S8 GuideDraft shape. Oracle: plan Section 5.1 GuideDraft
    entry and brief Section 5.2 GuideDraft field list."""

    def test_page_draft_carries_the_guide_draft_fields(self):
        """Pins plan Section 1.3 S8, GuideDraft shape for a page input.
        Oracle: plan Section 5.1 GuideDraft entry: provenance, exactly
        one of source_run_id or source_round_id, product_id, the
        version stamps and audit date the input record carries,
        opening_text, refused, refusal_code or null, actions, and
        standing_action."""
        record = audit_page(self.home, PAGE_PREFERENCE)
        draft = guide_for_run(self.home, field(record, "run_id"))
        for name in ("provenance", "product_id", "opening_text",
                     "refused", "refusal_code", "actions",
                     "standing_action"):
            self.assertIn(name, draft if isinstance(draft, dict)
                          else vars(draft))
        self.assertTrue(field(draft, "source_run_id"))
        self.assertFalse(field(draft, "source_round_id"))
        self.assertEqual(field(draft, "product_id"),
                         field(record, "product_id"))
        self.assertEqual(field(draft, "audit_date"), AUDIT_DATE)

    def test_round_draft_carries_source_round_and_no_run(self):
        """Pins plan Section 1.3 S8, GuideDraft shape for a round
        input. Oracle: plan Section 5.1 GuideDraft entry: exactly one
        standing of source_run_id or source_round_id, here the round
        form."""
        name_round(self.home, "round-1")
        import_answer(self.home, "round-1", ANSWER_NAMED_CITED)
        draft = guide_for_round(self.home, "round-1")
        self.assertTrue(field(draft, "source_round_id"))
        self.assertFalse(field(draft, "source_run_id"))
        self.assertTrue(field(draft, "product_id"))

    def test_each_action_carries_its_stated_fields(self):
        """Pins plan Section 1.3 S8, action field form. Oracle: plan
        Section 5.1 GuideDraft entry: each action carries code, text,
        input_source, page_audit or probe_round, the check or outcome
        that produced it, and worklist_class or null."""
        name_round(self.home, "round-empty")
        draft = guide_for_round(self.home, "round-empty")
        self.assertTrue(field(draft, "actions"))
        for action in field(draft, "actions"):
            for name in ("code", "text", "input_source",
                         "worklist_class"):
                self.assertIn(name, action if isinstance(action, dict)
                              else vars(action))
            self.assertEqual(field(action, "input_source"),
                             "probe_round")


class TestDraftSelectionOrdering(GuideBase):
    """Row S8 draft selection ordering. Oracle: brief Section 5.12
    item 137 draft rules and the IM7-BRK-13 landing at that section:
    prefer the first quotable evidence sentence in extracted order
    that passes the naming preference test; where none passes, fall
    back to the first quotable evidence sentence in extracted order.
    The draft opening is the canonical line plus the chosen
    sentence, attributed as the page gives it."""

    def test_preference_picks_first_sentence_that_names_the_product(self):
        """Pins plan Section 1.3 S8, draft selection ordering,
        preference limb. Oracle: brief Section 5.12 IM7-BRK-13
        landing: the first quotable sentence that passes the naming
        test is chosen over an earlier quotable sentence that does
        not name the product, an alias, or a category term."""
        record = audit_page(self.home, PAGE_PREFERENCE)
        draft = guide_for_run(self.home, field(record, "run_id"))
        self.assertEqual(
            field(draft, "opening_text"),
            CANONICAL + " Example Product recorded 42 percent faster "
            "retrieval in the same independent testing.")
        self.assertFalse(field(draft, "refused"))

    def test_fallback_picks_first_quotable_sentence(self):
        """Pins plan Section 1.3 S8, draft selection ordering,
        fallback limb. Oracle: brief Section 5.12 IM7-BRK-13 landing:
        where no quotable evidence sentence passes the preference
        test, the draft falls back to the first quotable evidence
        sentence in extracted order."""
        record = audit_page(self.home, PAGE_FALLBACK)
        draft = guide_for_run(self.home, field(record, "run_id"))
        self.assertEqual(
            field(draft, "opening_text"),
            CANONICAL + " Independent testing recorded 42 percent "
            "faster retrieval across many trials.")
        self.assertFalse(field(draft, "refused"))

    def test_category_term_alone_passes_the_preference_test(self):
        """Pins plan Section 1.3 S8, draft selection ordering,
        category limb. Oracle: brief Section 5.12 IM7-BRK-13 landing:
        the preference test is a naming test over the product name,
        its aliases, and its category terms; a sentence naming only
        a category term passes it."""
        record = audit_page(self.home, PAGE_CATEGORY_ONLY)
        draft = guide_for_run(self.home, field(record, "run_id"))
        self.assertEqual(
            field(draft, "opening_text"),
            CANONICAL + " Citation software recorded 42 percent "
            "faster retrieval in the same independent testing.")

    def test_empty_category_list_runs_the_test_on_name_and_aliases(self):
        """Pins plan Section 1.3 S8, draft selection ordering, empty
        category limb. Oracle: brief Section 5.12 IM7-BRK-13 landing:
        where the product category list stands empty, the preference
        test runs on the product name and its aliases only, so a
        sentence naming only a category term does not pass and the
        fallback stands."""
        seed_product(self, self.home, category=())
        record = audit_page(self.home, PAGE_CATEGORY_ONLY)
        draft = guide_for_run(self.home, field(record, "run_id"))
        self.assertEqual(
            field(draft, "opening_text"),
            CANONICAL + " Independent testing recorded 42 percent "
            "faster retrieval across many trials.")


class TestCitationOnlyAndRefusal(GuideBase):
    """Row S8 refusal behaviour and draft rules. Oracle: brief
    Section 5.12 item 137 draft rules under grill Q8."""

    def test_citation_only_page_drafts_the_canonical_line_alone(self):
        """Pins plan Section 1.3 S8, the citation only draft rule.
        Oracle: brief Section 5.12 item 137: on a citation only
        page, the draft is the canonical line alone, with no
        evidence sentence added and none invented, and code
        CITATION_ONLY_NO_QUOTABLE_SENTENCE recorded; the outcome is
        not a refusal."""
        record = audit_page(self.home, PAGE_CITATION_ONLY)
        draft = guide_for_run(self.home, field(record, "run_id"))
        self.assertEqual(field(draft, "opening_text"), CANONICAL)
        self.assertFalse(field(draft, "refused"))
        self.assertIsNone(field(draft, "refusal_code"))
        self.assertIn("CITATION_ONLY_NO_QUOTABLE_SENTENCE",
                      action_codes(draft))

    def test_no_reusable_evidence_refuses_and_still_produces_actions(self):
        """Pins plan Section 1.3 S8, refusal behaviour. Oracle: brief
        Section 5.12 item 137: where no reusable evidence stands,
        the guide refuses, opening_text is present with a null
        value, code NO_REUSABLE_EVIDENCE is recorded, and the action
        list is still produced."""
        record = audit_page(self.home, PAGE_NO_EVIDENCE)
        draft = guide_for_run(self.home, field(record, "run_id"))
        self.assertTrue(field(draft, "refused"))
        self.assertIsNone(field(draft, "opening_text"))
        self.assertEqual(field(draft, "refusal_code"),
                         "NO_REUSABLE_EVIDENCE")
        self.assertIsInstance(field(draft, "actions"), list)
        self.assertIn("LOW_CITATIONS", action_codes(draft))


class TestNoTriggerCase(GuideBase):
    """Row S8 the no trigger case. Oracle: brief Section 5.12 item
    137 GuideDraft outcomes, stated once."""

    def test_page_with_no_firing_trigger_is_canonical_alone_not_refusal(self):
        """Pins plan Section 1.3 S8, the no trigger case for a page
        input. Oracle: brief Section 5.12 item 137: for a page input
        with no firing trigger, the outcome is the canonical line
        alone with an empty action list, not a refusal and not an
        error."""
        record = audit_page(self.home, PAGE_STRONG)
        draft = guide_for_run(self.home, field(record, "run_id"))
        self.assertEqual(field(draft, "opening_text"), CANONICAL)
        self.assertEqual(field(draft, "actions"), [])
        self.assertFalse(field(draft, "refused"))
        self.assertIsNone(field(draft, "refusal_code"))

    def test_round_with_no_firing_trigger_is_canonical_alone(self):
        """Pins plan Section 1.3 S8, the no trigger case for a round
        input. Oracle: brief Section 5.12 item 137: no firing round
        trigger gives the canonical line alone with an empty action
        list, refused false, refusal_code null."""
        name_round(self.home, "round-1")
        import_answer(self.home, "round-1", ANSWER_NAMED_CITED)
        draft = guide_for_round(self.home, "round-1")
        self.assertEqual(field(draft, "opening_text"), CANONICAL)
        self.assertEqual(field(draft, "actions"), [])
        self.assertFalse(field(draft, "refused"))
        self.assertIsNone(field(draft, "refusal_code"))


class TestClosedTriggerListAsBriefData(GuideBase):
    """Row S8 the closed trigger list and draft rules (items 137 and
    139) as brief data. Oracle: brief Section 5.12 item 137, the
    closed list stated in two parts, page triggers then round
    triggers, with item 139 for LOW_CITATIONS."""

    def test_trigger_code_set_is_exactly_the_closed_list(self):
        """Pins plan Section 1.3 S8, the closed trigger list as brief
        data. Oracle: brief Section 5.12 item 137: the FAIL_ and
        WARN_ forms of the ten checks, LOW_CITATIONS, the refusal
        code NO_REUSABLE_EVIDENCE,
        CITATION_ONLY_NO_QUOTABLE_SENTENCE, and the round triggers
        NOT_NAMED, NOT_NAMED_EARLY, NOT_CITED. No other trigger
        ships."""
        self.assertEqual(set(guide.TRIGGER_CODES), CLOSED_TRIGGER_CODES)
        self.assertEqual(len(guide.TRIGGER_CODES), 26)

    def test_low_citations_fires_below_two_distinct_cited_targets(self):
        """Pins plan Section 1.3 S8, item 139 as brief data. Oracle:
        brief Section 5.12 items 137 and 139: LOW_CITATIONS is
        produced where the distinct cited target count for the page
        is under 2, that is 0 or 1, a design value stated in the
        brief. This code is neither a FAIL_ nor a WARN_ form, so the
        row stands outside the CL-16 blocked class at B1."""
        record = audit_page(self.home, PAGE_ONE_CITATION)
        draft = guide_for_run(self.home, field(record, "run_id"))
        self.assertIn("LOW_CITATIONS", action_codes(draft))

    def test_empty_round_fires_all_three_round_triggers(self):
        """Pins plan Section 1.3 S8, the round trigger limb of the
        closed list. Oracle: brief Section 5.12 item 137 GuideDraft
        outcomes: an empty round fires all three round triggers on
        their terms, and a firing round trigger gives the canonical
        line alone, refused false, refusal_code null."""
        name_round(self.home, "round-empty")
        draft = guide_for_round(self.home, "round-empty")
        self.assertEqual(set(action_codes(draft)), ROUND_TRIGGER_CODES)
        self.assertEqual(field(draft, "opening_text"), CANONICAL)
        self.assertFalse(field(draft, "refused"))
        self.assertIsNone(field(draft, "refusal_code"))


class TestWorklistClassDerivation(GuideBase):
    """Row S8 worklist class derivation. Oracle: brief Section 5.12
    IM7-DIV-3 landing, cap first worklist: classes derive from the
    stored AuditRun alone, from its cap_status, its check outcomes,
    and its robots summary, and from nothing else."""

    def test_low_citations_action_is_cap_first_where_the_cap_operates(self):
        """Pins plan Section 1.3 S8, worklist class cap_first. Oracle:
        brief Section 5.12 IM7-DIV-3 landing and brief Section 5.8
        cap rule: cap_first stands for an action on the citations
        check, including one produced by LOW_CITATIONS, where the
        stored cap_status shows the evidence cap operating; the cap
        operates where citations, statistics, and quotations all
        count zero, as the no evidence page stands."""
        record = audit_page(self.home, PAGE_NO_EVIDENCE)
        self.assertTrue(field(field(record, "score"), "cap_status"))
        draft = guide_for_run(self.home, field(record, "run_id"))
        classes = {field(a, "code"): field(a, "worklist_class")
                   for a in field(draft, "actions")}
        self.assertEqual(classes["LOW_CITATIONS"], "cap_first")

    def test_low_citations_action_is_score_check_where_cap_does_not_operate(self):
        """Pins plan Section 1.3 S8, worklist class score_check.
        Oracle: brief Section 5.12 IM7-DIV-3 landing: score_check
        stands for every other action produced by a page check,
        including an action on an evidence check where the cap does
        not operate; one cited target stands, so the all zero cap
        condition does not stand."""
        record = audit_page(self.home, PAGE_ONE_CITATION)
        self.assertFalse(field(field(record, "score"), "cap_status"))
        draft = guide_for_run(self.home, field(record, "run_id"))
        classes = {field(a, "code"): field(a, "worklist_class")
                   for a in field(draft, "actions")}
        self.assertEqual(classes["LOW_CITATIONS"], "score_check")

    def test_round_actions_carry_no_class_value(self):
        """Pins plan Section 1.3 S8, worklist class on round actions.
        Oracle: brief Section 5.12 IM7-DIV-3 landing: for an action
        produced by a round outcome, no cap and no score stand, and
        the field carries no class value, standing null on every
        such action."""
        name_round(self.home, "round-empty")
        draft = guide_for_round(self.home, "round-empty")
        for action in field(draft, "actions"):
            self.assertIsNone(field(action, "worklist_class"))

    def test_defect_not_score_stands_empty_by_construction(self):
        """Pins plan Section 1.3 S8, worklist class defect_not_score
        empty limb. Oracle: brief Section 5.12 IM7-DIV-3 landing and
        plan Section 5.1 GuideDraft entry: no trigger in the closed
        list is produced by a robots outcome, so no action in
        version 1 derives this class, even on an audit that carries
        a robots summary."""
        record = audit_page(self.home, PAGE_ONE_CITATION,
                            robots_file=str(ROBOTS_A))
        draft = guide_for_run(self.home, field(record, "run_id"))
        name_round(self.home, "round-empty")
        round_draft = guide_for_round(self.home, "round-empty")
        for any_draft in (draft, round_draft):
            for action in field(any_draft, "actions"):
                self.assertNotEqual(field(action, "worklist_class"),
                                    "defect_not_score")


class TestStandingAction(GuideBase):
    """Row S8 the standing action. Oracle: brief Section 5.12 item
    137 standing action passage and plan Section 5.1 GuideDraft
    entry: ACT_THIRD_PARTY stands beside the actions list in the
    standing_action field, as separate guide content no check
    produces, manual and unscored, with no file ingestion route
    behind it."""

    def test_standing_action_stands_beside_the_actions_list(self):
        """Pins plan Section 1.3 S8, standing action placement.
        Oracle: brief Section 5.12 item 137: the standing action
        ships in every guide output, in the refusal case and in the
        no trigger case alike, standing beside the actions list and
        never as an element of it."""
        record = audit_page(self.home, PAGE_STRONG)
        plain = guide_for_run(self.home, field(record, "run_id"))
        refused_record = audit_page(self.home, PAGE_NO_EVIDENCE)
        refused = guide_for_run(self.home,
                                field(refused_record, "run_id"))
        for draft in (plain, refused):
            self.assertEqual(field(draft, "standing_action"),
                             "ACT_THIRD_PARTY")
            self.assertNotIn("ACT_THIRD_PARTY", action_codes(draft))

    def test_standing_action_is_a_code_and_carries_no_class_or_score(self):
        """Pins plan Section 1.3 S8, standing action form. Oracle:
        brief Section 5.12 IM7-DIV-3 landing: the standing action is
        not an element of the actions list, so it carries no class
        value and no class field at all; plan Section 5.1 states it
        manual and unscored, so the field carries the code alone and
        no score stands on it."""
        record = audit_page(self.home, PAGE_ONE_CITATION)
        draft = guide_for_run(self.home, field(record, "run_id"))
        standing = field(draft, "standing_action")
        self.assertEqual(standing, "ACT_THIRD_PARTY")
        self.assertIsInstance(standing, str)


class TestRepeatCalls(GuideBase):
    """Row S8 repeat calls. Oracle: plan Trade T-9: each repeat call
    over an unchanged record appends a new guide_record; no no op
    form is adopted."""

    def test_each_repeat_call_appends_a_new_guide_record(self):
        """Pins plan Section 1.3 S8, repeat calls, on trade T-9.
        Oracle: plan Section 4.6 trade T-9 and brief Section 11 N1:
        a repeat guide call over an unchanged record appends a new
        guide_record, so the journal entry count rises by exactly
        one per call and each draft stands on the same record
        content."""
        record = audit_page(self.home, PAGE_ONE_CITATION)
        before = field(service.status(home=str(self.home)),
                       "entry_count")
        first = guide_for_run(self.home, field(record, "run_id"))
        mid = field(service.status(home=str(self.home)), "entry_count")
        second = guide_for_run(self.home, field(record, "run_id"))
        after = field(service.status(home=str(self.home)),
                      "entry_count")
        self.assertEqual(mid, before + 1)
        self.assertEqual(after, mid + 1)
        self.assertEqual(field(first, "opening_text"),
                         field(second, "opening_text"))
        self.assertEqual(action_codes(first), action_codes(second))
        self.assertEqual(field(first, "refused"),
                         field(second, "refused"))


class TestGuideOffCompleteness(GuideBase):
    """Row S8 guide off completeness. Oracle: plan Section 1.3 S8
    and IM2-INV-4: the acceptance suites of S1 to S7 and S9 pass
    with no guide call made and no guide record present; the module
    boundary table at plan Section 5.3 shows no component depending
    on this slice. This test drives the non guide operations this
    module itself uses and states its standing in the writer paper:
    the full S1 to S7 and S9 suites are this step's own modules and
    are not re-run here."""

    def test_operations_and_reports_complete_with_no_guide_call(self):
        """Pins plan Section 1.3 S8, guide off completeness over the
        operations driven here. Oracle: IM2-INV-4 as the S8 entry
        states it: registry, audit, import, and probe report work
        completes with no guide call made, and the first guide call
        afterwards is the act that appends the first guide_record,
        raising the entry count by exactly one."""
        record = audit_page(self.home, PAGE_STRONG)
        name_round(self.home, "round-1")
        import_answer(self.home, "round-1", ANSWER_NAMED_CITED)
        report = service.probe_report(
            home=str(self.home), product=PRODUCT, round="round-1",
            form="advanced", audit_date=AUDIT_DATE)
        self.assertIn("rates", report if isinstance(report, dict)
                      else vars(report))
        before = field(service.status(home=str(self.home)),
                       "entry_count")
        guide_for_run(self.home, field(record, "run_id"))
        after = field(service.status(home=str(self.home)),
                      "entry_count")
        self.assertEqual(after, before + 1)


class TestGuideTiming(GuideBase):
    """Row S8 timing bound. Oracle: plan Section 1.5 timing bounds,
    CQ-D31: S8, one guide call over a stored record, 5 seconds, a
    plan design value at the stated test scale of one stored
    record."""

    def test_one_guide_call_within_five_seconds(self):
        """Pins plan Section 1.3 S8, timing bound at its stated
        scale. Oracle: plan Section 1.5 timing bounds: one guide
        call over a stored record completes within 5 seconds."""
        record = audit_page(self.home, PAGE_ONE_CITATION)
        start = time.monotonic()
        guide_for_run(self.home, field(record, "run_id"))
        self.assertLess(time.monotonic() - start, 5.0)


class TestControlInteraction(GuideBase):
    """Row S8 guide inputs over controls. Oracle: brief Section 5.8
    IM7-ANA-2 landing: the guide consumes no control as evidence,
    its round triggers compute over the round's non control answers
    only, and no control produces an action."""

    def test_controls_produce_no_action_and_round_triggers_skip_them(self):
        """Pins plan Section 1.3 S8, guide over a round holding only
        a designated control. Oracle: brief Section 5.8 IM7-ANA-2
        landing: a round whose only answer is a designated control
        stands empty for the guide's round triggers, so the three
        round triggers fire on the non control set and no action is
        produced by the control."""
        name_round(self.home, "round-control")
        import_answer(self.home, "round-control", ANSWER_CONTROL_PASS,
                      control_designation="positive")
        draft = guide_for_round(self.home, "round-control")
        self.assertEqual(set(action_codes(draft)), ROUND_TRIGGER_CODES)

    def test_failed_control_suppresses_guide_actions_for_the_round(self):
        """Pins plan Section 1.3 S8, guide suppression on a failed
        control. Oracle: brief Section 5.8 IM7-ANA-2 landing: a
        guide call over a round holding a failed control carries
        the control failure notice and produces no action from that
        round."""
        name_round(self.home, "round-failed-control")
        import_answer(self.home, "round-failed-control",
                      ANSWER_CONTROL_FAIL, control_designation="positive")
        draft = guide_for_round(self.home, "round-failed-control")
        self.assertEqual(field(draft, "actions"), [])


if __name__ == "__main__":
    unittest.main()
