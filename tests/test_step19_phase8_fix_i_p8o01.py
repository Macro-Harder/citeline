"""Step 19 Phase 8 fix seat I tests.

Each class pins one Phase 8 triage item, test first.
Oracle: design/audit/step-19-phase8-triage.md Part B
(P8O-01, the merged worksheet row P8O-02 with P8Y-03,
and P8Y-06), with the Orange and Yellow Phase 8 papers.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

import citeline
from citeline import install as install_module
from citeline import shell

PRODUCT_ROOT = Path(citeline.__file__).resolve().parent.parent


def readme_text():
    return (PRODUCT_ROOT / "README.md").read_text(
        encoding="utf-8")


def flat(text):
    return " ".join(text.split())


class TestP8O01UninstallWarning(unittest.TestCase):
    """P8O-01: uninstall of a used home warns in plain
    language, before deleting, naming the home and its
    journal and the records created by use, and the README
    sentence states that uninstall removes the used home
    and every record in its journal."""

    def setUp(self):
        self.tmp = Path(self.enterContext(
            tempfile.TemporaryDirectory()))
        self.location = self.tmp / "loc"
        self.home = self.tmp / "home"
        install_module.install(
            location=str(self.location), home=str(self.home))

    def run_main(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = install_module.main(argv)
        return code, out.getvalue()

    def test_readme_uninstall_sentence_states_used_home(self):
        text = flat(readme_text())
        self.assertIn("used home", text)
        self.assertIn("every record in its journal", text)

    def test_uninstall_warns_before_removing_used_home(self):
        journal = self.home / "journal.jsonl"
        journal.write_text(
            '{"entry": 1}\n', encoding="utf-8")
        code, out = self.run_main(
            ["uninstall", str(self.location),
             "--home", str(self.home)])
        self.assertEqual(code, 0)
        lines = out.splitlines()
        warnings = [line for line in lines
                    if line.startswith("warning:")]
        self.assertTrue(warnings, out)
        warning = warnings[0]
        self.assertIn(str(self.home), warning)
        self.assertIn("journal", warning)
        self.assertIn("every record", warning)
        self.assertIn("using the product", warning)
        removed_journal = "removed: %s" % journal
        self.assertIn(removed_journal, lines)
        self.assertLess(
            lines.index(warning), lines.index(removed_journal))
        self.assertFalse(self.home.exists())

    def test_no_warning_where_home_holds_no_work(self):
        code, out = self.run_main(
            ["uninstall", str(self.location),
             "--home", str(self.home)])
        self.assertEqual(code, 0)
        self.assertNotIn("warning:", out)
        self.assertFalse(self.home.exists())

    def test_no_warning_where_home_stands_unlinked(self):
        other = self.tmp / "other"
        other.mkdir()
        (other / "unrelated.txt").write_text(
            "x\n", encoding="utf-8")
        code, out = self.run_main(
            ["uninstall", str(self.location),
             "--home", str(other)])
        self.assertEqual(code, 0)
        self.assertNotIn("warning:", out)
        self.assertTrue(other.exists())


