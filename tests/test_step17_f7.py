"""Step 17 fix seat F7 tests: service, watch, and seams family.

Pins the register entries charged to F7 in the combined fix
wave: S17-R1-038, S17-R1-065, S17-R1-066, S17-R1-067,
S17-R1-068, S17-R1-069, S17-R1-070, S17-R1-071, S17-R1-072,
S17-R1-074, S17-R1-075, S17-R1-077, S17-R1-080, S17-R1-082,
S17-R1-085, S17-R1-086, S17-R1-102, S17-R1-109, S17-R1-111,
and supplementary S17-R1X-011, S17-R1X-016, S17-R1X-026,
S17-R1X-027, S17-R1X-030, S17-R1X-033, S17-R1X-041, with
the WatchPlan limb of S17-R1-033. Every test was written
before its cure and run failing for the register stated
reason. Oracle: the register entries at
design/audit/step-17-r1-findings-register.md and
design/audit/step-17-r1x-findings-register.md, the brief
items they cite, and the combined charge at
design/audit/step-17-r1x-disposition.md.
"""

import contextlib
import datetime
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from citeline import errors, install as install_module
from citeline import journal, service, shell, watch

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = FIXTURES / "w7-page.md"
AUDIT_DATE = "2026-11-13"
PRODUCT = "Acme Ledger"
Q1 = "What is Acme Ledger?"
Q2 = "Best ferry tracker?"
ROUND = "round-1"


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def seed(case, home):
    service.add_product(
        home=str(home), name=PRODUCT,
        canonical_line="Acme Ledger helps teams track citations.",
        domain="acme.example", audit_date=AUDIT_DATE)
    service.set_query_set(
        home=str(home), product=PRODUCT, query_set=[Q1, Q2],
        audit_date=AUDIT_DATE)
    service.name_round(
        home=str(home), product=PRODUCT, round_label=ROUND,
        importer_declaration="all captured",
        supplier_relation="independent party", audit_date=AUDIT_DATE)
    return home


def do_import(home, answer_file, **overrides):
    kwargs = {
        "home": str(home), "answer_file": str(answer_file),
        "product": PRODUCT, "round": ROUND, "engine_label": "Engine A",
        "query": Q1, "kind": "real_sample",
        "captured_on": "2026-11-10", "capture_method": "manual copy",
        "audit_date": AUDIT_DATE,
    }
    kwargs.update(overrides)
    return service.probe_import(**kwargs)


def journal_entries(home):
    path = Path(home) / "journal.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def entries_of_kind(home, kind):
    return [entry for entry in journal_entries(home)
            if entry.get("entry_kind") == kind]


def payloads_of_kind(home, kind):
    return [entry.get("payload") or {}
            for entry in entries_of_kind(home, kind)]


def token_of(exc):
    return getattr(exc, "token", None) or getattr(
        exc, "error_value", None)


def write_config(home, text):
    journal.write_config(str(home), text)


def temp_file(case, content, name="file.txt"):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    path = root / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def write_plan(case, plan, raw=None):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    path = root / "plan.json"
    path.write_text(raw if raw is not None else json.dumps(plan),
                    encoding="utf-8")
    return path


def rechain(home, mutate):
    """Rewrite the journal with one payload mutated, rechained."""
    entries = journal_entries(home)
    mutate(entries)
    lines = []
    previous = None
    for entry in entries:
        entry["previous_hash"] = previous
        raw = journal.canonical_bytes(entry)
        entry["entry_hash"] = hashlib.sha256(raw).hexdigest()
        previous = entry["entry_hash"]
        lines.append(raw.decode("utf-8"))
    (Path(home) / "journal.jsonl").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")


class HomeBase(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)


class SeededBase(HomeBase):
    def setUp(self):
        super().setUp()
        seed(self, self.home)


# ----------------------------------------------------------------
# S17-R1-038: stated limits enforced in the paths they govern.
# ----------------------------------------------------------------

