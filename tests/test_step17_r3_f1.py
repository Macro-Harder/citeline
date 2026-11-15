"""Step 17 round 3 fix seat F1 tests: journal family.

Each test pins one register entry from design/audit/
step-17-r3-findings-register.md (S17-R3-001 to S17-R3-008,
S17-R3-053, S17-R3-062, and S17-R3-065 under the Manager
ruling recorded in the step record) on the behaviour the
register states. Homes are scratch homes under a temporary
directory. No test here touches a standing test item or a
governed ground.
"""

import base64
import copy
import fcntl
import hashlib
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from citeline import journal


def product_payload(name="Product 0", product_id="p-0"):
    return {"name": name, "product_id": product_id}


def crafted_line(kind, payload, sequence, previous_hash):
    entry = {"sequence": sequence, "entry_kind": kind,
             "form_version": 1, "payload": payload,
             "previous_hash": previous_hash}
    return journal.canonical_bytes(entry)


class RoguePayload(dict):
    """A payload whose deepcopy appends re-entrantly, once."""

    def __init__(self, home, sink):
        super().__init__({"name": "rogue carrier"})
        self._home = home
        self._sink = sink

    def __deepcopy__(self, memo):
        try:
            journal.append_entry(
                self._home, "audit_record", {"tag": "rogue"})
            self._sink.append(("ok", None))
        except journal.JournalError as error:
            self._sink.append(("error", error.token))
            raise
        return {"name": "rogue carrier"}


class HomeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(
            dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def append_product(self, name="Product 0", product_id="p-0",
                       home=None, **kw):
        return journal.append_entry(
            home or self.home, "product_registered",
            product_payload(name, product_id), **kw)

    def journal_bytes(self, home=None):
        path = journal.journal_path(home or self.home)
        if not os.path.exists(path):
            return b""
        with open(path, "rb") as handle:
            return handle.read()

    def journal_lines(self, home=None):
        data = self.journal_bytes(home)
        return data.split(b"\n")[:-1] if data else []

    def write_raw_lines(self, lines, home=None):
        home = home or self.home
        with open(journal.journal_path(home), "wb") as handle:
            for line in lines:
                handle.write(line + b"\n")
        journal._scan_cache.clear()

    def plant_intent(self, record, home=None):
        home = home or self.home
        with open(journal._batch_intent_path(home), "w",
                  encoding="utf-8") as handle:
            handle.write(json.dumps(record))

    def intent_standing(self, home=None):
        return os.path.exists(
            journal._batch_intent_path(home or self.home))

    def hold_lock(self, home=None):
        lock_path = os.path.join(
            home or self.home, ".citeline-write.lock")
        handle = open(lock_path, "a+")
        self.addCleanup(handle.close)
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle

    def size_after(self, count, home=None):
        return sum(len(line) + 1
                   for line in self.journal_lines(home)[:count])


class LockReentryTests(HomeCase):
    def test_r3_001_reentrant_append_in_single_append_stores_nothing(self):
        self.append_product()
        sink = []
        rogue = RoguePayload(self.home, sink)
        with self.assertRaises(journal.JournalError) as caught:
            journal.append_entry(
                self.home, "product_registered", rogue)
        self.assertEqual(caught.exception.token, "WRITE_CONTENDED")
        self.assertEqual(caught.exception.row, "X-10")
        self.assertEqual(sink, [("error", "WRITE_CONTENDED")])
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 1)
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r3_001_reentrant_append_inside_batch_stores_nothing(self):
        self.append_product()
        sink = []
        rogue = RoguePayload(self.home, sink)
        batch = [("product_registered", rogue),
                 ("audit_record", {"tag": "batch second"})]
        with self.assertRaises(journal.JournalError) as caught:
            journal.append_entries_atomic(self.home, batch)
        self.assertEqual(caught.exception.token, "WRITE_CONTENDED")
        self.assertEqual(sink, [("error", "WRITE_CONTENDED")])
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 1)
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        self.assertFalse(self.intent_standing())

    def test_r3_001_batch_inner_appends_still_join(self):
        appended = journal.append_entries_atomic(
            self.home,
            [("product_registered", product_payload("P0", "p-0")),
             ("product_registered", product_payload("P1", "p-1"))])
        self.assertEqual([entry["sequence"] for entry in appended],
                         [1, 2])
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r3_001_appends_inside_a_container_lock_still_join(self):
        with journal._WriteLock(self.home):
            entry = journal.append_entry(
                self.home, "product_registered",
                product_payload("P0", "p-0"))
            self.assertEqual(entry["sequence"], 1)
            appended = journal.append_entries_atomic(
                self.home,
                [("product_registered", product_payload("P1", "p-1"))])
            self.assertEqual(appended[0]["sequence"], 2)
        journal._scan_cache.clear()
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class BatchIntentValidationTests(HomeCase):
    def test_r3_002_planted_record_cannot_erase_acknowledged_entries(self):
        for index in range(4):
            self.append_product("P%d" % index, "p-%d" % index)
        self.plant_intent({
            "journal_size": self.size_after(2), "anchor_path": None,
            "anchor_bytes": None, "count": 1})
        entry = self.append_product("P4", "p-4")
        self.assertEqual(entry["sequence"], 5)
        names = [entry["payload"]["name"]
                 for entry in journal.fold(self.home)]
        self.assertEqual(names, ["P0", "P1", "P2", "P3", "P4"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r3_002_planted_record_cannot_write_or_delete_outside_home(self):
        self.append_product("P0", "p-0")
        self.append_product("P1", "p-1")
        victim = os.path.join(self.tmp.name, "victim.txt")
        with open(victim, "w", encoding="utf-8") as handle:
            handle.write("victim content")
        self.plant_intent({
            "journal_size": 0, "anchor_path": victim,
            "anchor_bytes": base64.b64encode(
                b"overwritten by recovery").decode("ascii"),
            "count": 2})
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        with open(victim, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "victim content")
        self.assertEqual(len(self.journal_lines()), 2)
        self.plant_intent({
            "journal_size": 0, "anchor_path": victim,
            "anchor_bytes": None, "count": 2})
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        self.assertTrue(os.path.exists(victim))
        self.assertEqual(len(self.journal_lines()), 2)
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r3_002_oversize_size_does_not_pad_the_journal(self):
        self.append_product("P0", "p-0")
        before = self.journal_bytes()
        self.plant_intent({
            "journal_size": 100000, "anchor_path": None,
            "anchor_bytes": None, "count": 1})
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        self.assertEqual(self.journal_bytes(), before)
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r3_002_typed_anchor_bytes_raise_no_raw_error(self):
        anchor = os.path.join(self.tmp.name, "anchor.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        self.append_product("P0", "p-0")
        self.append_product("P1", "p-1")
        self.append_product("P2", "p-2")
        with open(anchor, "rb") as handle:
            anchor_now = handle.read()
        self.plant_intent({
            "journal_size": self.size_after(2), "anchor_path": anchor,
            "anchor_bytes": 123, "count": 1})
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        self.assertEqual(len(self.journal_lines()), 3)
        entry = self.append_product("P3", "p-3")
        self.assertEqual(entry["sequence"], 4)
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        self.assertTrue(os.path.exists(anchor))
        self.assertNotEqual(anchor_now, b"")

    def test_r3_002_anchor_bytes_mismatching_the_restored_head_refused(self):
        anchor = os.path.join(self.tmp.name, "anchor.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        self.append_product("P0", "p-0")
        self.append_product("P1", "p-1")
        self.append_product("P2", "p-2")
        with open(anchor, "rb") as handle:
            later_anchor = handle.read()
        self.plant_intent({
            "journal_size": self.size_after(2), "anchor_path": anchor,
            "anchor_bytes": base64.b64encode(
                later_anchor).decode("ascii"),
            "count": 1})
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        self.assertEqual(len(self.journal_lines()), 3)
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r3_002_genuine_kill_recovery_still_lands(self):
        self.append_product("P0", "p-0")
        size_before = len(self.journal_bytes())
        journal.append_entry(
            self.home, "answer_imported", {"answer_id": "a-1"})
        journal._write_batch_intent(
            self.home, size_before, None, None, 1)
        self.assertTrue(journal.recover_interrupted_batch(self.home))
        kinds = [entry["entry_kind"]
                 for entry in journal.fold(self.home)]
        self.assertNotIn("answer_imported", kinds)
        self.assertEqual(kinds[0], "product_registered")
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        self.assertFalse(self.intent_standing())


class ReplayRecoveryTests(HomeCase):
    def test_r3_003_replay_over_standing_intent_recovers_first(self):
        self.append_product("P0", "p-0")
        size_before = len(self.journal_bytes())
        partial = journal.append_entry(
            self.home, "audit_record", {"tag": "partial batch"})
        journal._write_batch_intent(
            self.home, size_before, None, None, 1)
        line = crafted_line(
            "round_named", {"round_id": "r-1"}, 3,
            partial["entry_hash"])
        with self.assertRaises(journal.JournalError):
            journal.replay(self.home, [line], resume=True)
        kinds = [entry["entry_kind"]
                 for entry in journal.fold(self.home)]
        self.assertEqual(kinds, ["product_registered",
                                 "failure_record"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        self.assertFalse(self.intent_standing())

    def test_r3_003_replay_without_intent_still_lands(self):
        other = os.path.join(self.tmp.name, "source")
        os.makedirs(other)
        journal.append_entry(other, "product_registered",
                             product_payload("S0", "p-s0"))
        journal.append_entry(other, "product_registered",
                             product_payload("S1", "p-s1"))
        with open(journal.journal_path(other), "rb") as handle:
            lines = handle.read().split(b"\n")[:-1]
        head = journal.replay(self.home, lines)
        self.assertEqual(head, hashlib.sha256(lines[-1]).hexdigest())
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class _Kill(BaseException):
    pass


class BatchRollbackOrderTests(HomeCase):
    def test_r3_004_rollback_restores_before_it_clears(self):
        self.append_product("P0", "p-0")
        order = []
        real_restore = journal._restore_journal_size
        real_clear = journal._clear_batch_intent

        def restore(path, size):
            order.append("restore")
            return real_restore(path, size)

        def clear(home):
            order.append("clear")
            return real_clear(home)

        batch = [("audit_record", {"tag": "one"}),
                 ("correction", {"supersedes_sequence": 999,
                                  "corrected_record": {"x": 1}})]
        with mock.patch.object(journal, "_restore_journal_size",
                               restore), \
                mock.patch.object(journal, "_clear_batch_intent",
                                  clear):
            with self.assertRaises(journal.JournalError):
                journal.append_entries_atomic(self.home, batch)
        self.assertEqual(order, ["restore", "clear"])
        self.assertEqual(len(self.journal_lines()), 1)

    def test_r3_004_kill_inside_rollback_leaves_recovery_standing(self):
        self.append_product("P0", "p-0")

        def killing_restore(path, size):
            raise _Kill()

        batch = [("audit_record", {"tag": "one"}),
                 ("audit_record", {"tag": "two"}),
                 ("correction", {"supersedes_sequence": 999,
                                  "corrected_record": {"x": 1}})]
        with mock.patch.object(journal, "_restore_journal_size",
                               killing_restore):
            with self.assertRaises(_Kill):
                journal.append_entries_atomic(self.home, batch)
        self.assertTrue(self.intent_standing())
        self.assertTrue(journal.recover_interrupted_batch(self.home))
        kinds = [entry["entry_kind"]
                 for entry in journal.fold(self.home)]
        self.assertEqual(kinds, ["product_registered",
                                 "failure_record"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class DuplicateRaiseKeyTests(HomeCase):
    def raise_chain(self, run_ids):
        lines = []
        previous = None
        values = [200000, 300000, 400000]
        for index, run_id in enumerate(run_ids):
            line = crafted_line(
                "limit_raise",
                {"limit": "limit_39",
                 "raised_value": values[index], "run_id": run_id},
                index + 1, previous)
            lines.append(line)
            previous = hashlib.sha256(line).hexdigest()
        return lines

    def test_r3_005_numeric_spellings_of_one_run_verify_as_duplicates(self):
        lines = self.raise_chain([1, 1.0, True])
        self.write_raw_lines(lines)
        self.assertFalse(journal.verify_chain(self.home)["passed"])
        other = os.path.join(self.tmp.name, "replay-home")
        os.makedirs(other)
        with self.assertRaises(journal.JournalError):
            journal.replay(other, lines)
        self.assertFalse(
            os.path.exists(journal.journal_path(other)))

    def test_r3_005_raises_for_distinct_runs_still_verify(self):
        lines = self.raise_chain(["run-a", "run-b"])
        self.write_raw_lines(lines[:2])
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class PlausiblePrefixShapeTests(HomeCase):
    def verify_with_tail(self, name, tail):
        home = os.path.join(self.tmp.name, name)
        os.makedirs(home)
        journal.append_entry(home, "product_registered",
                             product_payload("P", "p-0"))
        with open(journal.journal_path(home), "ab") as handle:
            handle.write(tail)
        journal._scan_cache.clear()
        self.hold_lock(home)
        return journal.verify_chain(home)

    def test_r3_006_token_shape_garbage_not_hidden_by_lock_holder(self):
        tails = [b'{"a":---', b'{"a":::', b'{"a":nul}',
                 b'{"a":1.2.3']
        for index, tail in enumerate(tails):
            result = self.verify_with_tail("h-%d" % index, tail)
            self.assertFalse(result["passed"], msg=repr(tail))

    def test_r3_006_genuine_partial_forms_still_ignored(self):
        tails = [b'{"entry_kind":"round_named","form_vers',
                 b'{"a":12', b'{"a":tru', b'{"a":nul']
        for index, tail in enumerate(tails):
            result = self.verify_with_tail("g-%d" % index, tail)
            self.assertTrue(result["passed"], msg=repr(tail))
            self.assertEqual(result["entry_count"], 1)


class CorrectionRangeTests(HomeCase):
    def chain(self, corrections):
        lines = []
        previous = None
        sequence = 0
        for kind, payload in corrections:
            sequence += 1
            line = crafted_line(kind, payload, sequence, previous)
            lines.append(line)
            previous = hashlib.sha256(line).hexdigest()
        return lines

    def test_r3_007_out_of_range_supersedes_does_not_verify(self):
        for index, value in enumerate((0, -1, 9999)):
            home = os.path.join(self.tmp.name, "h-%d" % index)
            os.makedirs(home)
            lines = self.chain([
                ("product_registered", product_payload("P", "p-0")),
                ("correction",
                 {"supersedes_sequence": value,
                  "corrected_record": product_payload("N", "p-0")}),
            ])
            self.write_raw_lines(lines, home=home)
            self.assertFalse(journal.verify_chain(home)["passed"],
                             msg=repr(value))
            other = os.path.join(self.tmp.name, "r-%d" % index)
            os.makedirs(other)
            with self.assertRaises(journal.JournalError,
                                   msg=repr(value)):
                journal.replay(other, lines)

    def test_r3_007_correction_superseding_a_later_entry_fails(self):
        lines = self.chain([
            ("product_registered", product_payload("P", "p-0")),
            ("correction",
             {"supersedes_sequence": 3,
              "corrected_record": product_payload("N", "p-0")}),
            ("product_registered", product_payload("Q", "p-1")),
        ])
        self.write_raw_lines(lines)
        self.assertFalse(journal.verify_chain(self.home)["passed"])

    def test_r3_007_v10_single_correction_still_verifies(self):
        lines = self.chain([
            ("correction",
             {"supersedes_sequence": 1,
              "corrected_record": product_payload("N", "p-0")}),
        ])
        self.write_raw_lines(lines)
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class FoldCopyTests(HomeCase):
    def test_r3_008_caller_mutation_does_not_write_back(self):
        journal.append_entry(
            self.home, "product_registered",
            {"name": "Original", "product_id": "p-0",
             "aliases": ["first"]})
        first = journal.fold(self.home)
        first[0]["payload"]["name"] = "Mutated"
        first[0]["payload"]["aliases"].append("second")
        second = journal.fold(self.home)
        self.assertEqual(second[0]["payload"]["name"], "Original")
        self.assertEqual(second[0]["payload"]["aliases"], ["first"])
        registry = journal.fold_registry(self.home)
        registry["p-0"]["name"] = "Mutated"
        registry["p-0"]["aliases"].append("second")
        again = journal.fold_registry(self.home)
        self.assertEqual(again["p-0"]["name"], "Original")
        self.assertEqual(again["p-0"]["aliases"], ["first"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class BatchIntentWriteFailureTests(HomeCase):
    def test_r3_053_unwritable_intent_record_bars_the_batch_loudly(self):
        os.makedirs(journal._batch_intent_path(self.home))
        with self.assertRaises(journal.JournalError) as caught:
            journal.append_entries_atomic(
                self.home,
                [("product_registered", product_payload("P0", "p-0")),
                 ("product_registered", product_payload("P1", "p-1"))])
        self.assertEqual(caught.exception.token,
                         "JOURNAL_VERIFY_FAILED")
        self.assertEqual(caught.exception.row, "I-2")
        self.assertEqual(self.journal_lines(), [])
        self.assertFalse(
            os.path.exists(journal.journal_path(self.home)))


class TemporaryLostTests(HomeCase):
    def test_r3_062_anchor_temporary_lost_raises_temporary_lost(self):
        anchor = os.path.join(self.tmp.name, "anchor.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        self.append_product("P0", "p-0")
        with mock.patch("os.replace",
                        side_effect=FileNotFoundError("lost")):
            with self.assertRaises(journal.JournalError) as caught:
                self.append_product("P1", "p-1")
        self.assertEqual(caught.exception.token, "TEMPORARY_LOST")
        self.assertEqual(caught.exception.row, "X-13")
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 1)
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r3_062_replay_temporary_lost_raises_temporary_lost(self):
        other = os.path.join(self.tmp.name, "source")
        os.makedirs(other)
        journal.append_entry(other, "product_registered",
                             product_payload("S0", "p-s0"))
        with open(journal.journal_path(other), "rb") as handle:
            lines = handle.read().split(b"\n")[:-1]
        with mock.patch("os.replace",
                        side_effect=FileNotFoundError("lost")):
            with self.assertRaises(journal.JournalError) as caught:
                journal.replay(self.home, lines)
        self.assertEqual(caught.exception.token, "TEMPORARY_LOST")
        self.assertEqual(caught.exception.row, "X-13")
        self.assertEqual(self.journal_lines(), [])

    def test_r3_062_other_anchor_write_failure_stays_verify_failed(self):
        anchor = os.path.join(self.tmp.name, "anchor.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        self.append_product("P0", "p-0")
        with mock.patch("os.replace",
                        side_effect=PermissionError("denied")):
            with self.assertRaises(journal.JournalError) as caught:
                self.append_product("P1", "p-1")
        self.assertEqual(caught.exception.token,
                         "JOURNAL_VERIFY_FAILED")
        self.assertEqual(len(self.journal_lines()), 1)


class RecoveryRecordTests(HomeCase):
    def plant_killed_batch(self):
        self.append_product("P0", "p-0")
        size_before = len(self.journal_bytes())
        journal.append_entry(
            self.home, "audit_record", {"tag": "partial"})
        journal._write_batch_intent(
            self.home, size_before, None, None, 1)
        return size_before

    def test_r3_065_recovery_appends_a_failure_record(self):
        size_before = self.plant_killed_batch()
        self.assertTrue(journal.recover_interrupted_batch(self.home))
        entries = journal.fold(self.home)
        self.assertEqual([entry["entry_kind"] for entry in entries],
                         ["product_registered", "failure_record"])
        payload = entries[1]["payload"]
        self.assertEqual(payload["operation"], "recovery")
        self.assertEqual(payload["batch_count"], 1)
        self.assertEqual(payload["restored_journal_size"], size_before)
        self.assertEqual(payload["restored_entry_count"], 1)
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        self.assertFalse(self.intent_standing())

    def test_r3_065_recovery_record_stands_before_the_next_append(self):
        self.plant_killed_batch()
        entry = self.append_product("P1", "p-1")
        self.assertEqual(entry["sequence"], 3)
        kinds = [item["entry_kind"]
                 for item in journal.fold(self.home)]
        self.assertEqual(kinds, ["product_registered",
                                 "failure_record",
                                 "product_registered"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r3_065_no_intent_no_recovery_no_record(self):
        self.append_product("P0", "p-0")
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        kinds = [entry["entry_kind"]
                 for entry in journal.fold(self.home)]
        self.assertEqual(kinds, ["product_registered"])


if __name__ == "__main__":
    unittest.main()
