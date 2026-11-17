"""Step 19 repair tests, fix seat 5: import intake and watch.

Each class pins one register item from the Step 19 split repair
queue. Tests were written before the fixes they pin.
"""

import json
import tempfile
import unittest
from pathlib import Path

from citeline import acquisition, journal, probe_import, service, shell, watch

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
PAGE = FIXTURES / "w7-page.md"
ANSWER = FIXTURES / "w7-answer.txt"


def seed_home(case):
    from citeline import install as install_module
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    for name in ("p-alpha", "p-beta"):
        service.add_product(
            home=str(home), name=name, canonical_line=name + " line.",
            domain="example.com", audit_date=AUDIT_DATE)
    audit = service.audit(home=str(home), page_file=str(PAGE),
                          audit_date=AUDIT_DATE)
    service.register_page(home=str(home), product="p-alpha",
                          snapshot=audit["snapshot_id"],
                          audit_date=AUDIT_DATE)
    service.set_query_set(home=str(home), product="p-alpha",
                          query_set=["What is Example Product?"],
                          audit_date=AUDIT_DATE)
    service.name_round(home=str(home), product="p-alpha",
                       round_label="round-1",
                       importer_declaration="operator",
                       supplier_relation="first party",
                       audit_date=AUDIT_DATE)
    service.probe_import(
        home=str(home), answer_file=str(ANSWER), product="p-alpha",
        round="round-1", engine_label="engine-a",
        query="What is Example Product?", kind="real_sample",
        captured_on="2026-11-10", capture_method="manual copy",
        audit_date=AUDIT_DATE)
    return root, home


def plan_file(case, data):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    path = root / "plan.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return root, path


def base_plan(home, scope, **extra):
    data = {"home": str(home), "scope": scope,
            "audit_date": AUDIT_DATE, "form": "simple"}
    data.update(extra)
    return data


class TestR19024HtmlForms(unittest.TestCase):
    """R19-024: HTML captures refused in every spelling."""

    SPELLINGS = {
        "prolog": "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                  "<!DOCTYPE html>\n<html><body><p>Answer</p>"
                  "</body></html>",
        "saved_from": "<!-- saved from url=(0023)https://chat.example.com/ -->\n"
                      "<html><body><p>Answer</p></body></html>",
        "comment_led": "<!-- chat export -->\n"
                       "<html><body><p>Answer</p></body></html>",
        "div_fragment": "<div class=\"answer\"><p>Answer text</p></div>",
        "p_fragment": "<p>Answer text</p>",
        "svg": "<svg xmlns=\"http://www.w3.org/2000/svg\">"
               "<text>Answer</text></svg>",
    }

    def test_html_spellings_are_html_form(self):
        for name, text in self.SPELLINGS.items():
            with self.subTest(spelling=name):
                self.assertEqual(
                    probe_import.check11_form(
                        text.encode("utf-8"), text),
                    "html")


class TestR19025JsonLines(unittest.TestCase):
    """R19-025: a JSON lines file with one non JSON line is still
    a JSON lines file, not one plain answer."""

    LINES = [json.dumps({"answer": "answer %d" % i}) for i in range(50)]

    def test_header_line_does_not_defeat_json_lines(self):
        text = "# Exported from ChatGPT on 2026-11-10\n" + "\n".join(self.LINES)
        self.assertEqual(
            probe_import.check11_form(text.encode("utf-8"), text),
            "json_lines")

    def test_truncated_last_line_does_not_defeat_json_lines(self):
        lines = list(self.LINES)
        lines[-1] = lines[-1][:10]
        text = "\n".join(lines)
        self.assertEqual(
            probe_import.check11_form(text.encode("utf-8"), text),
            "json_lines")

    def test_plain_prose_is_not_json_lines(self):
        text = ("Acme Ledger is a bookkeeping tool.\n"
                "It tracks citations for a page.\n"
                "Teams use it every week.")
        self.assertNotEqual(
            probe_import.check11_form(text.encode("utf-8"), text),
            "json_lines")


class TestR19045AllMissingInputs(unittest.TestCase):
    """R19-045: one refusal reports every missing required input."""

    def test_all_missing_inputs_named_in_one_refusal(self):
        with self.assertRaises(Exception) as caught:
            probe_import.validate_adapter_inputs(
                answer_file="answer.txt", product="p-alpha",
                round="round-1", engine_label=None, query=None,
                kind=None, captured_on=None, capture_method=None,
                audit_date=None)
        message = str(caught.exception)
        for name in ("engine_label", "query", "kind", "captured_on",
                     "capture_method", "audit_date"):
            self.assertIn(name, message)


class TestR19026ConfigGovernedSizeLimit(unittest.TestCase):
    """R19-026: the answer file size limit in force governs the
    import intake and stands named in the refusal."""

    def _home_with_limit(self, value):
        root, home = seed_home(self)
        journal.write_config(home, "answer_file_size = %d\n" % value)
        return root, home

    def test_raised_limit_admits_a_larger_answer_file(self):
        root, home = self._home_with_limit(2)
        path = Path(root) / "big-answer.txt"
        path.write_text(
            "This is a plain answer sentence about the product.\n"
            * 30000, encoding="utf-8")
        self.assertGreater(path.stat().st_size, 1024 * 1024)
        record = probe_import.probe_import(
            answer_file=str(path), product="p-alpha", round="round-1",
            engine_label="engine-a", query="What is Example Product?",
            kind="real_sample", captured_on="2026-11-10",
            capture_method="manual copy", audit_date=AUDIT_DATE,
            home=str(home))
        self.assertIsNotNone(record)

    def test_refusal_names_the_limit_in_force(self):
        root, home = self._home_with_limit(2)
        path = Path(root) / "huge-answer.txt"
        path.write_text("word " * 500000, encoding="utf-8")
        self.assertGreater(path.stat().st_size, 2 * 1024 * 1024)
        with self.assertRaises(Exception) as caught:
            probe_import.read_answer_file(str(path), home=str(home))
        self.assertIn("2 MiB", str(caught.exception))


