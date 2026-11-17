"""Step 19 fix tests for R19-082: set-category and --category.

Oracle: register item R19-082 and brief CL19-033. The README, the
help text, and brief Section 5.12 name category_terms only, so the
undocumented category spelling stands refused on set-category.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from citeline import install as install_module
from citeline import service, shell

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


class TestSetCategorySpelling(unittest.TestCase):

    def setUp(self):
        _root, self.home = make_home(self)
        service.add_product(
            home=str(self.home), name="Example Product",
            canonical_line="Example Product answers questions.",
            domain="example.com", audit_date=AUDIT_DATE)

    def test_category_spelling_refused(self):
        code, _out, err = run_shell(
            ["set-category", "--home", str(self.home),
             "--product", "Example Product",
             "--category", "citability",
             "--audit_date", AUDIT_DATE])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)

    def test_category_terms_spelling_accepted(self):
        code, _out, err = run_shell(
            ["set-category", "--home", str(self.home),
             "--product", "Example Product",
             "--category_terms", "citability",
             "--audit_date", AUDIT_DATE])
        self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()
