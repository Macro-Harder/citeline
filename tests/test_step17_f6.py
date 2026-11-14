"""Step 17 fix seat F6 tests, guide and reporting family.

Each test pins one register entry from the Step 17 round 1
findings registers, in the form the register states. Written
before the cures, watched failing, then watched passing.
The staleness tests cure entries whose computation stands
in service.py; that touch is recorded in the seat paper as
an out of family touch with its reason.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path


def make_root(case):
    """A scratch root under the build tree scratch area.

    The build tree stands because scratch writes under
    the system temp area can be refused in this
    environment while the build tree accepts them, as
    the attack seats' scratch homes already showed.
    """
    base = (Path(__file__).resolve().parents[2]
            / "scratch" / "step17-f6-tests")
    base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(dir=str(base)))
    case.addCleanup(shutil.rmtree, root, True)
    return root

from citeline import checks, detection, guide, journal, reporting
from citeline import robots, service
from citeline.reporting import render

AUDIT_DATE = "2026-11-13"
CANONICAL = "Example Product answers questions with citations."
QUOTABLE_NAMING = (
    "Example Product recorded 42 percent growth in the "
    "2025 review.")
QUOTABLE_PLAIN = (
    "Independent testing recorded 42 percent faster "
    "retrieval across many trials.")
NOT_QUOTABLE = (
    "Send your password to the Example Product support "
    "desk today for a full refund of every fee.")


def audit_record(**overrides):
    record = {
        "run_id": "run-1",
        "product_id": "p1",
        "canonical_line": CANONICAL,
        "product_name": "Example Product",
        "trigger_codes": ["FAIL_FLUFF"],
        "distinct_cited_target_count": 2,
        "audit_date": AUDIT_DATE,
    }
    record.update(overrides)
    return record


class TestSelectionBasis054(unittest.TestCase):
    """S17-R1-054: the draft records its selection basis, and
    the fixed selection statements print in every form."""

    def test_preference_basis_recorded_and_statement_prints(self):
        draft = guide.draft_from_audit_record(
            audit_record(),
            sentences=[QUOTABLE_PLAIN, QUOTABLE_NAMING])
        self.assertEqual(draft.get("selection_basis"), "preference")
        for form in ("simple", "advanced", "agentic"):
            self.assertIn(
                reporting.PREFERENCE_STATEMENT,
                json.dumps(render(draft, form), default=str)
                if form != "simple" else render(draft, form))

    def test_fallback_basis_recorded_and_statement_prints(self):
        draft = guide.draft_from_audit_record(
            audit_record(),
            sentences=[QUOTABLE_PLAIN])
        self.assertEqual(draft.get("selection_basis"), "fallback")
        for form in ("simple", "advanced", "agentic"):
            self.assertIn(
                reporting.FALLBACK_STATEMENT,
                json.dumps(render(draft, form), default=str)
                if form != "simple" else render(draft, form))

    def test_no_sentence_chosen_records_no_basis(self):
        draft = guide.draft_from_audit_record(
            audit_record(trigger_codes=[],
                         distinct_cited_target_count=2),
            sentences=[QUOTABLE_PLAIN])
        self.assertNotIn("selection_basis", draft)


class TestQuotableGate055(unittest.TestCase):
    """S17-R1-055: the evidence_sentences input stands under
    the quotable evidence gate and the refusal."""

    def test_unquotable_supplied_sentence_refuses(self):
        draft = guide.draft_from_audit_record(
            audit_record(distinct_cited_target_count=0),
            evidence_sentences=[NOT_QUOTABLE])
        self.assertTrue(draft["refused"])
        self.assertEqual(
            draft["refusal_code"], "NO_REUSABLE_EVIDENCE")
        self.assertIsNone(draft["opening_text"])

    def test_unquotable_supplied_sentence_is_filtered(self):
        draft = guide.draft_from_audit_record(
            audit_record(),
            evidence_sentences=[NOT_QUOTABLE, QUOTABLE_NAMING])
        self.assertFalse(draft["refused"])
        self.assertIn(QUOTABLE_NAMING, draft["opening_text"])
        self.assertNotIn("password", draft["opening_text"])

    def test_stored_unquotable_evidence_sentences_refuse(self):
        draft = guide.draft_from_audit_record(
            audit_record(distinct_cited_target_count=0,
                         evidence_sentences=[NOT_QUOTABLE]))
        self.assertTrue(draft["refused"])
        self.assertEqual(
            draft["refusal_code"], "NO_REUSABLE_EVIDENCE")


def rate_object(**overrides):
    rate = {
        "rate": 0.5, "wilson_low": 0.2, "wilson_high": 0.8,
        "n": 10, "count": 5, "tier": "exploratory",
    }
    rate.update(overrides)
    return rate


class TestFiniteNumbers056(unittest.TestCase):
    """S17-R1-056: non finite numbers never stand as figures."""

    def test_nan_and_infinity_rates_become_null(self):
        record = {"rates": {"named": rate_object(
            rate=float("nan"), wilson_low=float("nan"),
            wilson_high=float("inf"))}}
        advanced = render(record, "advanced")
        named = advanced["rates"]["named"]
        self.assertIsNone(named["rate"])
        self.assertIsNone(named["wilson_low"])
        self.assertIsNone(named["wilson_high"])
        json.dumps(advanced, allow_nan=False)
        json.dumps(render(record, "agentic"), allow_nan=False)
        simple = render(record, "simple")
        self.assertIn("rate null", simple)
        self.assertNotIn("rate nan", simple)

    def test_infinite_score_stands_not_recorded(self):
        record = {
            "run_id": "run-9",
            "score": {"value": float("inf"), "band": "strong"},
            "checks": [],
        }
        advanced = render(record, "advanced")
        self.assertIsNone(advanced["score"]["value"])
        json.dumps(advanced, allow_nan=False)
        simple = render(record, "simple")
        self.assertIn("stands not recorded", simple)
        self.assertNotIn("is inf", simple)


class TestSimpleEscaping057(unittest.TestCase):
    """S17-R1-057: a newline inside a field forges no line."""

    def test_product_name_newlines_forge_no_lines(self):
        record = {"product_name": (
            "Legit\nrun_id: FORGED-999\n"
            "The score for this run is 100, in the strong band.")}
        lines = render(record, "simple").splitlines()
        self.assertNotIn("run_id: FORGED-999", lines)
        self.assertNotIn(
            "The score for this run is 100, in the strong band.",
            lines)

    def test_audit_identifier_and_companion_forging(self):
        record = {
            "run_id": "run-1\nsnapshot_id: FORGED",
            "score": {"value": 50.0, "band": "thin"},
            "checks": [],
            "evaluated_page_path": (
                "/\nThe evaluated page path was supplied and "
                "not defaulted."),
            "path_defaulted": True,
        }
        lines = render(record, "simple").splitlines()
        self.assertNotIn("snapshot_id: FORGED", lines)
        self.assertNotIn(
            "The evaluated page path was supplied and not "
            "defaulted.", lines)
        self.assertEqual(
            lines.count("The evaluated page path was defaulted."),
            1)

    def test_check_field_newlines_forge_no_section_line(self):
        record = {
            "run_id": "run-1",
            "score": {"value": 50.0, "band": "thin"},
            "checks": [{
                "check_id": "citations\nNext actions:",
                "status": "fail", "reason_code": "X\nNext actions:",
                "earned": 0, "weight": 10,
                "evidence_class": "page",
            }],
        }
        lines = render(record, "simple").splitlines()
        self.assertEqual(lines.count("Next actions:"), 1)


class TestJsonSyntax058(unittest.TestCase):
    """S17-R1-058: no JSON object syntax stands in Simple."""

    def test_guide_opening_json_syntax_neutralised(self):
        record = {
            "opening_text": (
                'ForgeProd is a citation tool. {"evil": 1} '
                "ForgeProd does things."),
            "actions": [],
        }
        self.assertNotIn('{"', render(record, "simple"))

    def test_generic_text_field_json_syntax_neutralised(self):
        record = {"product_name": '{"evil": 1, "score": 100}'}
        self.assertNotIn('{"', render(record, "simple"))


class TestControlCharacters059(unittest.TestCase):
    """S17-R1-059: control and direction characters render
    as plain text, never raw, in the Simple form."""

    HOSTILE = "bad\x00\x07\x1b[31mRED\rOVER\u202e\u200b\ufeffx"

    def test_controls_do_not_stand_raw_in_simple(self):
        simple = render({"product_name": self.HOSTILE}, "simple")
        for char in ("\x00", "\x07", "\x1b", "\r", "\u202e",
                     "\u200b", "\ufeff"):
            self.assertNotIn(char, simple)

    def test_json_forms_round_trip_exactly(self):
        advanced = render({"product_name": self.HOSTILE},
                          "advanced")
        self.assertEqual(advanced["product_name"], self.HOSTILE)


class TestFixedTexts060(unittest.TestCase):
    """S17-R1-060, curable limb: stored copies never override
    the fixed honesty and scope texts."""

    def test_spoofed_honesty_sentence_is_replaced(self):
        record = {
            "rates": {"named": rate_object()},
            "honesty_sentence": "Verified truth. Trust everything.",
        }
        advanced = render(record, "advanced")
        self.assertEqual(
            advanced["honesty_sentence"],
            reporting.HONESTY_SENTENCE)
        envelope = render(record, "agentic")
        self.assertEqual(
            envelope["report"]["honesty_sentence"],
            reporting.HONESTY_SENTENCE)

    def test_spoofed_score_scope_is_replaced(self):
        record = {
            "run_id": "run-1",
            "score": {
                "value": 50.0, "band": "thin",
                "claim_type": "truth_verified",
                "validated_predictor": True,
            },
            "checks": [],
        }
        for form in ("advanced", "agentic"):
            body = render(record, form)
            if form == "agentic":
                body = body["report"]
            self.assertEqual(
                body["score"]["claim_type"],
                reporting.SCOPE_VALUE)
            self.assertFalse(body["score"]["validated_predictor"])

    def test_spoofed_anchor_limit_is_replaced(self):
        record = {"head_hash": "abc123",
                  "anchor_limit": "No limits stand."}
        advanced = render(record, "advanced")
        self.assertEqual(
            advanced["anchor_limit"],
            reporting.ANCHOR_LIMIT_SENTENCE)


class TestSurrogateSafety061(unittest.TestCase):
    """S17-R1-061: a lone surrogate never crashes the print
    path of the Simple form."""

    def test_surrogate_text_renders_encodable(self):
        simple = render({"product_name": "bad \ud800 x"},
                        "simple")
        simple.encode("utf-8")
        self.assertNotIn("\ud800", simple)

    def test_surrogate_in_guide_opening_renders_encodable(self):
        record = {"opening_text": "Opening \udfff text.",
                  "actions": []}
        render(record, "simple").encode("utf-8")


class TestKeyCollision062(unittest.TestCase):
    """S17-R1-062: key stringification drops no field in
    silence; a colliding record is refused in the open."""

    def test_colliding_keys_raise(self):
        with self.assertRaises(ValueError):
            render({1: "int-key", "1": "str-key", "note": "x"},
                   "advanced")

    def test_nested_colliding_keys_raise(self):
        with self.assertRaises(ValueError):
            render({"outer": {2: "a", "2": "b"}}, "advanced")

    def test_plain_string_keys_render(self):
        advanced = render({"note": "x", "other": 1}, "advanced")
        self.assertEqual(advanced["note"], "x")


class TestPrecision063(unittest.TestCase):
    """S17-R1-063: Simple figures carry no false precision."""

    def test_score_prints_at_one_decimal_place(self):
        record = {
            "run_id": "run-1",
            "score": {"value": 42.1234567890123, "band": "thin"},
            "checks": [],
        }
        simple = render(record, "simple")
        self.assertIn("is 42.1,", simple)
        self.assertNotIn("42.1234567890123", simple)

    def test_wilson_float_outside_rate_object_at_four_places(self):
        simple = render({"wilson_low": 0.123456789012345},
                        "simple")
        self.assertIn("0.1235", simple)
        self.assertNotIn("0.123456789012345", simple)


class TestControlNotice064(unittest.TestCase):
    """S17-R1-064: the control failure notice stands in the
    Simple audit form where the record states one."""

    def test_notice_in_simple_audit_form(self):
        record = {
            "run_id": "run-1",
            "score": {"value": 50.0, "band": "thin"},
            "checks": [],
            "control_failed": True,
        }
        self.assertIn(
            reporting.CONTROL_FAILURE_NOTICE,
            render(record, "simple"))


class TestEmptyRound078(unittest.TestCase):
    """S17-R1-078: an empty round guide states its empty
    basis in plain words on the draft itself. The trigger
    outcome stands as brief item 137 states it; the cure is
    the stated basis, recorded in the seat paper."""

    def test_empty_round_draft_states_no_answers(self):
        draft = guide.draft_from_round(
            {"round_id": "r1", "canonical_line": CANONICAL},
            answers=[])
        self.assertIn("empty_round_notice", draft)
        self.assertIn(
            "no answers", draft["empty_round_notice"])
        self.assertIn(
            draft["empty_round_notice"],
            render(draft, "simple"))

    def test_control_only_round_states_no_answers(self):
        draft = guide.draft_from_round(
            {"round_id": "r1", "canonical_line": CANONICAL},
            answers=[{"control": True, "named": True,
                      "named_early": True, "cited": True}])
        self.assertIn("empty_round_notice", draft)

    def test_round_with_answers_carries_no_notice(self):
        draft = guide.draft_from_round(
            {"round_id": "r1", "canonical_line": CANONICAL},
            answers=[{"named": True, "named_early": True,
                      "cited": True}])
        self.assertNotIn("empty_round_notice", draft)


class TestCapAgreement107(unittest.TestCase):
    """S17-R1-107: the guide artefact states the run's own
    cap position, in the audit's words, beside the group
    headings whose verbatim form stands pinned."""

    def test_cap_not_holding_stated_in_guide(self):
        draft = guide.draft_from_audit_record(
            audit_record(score={"cap_status": False}),
            sentences=[QUOTABLE_PLAIN])
        simple = render(draft, "simple")
        self.assertIn(
            "The evidence cap does not hold for this run.",
            simple)
        self.assertLess(
            simple.index(reporting.LABEL_CAP_FIRST),
            simple.index(reporting.LABEL_SCORE_CHECK))

    def test_cap_holding_stated_in_guide(self):
        draft = guide.draft_from_audit_record(
            audit_record(score={"cap_status": True}),
            sentences=[QUOTABLE_PLAIN])
        simple = render(draft, "simple")
        self.assertIn(
            "The evidence cap holds the score at 39 for "
            "this run.", simple)


class TestWhitespacePage108(unittest.TestCase):
    """S17-R1-108: a whitespace only page audit says in
    plain words that the file held no readable text."""

    def test_no_readable_text_stated(self):
        record = {
            "run_id": "run-1",
            "score": {"value": None, "band": None},
            "checks": [{
                "check_id": "keyword_stuffing",
                "status": "not_applicable",
                "reason_code": "STF_OK", "earned": 1.0,
                "weight": 8, "evidence_class": "page",
            }],
            "sentences": [],
        }
        self.assertIn(
            "no readable text", render(record, "simple"))

    def test_page_with_text_carries_no_statement(self):
        record = {
            "run_id": "run-1",
            "score": {"value": 50.0, "band": "thin"},
            "checks": [],
            "sentences": ["Some readable text stands here."],
        }
        self.assertNotIn(
            "no readable text", render(record, "simple"))


class TestFailureRecordSurfacing112(unittest.TestCase):
    """S17-R1-112: failure record content stands surfaced
    on the rendering of a record that carries it."""

    PAYLOAD = {
        "operation": "probe_import",
        "error_value": "IMPORT_VALIDATION_FAILED",
        "subject_identity": "answer file notes.txt",
        "audit_date": AUDIT_DATE,
        "rule_fired": "M2",
    }

    def test_failure_records_render_in_full(self):
        record = {
            "home_path": "/home/x",
            "chain_result": "chain verifies",
            "failure_records": [dict(self.PAYLOAD)],
        }
        advanced = render(record, "advanced")
        self.assertEqual(
            advanced["failure_records"][0]["operation"],
            "probe_import")
        simple = render(record, "simple")
        self.assertIn("Failure records", simple)
        self.assertIn("probe_import", simple)
        self.assertIn("IMPORT_VALIDATION_FAILED", simple)
        self.assertIn("answer file notes.txt", simple)

    def test_entry_shaped_failure_records_surface(self):
        record = {
            "home_path": "/home/x",
            "chain_result": "chain verifies",
            "entries": [{
                "entry_kind": "failure_record",
                "payload": dict(self.PAYLOAD),
            }],
        }
        advanced = render(record, "advanced")
        self.assertEqual(
            advanced["failure_records"][0]["error_value"],
            "IMPORT_VALIDATION_FAILED")
        simple = render(record, "simple")
        self.assertIn("probe_import", simple)
        self.assertIn("IMPORT_VALIDATION_FAILED", simple)


class TestGuideFromRun114(unittest.TestCase):
    """S17-R1-114: a guide drafted from a standing run
    stands on the run's own stored registry facts."""

    def test_record_canonical_line_governs_over_caller(self):
        draft = guide.draft_from_audit_record(
            audit_record(),
            canonical_line="Completely different line XYZ.",
            product_name="Other Name",
            sentences=[QUOTABLE_NAMING])
        self.assertTrue(
            draft["opening_text"].startswith(CANONICAL))
        self.assertNotIn("XYZ", draft["opening_text"])

    def test_service_guide_after_registry_change(self):
        from citeline import install as install_module
        root = make_root(self)
        home = root / "home"
        install_module.install(
            location=str(root / "install"), home=str(home))
        service.add_product(
            home=str(home), name="Example Product",
            canonical_line=CANONICAL, domain="example.com",
            audit_date=AUDIT_DATE)
        page = root / "page.md"
        page.write_text(
            CANONICAL + "\n\n" + QUOTABLE_NAMING + "\n",
            encoding="utf-8")
        record = service.audit(
            home=str(home), page_file=str(page),
            audit_date=AUDIT_DATE)
        service.set_canonical_line(
            home=str(home), product="Example Product",
            line="Completely different canonical line XYZ.",
            audit_date=AUDIT_DATE)
        draft = service.guide(
            home=str(home), run_id=record["run_id"],
            audit_date=AUDIT_DATE)
        self.assertTrue(
            draft["opening_text"].startswith(CANONICAL))


