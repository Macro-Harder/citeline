"""Step 17 round 3 fix seat F7 tests: service, watch, seams.

Pins the register entries charged to F7 in fix round 3:
S17-R3-029, S17-R3-046, S17-R3-047, S17-R3-048,
S17-R3-049, S17-R3-050, S17-R3-051, S17-R3-052,
S17-R3-059, S17-R3-060, S17-R3-061, S17-R3-064,
S17-R3-067, and S17-R3-068. Every test was written
before its cure and run failing for the register stated
reason, except the controls named as controls and the
entry S17-R3-051 evidence test, which stands as an
expected failure beside that entry's refusal in the
seat paper. Oracle: the round 3 findings register and
disposition.
"""

import datetime
import json
import multiprocessing
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from citeline import errors, install as install_module
from citeline import journal, service, watch

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = FIXTURES / "w7-page.md"
AUDIT_DATE = "2026-11-13"
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
    """Plant a genuine batch intent over the last entries.

    The intent names the journal size before the last
    tail_count entries, in the form the batch writer
    writes on a home with no anchor configured, so the
    standing entries of the tail stand as a killed
    batch's partial entries.
    """
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


# ----------------------------------------------------------------
# S17-R3-029: read routes recover or signal a partial batch.
# ----------------------------------------------------------------

