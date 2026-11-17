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

PRODUCT_ROOT = Path(citeline.__file__).resolve().parent.parent


def readme_text():
    return (PRODUCT_ROOT / "README.md").read_text(
        encoding="utf-8")


def flat(text):
    return " ".join(text.split())


class TestWorksheetRowInReadme(unittest.TestCase):
    """P8O-02 with P8Y-03: the README Use list names
    export-capture-worksheet with its flags, in the form
    the other subcommand lines stand in."""

    def test_use_list_names_export_capture_worksheet(self):
        text = readme_text()
        use = text.split("## Use", 1)[1].split(
            "guide takes exactly one selector", 1)[0]
        self.assertIn("export-capture-worksheet", use)
        line = [row for row in use.splitlines()
                if "export-capture-worksheet" in row][0]
        for flag in ("--home", "--product", "--round",
                     "--output_path", "--form"):
            self.assertIn(flag, line)