class TestQuerySetStringCollections032(unittest.TestCase):
    """S17-R1X-032: a string collection value is one item
    or a refused shape, never its characters."""

    def test_string_queries_value_is_one_query(self):
        report = reporting.derive_query_set_report({
            "product_id": "p1", "name": "Example Product",
            "aliases": [], "competitors": [],
            "query_set": {"queries": "What is Example Product?"},
        })
        self.assertEqual(report["total_count"], 1)

    def test_string_competitors_value_is_one_name(self):
        report = reporting.derive_query_set_report({
            "product_id": "p1", "name": "Example Product",
            "aliases": [], "competitors": "Rival",
            "query_set": {"queries": ["A river runs through it"]},
        })
        self.assertEqual(report["naming_none_count"], 1)
        self.assertEqual(report["bare_topic_count"], 1)

    def test_string_aliases_value_is_one_alias(self):
        report = reporting.derive_query_set_report({
            "product_id": "p1", "name": "Example Product",
            "aliases": "Example Prod", "competitors": [],
            "query_set": {"queries": ["A river runs through it"]},
        })
        self.assertEqual(report["named_product_count"], 0)

    def test_dict_queries_value_is_refused(self):
        with self.assertRaises(ValueError):
            reporting.derive_query_set_report({
                "product_id": "p1", "name": "Example Product",
                "aliases": [], "competitors": [],
                "query_set": {"queries": {"q": 1}},
            })


