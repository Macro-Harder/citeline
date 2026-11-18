"""Journal family.

Each test pins one register entry from design/audit/
the register paper on the behaviour the register and
the round 4 disposition state. Homes are scratch homes
under a temporary directory. No test here touches a
standing test item or a governed ground."""

import base64
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


def crafted_line(kind, payload, sequence, previous_hash, extra=None):
    entry = {"sequence": sequence, "entry_kind": kind,
             "form_version": 1, "payload": payload,
             "previous_hash": previous_hash}
    if extra:
        entry.update(extra)
    return journal.canonical_bytes(entry)


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

    def size_after(self, count, home=None):
        return sum(len(line) + 1
                   for line in self.journal_lines(home)[:count])

    def kinds(self, home=None):
        return [entry["entry_kind"]
                for entry in journal.fold(home or self.home)]


class PlausiblePrefixPositionTests(HomeCase):
    def test_r4_001_inter_token_garbage_is_not_plausible(self):
        tails = [b'{"a":"b":', b'{"a",', b'{"a":"b"1',
                 b'{"a":"b"true', b'{"a":"b"{', b'{"a":01',
                 b'{"a":[1 2', b'{"a":{"b":1,}']
        for tail in tails:
            self.assertFalse(
                journal._is_plausible_entry_prefix(tail),
                msg=repr(tail))

    def test_r4_001_genuine_partial_forms_still_plausible(self):
        tails = [b'{"entry_kind":"round_named","form_vers',
                 b'{"a":12', b'{"a":tru', b'{"a":nul',
                 b'{"a":"b', b'{"a":-', b'{"a":1e',
                 b'{"a":0', b'{"a":0.5', b'{"a":[1,2',
                 b'{"a":{"b":1,']
        for tail in tails:
            self.assertTrue(
                journal._is_plausible_entry_prefix(tail),
                msg=repr(tail))

    def test_r4_001_position_garbage_not_hidden_by_lock_holder(self):
        import fcntl
        for index, tail in enumerate(
                (b'{"a":"b":', b'{"a",', b'{"a":01')):
            home = os.path.join(self.tmp.name, "h-%d" % index)
            os.makedirs(home)
            journal.append_entry(home, "product_registered",
                                 product_payload("P", "p-0"))
            with open(journal.journal_path(home), "ab") as handle:
                handle.write(tail)
            journal._scan_cache.clear()
            lock_path = os.path.join(home, ".citeline-write.lock")
            handle = open(lock_path, "a+")
            self.addCleanup(handle.close)
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = journal.verify_chain(home)
            self.assertFalse(result["passed"], msg=repr(tail))
            fcntl.flock(handle, fcntl.LOCK_UN)
            handle.close()


