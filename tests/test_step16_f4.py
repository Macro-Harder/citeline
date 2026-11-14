"""Step 16 fix wave, builder F4: shell, launcher, installer.

Pins the round 1 defects D-07, D-08, D-21, and D-22 from the
Step 16 record. Oracle: brief Section 5.12 (a usage error call
reproduces the subcommand list in full and carries the
malformed call value; the form input defaults to simple and
the home input to the default home; a call missing a required
input is a generic malformed call), plan row U-8 (token
MALFORMED_CALL, usage class, exit 2, failure record appended
where the chain accepts appends), and plan Section 8.3 (the
installer overlap check runs before any install write).
Installer overlap and default location work runs on faithful
copies of the shipped tree in scratch, never on the shipped
tree itself.
"""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import citeline
from citeline import install as install_module
from citeline import journal, shell

AUDIT_DATE = "2026-11-13"
PRODUCT_ROOT = Path(citeline.__file__).resolve().parent.parent

LIST_MARKERS = (
    "add-product", "register-page", "probe import",
    "probe trend", "query-set-report", "guide", "verify",
    "status", "watch",
)


def run_shell(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        code = shell.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location = root / "install"
    home = root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, location, home


def failure_records(home):
    return [entry for entry in journal.fold(str(home))
            if entry.get("entry_kind") == "failure_record"]


def copy_product_tree(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    copy_root = root / "copy" / "product"
    shutil.copytree(
        PRODUCT_ROOT, copy_root,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return root, copy_root


def run_copy_installer(copy_root, args, op_home):
    env = dict(os.environ)
    env["HOME"] = str(op_home)
    return subprocess.run(
        [sys.executable, str(copy_root / "install.py")] + list(args),
        capture_output=True, text=True, env=env, timeout=60)


def tree_listing(root):
    """The files under one tree, interpreter bytecode aside.

    Running the copied installer imports its package, which
    writes bytecode caches beside the copied modules. Those
    caches are not install writes, so the overlap comparison
    stands over every other file.
    """
    return sorted(
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
        and path.suffix != ".pyc")


class TestD07ShellSilence(unittest.TestCase):
    """D-07: shell parse level invocation errors return in
    silence at exit 2, with no MALFORMED_CALL value, no
    invocation list, and no failure record."""

    def test_nine_malformed_forms_print_value_and_list(self):
        _, _, home = make_home(self)
        plan = Path(self.enterContext(
            tempfile.TemporaryDirectory())) / "plan.json"
        plan.write_text(json.dumps(
            {"home": str(home), "scope": "estate"}),
            encoding="utf-8")
        forms = [
            [],
            ["bogus-subcommand"],
            ["status", "--home", str(home), "--form", "banana"],
            ["status", "--home", str(home), "--bogus", "x"],
            ["status", "--home"],
            ["help", "extra"],
            ["probe", "bogus"],
            ["watch"],
            ["watch", "--plan", str(plan), "--form", "banana"],
        ]
        for argv in forms:
            with self.subTest(argv=argv):
                code, out, err = run_shell(argv)
                self.assertEqual(code, 2)
                self.assertIn("MALFORMED_CALL", err)
                combined = out + err
                for marker in LIST_MARKERS:
                    self.assertIn(marker, combined)

    def test_malformed_call_appends_failure_record(self):
        _, _, home = make_home(self)
        before = len(failure_records(home))
        code, _, _ = run_shell(
            ["status", "--home", str(home), "--form", "banana"])
        self.assertEqual(code, 2)
        records = failure_records(home)
        self.assertEqual(len(records), before + 1)
        payload = records[-1].get("payload") or {}
        self.assertEqual(payload.get("error_value"),
                         "MALFORMED_CALL")

    def test_watch_bad_form_appends_failure_record(self):
        _, _, home = make_home(self)
        plan_dir = Path(self.enterContext(
            tempfile.TemporaryDirectory()))
        plan = plan_dir / "plan.json"
        plan.write_text(json.dumps(
            {"home": str(home), "scope": "estate"}),
            encoding="utf-8")
        before = len(failure_records(home))
        code, _, err = run_shell(
            ["watch", "--plan", str(plan), "--form", "banana"])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)
        self.assertEqual(len(failure_records(home)), before + 1)

    def test_installer_malformed_calls_print_the_value(self):
        root, copy_root = copy_product_tree(self)
        op_home = root / "operator"
        op_home.mkdir()
        bad_flag = run_copy_installer(copy_root, ["--bogus"],
                                      op_home)
        self.assertEqual(bad_flag.returncode, 2)
        self.assertIn("MALFORMED_CALL", bad_flag.stderr)
        no_value = run_copy_installer(copy_root, ["--location"],
                                      op_home)
        self.assertEqual(no_value.returncode, 2)
        self.assertIn("MALFORMED_CALL", no_value.stderr)


class TestD08MissingRequiredInput(unittest.TestCase):
    """D-08: a call missing a required input leaks a raw Python
    binding message at exit 3, where row U-8 orders
    MALFORMED_CALL, usage, exit 2."""

    def assert_malformed(self, argv, missing_names):
        code, out, err = run_shell(argv)
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)
        combined = out + err
        self.assertNotIn("keyword-only", combined)
        self.assertNotIn("missing 1 required", combined)
        self.assertNotIn("audit()", combined)
        self.assertNotIn("add_product()", combined)
        self.assertNotIn("register_page()", combined)
        for name in missing_names:
            self.assertIn(name, err)
        for marker in LIST_MARKERS:
            self.assertIn(marker, combined)

    def test_audit_with_no_page_file(self):
        _, _, home = make_home(self)
        self.assert_malformed(
            ["audit", "--home", str(home)], ["page_file"])

    def test_add_product_missing_fields(self):
        _, _, home = make_home(self)
        self.assert_malformed(
            ["add-product", "--home", str(home)],
            ["name", "canonical_line", "domain"])

    def test_register_page_with_no_snapshot(self):
        _, _, home = make_home(self)
        self.assert_malformed(
            ["register-page", "--home", str(home),
             "--product", "Example Product"], ["snapshot"])

    def test_missing_input_appends_failure_record(self):
        _, _, home = make_home(self)
        before = len(failure_records(home))
        code, _, _ = run_shell(["audit", "--home", str(home)])
        self.assertEqual(code, 2)
        self.assertEqual(len(failure_records(home)), before + 1)


class TestD21InvocationDefaults(unittest.TestCase):
    """D-21: the form input defaults to simple and the home
    input to the default home; both stand unhonoured."""

    def test_form_defaults_to_simple(self):
        _, _, home = make_home(self)
        code, out, _ = run_shell(["status", "--home", str(home)])
        self.assertEqual(code, 0)
        code2, out2, _ = run_shell(
            ["status", "--home", str(home), "--form", "simple"])
        self.assertEqual(code2, 0)
        self.assertEqual(out, out2)
        self.assertFalse(out.lstrip().startswith("{"))

    def test_home_defaults_to_the_default_home(self):
        root, copy_root = copy_product_tree(self)
        op_home = root / "operator"
        op_home.mkdir()
        installed = run_copy_installer(copy_root, [], op_home)
        self.assertEqual(installed.returncode, 0,
                         installed.stderr)
        default_home = op_home / ".citeline"
        self.assertTrue(default_home.is_dir())
        launcher = copy_root.parent / "citeline" / "citeline.py"
        self.assertTrue(launcher.is_file())
        env = dict(os.environ)
        env["HOME"] = str(op_home)
        result = subprocess.run(
            [sys.executable, str(launcher), "status"],
            capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(default_home), result.stdout)
        self.assertNotIn("missing 1 required",
                         result.stdout + result.stderr)


class TestD22InstallerOverlap(unittest.TestCase):
    """D-22: the installer runs no overlap check, where plan
    Section 8.3 orders a refusal before any write when the
    install location equals, sits inside, or contains the
    product directory."""

    def assert_refused_without_writes(self, copy_root, location,
                                      op_home):
        before = tree_listing(copy_root)
        result = run_copy_installer(copy_root, [str(location)],
                                    op_home)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DESTINATION_EXISTS", result.stderr)
        self.assertEqual(tree_listing(copy_root), before)
        self.assertFalse((Path(location) / "citeline.py").exists()
                         and Path(location) == copy_root)
        return result

    def test_location_equal_to_product_directory_refused(self):
        root, copy_root = copy_product_tree(self)
        op_home = root / "operator"
        op_home.mkdir()
        self.assert_refused_without_writes(copy_root, copy_root,
                                           op_home)
        self.assertFalse((copy_root / "citeline.py").exists())
        self.assertFalse((copy_root / "config.txt").exists())

    def test_location_inside_product_directory_refused(self):
        root, copy_root = copy_product_tree(self)
        op_home = root / "operator"
        op_home.mkdir()
        inside = copy_root / "inner"
        self.assert_refused_without_writes(copy_root, inside,
                                           op_home)
        self.assertFalse(inside.exists())

    def test_location_containing_product_directory_refused(self):
        root, copy_root = copy_product_tree(self)
        op_home = root / "operator"
        op_home.mkdir()
        container = copy_root.parent
        self.assert_refused_without_writes(copy_root, container,
                                           op_home)
        self.assertFalse((container / "citeline.py").exists())
        self.assertFalse((container / "config.txt").exists())

    def test_non_overlapping_location_still_installs(self):
        root, copy_root = copy_product_tree(self)
        op_home = root / "operator"
        op_home.mkdir()
        location = root / "elsewhere"
        home = root / "home"
        result = run_copy_installer(
            copy_root,
            ["--location", str(location), "--home", str(home)],
            op_home)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((location / "citeline.py").is_file())


if __name__ == "__main__":
    unittest.main()
