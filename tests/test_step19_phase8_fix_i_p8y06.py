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


class TestP8Y06SecondRoundsKey(unittest.TestCase):
    """P8Y-06: second_rounds stands named where the other
    watch keys stand, in the shell help watch plan text
    and in the README watch plan key list, with its effect
    for picked target trends and its disregarded warning
    on an estate plan."""

    def test_help_watch_plan_text_names_second_rounds(self):
        text = flat(shell.help_text())
        self.assertIn("second_rounds", text)
        self.assertIn("picked", text)
        self.assertIn("disregarded", text)
        self.assertIn("estate", text)

    def test_readme_key_list_names_second_rounds(self):
        text = flat(readme_text())
        self.assertIn("second_rounds", text)
        self.assertIn("disregarded", text)


if __name__ == "__main__":
    unittest.main()
