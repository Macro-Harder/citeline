"""Step 16 supplementary fix wave, builder G5: audit invocation.

Defects pinned here, failing tests first:
E-05, the D-29 run_id form silently disregards fresh inputs
named beside it. A call naming run_id together with any fresh
audit input (page file, robots file, audit date, evaluated
page path, or product) refuses MALFORMED_CALL at row U-8,
exit 2. Through the shell the refusal carries the standing
shell outcome: the value printed, the subcommand list in
full, and one failure record where the chain accepts
appends. run_id alone, in any of the three forms, renders
the stored record and appends nothing, and a fresh call
without run_id audits exactly as before.
E-06, an audit omitting audit_date stores audit_date null
with audit_date_is_run_date true and no defaulted recording,
and freshness scores FRESH_NO_DATE. Brief Section 6.2 M1
requires the default to be the current UTC date, recorded
as defaulted and naming the date used: the stored record
carries audit_date set to the current UTC date and
audit_date_defaulted true beside it, a supplied date is
recorded as supplied with audit_date_defaulted false, and
freshness computes on the date used.
"""

import contextlib
import datetime
import io
import json
import tempfile
import unittest
from pathlib import Path

from citeline import journal, service, shell
from citeline import install as install_module

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
OTHER_DATE = "2020-01-01"
PRODUCT = "Example Product"
CANONICAL = "Example Product answers questions with citations."
PAGE = FIXTURES / "w7-page.md"
PAGE_STRONG = FIXTURES / "w6-page-strong.md"
ROBOTS = FIXTURES / "w7-robots.txt"

LIST_MARKERS = (
    "add-product", "register-page", "probe import",
    "probe trend", "query-set-report", "guide", "verify",
    "status", "watch",
)


def today_utc():
    return datetime.datetime.now(
        datetime.timezone.utc).date().isoformat()


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def seed_product(home):
    service.add_product(
        home=str(home), name=PRODUCT, canonical_line=CANONICAL,
        domain="example.com", audit_date=AUDIT_DATE)


def run_shell(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        code = shell.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def failure_records(home):
    return [entry for entry in journal.fold(str(home))
            if entry.get("entry_kind") == "failure_record"]


def audit_records(home):
    return [entry for entry in journal.fold(str(home))
            if entry.get("entry_kind") == "audit_record"]


def token_of(exc):
    record = service.recorded_error(exc)
    return record.get("error_value"), record.get("row"), \
        record.get("exit_code")


class G5Base(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)
        seed_product(self.home)
        self.record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        self.run_id = self.record["run_id"]

    def entry_count(self):
        return service.status(home=str(self.home))["entry_count"]


class TestE05RunIdBesideFreshInputs(G5Base):
    """E-05: no fresh input named beside a run identity is
    silently disregarded; the call refuses as malformed."""

    def assert_malformed_service_call(self, **kwargs):
        before = self.entry_count()
        audits_before = len(audit_records(self.home))
        with self.assertRaises(Exception) as caught:
            service.audit(home=str(self.home),
                          run_id=self.run_id, **kwargs)
        value, row, exit_code = token_of(caught.exception)
        self.assertEqual(value, "MALFORMED_CALL")
        self.assertEqual(row, "U-8")
        self.assertEqual(exit_code, 2)
        self.assertEqual(self.entry_count(), before)
        self.assertEqual(len(audit_records(self.home)),
                         audits_before)

    def test_different_page_file_beside_run_id_refuses(self):
        self.assert_malformed_service_call(
            page_file=str(PAGE_STRONG))

    def test_same_page_file_beside_run_id_refuses(self):
        self.assert_malformed_service_call(page_file=str(PAGE))

    def test_nonexistent_page_file_beside_run_id_refuses(self):
        self.assert_malformed_service_call(
            page_file=str(self.root / "no-such-page.md"))

    def test_directory_as_page_file_beside_run_id_refuses(self):
        self.assert_malformed_service_call(
            page_file=str(self.root))

    def test_robots_file_beside_run_id_refuses(self):
        self.assert_malformed_service_call(
            robots_file=str(ROBOTS))

    def test_different_audit_date_beside_run_id_refuses(self):
        self.assert_malformed_service_call(
            audit_date=OTHER_DATE)

    def test_same_audit_date_beside_run_id_refuses(self):
        self.assert_malformed_service_call(
            audit_date=AUDIT_DATE)

    def test_evaluated_page_path_beside_run_id_refuses(self):
        self.assert_malformed_service_call(
            evaluated_page_path="/somewhere/else")

    def test_product_beside_run_id_refuses(self):
        self.assert_malformed_service_call(product=PRODUCT)

    def test_non_date_beside_run_id_still_refuses_as_non_date(self):
        # The D-18 cure stands ahead of the E-05 refusal: a
        # value that is not a date refuses VALIDATION_FAILED,
        # as it did before this cure.
        with self.assertRaises(Exception) as caught:
            service.audit(home=str(self.home),
                          run_id=self.run_id,
                          audit_date="banana")
        value, _row, exit_code = token_of(caught.exception)
        self.assertEqual(value, "VALIDATION_FAILED")
        self.assertEqual(exit_code, 2)

    def assert_malformed_shell_call(self, extra):
        before_failures = len(failure_records(self.home))
        audits_before = len(audit_records(self.home))
        code, out, err = run_shell(
            ["audit", "--home", str(self.home),
             "--run_id", self.run_id] + extra)
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)
        for marker in LIST_MARKERS:
            self.assertIn(marker, out + err)
        self.assertEqual(len(audit_records(self.home)),
                         audits_before)
        records = failure_records(self.home)
        self.assertEqual(len(records), before_failures + 1)
        payload = records[-1].get("payload") or {}
        self.assertEqual(payload.get("error_value"),
                         "MALFORMED_CALL")

    def test_shell_page_file_beside_run_id_refuses(self):
        self.assert_malformed_shell_call(
            ["--page_file", str(PAGE_STRONG)])

    def test_shell_nonexistent_page_beside_run_id_refuses(self):
        self.assert_malformed_shell_call(
            ["--page_file", str(self.root / "missing.md")])

    def test_shell_robots_file_beside_run_id_refuses(self):
        self.assert_malformed_shell_call(
            ["--robots_file", str(ROBOTS)])

    def test_shell_audit_date_beside_run_id_refuses(self):
        self.assert_malformed_shell_call(
            ["--audit_date", OTHER_DATE])

    def test_shell_evaluated_path_beside_run_id_refuses(self):
        self.assert_malformed_shell_call(
            ["--evaluated_page_path", "/somewhere/else"])


