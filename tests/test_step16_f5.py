"""Step 16 fix tests, builder F5: service validation and failure records.

Defects covered: D-09 (a refused repeated round trend leaves a
failure record), D-16 (status over a missing home refuses with
HOME_MISSING), D-17 (an empty query set admits no query at
import), D-18 (the audit date input is validated as a date on
every service route that takes it), and D-20 (guide selector
validation follows the exactly one rule).

Every test calls the service layer operations the shell calls,
in a fresh installed home of its own. Dates are call inputs.
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from citeline import errors, service, shell
from citeline import install as install_module

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = FIXTURES / "w7-page.md"
AUDIT_DATE = "2026-11-13"
PRODUCT = "Acme Ledger"
QUERY = "What is Acme Ledger?"
ROUND = "round-1"


def token_of(exc):
    return getattr(exc, "token", None) or getattr(
        exc, "error_value", None)


def exit_code_of(exc):
    code = getattr(exc, "exit_code", None)
    if code is not None:
        return code
    entry = errors.error_for_token(token_of(exc))
    return entry["exit_code"] if entry is not None else None


def journal_entries(home):
    path = Path(home) / "journal.jsonl"
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def entries_of_kind(home, kind):
    return [entry for entry in journal_entries(home)
            if entry.get("entry_kind") == kind]


def failure_records(home):
    return entries_of_kind(home, "failure_record")


class F5Case(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(
            tempfile.TemporaryDirectory()))
        self.home = self.root / "home"
        install_module.install(
            location=str(self.root / "install"),
            home=str(self.home))

    def seed_product(self, with_query_set=True):
        service.add_product(
            home=str(self.home), name=PRODUCT,
            canonical_line="Acme Ledger helps teams track citations.",
            domain="acme.example", audit_date=AUDIT_DATE)
        if with_query_set:
            service.set_query_set(
                home=str(self.home), product=PRODUCT,
                query_set=[QUERY], audit_date=AUDIT_DATE)
        service.name_round(
            home=str(self.home), product=PRODUCT, round_label=ROUND,
            importer_declaration="all captured",
            supplier_relation="independent party",
            audit_date=AUDIT_DATE)

    def answer_file(self, text="Acme Ledger is a ledger tool."):
        path = self.root / "answer.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def do_import(self, answer, **overrides):
        kwargs = {
            "home": str(self.home), "answer_file": str(answer),
            "product": PRODUCT, "round": ROUND,
            "engine_label": "Engine A", "query": QUERY,
            "kind": "real_sample", "captured_on": "2026-11-10",
            "capture_method": "manual copy",
            "audit_date": AUDIT_DATE,
        }
        kwargs.update(overrides)
        return service.probe_import(**kwargs)


class TestD09RepeatedTrendFailureRecord(F5Case):
    def test_repeated_trend_refuses_and_appends_one_failure_record(self):
        self.seed_product()
        before = len(failure_records(self.home))
        with self.assertRaises(Exception) as caught:
            service.probe_trend(
                home=str(self.home), product=PRODUCT,
                round_a=ROUND, round_b=ROUND,
                audit_date=AUDIT_DATE)
        exc = caught.exception
        self.assertEqual(token_of(exc), "ROUND_REPEATED")
        self.assertEqual(exit_code_of(exc), 2)
        records = failure_records(self.home)
        self.assertEqual(len(records), before + 1)
        payload = records[-1].get("payload") or {}
        self.assertEqual(payload.get("error_value"), "ROUND_REPEATED")
        self.assertEqual(payload.get("rule_fired"), "ROUND_REPEATED")
        self.assertEqual(payload.get("subject_identity"), ROUND)
        self.assertEqual(payload.get("date"), AUDIT_DATE)
        chain = service.verify(home=str(self.home))
        self.assertTrue(chain["passed"])

    def test_repeated_trend_through_the_shell_prints_the_value(self):
        self.seed_product()
        stream = io.StringIO()
        with redirect_stderr(stream):
            code = shell.main([
                "probe", "trend", "--home", str(self.home),
                "--product", PRODUCT, "--round_a", ROUND,
                "--round_b", ROUND, "--audit_date", AUDIT_DATE])
        self.assertEqual(code, 2)
        self.assertIn("ROUND_REPEATED", stream.getvalue())
        self.assertEqual(len(failure_records(self.home)), 1)


class TestD16StatusOverMissingHome(F5Case):
    def test_status_over_missing_home_refuses_home_missing(self):
        missing = self.root / "no-such-home"
        with self.assertRaises(Exception) as caught:
            service.status(home=str(missing))
        exc = caught.exception
        self.assertEqual(token_of(exc), "HOME_MISSING")
        self.assertEqual(exit_code_of(exc), 2)
        self.assertFalse(missing.exists())

    def test_status_over_missing_home_through_the_shell(self):
        missing = self.root / "no-such-home"
        stream = io.StringIO()
        with redirect_stderr(stream):
            code = shell.main([
                "status", "--home", str(missing)])
        self.assertEqual(code, 2)
        self.assertIn("HOME_MISSING", stream.getvalue())
        self.assertFalse(missing.exists())

    def test_status_over_standing_home_still_reports(self):
        self.seed_product()
        state = service.status(home=str(self.home))
        self.assertEqual(state["chain_result"], "chain verifies")
        self.assertGreaterEqual(state["entry_count"], 1)

    def test_status_over_broken_chain_home_still_reports(self):
        self.seed_product()
        journal_path = Path(self.home) / "journal.jsonl"
        text = journal_path.read_text(encoding="utf-8")
        self.assertIn("Acme Ledger", text)
        journal_path.write_text(
            text.replace("Acme Ledger", "Bcme Ledger", 1),
            encoding="utf-8")
        state = service.status(home=str(self.home))
        self.assertTrue(state["chain_fails"])
        self.assertEqual(state["chain_result"], "chain fails verify")


class TestD17EmptyQuerySet(F5Case):
    def test_empty_query_set_refuses_any_query_at_import(self):
        self.seed_product(with_query_set=False)
        with self.assertRaises(Exception) as caught:
            self.do_import(self.answer_file(),
                           query="Anything at all?")
        exc = caught.exception
        self.assertEqual(token_of(exc), "IMPORT_VALIDATION_FAILED")
        self.assertEqual(exit_code_of(exc), 2)
        self.assertEqual(entries_of_kind(self.home, "answer_imported"),
                         [])
        records = failure_records(self.home)
        self.assertEqual(len(records), 1)
        payload = records[-1].get("payload") or {}
        self.assertEqual(payload.get("error_value"),
                         "IMPORT_VALIDATION_FAILED")

    def test_listed_query_still_imports_for_a_standing_set(self):
        self.seed_product(with_query_set=True)
        record = self.do_import(self.answer_file())
        self.assertEqual(record["query"], QUERY)
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 1)


class TestD18AuditDateValidation(F5Case):
    def assert_bad_date_refused(self, call):
        with self.assertRaises(Exception) as caught:
            call()
        exc = caught.exception
        self.assertEqual(token_of(exc), "VALIDATION_FAILED")
        self.assertEqual(exit_code_of(exc), 2)

    def test_add_product_refuses_a_non_date_audit_date(self):
        before = len(journal_entries(self.home))
        self.assert_bad_date_refused(lambda: service.add_product(
            home=str(self.home), name=PRODUCT,
            canonical_line="Acme Ledger helps teams.",
            domain="acme.example", audit_date="banana"))
        self.assertEqual(len(journal_entries(self.home)), before)
        self.assertEqual(service.list_products(home=str(self.home)),
                         [])

    def test_audit_refuses_a_non_date_audit_date_and_stores_nothing(self):
        self.seed_product()
        before = len(journal_entries(self.home))
        self.assert_bad_date_refused(lambda: service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date="banana"))
        self.assertEqual(len(journal_entries(self.home)), before)

    def test_probe_report_refuses_a_non_date_audit_date(self):
        self.seed_product()
        self.assert_bad_date_refused(lambda: service.probe_report(
            home=str(self.home), product=PRODUCT, round=ROUND,
            audit_date="14 Nov 2026"))

    def test_every_other_audit_date_route_refuses_a_non_date(self):
        self.seed_product()
        self.assert_bad_date_refused(lambda: service.name_round(
            home=str(self.home), product=PRODUCT,
            round_label="round-2",
            importer_declaration="all captured",
            supplier_relation="independent party",
            audit_date="banana"))
        self.assert_bad_date_refused(lambda: service.set_query_set(
            home=str(self.home), product=PRODUCT, query_set=[QUERY],
            audit_date="banana"))
        self.assert_bad_date_refused(lambda: service.probe_trend(
            home=str(self.home), product=PRODUCT, round_a=ROUND,
            round_b=ROUND, audit_date="banana"))
        self.assert_bad_date_refused(lambda: service.query_set_report(
            home=str(self.home), product=PRODUCT,
            audit_date="banana"))
        self.assert_bad_date_refused(lambda: service.guide(
            home=str(self.home), product=PRODUCT, round_label=ROUND,
            audit_date="banana"))
        self.assert_bad_date_refused(lambda: service.robots(
            home=str(self.home),
            robots_file=str(FIXTURES / "w7-robots.txt"),
            audit_date="banana"))

    def test_valid_iso_audit_date_still_accepted(self):
        self.seed_product()
        report = service.probe_report(
            home=str(self.home), product=PRODUCT, round=ROUND,
            audit_date=AUDIT_DATE)
        self.assertTrue(report)


class TestD20GuideSelectors(F5Case):
    def assert_malformed(self, call):
        with self.assertRaises(Exception) as caught:
            call()
        exc = caught.exception
        self.assertEqual(token_of(exc), "MALFORMED_CALL")
        self.assertEqual(exit_code_of(exc), 2)

    def test_both_selectors_named_is_a_malformed_call(self):
        self.seed_product()
        # The malformed ruling fires ahead of any run lookup,
        # so the run identity here needs no standing record.
        self.assert_malformed(lambda: service.guide(
            home=str(self.home), run_id="run-77",
            product=PRODUCT, round_label=ROUND,
            audit_date=AUDIT_DATE))

    def test_neither_selector_named_is_a_malformed_call(self):
        self.seed_product()
        self.assert_malformed(lambda: service.guide(
            home=str(self.home), audit_date=AUDIT_DATE))

    def test_half_of_the_round_selector_is_a_malformed_call(self):
        self.seed_product()
        self.assert_malformed(lambda: service.guide(
            home=str(self.home), product=PRODUCT,
            audit_date=AUDIT_DATE))
        self.assert_malformed(lambda: service.guide(
            home=str(self.home), round_label=ROUND,
            audit_date=AUDIT_DATE))

    def test_unknown_run_identity_carries_unknown_round(self):
        self.seed_product()
        with self.assertRaises(Exception) as caught:
            service.guide(
                home=str(self.home), run_id="run-999",
                audit_date=AUDIT_DATE)
        exc = caught.exception
        self.assertEqual(token_of(exc), "UNKNOWN_ROUND")
        self.assertEqual(exit_code_of(exc), 2)

    def test_unknown_round_label_carries_unknown_round(self):
        self.seed_product()
        with self.assertRaises(Exception) as caught:
            service.guide(
                home=str(self.home), product=PRODUCT,
                round_label="round-nope", audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "UNKNOWN_ROUND")

    def test_each_single_selector_still_guides(self):
        self.seed_product()
        # A stored audit record stands seeded directly through
        # the journal, in integer figures only, so this selector
        # control stands apart from the checks scoring shape.
        from citeline import journal
        product_id = service.list_products(
            home=str(self.home))[0]["product_id"]
        journal.append_entry(
            str(self.home), "audit_record",
            {"run_id": "run-77", "product_id": product_id,
             "product_name": PRODUCT,
             "canonical_line":
                 "Acme Ledger helps teams track citations.",
             "audit_date": AUDIT_DATE, "sentences": [],
             "trigger_codes": [],
             "distinct_cited_target_count": 0,
             "score": {"value": 50, "band": "thin",
                       "cap_status": False}},
            audit_date=AUDIT_DATE)
        by_run = service.guide(
            home=str(self.home), run_id="run-77",
            audit_date=AUDIT_DATE)
        self.assertIn("guide_id", by_run)
        self.assertEqual(by_run["source_run_id"], "run-77")
        by_round = service.guide(
            home=str(self.home), product=PRODUCT, round_label=ROUND,
            audit_date=AUDIT_DATE)
        self.assertIn("guide_id", by_round)


if __name__ == "__main__":
    unittest.main()
