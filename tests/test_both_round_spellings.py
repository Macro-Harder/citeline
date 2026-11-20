"""Repair tests: two spellings of the round label.

Oracle: the settled rule. A call carrying
both round label spellings stands refused in the open, so flag
order never silently chooses the round that gets named.
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


def seed_product(home):
    service.add_product(
        home=str(home), name="Example Product",
        canonical_line="Example Product answers questions.",
        domain="example.com", audit_date=AUDIT_DATE)


class TestBothRoundSpellings(unittest.TestCase):

    def _name_round(self, home, flags):
        return run_shell(
            ["name-round", "--home", str(home),
             "--product", "Example Product"] + flags + [
                 "--importer_declaration", "operator",
                 "--supplier_relation", "first party",
                 "--audit_date", AUDIT_DATE])

    def test_both_spellings_refused_round_first(self):
        _root, home = make_home(self)
        seed_product(home)
        code, _out, err = self._name_round(
            home, ["--round", "round-2", "--round_label", "round-3"])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)

    def test_both_spellings_refused_label_first(self):
        _root, home = make_home(self)
        seed_product(home)
        code, _out, err = self._name_round(
            home, ["--round_label", "round-3", "--round", "round-2"])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)

    def test_single_spelling_still_names_the_round(self):
        _root, home = make_home(self)
        seed_product(home)
        code, _out, err = self._name_round(home, ["--round", "round-2"])
        self.assertEqual(code, 0, err)


if __name__ == "__main__":
    unittest.main()