class Test038LimitsEnforced(SeededBase):
    def test_products_per_home_limit_enforced(self):
        write_config(self.home, "products_per_home = 2\n")
        service.add_product(
            home=str(self.home), name="Second Product",
            canonical_line="Second line.", domain="second.example",
            audit_date=AUDIT_DATE)
        with self.assertRaises(Exception) as caught:
            service.add_product(
                home=str(self.home), name="Third Product",
                canonical_line="Third line.", domain="third.example",
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_answers_per_round_limit_enforced(self):
        write_config(self.home, "answers_per_round = 1\n")
        first = temp_file(self, "Acme Ledger is a ledger tool.\n",
                          "a1.txt")
        do_import(self.home, first)
        second = temp_file(
            self, "Another answer naming Acme Ledger plainly.\n",
            "a2.txt")
        with self.assertRaises(Exception) as caught:
            do_import(self.home, second, engine_label="Engine B",
                      captured_on="2026-11-11")
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 1)

    def test_capture_method_length_limit_enforced(self):
        answer = temp_file(self, "Acme Ledger is a ledger tool.\n")
        with self.assertRaises(Exception) as caught:
            do_import(self.home, answer,
                      capture_method="m" * 2001)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)

    def test_extracted_text_answer_limit_enforced(self):
        write_config(
            self.home,
            "extracted_text_length_per_page_or_answer = 10\n")
        answer = temp_file(
            self, "Acme Ledger is a ledger tool with more text.\n")
        with self.assertRaises(Exception) as caught:
            do_import(self.home, answer)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)

    def test_evidence_span_limits_enforced_on_audit_record(self):
        sentences = "\n".join(
            "EvProd grew by %d percent in 2024 according to "
            "Researcher%d (https://src.example/%d)." % (i, i, i)
            for i in range(80))
        page = temp_file(self, "# EvProd\n\n" + sentences + "\n",
                         "page.md")
        record = service.audit(
            home=str(self.home), page_file=str(page),
            audit_date=AUDIT_DATE)
        total = 0
        for check in record["checks"]:
            spans = check.get("evidence_spans") or []
            self.assertLessEqual(len(spans), 20)
            total += len(spans)
            for span in spans:
                self.assertLessEqual(len(span.get("excerpt") or ""), 120)
        self.assertLessEqual(total, 200)

    def test_front_matter_key_count_limit_enforced(self):
        keys = "\n".join("key%d: value%d" % (i, i) for i in range(101))
        page = temp_file(
            self, "---\n%s\n---\n# Title\n\nBody text.\n" % keys,
            "page.md")
        with self.assertRaises(Exception) as caught:
            service.audit(home=str(self.home), page_file=str(page),
                          audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_error_message_length_bounded_in_recorded_error(self):
        exc = errors.CitelineError(
            "x" * 2000, token="VALIDATION_FAILED")
        record = service.recorded_error(exc)
        self.assertLessEqual(len(record["message"]), 500)

    def test_run_wall_clock_backstop_enforced_on_import(self):
        answer = temp_file(self, "Acme Ledger is a ledger tool.\n")
        clock = mock.Mock(side_effect=[0.0, 1.0, 10000.0])
        with mock.patch.object(service, "_clock", clock):
            with self.assertRaises(Exception) as caught:
                do_import(self.home, answer)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 0)


# ----------------------------------------------------------------
# S17-R1-080 and S17-R1X-011: config and raise limits govern.
# ----------------------------------------------------------------