class Test029ReadSideRecovery(SeededBase):

    def import_one(self):
        answer = temp_file(
            self, "Acme Ledger is a ledger tool.\n", "answer.txt")
        do_import(self.home, answer)

    def test_status_recovers_partial_batch(self):
        self.import_one()
        intent = plant_partial_batch(self, self.home, 2)
        result = service.status(home=str(self.home))
        self.assertFalse(intent.exists())
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)
        values = [payload.get("error_value")
                  for payload in result.get("failure_records") or []]
        # The recovery record's error_value stands in the
        # closed vocabulary: Step 19 item R19-095 supersedes
        # the raw interrupted_batch string this assertion
        # pinned before that cure.
        self.assertIn("TEMPORARY_LOST", values)

    def test_probe_report_recovers_partial_batch(self):
        self.import_one()
        intent = plant_partial_batch(self, self.home, 2)
        service.probe_report(
            home=str(self.home), product=PRODUCT, round=ROUND,
            audit_date=AUDIT_DATE)
        self.assertFalse(intent.exists())
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)

    def test_register_page_judges_recovered_state(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        snapshot_id = record["snapshot_id"]
        plant_partial_batch(self, self.home, 2)
        with self.assertRaises(errors.CitelineError) as caught:
            service.register_page(
                home=str(self.home), product=PRODUCT,
                snapshot=snapshot_id, audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")


# ----------------------------------------------------------------
# S17-R3-046: the evaluated page path stands under the guard.
# ----------------------------------------------------------------

class Test046EvaluatedPathGuard(SeededBase):

    def failure_values(self):
        return [payload.get("error_value")
                for payload in payloads_of_kind(
                    self.home, "failure_record")]

    def test_surrogate_evaluated_path_refused_in_vocabulary(self):
        with self.assertRaises(errors.CitelineError) as caught:
            service.audit(
                home=str(self.home), page_file=str(PAGE),
                evaluated_page_path="/p\ud800x",
                audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(self.failure_values(),
                         ["SUPPLIED_PATH_UNSAFE"])

    def test_nul_evaluated_path_refused_in_vocabulary(self):
        with self.assertRaises(errors.CitelineError) as caught:
            service.audit(
                home=str(self.home), page_file=str(PAGE),
                evaluated_page_path="/p\x00x",
                audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(self.failure_values(),
                         ["SUPPLIED_PATH_UNSAFE"])


# ----------------------------------------------------------------
# S17-R3-047: a bad audit date appends one failure record
# on the five failure record routes.
# ----------------------------------------------------------------

class Test047AuditDateFailureRecord(SeededBase):

    def assert_one_record(self, call):
        before = len(payloads_of_kind(self.home, "failure_record"))
        with self.assertRaises(errors.CitelineError) as caught:
            call()
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        after = len(payloads_of_kind(self.home, "failure_record"))
        self.assertEqual(after - before, 1)

    def test_audit_route(self):
        self.assert_one_record(lambda: service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date="2026-13-40"))

    def test_guide_route(self):
        self.assert_one_record(lambda: service.guide(
            home=str(self.home), run_id="run-99",
            audit_date="not-a-date"))

    def test_probe_report_route(self):
        self.assert_one_record(lambda: service.probe_report(
            home=str(self.home), product=PRODUCT, round=ROUND,
            audit_date="2026-02-30"))

    def test_probe_trend_route(self):
        self.assert_one_record(lambda: service.probe_trend(
            home=str(self.home), product=PRODUCT, round_a=ROUND,
            round_b="round-2", audit_date="2026-02-30"))

    def test_query_set_report_route(self):
        self.assert_one_record(lambda: service.query_set_report(
            home=str(self.home), product=PRODUCT,
            audit_date="not-a-date"))


# ----------------------------------------------------------------
# S17-R3-048: stored field validation over the non string
# answer fields its readers consume.
# ----------------------------------------------------------------

class Test048StoredFieldValidation(SeededBase):

    def setUp(self):
        super().setUp()
        answer = temp_file(
            self, "Acme Ledger is a ledger tool.\n", "answer.txt")
        do_import(self.home, answer)
        self.standing = payloads_of_kind(
            self.home, "answer_imported")[0]

    def append_swapped(self, **changes):
        payload = dict(self.standing)
        payload.update(changes)
        journal.append_entry(
            str(self.home), "answer_imported", payload,
            audit_date=AUDIT_DATE)

    def test_status_refuses_string_characters(self):
        self.append_swapped(
            answer_size={"characters": "many", "words": 3})
        with self.assertRaises(errors.CitelineError) as caught:
            service.status(home=str(self.home))
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")

    def test_status_refuses_oversize_characters(self):
        self.append_swapped(
            answer_size={"characters": 10 ** 400, "words": 3})
        with self.assertRaises(errors.CitelineError) as caught:
            service.status(home=str(self.home))
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")

    def test_probe_report_refuses_swapped_control_fields(self):
        self.append_swapped(control_flag="false", control_kind=123)
        with self.assertRaises(errors.CitelineError) as caught:
            service.probe_report(
                home=str(self.home), product=PRODUCT, round=ROUND,
                audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")


# ----------------------------------------------------------------
# S17-R3-049 and S17-R3-050: the plan file path judged at
# open, and the list_products home check.
# ----------------------------------------------------------------

class Test049PlanPathJudged(unittest.TestCase):

    def test_nul_plan_path_refused_in_vocabulary(self):
        with self.assertRaises(errors.CitelineError) as caught:
            watch.run_watch(plan_file="plan\x00.json")
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")

    def test_surrogate_plan_path_refused_in_vocabulary(self):
        with self.assertRaises(errors.CitelineError) as caught:
            watch.run_watch(plan_file="plan\ud800.json")
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")


class Test050ListProductsHomeCheck(unittest.TestCase):

    def test_nul_home_answers_home_missing(self):
        with self.assertRaises(errors.CitelineError) as caught:
            service.list_products(home="x\x00y")
        self.assertEqual(token_of(caught.exception), "HOME_MISSING")


# ----------------------------------------------------------------
# S17-R3-051: the picked watch round cost shape. The
# evidence test stands as an expected failure beside the
# refusal recorded in the seat paper: the per target cost
# grows with the journal the round itself writes, through
# full journal rehash scans no service or watch cure in
# this seat's family can remove.
# ----------------------------------------------------------------

def _child_append_failure_record(home, go_path, done_path):
    deadline = time.time() + 20
    while time.time() < deadline and not os.path.exists(go_path):
        time.sleep(0.02)
    try:
        journal.append_entry(
            home, "failure_record",
            {"operation": "probe report",
             "error_value": "UNKNOWN_ROUND",
             "subject_identity": "intervening",
             "date": AUDIT_DATE, "rule_fired": "UNKNOWN_ROUND"},
            audit_date=AUDIT_DATE)
    except Exception:
        pass
    with open(done_path, "w", encoding="utf-8") as handle:
        handle.write("done")


class Test051WatchCostShape(SeededBase):

    def make_plan(self, count):
        targets = []
        for index in range(count):
            page = temp_file(
                self, "# Acme\n\nAcme Ledger helps teams.\n",
                "page%d.md" % index)
            targets.append(
                {"product": PRODUCT, "page_file": str(page)})
        plan = {"home": str(self.home), "scope": "picked",
                "targets": targets, "audit_date": AUDIT_DATE}
        return temp_file(self, json.dumps(plan), "plan.json")

    def test_small_round_completes_correctly(self):
        result = watch.run_watch(plan_file=str(self.make_plan(3)))
        self.assertEqual(result["outcome_counts"]["completed"], 3)

    @unittest.expectedFailure
    def test_rehash_work_stays_linear_in_round_size(self):
        original = journal._entries_with_hash
        stats = {"entries": 0}

        def counting(scan):
            out = original(scan)
            stats["entries"] += len(out)
            return out

        with mock.patch.object(
                journal, "_entries_with_hash", counting):
            watch.run_watch(plan_file=str(self.make_plan(6)))
        # A cost shape linear in the round would rehash a
        # bounded number of entries per target; the round
        # as built rehashes the whole standing journal
        # several times per target, so the total grows
        # with the product of targets and journal size.
        self.assertLessEqual(stats["entries"], 150)


# ----------------------------------------------------------------
# S17-R3-052: the audit assembly snapshot identity and
# limits run identity resolved from the storing entries.
# ----------------------------------------------------------------

class Test052AuditAssemblyIdentity(SeededBase):

    def test_intervening_append_cannot_move_the_citation(self):
        root = Path(self.enterContext(
            tempfile.TemporaryDirectory()))
        go_path = str(root / "go")
        done_path = str(root / "done")
        context = multiprocessing.get_context("fork")
        child = context.Process(
            target=_child_append_failure_record,
            args=(str(self.home), go_path, done_path))
        child.start()
        real_batch = journal.append_entries_atomic

        def gated(home, entries, audit_date=None, run_id=None):
            with open(go_path, "w", encoding="utf-8") as handle:
                handle.write("go")
            deadline = time.time() + 20
            while time.time() < deadline \
                    and not os.path.exists(done_path):
                time.sleep(0.02)
            return real_batch(
                home, entries, audit_date=audit_date,
                run_id=run_id)

        try:
            with mock.patch.object(
                    journal, "append_entries_atomic", gated):
                record = service.audit(
                    home=str(self.home), page_file=str(PAGE),
                    audit_date=AUDIT_DATE)
        finally:
            child.join(timeout=20)
        snapshots = payloads_of_kind(self.home, "snapshot_registered")
        stored = payloads_of_kind(self.home, "audit_record")[-1]
        self.assertEqual(stored["snapshot_id"],
                         snapshots[-1]["snapshot_id"])
        self.assertEqual(record["snapshot_id"],
                         snapshots[-1]["snapshot_id"])
        self.assertEqual(
            stored["limits_in_force"]["run_id"], stored["run_id"])

    def test_ordinary_audit_citation_holds_control(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        snapshots = payloads_of_kind(self.home, "snapshot_registered")
        self.assertEqual(record["snapshot_id"],
                         snapshots[-1]["snapshot_id"])
        self.assertEqual(
            record["limits_in_force"]["run_id"], record["run_id"])


# ----------------------------------------------------------------
# S17-R3-059: the cadence interval reading stands inside
# the forms its own docstring states.
# ----------------------------------------------------------------

class Test059CadenceForms(unittest.TestCase):

    def test_non_latin_digits_read_no_interval(self):
        self.assertIsNone(watch._cadence_interval_days(
            "every ٧ days"))
        self.assertIsNone(watch._cadence_interval_days(
            "every ７ days"))

    def test_zero_interval_reads_no_interval(self):
        self.assertIsNone(watch._cadence_interval_days("every 0 days"))
        self.assertIsNone(watch._cadence_interval_days("0 days"))

    def test_bare_number_form_reads_no_interval(self):
        self.assertIsNone(watch._cadence_interval_days("7 days"))

    def test_stated_forms_still_read_control(self):
        self.assertEqual(watch._cadence_interval_days("every 7 days"), 7)
        self.assertEqual(watch._cadence_interval_days("weekly"), 7)
        self.assertEqual(
            watch._cadence_interval_days("every 2 weeks"), 14)


# ----------------------------------------------------------------
# S17-R3-060: the import route audit date stands under the
# service validator discipline and token.
# ----------------------------------------------------------------

class Test060ImportAuditDate(SeededBase):

    def answer(self):
        return temp_file(
            self, "Acme Ledger is a ledger tool.\n", "answer.txt")

    def test_datetime_audit_date_accepted_and_normalised(self):
        do_import(self.home, self.answer(), audit_date=datetime.datetime(
            2026, 11, 13, 23, 59))
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 1)

    def test_integer_audit_date_accepted_and_normalised(self):
        do_import(self.home, self.answer(), audit_date=20261113)
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 1)

    def test_bad_string_refused_under_service_token(self):
        with self.assertRaises(errors.CitelineError) as caught:
            do_import(self.home, self.answer(),
                      audit_date="14/11/2026")
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")


# ----------------------------------------------------------------
# S17-R3-061: the error vocabulary constructor enforces
# the closed set its module states.
# ----------------------------------------------------------------

class Test061VocabularyConstructor(unittest.TestCase):

    def test_unknown_token_refused(self):
        with self.assertRaises(ValueError):
            errors.CitelineError("x", token="NOPE_TOKEN")

    def test_row_token_mismatch_refused(self):
        with self.assertRaises(ValueError):
            errors.CitelineError(
                "x", token="VALIDATION_FAILED", row="U-1")

    def test_unhashable_token_refused_without_raw_type_error(self):
        with self.assertRaises(ValueError):
            errors.CitelineError("x", token=["VALIDATION_FAILED"])
        with self.assertRaises(ValueError):
            errors.CitelineError("x", row=["X-5"])

    def test_non_string_token_refused(self):
        with self.assertRaises(ValueError):
            errors.CitelineError("x", token=123)
        with self.assertRaises(ValueError):
            errors.CitelineError("x", token=b"VALIDATION_FAILED")

    def test_valid_forms_still_construct_control(self):
        exc = errors.CitelineError("x", token="VALIDATION_FAILED")
        self.assertEqual(exc.row, "X-5")
        self.assertEqual(exc.exit_code, 2)
        exc = errors.CitelineError("x", row="X-5")
        self.assertEqual(exc.token, "VALIDATION_FAILED")
        exc = errors.JournalError("a plain journal failure")
        self.assertIsNone(exc.token)


# ----------------------------------------------------------------
# S17-R3-064: the watch coverage count and the failure
# record surfacing assembly fold with corrections.
# ----------------------------------------------------------------

class Test064CorrectionsAwareReaders(SeededBase):

    def test_watch_coverage_count_reads_corrections(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        service.register_page(
            home=str(self.home), product=PRODUCT,
            snapshot=record["snapshot_id"], audit_date=AUDIT_DATE)
        products = service.list_products(home=str(self.home))
        count, _paths = watch._standing_product_page_snapshot_count(
            str(self.home), products)
        self.assertEqual(count, 1)
        registration = entries_of_kind(
            self.home, "snapshot_registered")[-1]
        corrected = dict(registration.get("payload") or {})
        corrected["is_product_page"] = False
        journal.append_entry(
            str(self.home), "correction",
            {"supersedes_sequence": registration["sequence"],
             "corrected_record": corrected},
            audit_date=AUDIT_DATE)
        count, _paths = watch._standing_product_page_snapshot_count(
            str(self.home), products)
        self.assertEqual(count, 0)

    def test_failure_surfacing_reads_corrections(self):
        with self.assertRaises(errors.CitelineError):
            service.probe_report(
                home=str(self.home), product=PRODUCT, round="nope",
                audit_date=AUDIT_DATE)
        failure = entries_of_kind(self.home, "failure_record")[-1]
        corrected = dict(failure.get("payload") or {})
        corrected["error_value"] = "CORRECTED_MARKER"
        corrected["rule_fired"] = "CORRECTED_MARKER"
        journal.append_entry(
            str(self.home), "correction",
            {"supersedes_sequence": failure["sequence"],
             "corrected_record": corrected},
            audit_date=AUDIT_DATE)
        result = service.status(home=str(self.home))
        values = [payload.get("error_value")
                  for payload in result.get("failure_records") or []]
        self.assertIn("CORRECTED_MARKER", values)
        self.assertNotIn("UNKNOWN_ROUND", values)


# ----------------------------------------------------------------
# S17-R3-067: the failure surfacing assembly stands a
# stored entry on its surface whatever its payload holds.
# ----------------------------------------------------------------

class Test067EmptyPayloadSurfaces(SeededBase):

    def test_empty_payload_failure_record_surfaces(self):
        journal.append_entry(
            str(self.home), "failure_record", {},
            audit_date=AUDIT_DATE)
        result = service.status(home=str(self.home))
        self.assertIn("failure_records", result)
        self.assertIn({}, result["failure_records"])


# ----------------------------------------------------------------
# S17-R3-068: one reading of the limits in force governs
# the audit statement and the extraction enforcement, the
# front matter family included.
# ----------------------------------------------------------------

class Test068FrontMatterLimitsPlumbing(SeededBase):

    def fm_page(self, value_chars=100, keys=1):
        lines = ["---"]
        for index in range(keys):
            lines.append("key%d: %s" % (index, "v" * value_chars))
        lines += ["---", "Acme Ledger helps teams track citations."]
        return temp_file(
            self, "\n".join(lines) + "\n", "page.md")

    def test_config_block_size_governs_extraction(self):
        journal.write_config(
            str(self.home), "front_matter_block_size = 1\n")
        page = self.fm_page(value_chars=3000)
        with self.assertRaises(errors.CitelineError) as caught:
            service.audit(
                home=str(self.home), page_file=str(page),
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_config_value_length_governs_extraction(self):
        journal.write_config(
            str(self.home),
            "front_matter_value_length_per_key = 10\n")
        page = self.fm_page(value_chars=100)
        with self.assertRaises(errors.CitelineError) as caught:
            service.audit(
                home=str(self.home), page_file=str(page),
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_import_value_length_governs_at_service_seam(self):
        journal.write_config(
            str(self.home),
            "front_matter_value_length_per_key = 10\n")
        answer = temp_file(
            self, "---\ntitle: %s\n---\nAcme Ledger answer text.\n"
            % ("v" * 100), "answer.txt")
        with self.assertRaises(errors.CitelineError) as caught:
            do_import(self.home, answer)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_import_key_count_governs_at_service_seam(self):
        journal.write_config(
            str(self.home), "front_matter_key_count = 5\n")
        lines = ["---"]
        lines += ["key%d: value" % i for i in range(10)]
        lines += ["---", "Acme Ledger answer text."]
        answer = temp_file(
            self, "\n".join(lines) + "\n", "answer.txt")
        with self.assertRaises(errors.CitelineError) as caught:
            do_import(self.home, answer)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