class TestR19027PageFrontMatter(unittest.TestCase):
    """R19-027: the front matter tag construct rule fires at the
    page intake as it fires at the import intake."""

    BLOCK = "---\nkey: &a value\n---\nBody text about the product."

    def test_import_intake_refuses_the_block(self):
        with self.assertRaises(Exception):
            probe_import.extract_front_matter(self.BLOCK)

    def test_page_intake_refuses_the_identical_block(self):
        notes = []
        with self.assertRaises(Exception):
            acquisition._front_matter(self.BLOCK, "text", notes)


class TestR19020Projection(unittest.TestCase):
    """R19-020: the WatchRun projection prices what the round
    will actually append, failure records included."""

    def test_failing_probe_target_is_priced_at_its_failure_record(self):
        _, home = seed_home(self)
        _, path = plan_file(self, base_plan(home, "picked", targets=[
            {"product": "p-alpha", "round": "no-such-round"}]))
        result = watch.run_watch(plan_file=str(path))
        self.assertEqual(result["entries"][0]["outcome"], "failed")
        self.assertEqual(
            result["capacity_projection"]["projected_entries"], 1)

    def test_failing_audit_target_is_priced_at_its_success_cost(self):
        _, home = seed_home(self)
        _, path = plan_file(self, base_plan(home, "picked", targets=[
            {"product": "p-alpha", "page_file": "/no/such/page.md"}]))
        result = watch.run_watch(plan_file=str(path))
        self.assertEqual(result["entries"][0]["outcome"], "failed")
        self.assertEqual(
            result["capacity_projection"]["projected_entries"], 2)


class TestR19053OccupiedOutputFirst(unittest.TestCase):
    """R19-053: an occupied output path refuses before the round
    work runs, so no round is spent producing no artefact."""

    def test_occupied_output_spends_no_round(self):
        root, home = seed_home(self)
        out_path = root / "watchrun.txt"
        out_path.write_text("earlier round\n", encoding="utf-8")
        _, path = plan_file(self, base_plan(
            home, "picked", output=str(out_path), targets=[
                {"product": "p-alpha", "page_file": str(PAGE)}]))
        before = service.status(home=str(home))["entry_count"]
        with self.assertRaises(Exception) as caught:
            watch.run_watch(plan_file=str(path))
        self.assertEqual(
            getattr(caught.exception, "error_value", None),
            "DESTINATION_EXISTS")
        after = service.status(home=str(home))["entry_count"]
        self.assertEqual(before, after)
        self.assertEqual(out_path.read_text(encoding="utf-8"),
                         "earlier round\n")


class TestR19037MissingDirectoryToken(unittest.TestCase):
    """R19-037: a write into a missing directory is not reported
    under DESTINATION_EXISTS."""

    def test_missing_directory_write_names_the_missing_directory(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        out_path = root / "no-such-dir" / "watchrun.txt"
        with self.assertRaises(Exception) as caught:
            watch._write_output({"form": "simple"}, str(out_path),
                                "simple")
        value = getattr(caught.exception, "error_value", None)
        self.assertNotEqual(value, "DESTINATION_EXISTS")
        self.assertIn("does not exist", str(caught.exception))


class TestR19103WatchFormSplit(unittest.TestCase):
    """R19-103: the watch form named on the invocation governs
    the written artefact as it governs the printed rendering."""

    def test_cli_form_governs_the_written_artefact(self):
        root, home = seed_home(self)
        out_path = root / "watchrun.txt"
        _, path = plan_file(self, base_plan(
            home, "picked", output=str(out_path), targets=[
                {"product": "p-alpha", "round": "round-1"}]))
        code = shell.main(
            ["watch", "--plan", str(path), "--form", "agentic"])
        self.assertEqual(code, 0)
        text = out_path.read_text(encoding="utf-8")
        self.assertIn("\"form\": \"agentic\"", text)


class TestR19104PlanWarnings(unittest.TestCase):
    """R19-104: unknown plan keys and a missing form key stand
    warned, not silently accepted."""

    def test_missing_form_key_is_warned(self):
        _, home = seed_home(self)
        data = base_plan(home, "estate")
        del data["form"]
        _, path = plan_file(self, data)
        result = watch.run_watch(plan_file=str(path))
        self.assertTrue(any(
            "form" in warning
            for warning in result["plan_warnings"]))

    def test_unknown_key_is_warned(self):
        _, home = seed_home(self)
        _, path = plan_file(self, base_plan(
            home, "estate", bogus_key="x"))
        result = watch.run_watch(plan_file=str(path))
        self.assertTrue(any(
            "bogus_key" in warning
            for warning in result["plan_warnings"]))


if __name__ == "__main__":
    unittest.main()
