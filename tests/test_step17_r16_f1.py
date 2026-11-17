"""Journal family.

Each defect pin states one entry of the register paper.
Entry: the replay resume branch is a fifth journal write
road carrying no post write judgement, so a rename plant
timed at the return of the helper lstat reading of its
pre write rejudgement passes every judgement and the
replayed lines land under the outside name with success
reported. Entry: the restore truncate carries no
judgement after its rejudgement and none after its
truncate, so a rename plant timed at the return of the
helper lstat reading of its rejudgement lands the
truncate on the file under the outside name. Entry, in
its bounded limb form: the lock holder line write follows
its rejudgement with no post write judgement, so a plant
at the return of the helper lstat of the rejudgement
leaves the holder line under the outside name with the
acquire granted. Entry: a rename plant timed at the
return of the lstat reading inside the judgement act
passes the last judgement of the config write, of the
journal append, and of the batch intent write. The pins
for that entry stand in two forms: a plant one reading
earlier, at the return of the lstat reading of the
judgement before the last, stands refused in the
vocabulary and the remedy form of its site on every road,
and a plant at the return of the lstat reading of the
last judgement stands pinned in its bounded form, the
form the fix paper in the register states in its
corrected cure claim, equivalent to a rename after the
call returns, which no judgement inside the call reaches.
The plants below wrap os.lstat and rename the target at
the return of the counted call on that path, returning
the stale stat result the caller already read, in the
form the round 16 attack papers state. Counted calls
stand measured on the uncured tree with the scan cache
cleared, in the form the journal paper of round 16
records: replay resume, journal path 4 calls; restore
truncate, journal path 2 calls; lock acquire, lock path 2
calls; journal append, journal path 5 calls; config
write, config path 8 calls; batch intent write, intent
path 3 calls. Homes are scratch homes under a temporary
directory. No test here touches a standing test item or a
governed ground: CARRY and CARRY stand untouched in exact
form, and the refused stands apart and untouched."""

import hashlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from citeline import journal
from citeline.errors import ConfigError


class HomeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(
            dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def read_bytes(self, path):
        with open(path, "rb") as handle:
            return handle.read()

    def plant_on_counted_lstat(self, target, outside, plant_at,
                               replacement=None):
        real_lstat = os.lstat
        state = {"count": 0}

        def wrapper(path, *args, **kwargs):
            info = real_lstat(path, *args, **kwargs)
            if os.fspath(path) == target:
                state["count"] += 1
                if state["count"] == plant_at \
                        and os.path.lexists(target):
                    os.rename(target, outside)
                    if replacement is not None:
                        with open(target, "wb") as handle:
                            handle.write(replacement)
            return info

        return mock.patch.object(os, "lstat", wrapper)

    def seed_journal(self):
        journal.append_entry(
            self.home, "product_registered",
            {"name": "Product 0", "product_id": "p-0"})
        path = journal.journal_path(self.home)
        return path, self.read_bytes(path)

    def second_line(self, seed):
        raw = seed.rstrip(b"\n")
        entry = {
            "sequence": 2,
            "entry_kind": "audit_record",
            "form_version": 1,
            "payload": {"tag": "replayed"},
            "previous_hash": hashlib.sha256(raw).hexdigest(),
        }
        return journal.canonical_bytes(entry)


class ReplayResumePlantTests(HomeCase):
    def test_r16_001_replay_resume_rename_at_pre_write_lstat_refused(self):
        path, seed = self.seed_journal()
        line = self.second_line(seed)
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        journal._scan_cache.clear()
        with self.plant_on_counted_lstat(path, outside, 4):
            with self.assertRaises(journal.JournalError) as caught:
                journal.replay(self.home, [line], resume=True)
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        self.assertFalse(os.path.lexists(path))
        self.assertEqual(self.read_bytes(outside), seed)

    def test_r16_001_replay_resume_rename_at_open_lstat_refused(self):
        path, seed = self.seed_journal()
        line = self.second_line(seed)
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        journal._scan_cache.clear()
        with self.plant_on_counted_lstat(path, outside, 3):
            with self.assertRaises(journal.JournalError) as caught:
                journal.replay(self.home, [line], resume=True)
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        self.assertFalse(os.path.lexists(path))
        self.assertEqual(self.read_bytes(outside), seed)

    def test_r16_001_replay_resume_plain_form_lands(self):
        path, seed = self.seed_journal()
        line = self.second_line(seed)
        journal._scan_cache.clear()
        result = journal.replay(self.home, [line], resume=True)
        self.assertEqual(result,
                         hashlib.sha256(line).hexdigest())
        self.assertEqual(len(self.read_bytes(path).splitlines()), 2)
        journal._scan_cache.clear()
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class RestorePlantTests(HomeCase):
    def standing_journal(self):
        path, seed = self.seed_journal()
        journal.append_entry(
            self.home, "audit_record", {"tag": "second"})
        full = self.read_bytes(path)
        first_size = len(full.split(b"\n")[0]) + 1
        return path, full, first_size

    def test_r16_002_restore_rename_at_rejudgement_lstat_stands(self):
        path, full, first_size = self.standing_journal()
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        with self.plant_on_counted_lstat(path, outside, 2):
            journal._restore_journal_size(path, first_size)
        self.assertFalse(os.path.lexists(path))
        self.assertEqual(self.read_bytes(outside), full)

    def test_r16_002_restore_rename_with_replacement_stands(self):
        path, full, first_size = self.standing_journal()
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        with self.plant_on_counted_lstat(path, outside, 2,
                                         replacement=full):
            journal._restore_journal_size(path, first_size)
        self.assertEqual(self.read_bytes(outside), full)
        self.assertEqual(self.read_bytes(path), full)

    def test_r16_002_restore_plain_form_truncates(self):
        path, full, first_size = self.standing_journal()
        journal._restore_journal_size(path, first_size)
        self.assertEqual(os.path.getsize(path), first_size)


class LockPlantBoundedLimbTests(HomeCase):
    def test_r16_003_lock_rename_at_rejudgement_lstat_refused(self):
        lock_path = journal._lock_path(self.home)
        with open(lock_path, "wb") as handle:
            handle.write(b"")
        outside = os.path.join(self.tmp.name, "lock-out")
        with self.plant_on_counted_lstat(lock_path, outside, 2):
            with self.assertRaises(journal.JournalError) as caught:
                with journal._WriteLock(self.home):
                    pass
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        self.assertFalse(os.path.lexists(lock_path))
        self.assertEqual(self.read_bytes(outside), b"")
        with journal._WriteLock(self.home):
            pass

    def test_r16_003_lock_plain_form_lands(self):
        lock_path = journal._lock_path(self.home)
        with journal._WriteLock(self.home):
            pass
        self.assertTrue(
            self.read_bytes(lock_path).startswith(b"holder pid "))


class LastJudgementTimingTests(HomeCase):
    def test_r16_015_config_rename_one_reading_earlier_refused(self):
        journal.write_config(self.home, "journal_length = 5\n")
        path = journal.config_path(self.home)
        outside = os.path.join(self.tmp.name, "config-out.txt")
        with self.plant_on_counted_lstat(path, outside, 7):
            with self.assertRaises(ConfigError) as caught:
                journal.write_config(
                    self.home, "journal_length = 99\n")
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        self.assertFalse(os.path.lexists(path))
        self.assertEqual(self.read_bytes(outside), b"")

    def test_r16_015_config_rename_at_last_lstat_bounded_form(self):
        journal.write_config(self.home, "journal_length = 5\n")
        path = journal.config_path(self.home)
        outside = os.path.join(self.tmp.name, "config-out.txt")
        with self.plant_on_counted_lstat(path, outside, 8):
            journal.write_config(self.home, "journal_length = 99\n")
        self.assertFalse(os.path.lexists(path))
        self.assertEqual(self.read_bytes(outside),
                         b"journal_length = 99\n")

    def test_r16_015_append_rename_one_reading_earlier_refused(self):
        path, seed = self.seed_journal()
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        journal._scan_cache.clear()
        with self.plant_on_counted_lstat(path, outside, 4):
            with self.assertRaises(journal.JournalError) as caught:
                journal.append_entry(
                    self.home, "audit_record", {"tag": "second"})
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        self.assertFalse(os.path.lexists(path))
        self.assertEqual(self.read_bytes(outside), seed)

    def test_r16_015_append_rename_at_last_lstat_bounded_form(self):
        path, seed = self.seed_journal()
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        journal._scan_cache.clear()
        with self.plant_on_counted_lstat(path, outside, 5):
            entry = journal.append_entry(
                self.home, "audit_record", {"tag": "second"})
        self.assertEqual(entry["sequence"], 2)
        self.assertFalse(os.path.lexists(path))
        landed = self.read_bytes(outside)
        self.assertTrue(landed.startswith(seed))
        self.assertEqual(len(landed.splitlines()), 2)

    def test_r16_015_intent_rename_one_reading_earlier_refused(self):
        intent_path = journal._batch_intent_path(self.home)
        with open(intent_path, "wb") as handle:
            handle.write(b"{}")
        outside = os.path.join(self.tmp.name, "intent-out.json")
        with self.plant_on_counted_lstat(intent_path, outside, 2):
            written = journal._write_batch_intent(
                self.home, 0, None, None, 1)
        self.assertFalse(written)
        self.assertFalse(os.path.lexists(intent_path))
        self.assertEqual(self.read_bytes(outside), b"")

    def test_r16_015_intent_rename_at_last_lstat_bounded_form(self):
        intent_path = journal._batch_intent_path(self.home)
        with open(intent_path, "wb") as handle:
            handle.write(b"{}")
        outside = os.path.join(self.tmp.name, "intent-out.json")
        with self.plant_on_counted_lstat(intent_path, outside, 3):
            written = journal._write_batch_intent(
                self.home, 0, None, None, 1)
        self.assertTrue(written)
        self.assertFalse(os.path.lexists(intent_path))
        self.assertIn(b"journal_size", self.read_bytes(outside))


if __name__ == "__main__":
    unittest.main()
