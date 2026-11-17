"""Step 19 Phase 6 mop up tests.

Each class pins one remainder item of the Step 19 repair loop.
Tests were written before the fixes they pin. Dates are call
inputs in every test.
"""

import inspect
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from citeline import journal, service, shell, watch
from citeline import install as install_module

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
ANSWER = FIXTURES / "w7-answer.txt"
QUERY = "What is Example Product?"


def make_home(case, name="home"):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / ("install-" + name), root / name
    install_module.install(location=str(location), home=str(home))
    return root, home


def seed_product_and_round(case, home, product="p-alpha"):
    service.add_product(
        home=str(home), name=product, canonical_line=product + " line.",
        domain="example.com", audit_date=AUDIT_DATE)
    service.set_query_set(home=str(home), product=product,
                          query_set=[QUERY], audit_date=AUDIT_DATE)
    service.name_round(home=str(home), product=product,
                       round_label="round-1",
                       importer_declaration="operator",
                       supplier_relation="first party",
                       audit_date=AUDIT_DATE)
    return home


def entry_count(home):
    return service.status(home=str(home))["entry_count"]


class TestR19026ServiceForwarding(unittest.TestCase):
    """R19-026 remainder: the service route forwards its home
    into the import intake calls, so the answer file size limit
    in force governs the command line route and stands named
    in the refusal."""

    CONFIG = ("answer_file_size = 2\n"
              "extracted_text_length_per_page_or_answer = 5000000\n")

    def _seeded_home(self):
        root, home = make_home(self)
        journal.write_config(home, self.CONFIG)
        seed_product_and_round(self, home)
        return root, home

    def test_raised_limit_admits_a_larger_answer_file(self):
        root, home = self._seeded_home()
        path = Path(root) / "big-answer.txt"
        path.write_text(
            "This is a plain answer sentence about the product.\n"
            * 30000, encoding="utf-8")
        self.assertGreater(path.stat().st_size, 1024 * 1024)
        self.assertLess(path.stat().st_size, 2 * 1024 * 1024)
        record = service.probe_import(
            home=str(home), answer_file=str(path), product="p-alpha",
            round="round-1", engine_label="engine-a", query=QUERY,
            kind="real_sample", captured_on="2026-11-10",
            capture_method="manual copy", audit_date=AUDIT_DATE)
        self.assertIsNotNone(record)

    def test_refusal_names_the_limit_in_force(self):
        root, home = self._seeded_home()
        path = Path(root) / "huge-answer.txt"
        path.write_text("word " * 500000, encoding="utf-8")
        self.assertGreater(path.stat().st_size, 2 * 1024 * 1024)
        with self.assertRaises(Exception) as caught:
            service.probe_import(
                home=str(home), answer_file=str(path),
                product="p-alpha", round="round-1",
                engine_label="engine-a", query=QUERY,
                kind="real_sample", captured_on="2026-11-10",
                capture_method="manual copy", audit_date=AUDIT_DATE)
        self.assertIn("2 MiB", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
