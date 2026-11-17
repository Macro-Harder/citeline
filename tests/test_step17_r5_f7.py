"""Service, watch, seams.

Pins the register entries charged to F7 in fix round 5: and.
Every test was written before its cure and run failing for
the register stated reason, except the controls named as
controls. Oracle: the round 5 findings register and
disposition."""

import json
import os
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


def gated_batch(case, shift_config=None):
    """A batch gate planting a genuine intent record, in the
    form of the round 4 seat test for."""
    real_batch = journal.append_entries_atomic

    def gated(home, entries, audit_date=None, run_id=None):
        path = Path(home) / "journal.jsonl"
        size = path.stat().st_size
        journal._write_batch_intent(home, size, None, None, 1)
        result = real_batch(
            home, entries, audit_date=audit_date, run_id=run_id)
        if shift_config is not None:
            journal.write_config(home, shift_config)
        return result

    return gated


class SeededBase(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)
        seed(self, self.home)

    def import_one(self):
        answer = temp_file(
            self, "Acme Ledger is a ledger tool.\n", "answer.txt")
        return do_import(self.home, answer)


# ----------------------------------------------------------------:
# the assembly correction stands landed or the audit stands
# refused, never a success over a correction that never landed.
# ----------------------------------------------------------------

class Test050CorrectionLandedOrRefused(SeededBase):

    def test_correction_at_the_cap_refuses_the_audit(self):
        journal.write_config(
            str(self.home), "journal_length = 6\n")
        with mock.patch.object(
                journal, "append_entries_atomic",
                gated_batch(self)):
            with self.assertRaises(errors.CitelineError) as caught:
                service.audit(
                    home=str(self.home), page_file=str(PAGE),
                    audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "JOURNAL_CAP_EXCEEDED")
        self.assertEqual(
            len(entries_of_kind(self.home, "correction")), 0)

    def test_unlanded_correction_heals_at_the_form_request(self):
        journal.write_config(
            str(self.home), "journal_length = 6\n")
        with mock.patch.object(
                journal, "append_entries_atomic",
                gated_batch(self)):
            with self.assertRaises(errors.CitelineError):
                service.audit(
                    home=str(self.home), page_file=str(PAGE),
                    audit_date=AUDIT_DATE)
        journal.write_config(
            str(self.home), "journal_length = 10\n")
        standing = service.audit(
            home=str(self.home), run_id="run-6")
        snapshots = payloads_of_kind(
            self.home, "snapshot_registered")
        self.assertEqual(
            standing["snapshot_id"], snapshots[-1]["snapshot_id"])
        self.assertEqual(
            standing["limits_in_force"]["run_id"], "run-6")
        self.assertEqual(
            len(entries_of_kind(self.home, "correction")), 1)
        again = service.audit(
            home=str(self.home), run_id="run-6")
        self.assertEqual(again["snapshot_id"],
                         snapshots[-1]["snapshot_id"])

    def test_ordinary_gated_audit_still_lands_control(self):
        with mock.patch.object(
                journal, "append_entries_atomic",
                gated_batch(self)):
            record = service.audit(
                home=str(self.home), page_file=str(PAGE),
                audit_date=AUDIT_DATE)
        snapshots = payloads_of_kind(
            self.home, "snapshot_registered")
        self.assertEqual(record["snapshot_id"],
                         snapshots[-1]["snapshot_id"])
        self.assertEqual(
            len(entries_of_kind(self.home, "correction")), 1)


# ----------------------------------------------------------------:
# an intent record planted inside the assembly hold stands judged
# before the assembly entries stand reported settled.
# ----------------------------------------------------------------

