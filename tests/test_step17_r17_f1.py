"""Journal family.

Each defect pin states one entry of the register paper.
Entry: append_entry stores its extended scan cache
entry after the last judgement of the call, on a stat
key taken from the journal path as it then stands, so a
rename plant timed at the return of the last judgement
lstat reading fixes the key the call stores under and
later reads in the same process are served a passed two
entry chain over an absent journal path, or over a seed
replacement holding one entry. Entry: the post write
judgement the replay resume cure added reads its handle
and then its path, and a rename plant timed at the
return of that path reading passes the judgement whole,
the replay returning success with the replayed lines
under the outside name. Entry, in its bounded limb
form: the same timing at the post write judgement of
the lock holder line write leaves the acquire granted
with the holder line under the outside name. The pins
for stand in two forms: a plant at the return of the
lstat reading of the post write judgement the earlier
cure added stands refused in the vocabulary and the
remedy form of its site, and a plant at the return of
the lstat reading of the further rejudgement the cure
of this round adds, the last judgement of its road,
stands pinned in its bounded form, equivalent to a
rename after the call returns, which no judgement
inside the call reaches, in the form the fix paper in
the register states. The plants below wrap os.lstat and
rename the target at the return of the counted call on
that path, returning the stale stat result the caller
already read, in the form the round 17 attack papers
state. Counted calls stand measured on the uncured tree
with the scan cache cleared: journal append, journal
path 5 calls; replay resume, journal path 5 calls; lock
acquire, lock path 3 calls. Homes are scratch homes
under a temporary directory. No test here touches a
standing test item or a governed ground: CARRY and
CARRY stand untouched in exact form, and the refused
stands apart and untouched, no cure stating any parent
directory anchor."""

import hashlib
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from citeline import journal


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


class AppendCacheStoreTests(HomeCase):
    def test_r17_001_append_plant_at_last_lstat_no_replacement(self):
        path, seed = self.seed_journal()
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        journal._scan_cache.clear()
        with self.plant_on_counted_lstat(path, outside, 5):
            entry = journal.append_entry(
                self.home, "audit_record", {"tag": "second"})
        self.assertEqual(entry["sequence"], 2)
        self.assertFalse(os.path.lexists(path))
        result = journal.verify_chain(self.home)
        self.assertEqual(result["entry_count"], 0)
        self.assertEqual(journal.fold(self.home), [])

    def test_r17_001_append_plant_at_last_lstat_seed_replacement(self):
        path, seed = self.seed_journal()
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        journal._scan_cache.clear()
        with self.plant_on_counted_lstat(path, outside, 5,
                                         replacement=seed):
            entry = journal.append_entry(
                self.home, "audit_record", {"tag": "second"})
        self.assertEqual(entry["sequence"], 2)
        self.assertEqual(self.read_bytes(path), seed)
        result = journal.verify_chain(self.home)
        self.assertEqual(result["entry_count"], 1)
        self.assertEqual(
            result["head_hash"],
            hashlib.sha256(seed.splitlines()[0]).hexdigest())
        self.assertEqual(len(journal.fold(self.home)), 1)

    def test_r17_001_append_post_return_rename_control(self):
        path, seed = self.seed_journal()
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        journal._scan_cache.clear()
        entry = journal.append_entry(
            self.home, "audit_record", {"tag": "second"})
        self.assertEqual(entry["sequence"], 2)
        os.rename(path, outside)
        result = journal.verify_chain(self.home)
        self.assertEqual(result["entry_count"], 0)

    def test_r17_001_append_plain_form_verifies_two(self):
        path, seed = self.seed_journal()
        journal._scan_cache.clear()
        entry = journal.append_entry(
            self.home, "audit_record", {"tag": "second"})
        self.assertEqual(entry["sequence"], 2)
        result = journal.verify_chain(self.home)
        self.assertTrue(result["passed"])
        self.assertEqual(result["entry_count"], 2)


class ReplayPostWriteJudgementTests(HomeCase):
    def test_r17_009_replay_plant_at_post_write_lstat_refused(self):
        path, seed = self.seed_journal()
        line = self.second_line(seed)
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        journal._scan_cache.clear()
        with self.plant_on_counted_lstat(path, outside, 5):
            with self.assertRaises(journal.JournalError) as caught:
                journal.replay(self.home, [line], resume=True)
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        self.assertFalse(os.path.lexists(path))
        self.assertEqual(self.read_bytes(outside), seed)

    def test_r17_009_replay_plant_at_last_lstat_bounded_form(self):
        path, seed = self.seed_journal()
        line = self.second_line(seed)
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        journal._scan_cache.clear()
        with self.plant_on_counted_lstat(path, outside, 6):
            result = journal.replay(self.home, [line], resume=True)
        self.assertEqual(result,
                         hashlib.sha256(line).hexdigest())
        self.assertFalse(os.path.lexists(path))
        landed = self.read_bytes(outside)
        self.assertTrue(landed.startswith(seed))
        self.assertEqual(len(landed.splitlines()), 2)

    def test_r17_009_replay_plain_form_lands(self):
        path, seed = self.seed_journal()
        line = self.second_line(seed)
        journal._scan_cache.clear()
        result = journal.replay(self.home, [line], resume=True)
        self.assertEqual(result,
                         hashlib.sha256(line).hexdigest())
        self.assertEqual(len(self.read_bytes(path).splitlines()), 2)
        journal._scan_cache.clear()
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class LockPostWriteJudgementTests(HomeCase):
    def standing_lock(self):
        lock_path = journal._lock_path(self.home)
        with open(lock_path, "wb") as handle:
            handle.write(b"")
        return lock_path

    def test_r17_010_lock_plant_at_post_write_lstat_refused(self):
        lock_path = self.standing_lock()
        outside = os.path.join(self.tmp.name, "lock-out")
        with self.plant_on_counted_lstat(lock_path, outside, 3):
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

    def test_r17_010_lock_plant_at_last_lstat_bounded_form(self):
        lock_path = self.standing_lock()
        outside = os.path.join(self.tmp.name, "lock-out")
        with self.plant_on_counted_lstat(lock_path, outside, 4):
            with journal._WriteLock(self.home):
                pass
        self.assertFalse(os.path.lexists(lock_path))
        self.assertTrue(
            self.read_bytes(outside).startswith(b"holder pid "))

    def test_r17_010_lock_plain_form_lands(self):
        lock_path = journal._lock_path(self.home)
        with journal._WriteLock(self.home):
            pass
        self.assertTrue(
            self.read_bytes(lock_path).startswith(b"holder pid "))


if __name__ == "__main__":
    unittest.main()
