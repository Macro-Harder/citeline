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


class TestR19013RealInstall(InstallCase):
    """R19-013: a real install stands independent of the
    building tree path, and a broken installation fails with
    a recorded Citeline error at a designed exit code, never
    a raw traceback at exit 1. Locus CL19-160, CL19-161,
    CL19-200."""

    def copy_tree(self):
        import shutil
        copy_root = self.tmp / "copy" / "product"
        shutil.copytree(
            PRODUCT_ROOT, copy_root,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return copy_root

    def clean_env(self):
        env = dict(os.environ)
        env["HOME"] = str(self.tmp)
        env.pop("PYTHONPATH", None)
        return env

    def run_installer(self, copy_root, args):
        return subprocess.run(
            [sys.executable, str(copy_root / "install.py")] + args,
            capture_output=True, text=True, env=self.clean_env(),
            timeout=60)

    def test_install_stands_after_source_tree_moves(self):
        copy_root = self.copy_tree()
        done = self.run_installer(
            copy_root, ["--location", str(self.location),
                        "--home", str(self.home)])
        self.assertEqual(done.returncode, 0, done.stderr)
        moved = self.tmp / "copy" / "product-moved"
        os.rename(copy_root, moved)
        result = subprocess.run(
            [sys.executable, str(self.location / "citeline.py"),
             "status", "--home", str(self.home),
             "--form", "simple"],
            capture_output=True, text=True, env=self.clean_env(),
            timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("head", result.stdout)

    def test_broken_installation_fails_with_recorded_error(self):
        self.install()
        package = self.location / "citeline"
        if package.is_dir():
            import shutil
            shutil.rmtree(package)
        else:
            launcher = self.location / "citeline.py"
            launcher.write_text(
                launcher.read_text(encoding="utf-8").replace(
                    str(PRODUCT_ROOT), str(self.tmp / "gone")),
                encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(self.location / "citeline.py"),
             "status", "--home", str(self.home)],
            capture_output=True, text=True, env=self.clean_env(),
            timeout=60)
        self.assertNotEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("DESTINATION_EXISTS", result.stderr)


class TestR19015Permissions(InstallCase):
    """R19-015: restrictive permissions on the home, the
    journal, and the config, set by the product itself and
    not by whatever the process umask gives."""

    def setUp(self):
        super().setUp()
        self.old_umask = os.umask(0o022)
        self.addCleanup(os.umask, self.old_umask)

    def mode(self, path):
        return stat.S_IMODE(os.lstat(path).st_mode)

    def test_home_and_installer_config_are_owner_only(self):
        self.install()
        self.assertEqual(self.mode(self.home), 0o700)
        self.assertEqual(
            self.mode(self.location / "config.txt"), 0o600)

    def test_journal_and_home_config_tightened_on_repeat(self):
        self.install()
        journal = self.home / "journal.jsonl"
        journal.write_text('{"entry": 1}\n', encoding="utf-8")
        os.chmod(journal, 0o644)
        home_config = self.home / "config.txt"
        home_config.write_text("x = 1\n", encoding="utf-8")
        os.chmod(home_config, 0o644)
        self.install()
        self.assertEqual(self.mode(journal), 0o600)
        self.assertEqual(self.mode(home_config), 0o600)
        self.assertEqual(self.mode(self.home), 0o700)


if __name__ == "__main__":
    unittest.main()
