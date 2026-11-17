"""Step 19 fix tests for R19-099: a repeated scalar flag stands refused.

Oracle: register item R19-099 and brief CL19-044, repetition stands
admitted for list valued inputs only. A repeated scalar flag must
never silently govern by its last value.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from citeline import install as install_module
from citeline import registry, service, shell

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


class TestRepeatedScalarFlag(unittest.TestCase):

    def test_repeated_form_flag_refused(self):
        _root, home = make_home(self)
        code, _out, err = run_shell(
            ["status", "--home", str(home),
             "--form", "simple", "--form", "advanced"])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)

    def test_repeated_home_flag_refused(self):
        _root, home = make_home(self)
        code, _out, err = run_shell(
            ["status", "--home", str(home), "--home", str(home)])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)

    def test_repeated_name_flag_refused_and_nothing_stored(self):
        _root, home = make_home(self)
        code, _out, err = run_shell(
            ["add-product", "--home", str(home),
             "--name", "First Product", "--name", "Second Product",
             "--canonical_line", "A line.",
             "--domain", "example.com",
             "--audit_date", AUDIT_DATE])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)
        products = service.list_products(home=str(home))
        records = products.get("products", []) \
            if isinstance(products, dict) else products
        self.assertEqual(records, [])

    def test_repeated_list_flag_still_admitted(self):
        _root, home = make_home(self)
        code, _out, err = run_shell(
            ["add-product", "--home", str(home),
             "--name", "Example Product",
             "--canonical_line", "A line.",
             "--domain", "example.com",
             "--aliases", "Alpha", "--aliases", "Beta",
             "--audit_date", AUDIT_DATE])
        self.assertEqual(code, 0, err)
        record = registry.get_product(str(home), "Example Product")
        self.assertEqual(record["aliases"], ["Alpha", "Beta"])


if __name__ == "__main__":
    unittest.main()
