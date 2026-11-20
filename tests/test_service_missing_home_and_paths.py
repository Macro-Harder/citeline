"""Service, watch, seams.

Pins the settled rules:
and, plus the report route backstop limb of charged
through the F5 refusal. Every test was written before
its cure and run failing for the register stated reason.
Oracle: the round 2 settled findings."""

import contextlib
import hashlib
import io
import json
import os
import tempfile
import threading
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


def mutate_payload(home, kind, field, value, index=0):
    def change(entries):
        seen = 0
        for entry in entries:
            if entry.get("entry_kind") == kind:
                if seen == index:
                    entry["payload"][field] = value
                    return
                seen += 1
        raise AssertionError("no %s entry" % kind)
    rechain(home, change)


def mutate_product_field(home, field, value):
    """Set one field on every registry payload carrying it,
    so the standing product record itself carries the swap."""
    def change(entries):
        for entry in entries:
            if entry.get("entry_kind") in (
                    "product_registered", "registry_change"):
                payload = entry.get("payload") or {}
                if field in payload:
                    payload[field] = value
    rechain(home, change)


class HomeBase(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)


class SeededBase(HomeBase):
    def setUp(self):
        super().setUp()
        seed(self, self.home)


# ----------------------------------------------------------------:
# a NUL byte in a supplied path stands in the governed vocabulary
# at the service routes.
# ----------------------------------------------------------------