class Test080ConfigGoverns(SeededBase):
    def test_config_page_file_size_governs_audit(self):
        write_config(self.home, "page_file_size = 1\n")
        page = temp_file(
            self,
            "<html><body><script>" + "a" * 1500000 +
            "</script><p>short text</p></body></html>",
            "big.html")
        with self.assertRaises(Exception) as caught:
            service.audit(home=str(self.home), page_file=str(page),
                          audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_config_extracted_text_governs_audit(self):
        write_config(
            self.home,
            "extracted_text_length_per_page_or_answer = 10\n")
        page = temp_file(
            self, "A page holding far more than ten characters "
                  "of plain text.\n", "page.txt")
        with self.assertRaises(Exception) as caught:
            service.audit(home=str(self.home), page_file=str(page),
                          audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")


class TestX011RaisePlumbing(HomeBase):
    def test_raise_reaches_audit_and_is_stated_in_its_record(self):
        write_config(self.home, "journal_length = 3\n")
        service.add_product(
            home=str(self.home), name=PRODUCT,
            canonical_line="Acme Ledger helps teams track citations.",
            domain="acme.example", audit_date=AUDIT_DATE)
        journal.append_entry(
            str(self.home), "limit_raise",
            {"run_id": "run-4", "limit": "limit_39",
             "raised_value": 4},
            audit_date=AUDIT_DATE)
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        self.assertEqual(record["run_id"], "run-4")
        limits = record["limits_in_force"]
        self.assertTrue(limits["raised_limits"])
        self.assertEqual(
            limits["by_limit"]["journal_length"]["value"], 4)
        self.assertEqual(
            limits["by_limit"]["journal_length"]["source"], "raise")

    def test_status_states_it_reports_no_run(self):
        result = service.status(home=str(self.home))
        limits = result["limits_in_force"]
        self.assertIsNone(limits["run_id"])
        self.assertIn("no run", limits["run_reported"])


class TestX016MidRunLimits(HomeBase):
    def test_audit_record_states_limits_at_run_start(self):
        seed(self, self.home)
        write_config(self.home, "page_file_size = 2\n")
        from citeline import acquisition
        original = acquisition.extract_page

        def changing_extract(*args, **kwargs):
            result = original(*args, **kwargs)
            write_config(self.home, "page_file_size = 1\n")
            return result

        with mock.patch.object(
                acquisition, "extract_page", changing_extract):
            record = service.audit(
                home=str(self.home), page_file=str(PAGE),
                audit_date=AUDIT_DATE)
        limits = record["limits_in_force"]
        self.assertEqual(
            limits["by_limit"]["page_file_size"]["value"], 2)
        change = limits.get("config_changed_during_run")
        self.assertIsNotNone(change)
        self.assertEqual(
            change["limits_at_record"]["page_file_size"]["value"], 1)


# ----------------------------------------------------------------
# S17-R1-065 to S17-R1-068: install and shell failure forms.
# ----------------------------------------------------------------

class TestInstallForms(unittest.TestCase):
    def test_065_filesystem_failure_is_a_governed_error(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        blocker = root / "blocker"
        blocker.write_text("occupied", encoding="utf-8")
        with self.assertRaises(
                install_module.InstallError) as caught:
            install_module.install(
                location=str(blocker / "newloc"),
                home=str(root / "home"))
        self.assertIn(caught.exception.exit_code, (2, 3, 5))

    def test_065_install_main_returns_a_table_code_not_1(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        blocker = root / "blocker"
        blocker.write_text("occupied", encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = install_module.main(
                [str(blocker / "loc"), "--home", str(root / "home")])
        self.assertIn(code, (2, 3, 5))
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_066_home_standing_as_a_file_is_refused(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        home_file = root / "home-file"
        home_file.write_text("occupied", encoding="utf-8")
        with self.assertRaises(install_module.InstallError) as caught:
            install_module.install(
                location=str(root / "loc"), home=str(home_file))
        self.assertEqual(caught.exception.token, "DESTINATION_EXISTS")

    def test_067_config_standing_as_a_directory_is_refused(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        location = root / "loc"
        (location / "config.txt").mkdir(parents=True)
        with self.assertRaises(install_module.InstallError) as caught:
            install_module.install(
                location=str(location), home=str(root / "home"))
        self.assertEqual(caught.exception.token, "CONFIG_INVALID")
        self.assertEqual(caught.exception.exit_code, 5)

    def test_067_config_symlink_to_invalid_config_is_checked(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        bad = root / "bad-config.txt"
        bad.write_text("no separator here\n", encoding="utf-8")
        location = root / "loc"
        location.mkdir()
        os.symlink(bad, location / "config.txt")
        with self.assertRaises(install_module.InstallError) as caught:
            install_module.install(
                location=str(location), home=str(root / "home"))
        self.assertEqual(caught.exception.token, "CONFIG_INVALID")

    def test_068_writing_shell_call_over_file_home_is_governed(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        home_file = root / "home-file"
        home_file.write_text("occupied", encoding="utf-8")
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), \
                contextlib.redirect_stdout(io.StringIO()):
            code = shell.main([
                "add-product", "--home", str(home_file),
                "--name", "Ghost", "--canonical_line", "Ghost line.",
                "--domain", "g.example", "--audit_date", AUDIT_DATE])
        self.assertEqual(code, 2)
        self.assertIn("HOME_MISSING", stderr.getvalue())


# ----------------------------------------------------------------
# S17-R1-069 to S17-R1-072, S17-R1-074, S17-R1-109: WatchPlan.
# ----------------------------------------------------------------

class TestWatchPlanForms(SeededBase):
    def picked_plan(self, targets):
        return {
            "home": str(self.home), "scope": "picked",
            "targets": targets, "audit_date": AUDIT_DATE,
            "form": "advanced",
        }

    def test_069_non_string_product_refused_at_open(self):
        plan = self.picked_plan([
            {"product": PRODUCT, "page_file": str(PAGE)},
            {"product": ["x"], "page_file": str(PAGE)},
        ])
        before = len(journal_entries(self.home))
        with self.assertRaises(Exception) as caught:
            watch.run_watch(plan_file=str(write_plan(self, plan)))
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")
        self.assertEqual(len(journal_entries(self.home)), before)

    def test_070_duplicate_target_inert_difference_refused(self):
        variants = [
            {"product": PRODUCT, "page_file": str(PAGE), "zzz": 1},
            {"product": PRODUCT, "page_file": str(PAGE),
             "guide": False},
            {"product": PRODUCT, "page_file": str(PAGE),
             "robots_file": None},
            {"product": PRODUCT,
             "page_file": str(FIXTURES) + "/../fixtures/w7-page.md"},
        ]
        for variant in variants:
            plan = self.picked_plan([
                {"product": PRODUCT, "page_file": str(PAGE)},
                variant,
            ])
            with self.assertRaises(Exception) as caught:
                watch.run_watch(plan_file=str(write_plan(self, plan)))
            self.assertEqual(
                token_of(caught.exception), "WATCH_DUPLICATE_TARGET",
                variant)

    def test_071_coverage_counts_registered_products_only(self):
        service.add_product(
            home=str(self.home), name="Second Product",
            canonical_line="Second line.", domain="second.example",
            audit_date=AUDIT_DATE)
        plan = self.picked_plan([
            {"product": "ghost-1", "page_file": str(PAGE)},
            {"product": "ghost-2", "page_file": str(PAGE)},
            {"product": PRODUCT, "page_file": str(PAGE)},
        ])
        result = watch.run_watch(plan_file=str(write_plan(self, plan)))
        figure = result["coverage_statement"][
            "products_with_audit_target"]
        self.assertEqual(figure["count"], 1)
        self.assertEqual(figure["denominator"], 2)

    def test_071_snapshots_audited_same_population(self):
        plan = self.picked_plan([
            {"product": PRODUCT, "page_file": str(PAGE)}])
        result = watch.run_watch(plan_file=str(write_plan(self, plan)))
        figure = result["coverage_statement"]["snapshots_audited"]
        self.assertEqual(figure["count"], 0)
        self.assertEqual(figure["denominator"], 0)

    def test_072_plan_field_types_validated(self):
        bad_plans = [
            {"output": ["evil-name"]},
            {"output": 12345},
            {"form": ""},
            {"audit_date": 20261113},
            {"cadence": 7},
        ]
        for bad in bad_plans:
            plan = {
                "home": str(self.home), "scope": "estate",
                "audit_date": AUDIT_DATE, "form": "advanced",
            }
            plan.update(bad)
            with self.assertRaises(Exception) as caught:
                watch.run_watch(plan_file=str(write_plan(self, plan)))
            self.assertEqual(
                token_of(caught.exception), "MALFORMED_CALL", bad)

    def test_074_duplicate_plan_key_refused(self):
        raw = (
            '{"home": "%s", "home": "%s", "scope": "estate", '
            '"audit_date": "%s"}'
            % (self.home, self.home, AUDIT_DATE))
        with self.assertRaises(Exception) as caught:
            watch.run_watch(
                plan_file=str(write_plan(self, None, raw=raw)))
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")

    def test_074_duplicate_target_key_refused(self):
        raw = (
            '{"home": "%s", "scope": "picked", "audit_date": "%s", '
            '"targets": [{"product": "%s", "product": "%s", '
            '"page_file": "%s"}]}'
            % (self.home, AUDIT_DATE, PRODUCT, PRODUCT, PAGE))
        with self.assertRaises(Exception) as caught:
            watch.run_watch(
                plan_file=str(write_plan(self, None, raw=raw)))
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")

    def test_033_watchplan_deep_nesting_refused_not_crash(self):
        raw = (
            '{"home": "%s", "scope": "estate", "audit_date": "%s", '
            '"cadence": %s}' % (
                self.home, AUDIT_DATE,
                "[" * 10000 + "]" * 10000))
        with self.assertRaises(Exception) as caught:
            watch.run_watch(
                plan_file=str(write_plan(self, None, raw=raw)))
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")

    def test_109_unknown_plan_key_warns_by_name(self):
        plan = {
            "home": str(self.home), "scope": "estate",
            "audit_date": AUDIT_DATE, "form": "advanced",
            "zzz_unknown": 1,
        }
        result = watch.run_watch(plan_file=str(write_plan(self, plan)))
        warnings = result.get("plan_warnings") or []
        self.assertTrue(
            any("zzz_unknown" in warning for warning in warnings),
            warnings)


# ----------------------------------------------------------------
# S17-R1-075: readers on type swapped stored fields.
# ----------------------------------------------------------------

class Test075TypeSwappedFields(SeededBase):
    def test_answer_text_integer_does_not_crash_probe_report(self):
        answer = temp_file(self, "Acme Ledger is a ledger tool.\n")
        do_import(self.home, answer)

        def mutate(entries):
            for entry in entries:
                if entry.get("entry_kind") == "answer_imported":
                    entry["payload"]["answer_text"] = 12345
        rechain(self.home, mutate)
        with self.assertRaises(errors.CitelineError) as caught:
            service.probe_report(
                home=str(self.home), product=PRODUCT, round=ROUND,
                audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")

    def test_audit_sentences_integer_does_not_crash_guide(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)

        def mutate(entries):
            for entry in entries:
                if entry.get("entry_kind") == "audit_record":
                    entry["payload"]["sentences"] = 123
        rechain(self.home, mutate)
        with self.assertRaises(errors.CitelineError):
            service.guide(
                home=str(self.home), run_id=record["run_id"],
                audit_date=AUDIT_DATE)

    def test_canonical_line_integer_does_not_crash_audit(self):
        def mutate(entries):
            for entry in entries:
                payload = entry.get("payload") or {}
                if "canonical_line" in payload:
                    payload["canonical_line"] = 123
        rechain(self.home, mutate)
        with self.assertRaises(errors.CitelineError) as caught:
            service.audit(
                home=str(self.home), page_file=str(PAGE),
                audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")


# ----------------------------------------------------------------
# S17-R1-077: identities from the append's own sequence.
# ----------------------------------------------------------------

class Test077SequenceIdentities(SeededBase):
    def test_answer_identity_derives_from_append_sequence(self):
        answer = temp_file(self, "Acme Ledger is a ledger tool.\n")
        with mock.patch.object(service, "_entry_count",
                               return_value=0):
            do_import(self.home, answer)
        stored = entries_of_kind(self.home, "answer_imported")
        self.assertEqual(len(stored), 1)
        self.assertEqual(
            stored[0]["payload"]["answer_id"],
            "ans-%d" % stored[0]["sequence"])

    def test_run_identity_derives_from_append_sequence(self):
        with mock.patch.object(service, "_entry_count",
                               return_value=0):
            service.audit(home=str(self.home), page_file=str(PAGE),
                          audit_date=AUDIT_DATE)
        stored = entries_of_kind(self.home, "audit_record")
        self.assertEqual(len(stored), 1)
        self.assertEqual(
            stored[0]["payload"]["run_id"],
            "run-%d" % stored[0]["sequence"])


# ----------------------------------------------------------------
# S17-R1-082: the report fold bound to the first import basis.
# ----------------------------------------------------------------

class Test082FirstImportBasis(SeededBase):
    def test_probe_report_uses_registry_at_first_import(self):
        service.set_aliases(
            home=str(self.home), product=PRODUCT, aliases=["Acme"],
            audit_date=AUDIT_DATE)
        answer = temp_file(
            self, "Acme is a fine tool for ledgers.\n")
        do_import(self.home, answer)
        service.set_aliases(
            home=str(self.home), product=PRODUCT, aliases=[],
            audit_date=AUDIT_DATE)
        report = service.probe_report(
            home=str(self.home), product=PRODUCT, round=ROUND,
            form="advanced", audit_date=AUDIT_DATE)
        self.assertEqual(report["rates"]["named"]["rate"], 1.0)

    def test_probe_report_query_set_stamp_at_first_import(self):
        answer = temp_file(self, "Acme Ledger is a ledger tool.\n")
        do_import(self.home, answer)
        service.set_query_set(
            home=str(self.home), product=PRODUCT,
            query_set=[Q1, Q2, "A third query?"],
            audit_date=AUDIT_DATE)
        report = service.probe_report(
            home=str(self.home), product=PRODUCT, round=ROUND,
            form="advanced", audit_date=AUDIT_DATE)
        stamps = report.get("version_stamps") or {}
        self.assertEqual(stamps.get("query_set_version"), 2)


# ----------------------------------------------------------------
# S17-R1-085: failure records on the routes that append none.
# ----------------------------------------------------------------

class Test085FailureRecords(SeededBase):
    def failure_count(self):
        return len(entries_of_kind(self.home, "failure_record"))

    def test_failed_probe_report_appends_one_failure_record(self):
        before = self.failure_count()
        with self.assertRaises(Exception):
            service.probe_report(
                home=str(self.home), product=PRODUCT,
                round="no-such-round", audit_date=AUDIT_DATE)
        self.assertEqual(self.failure_count(), before + 1)
        record = payloads_of_kind(self.home, "failure_record")[-1]
        self.assertEqual(record["operation"], "probe report")

    def test_failed_guide_appends_one_failure_record(self):
        before = self.failure_count()
        with self.assertRaises(Exception):
            service.guide(
                home=str(self.home), run_id="run-999",
                audit_date=AUDIT_DATE)
        self.assertEqual(self.failure_count(), before + 1)

    def test_failed_query_set_report_appends_one_failure_record(self):
        before = self.failure_count()
        with self.assertRaises(Exception):
            service.query_set_report(
                home=str(self.home), product="no-such-product",
                audit_date=AUDIT_DATE)
        self.assertEqual(self.failure_count(), before + 1)

    def test_failed_audit_appends_one_failure_record(self):
        before = self.failure_count()
        missing = Path(self.home) / "no-such-page.md"
        with self.assertRaises(Exception):
            service.audit(
                home=str(self.home), page_file=str(missing),
                audit_date=AUDIT_DATE)
        self.assertEqual(self.failure_count(), before + 1)
        record = payloads_of_kind(self.home, "failure_record")[-1]
        self.assertEqual(record["operation"], "audit")

    def test_repeated_trend_appends_exactly_one_failure_record(self):
        before = self.failure_count()
        with self.assertRaises(Exception) as caught:
            service.probe_trend(
                home=str(self.home), product=PRODUCT,
                round_a=ROUND, round_b=ROUND, audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "ROUND_REPEATED")
        self.assertEqual(self.failure_count(), before + 1)


# ----------------------------------------------------------------
# S17-R1-086 and S17-R1X-027: corrections aware reporting.
# ----------------------------------------------------------------

class Test086Corrections(SeededBase):
    def correct(self, sequence, corrected_record):
        journal.append_entry(
            str(self.home), "correction",
            {"supersedes_sequence": sequence,
             "corrected_record": corrected_record},
            audit_date=AUDIT_DATE)

    def test_correction_governs_probe_report(self):
        answer = temp_file(self, "Acme Ledger is a ledger tool.\n")
        do_import(self.home, answer)
        stored = entries_of_kind(self.home, "answer_imported")[0]
        corrected = dict(stored["payload"])
        corrected["answer_text"] = "A text naming nothing at all.\n"
        self.correct(stored["sequence"], corrected)
        report = service.probe_report(
            home=str(self.home), product=PRODUCT, round=ROUND,
            form="advanced", audit_date=AUDIT_DATE)
        self.assertEqual(report["rates"]["named"]["rate"], 0.0)

    def test_correction_governs_audit_form_request(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        stored = entries_of_kind(self.home, "audit_record")[0]
        corrected = dict(stored["payload"])
        corrected["canonical_line"] = "The corrected standing line."
        self.correct(stored["sequence"], corrected)
        form = service.audit(
            home=str(self.home), run_id=record["run_id"])
        self.assertEqual(
            form["canonical_line"], "The corrected standing line.")

    def test_correction_governs_guide_from_run(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        stored = entries_of_kind(self.home, "audit_record")[0]
        corrected = json.loads(json.dumps(stored["payload"]))
        corrected["score"]["value"] = 100.0
        corrected["score"]["cap_status"] = True
        self.correct(stored["sequence"], corrected)
        draft = service.guide(
            home=str(self.home), run_id=record["run_id"],
            audit_date=AUDIT_DATE)
        self.assertTrue(draft["cap_status"])

    def test_correction_governs_round_lookup(self):
        answer = temp_file(self, "Acme Ledger is a ledger tool.\n")
        do_import(self.home, answer)
        stored = entries_of_kind(self.home, "round_named")[-1]
        corrected = dict(stored["payload"])
        corrected["round_label"] = "round-renamed"
        self.correct(stored["sequence"], corrected)
        report = service.probe_report(
            home=str(self.home), product=PRODUCT,
            round="round-renamed", form="advanced",
            audit_date=AUDIT_DATE)
        self.assertEqual(report["round"], "round-renamed")
        with self.assertRaises(Exception) as caught:
            service.probe_report(
                home=str(self.home), product=PRODUCT, round=ROUND,
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "UNKNOWN_ROUND")


# ----------------------------------------------------------------
# S17-R1-102: register page operator explanation.
# ----------------------------------------------------------------

class Test102RegisterPageExplanation(SeededBase):
    def test_unknown_snapshot_error_explains_where_snapshots_come_from(
            self):
        with self.assertRaises(Exception) as caught:
            service.register_page(
                home=str(self.home), product=PRODUCT,
                snapshot="/some/page.md", audit_date=AUDIT_DATE)
        message = str(caught.exception)
        self.assertIn("snapshot_id", message)
        self.assertIn("audit", message)
        self.assertIn("belongs to the product", message)


# ----------------------------------------------------------------
# S17-R1X-026, S17-R1X-033: the audit date validator's types.
# ----------------------------------------------------------------

class TestDateValidatorTypes(SeededBase):
    def test_x026_date_object_audit_completes_and_stores_text(self):
        before = len(journal_entries(self.home))
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=datetime.date(2026, 11, 13))
        self.assertEqual(record["audit_date"], "2026-11-13")
        self.assertEqual(len(journal_entries(self.home)), before + 2)
        stored = payloads_of_kind(self.home, "audit_record")[-1]
        self.assertEqual(stored["audit_date"], "2026-11-13")
        self.assertIsInstance(stored["audit_date"], str)

    def test_x026_date_object_guide_completes(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        draft = service.guide(
            home=str(self.home), run_id=record["run_id"],
            audit_date=datetime.datetime(2026, 11, 13, 9, 30))
        self.assertIsNotNone(draft)

    def test_x033_integer_audit_date_normalised_to_text(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=20261114)
        self.assertEqual(record["audit_date"], "2026-11-14")
        stored = payloads_of_kind(self.home, "audit_record")[-1]
        self.assertEqual(stored["audit_date"], "2026-11-14")
        self.assertIsInstance(stored["audit_date"], str)


# ----------------------------------------------------------------
# S17-R1X-030: list_products on a journal that does not parse.
# ----------------------------------------------------------------

class TestX030ListProducts(SeededBase):
    def test_broken_journal_signals_in_the_governed_value(self):
        path = Path(self.home) / "journal.jsonl"
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("this is not a journal line\n")
        with self.assertRaises(errors.CitelineError) as caught:
            service.list_products(home=str(self.home))
        self.assertEqual(
            token_of(caught.exception), "JOURNAL_VERIFY_FAILED")

    def test_empty_home_still_lists_no_products(self):
        root, home = make_home(self)
        self.assertEqual(service.list_products(home=str(home)), [])


# ----------------------------------------------------------------
# S17-R1-111 and S17-R1X-041: the staleness axis omission.
# ----------------------------------------------------------------

class Test111StalenessAxes(SeededBase):
    def round_row(self, view):
        for row in view["records"]:
            if row["record_kind"] == "round":
                return row
        raise AssertionError("no round row in the view")

    def test_round_query_set_axis_bound_and_compared(self):
        answer = temp_file(self, "Acme Ledger is a ledger tool.\n")
        do_import(self.home, answer)
        service.set_query_set(
            home=str(self.home), product=PRODUCT,
            query_set=[Q1, Q2, "A third query?"],
            audit_date=AUDIT_DATE)
        view = service.staleness_view(home=str(self.home))
        row = self.round_row(view)
        self.assertEqual(row["bound_versions"].get(
            "query_set_version"), 2)
        self.assertEqual(row["versions_in_force"].get(
            "query_set_version"), 3)
        self.assertIn("query_set_version", row["changed_axes"])
        self.assertEqual(row["state"], "across a break")

    def test_unbound_mapped_axes_listed_as_not_recorded(self):
        service.audit(home=str(self.home), page_file=str(PAGE),
                      audit_date=AUDIT_DATE)
        view = service.staleness_view(home=str(self.home))
        audit_row = [row for row in view["records"]
                     if row["record_kind"] == "audit_run"][0]
        self.assertIn("lexicon_version", audit_row["not_recorded_axes"])
        round_row = self.round_row(view)
        for axis in ("registry_version", "detector_version",
                     "lexicon_version"):
            self.assertIn(axis, round_row["not_recorded_axes"])
        self.assertEqual(round_row["bound_versions"].get(
            "query_set_version"), 2)


if __name__ == "__main__":
    unittest.main()
