"""Repair tests: service operations, clock, failure records.

Each test pins one repair queue item of the split
(the audit record, Section 3) in the service
locus, plus queue addition from the failing test
mapping paper. Dates are call inputs in every test.
Timing aspects stand under the cost bound carve out: the
clock tests patch the service clock seam, so they judge
logic, never elapsed wall time.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from citeline import errors, journal, service, watch
from citeline import install as install_module

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
PAGE = FIXTURES / "w7-page.md"
ROBOTS = FIXTURES / "w7-robots.txt"
ANSWER = FIXTURES / "w7-answer.txt"
PRODUCT = "Example Product"
ROUND = "round-1"
QUERY = "What is Example Product?"


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def seed_product(case, home):
    service.add_product(
        home=str(home), name=PRODUCT,
        canonical_line="Example Product answers questions with citations.",
        domain="example.com", audit_date=AUDIT_DATE)
    service.set_query_set(
        home=str(home), product=PRODUCT, query_set=[QUERY],
        audit_date=AUDIT_DATE)
    service.name_round(
        home=str(home), product=PRODUCT, round_label=ROUND,
        importer_declaration="operator", supplier_relation="first party",
        audit_date=AUDIT_DATE)
    return home


def seed_round(case, home):
    seed_product(case, home)
    service.probe_import(
        home=str(home), answer_file=str(ANSWER), product=PRODUCT,
        round=ROUND, engine_label="engine-a", query=QUERY,
        kind="real_sample", captured_on="2026-11-10",
        capture_method="manual copy", audit_date=AUDIT_DATE)
    return home


def entry_count(home):
    return service.status(home=str(home))["entry_count"]


def jumping_clock():
    state = {"calls": 0}

    def fake():
        state["calls"] += 1
        return 0.0 if state["calls"] == 1 else 10000.0

    return fake


class TestR19017NonAppendingFailures(unittest.TestCase):
    """The settled rule: the operations the brief names as non appending
    (probe report, probe trend, query-set-report) append no
    failure record on failure."""

    def test_failed_probe_report_appends_nothing(self):
        _, home = make_home(self)
        seed_product(self, home)
        before = entry_count(home)
        with self.assertRaises(Exception):
            service.probe_report(
                home=str(home), product=PRODUCT, round="no-such-round",
                audit_date=AUDIT_DATE)
        self.assertEqual(entry_count(home), before)

    def test_failed_probe_trend_appends_nothing(self):
        _, home = make_home(self)
        seed_product(self, home)
        before = entry_count(home)
        with self.assertRaises(Exception):
            service.probe_trend(
                home=str(home), product=PRODUCT, round_a="no-such-a",
                round_b="no-such-b", audit_date=AUDIT_DATE)
        self.assertEqual(entry_count(home), before)

    def test_failed_query_set_report_appends_nothing(self):
        _, home = make_home(self)
        seed_product(self, home)
        before = entry_count(home)
        with self.assertRaises(Exception):
            service.query_set_report(
                home=str(home), product="No Such Product",
                audit_date=AUDIT_DATE)
        self.assertEqual(entry_count(home), before)


class TestR19018ProbeReportDeterminism(unittest.TestCase):
    """The settled rule: standing failure record payloads stay out of
    the probe report record, so identical probe report calls
    return identical JSON however many failing calls
    intervened."""

    def test_probe_report_bytes_stable_across_failing_calls(self):
        _, home = make_home(self)
        seed_round(self, home)
        first = service.probe_report(
            home=str(home), product=PRODUCT, round=ROUND,
            form="agentic", audit_date=AUDIT_DATE)
        first_text = json.dumps(first, sort_keys=True)
        self.assertNotIn("failure_records", first_text)
        with self.assertRaises(Exception):
            service.audit(
                home=str(home), page_file=str(FIXTURES / "no-page.md"),
                audit_date=AUDIT_DATE)
        with self.assertRaises(Exception):
            service.guide(
                home=str(home), run_id="run-9999",
                audit_date=AUDIT_DATE)
        second = service.probe_report(
            home=str(home), product=PRODUCT, round=ROUND,
            form="agentic", audit_date=AUDIT_DATE)
        self.assertEqual(json.dumps(second, sort_keys=True), first_text)


class TestR19007StalenessRounds(unittest.TestCase):
    """The settled rule: the staleness view lists one row per standing
    round, so one imported round appears once."""

    def test_imported_round_appears_once(self):
        _, home = make_home(self)
        seed_round(self, home)
        view = service.staleness_view(home=str(home))
        rounds = [row for row in view["records"]
                  if row.get("record_kind") == "round"]
        self.assertEqual(len(rounds), 1)
        self.assertEqual(view["record_count"], len(view["records"]))


class TestR19009ImportPreflightSizeLimb(unittest.TestCase):
    """The settled rule: the import preflight reads
    total_home_size_remaining from the capacity_outlook
    nesting, so its limit 40 refusal can fire."""

    def test_preflight_limit_40_fires_from_nested_outlook(self):
        _, home = make_home(self)
        seed_product(self, home)
        snapshot = {"capacity_outlook": {"total_home_size_remaining": 10}}
        with mock.patch.object(
                journal, "status_snapshot", return_value=snapshot):
            with self.assertRaises(errors.CitelineError) as caught:
                service._import_preflight(home, str(ANSWER), 0)
        self.assertEqual(caught.exception.limit_number, 40)
        self.assertEqual(
            caught.exception.refusal_context, "import_preflight")


class TestR19011AuditCapContext(unittest.TestCase):
    """The settled rule: an audit refused at the journal cap carries
    the audit append cap context, not an import preflight
    refusal."""

    def test_audit_cap_refusal_names_audit(self):
        _, home = make_home(self)
        seed_product(self, home)
        current = entry_count(home)
        journal.write_config(
            home, "journal_length = %d\n" % current)
        with self.assertRaises(errors.CitelineError) as caught:
            service.audit(
                home=str(home), page_file=str(PAGE),
                audit_date=AUDIT_DATE)
        self.assertEqual(
            caught.exception.refusal_context, "audit_preflight")
        self.assertIn("audit", str(caught.exception))


class TestR19098StatusCapacityOutlook(unittest.TestCase):
    """The settled rule: the status capacity outlook carries no
    invented per entry kind division."""

    def test_status_outlook_has_no_by_entry_kind(self):
        _, home = make_home(self)
        seed_product(self, home)
        result = service.status(home=str(home))
        self.assertNotIn("by_entry_kind", result["capacity_outlook"])
        self.assertNotIn(
            "by_entry_kind_basis", result["capacity_outlook"])


class TestR19023GuideClockBound(unittest.TestCase):
    """The settled rule and the guide limb of the settled rule: the guide route
    reads the clock, so limit 41 aborts a guide call whose
    run passes the backstop in force."""

    def test_guide_aborts_past_the_backstop(self):
        _, home = make_home(self)
        seed_product(self, home)
        audit = service.audit(
            home=str(home), page_file=str(PAGE), audit_date=AUDIT_DATE)
        with mock.patch.object(service, "_clock", jumping_clock()):
            with self.assertRaises(errors.CitelineError) as caught:
                service.guide(
                    home=str(home), run_id=audit["run_id"],
                    audit_date=AUDIT_DATE)
        self.assertEqual(caught.exception.token, "LIMIT_EXCEEDED")


class TestR19010RemainingOperationsClock(unittest.TestCase):
    """The settled rule, remaining operations limb: guide, robots,
    robots preview, query-set-report, status, verify, and
    staleness read the clock, so limit 41 aborts them and
    limit 42 guards the robots file parse."""

    def assert_aborts(self, call):
        with mock.patch.object(service, "_clock", jumping_clock()):
            with self.assertRaises(errors.CitelineError) as caught:
                call()
        self.assertEqual(caught.exception.token, "LIMIT_EXCEEDED")

    def test_status_reads_the_clock(self):
        _, home = make_home(self)
        seed_product(self, home)
        self.assert_aborts(lambda: service.status(home=str(home)))

    def test_verify_reads_the_clock(self):
        _, home = make_home(self)
        seed_product(self, home)
        self.assert_aborts(lambda: service.verify(home=str(home)))

    def test_staleness_reads_the_clock(self):
        _, home = make_home(self)
        seed_product(self, home)
        self.assert_aborts(
            lambda: service.staleness_view(home=str(home)))

    def test_query_set_report_reads_the_clock(self):
        _, home = make_home(self)
        seed_product(self, home)
        self.assert_aborts(lambda: service.query_set_report(
            home=str(home), product=PRODUCT, audit_date=AUDIT_DATE))

    def test_robots_reads_the_clock(self):
        _, home = make_home(self)
        seed_product(self, home)
        self.assert_aborts(lambda: service.robots(
            home=str(home), robots_file=str(ROBOTS),
            audit_date=AUDIT_DATE))

    def test_robots_preview_reads_the_clock(self):
        _, home = make_home(self)
        seed_product(self, home)
        self.assert_aborts(lambda: service.robots_preview(
            home=str(home), first_robots_file=str(ROBOTS),
            second_robots_file=str(ROBOTS), audit_date=AUDIT_DATE))


class TestR19010WatchRoundClock(unittest.TestCase):
    """The settled rule, watch limb: run_watch enforces a round level
    clock, so a watch round aborts at the per run backstop."""

    def test_watch_round_aborts_past_the_backstop(self):
        _, home = make_home(self)
        seed_product(self, home)
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        plan = root / "plan.json"
        plan.write_text(json.dumps({
            "home": str(home), "scope": "picked",
            "audit_date": AUDIT_DATE, "form": "simple",
            "targets": [{"product": PRODUCT, "round": ROUND}],
        }), encoding="utf-8")
        with mock.patch.object(
                watch, "_clock", jumping_clock(), create=True):
            with self.assertRaises(errors.CitelineError) as caught:
                watch.run_watch(plan_file=str(plan))
        self.assertEqual(caught.exception.token, "LIMIT_EXCEEDED")


class TestU11AuditArtefactFields(unittest.TestCase):
    """ the Advanced audit artefact carries no
    facts_counts field; reporting adds no field the stored
    record does not trace."""

    def test_audit_record_carries_no_facts_counts(self):
        _, home = make_home(self)
        seed_product(self, home)
        record = service.audit(
            home=str(home), page_file=str(PAGE), audit_date=AUDIT_DATE)
        self.assertNotIn("facts_counts", record)


if __name__ == "__main__":
    unittest.main()
