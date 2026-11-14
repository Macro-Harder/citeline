"""Step 16 supplementary fix G6 tests: E-08 and E-09.

Written test first for the round 2 supplementary defects
E-08 and E-09. The recorded perspective of this seat:
records and warnings surfaced, what the product computes
for the user it also shows the user.

E-08 oracle: plan joined entry 13, row X-5, token
VALIDATION_FAILED, usage class, exit code 2, failure
record behaviour: a failure record in the fixed shape
stands appended where the chain accepts appends, and
nothing else is written. The row governs both identifier
failures of register-page, the non-standing identity
(cured in round 1) and the missing or empty identity.

E-09 oracle: brief Section 3.5 point 5 (decision list
item 142): an unknown key is reported as a warning and
is not an install failure; the brief install statement
config failure outcomes: an unknown key stays a warning
and is not a failure, beside the limb that a config file
that cannot be parsed, holds a wrong form value, or
holds a duplicate key fails the install and fails any
run that reads it; plan Section 3.2 rule 4: an unknown
key is reported as a warning and is not a failure.
The surfaces cured are the ones those statements and
the round 2 evidence reach: the installer install route
over a pre-existing config at the install location, and
the run side home reporting routes, status and verify,
whose records are built from the journal snapshot that
reads the home config. Installer work runs on faithful
copies of the shipped tree in scratch, never into the
shipped tree.
"""

import contextlib
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import citeline
from citeline import install as install_module
from citeline import journal, service, shell

