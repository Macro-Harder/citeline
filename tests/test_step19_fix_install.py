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


class TestR19028UninstallNamesHome(InstallCase):
    """R19-028: the documented uninstall form can name a
    non default home and acts on the home named, never
    silently against the default home. README CL19-030,
    CL19-027."""

    def run_top_installer(self, args, fake_home):
        env = dict(os.environ)
        env["HOME"] = str(fake_home)
        env.pop("PYTHONPATH", None)
        return subprocess.run(
            [sys.executable, str(PRODUCT_ROOT / "install.py")] + args,
            capture_output=True, text=True, env=env, timeout=60)

    def test_documented_uninstall_form_names_the_home(self):
        fake_home = self.tmp / "fakehome"
        fake_home.mkdir()
        default_home = fake_home / ".citeline"
        default_home.mkdir()
        self.install()
        result = self.run_top_installer(
            ["uninstall", str(self.location), str(self.home)],
            fake_home)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("home: %s" % self.home, result.stdout)
        self.assertFalse(self.home.exists())
        self.assertFalse(self.location.exists())
        self.assertTrue(default_home.exists())


class TestR19029Upgrade(InstallCase):
    """R19-029: an upgrade path stands for a standing
    installation: reinstalling over a launcher from an
    earlier tree upgrades it in place, and the route is
    stated in the shipped installer text. CL19-025,
    CL19-159, CL19-165."""

    def test_reinstall_upgrades_a_standing_launcher(self):
        self.install()
        launcher = self.location / "citeline.py"
        launcher.write_text(
            launcher.read_text(encoding="utf-8")
            + "# previous version marker\n", encoding="utf-8")
        module = self.location / "citeline" / "shell.py"
        source_bytes = module.read_bytes()
        module.write_bytes(source_bytes + b"\n# old bytes\n")
        result = self.install()
        self.assertEqual(
            launcher.read_text(encoding="utf-8"),
            install_module._product_file_text())
        self.assertEqual(module.read_bytes(), source_bytes)
        self.assertEqual(result["product_file_state"], "upgraded")

    def test_foreign_file_still_refused_on_reinstall(self):
        self.location.mkdir(parents=True)
        planted = self.location / "citeline.py"
        planted.write_text("planted\n", encoding="utf-8")
        with self.assertRaises(Exception):
            self.install()
        self.assertEqual(
            planted.read_text(encoding="utf-8"), "planted\n")


class TestR19030UninstallRemaining(InstallCase):
    """R19-030: uninstall output names everything that
    remains after the call, and states plainly where nothing
    was found or nothing was removed. Brief CL19-165,
    CL19-226."""

    def run_main(self, argv):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = install_module.main(argv)
        return code, out.getvalue()

    def test_leftover_config_is_named_in_output(self):
        self.location.mkdir(parents=True)
        config = self.location / "config.txt"
        config.write_text("home = %s\n" % self.home,
                          encoding="utf-8")
        self.install()
        code, out = self.run_main(
            ["uninstall", str(self.location),
             "--home", str(self.home)])
        self.assertEqual(code, 0)
        self.assertIn("remaining: %s" % config, out)

    def test_nothing_found_is_stated_plainly(self):
        code, out = self.run_main(
            ["uninstall", str(self.location),
             "--home", str(self.home)])
        self.assertEqual(code, 0)
        self.assertIn("nothing was found", out)
        self.assertIn("nothing was removed", out)

    def test_unlinked_home_is_named_as_remaining(self):
        self.location.mkdir(parents=True)
        self.home.mkdir()
        (self.home / "unrelated.txt").write_text(
            "x\n", encoding="utf-8")
        code, out = self.run_main(
            ["uninstall", str(self.location),
             "--home", str(self.home)])
        self.assertEqual(code, 0)
        self.assertIn("remaining: %s" % self.home, out)


class TestR19042HelpAndErrors(InstallCase):
    """R19-042: the installer has a help surface, and every
    installer error states the usage, the next step, and
    what was not installed or removed. CL19-127."""

    def run_main(self, argv):
        import contextlib
        import io
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = install_module.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_help_surface_answers_at_exit_0(self):
        for flag in ("--help", "-h"):
            code, out, _ = self.run_main([flag])
            self.assertEqual(code, 0, flag)
            self.assertIn("usage", out.lower())
            self.assertIn("uninstall", out)

    def test_malformed_calls_state_usage_next_step_and_no_act(self):
        for argv in (["--bogus"], ["--location"],
                     ["extra1", "extra2"]):
            code, _, err = self.run_main(argv)
            self.assertEqual(code, 2, argv)
            self.assertIn("MALFORMED_CALL", err)
            self.assertIn("usage", err.lower())
            self.assertIn("next step", err)
            self.assertIn(
                "nothing was installed or removed", err)

    def test_install_error_states_usage_next_step_and_no_completion(self):
        blocker = self.tmp / "blocker"
        blocker.write_text("occupied\n", encoding="utf-8")
        code, _, err = self.run_main(
            [str(blocker / "loc"), "--home", str(self.home)])
        self.assertIn(code, (2, 3, 5))
        self.assertIn("usage", err.lower())
        self.assertIn("next step", err)
        self.assertIn("did not complete", err)