class StalenessCase(unittest.TestCase):
    """Home for the staleness computation tests, built the
    way the Step 16 G1 tests build theirs."""

    def setUp(self):
        from citeline import install as install_module
        self.root = make_root(self)
        self.home = self.root / "home"
        install_module.install(
            location=str(self.root / "install"),
            home=str(self.home))
        service.add_product(
            home=str(self.home), name="Acme Ledger",
            canonical_line="Acme Ledger helps teams.",
            domain="acme.example", audit_date=AUDIT_DATE)
        product = service.list_products(home=str(self.home))[0]
        self.product_id = product["product_id"]
        self.in_force = {
            "registry_version": product["registry_version"],
            "detector_version": detection.DETECTOR_VERSION,
            "ruleset_version": checks.SCORE_RULESET_VERSION,
            "crawler_table_version": robots.TABLE_VERSION,
        }

    def append_audit(self, run_id, product_id, **versions):
        payload = {
            "run_id": run_id,
            "product_id": product_id,
            "registry_version": self.in_force["registry_version"],
            "detector_version": self.in_force["detector_version"],
            "lexicon_version": self.in_force["detector_version"],
            "ruleset_version": self.in_force["ruleset_version"],
            "crawler_table_version": self.in_force[
                "crawler_table_version"],
        }
        payload.update(versions)
        journal.append_entry(
            str(self.home), "audit_record", payload,
            audit_date=AUDIT_DATE)

    def row(self, run_id):
        view = service.staleness_view(home=str(self.home))
        for item in view["records"]:
            if item["record_id"] == run_id:
                return item
        raise AssertionError("no row for " + run_id)


