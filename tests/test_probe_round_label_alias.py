"""Repair tests: the round label alias on probe calls.

Oracle: the settled rule.
The round_label spelling names the round on probe import, probe
report, and probe trend, as it does on name-round and guide, and
the round spelling names the first round on probe trend.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from citeline import install as install_module
from citeline import service, shell

AUDIT_DATE = "2026-11-17"


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location = root / "install"
    home = root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def run_shell(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        code = shell.main(argv)
    return code, out.getvalue(), err.getvalue()


def seed(case, home, rounds=("round-1",)):
    service.add_product(
        home=str(home), name="Example Product",
        canonical_line="Example Product answers questions.",
        domain="example.com", audit_date=AUDIT_DATE)
    for label in rounds:
        service.name_round(
            home=str(home), product="Example Product",
            round_label=label, importer_declaration="operator",
            supplier_relation="first party", audit_date=AUDIT_DATE)


class TestProbeRoundLabelAlias(unittest.TestCase):

    def test_probe_report_round_label_accepted(self):
        _root, home = make_home(self)
        seed(self, home)
        code, _out, err = run_shell(
            ["probe", "report", "--home", str(home),
             "--product", "Example Product",
             "--round_label", "round-1",
             "--audit_date", AUDIT_DATE, "--form", "simple"])
        self.assertNotIn("MALFORMED_CALL", err)
        self.assertEqual(code, 0, err)

    def test_probe_import_round_label_accepted(self):
        root, home = make_home(self)
        service.add_product(
            home=str(home), name="Example Product",
            canonical_line="Example Product answers questions.",
            domain="example.com",
            query_set=["What is Example Product?"],
            audit_date=AUDIT_DATE)
        service.name_round(
            home=str(home), product="Example Product",
            round_label="round-1", importer_declaration="operator",
            supplier_relation="first party", audit_date=AUDIT_DATE)
        answer = root / "answer.txt"
        answer.write_text(
            "Example Product is a citation auditing tool.\n",
            encoding="utf-8")
        code, _out, err = run_shell(
            ["probe", "import", "--home", str(home),
             "--answer_file", str(answer),
             "--product", "Example Product",
             "--round_label", "round-1",
             "--engine_label", "Fixture Engine",
             "--query", "What is Example Product?",
             "--kind", "fixture",
             "--captured_on", "2026-11-16",
             "--capture_method", "manual copy",
             "--control_designation", "positive",
             "--audit_date", AUDIT_DATE, "--form", "simple"])
        self.assertNotIn("MALFORMED_CALL", err)
        self.assertEqual(code, 0, err)

    def test_probe_trend_round_spelling_accepted(self):
        _root, home = make_home(self)
        seed(self, home, rounds=("round-1", "round-2"))
        code, _out, err = run_shell(
            ["probe", "trend", "--home", str(home),
             "--product", "Example Product",
             "--round", "round-1", "--round_b", "round-2",
             "--audit_date", AUDIT_DATE, "--form", "simple"])
        self.assertNotIn("MALFORMED_CALL", err)
        self.assertEqual(code, 0, err)

    def test_probe_trend_round_label_spelling_accepted(self):
        _root, home = make_home(self)
        seed(self, home, rounds=("round-1", "round-2"))
        code, _out, err = run_shell(
            ["probe", "trend", "--home", str(home),
             "--product", "Example Product",
             "--round_label", "round-1", "--round_b", "round-2",
             "--audit_date", AUDIT_DATE, "--form", "simple"])
        self.assertNotIn("MALFORMED_CALL", err)
        self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()