class TestE05RunIdAloneAndFreshCalls(G5Base):
    """E-05 standing limbs: run_id alone renders the stored
    record in every form and appends nothing; a fresh call
    without run_id audits as before; the D-08 boundary stands
    (page file required exactly where the call names neither
    a page file nor a run identity)."""

    def test_service_run_id_alone_renders_stored_record(self):
        before = self.entry_count()
        again = service.audit(home=str(self.home),
                              run_id=self.run_id)
        self.assertEqual(self.entry_count(), before)
        self.assertEqual(again["run_id"], self.run_id)
        self.assertEqual(again["checks"], self.record["checks"])
        self.assertEqual(again["score"], self.record["score"])
        self.assertEqual(again["audit_date"], AUDIT_DATE)

    def test_shell_run_id_alone_renders_in_all_three_forms(self):
        for form in ("simple", "advanced", "agentic"):
            with self.subTest(form=form):
                before = self.entry_count()
                code, out, err = run_shell(
                    ["audit", "--home", str(self.home),
                     "--run_id", self.run_id, "--form", form])
                self.assertEqual(code, 0, err)
                self.assertEqual(self.entry_count(), before)
                self.assertIn(self.run_id, out)

    def test_unknown_run_id_alone_refuses_unknown_round(self):
        before = self.entry_count()
        with self.assertRaises(Exception) as caught:
            service.audit(home=str(self.home),
                          run_id="run-9999")
        value, _row, exit_code = token_of(caught.exception)
        self.assertEqual(value, "UNKNOWN_ROUND")
        self.assertEqual(exit_code, 2)
        self.assertEqual(self.entry_count(), before)

    def test_fresh_call_without_run_id_creates_a_new_run(self):
        before = self.entry_count()
        fresh = service.audit(home=str(self.home),
                              page_file=str(PAGE),
                              audit_date=AUDIT_DATE)
        self.assertGreater(self.entry_count(), before)
        self.assertNotEqual(fresh["run_id"], self.run_id)

    def test_shell_audit_with_neither_input_is_malformed(self):
        code, _out, err = run_shell(
            ["audit", "--home", str(self.home)])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)
        self.assertIn("page_file", err)


