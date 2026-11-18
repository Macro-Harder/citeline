"""Step 19 Phase 7 fix seat E tests.

This file pins the Phase 7 home selection items
S19-P7A2-05 and S19-P7A2-06 at the service and shell loci. Tests were written before the fixes they pin.
Dates are call inputs in every test.

Restatement, Step 20 seat FX20-09: three pins in this file
stated the superseded one hop behaviour for home
selection. Delegated decision 9 of the Step 20 register
decides that selection resolves to a fixed point and that
a selection cycle is refused with a named error, never
followed and never looped, and the FX20-07 cure lands
that decision with the token CONFIG_INVALID at row X-1.
The chain pin, the shell status pin, and the cycle pin
stand restated to that behaviour in their original
strength. Where a service call naming an earlier home in
the chain itself resolves to the fixed point under the
decision, the landing assertions for the earlier homes
stand read at the journal level, over the entries each
home's own journal holds, which is the level at which
where the product landed stands stated without the
resolution the pin is testing. The three relative
selection pins stand as they stood: relative selection
was not superseded.
"""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from citeline import journal, service, shell
from citeline import install as install_module

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
ANSWER = FIXTURES / "w7-answer.txt"
QUERY = "What is Example Product?"


def make_home(case, name="home"):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / ("install-" + name), root / name
    install_module.install(location=str(location), home=str(home))
    return root, home


def seed(case, home, product="p-alpha"):
    service.add_product(
        home=str(home), name=product, canonical_line=product + " line.",
        domain="example.com", audit_date=AUDIT_DATE)
    service.set_query_set(home=str(home), product=product,
                          query_set=[QUERY], audit_date=AUDIT_DATE)
    service.name_round(home=str(home), product=product,
                       round_label="round-1",
                       importer_declaration="operator",
                       supplier_relation="first party",
                       audit_date=AUDIT_DATE)
    return home


def raw_entries(home):
    path = Path(home) / "journal.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def count(home):
    return len(raw_entries(home))


def failures(home):
    return [e for e in raw_entries(home)
            if e.get("entry_kind") == "failure_record"]


def set_cap(home, n):
    journal.write_config(home, "journal_length = %d\n" % n)


def page_file(root, name="page.txt"):
    p = Path(root) / name
    p.write_text("# Example Product\n\np-alpha line.\n\n"
                 "Example Product does things well.\n", encoding="utf-8")
    return p


def answer_file(root, name, text):
    p = Path(root) / name
    p.write_text(text, encoding="utf-8")
    return p


def tok(exc):
    return (getattr(exc, "token", None)
            or getattr(exc, "error_value", None))


def import_kwargs(answer):
    return dict(answer_file=str(answer), product="p-alpha",
                round="round-1", engine_label="engine-a", query=QUERY,
                kind="real_sample", captured_on="2026-11-10",
                capture_method="manual copy", audit_date=AUDIT_DATE)


def install_at(root, tag, home):
    location = Path(root) / ("install-" + tag)
    install_module.install(location=str(location), home=str(home))
    return home


def product_names(home):
    return [item.get("name") for item in service.list_products(home=str(home))]


def journal_holds(home, name):
    return any(name in json.dumps(entry) for entry in raw_entries(home))


