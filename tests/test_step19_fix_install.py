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


class TestR19014Provenance(InstallCase):
    """R19-014: uninstall checks provenance before every
    removal, as the config file marker check already does,
    per README CL19-030 and brief CL19-162."""

    def test_foreign_product_file_survives_uninstall(self):
        self.location.mkdir(parents=True)
        victim = self.location / "citeline.py"
        victim.write_text("keep me\n", encoding="utf-8")
        other = self.location / "other.txt"
        other.write_text("keep me too\n", encoding="utf-8")
        self.home.mkdir()
        self.uninstall()
        self.assertEqual(
            victim.read_text(encoding="utf-8"), "keep me\n")
        self.assertTrue(other.exists())
        self.assertTrue(self.location.exists())
        self.assertTrue(self.home.exists())

    def test_never_installed_empty_directories_survive(self):
        self.location.mkdir(parents=True)
        self.home.mkdir()
        self.uninstall()
        self.assertTrue(self.location.exists())
        self.assertTrue(self.home.exists())

    def test_unlinked_home_with_foreign_content_survives(self):
        self.location.mkdir(parents=True)
        self.home.mkdir()
        kept = self.home / "unrelated.txt"
        kept.write_text("not product data\n", encoding="utf-8")
        self.uninstall()
        self.assertTrue(kept.exists())
        self.assertTrue(self.home.exists())

    def test_installer_product_file_still_removed(self):
        self.install()
        self.uninstall()
        self.assertFalse((self.location / "citeline.py").exists())
        self.assertFalse(self.location.exists())
        self.assertFalse(self.home.exists())


if __name__ == "__main__":
    unittest.main()