class Test051IntentPlantedInsideHold(SeededBase):

    def plant_at_correction(self, count):
        real_append = journal.append_entry
        state = {"planted": False}
        home = self.home

        def wrapper(home_arg, kind, payload, audit_date=None,
                    run_id=None):
            if kind == "correction" and not state["planted"]:
                state["planted"] = True
                path = Path(home) / "journal.jsonl"
                lines = path.read_bytes().splitlines(
                    keepends=True)
                size = sum(len(line) for line in lines[:4])
                journal._write_batch_intent(
                    str(home), size, None, None, count)
            return real_append(
                home_arg, kind, payload, audit_date=audit_date,
                run_id=run_id)

        return wrapper

    def test_valid_planted_intent_rolls_the_assembly_back(self):
        with mock.patch.object(
                journal, "append_entries_atomic",
                gated_batch(self)):
            with mock.patch.object(
                    journal, "append_entry",
                    self.plant_at_correction(3)):
                with self.assertRaises(
                        errors.CitelineError) as caught:
                    service.audit(
                        home=str(self.home), page_file=str(PAGE),
                        audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "JOURNAL_VERIFY_FAILED")
        intent = Path(journal._batch_intent_path(str(self.home)))
        self.assertFalse(intent.exists())
        self.assertEqual(
            entries_of_kind(self.home, "snapshot_registered"), [])
        self.assertEqual(
            entries_of_kind(self.home, "audit_record"), [])
        with self.assertRaises(errors.CitelineError) as caught:
            service.audit(home=str(self.home), run_id="run-6")
        self.assertEqual(
            token_of(caught.exception), "UNKNOWN_ROUND")

    def test_invalid_planted_intent_leaves_the_record_control(self):
        with mock.patch.object(
                journal, "append_entries_atomic",
                gated_batch(self)):
            with mock.patch.object(
                    journal, "append_entry",
                    self.plant_at_correction(2)):
                record = service.audit(
                    home=str(self.home), page_file=str(PAGE),
                    audit_date=AUDIT_DATE)
        snapshots = payloads_of_kind(
            self.home, "snapshot_registered")
        self.assertEqual(record["snapshot_id"],
                         snapshots[-1]["snapshot_id"])
        self.assertEqual(
            len(entries_of_kind(self.home, "correction")), 1)


# ----------------------------------------------------------------:
# the stored snapshot field supplied_path stands judged at the
# readers that consume it.
# ----------------------------------------------------------------

class Test052SuppliedPathJudged(unittest.TestCase):

    def planted_home(self, supplied_path):
        root, home = make_home(self)
        seed(self, home)
        answer = temp_file(
            self, "Acme Ledger is a ledger tool.\n", "answer.txt")
        do_import(home, answer)
        product_id = payloads_of_kind(
            home, "product_registered")[0]["product_id"]
        journal.append_entry(
            str(home), "snapshot_registered",
            {"snapshot_id": "snap-planted",
             "product_id": product_id, "is_product_page": True,
             "supplied_path": supplied_path},
            audit_date=AUDIT_DATE)
        return home

    def test_swapped_supplied_path_refused_at_both_readers(self):
        for bad in (123, ["x"], {"p": 1}, True):
            with self.subTest(bad=repr(bad)):
                home = self.planted_home(bad)
                with self.assertRaises(
                        errors.CitelineError) as caught:
                    service.estate_grounds(
                        home=str(home), product=PRODUCT)
                self.assertEqual(
                    token_of(caught.exception), "VALIDATION_FAILED")
                self.assertIn(
                    "supplied_path", str(caught.exception))
                products = service.list_products(home=str(home))
                with self.assertRaises(
                        errors.CitelineError) as caught:
                    watch._standing_product_page_snapshot_count(
                        str(home), products)
                self.assertEqual(
                    token_of(caught.exception), "VALIDATION_FAILED")
                self.assertIn(
                    "supplied_path", str(caught.exception))

    def test_string_supplied_path_still_reads_control(self):
        home = self.planted_home(str(PAGE))
        grounds = service.estate_grounds(
            home=str(home), product=PRODUCT)
        self.assertEqual(grounds["page_path"], str(PAGE))
        products = service.list_products(home=str(home))
        count, paths = watch._standing_product_page_snapshot_count(
            str(home), products)
        self.assertEqual(count, 1)
        self.assertEqual(
            paths, {os.path.realpath(str(PAGE))})


# ----------------------------------------------------------------:
# the audit form request reader stands under the stored audit
# field discipline its sibling reader enforces.
# ----------------------------------------------------------------

