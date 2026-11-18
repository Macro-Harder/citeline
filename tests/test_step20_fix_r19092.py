"""Step 20 fix tests for R19-092 and the R19-081 pin restatement.

Oracle: design/audit/step-20-case-r19-092.md, Units A, B, and C,
and the R19-081 restatement in its two halves. A repeat audit
runs new. Audit returns no standing record. The stored record
of a completed audit run is returned only through the named
re-render route, shell subcommand audit-render over service
operation audit_render.

Count discipline in this file: a shell malformed call appends
exactly one governed failure record under the standing shell
discipline, so the shell tests pin the stored audit and
snapshot entry counts as unchanged and state the failure
record count separately. Service calls and successful shell
calls pin the total entry count as unchanged.
"""

import contextlib
import copy
import inspect
import io
import json
import tempfile
import unittest
from pathlib import Path

from citeline import journal, service, shell
from citeline import install as install_module

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
PAGE = FIXTURES / "w7-page.md"
PRODUCT = "Example Product"
README = Path(__file__).parent.parent / "README.md"
FORMS = ("simple", "advanced", "agentic")


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    service.add_product(
        home=str(home), name=PRODUCT,
        canonical_line="Example Product answers questions.",
        domain="example.com", audit_date=AUDIT_DATE)
    return root, home


def run_shell(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), \
            contextlib.redirect_stderr(err):
        code = shell.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def total_count(home):
    return service.status(home=str(home))["entry_count"]


def stored_counts(home):
    kinds = {}
    for entry in journal.fold(str(home)):
        kind = entry.get("entry_kind")
        kinds[kind] = kinds.get(kind, 0) + 1
    return kinds


def stored_audit_snapshot(home):
    kinds = stored_counts(home)
    return (kinds.get("audit_record", 0),
            kinds.get("snapshot_registered", 0))


def failure_count(home):
    return stored_counts(home).get("failure_record", 0)


class R19092Base(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)
        self.record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        self.run_id = self.record["run_id"]


class TestUnitAAuditStopsReturningStandingRecord(R19092Base):

    def test_a1_shell_audit_run_id_refused_in_all_forms(self):
        for form in FORMS:
            with self.subTest(form=form):
                stored_before = stored_audit_snapshot(self.home)
                failures_before = failure_count(self.home)
                code, _out, err = run_shell(
                    ["audit", "--home", str(self.home),
                     "--run_id", self.run_id, "--form", form])
                self.assertEqual(code, 2)
                self.assertIn("MALFORMED_CALL", err)
                self.assertEqual(
                    stored_audit_snapshot(self.home), stored_before)
                self.assertEqual(
                    failure_count(self.home), failures_before + 1)

    def test_a2_page_file_required_without_exception(self):
        stored_before = stored_audit_snapshot(self.home)
        code, _out, err = run_shell(
            ["audit", "--home", str(self.home),
             "--run_id", self.run_id])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)
        code, _out, err = run_shell(
            ["audit", "--home", str(self.home)])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)
        self.assertEqual(
            stored_audit_snapshot(self.home), stored_before)

    def test_a3_run_id_absent_from_service_audit_signatures(self):
        for func in (service.audit, service._audit_impl,
                     service._audit_body):
            with self.subTest(func=func.__name__):
                self.assertNotIn(
                    "run_id", inspect.signature(func).parameters)

    def test_a4_two_fresh_audits_are_distinct_operations(self):
        before = total_count(self.home)
        one = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        two = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        self.assertNotEqual(one["run_id"], two["run_id"])
        self.assertNotEqual(one["snapshot_id"], two["snapshot_id"])
        self.assertEqual(total_count(self.home), before + 4)


