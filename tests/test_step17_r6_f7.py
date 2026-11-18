"""Service, watch, seams.

Pins the settled rules
Every test was written before its cure and run failing for
the register stated reason, except the controls named as
controls. Oracle: the round 6 findings register and
disposition."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from citeline import errors, install as install_module
from citeline import guide as guide_module
from citeline import journal, service, watch

FIXTURES = Path(__file__).parent / "fixtures"
PAGE = FIXTURES / "w7-page.md"
AUDIT_DATE = "2026-11-14"
PRODUCT = "Acme Ledger"
Q1 = "What is Acme Ledger?"
Q2 = "Best ferry tracker?"
ROUND = "round-1"
ROUND0 = "round-0"


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


def correct_entry(home, entry, **changes):
    corrected = dict(entry.get("payload") or {})
    corrected.update(changes)
    journal.append_entry(
        str(home), "correction",
        {"supersedes_sequence": entry["sequence"],
         "corrected_record": corrected},
        audit_date=AUDIT_DATE)
    return corrected


class SeededBase(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)
        seed(self, self.home)

    def import_one(self):
        answer = temp_file(
            self, "Acme Ledger is a ledger tool.\n", "answer.txt")
        return do_import(self.home, answer)


# ----------------------------------------------------------------:
# the round stamp fields stand judged at the probe report artefact
# stamp positions.
# ----------------------------------------------------------------

class Test042RoundStampsJudged(SeededBase):

    def setUp(self):
        super().setUp()
        self.import_one()
        self.round_entry = entries_of_kind(
            self.home, "round_named")[-1]

    def report(self):
        return service.probe_report(
            home=str(self.home), product=PRODUCT, round=ROUND,
            audit_date=AUDIT_DATE)

    def test_swapped_declaration_types_refuse(self):
        for bad in (123, ["x"], {"p": 1}, True):
            with self.subTest(bad=repr(bad)):
                root, home = make_home(self)
                seed(self, home)
                answer = temp_file(
                    self, "Acme Ledger is a ledger tool.\n",
                    "answer.txt")
                do_import(home, answer)
                entry = entries_of_kind(home, "round_named")[-1]
                correct_entry(home, entry, importer_declaration=bad)
                with self.assertRaises(
                        errors.CitelineError) as caught:
                    service.probe_report(
                        home=str(home), product=PRODUCT, round=ROUND,
                        audit_date=AUDIT_DATE)
                self.assertEqual(
                    token_of(caught.exception), "VALIDATION_FAILED")
                self.assertIn(
                    "importer_declaration", str(caught.exception))

    def test_out_of_set_declaration_string_refuses(self):
        correct_entry(
            self.home, self.round_entry,
            importer_declaration="bogus_text")
        with self.assertRaises(errors.CitelineError) as caught:
            self.report()
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        self.assertIn("importer_declaration", str(caught.exception))

    def test_swapped_version_stamps_refuse(self):
        for field in ("registry_version_at_first_import",
                      "detector_version_at_first_import"):
            for bad in (["x"], {"p": 1}, True, "two"):
                with self.subTest(field=field, bad=repr(bad)):
                    root, home = make_home(self)
                    seed(self, home)
                    answer = temp_file(
                        self, "Acme Ledger is a ledger tool.\n",
                        "answer.txt")
                    do_import(home, answer)
                    entry = entries_of_kind(
                        home, "round_named")[-1]
                    correct_entry(home, entry, **{field: bad})
                    with self.assertRaises(
                            errors.CitelineError) as caught:
                        service.probe_report(
                            home=str(home), product=PRODUCT,
                            round=ROUND, audit_date=AUDIT_DATE)
                    self.assertEqual(
                        token_of(caught.exception),
                        "VALIDATION_FAILED")
                    self.assertIn(field, str(caught.exception))

    def test_genuine_stamps_still_surface_control(self):
        report = self.report()
        standing = payloads_of_kind(self.home, "round_named")[-1]
        self.assertEqual(
            report["registry_version_at_first_import"],
            standing["registry_version_at_first_import"])
        self.assertIsInstance(
            report["registry_version_at_first_import"], int)
        self.assertIsInstance(
            report["detector_version_at_first_import"], int)
        frame = report.get("sampling_frame") or {}
        self.assertEqual(
            frame.get("importer_declaration"), "all_captured")


# ----------------------------------------------------------------:
# an empty string supplied_path stands read as one value, no path,
# at every seam.
# ----------------------------------------------------------------

class Test043EmptySuppliedPathOneReading(SeededBase):

    def plant_snapshot(self, supplied_path):
        product_id = payloads_of_kind(
            self.home, "product_registered")[0]["product_id"]
        journal.append_entry(
            str(self.home), "snapshot_registered",
            {"snapshot_id": "snap-planted",
             "product_id": product_id, "is_product_page": True,
             "supplied_path": supplied_path},
            audit_date=AUDIT_DATE)

    def test_empty_path_reads_as_no_path_at_grounds_and_count(self):
        self.plant_snapshot("")
        grounds = service.estate_grounds(
            home=str(self.home), product=PRODUCT)
        self.assertIsNone(grounds["page_path"])
        products = service.list_products(home=str(self.home))
        count, paths = watch._standing_product_page_snapshot_count(
            str(self.home), products)
        self.assertEqual(count, 0)
        self.assertEqual(paths, set())

    def test_empty_path_skips_at_the_estate_dispatch(self):
        self.import_one()
        self.plant_snapshot("")
        plan = {"home": str(self.home), "scope": "estate",
                "audit_date": AUDIT_DATE}
        plan_file = temp_file(
            self, json.dumps(plan), "plan.json")
        result = watch.run_watch(plan_file=str(plan_file))
        audit_entries = [
            entry for entry in result["entries"]
            if entry["target_kind"] == "audit"]
        self.assertEqual(len(audit_entries), 1)
        self.assertEqual(audit_entries[0]["outcome"], "skipped")

    def test_real_path_still_reads_control(self):
        self.plant_snapshot(str(PAGE))
        grounds = service.estate_grounds(
            home=str(self.home), product=PRODUCT)
        self.assertEqual(grounds["page_path"], str(PAGE))
        products = service.list_products(home=str(self.home))
        count, paths = watch._standing_product_page_snapshot_count(
            str(self.home), products)
        self.assertEqual(count, 1)
        self.assertEqual(paths, {os.path.realpath(str(PAGE))})


# ----------------------------------------------------------------:
# the guide store stands judged at the store on both selectors the
# guide route states.
# ----------------------------------------------------------------

class Test044GuideStoreBothSelectors(SeededBase):

    def setUp(self):
        super().setUp()
        self.import_one()

    def bound_registry_entry(self):
        changes = entries_of_kind(self.home, "registry_change")
        if changes:
            return changes[-1]
        return entries_of_kind(self.home, "product_registered")[-1]

    def test_correction_at_the_append_gate_never_lands(self):
        entry = self.bound_registry_entry()
        real_append = journal.append_entry
        state = {"plant_failed": False}

        def wrapper(home, kind, payload, audit_date=None,
                    run_id=None):
            if kind == "guide_record":
                corrected = dict(entry.get("payload") or {})
                corrected["canonical_line"] = (
                    "Corrected canonical line for Acme Ledger.")
                try:
                    real_append(
                        home, "correction",
                        {"supersedes_sequence": entry["sequence"],
                         "corrected_record": corrected},
                        audit_date=AUDIT_DATE)
                except Exception:
                    state["plant_failed"] = True
            return real_append(
                home, kind, payload, audit_date=audit_date,
                run_id=run_id)

        with mock.patch.object(journal, "append_entry", wrapper):
            service.guide(
                home=str(self.home), product=PRODUCT,
                round_label=ROUND, audit_date=AUDIT_DATE)
        self.assertTrue(state["plant_failed"])
        self.assertEqual(
            entries_of_kind(self.home, "correction"), [])
        guides = payloads_of_kind(self.home, "guide_record")
        self.assertEqual(len(guides), 1)
        self.assertIn(
            "Acme Ledger helps teams track citations.",
            str(guides[-1].get("opening_text") or ""))

    def test_correction_during_the_build_refuses_at_the_store(self):
        entry = self.bound_registry_entry()
        real_draft = guide_module.draft_from_round
        landed = {"done": False}

        def wrapper(round_record, **kwargs):
            draft = real_draft(round_record, **kwargs)
            if not landed["done"]:
                landed["done"] = True
                corrected = dict(entry.get("payload") or {})
                corrected["canonical_line"] = (
                    "Corrected canonical line for Acme Ledger.")
                journal.append_entry(
                    str(self.home), "correction",
                    {"supersedes_sequence": entry["sequence"],
                     "corrected_record": corrected},
                    audit_date=AUDIT_DATE)
            return draft

        with mock.patch.object(
                guide_module, "draft_from_round", wrapper):
            with self.assertRaises(errors.CitelineError) as caught:
                service.guide(
                    home=str(self.home), product=PRODUCT,
                    round_label=ROUND, audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        self.assertEqual(
            payloads_of_kind(self.home, "guide_record"), [])

    def test_plain_product_round_guide_still_stores_control(self):
        result = service.guide(
            home=str(self.home), product=PRODUCT,
            round_label=ROUND, audit_date=AUDIT_DATE)
        self.assertIsNotNone(result.get("guide_id"))
        guides = payloads_of_kind(self.home, "guide_record")
        self.assertEqual(len(guides), 1)
        self.assertIn(
            "Acme Ledger helps teams track citations.",
            str(guides[-1].get("opening_text") or ""))


# ----------------------------------------------------------------:
# the plan second_rounds record keys stand judged under the plan
# shape discipline.
# ----------------------------------------------------------------

class Test045SecondRoundsKeysJudged(SeededBase):

    def test_non_string_record_key_refuses_at_open(self):
        plan = {"home": str(self.home), "scope": "picked",
                "targets": [{"product": PRODUCT, "round": ROUND}],
                "second_rounds": {123: ROUND0},
                "audit_date": AUDIT_DATE}
        with self.assertRaises(errors.CitelineError) as caught:
            watch._validate_plan(plan)
        self.assertEqual(
            token_of(caught.exception), "MALFORMED_CALL")

    def two_round_home(self):
        root, home = make_home(self)
        service.add_product(
            home=str(home), name=PRODUCT,
            canonical_line="Acme Ledger helps teams track citations.",
            domain="acme.example", audit_date=AUDIT_DATE)
        service.set_query_set(
            home=str(home), product=PRODUCT, query_set=[Q1, Q2],
            audit_date=AUDIT_DATE)
        service.name_round(
            home=str(home), product=PRODUCT, round_label=ROUND0,
            importer_declaration="all captured",
            supplier_relation="independent party",
            audit_date=AUDIT_DATE)
        answer = temp_file(
            self, "Acme Ledger is a ledger tool.\n", "answer.txt")
        do_import(home, answer, round=ROUND0)
        service.name_round(
            home=str(home), product=PRODUCT, round_label=ROUND,
            importer_declaration="all captured",
            supplier_relation="independent party",
            audit_date=AUDIT_DATE)
        answer = temp_file(
            self, "Acme Ledger is a ledger tool.\n", "answer.txt")
        do_import(home, answer, round=ROUND)
        return home

    def run_plan(self, home, second_rounds):
        plan = {"home": str(home), "scope": "picked",
                "targets": [{"product": PRODUCT, "round": ROUND}],
                "second_rounds": second_rounds,
                "audit_date": AUDIT_DATE}
        plan_file = temp_file(
            self, json.dumps(plan), "plan.json")
        return watch.run_watch(plan_file=str(plan_file))

    def test_key_naming_no_product_stands_warned_in_the_open(self):
        home = self.two_round_home()
        result = self.run_plan(home, {"No Such Product": ROUND0})
        warnings = result.get("plan_warnings") or []
        self.assertTrue(
            any("No Such Product" in warning
                for warning in warnings),
            "no warning names the disregarded key: %r" % (warnings,))
        probe = [entry for entry in result["entries"]
                 if entry["target_kind"] == "probe"][0]
        self.assertIsNone(probe.get("trend_pair"))

    def test_key_naming_the_product_still_pairs_control(self):
        home = self.two_round_home()
        result = self.run_plan(home, {PRODUCT: ROUND0})
        probe = [entry for entry in result["entries"]
                 if entry["target_kind"] == "probe"][0]
        self.assertEqual(probe.get("trend_pair"), [ROUND0, ROUND])
        warnings = result.get("plan_warnings") or []
        self.assertFalse(
            any(PRODUCT in warning for warning in warnings))


# ----------------------------------------------------------------:
# both service key counters stand on the one block reading the
# parser reads.
# ----------------------------------------------------------------

FLOW_BLOCK = (
    '{"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "a": 6}')


class Test046FlowDuplicateCountedAsItStands(SeededBase):

    def page_with_block(self, block):
        return temp_file(
            self, "---\n" + block + "\n---\n"
            "Acme Ledger helps teams track citations.\n",
            "page.md")

    def test_audit_counter_counts_every_occurrence(self):
        page = self.page_with_block(FLOW_BLOCK)
        self.assertEqual(service._front_matter_key_count(page), 6)
        distinct = self.page_with_block(
            '{"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}')
        self.assertEqual(
            service._front_matter_key_count(distinct), 5)

    def test_audit_refuses_the_block_over_the_stated_limit(self):
        journal.write_config(
            str(self.home), "front_matter_key_count = 5\n")
        page = self.page_with_block(FLOW_BLOCK)
        with self.assertRaises(errors.CitelineError) as caught:
            service.audit(
                home=str(self.home), page_file=str(page),
                audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_import_seam_counts_every_occurrence(self):
        journal.write_config(
            str(self.home), "front_matter_key_count = 5\n")
        answer = self.page_with_block(FLOW_BLOCK)
        with self.assertRaises(errors.CitelineError) as caught:
            service._import_front_matter_limits(
                str(self.home), str(answer))
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")


# ----------------------------------------------------------------:
# the error vocabulary helpers and the CitelineError constructor
# stand guarded against a string subclass whose equality raises.
# ----------------------------------------------------------------

class EqStr(str):
    __hash__ = str.__hash__

    def __eq__(self, other):
        raise RuntimeError("equality stands unavailable")


class Test047EqualityRaisingStringGuarded(unittest.TestCase):

    def test_helpers_return_none_on_the_equality_form(self):
        self.assertIsNone(
            errors.error_for_token(EqStr("VALIDATION_FAILED")))
        self.assertIsNone(errors.error_for_row(EqStr("X-5")))

    def test_constructor_refuses_it_as_a_value_error(self):
        with self.assertRaises(ValueError):
            errors.CitelineError(
                "boom", token=EqStr("VALIDATION_FAILED"))
        with self.assertRaises(ValueError):
            errors.CitelineError("boom", row=EqStr("X-5"))

    def test_plain_lookups_still_resolve_control(self):
        self.assertEqual(
            errors.error_for_token("VALIDATION_FAILED")["row"],
            "X-5")
        self.assertEqual(
            errors.error_for_row("X-5")["token"],
            "VALIDATION_FAILED")
        err = errors.CitelineError("boom", token="VALIDATION_FAILED")
        self.assertEqual(err.row, "X-5")


# ----------------------------------------------------------------:
# the watch coverage count judges the product identity before it
# tests membership.
# ----------------------------------------------------------------

class Test049CoverageCountJudgesProductIdentity(SeededBase):

    def plant_snapshot(self, product_id):
        journal.append_entry(
            str(self.home), "snapshot_registered",
            {"snapshot_id": "snap-planted",
             "product_id": product_id, "is_product_page": True,
             "supplied_path": str(PAGE)},
            audit_date=AUDIT_DATE)

    def test_unhashable_product_identity_refuses_in_vocabulary(self):
        for bad in (["x"], {"p": 1}):
            with self.subTest(bad=repr(bad)):
                root, home = make_home(self)
                seed(self, home)
                product_id = payloads_of_kind(
                    home, "product_registered")[0]["product_id"]
                journal.append_entry(
                    str(home), "snapshot_registered",
                    {"snapshot_id": "snap-planted",
                     "product_id": bad, "is_product_page": True,
                     "supplied_path": str(PAGE)},
                    audit_date=AUDIT_DATE)
                products = service.list_products(home=str(home))
                with self.assertRaises(
                        errors.CitelineError) as caught:
                    watch._standing_product_page_snapshot_count(
                        str(home), products)
                self.assertEqual(
                    token_of(caught.exception), "VALIDATION_FAILED")
                self.assertIn("product_id", str(caught.exception))

    def test_genuine_product_identity_still_counts_control(self):
        product_id = payloads_of_kind(
            self.home, "product_registered")[0]["product_id"]
        self.plant_snapshot(product_id)
        products = service.list_products(home=str(self.home))
        count, paths = watch._standing_product_page_snapshot_count(
            str(self.home), products)
        self.assertEqual(count, 1)


# ----------------------------------------------------------------:
# the service round fold judges the stored round identity before
# it keys its dict.
# ----------------------------------------------------------------

class Test050RoundFoldJudgesRoundIdentity(SeededBase):

    def test_swapped_round_identity_refuses_in_vocabulary(self):
        self.import_one()
        entry = entries_of_kind(self.home, "round_named")[-1]
        correct_entry(self.home, entry, round_id={"x": 1})
        product_record = service.list_products(
            home=str(self.home))[0]
        with self.assertRaises(errors.CitelineError) as caught:
            service._round_record(
                self.home, product_record, ROUND)
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        self.assertIn("round_id", str(caught.exception))
        with self.assertRaises(errors.CitelineError) as caught:
            service.probe_report(
                home=str(self.home), product=PRODUCT, round=ROUND,
                audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")

    def test_genuine_round_identity_still_resolves_control(self):
        self.import_one()
        product_record = service.list_products(
            home=str(self.home))[0]
        record = service._round_record(
            self.home, product_record, ROUND)
        self.assertIsNotNone(record)
        self.assertEqual(record.get("round_label"), ROUND)


# ----------------------------------------------------------------
# and: the deferred recovery signal and its readers.
# ----------------------------------------------------------------

class DeferredBase(SeededBase):

    def make_deferred(self):
        path = Path(self.home) / "journal.jsonl"
        size = path.stat().st_size
        for name in ("Ghost One", "Ghost Two"):
            journal.append_entry(
                str(self.home), "product_registered",
                {"product_id": "p-" + name.split()[1].lower(),
                 "name": name,
                 "canonical_line": name + " line.",
                 "domain": "ghost.example"},
                audit_date=AUDIT_DATE)
        written = journal._write_batch_intent(
            str(self.home), size, None, None, 2)
        self.assertTrue(written)
        journal.write_config(
            str(self.home), "journal_length = 3\n")
        self.seed_size = size


class Test052SignalJudgesTheDeferral(DeferredBase):

    def test_deferred_home_still_refuses_control(self):
        self.make_deferred()
        with self.assertRaises(errors.CitelineError) as caught:
            service.status(home=str(self.home))
        self.assertEqual(
            token_of(caught.exception), "JOURNAL_CAP_EXCEEDED")

    def test_record_landing_after_the_attempt_does_not_fire(self):
        path = Path(self.home) / "journal.jsonl"
        size = path.stat().st_size
        for name in ("Ghost One", "Ghost Two"):
            journal.append_entry(
                str(self.home), "product_registered",
                {"product_id": "p-" + name.split()[1].lower(),
                 "name": name,
                 "canonical_line": name + " line.",
                 "domain": "ghost.example"},
                audit_date=AUDIT_DATE)
        real_recover = journal.recover_interrupted_batch
        state = {"planted": False}

        def wrapper(home):
            result = real_recover(home)
            if not state["planted"]:
                state["planted"] = True
                journal._write_batch_intent(
                    str(home), size, None, None, 2)
            return result

        with mock.patch.object(
                journal, "recover_interrupted_batch", wrapper):
            result = service.status(home=str(self.home))
        self.assertEqual(result["entry_count"], 5)
        intent = Path(journal._batch_intent_path(str(self.home)))
        self.assertTrue(intent.exists())

    def test_recovery_landing_inside_the_validation_does_not_fire(self):
        self.make_deferred()
        real_validate = journal._validate_batch_intent
        state = {"calls": 0, "inner": False}

        def guarded(home, record):
            if state["inner"]:
                return real_validate(home, record)
            state["calls"] += 1
            if state["calls"] == 2:
                journal.write_config(
                    str(home), "journal_length = 10\n")
                state["inner"] = True
                try:
                    journal.recover_interrupted_batch(str(home))
                finally:
                    state["inner"] = False
            return real_validate(home, record)

        with mock.patch.object(
                journal, "_validate_batch_intent", guarded):
            result = service.status(home=str(self.home))
        self.assertEqual(result["entry_count"], 4)
        intent = Path(journal._batch_intent_path(str(self.home)))
        self.assertFalse(intent.exists())


class Test053SignalReaderDescriptorDiscipline(DeferredBase):

    def test_fifo_swapped_into_the_window_does_not_wedge(self):
        self.make_deferred()
        intent = journal._batch_intent_path(str(self.home))
        child = (
            "import os, sys\n"
            "sys.path.insert(0, %r)\n"
            "from unittest import mock\n"
            "from citeline import journal, service\n"
            "home = %r\n"
            "intent = %r\n"
            "real_probe = journal._lock_held_by_other\n"
            "state = {'swapped': False}\n"
            "def probe(home_arg):\n"
            "    if not state['swapped']:\n"
            "        state['swapped'] = True\n"
            "        os.unlink(intent)\n"
            "        os.mkfifo(intent)\n"
            "    return real_probe(home_arg)\n"
            "with mock.patch.object(\n"
            "        journal, '_lock_held_by_other', probe):\n"
            "    try:\n"
            "        result = service.status(home=home)\n"
            "        print('completed', result.get('entry_count'))\n"
            "    except Exception as exc:\n"
            "        print('refused', getattr(exc, 'token', None))\n"
            % (os.path.join(
                os.path.dirname(os.path.abspath(__file__)), ".."),
               str(self.home), intent))
        try:
            result = subprocess.run(
                [sys.executable, "-c", child],
                capture_output=True, text=True, timeout=30)
        except subprocess.TimeoutExpired:
            self.fail(
                "the status call wedged in the signal open on "
                "a FIFO swapped into the intent path")
        self.assertIn(
            result.stdout.strip().split(" ")[0],
            ("completed", "refused"),
            "child produced no result: %r %r"
            % (result.stdout, result.stderr))


# ----------------------------------------------------------------:
# the audit form request reader stands validated as it scans.
# ----------------------------------------------------------------

class Test055FormRequestValidatedAsItScans(SeededBase):

    def audit_one(self):
        return service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)

    def test_swapped_own_run_identity_refuses_in_vocabulary(self):
        record = self.audit_one()
        entry = entries_of_kind(self.home, "audit_record")[-1]
        correct_entry(self.home, entry, run_id=123)
        with self.assertRaises(errors.CitelineError) as caught:
            service.audit(
                home=str(self.home), run_id=record["run_id"])
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        self.assertIn("run_id", str(caught.exception))

    def test_swapped_sibling_run_identity_refuses_in_vocabulary(self):
        first = self.audit_one()
        second = self.audit_one()
        self.assertNotEqual(first["run_id"], second["run_id"])
        entry = entries_of_kind(self.home, "audit_record")[0]
        correct_entry(self.home, entry, run_id=123)
        with self.assertRaises(errors.CitelineError) as caught:
            service.audit(
                home=str(self.home), run_id=second["run_id"])
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        self.assertIn("run_id", str(caught.exception))

    def test_unswapped_form_request_still_returns_control(self):
        record = self.audit_one()
        standing = service.audit(
            home=str(self.home), run_id=record["run_id"])
        self.assertEqual(standing["run_id"], record["run_id"])


if __name__ == "__main__":
    unittest.main()