class Test018NulPathVocabulary(SeededBase):

    def test_audit_nul_page_refuses_supplied_path_unsafe(self):
        with self.assertRaises(Exception) as caught:
            service.audit(
                home=str(self.home), page_file="bad\x00p.md",
                audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "SUPPLIED_PATH_UNSAFE")

    def test_audit_nul_page_failure_record_carries_token(self):
        before = len(entries_of_kind(self.home, "failure_record"))
        with self.assertRaises(Exception):
            service.audit(
                home=str(self.home), page_file="bad\x00p.md",
                audit_date=AUDIT_DATE)
        records = payloads_of_kind(self.home, "failure_record")
        self.assertEqual(len(records), before + 1)
        self.assertEqual(
            records[-1]["error_value"], "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(
            records[-1]["rule_fired"], "SUPPLIED_PATH_UNSAFE")

    def test_audit_nul_robots_refuses_supplied_path_unsafe(self):
        with self.assertRaises(Exception) as caught:
            service.audit(
                home=str(self.home), page_file=str(PAGE),
                robots_file="bad\x00r.txt", audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(
            len(entries_of_kind(self.home, "snapshot_registered")), 0)

    def test_robots_route_nul_refuses_supplied_path_unsafe(self):
        with self.assertRaises(Exception) as caught:
            service.robots(
                home=str(self.home), robots_file="bad\x00r.txt",
                audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "SUPPLIED_PATH_UNSAFE")

    def test_robots_preview_nul_refuses_supplied_path_unsafe(self):
        good = temp_file(self, "User-agent: *\nAllow: /\n", "r.txt")
        with self.assertRaises(Exception) as caught:
            service.robots_preview(
                home=str(self.home), first_robots_file=str(good),
                second_robots_file="bad\x00r.txt",
                audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "SUPPLIED_PATH_UNSAFE")

    def test_import_nul_answer_refuses_and_records_token(self):
        with self.assertRaises(Exception) as caught:
            do_import(self.home, "bad\x00a.txt")
        self.assertEqual(
            token_of(caught.exception), "SUPPLIED_PATH_UNSAFE")
        records = payloads_of_kind(self.home, "failure_record")
        self.assertTrue(records)
        self.assertEqual(
            records[-1]["error_value"], "SUPPLIED_PATH_UNSAFE")

    def test_import_surrogate_answer_refuses_and_records_token(self):
        with self.assertRaises(Exception) as caught:
            do_import(self.home, "bad\ud800a.txt")
        self.assertEqual(
            token_of(caught.exception), "SUPPLIED_PATH_UNSAFE")
        records = payloads_of_kind(self.home, "failure_record")
        self.assertTrue(records)
        self.assertEqual(
            records[-1]["error_value"], "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(
            records[-1]["rule_fired"], "SUPPLIED_PATH_UNSAFE")

    def test_shell_audit_nul_answers_with_token(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            code = shell.main([
                "audit", "--home", str(self.home),
                "--page_file", "bad\x00p.md",
                "--audit_date", AUDIT_DATE])
        self.assertEqual(code, 5)
        self.assertIn("SUPPLIED_PATH_UNSAFE", err.getvalue())


# ----------------------------------------------------------------
# and: no state created by a read over a missing home, and the
# guide assembly runs the home check.
# ----------------------------------------------------------------

class Test070MissingHomeCreatesNothing(unittest.TestCase):

    def setUp(self):
        self.root = Path(
            self.enterContext(tempfile.TemporaryDirectory()))
        self.missing = self.root / "missing-home"

    def test_probe_report_missing_home_creates_nothing(self):
        with self.assertRaises(Exception) as caught:
            service.probe_report(
                home=str(self.missing), product=PRODUCT, round=ROUND,
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "HOME_MISSING")
        self.assertFalse(self.missing.exists())

    def test_fresh_audit_missing_home_creates_nothing(self):
        with self.assertRaises(Exception) as caught:
            service.audit(
                home=str(self.missing), page_file=str(PAGE),
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "HOME_MISSING")
        self.assertFalse(self.missing.exists())

    def test_query_set_report_missing_home_creates_nothing(self):
        with self.assertRaises(Exception) as caught:
            service.query_set_report(
                home=str(self.missing), product=PRODUCT,
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "HOME_MISSING")
        self.assertFalse(self.missing.exists())


class Test071GuideMissingHome(SeededBase):

    def setUp(self):
        super().setUp()
        self.missing = self.root / "missing-home"

    def test_guide_by_run_missing_home_is_home_missing(self):
        with self.assertRaises(Exception) as caught:
            service.guide(
                home=str(self.missing), run_id="run-1",
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "HOME_MISSING")
        self.assertFalse(self.missing.exists())

    def test_guide_by_round_missing_home_is_home_missing(self):
        with self.assertRaises(Exception) as caught:
            service.guide(
                home=str(self.missing), product=PRODUCT,
                round_label=ROUND, audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "HOME_MISSING")
        self.assertFalse(self.missing.exists())


# ----------------------------------------------------------------:
# the audit appends land whole or not at all, on the batch
# primitive, and its failure record catches every governed failure
# class of the route.
# ----------------------------------------------------------------

class Test072AuditAppendComposition(SeededBase):

    def test_robots_decoding_failure_leaves_no_orphan(self):
        robots = temp_file(self, b"\xff\xfe\x00\x00bad", "r.bin")
        before = len(journal_entries(self.home))
        with self.assertRaises(Exception) as caught:
            service.audit(
                home=str(self.home), page_file=str(PAGE),
                robots_file=str(robots), audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "ROBOTS_DECODING_FAILED")
        self.assertEqual(
            len(entries_of_kind(self.home, "snapshot_registered")), 0)
        self.assertEqual(
            len(entries_of_kind(self.home, "audit_record")), 0)
        records = payloads_of_kind(self.home, "failure_record")
        self.assertEqual(len(journal_entries(self.home)), before + 1)
        self.assertEqual(
            records[-1]["error_value"], "ROBOTS_DECODING_FAILED")

    def test_failure_after_extraction_leaves_no_orphan(self):
        from citeline import checks as checks_module
        boom = errors.CitelineError(
            "the checks computation failed in a governed form",
            token="PAGE_EXTRACTION_FAILED")
        with mock.patch.object(
                checks_module, "run_checks", side_effect=boom):
            with self.assertRaises(Exception) as caught:
                service.audit(
                    home=str(self.home), page_file=str(PAGE),
                    audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "PAGE_EXTRACTION_FAILED")
        self.assertEqual(
            len(entries_of_kind(self.home, "snapshot_registered")), 0)
        self.assertEqual(
            len(entries_of_kind(self.home, "audit_record")), 0)
        self.assertEqual(
            len(entries_of_kind(self.home, "failure_record")), 1)

    def test_successful_audit_stores_snapshot_and_record_together(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        snapshots = payloads_of_kind(self.home, "snapshot_registered")
        records = payloads_of_kind(self.home, "audit_record")
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(record["snapshot_id"], snapshots[0]["snapshot_id"])
        self.assertEqual(records[0]["snapshot_id"], snapshots[0]["snapshot_id"])
        self.assertEqual(records[0]["run_id"], record["run_id"])


# ----------------------------------------------------------------,
# service limb: the run time aliases and category terms reach the
# guide draft from the audit record.
# ----------------------------------------------------------------

class Test058ServiceGuideBasis(HomeBase):

    PAGE_TEXT = (
        "# Acme Ledger\n\n"
        "Acme Ledger helps teams track citations.\n\n"
        "Plain results were recorded across many trials in "
        "the review period.\n\n"
        "Zebras recorded 43 percent growth in the 2025 review.\n\n"
        "Widge recorded 44 percent growth in the 2025 review.\n")

    def setUp(self):
        super().setUp()
        service.add_product(
            home=str(self.home), name=PRODUCT,
            canonical_line="Acme Ledger helps teams track citations.",
            domain="acme.example", aliases=["Widge"],
            audit_date=AUDIT_DATE)
        self.page = temp_file(self, self.PAGE_TEXT, "page.md")
        self.record = service.audit(
            home=str(self.home), page_file=str(self.page),
            audit_date=AUDIT_DATE)

    def test_audit_record_carries_run_time_aliases(self):
        stored = payloads_of_kind(self.home, "audit_record")[-1]
        self.assertEqual(stored.get("aliases"), ["Widge"])

    def test_guide_uses_run_time_alias_before_any_change(self):
        draft = service.guide(
            home=str(self.home), run_id=self.record["run_id"],
            audit_date=AUDIT_DATE)
        self.assertEqual(draft.get("selection_basis"), "preference")
        self.assertIn("Widge recorded", draft["opening_text"])

    def test_later_alias_change_does_not_enter_draft(self):
        service.set_aliases(
            home=str(self.home), product=PRODUCT, aliases=["Zebras"],
            audit_date=AUDIT_DATE)
        draft = service.guide(
            home=str(self.home), run_id=self.record["run_id"],
            audit_date=AUDIT_DATE)
        self.assertEqual(draft.get("selection_basis"), "preference")
        self.assertIn("Widge recorded", draft["opening_text"])


# ----------------------------------------------------------------,:
# WatchPlan validation in its named values and its duplicate
# identity.
# ----------------------------------------------------------------

class Test073NullSelectors(SeededBase):

    def plan(self, target):
        return {"home": str(self.home), "scope": "picked",
                "targets": [target], "audit_date": AUDIT_DATE}

    def test_null_page_file_refused_at_open(self):
        path = write_plan(self, self.plan(
            {"product": PRODUCT, "page_file": None}))
        before = len(journal_entries(self.home))
        with self.assertRaises(Exception) as caught:
            watch.run_watch(plan_file=str(path))
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")
        self.assertEqual(len(journal_entries(self.home)), before)

    def test_null_round_refused_at_open(self):
        path = write_plan(self, self.plan(
            {"product": PRODUCT, "round": None}))
        with self.assertRaises(Exception) as caught:
            watch.run_watch(plan_file=str(path))
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")

    def test_null_round_beside_page_file_names_one_selector(self):
        path = write_plan(self, self.plan(
            {"product": PRODUCT, "page_file": str(PAGE),
             "round": None}))
        result = watch.run_watch(plan_file=str(path))
        self.assertEqual(result["entries"][0]["outcome"], "completed")


class Test074EvaluatedPathIdentity(SeededBase):

    def plan(self, first, second):
        return {"home": str(self.home), "scope": "picked",
                "audit_date": AUDIT_DATE, "targets": [
                    {"product": PRODUCT, "page_file": str(PAGE),
                     "evaluated_page_path": first},
                    {"product": PRODUCT, "page_file": str(PAGE),
                     "evaluated_page_path": second}]}

    def assert_duplicate(self, first, second):
        path = write_plan(self, self.plan(first, second))
        with self.assertRaises(Exception) as caught:
            watch.run_watch(plan_file=str(path))
        self.assertEqual(
            token_of(caught.exception), "WATCH_DUPLICATE_TARGET")

    def test_doubled_slash_spelling_is_duplicate(self):
        self.assert_duplicate("/p", "//p")

    def test_dot_segment_spelling_is_duplicate(self):
        self.assert_duplicate("/p", "/./p")

    def test_trailing_slash_spelling_is_duplicate(self):
        self.assert_duplicate("/p", "/p/")


class Test079EmptyRobotsIdentity(SeededBase):

    def test_empty_robots_file_is_duplicate_of_absent(self):
        plan = {"home": str(self.home), "scope": "picked",
                "audit_date": AUDIT_DATE, "targets": [
                    {"product": PRODUCT, "page_file": str(PAGE)},
                    {"product": PRODUCT, "page_file": str(PAGE),
                     "robots_file": ""}]}
        path = write_plan(self, plan)
        with self.assertRaises(Exception) as caught:
            watch.run_watch(plan_file=str(path))
        self.assertEqual(
            token_of(caught.exception), "WATCH_DUPLICATE_TARGET")

    def test_empty_robots_file_is_duplicate_of_null(self):
        plan = {"home": str(self.home), "scope": "picked",
                "audit_date": AUDIT_DATE, "targets": [
                    {"product": PRODUCT, "page_file": str(PAGE),
                     "robots_file": ""},
                    {"product": PRODUCT, "page_file": str(PAGE),
                     "robots_file": None}]}
        path = write_plan(self, plan)
        with self.assertRaises(Exception) as caught:
            watch.run_watch(plan_file=str(path))
        self.assertEqual(
            token_of(caught.exception), "WATCH_DUPLICATE_TARGET")


# ----------------------------------------------------------------:
# the install argument shapes.
# ----------------------------------------------------------------

class Test075InstallArgumentShapes(unittest.TestCase):

    def run_main(self, argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            code = install_module.main(argv)
        return code, err.getvalue()

    def test_empty_location_is_malformed(self):
        code, err = self.run_main([""])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)

    def test_empty_home_flag_is_malformed(self):
        code, err = self.run_main(["--home", ""])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)

    def test_empty_location_library_form_is_malformed(self):
        with self.assertRaises(Exception) as caught:
            install_module.install(location="", home="/tmp/x-home")
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")

    def test_double_uninstall_word_is_malformed(self):
        code, err = self.run_main(["uninstall", "uninstall"])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err)


# ----------------------------------------------------------------:
# the audit date validator's type discipline.
# ----------------------------------------------------------------

class Test076AuditDateTypes(SeededBase):

    def test_float_audit_date_refused(self):
        with self.assertRaises(Exception) as caught:
            service.probe_report(
                home=str(self.home), product=PRODUCT, round=ROUND,
                audit_date=20261114.5)
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")

    def test_float_with_zero_fraction_refused(self):
        with self.assertRaises(Exception) as caught:
            service._validate_audit_date(20261114.0)
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")

    def test_integer_audit_date_still_normalised(self):
        self.assertEqual(
            service._validate_audit_date(20261114), "2026-11-14")


# ----------------------------------------------------------------
# and: the output and target path strings judged before any
# filesystem call can raise.
# ----------------------------------------------------------------

class Test077OutputPathGoverned(SeededBase):

    def test_nul_output_fails_in_destination_exists_form(self):
        plan = {"home": str(self.home), "scope": "picked",
                "audit_date": AUDIT_DATE,
                "output": "bad\x00out",
                "targets": [{"product": PRODUCT,
                             "page_file": str(PAGE)}]}
        path = write_plan(self, plan)
        with self.assertRaises(Exception) as caught:
            watch.run_watch(plan_file=str(path))
        self.assertEqual(
            token_of(caught.exception), "DESTINATION_EXISTS")
        self.assertEqual(
            len(entries_of_kind(self.home, "audit_record")), 1)

    def test_surrogate_output_fails_in_destination_exists_form(self):
        raw = json.dumps({
            "home": str(self.home), "scope": "picked",
            "audit_date": AUDIT_DATE, "output": "placeholder",
            "targets": [{"product": PRODUCT,
                         "page_file": str(PAGE)}]})
        raw = raw.replace("placeholder", "\\ud800out")
        path = write_plan(self, None, raw=raw)
        with self.assertRaises(Exception) as caught:
            watch.run_watch(plan_file=str(path))
        self.assertEqual(
            token_of(caught.exception), "DESTINATION_EXISTS")


class Test078TargetPathValidation(SeededBase):

    def plan(self, target):
        return {"home": str(self.home), "scope": "picked",
                "audit_date": AUDIT_DATE, "targets": [target]}

    def test_nul_page_file_refused_at_open(self):
        path = write_plan(self, self.plan(
            {"product": PRODUCT, "page_file": "bad\x00p.md"}))
        before = len(journal_entries(self.home))
        with self.assertRaises(Exception) as caught:
            watch.run_watch(plan_file=str(path))
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")
        self.assertEqual(len(journal_entries(self.home)), before)

    def test_nul_robots_file_refused_at_open(self):
        path = write_plan(self, self.plan(
            {"product": PRODUCT, "page_file": str(PAGE),
             "robots_file": "bad\x00r.txt"}))
        with self.assertRaises(Exception) as caught:
            watch.run_watch(plan_file=str(path))
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")

    def test_surrogate_page_file_refused_at_open(self):
        raw = json.dumps(self.plan(
            {"product": PRODUCT, "page_file": "placeholder"}))
        raw = raw.replace("placeholder", "\\ud800page")
        path = write_plan(self, None, raw=raw)
        with self.assertRaises(Exception) as caught:
            watch.run_watch(plan_file=str(path))
        self.assertEqual(token_of(caught.exception), "MALFORMED_CALL")


# ----------------------------------------------------------------:
# the shell list intake's depth discipline.
# ----------------------------------------------------------------

class Test080ShellListDepth(SeededBase):

    def test_deeply_nested_list_is_a_malformed_call(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            code = shell.main([
                "add-product", "--home", str(self.home),
                "--name", "Other Product",
                "--canonical_line", "Other line.",
                "--domain", "other.example",
                "--aliases", "[" * 10000 + "]" * 10000])
        self.assertEqual(code, 2)
        self.assertIn("MALFORMED_CALL", err.getvalue())


# ----------------------------------------------------------------:
# the type swap field validation at the readers.
# ----------------------------------------------------------------

class Test081TypeSwapReaders(SeededBase):

    def setUp(self):
        super().setUp()
        answer = temp_file(self, "Acme Ledger is a ledger tool.\n")
        do_import(self.home, answer)
        self.record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)

    def assert_validation(self, call, field):
        with self.assertRaises(Exception) as caught:
            call()
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        self.assertIn(field, str(caught.exception))

    def test_answer_query_integer_refused_at_probe_report(self):
        mutate_payload(self.home, "answer_imported", "query", 123)
        self.assert_validation(
            lambda: service.probe_report(
                home=str(self.home), product=PRODUCT, round=ROUND,
                audit_date=AUDIT_DATE), "query")

    def test_answer_captured_on_list_refused_at_probe_report(self):
        mutate_payload(
            self.home, "answer_imported", "captured_on", ["x"])
        self.assert_validation(
            lambda: service.probe_report(
                home=str(self.home), product=PRODUCT, round=ROUND,
                audit_date=AUDIT_DATE), "captured_on")

    def test_answer_capture_method_dict_refused_at_probe_report(self):
        mutate_payload(
            self.home, "answer_imported", "capture_method", {"a": 1})
        self.assert_validation(
            lambda: service.probe_report(
                home=str(self.home), product=PRODUCT, round=ROUND,
                audit_date=AUDIT_DATE), "capture_method")

    def test_answer_engine_label_integer_refused_at_probe_report(self):
        mutate_payload(
            self.home, "answer_imported", "engine_label_normalised",
            123)
        self.assert_validation(
            lambda: service.probe_report(
                home=str(self.home), product=PRODUCT, round=ROUND,
                audit_date=AUDIT_DATE), "engine_label_normalised")

    def test_product_aliases_integer_refused_at_probe_report(self):
        mutate_payload(
            self.home, "product_registered", "aliases", 12345)
        self.assert_validation(
            lambda: service.probe_report(
                home=str(self.home), product=PRODUCT, round=ROUND,
                audit_date=AUDIT_DATE), "aliases")

    def test_product_aliases_dict_refused_at_query_set_report(self):
        mutate_product_field(self.home, "aliases", {"a": 1})
        self.assert_validation(
            lambda: service.query_set_report(
                home=str(self.home), product=PRODUCT,
                audit_date=AUDIT_DATE), "aliases")

    def test_product_competitors_integer_refused_at_probe_report(self):
        mutate_payload(
            self.home, "product_registered", "competitors", 123)
        self.assert_validation(
            lambda: service.probe_report(
                home=str(self.home), product=PRODUCT, round=ROUND,
                audit_date=AUDIT_DATE), "competitors")

    def test_product_query_set_integer_refused_at_worksheet(self):
        mutate_product_field(self.home, "query_set", 123)
        self.assert_validation(
            lambda: service.export_capture_worksheet(
                home=str(self.home), product=PRODUCT, round=ROUND,
                output_path=None, audit_date=AUDIT_DATE), "query_set")

    def test_product_category_integer_refused_at_guide_by_run(self):
        mutate_product_field(self.home, "category", 123)
        self.assert_validation(
            lambda: service.guide(
                home=str(self.home), run_id=self.record["run_id"],
                audit_date=AUDIT_DATE), "category")

    def test_audit_canonical_line_integer_refused_at_guide(self):
        mutate_payload(
            self.home, "audit_record", "canonical_line", 123)
        self.assert_validation(
            lambda: service.guide(
                home=str(self.home), run_id=self.record["run_id"],
                audit_date=AUDIT_DATE), "canonical_line")

    def test_audit_product_name_list_refused_at_guide(self):
        mutate_payload(
            self.home, "audit_record", "product_name", ["x"])
        self.assert_validation(
            lambda: service.guide(
                home=str(self.home), run_id=self.record["run_id"],
                audit_date=AUDIT_DATE), "product_name")

    def test_audit_sentences_wrong_element_refused_at_guide(self):
        mutate_payload(
            self.home, "audit_record", "sentences", [1, 2])
        self.assert_validation(
            lambda: service.guide(
                home=str(self.home), run_id=self.record["run_id"],
                audit_date=AUDIT_DATE), "sentences")

    def test_audit_trigger_codes_integer_refused_at_guide(self):
        mutate_payload(
            self.home, "audit_record", "trigger_codes", 123)
        self.assert_validation(
            lambda: service.guide(
                home=str(self.home), run_id=self.record["run_id"],
                audit_date=AUDIT_DATE), "trigger_codes")

    def test_audit_cited_count_list_refused_at_guide(self):
        mutate_payload(
            self.home, "audit_record",
            "distinct_cited_target_count", ["x"])
        self.assert_validation(
            lambda: service.guide(
                home=str(self.home), run_id=self.record["run_id"],
                audit_date=AUDIT_DATE),
            "distinct_cited_target_count")

    def test_audit_run_id_dict_refused_at_guide(self):
        mutate_payload(
            self.home, "audit_record", "run_id", {"a": 1})
        self.assert_validation(
            lambda: service.guide(
                home=str(self.home), run_id=self.record["run_id"],
                audit_date=AUDIT_DATE), "run_id")

    def test_round_identity_list_refused_at_staleness(self):
        mutate_payload(self.home, "round_named", "round_id", ["x"])
        self.assert_validation(
            lambda: service.staleness_view(home=str(self.home)),
            "round_id")

    def test_product_identity_dict_refused_at_staleness(self):
        mutate_payload(
            self.home, "product_registered", "product_id", {"a": 1})
        self.assert_validation(
            lambda: service.staleness_view(home=str(self.home)),
            "product_id")


# ----------------------------------------------------------------:
# the limits plumbing to acquisition, one reading.
# ----------------------------------------------------------------

class Test085LimitsPlumbing(SeededBase):

    def test_config_page_size_governs_acquisition_reader(self):
        journal.write_config(
            str(self.home), "page_file_size = 10\n")
        page = temp_file(
            self,
            "<html><body><script>" + "a" * (3 * 1024 * 1024) +
            "</script><p>Acme Ledger helps teams.</p></body></html>",
            "big.html")
        record = service.audit(
            home=str(self.home), page_file=str(page),
            audit_date=AUDIT_DATE)
        self.assertIsNotNone(record["run_id"])

    def test_run_raise_of_extracted_text_reaches_extraction(self):
        journal.write_config(
            str(self.home),
            "extracted_text_length_per_page_or_answer = 10\n")
        count = journal.verify_chain(str(self.home))["entry_count"]
        run_id = "run-%d" % (count + 3)
        journal.append_entry(
            str(self.home), "limit_raise",
            {"run_id": run_id, "limit": "limit_3",
             "raised_value": 100000},
            audit_date=AUDIT_DATE)
        page = temp_file(
            self, "A plain page holding about one hundred "
                  "characters of ordinary text for the audit "
                  "to read in full here.\n", "page.txt")
        record = service.audit(
            home=str(self.home), page_file=str(page),
            audit_date=AUDIT_DATE)
        self.assertEqual(record["run_id"], run_id)


# ----------------------------------------------------------------:
# the front matter key count on the parsed text.
# ----------------------------------------------------------------

class Test086FrontMatterBom(SeededBase):

    def page_with_keys(self, bom):
        lines = ["---"]
        lines += ["key%d: value" % i for i in range(101)]
        lines += ["---", "Acme Ledger helps teams track citations."]
        raw = ("\n".join(lines) + "\n").encode("utf-8")
        if bom:
            raw = b"\xef\xbb\xbf" + raw
        return temp_file(self, raw, "page.md")

    def test_plain_form_refused_control(self):
        with self.assertRaises(Exception) as caught:
            service.audit(
                home=str(self.home),
                page_file=str(self.page_with_keys(False)),
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_bom_form_refused_the_same(self):
        with self.assertRaises(Exception) as caught:
            service.audit(
                home=str(self.home),
                page_file=str(self.page_with_keys(True)),
                audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")


# ----------------------------------------------------------------:
# concurrent first imports judged inside the lock.
# ----------------------------------------------------------------

class Test090ConcurrentFirstImports(SeededBase):

    def test_identical_concurrent_first_imports_store_one(self):
        # Deterministic harness: the atomic append is
        # gated so the second caller appends only after
        # the first caller batch has completed, while both
        # callers stand judged against the standing set
        # each read before either appended, the register
        # worked case in its process form. Where the
        # judgement stands inside a lock, the second
        # caller is judged after the first has stored, or
        # stands contended, and never reaches the gate in
        # its unjudged form.
        answer = temp_file(
            self, "Acme Ledger is a ledger tool.\n", "answer.txt")
        arrivals = []
        arrivals_lock = threading.Lock()
        first_done = threading.Event()
        real_append = journal.append_entries_atomic

        def gated_append(*args, **kwargs):
            with arrivals_lock:
                role = len(arrivals)
                arrivals.append(role)
            if role == 0:
                try:
                    return real_append(*args, **kwargs)
                finally:
                    first_done.set()
            first_done.wait(timeout=30)
            return real_append(*args, **kwargs)

        outcomes = []
        lock = threading.Lock()

        def worker():
            try:
                do_import(self.home, answer)
                outcome = "stored"
            except Exception as exc:
                outcome = token_of(exc) or type(exc).__name__
            with lock:
                outcomes.append(outcome)

        with mock.patch.object(
                journal, "append_entries_atomic", gated_append):
            threads = [threading.Thread(target=worker)
                       for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=60)
        self.assertEqual(outcomes.count("stored"), 1)
        self.assertEqual(
            len(entries_of_kind(self.home, "answer_imported")), 1)
        stamps = [
            entry for entry in entries_of_kind(self.home, "round_named")
            if (entry.get("payload") or {}).get(
                "registry_version_at_first_import") is not None]
        self.assertEqual(len(stamps), 1)
        for outcome in outcomes:
            if outcome != "stored":
                self.assertIn(
                    outcome, ("DUPLICATE_IMPORT", "WRITE_CONTENDED"))


# ----------------------------------------------------------------:
# the cadence conversion bounded.
# ----------------------------------------------------------------

class Test093CadenceDigitRun(SeededBase):

    def test_long_digit_run_cadence_returns_summary(self):
        plan = {"home": str(self.home), "scope": "picked",
                "audit_date": AUDIT_DATE,
                "cadence": "every " + "9" * 5000 + " days",
                "targets": [{"product": PRODUCT,
                             "page_file": str(PAGE)}]}
        path = write_plan(self, plan)
        result = watch.run_watch(plan_file=str(path))
        self.assertEqual(result["entries"][0]["outcome"], "completed")
        self.assertEqual(
            result["freshness_view"]["forward_count"],
            {"recorded": False, "state": "not_recorded"})


# ----------------------------------------------------------------:
# failure records surface on operator surfaces.
# ----------------------------------------------------------------

class Test101FailureRecordSurfacing(SeededBase):

    def setUp(self):
        super().setUp()
        answer = temp_file(self, "Acme Ledger is a ledger tool.\n")
        do_import(self.home, answer)
        # Restated in its seed limb only, for the settled rule
        # item the settled rule: one seed failure record now stands
        # created by a failed import, an appending operation
        # whose failure record stands, instead of by a failed
        # probe report, a non appending operation whose cure
        # stopped it appending. The other seed, a failed guide
        # call, stands as before: guide is an appending
        # operation and its failure record stands. Both seed
        # records carry UNKNOWN_ROUND, and the count stands 2.
        with self.assertRaises(Exception):
            do_import(self.home, answer, round="no-such-round")
        with self.assertRaises(Exception):
            service.guide(
                home=str(self.home), run_id="run-999",
                audit_date=AUDIT_DATE)
        self.assertEqual(
            len(entries_of_kind(self.home, "failure_record")), 2)

    def failure_values(self, record):
        payloads = record.get("failure_records") or []
        return [item.get("error_value") for item in payloads]

    def test_status_surfaces_failure_records(self):
        record = service.status(home=str(self.home))
        self.assertIn("UNKNOWN_ROUND", self.failure_values(record))

    def test_verify_surfaces_failure_records(self):
        record = service.verify(home=str(self.home))
        self.assertIn("UNKNOWN_ROUND", self.failure_values(record))

    def test_probe_report_surfaces_failure_records(self):
        # Restated for the settled rule: the
        # probe report record now keeps standing failure
        # record payloads out in full, so two identical probe
        # report calls return identical JSON however many
        # failing calls intervened. The standing seed records
        # stand in the journal, the report call appends
        # nothing, and the report carries no failure_records.
        report = service.probe_report(
            home=str(self.home), product=PRODUCT, round=ROUND,
            form="advanced", audit_date=AUDIT_DATE)
        self.assertNotIn("failure_records", report)
        self.assertEqual(self.failure_values(report), [])
        self.assertEqual(
            len(entries_of_kind(self.home, "failure_record")), 2)

    def test_staleness_view_surfaces_failure_records(self):
        view = service.staleness_view(home=str(self.home))
        self.assertIn("UNKNOWN_ROUND", self.failure_values(view))

    def test_guide_draft_surfaces_failure_records(self):
        draft = service.guide(
            home=str(self.home), product=PRODUCT, round_label=ROUND,
            audit_date=AUDIT_DATE)
        self.assertIn("UNKNOWN_ROUND", self.failure_values(draft))


# ----------------------------------------------------------------:
# the staleness assembly reads corrections.
# ----------------------------------------------------------------

class Test103StalenessCorrections(SeededBase):

    def test_corrected_audit_record_governs_staleness_row(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        stored = entries_of_kind(self.home, "audit_record")[0]
        corrected = dict(stored["payload"])
        corrected["registry_version"] = 99
        journal.append_entry(
            str(self.home), "correction",
            {"supersedes_sequence": stored["sequence"],
             "corrected_record": corrected},
            audit_date=AUDIT_DATE)
        view = service.staleness_view(home=str(self.home))
        rows = [row for row in view["records"]
                if row["record_id"] == record["run_id"]]
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["bound_versions"].get("registry_version"), 99)
        self.assertEqual(rows[0]["state"], "across a break")


# ----------------------------------------------------------------,
# report route backstop limb: limit 41 at the service seam on the
# report routes, on the F5 refusal.
# ----------------------------------------------------------------

class Test052ReportBackstop(SeededBase):

    def setUp(self):
        super().setUp()
        answer = temp_file(self, "Acme Ledger is a ledger tool.\n")
        do_import(self.home, answer)

    def test_probe_report_aborts_at_backstop(self):
        clock = mock.Mock(side_effect=[0.0, 10000.0, 10000.0])
        with mock.patch.object(service, "_clock", clock):
            with self.assertRaises(Exception) as caught:
                service.probe_report(
                    home=str(self.home), product=PRODUCT, round=ROUND,
                    audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_probe_trend_aborts_at_backstop(self):
        service.name_round(
            home=str(self.home), product=PRODUCT, round_label="round-2",
            importer_declaration="all captured",
            supplier_relation="independent party",
            audit_date=AUDIT_DATE)
        clock = mock.Mock(side_effect=[0.0, 10000.0, 10000.0])
        with mock.patch.object(service, "_clock", clock):
            with self.assertRaises(Exception) as caught:
                service.probe_trend(
                    home=str(self.home), product=PRODUCT,
                    round_a=ROUND, round_b="round-2",
                    audit_date=AUDIT_DATE)
        self.assertEqual(token_of(caught.exception), "LIMIT_EXCEEDED")


if __name__ == "__main__":
    unittest.main()
