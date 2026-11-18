"""Repair tests: failure messages guide the operator.

Oracle: the settled rule. A
shell failure message states a next step and states what was
stored, or that nothing was stored, and carries no raw errno
text and no raw Python wording.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from citeline import install as install_module
from citeline import shell

AUDIT_DATE = "2026-11-17"


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


class TestFailureMessageGuidance(unittest.TestCase):

    def test_missing_home_states_next_step_and_stored_state(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        missing = root / "no-such-home"
        code, _out, err = run_shell(
            ["status", "--home", str(missing), "--form", "simple"])
        self.assertNotEqual(code, 0)
        self.assertIn("HOME_MISSING", err)
        self.assertIn("installer", err)
        self.assertIn("Nothing was stored", err)

    def test_missing_page_file_plain_words_and_guidance(self):
        root, home = make_home(self)
        missing = root / "no-such-page.md"
        code, _out, err = run_shell(
            ["audit", "--home", str(home),
             "--page_file", str(missing),
             "--audit_date", AUDIT_DATE, "--form", "simple"])
        self.assertNotEqual(code, 0)
        self.assertNotIn("Errno", err)
        self.assertIn("does not exist", err)
        self.assertIn("Next step", err)
        self.assertIn("Nothing was stored", err)


if __name__ == "__main__":
    unittest.main()