AUDIT_DATE = "2026-11-14"
PRODUCT = "Example Product"
CANONICAL = "The reference sentence that must match verbatim."
PRODUCT_ROOT = Path(citeline.__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
UNKNOWN_KEY = "unknown_key_xyz"
UNKNOWN_CONFIG = "journal_length = 5000\nunknown_key_xyz = 1\n"


def failure_records(home):
    return [entry.get("payload") or {}
            for entry in journal.fold(str(home))
            if entry.get("entry_kind") == "failure_record"]


def entries_of_kind(home, kind):
    return [entry.get("payload") or {}
            for entry in journal.fold(str(home))
            if entry.get("entry_kind") == kind]


def run_shell(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        code = shell.main(list(argv))
    return code, out.getvalue(), err.getvalue()


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


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class G6Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)
        service.add_product(
            home=self.home, name=PRODUCT, canonical_line=CANONICAL,
            domain="example.invalid", audit_date=AUDIT_DATE)

    def tearDown(self):
        self.tmp.cleanup()

    def assert_refusal_shape(self, exc):
        token = getattr(exc, "error_value", None) or getattr(
            exc, "token", None)
        self.assertEqual(token, "VALIDATION_FAILED")
        self.assertEqual(getattr(exc, "row", None), "X-5")
        self.assertEqual(getattr(exc, "exit_code", None), 2)

    def assert_one_new_failure_record(self, before):
        records = failure_records(self.home)
        self.assertEqual(len(records), before + 1)
        payload = records[-1]
        self.assertEqual(payload.get("operation"), "register_page")
        self.assertEqual(payload.get("error_value"),
                         "VALIDATION_FAILED")
        self.assertEqual(payload.get("rule_fired"),
                         "VALIDATION_FAILED")
        self.assertEqual(payload.get("date"), AUDIT_DATE)
        self.assertIn("subject_identity", payload)
        self.assertEqual(
            entries_of_kind(self.home, "snapshot_registered"), [])


class TestE08MissingIdentityFailureRecord(G6Base):
    """E-08: the missing or empty snapshot identity form of
    register-page refuses correctly but appends no failure
    record, where row X-5 orders one."""

    def test_none_snapshot_appends_one_failure_record(self):
        before = len(failure_records(self.home))
        with self.assertRaises(Exception) as caught:
            service.register_page(
                home=self.home, product=PRODUCT, snapshot=None,
                audit_date=AUDIT_DATE)
        self.assert_refusal_shape(caught.exception)
        self.assert_one_new_failure_record(before)

    def test_empty_snapshot_appends_one_failure_record(self):
        before = len(failure_records(self.home))
        with self.assertRaises(Exception) as caught:
            service.register_page(
                home=self.home, product=PRODUCT, snapshot="",
                audit_date=AUDIT_DATE)
        self.assert_refusal_shape(caught.exception)
        self.assert_one_new_failure_record(before)

    def test_dict_without_snapshot_id_appends_one_failure_record(self):
        before = len(failure_records(self.home))
        with self.assertRaises(Exception) as caught:
            service.register_page(
                home=self.home, product=PRODUCT, snapshot={},
                audit_date=AUDIT_DATE)
        self.assert_refusal_shape(caught.exception)
        self.assert_one_new_failure_record(before)

    def test_cli_empty_snapshot_value_appends_one_failure_record(self):
        before = len(failure_records(self.home))
        entries_before = len(journal.fold(self.home))
        code, out, err = run_shell(
            ["register-page", "--home", self.home,
             "--product", PRODUCT, "--snapshot", "",
             "--audit_date", AUDIT_DATE])
        self.assertEqual(code, 2)
        self.assertIn("VALIDATION_FAILED", err)
        self.assert_one_new_failure_record(before)
        self.assertEqual(len(journal.fold(self.home)),
                         entries_before + 1)

    def test_chain_verifies_and_later_registration_appends(self):
        with self.assertRaises(Exception):
            service.register_page(
                home=self.home, product=PRODUCT, snapshot="",
                audit_date=AUDIT_DATE)
        chain = journal.verify_chain(self.home)
        self.assertTrue(chain.get("passed"))
        page = os.path.join(self.tmp.name, "page.md")
        with open(page, "w", encoding="utf-8") as handle:
            handle.write("# Example Product\n\n"
                         "Example Product answers questions.\n")
        audit = service.audit(home=self.home, page_file=page,
                              audit_date=AUDIT_DATE)
        registered = service.register_page(
            home=self.home, product=PRODUCT,
            snapshot=audit["snapshot_id"], audit_date=AUDIT_DATE)
        self.assertTrue(registered["is_product_page"])


class TestE09InstallerWarning(unittest.TestCase):
    """E-09, installer surface: a config carrying an unknown
    key installs silently, where a warning naming the key
    stands ordered and the install still succeeds."""

    def place_config(self, root, text):
        location = root / "install"
        location.mkdir(parents=True)
        config = location / "config.txt"
        config.write_text(text, encoding="utf-8")
        return location, config

    def test_installer_prints_warning_naming_key_and_succeeds(self):
        root, copy_root = copy_product_tree(self)
        op_home = root / "operator"
        op_home.mkdir()
        location, config = self.place_config(root, UNKNOWN_CONFIG)
        before = file_hash(config)
        result = run_copy_installer(
            copy_root,
            ["--location", str(location),
             "--home", str(root / "home")], op_home)
        combined = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, combined)
        self.assertIn("warning", combined.lower())
        self.assertIn(UNKNOWN_KEY, combined)
        self.assertIn("pre-existing config left untouched", combined)
        self.assertEqual(file_hash(config), before)
        self.assertTrue((location / "citeline.py").is_file())

    def test_install_report_carries_the_warning(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        location, config = self.place_config(root, UNKNOWN_CONFIG)
        report = install_module.install(
            location=str(location), home=str(root / "home"))
        warnings = report.get("warnings") or []
        self.assertTrue(
            any(UNKNOWN_KEY in str(item) for item in warnings),
            report)
        self.assertEqual(report.get("config"),
                         "pre-existing config left untouched")

    def test_valid_pre_existing_config_installs_with_no_warning(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        location, config = self.place_config(
            root, (FIXTURES / "w1-config-valid.txt").read_text(
                encoding="utf-8"))
        report = install_module.install(
            location=str(location), home=str(root / "home"))
        self.assertEqual(report.get("warnings"), [])

    def test_repeat_install_prints_no_warning_for_installer_keys(self):
        root, copy_root = copy_product_tree(self)
        op_home = root / "operator"
        op_home.mkdir()
        location = root / "install"
        home = root / "home"
        first = run_copy_installer(
            copy_root,
            ["--location", str(location), "--home", str(home)],
            op_home)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = run_copy_installer(
            copy_root,
            ["--location", str(location), "--home", str(home)],
            op_home)
        combined = second.stdout + second.stderr
        self.assertEqual(second.returncode, 0, combined)
        self.assertNotIn("warning", combined.lower())
        self.assertNotIn("unknown key", combined.lower())

    def test_invalid_config_still_fails_the_install(self):
        root, copy_root = copy_product_tree(self)
        op_home = root / "operator"
        op_home.mkdir()
        location, config = self.place_config(
            root, (FIXTURES / "w1-config-duplicate.txt").read_text(
                encoding="utf-8"))
        before = file_hash(config)
        result = run_copy_installer(
            copy_root,
            ["--location", str(location),
             "--home", str(root / "home")], op_home)
        combined = result.stdout + result.stderr
        self.assertEqual(result.returncode, 5, combined)
        self.assertIn("CONFIG_INVALID", combined)
        self.assertEqual(file_hash(config), before)
        self.assertFalse((location / "citeline.py").exists())


class TestE09RunSideWarning(G6Base):
    """E-09, run side: a status call over a home carrying
    the same config printed no warning, although the valid
    key stood in force."""

    def write_unknown_config(self):
        journal.write_config(self.home, UNKNOWN_CONFIG)

    def test_status_record_carries_warning_and_valid_key_in_force(self):
        self.write_unknown_config()
        status = service.status(home=self.home)
        warnings = status.get("config_warnings") or []
        self.assertTrue(
            any(UNKNOWN_KEY in str(item) for item in warnings),
            status.get("config_warnings"))
        outlook = status["capacity_outlook"]
        self.assertEqual(
            outlook["journal_length_remaining"]
            + status["entry_count"], 5000)

    def test_status_shell_prints_warning_in_simple_and_advanced(self):
        self.write_unknown_config()
        for form in ("simple", "advanced"):
            with self.subTest(form=form):
                code, out, err = run_shell(
                    ["status", "--home", self.home,
                     "--form", form])
                combined = out + err
                self.assertEqual(code, 0, combined)
                self.assertIn(UNKNOWN_KEY, combined)
                self.assertIn("warning", combined.lower())

    def test_verify_record_carries_warning(self):
        self.write_unknown_config()
        result = service.verify(home=self.home)
        self.assertTrue(result.get("passed"))
        warnings = result.get("config_warnings") or []
        self.assertTrue(
            any(UNKNOWN_KEY in str(item) for item in warnings),
            result.get("config_warnings"))

    def test_clean_home_status_carries_no_config_warnings(self):
        status = service.status(home=self.home)
        self.assertEqual(status.get("config_warnings"), [])


if __name__ == "__main__":
    unittest.main()