class Test053FormRequestJudged(SeededBase):

    def test_each_swapped_field_refused_at_the_form_request(self):
        swaps = (
            ("sentences", "not-a-list"),
            ("sentences", [1, 2]),
            ("trigger_codes", "FAIL_X"),
            ("canonical_line", 42),
            ("distinct_cited_target_count", "three"),
        )
        for field, bad in swaps:
            with self.subTest(field=field, bad=repr(bad)):
                root, home = make_home(self)
                seed(self, home)
                record = service.audit(
                    home=str(home), page_file=str(PAGE),
                    audit_date=AUDIT_DATE)
                audit_entry = entries_of_kind(
                    home, "audit_record")[-1]
                corrected = dict(audit_entry.get("payload") or {})
                corrected[field] = bad
                journal.append_entry(
                    str(home), "correction",
                    {"supersedes_sequence": audit_entry["sequence"],
                     "corrected_record": corrected},
                    audit_date=AUDIT_DATE)
                with self.assertRaises(
                        errors.CitelineError) as caught:
                    service.audit(
                        home=str(home), run_id=record["run_id"])
                self.assertEqual(
                    token_of(caught.exception), "VALIDATION_FAILED")
                self.assertIn(field, str(caught.exception))

    def test_unswapped_form_request_still_returns_control(self):
        record = service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)
        standing = service.audit(
            home=str(self.home), run_id=record["run_id"])
        self.assertEqual(standing["run_id"], record["run_id"])
        self.assertEqual(
            standing["snapshot_id"], record["snapshot_id"])


# ----------------------------------------------------------------:
# the picked target identity and dispatch stand judged on the
# selector values, an empty page file beside a named round
# standing as no page selector on every seam.
# ----------------------------------------------------------------

class Test054EmptyPageFileBesideRound(SeededBase):

    def plan_file(self, target):
        plan = {"home": str(self.home), "scope": "picked",
                "targets": [target], "audit_date": AUDIT_DATE}
        return temp_file(
            self, json.dumps(plan), "plan.json")

    def test_identity_reads_the_empty_page_file_as_no_selector(self):
        target = {"product": PRODUCT, "page_file": "",
                  "round": ROUND}
        accepted = watch._validate_plan(
            {"home": str(self.home), "scope": "picked",
             "targets": [target]})
        self.assertEqual(len(accepted), 1)
        self.assertEqual(
            watch._target_identity(target),
            ("probe", PRODUCT, ROUND))

    def test_run_watch_dispatches_the_target_as_a_probe(self):
        self.import_one()
        plan = self.plan_file(
            {"product": PRODUCT, "page_file": "", "round": ROUND})
        result = watch.run_watch(plan_file=str(plan))
        self.assertEqual(len(result["entries"]), 1)
        entry = result["entries"][0]
        self.assertEqual(entry["target_kind"], "probe")
        self.assertEqual(entry["outcome"], "completed")

    def test_named_page_file_beside_empty_round_control(self):
        plan = self.plan_file(
            {"product": PRODUCT, "page_file": str(PAGE),
             "round": ""})
        result = watch.run_watch(plan_file=str(plan))
        self.assertEqual(len(result["entries"]), 1)
        entry = result["entries"][0]
        self.assertEqual(entry["target_kind"], "audit")
        self.assertEqual(entry["outcome"], "completed")


# ----------------------------------------------------------------:
# the cadence separator stands as the one ordinary space the
# stated form writes.
# ----------------------------------------------------------------

class Test055CadenceOneSpace(unittest.TestCase):

    def test_a_run_of_spaces_reads_no_interval(self):
        self.assertIsNone(
            watch._cadence_interval_days("every  2  days"))
        self.assertIsNone(
            watch._cadence_interval_days("every  2 days"))
        self.assertIsNone(
            watch._cadence_interval_days("every 2  days"))
        self.assertIsNone(
            watch._cadence_interval_days("every  2  months"))

    def test_the_stated_single_space_form_still_reads_control(self):
        self.assertEqual(
            watch._cadence_interval_days("every 2 days"), 2)
        self.assertEqual(
            watch._cadence_interval_days("every 2 months"), 60)


# ----------------------------------------------------------------:
# the error vocabulary helpers stand guarded against an unhashable
# string subclass.
# ----------------------------------------------------------------

class BadStr(str):
    __hash__ = None


