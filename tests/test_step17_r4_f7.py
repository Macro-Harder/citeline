"""Service, watch, seams.

Pins the register entries charged to F7 in fix round 4:
and. Entry is a rename charge in
product/tests/test_step16_f5.py and stands pinned by that
file's own run, not by a test here. Every test was written
before its cure and run failing for the register stated
reason, except the controls named as controls. Oracle: the
round 4 findings register and disposition."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from citeline import errors, install as install_module
from citeline import guide as guide_module
from citeline import journal, service, watch

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = FIXTURES / "w7-page.md"
ROBOTS = FIXTURES / "w7-robots.txt"
AUDIT_DATE = "2026-11-14"
PRODUCT = "Acme Ledger"
Q1 = "What is Acme Ledger?"
Q2 = "Best ferry tracker?"
ROUND = "round-1"


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def seed(case, home):
    service.add_product(
        home=str(home), name=PRODUCT,
        canonical_line="Acme Ledger helps teams track citations.",
        domain="acme.example", audit_date=AUDIT_DATE)
    service.set_query_set(
        home=str(home), product=PRODUCT, query_set=[Q1, Q2],
        audit_date=AUDIT_DATE)
    service.name_round(
        home=str(home), product=PRODUCT, round_label=ROUND,
        importer_declaration="all captured",
        supplier_relation="independent party", audit_date=AUDIT_DATE)
    return home


def do_import(home, answer_file, **overrides):
    kwargs = {
        "home": str(home), "answer_file": str(answer_file),
        "product": PRODUCT, "round": ROUND, "engine_label": "Engine A",
        "query": Q1, "kind": "real_sample",
        "captured_on": "2026-11-10", "capture_method": "manual copy",
        "audit_date": AUDIT_DATE,
    }
    kwargs.update(overrides)
    return service.probe_import(**kwargs)


def journal_entries(home):
    path = Path(home) / "journal.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def entries_of_kind(home, kind):
    return [entry for entry in journal_entries(home)
            if entry.get("entry_kind") == kind]


def payloads_of_kind(home, kind):
    return [entry.get("payload") or {}
            for entry in entries_of_kind(home, kind)]


def token_of(exc):
    return getattr(exc, "token", None) or getattr(
        exc, "error_value", None)


def temp_file(case, content, name="file.txt"):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    path = root / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def plant_partial_batch(case, home, tail_count):
    path = Path(home) / "journal.jsonl"
    lines = path.read_bytes().splitlines(keepends=True)
    size = sum(len(line) for line in lines[:-tail_count])
    written = journal._write_batch_intent(
        str(home), size, None, None, tail_count)
    case.assertTrue(written)
    return Path(journal._batch_intent_path(str(home)))


class SeededBase(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)
        seed(self, self.home)

    def import_one(self):
        answer = temp_file(
            self, "Acme Ledger is a ledger tool.\n", "answer.txt")
        return do_import(self.home, answer)


# ----------------------------------------------------------------:
# export_capture_worksheet runs the recovery.
# ----------------------------------------------------------------

class Test050WorksheetExportRecovery(SeededBase):

    def test_worksheet_export_recovers_partial_batch(self):
        intent = plant_partial_batch(self, self.home, 1)
        out = temp_file(self, "", "sheet.txt")
        out.unlink()
        with self.assertRaises(errors.CitelineError) as caught:
            service.export_capture_worksheet(
                home=str(self.home), product=PRODUCT, round=ROUND,
                output_path=str(out), audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "UNKNOWN_ROUND")
        self.assertFalse(intent.exists())
        self.assertFalse(out.exists())


# ----------------------------------------------------------------:
# registry judgement routes judge recovered state.
# ----------------------------------------------------------------

class Test051RegistryRoutesRecover(SeededBase):

    def test_name_round_judges_recovered_state(self):
        intent = plant_partial_batch(self, self.home, 1)
        service.name_round(
            home=str(self.home), product=PRODUCT, round_label=ROUND,
            importer_declaration="all captured",
            supplier_relation="independent party",
            audit_date=AUDIT_DATE)
        self.assertFalse(intent.exists())

    def test_set_query_set_judges_recovered_state(self):
        intent = plant_partial_batch(self, self.home, 3)
        with self.assertRaises(errors.CitelineError) as caught:
            service.set_query_set(
                home=str(self.home), product=PRODUCT, query_set=[Q1],
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "UNKNOWN_PRODUCT")
        self.assertFalse(intent.exists())


# ----------------------------------------------------------------:
# robots routes leave no partial batch standing.
# ----------------------------------------------------------------

class Test052RobotsRoutesRecover(SeededBase):

    def test_robots_route_recovers_partial_batch(self):
        intent = plant_partial_batch(self, self.home, 1)
        service.robots(
            home=str(self.home), robots_file=str(ROBOTS),
            audit_date=AUDIT_DATE)
        self.assertFalse(intent.exists())

    def test_robots_preview_recovers_partial_batch(self):
        intent = plant_partial_batch(self, self.home, 1)
        service.robots_preview(
            home=str(self.home), first_robots_file=str(ROBOTS),
            second_robots_file=str(ROBOTS), audit_date=AUDIT_DATE)
        self.assertFalse(intent.exists())


# ----------------------------------------------------------------:
# robots preview audit date failure is recorded.
# ----------------------------------------------------------------

class Test053PreviewAuditDateRecorded(SeededBase):

    def test_bad_audit_date_appends_one_failure_record(self):
        before = len(payloads_of_kind(self.home, "failure_record"))
        with self.assertRaises(errors.CitelineError) as caught:
            service.robots_preview(
                home=str(self.home), first_robots_file=str(ROBOTS),
                second_robots_file=str(ROBOTS),
                audit_date="2026-02-30")
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        after = len(payloads_of_kind(self.home, "failure_record"))
        self.assertEqual(after - before, 1)


# ----------------------------------------------------------------:
# the home check stands on estate_grounds and
# export_capture_worksheet as on list_products.
# ----------------------------------------------------------------

class Test054HomeCheck(unittest.TestCase):

    def test_estate_grounds_missing_home(self):
        with self.assertRaises(errors.CitelineError) as caught:
            service.estate_grounds(
                home="/nonexistent-home-r4-f7", product=PRODUCT)
        self.assertEqual(token_of(caught.exception), "HOME_MISSING")

    def test_estate_grounds_nul_home(self):
        with self.assertRaises(errors.CitelineError) as caught:
            service.estate_grounds(home="x\x00y", product=PRODUCT)
        self.assertEqual(token_of(caught.exception), "HOME_MISSING")

    def test_estate_grounds_surrogate_home(self):
        with self.assertRaises(errors.CitelineError) as caught:
            service.estate_grounds(home="x\ud800y", product=PRODUCT)
        self.assertEqual(token_of(caught.exception), "HOME_MISSING")

    def test_export_missing_home(self):
        with self.assertRaises(errors.CitelineError) as caught:
            service.export_capture_worksheet(
                home="/nonexistent-home-r4-f7", product=PRODUCT,
                round=ROUND, audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "HOME_MISSING")

    def test_export_nul_home(self):
        with self.assertRaises(errors.CitelineError) as caught:
            service.export_capture_worksheet(
                home="x\x00y", product=PRODUCT, round=ROUND,
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "HOME_MISSING")


# ----------------------------------------------------------------:
# the snapshot boolean stands judged.
# ----------------------------------------------------------------

class Test055SnapshotBooleanJudged(SeededBase):

    def setUp(self):
        super().setUp()
        self.import_one()
        product_id = payloads_of_kind(
            self.home, "product_registered")[0]["product_id"]
        journal.append_entry(
            str(self.home), "snapshot_registered",
            {"snapshot_id": "snap-planted", "product_id": product_id,
             "is_product_page": "false", "supplied_path": str(PAGE)},
            audit_date=AUDIT_DATE)

    def test_estate_grounds_refuses_string_false(self):
        with self.assertRaises(errors.CitelineError) as caught:
            service.estate_grounds(
                home=str(self.home), product=PRODUCT)
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")

    def test_watch_coverage_count_ignores_string_false(self):
        products = service.list_products(home=str(self.home))
        count, _paths = watch._standing_product_page_snapshot_count(
            str(self.home), products)
        self.assertEqual(count, 0)


# ----------------------------------------------------------------:
# a negative answer size count stands judged.
# ----------------------------------------------------------------

class Test056NegativeAnswerSize(SeededBase):

    def test_status_refuses_negative_counts(self):
        self.import_one()
        standing = payloads_of_kind(self.home, "answer_imported")[0]
        swapped = dict(standing)
        swapped["answer_size"] = {"characters": -500, "words": -3}
        journal.append_entry(
            str(self.home), "answer_imported", swapped,
            audit_date=AUDIT_DATE)
        with self.assertRaises(errors.CitelineError) as caught:
            service.status(home=str(self.home))
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")


# ----------------------------------------------------------------:
# an empty string selector stands as no selector.
# ----------------------------------------------------------------

class Test057EmptySelector(unittest.TestCase):

    def plan(self, target):
        return {"home": "/tmp/home", "scope": "picked",
                "targets": [target], "audit_date": AUDIT_DATE}

    def test_empty_page_file_refused_at_open(self):
        with self.assertRaises(errors.CitelineError) as caught:
            watch._validate_plan(self.plan(
                {"product": PRODUCT, "page_file": ""}))
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")

    def test_empty_round_refused_at_open(self):
        with self.assertRaises(errors.CitelineError) as caught:
            watch._validate_plan(self.plan(
                {"product": PRODUCT, "round": ""}))
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")

    def test_named_selectors_still_open_control(self):
        targets = watch._validate_plan(self.plan(
            {"product": PRODUCT, "page_file": "/tmp/page.md"}))
        self.assertEqual(len(targets), 1)
        targets = watch._validate_plan(self.plan(
            {"product": PRODUCT, "round": ROUND}))
        self.assertEqual(len(targets), 1)


# ----------------------------------------------------------------:
# the cadence reading stands inside its stated forms.
# ----------------------------------------------------------------

class Test058CadenceForms(unittest.TestCase):

    def test_annually_reads_no_interval(self):
        self.assertIsNone(watch._cadence_interval_days("annually"))

    def test_unicode_whitespace_separator_reads_no_interval(self):
        self.assertIsNone(watch._cadence_interval_days(
            "every 2 days"))

    def test_stated_forms_still_read_control(self):
        self.assertEqual(watch._cadence_interval_days("yearly"), 365)
        self.assertEqual(
            watch._cadence_interval_days("every 2 days"), 2)


# ----------------------------------------------------------------:
# the vocabulary lookup helpers meet an unhashable value in the
# module's own form.
# ----------------------------------------------------------------

class Test059LookupHelpers(unittest.TestCase):

    def test_unhashable_token_returns_none(self):
        self.assertIsNone(errors.error_for_token(["HOME_MISSING"]))

    def test_unhashable_row_returns_none(self):
        self.assertIsNone(errors.error_for_row({"row": 1}))

    def test_recorded_error_survives_unhashable_token(self):
        class ForeignError(Exception):
            token = ["HOME_MISSING"]

        record = service.recorded_error(ForeignError("boom"))
        self.assertIsInstance(record, dict)
        self.assertEqual(record["message"], "boom")

    def test_hashable_lookups_still_work_control(self):
        self.assertEqual(
            errors.error_for_token("HOME_MISSING")["row"], "U-6")
        self.assertEqual(
            errors.error_for_row("U-6")["token"], "HOME_MISSING")


# ----------------------------------------------------------------:
# the key count stands enforced over the whole block.
# ----------------------------------------------------------------

class Test060KeyCountWholeBlock(SeededBase):

    def test_keys_past_the_reading_window_count(self):
        journal.write_config(
            str(self.home),
            "front_matter_key_count = 5\n"
            "front_matter_block_size = 128\n"
            "front_matter_value_length_per_key = 30000\n"
            "front_matter_size_after_alias_expansion = 256\n")
        lines = ["---"]
        for index in range(4):
            lines.append("big%d: %s" % (index, "v" * 20000))
        for index in range(10):
            lines.append("small%d: value" % index)
        lines += ["---", "Acme Ledger helps teams track citations."]
        page = temp_file(self, "\n".join(lines) + "\n", "page.md")
        with self.assertRaises(errors.CitelineError) as caught:
            service.audit(
                home=str(self.home), page_file=str(page),
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")


# ----------------------------------------------------------------:
# one reading of the limits governs the whole run.
# ----------------------------------------------------------------

class Test061OneLimitsReading(SeededBase):

    def test_extraction_enforces_the_stated_reading(self):
        journal.write_config(
            str(self.home),
            "front_matter_value_length_per_key = 10\n")
        page = temp_file(
            self, "---\ntitle: %s\n---\n"
            "Acme Ledger helps teams track citations.\n"
            % ("v" * 100), "page.md")
        real = journal.effective_limits
        calls = {"count": 0}

        def shifting(home, run_id=None):
            calls["count"] += 1
            limits = real(home, run_id=run_id)
            if calls["count"] > 1:
                limits = dict(limits)
                entry = dict(
                    limits["front_matter_value_length_per_key"])
                entry["value"] = 100000
                limits["front_matter_value_length_per_key"] = entry
            return limits

        with mock.patch.object(journal, "effective_limits", shifting):
            with self.assertRaises(errors.CitelineError) as caught:
                service.audit(
                    home=str(self.home), page_file=str(page),
                    audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")


# ----------------------------------------------------------------:
# the failure record kind stands judged at its surfacing readers.
# ----------------------------------------------------------------

class Test066FailureRecordKindJudged(SeededBase):

    def test_status_refuses_list_error_value(self):
        journal.append_entry(
            str(self.home), "failure_record",
            {"operation": "audit", "error_value": ["x"],
             "subject_identity": "page", "rule_fired": "x"},
            audit_date=AUDIT_DATE)
        with self.assertRaises(errors.CitelineError) as caught:
            service.status(home=str(self.home))
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")

    def test_status_refuses_integer_operation(self):
        journal.append_entry(
            str(self.home), "failure_record",
            {"operation": 7, "error_value": "VALIDATION_FAILED",
             "subject_identity": "page",
             "rule_fired": "VALIDATION_FAILED"},
            audit_date=AUDIT_DATE)
        with self.assertRaises(errors.CitelineError) as caught:
            service.status(home=str(self.home))
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")

    def test_complete_failure_record_still_surfaces_control(self):
        journal.append_entry(
            str(self.home), "failure_record",
            {"operation": "audit", "error_value": "VALIDATION_FAILED",
             "subject_identity": "page",
             "rule_fired": "VALIDATION_FAILED"},
            audit_date=AUDIT_DATE)
        result = service.status(home=str(self.home))
        self.assertEqual(len(result.get("failure_records") or []), 1)


# ----------------------------------------------------------------:
# the audit identities stand against a batch head recovery landing
# inside the assembly hold.
# ----------------------------------------------------------------

class Test067AuditIdentitiesAgainstRecovery(SeededBase):

    def test_batch_head_recovery_cannot_move_the_citation(self):
        real_batch = journal.append_entries_atomic

        def gated(home, entries, audit_date=None, run_id=None):
            path = Path(home) / "journal.jsonl"
            size = path.stat().st_size
            journal._write_batch_intent(home, size, None, None, 1)
            return real_batch(
                home, entries, audit_date=audit_date, run_id=run_id)

        with mock.patch.object(
                journal, "append_entries_atomic", gated):
            record = service.audit(
                home=str(self.home), page_file=str(PAGE),
                audit_date=AUDIT_DATE)
        snapshots = payloads_of_kind(self.home, "snapshot_registered")
        self.assertEqual(record["snapshot_id"],
                         snapshots[-1]["snapshot_id"])
        self.assertEqual(
            record["limits_in_force"]["run_id"], record["run_id"])
        standing = service.audit(
            home=str(self.home), run_id=record["run_id"])
        self.assertEqual(standing["snapshot_id"],
                         snapshots[-1]["snapshot_id"])
        self.assertEqual(
            standing["limits_in_force"]["run_id"], record["run_id"])


# ----------------------------------------------------------------:
# the probe import batch call stands inside the route failure
# record discipline.
# ----------------------------------------------------------------

class Test073ImportBatchFailureRecorded(SeededBase):

    def test_batch_failure_appends_exactly_one_failure_record(self):
        intent_path = Path(journal._batch_intent_path(str(self.home)))
        intent_path.mkdir()
        answer = temp_file(
            self, "Acme Ledger is a ledger tool.\n", "answer.txt")
        with self.assertRaises(errors.CitelineError) as caught:
            do_import(self.home, answer)
        self.assertEqual(
            token_of(caught.exception), "JOURNAL_VERIFY_FAILED")
        records = payloads_of_kind(self.home, "failure_record")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].get("operation"), "probe import")


# ----------------------------------------------------------------:
# one probe report artefact stands on one fold instant.
# ----------------------------------------------------------------

class Test075ProbeReportOneInstant(SeededBase):

    def test_correction_between_folds_does_not_split_the_artefact(self):
        self.import_one()
        with self.assertRaises(errors.CitelineError):
            service.probe_report(
                home=str(self.home), product=PRODUCT, round="nope",
                audit_date=AUDIT_DATE)
        failure = entries_of_kind(self.home, "failure_record")[-1]
        real_round_entries = service._round_entries
        landed = {"done": False}

        def wrapper(home, product_record, round_record):
            entries = real_round_entries(
                home, product_record, round_record)
            if not landed["done"]:
                landed["done"] = True
                corrected = dict(failure.get("payload") or {})
                corrected["error_value"] = "CORRECTED_MARKER"
                corrected["rule_fired"] = "CORRECTED_MARKER"
                journal.append_entry(
                    str(home), "correction",
                    {"supersedes_sequence": failure["sequence"],
                     "corrected_record": corrected},
                    audit_date=AUDIT_DATE)
            return entries

        with mock.patch.object(service, "_round_entries", wrapper):
            result = service.probe_report(
                home=str(self.home), product=PRODUCT, round=ROUND,
                audit_date=AUDIT_DATE)
        values = [payload.get("error_value")
                  for payload in result.get("failure_records") or []]
        self.assertNotIn("CORRECTED_MARKER", values)
        self.assertIn("UNKNOWN_ROUND", values)


# ----------------------------------------------------------------:
# the guide assembly stands under the identity discipline the
# audit assembly stands under.
# ----------------------------------------------------------------

class Test076GuideStoreReReads(SeededBase):

    def test_guide_stored_after_a_correction_follows_it(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        audit_entry = entries_of_kind(self.home, "audit_record")[-1]
        real_draft = guide_module.draft_from_audit_record
        landed = {"done": False}

        def wrapper(audit_record, **kwargs):
            draft = real_draft(audit_record, **kwargs)
            if not landed["done"]:
                landed["done"] = True
                corrected = dict(audit_entry.get("payload") or {})
                corrected["canonical_line"] = (
                    "Corrected canonical line for Acme Ledger.")
                journal.append_entry(
                    str(self.home), "correction",
                    {"supersedes_sequence": audit_entry["sequence"],
                     "corrected_record": corrected},
                    audit_date=AUDIT_DATE)
            return draft

        with mock.patch.object(
                guide_module, "draft_from_audit_record", wrapper):
            service.guide(
                home=str(self.home), run_id=record["run_id"],
                audit_date=AUDIT_DATE)
        guides = payloads_of_kind(self.home, "guide_record")
        self.assertEqual(len(guides), 1)
        self.assertIn(
            "Corrected canonical line for Acme Ledger.",
            str(guides[-1].get("opening_text") or ""))


if __name__ == "__main__":
    unittest.main()
