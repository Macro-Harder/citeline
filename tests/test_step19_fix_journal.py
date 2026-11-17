"""Step 19 Phase 6 fix tests, journal seat (Fix seat 3).

One class per register item cured in citeline/journal.py:
R19-034, R19-035, R19-038, R19-039 and R19-040 (scale
logic pins; their timings stand as measurements in the
seat paper, under the cost bound carve out), R19-094,
R19-095, R19-021, R19-022, and R19-105. Each test pins the
behaviour its item states, written before the cure.
"""

import hashlib
import os
import tempfile
import threading
import unittest

import citeline.journal as journal
from citeline import errors


HOME_DATE = "2026-11-17"


def product_payload(name, product_id):
    return {"name": name, "product_id": product_id,
            "canonical_line": name + " line",
            "domain": "example.com", "competitors": [],
            "aliases": [], "query_set": [], "category": []}


class HomeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def append_product(self, name, product_id):
        return journal.append_entry(
            self.home, "product_registered",
            product_payload(name, product_id),
            audit_date=HOME_DATE)

    def anchored_home(self, entries=1):
        anchor = os.path.join(self.tmp.name, "anchor.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        for index in range(entries):
            self.append_product("P%d" % index, "p-%d" % index)
        journal._scan_cache.clear()
        return anchor


class AnchorReadGuardTests(HomeCase):
    """R19-034: the anchor read stands guarded by a regular
    file check and a size bound, so status and verify can
    neither hang on a FIFO nor be killed on a swapped
    anchor file, while a standing recording, a recording
    behind a link to a regular file included, still reads
    as it read."""

    def test_anchor_fifo_does_not_hang_status(self):
        self.append_product("P0", "p-0")
        anchor = os.path.join(self.tmp.name, "anchor_fifo")
        os.mkfifo(anchor)
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        journal._scan_cache.clear()
        outcome = {}

        def run_status():
            outcome["state"] = journal.status_snapshot(self.home)

        worker = threading.Thread(target=run_status, daemon=True)
        worker.start()
        worker.join(15)
        self.assertFalse(worker.is_alive())
        self.assertIn("state", outcome)
        self.assertNotEqual(
            outcome["state"]["anchor"]["agreement"], "matching")

    def test_anchor_oversize_file_reads_bounded(self):
        self.append_product("P0", "p-0")
        anchor = os.path.join(self.tmp.name, "anchor_big")
        with open(anchor, "wb") as handle:
            handle.truncate(5 * 1024 * 1024)
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        journal._scan_cache.clear()
        state = journal.status_snapshot(self.home)
        self.assertIsNone(state["anchor"]["recorded_head"])
        result = journal.verify_chain(self.home)
        self.assertTrue(result["passed"])

    def test_anchor_recording_still_reads_as_matching(self):
        anchor = self.anchored_home(1)
        state = journal.status_snapshot(self.home)
        self.assertEqual(state["anchor"]["agreement"], "matching")
        self.assertIsNotNone(state["anchor"]["recorded_head"])

    def test_anchor_link_to_regular_file_still_reads(self):
        anchor = self.anchored_home(1)
        with open(anchor, "r", encoding="utf-8") as handle:
            standing = handle.read()
        holder = os.path.join(self.tmp.name, "holder.txt")
        with open(holder, "w", encoding="utf-8") as handle:
            handle.write(standing)
        os.unlink(anchor)
        os.symlink(holder, anchor)
        journal._scan_cache.clear()
        state = journal.status_snapshot(self.home)
        self.assertEqual(state["anchor"]["agreement"], "matching")


class AnchorTornFormTests(HomeCase):
    """R19-035: a malformed anchor stands reported in the
    torn form, and no unparsed first token stands printed
    as a recorded head."""

    def test_malformed_anchor_reports_torn(self):
        anchor = self.anchored_home(2)
        with open(anchor, "w", encoding="utf-8") as handle:
            handle.write("garbage partial")
        journal._scan_cache.clear()
        state = journal.status_snapshot(self.home)
        self.assertEqual(state["anchor"]["agreement"], "torn")
        self.assertIsNone(state["anchor"]["recorded_head"])
        self.assertIsNone(state["anchor"]["recorded_sequence"])


class VerifyErrorValueTests(HomeCase):
    """R19-094: the verify error_value field carries the
    vocabulary token, not the integer exit code."""

    def test_verify_error_value_is_the_token(self):
        self.append_product("P0", "p-0")
        with open(journal.journal_path(self.home), "ab") as handle:
            handle.write(b"a complete corrupt line\n")
        journal._scan_cache.clear()
        result = journal.verify_chain(self.home)
        self.assertFalse(result["passed"])
        self.assertEqual(result["error_value"],
                         "JOURNAL_VERIFY_FAILED")
        self.assertEqual(result["row"], "I-2")
        self.assertEqual(result["exit_code"], 5)


class RecoveryRecordVocabularyTests(HomeCase):
    """R19-095: the recovery failure record stands built
    through the CitelineError constructor guard, so its
    error_value is one of the closed vocabulary tokens,
    with its row, class, and exit code carried."""

    def test_recovery_record_error_value_in_vocabulary(self):
        self.append_product("P0", "p-0")
        with open(journal.journal_path(self.home), "rb") as handle:
            size_before = len(handle.read())
        journal.append_entry(
            self.home, "audit_record", {"tag": "partial"})
        journal._write_batch_intent(
            self.home, size_before, None, None, 1)
        self.assertTrue(journal.recover_interrupted_batch(self.home))
        entries = journal.fold(self.home)
        records = [entry for entry in entries
                   if entry["entry_kind"] == "failure_record"]
        self.assertEqual(len(records), 1)
        payload = records[0]["payload"]
        self.assertEqual(payload["operation"], "recovery")
        tokens = {row["token"] for row in errors.ERROR_VOCABULARY}
        self.assertIn(payload["error_value"], tokens)
        self.assertEqual(payload["error_value"], "TEMPORARY_LOST")
        self.assertEqual(payload["row"], "X-13")
        self.assertEqual(payload["precedence_class"], "integrity")
        self.assertEqual(payload["exit_code"], 5)


class ReplaySizeCapTests(HomeCase):
    """R19-021: the replay path enforces the home size cap
    as append_entry enforces it, not the journal length
    cap alone."""

    def test_replay_refuses_chain_over_home_size_cap(self):
        big_text = "x" * 600_000_000
        first = {"sequence": 1, "entry_kind": "product_registered",
                 "form_version": 1,
                 "payload": {"name": big_text,
                             "product_id": "p-big"},
                 "previous_hash": None}
        first_line = journal.canonical_bytes(first)
        second = {"sequence": 2,
                  "entry_kind": "product_registered",
                  "form_version": 1,
                  "payload": {"name": big_text,
                              "product_id": "p-big-2"},
                  "previous_hash":
                      hashlib.sha256(first_line).hexdigest()}
        second_line = journal.canonical_bytes(second)
        with self.assertRaises(journal.JournalError) as caught:
            journal.replay(self.home, [first_line, second_line])
        self.assertEqual(caught.exception.token,
                         "JOURNAL_CAP_EXCEEDED")
        self.assertEqual(caught.exception.limit_number, 40)
        self.assertFalse(
            os.path.exists(journal.journal_path(self.home)))


class HomeSizeCapScopeTests(HomeCase):
    """R19-022: the home size cap counts only files the
    product created, so a foreign file in the home cannot
    consume the cap, drive the remaining figure negative,
    or block writes."""

    def test_foreign_file_does_not_consume_the_cap(self):
        self.append_product("P0", "p-0")
        foreign = os.path.join(self.home, "foreign.bin")
        with open(foreign, "wb") as handle:
            handle.truncate(1024 * 1024 * 1024 + 1024)
        journal._scan_cache.clear()
        state = journal.status_snapshot(self.home)
        remaining = state["capacity_outlook"][
            "total_home_size_remaining"]
        self.assertGreater(remaining, 0)
        entry = self.append_product("P1", "p-1")
        self.assertEqual(entry["sequence"], 2)


class ConfigRelationTests(HomeCase):
    """R19-105: the two config key relations stand stated
    where the config keys are specified, and the
    CONFIG_INVALID refusal names the relation."""

    def test_front_matter_relation_named_in_refusal(self):
        with self.assertRaises(journal.ConfigError) as caught:
            journal.parse_config("front_matter_block_size = 100\n")
        message = str(caught.exception)
        self.assertIn("relation", message)
        self.assertIn("front_matter_size_after_alias_expansion",
                      message)
        self.assertIn("front_matter_block_size", message)
        self.assertEqual(caught.exception.token, "CONFIG_INVALID")

    def test_evidence_spans_relation_named_in_refusal(self):
        with self.assertRaises(journal.ConfigError) as caught:
            journal.parse_config(
                "evidence_spans_per_report = 100\n"
                "evidence_spans_per_check = 150\n")
        message = str(caught.exception)
        self.assertIn("relation", message)
        self.assertIn("evidence_spans_per_report", message)
        self.assertIn("evidence_spans_per_check", message)
        self.assertEqual(caught.exception.token, "CONFIG_INVALID")

    def test_config_inside_the_relations_still_parses(self):
        values, _warnings = journal.parse_config(
            "front_matter_block_size = 10\n"
            "evidence_spans_per_check = 10\n")
        self.assertEqual(values["front_matter_block_size"], 10)
        self.assertEqual(values["evidence_spans_per_check"], 10)