class TestUnitBNamedRerenderRoute(R19092Base):

    def test_b1_service_audit_render_return_shape(self):
        before = total_count(self.home)
        rendered = service.audit_render(
            home=str(self.home), run_id=self.run_id)
        self.assertEqual(
            rendered["audit_run"], self.record["audit_run"])
        self.assertNotIn("snapshot", rendered)
        self.assertEqual(total_count(self.home), before)

    def test_b2_shell_audit_render_all_forms_byte_identical(self):
        before = total_count(self.home)
        for form in FORMS:
            with self.subTest(form=form):
                code_one, out_one, err_one = run_shell(
                    ["audit-render", "--home", str(self.home),
                     "--run_id", self.run_id, "--form", form])
                code_two, out_two, _err_two = run_shell(
                    ["audit-render", "--home", str(self.home),
                     "--run_id", self.run_id, "--form", form])
                self.assertEqual(code_one, 0, err_one)
                self.assertEqual(code_two, 0)
                self.assertEqual(out_one, out_two)
                if form in ("advanced", "agentic"):
                    self.assertIn(self.run_id, out_one)
        self.assertEqual(total_count(self.home), before)

    def test_b3_fresh_input_beside_run_id_refused(self):
        stored_before = stored_audit_snapshot(self.home)
        for extra in (["--page_file", str(PAGE)],
                      ["--audit_date", AUDIT_DATE]):
            with self.subTest(extra=extra):
                code, _out, err = run_shell(
                    ["audit-render", "--home", str(self.home),
                     "--run_id", self.run_id] + extra)
                self.assertEqual(code, 2)
                self.assertIn("MALFORMED_CALL", err)
        self.assertEqual(
            stored_audit_snapshot(self.home), stored_before)

    def test_b4_missing_run_id_refused(self):
        stored_before = stored_audit_snapshot(self.home)
        code, _out, err = run_shell(
            ["audit-render", "--home", str(self.home)])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)
        self.assertEqual(
            stored_audit_snapshot(self.home), stored_before)

    def test_b5_unknown_id_pair_pins_unknown_round(self):
        before = total_count(self.home)
        with self.assertRaises(Exception) as caught:
            service.audit_render(
                home=str(self.home), run_id="no-such-run")
        record = service.recorded_error(caught.exception)
        self.assertEqual(record.get("error_value"), "UNKNOWN_ROUND")
        self.assertIn(
            "no completed audit record stands under the "
            "identity given", str(caught.exception))
        self.assertEqual(total_count(self.home), before)
        code, _out, err = run_shell(
            ["audit-render", "--home", str(self.home),
             "--run_id", "no-such-run"])
        self.assertEqual(code, 2)
        self.assertIn("UNKNOWN_ROUND", err)
        self.assertEqual(total_count(self.home), before)


class TestUnitCHelpAndReadme(unittest.TestCase):

    def _line(self, lines, prefix):
        for line in lines:
            if line.strip().startswith(prefix):
                return line.strip()
        self.fail("no line starting with %r" % prefix)

    def test_c1_help_and_readme_surface_agreement(self):
        help_lines = shell.help_text().splitlines()
        readme_lines = README.read_text(
            encoding="utf-8").splitlines()
        help_audit = self._line(help_lines, "audit --home")
        readme_audit = self._line(readme_lines, "audit --home")
        self.assertEqual(help_audit, readme_audit)
        self.assertNotIn("--run_id", help_audit)
        self.assertNotIn("--run_id", readme_audit)
        help_render = self._line(help_lines, "audit-render ")
        readme_render = self._line(readme_lines, "audit-render ")
        self.assertEqual(help_render, readme_render)
        self.assertEqual(
            help_render, "audit-render --home --run_id --form")

    def test_c2_readme_states_the_split_in_prose(self):
        text = " ".join(
            README.read_text(encoding="utf-8").split())
        self.assertIn("An audit call runs a new audit", text)
        self.assertIn(
            "audit-render returns the stored record of a "
            "completed audit run and runs no audit", text)


def _mask_identity(value):
    if isinstance(value, dict):
        return {
            key: ("<identity>" if key in ("run_id", "snapshot_id")
                  else _mask_identity(item))
            for key, item in value.items()}
    if isinstance(value, list):
        return [_mask_identity(item) for item in value]
    return value


class TestR19081RestatedPin(R19092Base):

    def test_r19081_fresh_pair_differs_only_at_identity_loci(self):
        one = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        two = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        self.assertNotEqual(one["run_id"], two["run_id"])
        self.assertNotEqual(one["snapshot_id"], two["snapshot_id"])
        self.assertEqual(
            _mask_identity(one), _mask_identity(two))
        text_one = json.dumps(one, sort_keys=True, default=str)
        text_two = json.dumps(two, sort_keys=True, default=str)
        self.assertNotEqual(text_one, text_two)

    def test_r19081_byte_identity_holds_on_rerender_route(self):
        for form in FORMS:
            with self.subTest(form=form):
                code_one, out_one, err_one = run_shell(
                    ["audit-render", "--home", str(self.home),
                     "--run_id", self.run_id, "--form", form])
                code_two, out_two, _err = run_shell(
                    ["audit-render", "--home", str(self.home),
                     "--run_id", self.run_id, "--form", form])
                self.assertEqual(code_one, 0, err_one)
                self.assertEqual(code_two, 0)
                self.assertEqual(out_one, out_two)
        rendered = service.audit_render(
            home=str(self.home), run_id=self.run_id)
        self.assertEqual(
            rendered["audit_run"], self.record["audit_run"])


if __name__ == "__main__":
    unittest.main()