class TestP7A2HomeSelection(unittest.TestCase):
    """S19-P7A2-05 and S19-P7A2-06: the home a governing call
    acts on stands the same at every entry point, and a
    relative home_path selection denotes a fixed home, not
    whatever the caller working directory makes it denote.
    Selection resolves to a fixed point, and a selection
    cycle stands refused with CONFIG_INVALID."""

    def _chain(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        home_c = install_at(root, "c", root / "home-c")
        home_b = install_at(root, "b", root / "home-b")
        home_a = install_at(root, "a", root / "home-a")
        journal.write_config(home_b, "home_path = %s\n" % (home_c,))
        journal.write_config(home_a, "home_path = %s\n" % (home_b,))
        return root, home_a, home_b, home_c

    def test_direct_service_chain_resolves_to_fixed_point(self):
        root, home_a, home_b, home_c = self._chain()
        service.add_product(
            home=str(home_a), name="p-chain",
            canonical_line="p-chain line.", domain="example.com",
            audit_date=AUDIT_DATE)
        self.assertIn("p-chain", product_names(home_c))
        self.assertTrue(journal_holds(home_c, "p-chain"))
        self.assertFalse(journal_holds(home_a, "p-chain"))
        self.assertFalse(journal_holds(home_b, "p-chain"))
        self.assertEqual(service.status(home=str(home_a))["home_path"],
                         str(home_c))

    def test_shell_no_flag_status_matches_direct_service_on_chain(self):
        root, home_a, home_b, home_c = self._chain()
        out = io.StringIO()
        with mock.patch.object(shell, "_default_home",
                               lambda: str(home_a)):
            with redirect_stdout(out):
                code = shell.main(["status", "--form", "simple"])
        self.assertEqual(code, 0)
        self.assertIn(str(home_c), out.getvalue())
        self.assertNotIn(str(home_b), out.getvalue())

    def test_cycle_is_refused_with_config_invalid(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        home_b = install_at(root, "cb", root / "home-cb")
        home_a = install_at(root, "ca", root / "home-ca")
        journal.write_config(home_a, "home_path = %s\n" % (home_b,))
        journal.write_config(home_b, "home_path = %s\n" % (home_a,))
        with self.assertRaises(Exception) as caught_a:
            service.add_product(
                home=str(home_a), name="p-cyc-a",
                canonical_line="p-cyc-a line.", domain="example.com",
                audit_date=AUDIT_DATE)
        self.assertEqual(tok(caught_a.exception), "CONFIG_INVALID")
        with self.assertRaises(Exception) as caught_b:
            service.add_product(
                home=str(home_b), name="p-cyc-b",
                canonical_line="p-cyc-b line.", domain="example.com",
                audit_date=AUDIT_DATE)
        self.assertEqual(tok(caught_b.exception), "CONFIG_INVALID")
        self.assertFalse(journal_holds(home_a, "p-cyc-a"))
        self.assertFalse(journal_holds(home_b, "p-cyc-a"))
        self.assertFalse(journal_holds(home_a, "p-cyc-b"))
        self.assertFalse(journal_holds(home_b, "p-cyc-b"))

    def _relative_setup(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        home_a = install_at(root, "ra", root / "home-a")
        target = install_at(root, "rt", home_a / "reltarget")
        journal.write_config(home_a, "home_path = reltarget\n")
        return root, home_a, target

    def test_relative_selection_ignores_caller_directory_decoy(self):
        root, home_a, target = self._relative_setup()
        elsewhere = root / "elsewhere"
        decoy = install_at(root, "decoy", elsewhere / "reltarget")
        cwd = os.getcwd()
        try:
            os.chdir(str(elsewhere))
            service.add_product(
                home=str(home_a), name="p-rel",
                canonical_line="p-rel line.", domain="example.com",
                audit_date=AUDIT_DATE)
        finally:
            os.chdir(cwd)
        self.assertIn("p-rel", product_names(target))
        self.assertNotIn("p-rel", product_names(decoy))

    def test_relative_selection_works_from_unrelated_directory(self):
        root, home_a, target = self._relative_setup()
        empty = root / "empty"
        empty.mkdir()
        cwd = os.getcwd()
        try:
            os.chdir(str(empty))
            service.add_product(
                home=str(home_a), name="p-rel2",
                canonical_line="p-rel2 line.", domain="example.com",
                audit_date=AUDIT_DATE)
        finally:
            os.chdir(cwd)
        self.assertIn("p-rel2", product_names(target))

    def test_shell_relative_selection_reports_the_fixed_home(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        operator = root / "operator"
        default_home = operator / ".citeline"
        default_home.mkdir(parents=True)
        target = install_at(root, "srt", default_home / "reltarget")
        (default_home / "config.txt").write_text(
            "home_path = reltarget\n", encoding="utf-8")
        elsewhere = root / "elsewhere"
        install_at(root, "sdecoy", elsewhere / "reltarget")
        out = io.StringIO()
        cwd = os.getcwd()
        try:
            os.chdir(str(elsewhere))
            with mock.patch.dict(os.environ, {"HOME": str(operator)}):
                with redirect_stdout(out):
                    code = shell.main(["status", "--form", "simple"])
        finally:
            os.chdir(cwd)
        self.assertEqual(code, 0)
        self.assertIn(str(target), out.getvalue())


if __name__ == "__main__":
    unittest.main()
