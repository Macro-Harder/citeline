"""Repair tests.

Each class pins one triage item, test first.
Oracle: the audit record Part B
(the repair item, the merged worksheet row the repair item with the repair item,
and the repair item), with the settled findings.
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
    """The repair item with the repair item: the README Use list names
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


