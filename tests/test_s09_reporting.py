"""Slice S9 tests: reporting and the three reading forms.

Written before the product exists. Every test imports the product
package named citeline and calls the operations under the names the
plan states: module reporting for the slice (plan Section 5.3 module
boundary row for S9), the service layer operations of brief Section
5.4, and the shell format act for rendering a standing result in a
second form (brief Section 5.12 invocation to artefact mapping: a
second form of a standing result renders the stored record and does
not re-run the operation). Import or attribute failure is the
expected red state. No stub and no mock of the product stands in
this file. Dates are call inputs in every test; no test reads a date
from a clock.

Every test method docstring names the matrix row it pins by section
qualified identifier and the oracle passage. Trade T-7 settled key (register R1-050): the Agentic envelope key
stands settled as report, the key the plan Agentic shape statement
names for the report payload; this module, the owned side of the
forms, pins that key, and the S3 side conforms to it. Status
dependent limbs
stand blocked and stand filed in blocked-w6.md, not written here:
the failed and warned ordering limb on CL-16 at B1, its top adverse
reasons selection limb on CL-16 and L-CC-6 together, AuditRun
facts_counts on L-CC-4, the html_variant_claim presentation on
L-CC-5, and the IM7-BRK-11 severed Simple classification limb on
CL-13 at K-13 inside B2.
"""

import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path

from citeline import reporting, service, shell, watch
from citeline import install as install_module

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
CANONICAL = "Example Product answers questions with citations."
PRODUCT = "Example Product"
QUERY = "What is Example Product?"

PAGE_STRONG = FIXTURES / "w6-page-strong.md"
PAGE_HOSTILE = FIXTURES / "w6-page-hostile.md"
PAGE_FALLBACK = FIXTURES / "w6-page-fallback.md"
PAGE_PREFERENCE = FIXTURES / "w6-page-preference.md"
PAGE_NO_EVIDENCE = FIXTURES / "w6-page-no-evidence.md"
PAGE_ONE_CITATION = FIXTURES / "w6-page-one-citation.md"
ROBOTS_A = FIXTURES / "w6-robots-a.txt"
ROBOTS_B = FIXTURES / "w6-robots-b.txt"
ANSWER_NAMED_CITED = FIXTURES / "w6-answer-named-cited.txt"
ANSWER_NAMED = FIXTURES / "w6-answer-named.txt"
ANSWER_PLAIN = FIXTURES / "w6-answer-plain.txt"
ANSWER_CONTROL_PASS = FIXTURES / "w6-answer-control-pass.txt"
ANSWER_CONTROL_FAIL = FIXTURES / "w6-answer-control-fail.txt"
WATCHPLAN = FIXTURES / "w6-watchplan-picked.json"

HONESTY = ("This score is a signal index. It measures the presence "
           "of citability signals. It is not validated as a "
           "predictor of citation, and it does not verify truth.")
ANCHOR_LIMIT = ("Verify proves internal consistency only. A writer "
                "who replaces the whole product home can replace "
                "the chain with it. Record the head hash outside "
                "the product home.")
REFUSAL_SENTENCE = ("The guide drafts no opening for this page, "
                    "because no reusable evidence stands on it.")
CITATION_ONLY_SENTENCE = ("This page carries citations and no "
                          "quotable evidence sentence, so the draft "
                          "opening is the canonical line alone.")
FALLBACK_STATEMENT = "The evidence sentence does not name the product."
PREFERENCE_STATEMENT = ("The draft opening uses the first quotable "
                        "sentence that names the product, an alias, "
                        "or a category term. It was chosen by naming "
                        "only, and what it states is the page's own "
                        "statement.")
LABEL_CAP_FIRST = ("First: actions on citations, statistics, or "
                   "quotations, while the evidence cap holds the "
                   "score at 39. This is an order of work, not a "
                   "promised result.")
LABEL_SCORE_CHECK = ("Next: actions on the checks that earn the "
                     "score, where the evidence cap does not hold. "
                     "This is an order of work, not a promised "
                     "result.")
LABEL_DEFECT = ("Separate: actions on a defect that is not a score "
                "matter. This is an order of work, not a promised "
                "result.")
SCOPE_VALUE = "signal_presence_only"
FORMS = ("simple", "advanced", "agentic")


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def as_text(artefact):
    if isinstance(artefact, str):
        return artefact
    return json.dumps(artefact, sort_keys=True)


def payload(artefact):
    """The report payload of an artefact: itself for Advanced, the
    object under the one named report key for Agentic."""
    if isinstance(artefact, dict) and "report" in artefact:
        return artefact["report"]
    return artefact


