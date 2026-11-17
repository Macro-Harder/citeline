"""Step 19 fix tests for R19-043: usage errors name the fault only.

Oracle: register item R19-043. A shell usage error prints no full
help text to stdout, and its error names the actual fault,
including the flag at fault and the equals joined form where
that is the fault. The help subcommand still prints the full
help text.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from citeline import install as install_module
from citeline import shell

HELP_HEAD = "citeline: the invocation surface"


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location = root / "install"
    home = root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def run_shell(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        code = shell.main(argv)
    return code, out.getvalue(), err.getvalue()


class TestUsageErrorShape(unittest.TestCase):

    def test_no_arguments_no_help_flood(self):
        code, out, err = run_shell([])
        self.assertEqual(code, 2)
        self.assertNotIn(HELP_HEAD, out)
        self.assertIn("MALFORMED_CALL", err)

    def test_unknown_subcommand_no_help_flood(self):
        code, out, err = run_shell(["boguscmd"])
        self.assertEqual(code, 2)
        self.assertNotIn(HELP_HEAD, out)
        self.assertIn("boguscmd", err)

    def test_missing_flag_value_names_the_flag(self):
        _root, home = make_home(self)
        code, out, err = run_shell(["status", "--home"])
        self.assertEqual(code, 2)
        self.assertNotIn(HELP_HEAD, out)
        self.assertIn("--home", err)

    def test_equals_joined_form_names_flag_and_form(self):
        _root, home = make_home(self)
        code, out, err = run_shell(
            ["status", "--home=%s" % home, "--form=simple"])
        self.assertEqual(code, 2)
        self.assertNotIn(HELP_HEAD, out)
        self.assertIn("--home", err)
        self.assertIn("equals", err)

    def test_unknown_flag_names_the_flag(self):
        _root, home = make_home(self)
        code, out, err = run_shell(
            ["status", "--home", str(home), "--bogus", "x"])
        self.assertEqual(code, 2)
        self.assertNotIn(HELP_HEAD, out)
        self.assertIn("--bogus", err)

    def test_bad_form_value_no_help_flood(self):
        _root, home = make_home(self)
        code, out, err = run_shell(
            ["status", "--home", str(home), "--form", "bogus"])
        self.assertEqual(code, 2)
        self.assertNotIn(HELP_HEAD, out)
        self.assertIn("bogus", err)

    def test_help_subcommand_still_prints_full_help(self):
        code, out, _err = run_shell(["help"])
        self.assertEqual(code, 0)
        self.assertIn(HELP_HEAD, out)


if __name__ == "__main__":
    unittest.main()
