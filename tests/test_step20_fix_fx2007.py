"""Repair tests: shell and text surfaces
and delegated decisions 4 to 11.

Each test pins one settled rule
of design/steps/step-20-register.md on its own evidence.
Copyright: J.P. Picard aka Macro-Harder.
"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from citeline import errors, metrics, reporting, service, shell
from citeline import install as install_module

AUDIT_DATE = "2026-11-17"
PRODUCT = "Acme Ledger"
QUERY = "What is Acme Ledger?"
ROUND = "round-1"
ROOT = Path(__file__).resolve().parent.parent


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


def readme_text():
    return (ROOT / "README.md").read_text(encoding="utf-8")


def answer_row(engine, method, day, control=False, kind="sampled",
               named=True):
    return {
        "named": named, "named_early": False, "cited": False,
        "cluster_id": engine + day, "near_duplicate": False,
        "matched_aliases": [], "query": "q-one",
        "engine_label": engine, "capture_method": method,
        "captured_on": day, "source_kind": kind, "kind": kind,
        "control": control, "control_flag": control,
        "control_kind": "positive" if control else None,
        "competitor_named": False, "per_competitor": [],
        "citation_instances": 0, "self_citation_instances": 0,
        "text": "some answer text",
    }


class TestShellSurfaces(unittest.TestCase):

    def test_s20_13_failure_print_states_failure_record(self):
        root, home = make_home(self)
        code, _out, err = run_shell(
            ["audit", "--home", str(home), "--bogus", "x",
             "--audit_date", AUDIT_DATE])
        self.assertEqual(code, 2)
        self.assertNotIn(
            "Nothing was stored for the failed subject by "
            "this call.", err)
        self.assertIn("failure record", err)
        journal = (home / "journal.jsonl").read_text(
            encoding="utf-8")
        self.assertIn("failure_record", journal)

    def test_s20_15_watch_parse_fault_is_named(self):
        code, _out, err = run_shell(
            ["watch", "--plan", "plan.json", "--bogus", "x"])
        self.assertEqual(code, 2)
        self.assertNotIn("names no plan", err)
        self.assertIn("bogus", err)

    def test_s20_15_watch_missing_plan_still_named(self):
        code, _out, err = run_shell(["watch", "--form", "simple"])
        self.assertEqual(code, 2)
        self.assertIn("names no plan", err)

    def test_s20_17_help_states_exactly_one_selector(self):
        self.assertIn("exactly one selector", shell.help_text())

    def test_s20_33_help_list_sentence_names_six(self):
        text = shell.help_text()
        start = text.index("List valued inputs")
        sentence = text[start:text.index("\n", start)]
        for name in ("--competitors", "--aliases", "--query_set",
                     "--category_terms", "--queries",
                     "--engine_labels"):
            self.assertIn(name, sentence)

    def test_s20_33_readme_list_sentence_names_six(self):
        text = readme_text()
        start = text.index("List valued inputs")
        sentence = text[start:text.index("take a comma", start)]
        for name in ("--queries", "--engine_labels"):
            self.assertIn(name, sentence)

    def test_s20_32_uninstall_home_form_agrees(self):
        self.assertIn("uninstall [location] [home]", readme_text())
        self.assertIn(
            "uninstall [location] [home]", shell.help_text())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            install_module.main(["--help"])
        self.assertIn(
            "uninstall [location] [home]", out.getvalue())

    def test_s20_40_readme_names_uninstall_flag(self):
        self.assertIn("--uninstall", readme_text())

    def test_decision_4_readme_states_retention_locus(self):
        flat = " ".join(readme_text().split())
        self.assertIn(
            "retained until the operator deletes the home "
            "by hand", flat)

    def test_decision_11_exit_one_reserved_in_shell_text(self):
        doc = shell.__doc__ or ""
        self.assertIn("reserved", doc)
        self.assertIn("No domain outcome takes", doc)


class TestR19087SuppliedPathClass(unittest.TestCase):

    def test_missing_page_file_takes_input_class(self):
        root, home = make_home(self)
        missing = root / "no-such-page.md"
        with self.assertRaises(errors.CitelineError) as caught:
            service.audit(
                home=str(home), page_file=str(missing),
                audit_date=AUDIT_DATE)
        self.assertNotEqual(
            caught.exception.token, "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.exit_code, 2)

    def test_existing_directory_page_file_stays_integrity(self):
        root, home = make_home(self)
        with self.assertRaises(errors.CitelineError) as caught:
            service.audit(
                home=str(home), page_file=str(root),
                audit_date=AUDIT_DATE)
        self.assertEqual(
            caught.exception.token, "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.exit_code, 5)

    def test_missing_answer_file_already_input_class(self):
        from citeline import probe_import as import_module
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        with self.assertRaises(Exception) as caught:
            import_module.read_answer_file(str(root / "nope.txt"))
        token = getattr(caught.exception, "token", None) or \
            getattr(caught.exception, "error_value", None) or \
            str(caught.exception)
        self.assertIn("IMPORT_VALIDATION_FAILED", str(token))
        exit_code = getattr(caught.exception, "exit_code", None)
        if exit_code is not None:
            self.assertEqual(exit_code, 2)


class TestCaptureContextDecisions(unittest.TestCase):

    def test_dq_p7g1_context_includes_controls(self):
        answers = [
            answer_row("Engine A", "manual copy", "2026-11-01"),
            answer_row("Control Engine", "control method",
                       "2026-11-02", control=True),
        ]
        result = metrics.round_metrics(answers, "sampled")
        context = result["capture_context"]
        self.assertIn("Control Engine", context["engine_labels"])
        self.assertIn(
            "control method", context["capture_methods"])
        self.assertIn("2026-11-02", context["capture_dates"])
        frame = result["sampling_frame"]
        self.assertIn("Control Engine", frame["engine_label_set"])
        self.assertIn(
            "control method", frame["capture_methods_asserted"])
        self.assertEqual(result["rates"]["named"]["n"], 1)

    def test_dq_p7g2_multi_kind_pooled_context(self):
        entries = []
        for index, (kind, engine) in enumerate((
                ("real_sample", "Engine R"),
                ("fixture", "Engine F"))):
            entries.append({
                "sequence": index + 1,
                "entry_kind": "answer_imported",
                "payload": {
                    "answer_text": "Acme Ledger text %d" % index,
                    "query": QUERY, "kind": kind,
                    "engine_label_original": engine,
                    "engine_label_normalised": engine,
                    "capture_method": "manual copy",
                    "captured_on": "2026-11-10",
                    "control_flag": False,
                },
            })
        result = metrics.round_metrics_from_journal(entries)
        self.assertIn("per_kind", result)
        context = result.get("capture_context") or {}
        labels = context.get("engine_labels") or []
        self.assertIn("Engine R", labels)
        self.assertIn("Engine F", labels)

    def test_dq_p7g3_rows_container_flag_excepted(self):
        record = {"answer_metrics_rows": [{"control_flag": True}],
                  "control_failed": False}
        advanced = reporting.render(record, form="advanced")
        self.assertNotIn("control_failure_notice", advanced)

    def test_dq_p7g3_rows_container_nested_flag_not_excepted(self):
        record = {"answer_metrics_rows": [
                      {"detail": {"control_flag": True}}],
                  "control_failed": False}
        advanced = reporting.render(record, form="advanced")
        self.assertEqual(
            advanced.get("control_failure_notice"),
            reporting.CONTROL_FAILURE_NOTICE)


class TestHomeChainAndLimits(unittest.TestCase):

    def _plain_home(self, root, name, config=None):
        home = root / name
        home.mkdir()
        if config is not None:
            (home / "config.txt").write_text(
                config, encoding="utf-8")
        return home

    def test_decision_9_selection_resolves_to_fixed_point(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        home_c = self._plain_home(root, "home-c")
        home_b = self._plain_home(
            root, "home-b", "home_path = %s\n" % home_c)
        home_a = self._plain_home(
            root, "home-a", "home_path = %s\n" % home_b)
        self.assertEqual(
            service._resolve_home(str(home_a)), str(home_c))

    def test_decision_9_selection_cycle_refused_named(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        home_a = root / "home-a"
        home_b = root / "home-b"
        home_a.mkdir()
        home_b.mkdir()
        (home_a / "config.txt").write_text(
            "home_path = %s\n" % home_b, encoding="utf-8")
        (home_b / "config.txt").write_text(
            "home_path = %s\n" % home_a, encoding="utf-8")
        with self.assertRaises(errors.CitelineError) as caught:
            service._resolve_home(str(home_a))
        self.assertEqual(caught.exception.token, "CONFIG_INVALID")

    def test_decision_10_named_home_limits_govern_import(self):
        root, governed = make_home(self)
        service.add_product(
            home=str(governed), name=PRODUCT,
            canonical_line="Acme Ledger helps teams track "
                           "citations.",
            domain="acme.example", audit_date=AUDIT_DATE)
        service.set_query_set(
            home=str(governed), product=PRODUCT,
            query_set=[QUERY], audit_date=AUDIT_DATE)
        service.name_round(
            home=str(governed), product=PRODUCT,
            round_label=ROUND,
            importer_declaration="all captured",
            supplier_relation="independent party",
            audit_date=AUDIT_DATE)
        named = root / "named-home"
        named.mkdir()
        (named / "config.txt").write_text(
            "home_path = %s\ncapture_method_text_length = 3\n"
            % governed, encoding="utf-8")
        answer_file = root / "answer.txt"
        answer_file.write_text(
            "Acme Ledger is named here. "
            "See https://acme.example/ for more.",
            encoding="utf-8")
        with self.assertRaises(errors.CitelineError) as caught:
            service.probe_import(
                home=str(named), answer_file=str(answer_file),
                product=PRODUCT, round=ROUND,
                engine_label="Engine A", query=QUERY,
                kind="real_sample", captured_on="2026-11-10",
                capture_method="manual copy",
                audit_date=AUDIT_DATE)
        self.assertEqual(caught.exception.token, "LIMIT_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
