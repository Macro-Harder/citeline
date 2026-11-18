"""Repair tests: one error name for the run_id refusal.

Oracle: the settled rule. An audit call naming a run
identity beside fresh inputs stands refused under the one
error name MALFORMED_CALL, regardless of whether the
audit_date value parses. Which calls stand refused does not
change; only the error name is stable.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from citeline import install as install_module
from citeline import shell


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


class TestRunIdCombinationName(unittest.TestCase):

    def _audit(self, home, page, audit_date):
        return run_shell(
            ["audit", "--home", str(home), "--run_id", "run-1",
             "--page_file", str(page), "--audit_date", audit_date,
             "--form", "simple"])

    def test_valid_date_refused_as_malformed_call(self):
        root, home = make_home(self)
        page = root / "page.md"
        page.write_text("Body text.\n", encoding="utf-8")
        code, _out, err = self._audit(home, page, "2026-11-17")
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)

    def test_unparsable_date_refused_under_the_same_name(self):
        root, home = make_home(self)
        page = root / "page.md"
        page.write_text("Body text.\n", encoding="utf-8")
        code, _out, err = self._audit(home, page, "not-a-date")
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)
        self.assertNotIn("VALIDATION_FAILED", err)


if __name__ == "__main__":
    unittest.main()
