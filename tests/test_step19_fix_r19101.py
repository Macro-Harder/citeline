"""Repair tests: no silent discard between spellings.

Oracle: the settled rule. Where
both spellings of one input stand on a call, the call stands
refused in the open; one value never silently discards the other.
The install positional limb of the item stands with the install
repair; this file pins the two shell limbs.
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


class TestBothSpellingsNeverSilentlyDiscarded(unittest.TestCase):

    def test_set_category_both_spellings_refused(self):
        _root, home = make_home(self)
        service.add_product(
            home=str(home), name="Example Product",
            canonical_line="Example Product answers questions.",
            domain="example.com", audit_date=AUDIT_DATE)
        code, _out, err = run_shell(
            ["set-category", "--home", str(home),
             "--product", "Example Product",
             "--category_terms", "citability",
             "--category", "ranking",
             "--audit_date", AUDIT_DATE])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)

    def test_robots_preview_both_date_spellings_refused(self):
        root, home = make_home(self)
        first = root / "robots-a.txt"
        second = root / "robots-b.txt"
        first.write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
        second.write_text("User-agent: *\nAllow: /\n", encoding="utf-8")
        code, _out, err = run_shell(
            ["robots-preview", "--home", str(home),
             "--first_robots_file", str(first),
             "--second_robots_file", str(second),
             "--evaluated_page_path", "/page",
             "--first_capture_date", "2026-11-10",
             "--second_capture_date", "2026-11-16",
             "--first_captured_on", "2026-11-11",
             "--second_captured_on", "2026-11-15",
             "--audit_date", AUDIT_DATE, "--form", "simple"])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)


if __name__ == "__main__":
    unittest.main()
