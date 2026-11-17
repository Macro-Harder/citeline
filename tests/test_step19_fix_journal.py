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