class TestR19016ExclusiveCreate(InstallCase):
    """R19-016: installer file creation uses exclusive
    create, so a link planted between the existence checks
    and the write is refused and never followed, matching
    the journal code discipline."""

    def test_exclusive_create_refuses_a_planted_link(self):
        outside = self.tmp / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")
        target = self.tmp / "citeline.py"
        os.symlink(outside, target)
        with self.assertRaises(OSError):
            install_module._create_file_exclusive(
                str(target), "launcher text\n")
        self.assertEqual(
            outside.read_text(encoding="utf-8"), "outside\n")

    def test_exclusive_create_refuses_an_existing_file(self):
        target = self.tmp / "config.txt"
        target.write_text("standing\n", encoding="utf-8")
        with self.assertRaises(OSError):
            install_module._create_file_exclusive(
                str(target), "new text\n")
        self.assertEqual(
            target.read_text(encoding="utf-8"), "standing\n")

    def test_install_refuses_link_at_product_file_path(self):
        self.location.mkdir(parents=True)
        outside = self.tmp / "outside2.txt"
        outside.write_text("outside\n", encoding="utf-8")
        os.symlink(outside, self.location / "citeline.py")
        with self.assertRaises(Exception):
            self.install()
        self.assertEqual(
            outside.read_text(encoding="utf-8"), "outside\n")


class TestR19032AbsoluteLocation(InstallCase):
    """R19-032: a relative install location is printed as
    an absolute path in the install output, as the home
    lines in the same output already print. CL19-028,
    CL19-226."""

    def test_relative_location_prints_absolute(self):
        import contextlib
        import io
        old_cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, old_cwd)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = install_module.main(
                ["reloc", "--home", str(self.home)])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn(
            "location: %s" % (self.tmp / "reloc"), text)
        self.assertNotIn("location: reloc\n", text)
        self.assertIn(
            "created: %s" % (self.tmp / "reloc"), text)


class TestR19046ConfigInvalidDetail(InstallCase):
    """R19-046: the install CONFIG_INVALID message names
    the cause, the rule broken, and the line at fault,
    distinguishing the parse, wrong form value, and
    duplicate key causes. Brief CL19-164."""

    def install_with_config(self, text):
        self.location.mkdir(parents=True)
        (self.location / "config.txt").write_text(
            text, encoding="utf-8")
        with self.assertRaises(
                install_module.InstallError) as caught:
            self.install()
        self.assertEqual(
            caught.exception.token, "CONFIG_INVALID")
        return str(caught.exception)

    def test_parse_cause_names_line(self):
        message = self.install_with_config(
            "home = %s\na line with no equals\n" % self.home)
        self.assertIn("parse", message)
        self.assertIn("line 2", message)

    def test_duplicate_cause_names_line(self):
        message = self.install_with_config(
            "page_file_size = 10\npage_file_size = 20\n")
        self.assertIn("duplicate", message)
        self.assertIn("line 2", message)

    def test_wrong_form_cause_names_line(self):
        message = self.install_with_config(
            "page_file_size = abc\n")
        self.assertIn("wrong form", message)
        self.assertIn("line 1", message)

    def test_causes_produce_different_messages(self):
        first = self.install_with_config("no equals here\n")
        self.location = self.tmp / "loc2"
        second = self.install_with_config(
            "page_file_size = 1\npage_file_size = 2\n")
        self.assertNotEqual(first, second)


class TestR19047RepeatInstallState(InstallCase):
    """R19-047: a repeat install over a complete
    installation reports per item state, stating that the
    product file and the home already stand complete where
    they do. Brief CL19-165."""

    def test_repeat_install_reports_per_item_state(self):
        import contextlib
        import io
        self.install()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = install_module.main(
                [str(self.location), "--home", str(self.home)])
        self.assertEqual(code, 0)
        text = out.getvalue()
        self.assertIn(
            "standing: %s" % (self.location / "citeline.py"),
            text)
        self.assertIn("standing: %s" % self.home, text)
        self.assertIn("already stand complete", text)

    def test_repeat_install_report_carries_standing_items(self):
        self.install()
        result = self.install()
        standing = result.get("standing_items") or []
        self.assertIn(str(self.location / "citeline.py"),
                      standing)
        self.assertIn(str(self.home), standing)


if __name__ == "__main__":
    unittest.main()
