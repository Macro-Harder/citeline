"""Step 16 fix F3 tests: D-03 register page standing snapshot and D-04 watch coverage.

Written test first for the round 1 defects D-03 and D-04.
D-03 oracle: brief Section 5.2 PageSnapshot shape and
Section 5.12 item 136, registration sets is_product_page on
the standing PageSnapshot named by its snapshot_id for that
product, and plan joined entry 13 row X-5, token
VALIDATION_FAILED, usage class, exit code 2, failure record
appended where the chain accepts appends, the row this fix
chooses for an identifier naming no standing snapshot for
the product, stated in the fix paper.
D-04 oracle: plan Section 5.1 WatchRun coverage statement,
registered product page snapshots counted against snapshots
audited, computed from registry and journal facts.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from citeline import journal, service, watch

AUDIT_DATE = "2026-11-14"
PRODUCT = "Example Product"
CANONICAL = "The reference sentence that must match verbatim."
FIXTURES = Path(__file__).parent / "fixtures"
PAGE = FIXTURES / "w7-page.md"


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def entries_of_kind(home, kind):
    out = []
    for entry in journal.fold(str(home)):
        if isinstance(entry, dict):
            entry_kind = entry.get("entry_kind")
            payload = entry.get("payload") or {}
        else:
            entry_kind = getattr(entry, "entry_kind", None)
            payload = getattr(entry, "payload", {}) or {}
        if entry_kind == kind:
            out.append(payload)
    return out


class F3Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def add_default(self, name=PRODUCT):
        return service.add_product(
            home=self.home, name=name, canonical_line=CANONICAL,
            domain="example.invalid", audit_date=AUDIT_DATE)

    def make_page(self):
        page = os.path.join(self.tmp.name, "page.md")
        with open(page, "w", encoding="utf-8") as handle:
            handle.write("# Example Product\n\n"
                         "Example Product answers questions "
                         "with citations.\n")
        return page

    def audit_and_register(self):
        product = self.add_default()
        page = self.make_page()
        audit = service.audit(home=self.home, page_file=page,
                              audit_date=AUDIT_DATE)
        snapshot_id = field(audit, "snapshot_id")
        registered = service.register_page(
            home=self.home, product=PRODUCT, snapshot=snapshot_id,
            audit_date=AUDIT_DATE)
        return product, page, audit, registered


class TestD03RegisterPage(F3Base):
    def test_page_file_path_as_snapshot_is_refused(self):
        self.add_default()
        page = self.make_page()
        with self.assertRaises(Exception) as caught:
            service.register_page(
                home=self.home, product=PRODUCT, snapshot=page,
                audit_date=AUDIT_DATE)
        exc = caught.exception
        token = getattr(exc, "error_value", None) or getattr(
            exc, "token", None)
        self.assertEqual(token, "VALIDATION_FAILED")
        self.assertEqual(getattr(exc, "row", None), "X-5")
        self.assertEqual(getattr(exc, "exit_code", None), 2)
        self.assertEqual(getattr(exc, "precedence_class", None),
                         getattr(exc, "error_class", "usage"))
        self.assertEqual(
            entries_of_kind(self.home, "snapshot_registered"), [])
        failures = entries_of_kind(self.home, "failure_record")
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].get("error_value"),
                         "VALIDATION_FAILED")
        self.assertEqual(failures[0].get("operation"),
                         "register_page")

    def test_invented_snapshot_is_refused(self):
        self.add_default()
        with self.assertRaises(Exception) as caught:
            service.register_page(
                home=self.home, product=PRODUCT, snapshot="snap-999",
                audit_date=AUDIT_DATE)
        token = getattr(caught.exception, "error_value", None) \
            or getattr(caught.exception, "token", None)
        self.assertEqual(token, "VALIDATION_FAILED")
        self.assertEqual(
            entries_of_kind(self.home, "snapshot_registered"), [])

    def test_session_order_register_before_audit_fails_at_register(self):
        self.add_default()
        page = self.make_page()
        with self.assertRaises(Exception):
            service.register_page(
                home=self.home, product=PRODUCT, snapshot=page,
                audit_date=AUDIT_DATE)
        grounds = service.estate_grounds(
            home=self.home, product=PRODUCT)
        self.assertIsNone(grounds.get("page_path"))

    def test_bad_registration_does_not_displace_sound_one(self):
        product, page, audit, registered = self.audit_and_register()
        before = entries_of_kind(self.home, "snapshot_registered")
        with self.assertRaises(Exception) as caught:
            service.register_page(
                home=self.home, product=PRODUCT, snapshot="snap-999",
                audit_date=AUDIT_DATE)
        token = getattr(caught.exception, "error_value", None) \
            or getattr(caught.exception, "token", None)
        self.assertEqual(token, "VALIDATION_FAILED")
        after = entries_of_kind(self.home, "snapshot_registered")
        self.assertEqual(after, before)
        grounds = service.estate_grounds(
            home=self.home, product=PRODUCT)
        self.assertEqual(grounds.get("page_path"), page)

    def test_snapshot_of_another_product_is_refused(self):
        first, page, audit, registered = self.audit_and_register()
        other = service.add_product(
            home=self.home, name="Other Product",
            canonical_line="Other line.", domain="other.invalid",
            audit_date=AUDIT_DATE)
        snapshot_id = field(audit, "snapshot_id")
        with self.assertRaises(Exception) as caught:
            service.register_page(
                home=self.home, product="Other Product",
                snapshot=snapshot_id, audit_date=AUDIT_DATE)
        token = getattr(caught.exception, "error_value", None) \
            or getattr(caught.exception, "token", None)
        self.assertEqual(token, "VALIDATION_FAILED")

    def test_success_carries_full_page_snapshot_shape(self):
        product, page, audit, registered = self.audit_and_register()
        self.assertTrue(field(registered, "is_product_page"))
        self.assertEqual(field(registered, "supplied_path"), page)
        self.assertTrue(field(registered, "sha256"))
        self.assertTrue(field(registered, "format"))
        stored = entries_of_kind(self.home, "snapshot_registered")
        standing = [p for p in stored
                    if p.get("snapshot_id")
                    == field(audit, "snapshot_id")
                    and p.get("is_product_page")]
        self.assertTrue(standing)
        self.assertEqual(standing[-1].get("supplied_path"), page)
        self.assertTrue(standing[-1].get("sha256"))
        self.assertTrue(standing[-1].get("format"))
        grounds = service.estate_grounds(
            home=self.home, product=PRODUCT)
        self.assertEqual(grounds.get("page_path"), page)


class TestD04WatchCoverage(unittest.TestCase):
    def test_clean_home_coverage_counts_standing_snapshots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            home.mkdir(parents=True)
            for name in ("p-alpha", "p-beta"):
                service.add_product(
                    home=str(home), name=name,
                    canonical_line=name + " line.",
                    domain="example.com", audit_date=AUDIT_DATE)
            audit = service.audit(home=str(home),
                                  page_file=str(PAGE),
                                  audit_date=AUDIT_DATE)
            service.register_page(
                home=str(home), product="p-alpha",
                snapshot=audit["snapshot_id"],
                audit_date=AUDIT_DATE)
            plan = {"home": str(home), "scope": "estate",
                    "audit_date": AUDIT_DATE, "form": "simple"}
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan),
                                 encoding="utf-8")
            result = watch.run_watch(plan_file=str(plan_path))
            coverage = result["coverage_statement"]
            self.assertEqual(
                coverage["product_page_snapshots"]["count"], 1)
            self.assertEqual(
                coverage["snapshots_audited"]["count"], 1)
            self.assertEqual(
                coverage["snapshots_audited"]["denominator"], 1)


if __name__ == "__main__":
    unittest.main()
