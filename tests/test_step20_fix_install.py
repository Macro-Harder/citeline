"""Step 20 fix seat FX20-02, installer and uninstall items.

Each class pins one register item from the Step 20 defect
register, test first. Oracle: the register item text in
design/steps/step-20-register.md, with the Step 19 cures
at the final head standing as regression ground.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import citeline
from citeline import errors
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

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class TestS2002ForeignHome(InstallCase):
    """S20-02: a foreign home is removed whole on the
    strength of one file name."""

    def test_foreign_home_with_journal_name_survives(self):
        self.write(self.home / "journal.jsonl", "{}\n")
        precious = self.write(
            self.home / "precious.txt", "operator data\n")
        deep = self.write(
            self.home / "sub" / "deep.txt", "deep data\n")
        report = self.uninstall()
        self.assertTrue(precious.exists())
        self.assertTrue(deep.exists())
        self.assertTrue((self.home / "journal.jsonl").exists())
        self.assertTrue(self.home.exists())
        self.assertIn(str(self.home), report["remaining"])
        self.assertFalse(report["complete"])

    def test_journal_name_alone_does_not_remove_home(self):
        self.write(self.home / ".citeline-write.lock", "")
        kept = self.write(self.home / "notes.txt", "mine\n")
        self.uninstall()
        self.assertTrue(kept.exists())
        self.assertTrue(self.home.exists())


class TestS2003ForeignPackage(InstallCase):
    """S20-03: a foreign package directory at a never
    installed location is removed whole."""

    def test_foreign_package_survives_uninstall(self):
        init = self.write(
            self.location / "citeline" / "__init__.py",
            "operator package\n")
        module = self.write(
            self.location / "citeline" / "module.py",
            "operator module\n")
        self.home.mkdir()
        report = self.uninstall()
        self.assertTrue(init.exists())
        self.assertTrue(module.exists())
        self.assertTrue((self.location / "citeline").exists())
        self.assertTrue(self.location.exists())
        self.assertTrue(self.home.exists())
        self.assertIn(
            str(self.location / "citeline"),
            report["remaining"])


class TestS2009ForeignFilesInsideInstall(InstallCase):
    """S20-09: the uninstall tree walks delete foreign
    files placed inside a genuine install."""

    def test_foreign_files_inside_genuine_install_survive(self):
        self.install()
        notes = self.write(
            self.location / "citeline" / "operator_notes.txt",
            "operator notes\n")
        keep = self.write(
            self.home / "operator_keep.txt", "operator keep\n")
        report = self.uninstall()
        self.assertTrue(notes.exists())
        self.assertEqual(
            notes.read_text(encoding="utf-8"),
            "operator notes\n")
        self.assertTrue(keep.exists())
        self.assertFalse((self.location / "citeline.py").exists())
        self.assertFalse(
            (self.location / "config.txt").exists())
        self.assertFalse(
            (self.location / "citeline" / "shell.py").exists())
        self.assertIn(str(notes), report["remaining"])
        self.assertIn(str(self.home), report["remaining"])
        self.assertFalse(report["complete"])

    def test_modified_package_file_survives(self):
        self.install()
        module = self.location / "citeline" / "shell.py"
        module.write_bytes(module.read_bytes() + b"\n# mine\n")
        self.uninstall()
        self.assertTrue(module.exists())
        self.assertTrue((self.location / "citeline").exists())


class TestS2010NonJournalProductHome(InstallCase):
    """S20-10: a home holding only non journal product
    files is never removed, and a reinstall resurrects it."""

    def test_home_holding_only_home_config_is_removed(self):
        self.install()
        self.write(
            self.home / "config.txt",
            "home = %s\n" % self.home)
        self.uninstall()
        self.assertFalse(self.home.exists())
        self.assertFalse(self.location.exists())

    def test_home_holding_only_registry_lock_is_removed(self):
        self.install()
        self.write(self.home / ".citeline-registry.lock", "")
        self.uninstall()
        self.assertFalse(self.home.exists())
        self.assertFalse(self.location.exists())

    def test_reinstall_after_removal_starts_empty(self):
        self.install()
        self.write(
            self.home / "config.txt",
            "home = %s\nstale = yes\n" % self.home)
        self.uninstall()
        self.install()
        self.assertFalse((self.home / "config.txt").exists())


class TestS2011SubstringProvenance(InstallCase):
    """S20-11: the provenance checks are substring tests,
    so quoted marker text passes as provenance."""

    def test_prose_quoting_launcher_marker_survives(self):
        prose = (
            "This file quotes the sentence Citeline launcher "
            "for one local installation and names "
            "_PACKAGE_PARENT in passing.\n")
        victim = self.write(
            self.location / "citeline.py", prose)
        self.home.mkdir()
        report = self.uninstall()
        self.assertEqual(
            victim.read_text(encoding="utf-8"), prose)
        self.assertIn(str(victim), report["remaining"])

    def test_config_comment_naming_marker_survives(self):
        config = self.write(
            self.location / "config.txt",
            "# note: created_by = citeline installer\n"
            "home = %s\n" % self.home)
        self.home.mkdir()
        self.uninstall()
        self.assertTrue(config.exists())
        self.assertTrue(self.location.exists())
        self.assertTrue(self.home.exists())

    def test_genuine_launcher_and_config_still_removed(self):
        self.install()
        self.uninstall()
        self.assertFalse(self.location.exists())
        self.assertFalse(self.home.exists())


class TestS2012CompleteField(InstallCase):
    """S20-12: the uninstall report states complete True
    unconditionally."""

    def test_complete_false_where_items_remain(self):
        self.write(self.location / "citeline.py", "keep me\n")
        self.home.mkdir()
        report = self.uninstall()
        self.assertTrue(report["remaining"])
        self.assertFalse(report["complete"])

    def test_complete_true_after_full_removal(self):
        self.install()
        report = self.uninstall()
        self.assertEqual(report["remaining"], [])
        self.assertTrue(report["complete"])


class TestS2014PythonFloorToken(InstallCase):
    """S20-14: the InstallError token PYTHON_FLOOR stands
    in no vocabulary table and falls back to row X-9."""

    def test_floor_refusal_carries_a_vocabulary_token(self):
        with mock.patch.object(
                sys, "version_info", (3, 10, 0)):
            with self.assertRaises(
                    install_module.InstallError) as caught:
                self.install()
        exc = caught.exception
        self.assertIn("Python 3.11 or later", str(exc))
        entry = errors.error_for_token(exc.token)
        self.assertIsNotNone(entry)
        self.assertEqual(exc.row, entry["row"])
        self.assertEqual(exc.exit_code, entry["exit_code"])
        self.assertNotEqual(exc.token, "PYTHON_FLOOR")
        self.assertFalse(self.location.exists())


class TestS2028FilesystemFailureToken(InstallCase):
    """S20-28: every filesystem failure on the install and
    uninstall routes is returned as DESTINATION_EXISTS."""

    def test_permission_failure_is_not_destination_exists(self):
        with mock.patch.object(
                os, "makedirs",
                side_effect=PermissionError("denied")):
            with self.assertRaises(
                    install_module.InstallError) as caught:
                self.install()
        self.assertNotEqual(
            caught.exception.token, "DESTINATION_EXISTS")

    def test_uninstall_permission_failure_token(self):
        self.install()
        with mock.patch.object(
                os, "unlink",
                side_effect=PermissionError("denied")):
            with self.assertRaises(
                    install_module.InstallError) as caught:
                self.uninstall()
        self.assertNotEqual(
            caught.exception.token, "DESTINATION_EXISTS")

    def test_existing_destination_still_destination_exists(self):
        with mock.patch.object(
                os, "makedirs",
                side_effect=FileExistsError("there")):
            with self.assertRaises(
                    install_module.InstallError) as caught:
                self.install()
        self.assertEqual(
            caught.exception.token, "DESTINATION_EXISTS")
        self.assertEqual(caught.exception.row, "X-9")


class TestS2029LinkToDirectoryMessage(InstallCase):
    """S20-29: a link to a directory is refused with a
    message stating it stands as a file."""

    def test_location_link_to_directory_message(self):
        target = self.tmp / "realdir"
        target.mkdir()
        os.symlink(target, self.location)
        with self.assertRaises(
                install_module.InstallError) as caught:
            self.install()
        message = str(caught.exception)
        self.assertIn("link", message)
        self.assertNotIn("stands as a file", message)
        self.assertTrue(target.exists())

    def test_home_link_to_directory_message(self):
        target = self.tmp / "realhome"
        target.mkdir()
        os.symlink(target, self.home)
        with self.assertRaises(
                install_module.InstallError) as caught:
            self.install()
        message = str(caught.exception)
        self.assertIn("link", message)
        self.assertNotIn("stands as a file", message)


class TestS2030FallbackConfigCheck(InstallCase):
    """S20-30: the fallback config check accepts wrong
    form values its docstring states it refuses."""

    def config_path(self, text):
        return self.write(self.location / "config.txt", text)

    def test_fallback_refuses_wrong_form_limit_value(self):
        path = self.config_path("page_file_size = abc\n")
        with mock.patch.dict(
                sys.modules, {"citeline.journal": None}):
            valid, _warnings = install_module._config_check(
                str(path), str(self.home))
        self.assertFalse(valid)

    def test_fallback_install_refuses_wrong_form_value(self):
        self.config_path("page_file_size = abc\n")
        with mock.patch.dict(
                sys.modules, {"citeline.journal": None}):
            with self.assertRaises(
                    install_module.InstallError) as caught:
                self.install()
        self.assertEqual(
            caught.exception.token, "CONFIG_INVALID")

    def test_fallback_accepts_well_formed_limit_value(self):
        path = self.config_path("page_file_size = 10\n")
        with mock.patch.dict(
                sys.modules, {"citeline.journal": None}):
            valid, _warnings = install_module._config_check(
                str(path), str(self.home))
        self.assertTrue(valid)

    def test_fallback_still_refuses_duplicate_key(self):
        path = self.config_path(
            "page_file_size = 10\npage_file_size = 20\n")
        with mock.patch.dict(
                sys.modules, {"citeline.journal": None}):
            valid, _warnings = install_module._config_check(
                str(path), str(self.home))
        self.assertFalse(valid)


class TestS2031PlantedLinkEvidence(InstallCase):
    """S20-31: a planted link alone authorises removal of
    never installed empty home and location directories."""

    def test_planted_link_alone_removes_no_directories(self):
        outside = self.write(
            self.tmp / "outside.txt", "outside\n")
        self.location.mkdir(parents=True)
        os.symlink(outside, self.location / "citeline.py")
        self.home.mkdir()
        report = self.uninstall()
        self.assertFalse(
            os.path.lexists(self.location / "citeline.py"))
        self.assertEqual(
            outside.read_text(encoding="utf-8"), "outside\n")
        self.assertTrue(self.home.exists())
        self.assertTrue(self.location.exists())
        self.assertIn(str(self.home), report["remaining"])
        self.assertIn(str(self.location), report["remaining"])
        self.assertFalse(report["complete"])


if __name__ == "__main__":
    unittest.main()
