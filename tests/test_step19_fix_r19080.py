"""Step 19 fix tests for R19-080: the worksheet export surface.

Oracle: register item R19-080, plan S5, and brief CL19-132,
CL19-140. The capture worksheet export stands on the operator
surface as the subcommand export-capture-worksheet, beside the
worksheet import route that already stands shipped, and the
help text names it.
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


class TestWorksheetExportSurface(unittest.TestCase):

    def setUp(self):
        self.root, self.home = make_home(self)
        service.add_product(
            home=str(self.home), name="Example Product",
            canonical_line="Example Product answers questions.",
            domain="example.com",
            query_set=["What is Example Product?"],
            audit_date=AUDIT_DATE)
        service.name_round(
            home=str(self.home), product="Example Product",
            round_label="round-1", importer_declaration="operator",
            supplier_relation="first party", audit_date=AUDIT_DATE)

    def test_export_writes_a_worksheet_file(self):
        target = self.root / "sheet.txt"
        code, _out, err = run_shell(
            ["export-capture-worksheet", "--home", str(self.home),
             "--product", "Example Product", "--round", "round-1",
             "--output_path", str(target),
             "--planned_answers", "2",
             "--audit_date", AUDIT_DATE, "--form", "simple"])
        self.assertEqual(code, 0, err)
        self.assertTrue(target.exists())
        text = target.read_text(encoding="utf-8")
        self.assertIn("Citeline capture worksheet", text)
        self.assertIn("round-1", text)

    def test_help_names_the_subcommand(self):
        self.assertIn("export-capture-worksheet", shell.help_text())


if __name__ == "__main__":
    unittest.main()