class TestE06AuditDateDefault(unittest.TestCase):
    """E-06: brief Section 6.2 M1. An omitted audit_date takes
    the current UTC date as the run date, the stored record
    carries audit_date_defaulted true naming that date in
    audit_date, and freshness computes on that date."""

    def setUp(self):
        self.root, self.home = make_home(self)
        seed_product(self.home)

    def freshness(self, record):
        for check in record["checks"]:
            if check.get("check_id") == "freshness":
                return check
        self.fail("no freshness check stands in the record")

    def stored_payload(self, run_id):
        for entry in audit_records(self.home):
            payload = entry.get("payload") or {}
            if payload.get("run_id") == run_id:
                return payload
        self.fail("no stored audit record for %s" % run_id)

    def test_omitted_date_defaults_to_current_utc_date(self):
        record = service.audit(home=str(self.home),
                               page_file=str(PAGE))
        self.assertEqual(record["audit_date"], today_utc())
        self.assertIs(record["audit_date_defaulted"], True)

    def test_omitted_date_default_is_stored_not_only_returned(self):
        record = service.audit(home=str(self.home),
                               page_file=str(PAGE))
        stored = self.stored_payload(record["run_id"])
        self.assertEqual(stored["audit_date"], today_utc())
        self.assertIs(stored["audit_date_defaulted"], True)
        self.assertIs(stored["audit_date_is_run_date"], True)

    def test_omitted_date_is_run_date_true_by_construction(self):
        # M1 beside IM7-BRK-2: where the audit date was itself
        # defaulted the boolean is true by construction,
        # because the default audit date is the current UTC
        # date the run runs on.
        record = service.audit(home=str(self.home),
                               page_file=str(PAGE))
        self.assertEqual(record["audit_date"], today_utc())
        self.assertIs(record["audit_date_is_run_date"], True)

    def test_freshness_computes_on_the_defaulted_date(self):
        # The strong page carries the date 2026-11-01 in its
        # text. Against the current UTC date that date stands
        # inside the 90 day full credit band on the day this
        # suite runs beside the build (2026-11-14), so the
        # check earns on age, not on absence of a date.
        record = service.audit(home=str(self.home),
                               page_file=str(PAGE_STRONG))
        check = self.freshness(record)
        self.assertNotEqual(check["reason_code"],
                            "FRESH_NO_DATE")
        self.assertEqual(check["reason_code"], "FRESH_OK")
        self.assertEqual(check["earned"], 1.0)

    def test_supplied_date_recorded_as_supplied(self):
        record = service.audit(home=str(self.home),
                               page_file=str(PAGE),
                               audit_date=AUDIT_DATE)
        self.assertEqual(record["audit_date"], AUDIT_DATE)
        self.assertIs(record["audit_date_defaulted"], False)
        self.assertIs(record["audit_date_is_run_date"], True)
        stored = self.stored_payload(record["run_id"])
        self.assertEqual(stored["audit_date"], AUDIT_DATE)
        self.assertIs(stored["audit_date_defaulted"], False)

    def test_non_date_still_refuses_and_stores_nothing(self):
        before = len(audit_records(self.home))
        with self.assertRaises(Exception) as caught:
            service.audit(home=str(self.home),
                          page_file=str(PAGE),
                          audit_date="banana")
        value, _row, exit_code = token_of(caught.exception)
        self.assertEqual(value, "VALIDATION_FAILED")
        self.assertEqual(exit_code, 2)
        self.assertEqual(len(audit_records(self.home)), before)

    def test_shell_omitted_date_records_the_default(self):
        code, out, err = run_shell(
            ["audit", "--home", str(self.home),
             "--page_file", str(PAGE), "--form", "advanced"])
        self.assertEqual(code, 0, err)
        body = json.loads(out)
        self.assertEqual(body["audit_date"], today_utc())
        self.assertIs(body["audit_date_defaulted"], True)

    def test_shell_simple_form_names_the_defaulted_date(self):
        code, out, err = run_shell(
            ["audit", "--home", str(self.home),
             "--page_file", str(PAGE)])
        self.assertEqual(code, 0, err)
        self.assertIn("audit_date: %s" % today_utc(), out)


if __name__ == "__main__":
    unittest.main()
