"""Step 19 fix seat 2, installer and uninstall items.

Each class pins one register item from the Step 19 split
repair queue, test first. Oracle: the cure stated for the
item in design/audit/step-19-split.md Section 3, with the
brief and README passages the register item cites.
"""

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import citeline
from citeline import install as install_module

PRODUCT_ROOT = Path(citeline.__file__).resolve().parent.parent


class InstallCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(
            tempfile.TemporaryDirectory()))
        self.location = self.tmp / "loc"
        self.home = self.tmp / "home"

    def install(self):
        return install_module.install(
            location=str(self.location), home=str(self.home))

    def uninstall(self):
        return install_module.uninstall(
            location=str(self.location), home=str(self.home))


class TestR19012UsedHomeRemoval(InstallCase):
    """R19-012: uninstall removes everything the installer
    created, a used home and its journal contents included,
    per brief CL19-162 and README CL19-030."""

    def test_uninstall_removes_used_home_and_journal_contents(self):
        self.install()
        journal = self.home / "journal.jsonl"
        journal.write_text('{"entry": 1}\n', encoding="utf-8")
        (self.home / "config.txt").write_text(
            "home = %s\n" % self.home, encoding="utf-8")
        nested = self.home / "kept"
        nested.mkdir()
        (nested / "answer.txt").write_text(
            "retained answer\n", encoding="utf-8")
        self.uninstall()
        self.assertFalse(self.home.exists())
        self.assertFalse(self.location.exists())

    def test_reinstall_after_used_uninstall_starts_empty(self):
        self.install()
        (self.home / "journal.jsonl").write_text(
            '{"entry": 1}\n', encoding="utf-8")
        self.uninstall()
        self.install()
        self.assertTrue(self.home.is_dir())
        self.assertFalse((self.home / "journal.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