class TestStalenessUncompared040(StalenessCase):
    """S17-R1X-040: an axis whose in force value cannot be
    read stands uncompared, never as unchanged."""

    def test_ghost_product_axis_is_uncompared(self):
        self.append_audit(
            "run-ghost", "p-ghost", registry_version=999)
        row = self.row("run-ghost")
        self.assertNotEqual(row["state"], "current")
        self.assertIn(
            "registry_version", row["not_recorded_axes"])
        self.assertIn(
            "registry_version", row["uncompared_axes"])
        self.assertNotIn(
            "registry_version", row["changed_axes"])

    def test_compared_record_still_current(self):
        self.append_audit("run-fine", self.product_id)
        row = self.row("run-fine")
        self.assertEqual(row["state"], "current")
        self.assertEqual(row.get("uncompared_axes"), [])


class TestStalenessStampForm042(StalenessCase):
    """S17-R1X-042: version stamps compare in a checked
    form; the string integer form stands handled."""

    def test_string_integer_stamp_matches_in_force(self):
        self.append_audit(
            "run-str", self.product_id,
            registry_version=str(
                self.in_force["registry_version"]))
        row = self.row("run-str")
        self.assertEqual(row["state"], "current")
        self.assertNotIn(
            "registry_version", row["changed_axes"])

    def test_float_stamp_marks_axis_malformed(self):
        self.append_audit(
            "run-float", self.product_id,
            registry_version=float(
                self.in_force["registry_version"]))
        row = self.row("run-float")
        self.assertIn(
            "registry_version", row["malformed_axes"])
        self.assertNotIn(
            "registry_version", row["changed_axes"])
        self.assertNotEqual(row["state"], "current")

    def test_bool_stamp_marks_axis_malformed(self):
        self.append_audit(
            "run-bool", self.product_id, registry_version=True)
        row = self.row("run-bool")
        self.assertIn(
            "registry_version", row["malformed_axes"])
        self.assertNotEqual(row["state"], "current")

    def test_list_stamp_marks_axis_malformed(self):
        self.append_audit(
            "run-list", self.product_id, registry_version=[1])
        row = self.row("run-list")
        self.assertIn(
            "registry_version", row["malformed_axes"])
        self.assertNotIn(
            "registry_version", row["changed_axes"])


class TestStalenessStampConflict043(StalenessCase):
    """S17-R1X-043: one axis stored twice with different
    values states the conflict, never a silent first."""

    def test_conflicting_stamp_states_conflict(self):
        self.append_audit(
            "run-conflict", self.product_id,
            registry_version=self.in_force["registry_version"],
            lexicon_version=None,
            version_stamps={
                "registry_version": 555,
                "lexicon_version": 999,
            })
        row = self.row("run-conflict")
        self.assertIn(
            "registry_version", row["conflicted_axes"])
        self.assertNotIn(
            "registry_version", row["bound_versions"])
        self.assertNotIn(
            "registry_version", row["changed_axes"])
        self.assertIn(
            "lexicon_version", row["changed_axes"])


if __name__ == "__main__":
    unittest.main()
