"""Step 19 fix tests for R19-083: robots-preview capture dates.

Oracle: register item R19-083, README CL19-038, help CL19-073, and
plan decision T-11. The capture dates arrive only as
first_capture_date and second_capture_date; the captured_on
spelling pair stands refused on robots-preview.
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


class TestRobotsPreviewSpellings(unittest.TestCase):

    def setUp(self):
        self.root, self.home = make_home(self)
        self.first = self.root / "robots-a.txt"
        self.second = self.root / "robots-b.txt"
        self.first.write_text("User-agent: *\nAllow: /\n",
                              encoding="utf-8")
        self.second.write_text("User-agent: *\nAllow: /\n",
                               encoding="utf-8")

    def _preview(self, date_flags):
        return run_shell(
            ["robots-preview", "--home", str(self.home),
             "--first_robots_file", str(self.first),
             "--second_robots_file", str(self.second),
             "--evaluated_page_path", "/page"] + date_flags + [
                 "--audit_date", AUDIT_DATE, "--form", "simple"])

    def test_captured_on_pair_refused(self):
        code, _out, err = self._preview(
            ["--first_captured_on", "2026-11-10",
             "--second_captured_on", "2026-11-16"])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)

    def test_capture_date_pair_accepted(self):
        code, _out, err = self._preview(
            ["--first_capture_date", "2026-11-10",
             "--second_capture_date", "2026-11-16"])
        self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()