class BatchIntentStartingStateTests(HomeCase):
    def genuine_anchor_setup(self):
        anchor = os.path.join(self.tmp.name, "anchor.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        self.append_product("P0", "p-0")
        size_before = len(self.journal_bytes())
        with open(anchor, "rb") as handle:
            anchor_bytes = handle.read()
        journal.append_entry(
            self.home, "audit_record", {"tag": "partial one"})
        journal.append_entry(
            self.home, "audit_record", {"tag": "partial two"})
        journal._write_batch_intent(
            self.home, size_before, anchor, anchor_bytes, 3)
        return anchor, size_before

    def test_r4_002_anchor_repoint_does_not_destroy_genuine_record(self):
        anchor, _size = self.genuine_anchor_setup()
        other = os.path.join(self.tmp.name, "anchor-two.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % other)
        self.assertTrue(journal.recover_interrupted_batch(self.home))
        # The partial batch stands removed and the record
        # stands acted, not cleared unacted. Restated at
        # Step 20 under delegated decision 1 (register item
        # R19-033, fix paper step-20-fix-05-journal-status):
        # the recovery record append meets the repointed
        # config anchor, which stands missing at its new
        # path, and a missing anchor no longer bars an
        # append, so the recovery record now stands here
        # where the round 3 append failure discipline
        # formerly barred it. The genuine record limb
        # below stands as it stood.
        self.assertEqual(self.kinds(), ["product_registered",
                                        "failure_record"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        self.assertFalse(self.intent_standing())
        with open(anchor, "rb") as handle:
            restored = handle.read()
        lines = self.journal_lines()
        self.assertEqual(
            restored,
            ("%s 1\n" % hashlib.sha256(lines[0]).hexdigest()
             ).encode("utf-8"))

    def test_r4_002_damaged_config_does_not_destroy_genuine_record(self):
        self.genuine_anchor_setup()
        config = journal.config_path(self.home)
        with open(config, "a", encoding="utf-8") as handle:
            handle.write("a malformed line\n")
        with self.assertRaises(journal.ConfigError):
            self.append_product("PX", "p-x")
        journal.write_config(
            self.home,
            "anchor_path = %s\n" % os.path.join(
                self.tmp.name, "anchor.txt"))
        entry = self.append_product("P1", "p-1")
        self.assertEqual(entry["sequence"], 3)
        self.assertEqual(self.kinds(), ["product_registered",
                                        "failure_record",
                                        "product_registered"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        self.assertFalse(self.intent_standing())


class JoinPermitTests(HomeCase):
    def test_r4_003_ambient_append_inside_batch_window_is_contended(self):
        self.append_product("P0", "p-0")
        sink = []
        real_write = journal._write_batch_intent

        def wrapper(home, size, anchor_path, anchor_bytes, count):
            try:
                journal.append_entry(
                    home, "audit_record", {"tag": "ambient"})
                sink.append(("ok", None))
            except journal.JournalError as error:
                sink.append(("error", error.token))
            return real_write(home, size, anchor_path,
                              anchor_bytes, count)

        batch = [
            ("limit_raise", {"limit": "limit_39",
                             "raised_value": 200000,
                             "run_id": "run-1"}),
            ("limit_raise", {"limit": "limit_39",
                             "raised_value": 300000,
                             "run_id": "run-1"}),
        ]
        with mock.patch.object(journal, "_write_batch_intent",
                               wrapper):
            with self.assertRaises(journal.JournalError) as caught:
                journal.append_entries_atomic(self.home, batch)
        self.assertEqual(caught.exception.token,
                         "LIMIT_RAISE_REPEATED")
        self.assertEqual(sink, [("error", "WRITE_CONTENDED")])
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 1)
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r4_003_batch_inner_appends_still_join(self):
        appended = journal.append_entries_atomic(
            self.home,
            [("product_registered", product_payload("P0", "p-0")),
             ("product_registered", product_payload("P1", "p-1"))])
        self.assertEqual([entry["sequence"] for entry in appended],
                         [1, 2])
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class RecoveryPrefixChainTests(HomeCase):
    def corrupt_first_line(self):
        lines = self.journal_lines()
        lines[0] = lines[0].replace(
            b"product_registered", b"product_registereX")
        self.write_raw_lines(lines)

    def test_r4_004_head_line_corruption_defers_recovery(self):
        self.append_product("P0", "p-0")
        size_before = len(self.journal_bytes())
        journal.append_entry(
            self.home, "audit_record", {"tag": "partial"})
        journal._write_batch_intent(
            self.home, size_before, None, None, 1)
        self.corrupt_first_line()
        before = self.journal_bytes()
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        self.assertTrue(self.intent_standing())
        self.assertEqual(self.journal_bytes(), before)
        lines = self.journal_lines()
        lines[0] = lines[0].replace(
            b"product_registereX", b"product_registered")
        self.write_raw_lines(lines)
        self.assertTrue(journal.recover_interrupted_batch(self.home))
        self.assertEqual(self.kinds(), ["product_registered",
                                        "failure_record"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r4_004_prefix_corruption_reports_no_landed_recovery(self):
        self.append_product("P0", "p-0")
        self.append_product("P1", "p-1")
        size_before = len(self.journal_bytes())
        journal.append_entry(
            self.home, "audit_record", {"tag": "partial"})
        journal._write_batch_intent(
            self.home, size_before, None, None, 1)
        self.corrupt_first_line()
        before = self.journal_bytes()
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        self.assertTrue(self.intent_standing())
        self.assertEqual(self.journal_bytes(), before)


class CorrectionTargetKindTests(HomeCase):
    def chain(self, items):
        lines = []
        previous = None
        for sequence, (kind, payload) in enumerate(items, start=1):
            line = crafted_line(kind, payload, sequence, previous)
            lines.append(line)
            previous = hashlib.sha256(line).hexdigest()
        return lines

    def test_r4_005_correction_of_a_correction_does_not_verify(self):
        lines = self.chain([
            ("product_registered", product_payload("P", "p-0")),
            ("correction",
             {"supersedes_sequence": 1,
              "corrected_record": product_payload("N", "p-0")}),
            ("correction",
             {"supersedes_sequence": 2,
              "corrected_record": product_payload("M", "p-0")}),
        ])
        self.write_raw_lines(lines)
        self.assertFalse(journal.verify_chain(self.home)["passed"])
        other = os.path.join(self.tmp.name, "replay-home")
        os.makedirs(other)
        with self.assertRaises(journal.JournalError):
            journal.replay(other, lines)

    def test_r4_005_correction_of_a_record_still_verifies(self):
        lines = self.chain([
            ("product_registered", product_payload("P", "p-0")),
            ("correction",
             {"supersedes_sequence": 1,
              "corrected_record": product_payload("N", "p-0")}),
        ])
        self.write_raw_lines(lines)
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r4_005_v10_single_correction_still_verifies(self):
        lines = self.chain([
            ("correction",
             {"supersedes_sequence": 1,
              "corrected_record": product_payload("N", "p-0")}),
        ])
        self.write_raw_lines(lines)
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class FoldCopyWholeEntryTests(HomeCase):
    def test_r4_006_mutation_of_extra_member_does_not_write_back(self):
        line = crafted_line(
            "product_registered",
            {"name": "Original", "product_id": "p-0"},
            1, None, extra={"extra": {"tags": ["first"]}})
        self.write_raw_lines([line])
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        first = journal.fold(self.home)
        first[0]["extra"]["tags"].append("second")
        first[0]["payload"]["name"] = "Mutated"
        second = journal.fold(self.home)
        self.assertEqual(second[0]["extra"]["tags"], ["first"])
        self.assertEqual(second[0]["payload"]["name"], "Original")
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class FoldRegistryUnhashableTests(HomeCase):
    def test_r4_007_unhashable_product_id_meets_journal_vocabulary(self):
        line = crafted_line(
            "product_registered",
            {"name": "P", "product_id": ["x"]}, 1, None)
        self.write_raw_lines([line])
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        with self.assertRaises(journal.JournalError) as caught:
            journal.fold_registry(self.home)
        self.assertEqual(caught.exception.token,
                         "JOURNAL_VERIFY_FAILED")
        self.assertEqual(caught.exception.row, "I-2")

    def test_r4_007_registry_fold_control_still_works(self):
        self.append_product("P0", "p-0")
        state = journal.fold_registry(self.home)
        self.assertEqual(state["p-0"]["name"], "P0")


class BatchIntentFormTests(HomeCase):
    def test_r4_008_record_with_extra_members_is_refused(self):
        anchor = os.path.join(self.tmp.name, "anchor.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        self.append_product("P0", "p-0")
        with open(anchor, "rb") as handle:
            anchor_bytes = handle.read()
        record = {
            "journal_size": len(self.journal_bytes()),
            "anchor_path": anchor,
            "anchor_bytes": base64.b64encode(
                anchor_bytes).decode("ascii"),
            "count": 2,
            "second_anchor_path": os.path.join(
                self.tmp.name, "elsewhere.txt"),
            "note": "planted",
        }
        self.plant_intent(record)
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        self.assertEqual(len(self.journal_lines()), 1)
        self.assertFalse(self.intent_standing())
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r4_008_extra_field_over_genuine_tail_is_refused(self):
        self.append_product("P0", "p-0")
        size_before = len(self.journal_bytes())
        journal.append_entry(
            self.home, "audit_record", {"tag": "partial"})
        record = {"journal_size": size_before, "anchor_path": None,
                  "anchor_bytes": None, "count": 1, "extra": 1}
        self.plant_intent(record)
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        self.assertEqual(len(self.journal_lines()), 2)

    def test_r4_008_exact_genuine_record_still_recovers(self):
        self.append_product("P0", "p-0")
        size_before = len(self.journal_bytes())
        journal.append_entry(
            self.home, "audit_record", {"tag": "partial"})
        journal._write_batch_intent(
            self.home, size_before, None, None, 1)
        self.assertTrue(journal.recover_interrupted_batch(self.home))
        self.assertEqual(self.kinds(), ["product_registered",
                                        "failure_record"])

    def test_r4_068_record_naming_no_batch_is_refused(self):
        self.append_product("P0", "p-0")
        record = {"journal_size": len(self.journal_bytes()),
                  "anchor_path": None, "anchor_bytes": None,
                  "count": 0}
        self.plant_intent(record)
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        self.assertEqual(len(self.journal_lines()), 1)
        self.assertFalse(self.intent_standing())
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class BatchIntentSymlinkTests(HomeCase):
    def test_r4_009_intent_write_does_not_follow_a_symlink(self):
        outside = os.path.join(self.tmp.name, "outside.json")
        os.symlink(outside, journal._batch_intent_path(self.home))
        with self.assertRaises(journal.JournalError) as caught:
            journal.append_entries_atomic(
                self.home,
                [("audit_record", {"tag": "one"})])
        self.assertEqual(caught.exception.token,
                         "JOURNAL_VERIFY_FAILED")
        self.assertEqual(caught.exception.row, "I-2")
        self.assertFalse(os.path.exists(outside))
        self.assertEqual(self.journal_lines(), [])


class BatchIntentParseGuardTests(HomeCase):
    def test_r4_063_deeply_nested_intent_record_refuses_in_vocabulary(self):
        self.append_product("P0", "p-0")
        path = journal._batch_intent_path(self.home)
        with open(path, "wb") as handle:
            handle.write(b"[" * 12000 + b"]" * 12000)
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        self.assertFalse(self.intent_standing())
        entry = self.append_product("P1", "p-1")
        self.assertEqual(entry["sequence"], 2)
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class RecoveryRecordCapTests(HomeCase):
    def test_r4_069_recovery_at_standing_cap_is_not_reported_landed(self):
        journal.write_config(self.home, "journal_length = 3\n")
        for index in range(3):
            self.append_product("P%d" % index, "p-%d" % index)
        journal._write_batch_intent(
            self.home, len(self.journal_bytes()), None, None, 1)
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        self.assertTrue(self.intent_standing())
        self.assertEqual(len(self.journal_lines()), 3)
        journal.write_config(self.home, "journal_length = 4\n")
        self.assertTrue(journal.recover_interrupted_batch(self.home))
        self.assertEqual(self.kinds(),
                         ["product_registered"] * 3
                         + ["failure_record"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r4_069_recovery_at_restored_cap_is_not_reported_landed(self):
        for index in range(5):
            self.append_product("P%d" % index, "p-%d" % index)
        size_before = self.size_after(3)
        journal._write_batch_intent(
            self.home, size_before, None, None, 2)
        journal.write_config(self.home, "journal_length = 3\n")
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        self.assertTrue(self.intent_standing())
        self.assertEqual(len(self.journal_lines()), 5)
        journal.write_config(self.home, "journal_length = 10\n")
        self.assertTrue(journal.recover_interrupted_batch(self.home))
        self.assertEqual(len(self.journal_lines()), 4)
        self.assertEqual(self.kinds()[-1], "failure_record")
        self.assertTrue(journal.verify_chain(self.home)["passed"])


if __name__ == "__main__":
    unittest.main()