class Test056UnhashableStringSubclass(unittest.TestCase):

    def test_helpers_return_none_on_the_unhashable_string(self):
        self.assertIsNone(
            errors.error_for_token(BadStr("HOME_MISSING")))
        self.assertIsNone(errors.error_for_row(BadStr("U-6")))

    def test_recorded_error_survives_the_unhashable_token(self):
        class ForeignError(Exception):
            token = BadStr("HOME_MISSING")

        record = service.recorded_error(ForeignError("boom"))
        self.assertIsInstance(record, dict)
        self.assertEqual(record["message"], "boom")

    def test_error_construction_refuses_it_as_a_value_error(self):
        with self.assertRaises(ValueError):
            errors.CitelineError(
                "boom", token=BadStr("HOME_MISSING"))

    def test_hashable_lookups_still_work_control(self):
        self.assertEqual(
            errors.error_for_token("HOME_MISSING")["row"], "U-6")
        self.assertEqual(
            errors.error_for_row("U-6")["token"], "HOME_MISSING")


# ----------------------------------------------------------------:
# the audit front matter key counter stands on the one block
# reading the parser reads.
# ----------------------------------------------------------------

class Test057KeyCounterOneBlockReading(SeededBase):

    def count_of(self, text):
        page = temp_file(self, text, "page.md")
        return service._front_matter_key_count(str(page))

    def test_dots_fence_closes_the_block(self):
        text = ("---\ntitle: one\nauthor: two\n...\n"
                + "".join("body%d: text\n" % i for i in range(6))
                + "Acme Ledger helps teams track citations.\n")
        self.assertEqual(self.count_of(text), 2)

    def test_unclosed_block_counts_no_block(self):
        text = ("---\ntitle: one\n"
                + "".join("key%d: text\n" % i for i in range(6)))
        self.assertIsNone(self.count_of(text))

    def test_flow_form_counts_its_json_keys(self):
        text = ('---\n{"a": 1, "b": 2, "c": 3, "d": 4, '
                '"e": 5, "f": 6}\n---\n'
                "Acme Ledger helps teams track citations.\n")
        self.assertEqual(self.count_of(text), 6)

    def test_indented_flow_form_counts_its_json_keys(self):
        keys = ",\n".join(
            '  "k%d": %d' % (i, i) for i in range(14))
        text = ("---\n{\n" + keys + "\n}\n---\n"
                "Acme Ledger helps teams track citations.\n")
        self.assertEqual(self.count_of(text), 14)

    def set_key_limit(self):
        journal.write_config(
            str(self.home),
            "front_matter_key_count = 5\n"
            "front_matter_block_size = 128\n"
            "front_matter_value_length_per_key = 30000\n"
            "front_matter_size_after_alias_expansion = 256\n")

    def test_dots_closed_two_key_block_passes_the_audit(self):
        self.set_key_limit()
        page = temp_file(
            self,
            "---\ntitle: one\nauthor: two\n...\n"
            + "".join("body%d: text\n" % i for i in range(6))
            + "Acme Ledger helps teams track citations.\n",
            "page.md")
        record = service.audit(
            home=str(self.home), page_file=str(page),
            audit_date=AUDIT_DATE)
        self.assertIsNotNone(record.get("run_id"))

    def test_flow_block_over_the_limit_refuses_the_audit(self):
        self.set_key_limit()
        page = temp_file(
            self,
            '---\n{"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, '
            '"f": 6}\n---\n'
            "Acme Ledger helps teams track citations.\n",
            "page.md")
        with self.assertRaises(errors.CitelineError) as caught:
            service.audit(
                home=str(self.home), page_file=str(page),
                audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")


# ----------------------------------------------------------------:
# one probe report artefact stands on one fold instant whole, its
# figure side and its failure side taken together.
# ----------------------------------------------------------------

class Test058ProbeReportOneFoldInstant(SeededBase):

    def test_two_corrections_between_folds_do_not_split(self):
        self.import_one()
        with self.assertRaises(errors.CitelineError):
            service.probe_report(
                home=str(self.home), product=PRODUCT, round="nope",
                audit_date=AUDIT_DATE)
        failure = entries_of_kind(self.home, "failure_record")[-1]
        answer = entries_of_kind(self.home, "answer_imported")[-1]
        real_round_entries = service._round_entries
        landed = {"done": False}

        def wrapper(home, product_record, round_record):
            if not landed["done"]:
                landed["done"] = True
                corrected = dict(failure.get("payload") or {})
                corrected["error_value"] = "CORRECTED_MARKER"
                corrected["rule_fired"] = "CORRECTED_MARKER"
                journal.append_entry(
                    str(home), "correction",
                    {"supersedes_sequence": failure["sequence"],
                     "corrected_record": corrected},
                    audit_date=AUDIT_DATE)
                moved = dict(answer.get("payload") or {})
                moved["query"] = Q2
                journal.append_entry(
                    str(home), "correction",
                    {"supersedes_sequence": answer["sequence"],
                     "corrected_record": moved},
                    audit_date=AUDIT_DATE)
            return real_round_entries(
                home, product_record, round_record)

        with mock.patch.object(service, "_round_entries", wrapper):
            result = service.probe_report(
                home=str(self.home), product=PRODUCT, round=ROUND,
                audit_date=AUDIT_DATE)
        values = [payload.get("error_value")
                  for payload in result.get("failure_records") or []]
        self.assertIn("UNKNOWN_ROUND", values)
        self.assertNotIn("CORRECTED_MARKER", values)
        per_query = result.get("per_query") or {}
        self.assertEqual(
            (per_query.get(Q1) or {}).get("answer_count"), 1)
        self.assertNotEqual(
            (per_query.get(Q2) or {}).get("answer_count"), 1)
        followup = service.probe_report(
            home=str(self.home), product=PRODUCT, round=ROUND,
            audit_date=AUDIT_DATE)
        values = [payload.get("error_value")
                  for payload in followup.get("failure_records")
                  or []]
        self.assertIn("CORRECTED_MARKER", values)
        per_query = followup.get("per_query") or {}
        self.assertEqual(
            (per_query.get(Q2) or {}).get("answer_count"), 1)


# ----------------------------------------------------------------:
# the guide store stands judged at the store, a guide stored only
# on the standing audit record at the moment it lands, the attempt
# bound stated in the open.
# ----------------------------------------------------------------

class Test059GuideStoreJudged(SeededBase):

    def audit_one(self):
        return service.audit(
            home=str(self.home), page_file=str(PAGE),
            audit_date=AUDIT_DATE)

    def test_correction_at_the_append_gate_never_lands(self):
        record = self.audit_one()
        audit_entry = entries_of_kind(self.home, "audit_record")[-1]
        real_append = journal.append_entry
        state = {"plant_failed": False}

        def wrapper(home, kind, payload, audit_date=None,
                    run_id=None):
            if kind == "guide_record":
                corrected = dict(audit_entry.get("payload") or {})
                corrected["canonical_line"] = (
                    "Corrected canonical line for Acme Ledger.")
                try:
                    real_append(
                        home, "correction",
                        {"supersedes_sequence":
                         audit_entry["sequence"],
                         "corrected_record": corrected},
                        audit_date=AUDIT_DATE)
                except Exception:
                    state["plant_failed"] = True
            return real_append(
                home, kind, payload, audit_date=audit_date,
                run_id=run_id)

        with mock.patch.object(journal, "append_entry", wrapper):
            service.guide(
                home=str(self.home), run_id=record["run_id"],
                audit_date=AUDIT_DATE)
        self.assertTrue(state["plant_failed"])
        self.assertEqual(
            entries_of_kind(self.home, "correction"), [])
        guides = payloads_of_kind(self.home, "guide_record")
        self.assertEqual(len(guides), 1)
        self.assertIn(
            "Acme Ledger helps teams track citations.",
            str(guides[-1].get("opening_text") or ""))

    def test_correction_on_every_build_refuses_at_the_store(self):
        record = self.audit_one()
        audit_entry = entries_of_kind(self.home, "audit_record")[-1]
        real_draft = guide_module.draft_from_audit_record
        builds = {"count": 0}

        def wrapper(audit_record, **kwargs):
            draft = real_draft(audit_record, **kwargs)
            builds["count"] += 1
            standing = service.audit(
                home=str(self.home), run_id=record["run_id"])
            corrected = dict(standing)
            corrected["canonical_line"] = (
                "Correction line %d for Acme Ledger."
                % builds["count"])
            journal.append_entry(
                str(self.home), "correction",
                {"supersedes_sequence": audit_entry["sequence"],
                 "corrected_record": corrected},
                audit_date=AUDIT_DATE)
            return draft

        with mock.patch.object(
                guide_module, "draft_from_audit_record", wrapper):
            with self.assertRaises(errors.CitelineError) as caught:
                service.guide(
                    home=str(self.home), run_id=record["run_id"],
                    audit_date=AUDIT_DATE)
        self.assertEqual(
            token_of(caught.exception), "VALIDATION_FAILED")
        self.assertEqual(
            payloads_of_kind(self.home, "guide_record"), [])

    def test_correction_during_first_build_still_followed(self):
        record = self.audit_one()
        audit_entry = entries_of_kind(self.home, "audit_record")[-1]
        real_draft = guide_module.draft_from_audit_record
        landed = {"done": False}

        def wrapper(audit_record, **kwargs):
            draft = real_draft(audit_record, **kwargs)
            if not landed["done"]:
                landed["done"] = True
                corrected = dict(audit_entry.get("payload") or {})
                corrected["canonical_line"] = (
                    "Corrected canonical line for Acme Ledger.")
                journal.append_entry(
                    str(self.home), "correction",
                    {"supersedes_sequence": audit_entry["sequence"],
                     "corrected_record": corrected},
                    audit_date=AUDIT_DATE)
            return draft

        with mock.patch.object(
                guide_module, "draft_from_audit_record", wrapper):
            service.guide(
                home=str(self.home), run_id=record["run_id"],
                audit_date=AUDIT_DATE)
        guides = payloads_of_kind(self.home, "guide_record")
        self.assertEqual(len(guides), 1)
        self.assertIn(
            "Corrected canonical line for Acme Ledger.",
            str(guides[-1].get("opening_text") or ""))


# ----------------------------------------------------------------:
# the WatchPlan target form stands judged before its fields stand
# read.
# ----------------------------------------------------------------

class Test065TargetFormJudgedAtOpen(unittest.TestCase):

    def plan(self, target):
        return {"home": "/tmp/home", "scope": "picked",
                "targets": [target], "audit_date": AUDIT_DATE}

    def test_non_object_targets_refuse_malformed_call(self):
        for bad in ("target", None, 5, ["x"], True):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(
                        errors.CitelineError) as caught:
                    watch._validate_plan(self.plan(bad))
                self.assertEqual(
                    token_of(caught.exception), "MALFORMED_CALL")

    def test_object_target_still_opens_control(self):
        targets = watch._validate_plan(self.plan(
            {"product": PRODUCT, "round": ROUND}))
        self.assertEqual(len(targets), 1)


# ----------------------------------------------------------------:
# the second round fields stand under the plan shape discipline.
# ----------------------------------------------------------------

class Test066SecondRoundFieldsJudged(unittest.TestCase):

    def plan(self, target=None, **extra):
        plan = {"home": "/tmp/home", "scope": "picked",
                "targets": [target or {"product": PRODUCT,
                                       "round": ROUND}],
                "audit_date": AUDIT_DATE}
        plan.update(extra)
        return plan

    def test_plan_second_round_as_a_list_refuses(self):
        with self.assertRaises(errors.CitelineError) as caught:
            watch._validate_plan(self.plan(second_round=[1, 2]))
        self.assertEqual(
            token_of(caught.exception), "MALFORMED_CALL")

    def test_plan_second_rounds_as_a_string_refuses(self):
        with self.assertRaises(errors.CitelineError) as caught:
            watch._validate_plan(self.plan(second_rounds="round-2"))
        self.assertEqual(
            token_of(caught.exception), "MALFORMED_CALL")

    def test_plan_second_rounds_with_a_number_value_refuses(self):
        with self.assertRaises(errors.CitelineError) as caught:
            watch._validate_plan(
                self.plan(second_rounds={PRODUCT: 5}))
        self.assertEqual(
            token_of(caught.exception), "MALFORMED_CALL")

    def test_target_second_round_as_a_record_refuses(self):
        with self.assertRaises(errors.CitelineError) as caught:
            watch._validate_plan(self.plan(
                {"product": PRODUCT, "round": ROUND,
                 "second_round": {"label": "round-2"}}))
        self.assertEqual(
            token_of(caught.exception), "MALFORMED_CALL")

    def test_stated_second_round_forms_still_open_control(self):
        self.assertEqual(len(watch._validate_plan(
            self.plan(second_round="round-2"))), 1)
        self.assertEqual(len(watch._validate_plan(
            self.plan(second_rounds={PRODUCT: ["round-2"]}))), 1)
        self.assertEqual(len(watch._validate_plan(
            self.plan(second_rounds=["round-2"]))), 1)
        self.assertEqual(len(watch._validate_plan(self.plan(
            {"product": PRODUCT, "round": ROUND,
             "second_round": "round-2"}))), 1)


# ----------------------------------------------------------------:
# the service seam duplicate front matter measurement stands whole
# on a JSON numeric value, the limit in force enforced on the
# service route.
# ----------------------------------------------------------------

class Test070SeamNumericMeasurement(SeededBase):

    def setUp(self):
        super().setUp()
        journal.write_config(
            str(self.home),
            "front_matter_value_length_per_key = 100\n")

    def answer_with_block(self, block):
        return temp_file(
            self, "---\n" + block + "\n---\n"
            "Acme Ledger is a ledger tool.\n", "answer.txt")

    def test_whole_numeric_value_over_the_limit_refuses(self):
        answer = self.answer_with_block(
            '{"note": %s}' % ("7" * 200))
        with self.assertRaises(errors.CitelineError) as caught:
            do_import(self.home, answer)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_numeric_value_inside_a_container_refuses(self):
        answer = self.answer_with_block(
            '{"note": [1.%s]}' % ("0" * 200))
        with self.assertRaises(errors.CitelineError) as caught:
            do_import(self.home, answer)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_short_numeric_value_still_imports_control(self):
        answer = self.answer_with_block(
            '{"note": %s}' % ("7" * 50))
        result = do_import(self.home, answer)
        self.assertIsNotNone(result)


# ----------------------------------------------------------------:
# the reading routes stand signalled where a recovery stands
# deferred whole.
# ----------------------------------------------------------------

class Test071DeferredRecoverySignalled(SeededBase):

    def setUp(self):
        super().setUp()
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

    def test_reading_routes_refuse_on_the_deferred_state(self):
        calls = (
            lambda: service.status(home=str(self.home)),
            lambda: service.verify(home=str(self.home)),
            lambda: service.list_products(home=str(self.home)),
            lambda: service.estate_grounds(
                home=str(self.home), product=PRODUCT),
            lambda: service.probe_report(
                home=str(self.home), product=PRODUCT, round=ROUND,
                audit_date=AUDIT_DATE),
            lambda: service.export_capture_worksheet(
                home=str(self.home), product=PRODUCT, round=ROUND,
                output_path=str(
                    Path(self.root) / "sheet-out.txt"),
                audit_date=AUDIT_DATE),
        )
        for call in calls:
            with self.assertRaises(errors.CitelineError) as caught:
                call()
            self.assertEqual(
                token_of(caught.exception), "JOURNAL_CAP_EXCEEDED")
        intent = Path(journal._batch_intent_path(str(self.home)))
        self.assertTrue(intent.exists())
        self.assertEqual(len(journal_entries(self.home)), 5)

    def test_routes_read_settled_state_once_the_cap_admits(self):
        journal.write_config(
            str(self.home), "journal_length = 10\n")
        result = service.status(home=str(self.home))
        self.assertEqual(result["entry_count"], 4)
        names = [record.get("name") for record in
                 service.list_products(home=str(self.home))]
        self.assertEqual(names, [PRODUCT])


# ----------------------------------------------------------------:
# the assembly correction stands on the one limits reading the run
# started under.
# ----------------------------------------------------------------

class Test072CorrectionOnTheStartReading(SeededBase):

    def test_config_shift_after_the_batch_does_not_restate(self):
        page = temp_file(
            self, "---\ntitle: %s\n---\n"
            "Acme Ledger helps teams track citations.\n"
            % ("v" * 100), "page.md")
        gated = gated_batch(
            self, shift_config=(
                "front_matter_value_length_per_key = 50\n"))
        with mock.patch.object(
                journal, "append_entries_atomic", gated):
            record = service.audit(
                home=str(self.home), page_file=str(page),
                audit_date=AUDIT_DATE)
        limits = record["limits_in_force"]
        self.assertEqual(limits["run_id"], record["run_id"])
        value = limits["by_limit"][
            "front_matter_value_length_per_key"]["value"]
        self.assertEqual(value, 4096)
        standing = service.audit(
            home=str(self.home), run_id=record["run_id"])
        self.assertEqual(
            standing["limits_in_force"]["by_limit"][
                "front_matter_value_length_per_key"]["value"],
            4096)


if __name__ == "__main__":
    unittest.main()