def walk_objects(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from walk_objects(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_objects(value)


def find_rates(artefact):
    for obj in walk_objects(payload(artefact)):
        if {"named", "named_early", "cited"} <= set(obj):
            return obj
    raise AssertionError("no authoritative rates object stands")


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def seed_product(home, queries=None):
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
    # Step 16 reconciliation under D-17: where the caller names
    # no query set, the seed registers the file query as the
    # product query set through the governed set_query_set
    # route before any probe import, so the imported query
    # stands in the product query set already, as brief item
    # 132 and the adapter contract order. A caller naming a
    # query set stands unchanged. No assertion in this file
    # changes.
    if queries is None:
        queries = [QUERY]
    service.set_query_set(
        home=str(home), product=PRODUCT, query_set=queries,
        audit_date=AUDIT_DATE)


def audit_page(home, page, **extra):
    return service.audit(
        home=str(home), page_file=str(page), audit_date=AUDIT_DATE,
        **extra)


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


def probe_report(home, label, form):
    return service.probe_report(
        home=str(home), product=PRODUCT, round=label, form=form,
        audit_date=AUDIT_DATE)


def render(record, form):
    return shell.format_record(record, form=form)


class ReportingBase(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)
        seed_product(self.home)

    def seed_audit(self, page=PAGE_STRONG, **extra):
        extra.setdefault("robots_file", str(ROBOTS_A))
        return audit_page(self.home, page, **extra)

    def seed_context_round(self, label="round-1"):
        """Three answers standing in two distinct engines, three
        distinct capture dates, and two distinct capture methods,
        hand counted from the import calls below."""
        name_round(self.home, label)
        import_answer(self.home, label, ANSWER_NAMED_CITED,
                      captured_on="2026-11-10", engine="engine-a",
                      method="manual copy")
        import_answer(self.home, label, ANSWER_NAMED,
                      captured_on="2026-11-11", engine="engine-b",
                      method="manual copy")
        import_answer(self.home, label, ANSWER_PLAIN,
                      captured_on="2026-11-12", engine="engine-a",
                      method="export file")
        return label


class TestCrossFormEquality(ReportingBase):
    """Row S9 cross form equality on values. Oracle: brief Section
    5.5 per form conformance checks and plan Section 1.3 S9: cross
    form equality on values across Simple, Advanced, and Agentic
    forms from one canonical record; plan contract N3, rendering
    stands as a pure transformation of one stored report."""

    def test_audit_values_equal_across_the_three_forms(self):
        """Pins plan Section 1.3 S9, cross form equality, audit
        values. Oracle: brief Section 5.5 Simple conformance check:
        the page path value matches the Advanced artefact value for
        audit and robots, compared as values and not as escaped
        renderings, and the audit artefact identifier lines match
        the Advanced values; brief Section 5.5 Agentic conformance:
        cross form equality holds on shared fields against the
        Advanced artefact for the same run."""
        record = self.seed_audit()
        advanced = render(record, "advanced")
        agentic = payload(render(record, "agentic"))
        simple = render(record, "simple")
        for name in ("run_id", "snapshot_id", "evaluated_page_path",
                     "path_defaulted", "audit_date"):
            self.assertEqual(field(advanced, name), field(agentic, name))
        self.assertEqual(field(field(advanced, "score"), "value"),
                         field(field(agentic, "score"), "value"))
        self.assertEqual(field(field(advanced, "score"), "band"),
                         field(field(agentic, "score"), "band"))
        self.assertIn(field(record, "run_id"), simple)
        self.assertIn(field(record, "snapshot_id"), simple)
        self.assertIn(str(field(field(advanced, "score"), "value")),
                      simple)

    def test_probe_rates_equal_across_the_three_forms(self):
        """Pins plan Section 1.3 S9, cross form equality, probe
        values. Oracle: brief Section 5.5: Advanced holds exactly
        one authoritative rates object, Agentic holds no number
        Advanced does not hold (item 122), and Simple states each
        rate with the number of answers, its numeric Wilson
        interval as a plain range in percent, its tier, and its
        warning on the same unit, so the values stand equal across
        forms in each form's rendering."""
        label = self.seed_context_round()
        advanced_rates = find_rates(probe_report(self.home, label,
                                                 "advanced"))
        agentic_rates = find_rates(probe_report(self.home, label,
                                                "agentic"))
        self.assertEqual(advanced_rates, agentic_rates)
        simple = probe_report(self.home, label, "simple")
        named = advanced_rates["named"]
        self.assertIn(str(named["n"]), simple)
        self.assertIn(named["tier"], simple)
        low_pct = round(named["wilson_low"] * 100)
        high_pct = round(named["wilson_high"] * 100)
        range_forms = (f"{low_pct} to {high_pct}",
                       f"{low_pct}-{high_pct}",
                       f"{low_pct}% to {high_pct}%",
                       f"{low_pct} percent to {high_pct} percent")
        self.assertTrue(any(r in simple for r in range_forms),
                        "interval as a plain range in percent")
        if named["tier"] in ("provisional", "small sample"):
            self.assertIn(
                "Small sample warning: this rate may change as "
                "more answers are added.", simple)

    def test_reporting_pipeline_and_shell_format_agree(self):
        """Pins plan Section 1.3 S9, rendering as one pipeline.
        Oracle: plan slice S9 entry: reporting owns rendering as
        one pipeline, and brief Section 5.4: the shell formats the
        record the service layer returns and holds no rule of its
        own, so the artefact the reporting pipeline renders and
        the artefact the shell formats stand equal for one stored
        record in one form."""
        record = self.seed_audit()
        self.assertEqual(as_text(reporting.render(record,
                                                  form="advanced")),
                         as_text(render(record, "advanced")))

    def test_guide_values_equal_across_the_three_forms(self):
        """Pins plan Section 1.3 S9, cross form equality, guide
        values. Oracle: brief Section 5.5 Advanced artefact list:
        for guide, the GuideDraft in full; the Simple guide
        artefact carries the same draft opening or refusal and the
        same actions in plain words."""
        record = audit_page(self.home, PAGE_ONE_CITATION)
        draft = service.guide(home=str(self.home),
                              run_id=field(record, "run_id"),
                              audit_date=AUDIT_DATE)
        advanced = render(draft, "advanced")
        agentic = payload(render(draft, "agentic"))
        simple = render(draft, "simple")
        self.assertEqual(field(advanced, "opening_text"),
                         field(agentic, "opening_text"))
        self.assertEqual(field(advanced, "opening_text"),
                         field(draft, "opening_text"))
        self.assertIn(field(draft, "opening_text"), simple)


class TestCommonCarry(ReportingBase):
    """Row S9 the common carry in every form. Oracle: brief Section
    5.5 common carry and commitments (c) and (e), and plan Section
    1.5 reverse trace table common carry row."""

    def test_honesty_sentence_verbatim_in_every_form(self):
        """Pins plan Section 1.3 S9, common carry, honesty sentence.
        Oracle: brief Section 5.5 item 121: the honesty sentence
        stands fixed once and used in every form, in JSON as a
        field, in text as a line; no form shortens it. Pinned here
        on audit, probe, and robots artefacts."""
        record = self.seed_audit()
        label = self.seed_context_round()
        for form in FORMS:
            self.assertIn(HONESTY, as_text(render(record, form)))
            self.assertIn(HONESTY,
                          as_text(probe_report(self.home, label, form)))
            robots = service.robots(
                home=str(self.home), robots_file=str(ROBOTS_A),
                form=form, audit_date=AUDIT_DATE)
            self.assertIn(HONESTY, as_text(robots))

    def test_anchor_limit_sentence_beside_any_head_hash(self):
        """Pins plan Section 1.3 S9, common carry, anchor limit
        sentence. Oracle: brief Section 5.5 commitment (c): in
        every form, a form that prints a head hash without the
        limit sentence fails its conformance check; verify and
        status responses carry the limit sentence beside the head
        hash field."""
        self.seed_audit()
        for form in FORMS:
            status = service.status(home=str(self.home))
            text = as_text(status)
            self.assertIn(ANCHOR_LIMIT, text)
            heads = [o for o in walk_objects(payload(status))
                     if o.get("head_hash")]
            self.assertTrue(heads)
            verify = service.verify(home=str(self.home))
            if form != "simple":
                for result in (status, verify):
                    holders = [o for o in walk_objects(
                        payload(render(result, form)))
                        if o.get("head_hash")]
                    self.assertTrue(holders)
                    for obj in holders:
                        self.assertIn(
                            ANCHOR_LIMIT,
                            [str(v) for v in obj.values()])
            self.assertIn(ANCHOR_LIMIT, as_text(verify))
            self.assertIn(ANCHOR_LIMIT,
                          as_text(render(status, form)))
            self.assertIn(ANCHOR_LIMIT,
                          as_text(render(verify, form)))

    def test_evaluated_page_path_with_defaulted_companion_default_case(self):
        """Pins plan Section 1.3 S9, common carry, evaluated page
        path with its path defaulted companion, defaulted case.
        Oracle: brief Section 5.5 commitment (e) as amended by
        IM7-BRK-10: every audit output and every robots output, in
        every form, shows the evaluated page path with the value
        the call used, including where the value is the default
        root path, and beside it whether that path was defaulted; a
        defaulted path is shown as the path used, never omitted."""
        record = self.seed_audit()
        self.assertTrue(field(record, "path_defaulted"))
        for form in FORMS:
            artefact = render(record, form)
            self.assertIn(field(record, "evaluated_page_path"),
                          as_text(artefact))
            if form != "simple":
                body = payload(artefact)
                self.assertTrue(field(body, "path_defaulted"))
                self.assertEqual(field(body, "evaluated_page_path"),
                                 field(record, "evaluated_page_path"))
            else:
                lines = artefact.splitlines()
                self.assertTrue(
                    any("defaulted" in line.lower()
                        and "not defaulted" not in line.lower()
                        for line in lines),
                    "Simple companion line states the path was "
                    "defaulted, in a line of its own")
                self.assertNotIn(
                    "not defaulted", artefact.lower(),
                    "no negated companion statement stands in "
                    "the defaulted case, so the word defaulted "
                    "stands here only in its unnegated form")

    def test_evaluated_page_path_with_defaulted_companion_supplied_case(self):
        """Pins plan Section 1.3 S9, common carry, evaluated page
        path with its path defaulted companion, supplied case.
        Oracle: brief Section 5.5 commitment (e): where the call
        supplied the path, the companion stands false and the
        supplied path stands in every form, its stated value in
        Simple matching the Advanced path_defaulted value for the
        same run."""
        record = self.seed_audit(evaluated_page_path="/pricing")
        self.assertFalse(field(record, "path_defaulted"))
        self.assertEqual(field(record, "evaluated_page_path"),
                         "/pricing")
        for form in FORMS:
            artefact = render(record, form)
            self.assertIn("/pricing", as_text(artefact))
            if form != "simple":
                self.assertFalse(
                    field(payload(artefact), "path_defaulted"))
            else:
                lines = artefact.splitlines()
                self.assertTrue(
                    any("not defaulted" in line.lower()
                        or "supplied" in line.lower()
                        for line in lines),
                    "Simple companion line states the path was "
                    "supplied, in a line of its own")
                for line in lines:
                    if "defaulted" in line.lower():
                        self.assertIn(
                            "not defaulted", line.lower(),
                            "no unnegated defaulted statement "
                            "stands in the supplied case")

    def test_version_stamps_and_audit_date_in_every_form(self):
        """Pins plan Section 1.3 S9, common carry, version stamps.
        Oracle: brief Section 5.5 common carry: the version stamps
        and the audit date stand in every form; plan Section 1.5
        reverse trace table: version stamps (ruleset, detector,
        registry, query set) and audit date render from the stamps
        and date stored on the record the form renders, equal as
        values across forms."""
        record = self.seed_audit()
        advanced = payload(render(record, "advanced"))
        agentic = payload(render(record, "agentic"))
        simple = render(record, "simple")
        stamp_values = []
        for name in ("ruleset_version", "detector_version",
                     "registry_version", "query_set_version"):
            found = [o[name] for o in walk_objects(advanced)
                     if name in o]
            self.assertTrue(found, name)
            stamp_values.append((name, found[0]))
        for key, value in stamp_values:
            found = [o for o in walk_objects(agentic)
                     if o.get(key) == value]
            self.assertTrue(found, key)
            self.assertIn(str(value), simple)
        self.assertEqual(field(advanced, "audit_date"), AUDIT_DATE)
        self.assertIn(AUDIT_DATE, simple)


class TestRenderingSafety(ReportingBase):
    """Row S9 rendering safety over the hostile corpus. Oracle: plan
    Section 1.3 S9 and IM2-BRK-20: rendering as one pipeline with
    escaping by field type, field classification stated with the
    types, escaping applied at the pipeline's one point, per form.
    The hostile material stands shared in fixtures/w6-page-hostile.md
    and stands catalogued in catalogue-w6.md."""

    HOSTILE_BITS = ('<script>alert("x")</script>',
                    "<img src=x onerror=alert(1)>",
                    "javascript:alert(1)")

    def test_hostile_text_renders_as_text_in_simple(self):
        """Pins plan Section 1.3 S9, rendering safety, Simple limb.
        Oracle: IM2-BRK-20 as the S9 entry states it: hostile page
        material renders in the Simple prose artefact as plain text
        characters, and the artefact contains no JSON object syntax
        (brief Section 5.5 Simple distinguishing criteria)."""
        record = audit_page(self.home, PAGE_HOSTILE)
        simple = render(record, "simple")
        for bit in self.HOSTILE_BITS:
            self.assertIn(bit, simple)
        self.assertNotIn('{"', simple)

    def test_hostile_values_round_trip_exactly_in_json_forms(self):
        """Pins plan Section 1.3 S9, rendering safety, JSON limbs.
        Oracle: IM2-BRK-20: escaping by field type at the pipeline's
        one point means a text field's stored value stands exact in
        the JSON forms, neither stripped nor entity encoded a
        second time; parsing the Agentic response as exactly one
        JSON value (brief Section 5.5 Agentic conformance) yields
        the same values as the Advanced artefact."""
        record = audit_page(self.home, PAGE_HOSTILE)
        advanced_text = as_text(render(record, "advanced"))
        self.assertNotIn("&lt;script&gt;", advanced_text)
        agentic_raw = render(record, "agentic")
        reparsed = json.loads(json.dumps(agentic_raw))
        self.assertEqual(payload(reparsed), payload(agentic_raw))
        joined = advanced_text
        self.assertIn("café", joined)
        self.assertIn("a=1&b=2", joined)
        stored_texts = []
        for obj in walk_objects(record if isinstance(
                record, dict) else vars(record)):
            for value in obj.values():
                if isinstance(value, str):
                    stored_texts.append(value)
        hostile_stored = [v for v in stored_texts
                          if any(bit in v for bit in
                                 self.HOSTILE_BITS) or "café" in v]
        self.assertTrue(hostile_stored)
        for form in ("advanced", "agentic"):
            body = payload(render(record, form))
            rendered_texts = []
            for obj in walk_objects(body):
                for value in obj.values():
                    if isinstance(value, str):
                        rendered_texts.append(value)
            for value in hostile_stored:
                self.assertIn(value, rendered_texts)

    def test_field_types_hold_their_form_in_json(self):
        """Pins plan Section 1.3 S9, rendering safety, field
        classification limb as behaviour. Oracle: IM2-BRK-20: field
        classification stated with the types; a numeric field
        renders as a number in the JSON forms, a code field renders
        verbatim as a string, and a text field renders as a string,
        in both JSON forms."""
        record = self.seed_audit()
        for form in ("advanced", "agentic"):
            body = payload(render(record, form))
            score = field(body, "score")
            self.assertIsInstance(field(score, "value"),
                                  (int, float))
            self.assertIsInstance(field(score, "band"), str)
            self.assertEqual(field(score, "claim_type"), SCOPE_VALUE)
            self.assertIs(field(score, "validated_predictor"), False)


class TestReverseTrace(ReportingBase):
    """Row S9 the reverse trace discipline. Oracle: plan Section
    1.5 reverse trace table, field by field (IM2-INV-1): every
    shipped report field maps to a stored record and journal kind,
    or to the one permitted rendering derivation; a field fillable
    only by computing a new number at render time fails the table
    at once, on contract 5.

    Shared material set (plan Section 1.5, IM2-DIV-6), stated once
    here on the passage's own terms: one registered product
    (product_id p-example in the trace material, a trace
    identifier and not a shipped record; the seeded product below
    stands as that product in this module), one supplied page
    file (w6-page-strong.md) and its PageSnapshot, one supplied
    robots file (w6-robots-a.txt), and one imported round of
    supplied answer files over that product. The trace tests in
    this class run over that set, including its imported round.

    Named gaps carried visibly through every later stage that
    would have consumed them: the per check status word stands as
    a named gap at SEAM-STATUS, BLOCKED-ON CL-16, and no status
    word value stands in any rendered form in this class; the
    empty extraction score stands as a named gap at
    SEAM-SCORE-EMPTY, BLOCKED-ON K-20, shown nowhere as a value,
    and no empty extraction score value stands in any rendered
    form in this class. The checks blob comparison is not the
    only treatment of the status word: the gap tests below name
    both gaps by seam and open item and assert their absence as
    values in the audit, guide, and probe stages that would have
    consumed them."""

    TRACE_GAPS = (("SEAM-STATUS", "CL-16"), ("SEAM-SCORE-EMPTY", "K-20"))

    def seed_shared_trace_set(self):
        """The shared material set stated in the class docstring:
        the seeded product, the strong page audit with the robots
        file, and one imported round over that product."""
        record = self.seed_audit()
        label = "round-trace"
        name_round(self.home, label)
        import_answer(self.home, label, ANSWER_NAMED_CITED)
        import_answer(self.home, label, ANSWER_NAMED)
        return record, label

    def test_named_gaps_carry_through_every_later_stage(self):
        """Pins plan Section 1.5, the named gaps at SEAM-STATUS
        (BLOCKED-ON CL-16) and SEAM-SCORE-EMPTY (BLOCKED-ON K-20):
        each gap stands named by seam and open item in this trace
        material, and no status word value and no empty extraction
        score value stands in the audit, guide, or probe artefacts
        rendered over the shared trace set."""
        record, label = self.seed_shared_trace_set()
        artefacts = [render(record, "advanced"),
                     probe_report(self.home, label, "advanced")]
        draft = service.guide(home=str(self.home),
                              run_id=field(record, "run_id"),
                              audit_date=AUDIT_DATE)
        artefacts.append(render(draft, "advanced"))
        for artefact in artefacts:
            for obj in walk_objects(payload(artefact)):
                self.assertNotIn("status_word", obj)
                self.assertNotIn("empty_extraction_score", obj)
                for value in obj.values():
                    self.assertNotEqual(value, "SEAM-STATUS-VALUE")
        for seam, item in self.TRACE_GAPS:
            self.assertIn(seam, type(self).__doc__)
            self.assertIn(item, type(self).__doc__)

    AUDIT_FIELDS = {
        "run_id", "product_id", "snapshot_id", "snapshot_sha256",
        "evaluated_page_path", "path_defaulted", "snapshot_format",
        "checks", "score", "cap_status", "robots_summary",
        "honesty_sentence", "anchor_limit", "audit_date",
        "ruleset_version", "detector_version", "registry_version",
        "query_set_version", "head_hash", "entry_count",
        "methods_note_version", "bounds",
    }

    def test_audit_artefact_fields_all_trace_to_the_record(self):
        """Pins plan Section 1.3 S9, reverse trace discipline, audit
        limb. Oracle: plan Section 1.5 reverse trace table rows for
        score, cap status, per check values, honesty and limit
        sentences, stamps, evaluated page path, and snapshot
        identity: the Advanced audit artefact carries no field
        outside the traced set, and its score, cap status, and per
        check earned values equal the stored AuditRun values, so
        rendering added no number. Cap status stands value
        compared expressly. facts_counts stands named as a
        blocked gap on L-CC-4 and is asserted absent, not admitted
        by name alone."""
        record = self.seed_audit()
        body = payload(render(record, "advanced"))
        traced = {"score", "checks", "evaluated_page_path",
                  "path_defaulted", "audit_date", "run_id",
                  "snapshot_id"}
        self.assertLessEqual(traced, set(body))
        for key in body:
            self.assertIn(key, self.AUDIT_FIELDS, key)
        self.assertEqual(field(body, "score"), field(record, "score"))
        self.assertEqual(field(body, "checks"),
                         field(record, "checks"))
        self.assertEqual(field(field(body, "score"), "cap_status")
                         if isinstance(field(body, "score"), dict)
                         and "cap_status" in field(body, "score")
                         else field(body, "cap_status"),
                         field(field(record, "score"), "cap_status")
                         if isinstance(field(record, "score"), dict)
                         and "cap_status" in field(record, "score")
                         else field(record, "cap_status"))
        for name in ("snapshot_id", "snapshot_sha256",
                     "snapshot_format", "robots_summary",
                     "head_hash", "entry_count",
                     "ruleset_version", "detector_version",
                     "registry_version", "query_set_version",
                     "evaluated_page_path", "path_defaulted",
                     "audit_date"):
            if name in body or (isinstance(record, dict)
                                and name in record) or \
                    hasattr(record, name):
                self.assertEqual(field(body, name),
                                 field(record, name), name)
        self.assertNotIn("facts_counts", body,
                         "facts_counts stands as a blocked gap on "
                         "L-CC-4 in blocked-w6.md entry 6 and no "
                         "untraced field passes by name alone")

    def test_second_render_of_a_standing_result_recomputes_nothing(self):
        """Pins plan Section 1.3 S9, reverse trace discipline,
        re-render limb. Oracle: brief Section 5.12 invocation to
        artefact mapping and plan contract N3: a second form of a
        standing result renders the stored record and does not
        re-run the operation, so two Advanced renders of one record
        stand equal value for value."""
        record = self.seed_audit()
        first = render(record, "advanced")
        second = render(record, "advanced")
        self.assertEqual(as_text(first), as_text(second))

    def test_trace_row_per_query_competitor_alias_breakdowns(self):
        """Pins plan Section 1.5 row: per query, per competitor,
        and per alias breakdowns render from the same RoundMetrics
        computation over the shared trace set round. Hand counted
        over that round's two imported answers, both under the
        one query and both naming the product: per query answer
        count 2 and named count 2; the one competitor, Rival,
        named in no answer, named count 0; the one registered
        alias, Example Prod, matched in no answer, count 0. Each
        breakdown stands asserted at its own named field."""
        record, label = self.seed_shared_trace_set()
        body = payload(probe_report(self.home, label, "advanced"))

        def holder(key):
            for obj in walk_objects(body):
                if key in obj:
                    return obj[key]
            raise AssertionError("no %s stands in the report" % key)

        per_query = holder("per_query")
        self.assertEqual(field(per_query[QUERY], "answer_count"), 2)
        self.assertEqual(field(per_query[QUERY], "named_count"), 2)
        per_competitor = holder("per_competitor")
        self.assertIn("Rival", per_competitor)
        self.assertEqual(field(per_competitor["Rival"],
                               "named_count"), 0)
        per_alias = holder("per_alias_counts")
        self.assertEqual(per_alias["Example Prod"], 0)

    def test_trace_row_cluster_count_effective_n_disclosed(self):
        """Pins plan Section 1.5 row: cluster count, effective n,
        and disclosed cluster figures render from the RoundMetrics
        computation, disclosed only. Hand counted over the shared
        round: its two imported answers stand in no near
        duplicate relation, so two clusters stand, the effective
        n stands at 2, the largest cluster share stands at one
        half, and no cluster stands chained."""
        record, label = self.seed_shared_trace_set()
        body = payload(probe_report(self.home, label, "advanced"))
        metrics = None
        for obj in walk_objects(body):
            if "effective_n" in obj:
                metrics = obj
                break
        self.assertIsNotNone(metrics)
        self.assertEqual(field(metrics, "cluster_count"), 2)
        self.assertEqual(field(metrics, "effective_n"), 2)
        self.assertAlmostEqual(field(metrics,
                                     "largest_cluster_share"),
                               0.5, places=6)
        self.assertEqual(field(metrics, "chained_cluster_count"), 0)

    def test_trace_row_trend_delta_or_series_break(self):
        """Pins plan Section 1.5 row: trend delta or stated series
        break renders from two RoundMetrics computations compared
        under contract C5; a break renders as a break."""
        name_round(self.home, "round-a")
        import_answer(self.home, "round-a", ANSWER_NAMED_CITED)
        name_round(self.home, "round-b")
        import_answer(self.home, "round-b", ANSWER_NAMED)
        trend = service.probe_trend(
            home=str(self.home), product=PRODUCT, round_a="round-a",
            round_b="round-b", form="advanced",
            audit_date=AUDIT_DATE)
        text = as_text(trend).lower()
        self.assertTrue("delta" in text or "break" in text)

    def test_trace_row_robots_report_non_finding_fields(self):
        """Pins plan Section 1.5 row: RobotsReport non finding
        report fields render from the robots evaluation over the
        supplied robots file and the shipped table. Each field
        the row names stands asserted by its exact key, on the
        field names the S4 module states for this report, with
        its value from that evaluation: the snapshot sha256
        computed here from the fixture bytes; the asserted
        capture date standing null, because the standalone
        robots call supplies no asserted capture date and the
        date may stand null only in that absent sense (brief
        item 135); the shipped table at version value 2 and
        snapshot date 2026-11-12; the crawl delay observation
        standing null, because the fixture carries no
        Crawl-delay line; one sitemap line; no line counted in
        the non protocol count, every fixture line standing as
        a group, a rule, or the recognised sitemap line; no
        unknown token, the fixture's one group token standing
        as the wildcard; and the finding count at the table
        size of 25. Superseded at Step 16 under defect E-04:
        the earlier form of this test asserted table_version 1.
        The Step 16 round 2 disposition, ruling on the brief
        Section 5.6 version rule on the S4 seat reading,
        displaces that form: the round 1 fix wave changed the
        evidence label value on four shipped rows and restored
        two stated fields across the shipped rows in one
        published revision, and the rule counts one bump per
        published table revision with no field change exempt,
        so the stamp stands at 2. This form asserts
        table_version 2, with the snapshot date unchanged at
        2026-11-12."""
        robots = service.robots(
            home=str(self.home), robots_file=str(ROBOTS_A),
            form="advanced", audit_date=AUDIT_DATE)
        body = payload(robots)
        self.assertEqual(
            field(body, "robots_snapshot_sha256"),
            hashlib.sha256(ROBOTS_A.read_bytes()).hexdigest())
        self.assertIsNone(
            field(body, "robots_snapshot_asserted_capture_date"))
        self.assertEqual(field(body, "table_version"), 2)
        self.assertEqual(str(field(body, "table_snapshot_date")),
                         "2026-11-12")
        record = self.seed_audit()
        summary = field(record, "robots_summary")
        self.assertTrue(field(body, "robots_ruleset_version"))
        self.assertEqual(field(body, "robots_ruleset_version"),
                         field(summary, "robots_ruleset_version"))
        self.assertIsNone(field(body, "crawl_delay_observation"))
        self.assertEqual(field(body, "sitemap_line_presence_count"),
                         1)
        self.assertEqual(field(body, "non_protocol_line_count"), 0)
        self.assertEqual(field(body, "unknown_token_count"), 0)
        self.assertEqual(field(body, "finding_count"), 25)

    def test_trace_row_robots_next_refresh_due_date_value(self):
        """Pins plan Section 1.5 row: RobotsReport
        next_refresh_due_date as a checked value, 2027-02-10 in
        the window between ship and the first post ship refresh,
        as the plan states the field."""
        robots = service.robots(
            home=str(self.home), robots_file=str(ROBOTS_A),
            form="advanced", audit_date=AUDIT_DATE)
        self.assertIn("2027-02-10", as_text(robots))

    def test_trace_row_rates_intervals_warnings_to_round_metrics(self):
        """Pins plan Section 1.5 row: rates intervals and warnings
        trace to the RoundMetrics computation over the round's
        answer_imported entries and the registry fold. Hand
        computed over the shared round's computation inputs, its
        two imported answers: both name the product, so the
        named rate stands at 1.0 over an n of 2; the two answers
        stand in two clusters, so the effective n the interval
        and tier run on stands at 2; the Wilson interval at rate
        1.0 and effective n 2, z of 1.96 clamped to 0 to 1,
        stands at 0.3424 to 1.0; the tier at effective n 2
        stands at count only, under 5; and the small sample
        warning stands as the fixed text the brief states."""
        record, label = self.seed_shared_trace_set()
        rates = find_rates(probe_report(self.home, label, "advanced"))
        named = rates["named"]
        self.assertEqual(field(named, "rate"), 1.0)
        self.assertEqual(field(named, "n"), 2)
        self.assertAlmostEqual(field(named, "wilson_low"), 0.3424,
                               places=4)
        self.assertEqual(field(named, "wilson_high"), 1.0)
        self.assertEqual(field(named, "tier"), "count only")
        self.assertEqual(
            field(named, "small_sample_warning"),
            "Small sample warning: this rate may change as "
            "more answers are added.")

    def test_trace_row_head_hash_and_entry_count_to_journal_fold(self):
        """Pins plan Section 1.5 row: head hash and entry count
        trace to the journal fold over the home the report
        reads."""
        record = self.seed_audit()
        body = payload(render(record, "advanced"))
        status = service.status(home=str(self.home))
        if "head_hash" in body:
            self.assertEqual(field(body, "head_hash"),
                             field(status, "head_hash"))
        if "entry_count" in body:
            self.assertEqual(field(body, "entry_count"),
                             field(status, "entry_count"))

    def test_trace_row_snapshot_identity_beside_page_score(self):
        """Pins plan Section 1.5 row: snapshot identity (sha256
        and format) travels beside a page score as values from
        the PageSnapshot and AuditRun records."""
        record = self.seed_audit()
        body = payload(render(record, "advanced"))
        self.assertEqual(field(body, "snapshot_sha256"),
                         field(record, "snapshot_sha256"))
        self.assertEqual(field(body, "snapshot_format"),
                         field(record, "snapshot_format"))
        self.assertIn("score", body)

    def test_trace_row_robots_findings_against_stored_summary(self):
        """Pins plan Section 1.5 row: robots findings in a report
        stand against the robots_summary stored inside the
        AuditRun record."""
        record = self.seed_audit()
        body = payload(render(record, "advanced"))
        self.assertEqual(field(body, "robots_summary"),
                         field(record, "robots_summary"))

    def test_guide_artefact_traces_to_the_guide_record(self):
        """Pins plan Section 1.3 S9, reverse trace discipline, guide
        limb. Oracle: plan Section 1.5 reverse trace table: guide
        actions, opening text, and refusal state render from the
        GuideDraft record (journal kind guide_record) the guide
        call stored, and from nothing else. The guide call here
        drafts from the shared material set's own stored audit
        record, the audit stage of seed_shared_trace_set, so
        this limb runs over the shared set like the rest of
        this class."""
        record, label = self.seed_shared_trace_set()
        draft = service.guide(home=str(self.home),
                              run_id=field(record, "run_id"),
                              audit_date=AUDIT_DATE)
        body = payload(render(draft, "advanced"))
        self.assertEqual(field(body, "opening_text"),
                         field(draft, "opening_text"))
        self.assertEqual(field(body, "refused"),
                         field(draft, "refused"))
        self.assertEqual(field(body, "actions"),
                         field(draft, "actions"))
        self.assertEqual(field(body, "standing_action"),
                         "ACT_THIRD_PARTY")


class TestDetachedArtefactConformance(ReportingBase):
    """Row S9 detached artefact conformance. Oracle: plan Section
    1.3 S9 and IM2-INV-2: fields that must survive detachment,
    listed per artefact. The per artefact list stands carried by
    name in the plan closing list (the detached artefact field
    list, owner the Step 13 test designer, due at Step 13 before
    the S9 closure), and this family stands on that carry: the
    lists stated in this class are that carry as this writer
    states it, per artefact, from the Section 5.1 shapes."""

    AUDIT_DETACHED = ("run_id", "product_id", "snapshot_id",
                      "snapshot_sha256", "snapshot_format",
                      "evaluated_page_path", "path_defaulted",
                      "checks", "score", "robots_summary",
                      "ruleset_version", "detector_version",
                      "registry_version", "query_set_version",
                      "audit_date", "audit_date_is_run_date",
                      "limits_in_force")
    GUIDE_DETACHED = ("provenance", "product_id", "opening_text",
                      "refused", "refusal_code", "actions",
                      "standing_action")
    GUIDE_DETACHED_ANY_OF = (("source_run_id", "source_round_id"),)
    GUIDE_DETACHED_STAMPS = ("ruleset_version", "detector_version",
                             "registry_version", "query_set_version",
                             "audit_date")
    QUERYSET_DETACHED = ("product_id", "query_set_version",
                         "marker_list_version", "total_count",
                         "interrogative_count", "comparison_count",
                         "named_product_count", "bare_topic_count",
                         "duplicate_count", "naming_none_count")
    WATCHRUN_DETACHED = ("home_path", "scope", "plan_file_sha256",
                         "audit_date", "entries", "outcome_counts",
                         "channel_outcome_counts",
                         "trend_no_pair_count", "coverage_statement",
                         "freshness_view", "capacity_projection",
                         "honesty_sentence")
    PROBETREND_DETACHED = ("round_a", "round_b",
                           "series_break_marker", "delta",
                           "composition_changed_note",
                           "asserted_capture_method_sets",
                           "normalised_capture_method_sets")
    ROBOTSPREVIEW_DETACHED = (
        "first_sha256", "second_sha256", "first_capture_date",
        "second_capture_date", "evaluated_page_path",
        "path_defaulted", "table_version", "table_snapshot_date",
        "robots_ruleset_version", "finding_counts", "changed_rows")

    def detach(self, artefact):
        path = Path(self.enterContext(
            tempfile.TemporaryDirectory())) / "detached.json"
        path.write_text(json.dumps(payload(artefact)),
                        encoding="utf-8")
        return json.loads(path.read_text(encoding="utf-8"))

    def test_audit_report_fields_survive_detachment(self):
        """Pins plan Section 1.3 S9, detached artefact conformance,
        audit report. Oracle: the closing list carry named in the
        class docstring, with the field list from the AuditRun
        shape at plan Section 5.1: the listed fields stand present
        with equal values in a copy of the artefact held outside
        the product home."""
        record = self.seed_audit()
        body = payload(render(record, "advanced"))
        detached = self.detach(body)
        for name in self.AUDIT_DETACHED:
            self.assertIn(name, detached)
            self.assertEqual(detached[name], field(body, name))

    def test_guide_draft_fields_survive_detachment(self):
        """Pins plan Section 1.3 S9, detached artefact conformance,
        guide draft. Oracle: the closing list carry named in the
        class docstring, with the field list from the GuideDraft
        shape at plan Section 5.1."""
        record = audit_page(self.home, PAGE_ONE_CITATION)
        draft = service.guide(home=str(self.home),
                              run_id=field(record, "run_id"),
                              audit_date=AUDIT_DATE)
        body = payload(render(draft, "advanced"))
        detached = self.detach(body)
        for name in self.GUIDE_DETACHED:
            self.assertIn(name, detached)
            self.assertEqual(detached[name], field(body, name))
        present_source = [n for pair in self.GUIDE_DETACHED_ANY_OF
                          for n in pair if n in detached]
        self.assertEqual(len(present_source), 1)
        for name in self.GUIDE_DETACHED_STAMPS:
            if name in body:
                self.assertIn(name, detached)

    def test_watch_run_fields_survive_detachment(self):
        """Pins plan Section 1.3 S9, detached artefact conformance,
        WatchRun. Oracle: the closing list carry named in the class
        docstring, with the field list from the WatchRun shape at
        plan Section 5.1: home path, scope as run, plan file
        sha256, audit date as run, per target entries, and the
        counts of each outcome stand present with equal values in
        a copy held outside the product home. The one per target
        entry stands asserted against the record the invoked
        audit stored for that target: its outcome stands
        completed and its stored record identity stands read
        back as the source run of a guide draft over it."""
        data = json.loads(WATCHPLAN.read_text(encoding="utf-8"))
        data["home"] = str(self.home)
        data["targets"][0]["page_file"] = str(PAGE_STRONG)
        plan_path = Path(self.enterContext(
            tempfile.TemporaryDirectory())) / "plan.json"
        plan_path.write_text(json.dumps(data), encoding="utf-8")
        run = watch.run_watch(plan_file=str(plan_path))
        self.assertEqual(
            field(run, "plan_file_sha256"),
            hashlib.sha256(plan_path.read_bytes()).hexdigest())
        entries = field(run, "entries")
        self.assertTrue(entries)
        counts = field(run, "outcome_counts")
        tallied = {}
        for entry in entries:
            outcome = field(entry, "outcome")
            tallied[outcome] = tallied.get(outcome, 0) + 1
        for outcome, total in tallied.items():
            value = counts[outcome] if isinstance(counts, dict) \
                else field(counts, outcome)
            self.assertEqual(value, total, outcome)
        entry = entries[0]
        self.assertEqual(field(entry, "outcome"), "completed")
        identity = field(entry, "record_identity")
        self.assertTrue(identity)
        draft = service.guide(home=str(self.home), run_id=identity,
                              audit_date=AUDIT_DATE)
        self.assertEqual(field(draft, "source_run_id"), identity,
                         "the entry's stored record identity is "
                         "the AuditRun the watch audit target "
                         "stored, read back by the guide call "
                         "over that same identity")
        detached = self.detach(run)
        for name in self.WATCHRUN_DETACHED:
            self.assertIn(name, detached)
            self.assertEqual(detached[name], field(run, name))

    def test_probe_trend_fields_survive_detachment(self):
        """Pins plan Section 1.3 S9, detached artefact conformance,
        ProbeTrend. Oracle: the closing list carry named in the
        class docstring, with the field list from the ProbeTrend
        shape at plan Section 5.1, stated in full in
        PROBETREND_DETACHED: the per round fields of a probe
        report for each of the two rounds, a series break
        marker, and the trend level outputs the shape states,
        the delta, the composition changed note, and the
        asserted and normalised capture method sets of both
        rounds, stand present with equal values in a copy held
        outside the product home."""
        name_round(self.home, "round-a")
        import_answer(self.home, "round-a", ANSWER_NAMED_CITED)
        name_round(self.home, "round-b")
        import_answer(self.home, "round-b", ANSWER_NAMED_CITED)
        trend = service.probe_trend(
            home=str(self.home), product=PRODUCT, round_a="round-a",
            round_b="round-b", form="advanced",
            audit_date=AUDIT_DATE)
        detached = self.detach(trend)
        self.assertEqual(detached, payload(trend))
        self.assertEqual(detached["round_a"], "round-a")
        self.assertEqual(detached["round_b"], "round-b")
        keys = set()
        for obj in walk_objects(detached):
            keys |= set(obj)
        for name in self.PROBETREND_DETACHED:
            self.assertTrue(name in detached or name in keys,
                            name)

    def test_query_set_report_fields_survive_detachment(self):
        """Pins plan Section 1.3 S9, detached artefact conformance,
        QuerySetReport. Oracle: the closing list carry named in the
        class docstring, with the field list from the
        QuerySetReport shape at plan Section 5.1."""
        seed_product(self.home, queries=[QUERY])
        report = service.query_set_report(
            home=str(self.home), product=PRODUCT, form="advanced",
            audit_date=AUDIT_DATE)
        body = payload(report)
        detached = self.detach(body)
        for name in self.QUERYSET_DETACHED:
            self.assertIn(name, detached)
            self.assertEqual(detached[name], field(body, name))


    def test_robots_preview_fields_survive_detachment(self):
        """Pins plan Section 1.3 S9, detached artefact conformance,
        RobotsPreview. Oracle: the closing list carry named in the
        class docstring, with the per artefact list stated in
        ROBOTSPREVIEW_DETACHED from the Section 5.1 RobotsPreview
        shape: both files sha256 values, capture dates or their
        stated omission, evaluated page path with path_defaulted,
        table version and snapshot date, robots_ruleset_version,
        finding counts, and changed rows."""
        preview = service.robots_preview(
            home=str(self.home), first_robots_file=str(ROBOTS_A),
            second_robots_file=str(ROBOTS_B), form="advanced",
            audit_date=AUDIT_DATE)
        body = payload(preview)
        detached = self.detach(body)
        keys = set()
        for obj in walk_objects(detached):
            keys |= set(obj)
        for name in self.ROBOTSPREVIEW_DETACHED:
            self.assertTrue(
                name in keys or name in detached, name)
        for fixture in (ROBOTS_A, ROBOTS_B):
            self.assertIn(hashlib.sha256(
                fixture.read_bytes()).hexdigest(),
                as_text(detached))


class TestReportingBounds(ReportingBase):
    """Row S9 the reporting bounds discipline. Oracle: plan Section
    1.3 slice S9 reporting bounds passage: every report artefact
    carries a bounds section in the same form in every reading
    form, standing beside the figures it bounds and duplicating no
    figure, stating two lists of equal standing, what this run
    establishes and what it does not establish."""

    def bounds_of(self, artefact):
        for obj in walk_objects(payload(artefact)):
            if "establishes" in obj and "does_not_establish" in obj:
                return obj
        raise AssertionError("no bounds section stands")

    def test_bounds_section_in_the_same_form_in_every_form(self):
        """Pins plan Section 1.3 S9, reporting bounds, same form
        limb. Oracle: plan slice S9 bounds passage: the bounds
        section stands in the same form in every reading form, on
        audit and probe artefacts alike, carrying its two lists in
        each form."""
        record = self.seed_audit()
        label = self.seed_context_round()
        for form in FORMS:
            for artefact in (render(record, form),
                             probe_report(self.home, label, form)):
                if form == "simple":
                    self.assertIn("establish", artefact)
                    low = artefact.lower()
                    self.assertIn("does not establish", low)
                    self.assertTrue(
                        artefact.index("establish") <
                        len(artefact),
                        "both lists stand in words in Simple")
                else:
                    bounds = self.bounds_of(artefact)
                    self.assertIsInstance(bounds["establishes"], list)
                    self.assertIsInstance(
                        bounds["does_not_establish"], list)

    def test_bounds_two_lists_of_equal_standing(self):
        """Pins plan Section 1.3 S9, reporting bounds, equal
        standing limb. Oracle: plan slice S9 bounds passage: the
        section states two lists of equal standing; in the JSON
        forms both stand as lists at the same level of the one
        bounds object, neither nested inside the other, and both
        stand non-empty."""
        record = self.seed_audit()
        for form in ("advanced", "agentic"):
            bounds = self.bounds_of(render(record, form))
            self.assertTrue(bounds["establishes"])
            self.assertTrue(bounds["does_not_establish"])
            self.assertNotIn("establishes",
                             json.dumps(bounds["does_not_establish"]))
            self.assertNotIn("does_not_establish",
                             json.dumps(bounds["establishes"]))

    def test_third_party_scope_line_in_the_bounds_section_every_form(self):
        """Pins plan Section 1.3 S9, reporting bounds, third party
        scope line. Oracle: plan slice S9 bounds passage and the
        Captain JP ruling carried in memory (third party mentions
        stay out): every report form carries one scope line in its
        bounds section stating that third party mentions stand
        outside version 1 measurement and that no figure in the
        artefact speaks for them; the line carries no third party
        material, ingests nothing, and scores nothing."""
        record = self.seed_audit()
        for form in FORMS:
            artefact = render(record, form)
            if form == "simple":
                low = artefact.lower()
                self.assertIn("third party", low)
                self.assertIn("outside version 1", low)
                self.assertIn("no figure", low)
            else:
                bounds = self.bounds_of(artefact)
                blob = as_text(bounds).lower()
                self.assertIn("third party", blob)
                self.assertIn("outside", blob)
                self.assertIn("no figure", blob)

    def test_presence_only_scope_value_in_the_same_object_as_any_figure(self):
        """Pins plan Section 1.3 S9, reporting bounds, field level
        presence only limb. Oracle: plan slice S9 bounds passage
        and plan Section 5.1 forms passage: in the Agentic form,
        any record object carrying a score, a rate, or a tier also
        carries, in that same record object, the short machine
        readable scope value stating the figure measures the
        presence of citability signals and verifies no truth and
        no provenance."""
        record = self.seed_audit()
        label = self.seed_context_round()
        for artefact in (render(record, "agentic"),
                         probe_report(self.home, label, "agentic")):
            carrying = []
            for obj in walk_objects(payload(artefact)):
                if "claim_type" in obj and "value" in obj:
                    carrying.append(obj)
                elif "wilson_low" in obj and "tier" in obj:
                    carrying.append(obj)
                elif "tier" in obj and ("rate" in obj or "n" in obj):
                    carrying.append(obj)
            self.assertTrue(carrying,
                            "figure objects as the passages name "
                            "them: the ScoreObject, each rate "
                            "entry, each object holding a tier")
            for obj in carrying:
                self.assertIn(SCOPE_VALUE,
                              [str(v) for v in obj.values()])

    def test_capture_context_counts_beside_round_metrics(self):
        """Pins plan Section 1.3 S9, reporting bounds, capture
        context limb. Oracle: plan slice S9 bounds passage and plan
        Section 5.1 RoundMetrics entry: wherever RoundMetrics is
        rendered, the bounds section states the round's capture
        context as counts of distinct engines, distinct capture
        dates, and distinct capture methods, from the stored
        records. The seeded round stands hand counted at two
        engines, three dates, and two methods."""
        label = self.seed_context_round()
        for form in FORMS:
            artefact = probe_report(self.home, label, form)
            if form == "simple":
                self.assertTrue(
                    any(phrase in artefact for phrase in
                        ("2 distinct engines", "engines: 2")),
                    "Simple states 2 distinct engines as a "
                    "labelled statement")
                self.assertTrue(
                    any(phrase in artefact for phrase in
                        ("3 distinct capture dates", "dates: 3")),
                    "Simple states 3 distinct capture dates as "
                    "a labelled statement")
                self.assertTrue(
                    any(phrase in artefact for phrase in
                        ("2 distinct capture methods",
                         "methods: 2")),
                    "Simple states 2 distinct capture methods "
                    "as a labelled statement")
            else:
                context = None
                for obj in walk_objects(payload(artefact)):
                    keys = set(obj)
                    if any("engine" in k for k in keys) and \
                            any("method" in k for k in keys):
                        context = obj
                self.assertIsNotNone(context)
                by_axis = {}
                for key, value in context.items():
                    if isinstance(value, int):
                        if "engine" in key:
                            by_axis["engine"] = value
                        elif "date" in key:
                            by_axis["date"] = value
                        elif "method" in key:
                            by_axis["method"] = value
                self.assertEqual(by_axis.get("engine"), 2)
                self.assertEqual(by_axis.get("date"), 3)
                self.assertEqual(by_axis.get("method"), 2)

    def test_methods_note_attachment_names_the_version_only(self):
        """Pins plan Section 1.3 S9, reporting bounds, methods note
        attachment limb. Oracle: brief Section 5.5 item 125: the
        methods note is one product level artefact, versioned on
        its own, and every Advanced report names the methods note
        version that governed its run; the note is not a section
        inside every report."""
        record = self.seed_audit()
        label = self.seed_context_round()
        draft_source = audit_page(self.home, PAGE_ONE_CITATION)
        draft = service.guide(home=str(self.home),
                              run_id=field(draft_source, "run_id"),
                              audit_date=AUDIT_DATE)
        bodies = [payload(render(record, "advanced")),
                  payload(probe_report(self.home, label, "advanced")),
                  payload(render(draft, "advanced"))]
        for body in bodies:
            versions = [o["methods_note_version"]
                        for o in walk_objects(body)
                        if "methods_note_version" in o]
            self.assertTrue(versions)
            for obj in walk_objects(body):
                self.assertNotIn("methods_note_text", obj)
                self.assertNotIn("methods_note", obj)

    def test_watch_run_artefact_carries_the_bounds_in_the_same_form(self):
        """Pins plan Section 1.3 S9, reporting bounds, WatchRun
        limb. Oracle: plan slice S9 bounds passage, watch form of
        the same discipline: the WatchRun artefact carries the
        bounds section in this same form, and the WatchRun shape at
        plan Section 5.1 carries the common carry in the form
        rendered."""
        data = json.loads(WATCHPLAN.read_text(encoding="utf-8"))
        data["home"] = str(self.home)
        data["targets"][0]["page_file"] = str(PAGE_STRONG)
        plan_path = Path(self.enterContext(
            tempfile.TemporaryDirectory())) / "plan.json"
        plan_path.write_text(json.dumps(data), encoding="utf-8")
        run = watch.run_watch(plan_file=str(plan_path))
        text = as_text(run)
        self.assertIn("third party", text.lower())
        self.assertIn(HONESTY, text)
        bounds = self.bounds_of(run)
        self.assertIsInstance(bounds["establishes"], list)
        self.assertIsInstance(bounds["does_not_establish"], list)
        self.assertTrue(bounds["establishes"])
        self.assertTrue(bounds["does_not_establish"])
        blob = as_text(bounds).lower()
        self.assertIn("third party", blob)
        self.assertIn("outside", blob)


class TestQuerySetReport(ReportingBase):
    """Row S9 QuerySetReport as an artefact. Oracle: brief Section
    5.12 IM7-DIV-4 landing and plan Section 5.1 QuerySetReport
    entry. Counts below stand hand computed from the seeded query
    set at authoring time: four query strings; interrogative 2
    (the two What forms), comparison 1 (the vs form), named product
    3 (both What forms and the vs form), bare topic 1 (the citation
    tools form), duplicates 1 (the lower case repeat of the first
    string, identical after the stated normalisation), and queries
    naming no product and no competitor 1 (the bare topic form)."""

    QUERIES = ["What is Example Product?",
               "Example Product vs Rival",
               "best citation tools",
               "what is example product?"]

    def setUp(self):
        super().setUp()
        seed_product(self.home, queries=self.QUERIES)

    def report(self, form):
        return service.query_set_report(
            home=str(self.home), product=PRODUCT, form=form,
            audit_date=AUDIT_DATE)

    def test_counts_hand_computed_from_the_query_set(self):
        """Pins plan Section 1.3 S9, QuerySetReport counts. Oracle:
        brief Section 5.12 IM7-DIV-4 landing: the report classifies
        each query string by surface form only under the four
        forms, and reports the count of query strings, a count for
        each form, a duplicate count on the pinned normalisation
        form, and the count of queries naming no product and no
        competitor."""
        expected = {"total_count": 4, "interrogative_count": 2,
                    "comparison_count": 1, "named_product_count": 3,
                    "bare_topic_count": 1, "duplicate_count": 1,
                    "naming_none_count": 1}
        for form in ("advanced", "agentic"):
            body = payload(self.report(form))
            for name, want in expected.items():
                self.assertEqual(field(body, name), want,
                                 "%s in the %s form" % (name, form))
        simple_lines = self.report("simple").splitlines()
        for label, want in (("asks a question", 2), ("compares", 1),
                            ("names the product", 3),
                            ("topic only", 1)):
            self.assertTrue(
                any(label in line and str(want) in line
                    for line in simple_lines),
                "Simple states the count %d beside its plain "
                "label %s" % (want, label))

    def test_identity_fields_and_versions_stand(self):
        """Pins plan Section 1.3 S9, QuerySetReport identity. Oracle:
        plan Section 1.5 reverse trace table: QuerySetReport
        product_id, query_set_version, and marker list version
        render from the Product record the derivation runs over."""
        body = payload(self.report("advanced"))
        self.assertTrue(field(body, "product_id"))
        self.assertTrue(field(body, "query_set_version"))
        self.assertTrue(field(body, "marker_list_version"))

    def test_overlap_and_coverage_statements_in_every_form(self):
        """Pins plan Section 1.3 S9, QuerySetReport statements.
        Oracle: brief Section 5.12 IM7-DIV-4 landing: the overlap
        statement stands in the report in plain words beside the
        counts, in every form; every form states that form
        coverage is a property of the question list, not of
        visibility; the Simple labels are plain words."""
        for form in FORMS:
            text = as_text(self.report(form)).lower()
            self.assertIn("not of visibility", text)
            self.assertIn("more than one", text)
        simple = self.report("simple")
        for label in ("asks a question", "compares",
                      "names the product", "topic only"):
            self.assertIn(label, simple)


class TestRobotsPreview(ReportingBase):
    """Row S9 RobotsPreview as an artefact. Oracle: plan Section
    5.1 RobotsPreview entry in severed form (IM7-DIV-7) and plan
    Part B entry B8: the preview artefact stands in full and
    unstored, with its own field list kept in its own named place
    outside the RobotsReport closure. No stored preview and no
    preview fold stands claimed."""

    PREVIEW_FIELDS = {
        "first_sha256", "second_sha256", "sha256_pair",
        "first_capture_date", "second_capture_date",
        "capture_dates", "evaluated_page_path", "path_defaulted",
        "table_version", "table_snapshot_date",
        "robots_ruleset_version", "finding_counts", "changed_rows",
        "first_finding_count", "second_finding_count",
    }
    ROBOTS_REPORT_ONLY = {"next_refresh_due_date",
                          "crawl_delay_observation",
                          "sitemap_line_presence_count"}

    def preview(self, **extra):
        extra.setdefault("form", "advanced")
        extra.setdefault("audit_date", AUDIT_DATE)
        return service.robots_preview(
            home=str(self.home), first_robots_file=str(ROBOTS_A),
            second_robots_file=str(ROBOTS_B), **extra)

    def test_preview_carries_the_two_file_sha256_pair(self):
        """Pins plan Section 1.3 S9, RobotsPreview sha256 pair.
        Oracle: plan Section 1.5 reverse trace table: the
        RobotsPreview two file sha256 pair renders from the two
        file evaluation over the two supplied robots files; the
        expected hashes stand computed here from the fixture bytes
        with hashlib, never recorded from a run."""
        body = payload(self.preview())
        text = as_text(body)
        for fixture in (ROBOTS_A, ROBOTS_B):
            digest = hashlib.sha256(
                fixture.read_bytes()).hexdigest()
            self.assertIn(digest, text)

    def test_preview_changed_rows_only_and_side_counts(self):
        """Pins plan Section 1.3 S9, RobotsPreview changed row
        selection. Oracle: plan Section 5.1 RobotsPreview entry:
        one entry per changed row only, with token in operator
        spelling, purpose class, finding under each file, and
        defect flag change where one stands; each side's finding
        count stands as the table size by construction, equal on
        both sides here because both files run over the one
        shipped table. The two fixtures differ in exactly one row,
        the Disallow row. That row stands in the wildcard group
        both files state (User-agent: *), so its token stands as
        that group token in operator spelling; the finding under
        each file stands as the rule as written in that file;
        and no purpose class or defect flag change stands on
        it, on the grounds stated in the assertions below."""
        body = payload(self.preview())
        self.assertEqual(field(body, "first_finding_count"), 25)
        self.assertEqual(field(body, "second_finding_count"), 25)
        changed = field(body, "changed_rows")
        self.assertEqual(len(changed), 1)
        row = changed[0]
        self.assertEqual(field(row, "token"), "*")
        self.assertIsNone(
            field(row, "purpose_class"),
            "the changed row stands in the wildcard group, "
            "which supplies every purpose class and no one "
            "class, so its purpose class stands null")
        self.assertEqual(field(row, "first_finding"),
                         "Disallow: /private")
        self.assertEqual(field(row, "second_finding"),
                         "Disallow: /admin")
        self.assertIsNone(
            field(row, "defect_flag_change"),
            "a defect flag change stands only on a search "
            "purpose row under DQ-3, and the wildcard row is "
            "no single purpose row, so no change stands")

    def test_preview_dates_supplied_and_omitted_forms(self):
        """Pins plan Section 1.3 S9, RobotsPreview capture dates.
        Oracle: plan Section 5.1 RobotsPreview entry and trade
        T-11: each file's asserted capture date arrives only as a
        named input of the robots-preview call, one per file, each
        optional; where a date stands supplied it stands carried,
        and where none stands supplied the date field stands
        omitted with the omission stated."""
        with_dates = as_text(self.preview(
            first_capture_date="2026-11-01",
            second_capture_date="2026-11-05"))
        self.assertIn("2026-11-01", with_dates)
        self.assertIn("2026-11-05", with_dates)
        without = as_text(self.preview())
        self.assertNotIn("2026-11-01", without)
        self.assertIn("omit", without.lower())

    def test_preview_path_defaulted_flag_both_ways(self):
        """Pins plan Section 1.3 S9, RobotsPreview path_defaulted.
        Oracle: plan Section 1.5 reverse trace table: the flag
        stands true where the call supplied no path and the root
        default operated and false where it supplied the path; a
        preview stores nothing and holds no AuditRun, so no stored
        record renders this flag."""
        defaulted = payload(self.preview())
        supplied = payload(self.preview(
            evaluated_page_path="/pricing"))
        self.assertTrue(field(defaulted, "path_defaulted"))
        self.assertFalse(field(supplied, "path_defaulted"))
        self.assertEqual(field(supplied, "evaluated_page_path"),
                         "/pricing")

    def test_preview_is_unstored_and_keeps_its_own_field_list(self):
        """Pins plan Section 1.3 S9, RobotsPreview unstored form and
        field list place. Oracle: plan Part B entry B8 and the S9
        entry's separate RobotsPreview closure statement: the
        preview stores nothing, so the journal entry count stands
        unchanged across the call, and the artefact's fields stand
        on its own list, carrying no RobotsReport only field such
        as next_refresh_due_date. Superseded at Step 16 under
        defect E-04, on its literal table_version assertion only:
        the earlier form of this test asserted table_version 1.
        The Step 16 round 2 disposition, ruling on the brief
        Section 5.6 version rule on the S4 seat reading,
        displaces that form: the round 1 fix wave changed the
        evidence label value on four shipped rows and restored
        two stated fields across the shipped rows in one
        published revision, and the rule counts one bump per
        published table revision with no field change exempt,
        so the stamp stands at 2. This form asserts
        table_version 2, with the snapshot date unchanged at
        2026-11-12. The assertion below binding the preview
        table_version to the shipped report table_version stands
        unamended and passes at 2."""
        before = field(service.status(home=str(self.home)),
                       "entry_count")
        body = payload(self.preview())
        after = field(service.status(home=str(self.home)),
                      "entry_count")
        self.assertEqual(before, after)
        keys = set()
        for obj in walk_objects(body):
            keys |= set(obj)
        self.assertFalse(keys & self.ROBOTS_REPORT_ONLY)
        for name in self.PREVIEW_FIELDS:
            self.assertTrue(name in keys or name in body, name)
        self.assertEqual(field(body, "table_version"), 2)
        self.assertEqual(str(field(body, "table_snapshot_date")),
                         "2026-11-12")
        shipped = payload(service.robots(
            home=str(self.home), robots_file=str(ROBOTS_A),
            form="advanced", audit_date=AUDIT_DATE))
        self.assertEqual(field(body, "table_version"),
                         field(shipped, "table_version"))
        self.assertEqual(str(field(body, "table_snapshot_date")),
                         str(field(shipped, "table_snapshot_date")))
        self.assertEqual(field(body, "robots_ruleset_version"),
                         field(shipped, "robots_ruleset_version"))


class TestControlFailureNotice(ReportingBase):
    """Row S9 notice N-L1-2. Oracle: brief Section 5.8 IM7-ANA-2
    landing, on the K-08 cure, carried at the S9 entry: the control
    failure notice stands outside the warning vocabulary entirely;
    it is not a warning kind, it stands in no warning list this
    slice renders, and no reading form presents it as a warning; it
    stands in a report only in its own notice form."""

    def seed_control_round(self, label, answer, designation="positive"):
        name_round(self.home, label)
        import_answer(self.home, label, answer,
                      control_designation=designation)
        return label

    def warning_entries(self, artefact):
        entries = []
        if isinstance(artefact, str):
            for line in artefact.splitlines():
                if "warning" in line.lower():
                    entries.append(line)
            return entries
        for obj in walk_objects(payload(artefact)):
            for key, value in obj.items():
                if "warning" in key and isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            entries.extend(
                                str(v) for v in item.values())
                        else:
                            entries.append(str(item))
                if "warning" in key and isinstance(value, str):
                    entries.append(value)
                if isinstance(value, dict) and "kind" in value \
                        and "warning" in key:
                    entries.append(str(value["kind"]))
        return entries

    def test_failed_control_notice_stands_in_its_own_form_every_form(self):
        """Pins plan Section 1.3 S9, notice N-L1-2, presence limb.
        Oracle: brief Section 5.8 IM7-ANA-2 landing: where a
        control outcome contradicts its asserted kind, the round
        report carries the control failure notice in all three
        forms, in Simple in words, in Advanced as a structured
        notice beside the per kind RoundMetrics sets, and in
        Agentic as a structured field of the report response."""
        label = self.seed_control_round("round-fail",
                                        ANSWER_CONTROL_FAIL)
        for form in FORMS:
            text = as_text(probe_report(self.home, label, form))
            self.assertIn("control", text.lower())
            self.assertIn("notice", text.lower())

    def test_notice_stands_in_no_warning_list_and_as_no_warning_kind(self):
        """Pins plan Section 1.3 S9, notice N-L1-2, vocabulary limb.
        Oracle: brief Section 5.8 IM7-ANA-2 landing on the K-08
        cure: the notice is not a warning kind, it enters no part
        of the closed warning vocabulary, and no reading form
        presents it as a warning, so no warning list in any form
        carries the notice and no warning entry names it."""
        label = self.seed_control_round("round-fail",
                                        ANSWER_CONTROL_FAIL)
        for form in FORMS:
            artefact = probe_report(self.home, label, form)
            entries = self.warning_entries(artefact)
            for entry in entries:
                self.assertNotIn("control failure", entry.lower())
                self.assertNotIn("control_failure", entry.lower())
            if form == "simple":
                self.assertTrue(
                    entries or "warning" not in artefact.lower(),
                    "Simple warning statements stand examined")

    def test_passing_control_round_carries_no_notice(self):
        """Pins plan Section 1.3 S9, notice N-L1-2, absence limb.
        Oracle: brief Section 5.8 IM7-ANA-2 landing: the notice
        stands where a control outcome contradicts its asserted
        kind, and a passed control is never presented as detector
        validation; a round whose designated control passes
        carries no control failure notice."""
        label = self.seed_control_round("round-pass",
                                        ANSWER_CONTROL_PASS)
        text = as_text(probe_report(self.home, label,
                                    "advanced")).lower()
        self.assertNotIn("control failure", text)


class TestGuideArtefactTexts(ReportingBase):
    """Row S9 guide artefact fixed texts. Oracle: brief Section
    5.5 Simple conformance check (a guide artefact is tested
    against all three fixed guide texts at Section 5.12, the
    rendering rule, the refusal sentence, and the citation only
    sentence, each verbatim where it applies) and brief Section
    5.12 IM7-BRK-13 and IM7-DIV-3 landings."""

    def guide_draft(self, page):
        record = audit_page(self.home, page)
        return service.guide(home=str(self.home),
                             run_id=field(record, "run_id"),
                             audit_date=AUDIT_DATE)

    def test_refusal_sentence_verbatim_in_the_simple_guide_artefact(self):
        """Pins plan Section 1.3 S9, guide artefact refusal text.
        Oracle: brief Section 5.12 item 137: the refusal sentence
        is a fixed text, printed verbatim where it applies."""
        draft = self.guide_draft(PAGE_NO_EVIDENCE)
        self.assertIn(REFUSAL_SENTENCE, render(draft, "simple"))

    def test_citation_only_sentence_verbatim_where_it_applies(self):
        """Pins plan Section 1.3 S9, guide artefact citation only
        text. Oracle: brief Section 5.12 item 137: the citation
        only sentence is a fixed text, printed verbatim where it
        applies."""
        draft = self.guide_draft(FIXTURES / "w6-page-citation-only.md")
        for form in FORMS:
            self.assertIn(CITATION_ONLY_SENTENCE,
                          as_text(render(draft, form)))

    def test_selection_statements_verbatim_in_every_form(self):
        """Pins plan Section 1.3 S9, guide artefact selection
        statements. Oracle: brief Section 5.12 IM7-BRK-13 landing:
        two statements are fixed verbatim and print in those words
        in the guide artefact in every form the draft ships in;
        the fallback statement where the fallback is used, and the
        preference statement where a sentence passing the
        preference test is chosen."""
        fallback = self.guide_draft(PAGE_FALLBACK)
        for form in FORMS:
            self.assertIn(FALLBACK_STATEMENT,
                          as_text(render(fallback, form)))
        chosen = self.guide_draft(PAGE_PREFERENCE)
        for form in FORMS:
            self.assertIn(PREFERENCE_STATEMENT,
                          as_text(render(chosen, form)))

    def test_simple_group_labels_verbatim_in_class_order(self):
        """Pins plan Section 1.3 S9, guide artefact group labels.
        Oracle: brief Section 5.12 IM7-DIV-3 landing rendering per
        form: in Simple the actions print grouped in class order,
        cap_first first, then score_check, then any
        defect_not_score action, each group under its fixed label
        text printed in those words in every Simple guide
        artefact."""
        draft = self.guide_draft(PAGE_ONE_CITATION)
        simple = render(draft, "simple")
        self.assertIn(LABEL_CAP_FIRST, simple)
        self.assertIn(LABEL_SCORE_CHECK, simple)
        self.assertIn(LABEL_DEFECT, simple)
        self.assertLess(simple.index(LABEL_CAP_FIRST),
                        simple.index(LABEL_SCORE_CHECK))
        self.assertLess(simple.index(LABEL_SCORE_CHECK),
                        simple.index(LABEL_DEFECT))


class TestAgenticEnvelope(ReportingBase):
    """Row S9 Agentic envelope. Oracle: brief Section 5.5 item 122:
    the Agentic response wraps the report payload under one named
    report key; the payload is never replaced by an actionable
    subset, so no number exists in Agentic that Advanced does not
    hold."""

    def test_payload_under_one_report_key_and_not_a_subset(self):
        """Pins plan Section 1.3 S9, Agentic envelope limb. Oracle:
        brief Section 5.5 item 122 and the Agentic conformance
        check: the response carries the contract fields only at
        the top level, the report payload sits under one named
        report key in the Section 5.2 shape, and the honesty and
        anchor limit fields stand in structured form in every
        response."""
        record = self.seed_audit()
        advanced = payload(render(record, "advanced"))
        envelope = render(record, "agentic")
        self.assertIn("report", envelope)
        body = envelope["report"]
        self.assertEqual(field(body, "score"), field(advanced,
                                                     "score"))
        self.assertEqual(field(body, "checks"),
                         field(advanced, "checks"))
        self.assertIn(HONESTY, as_text(envelope))
        self.assertIn(ANCHOR_LIMIT, as_text(envelope))


class TestReportingTiming(ReportingBase):
    """Row S9 timing bound. Oracle: plan Section 1.5 timing bounds,
    CQ-D31: S9, rendering of one report in all three forms, 10
    seconds, a plan design value at the stated scale of one
    report. No scale beyond one report stands owed."""

    def test_one_report_in_all_three_forms_within_ten_seconds(self):
        """Pins plan Section 1.3 S9, timing bound at its stated
        form. Oracle: plan Section 1.5 timing bounds: rendering of
        one report in all three forms completes within 10
        seconds."""
        record = self.seed_audit()
        start = time.monotonic()
        for form in FORMS:
            render(record, form)
        self.assertLess(time.monotonic() - start, 10.0)


if __name__ == "__main__":
    unittest.main()
