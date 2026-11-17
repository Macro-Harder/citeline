"""Step 17 round 15 fix seat F1 tests: journal family.

Each defect pin states entry S17-R15-001 from
design/audit/step-17-r15-findings-register.md: every
judgement of every journal write site judged the opened
handle alone, by a regular file form and a link count of
exactly one, and never judged that the path still names
that handle, so a rename plant at any counted reading,
at the config write, at the journal append, at the batch
intent write, and at the restore truncate alike, stood
unseen by every judgement of the write. The pins below
plant a rename, in stale form at the return of a counted
reading and in before form ahead of it, with no
replacement, with a replacement standing at the path,
and with a symbolic link standing at the path, and state
the refusal in the vocabulary and the remedy form of
each site. The lock holder line write stands pinned in
its bounded form only, as the entry states it. The
rename away and back controls and the plain controls
stand whole on both trees. Homes are scratch homes under
a temporary directory. No test here touches a standing
test item or a governed ground: CARRY S17-R4-070 and
CARRY S17-R5-026 stand untouched in exact form, and the
refused entry S17-R7-002 stands apart and untouched.
"""

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

    def plant_on_counted_fstat(self, target, plants):
        inode = os.lstat(target).st_ino
        real_fstat = os.fstat
        state = {"count": 0}

        def wrapper(fd):
            info = real_fstat(fd)
            if info.st_ino != inode:
                return info
            state["count"] += 1
            spec = plants.get(state["count"])
            if spec is None:
                return info
            before, action = spec
            if before:
                action()
                return real_fstat(fd)
            action()
            return info

        return mock.patch.object(os, "fstat", wrapper)

    def away_and_back_plants(self, target, outside,
                             away_after_lstat, back_at_fstat):
        real_lstat = os.lstat
        lstat_state = {"count": 0}

        def lstat_wrapper(path, *args, **kwargs):
            info = real_lstat(path, *args, **kwargs)
            if os.fspath(path) == target:
                lstat_state["count"] += 1
                if lstat_state["count"] == away_after_lstat \
                        and os.path.lexists(target):
                    os.rename(target, outside)
            return info

        def back_action():
            if os.path.lexists(outside):
                os.rename(outside, target)

        back = self.plant_on_counted_fstat(
            target, {back_at_fstat: (True, back_action)})
        return mock.patch.object(os, "lstat", lstat_wrapper), back

    def rename_plant(self, target, outside, plant_at, before=False,
                     replacement=None, symlink_to=None):
        def action():
            os.rename(target, outside)
            if replacement is not None:
                with open(target, "wb") as handle:
                    handle.write(replacement)
            if symlink_to is not None:
                os.symlink(symlink_to, target)

        return self.plant_on_counted_fstat(
            target, {plant_at: (before, action)})

    def seed_journal(self):
        journal.append_entry(
            self.home, "product_registered",
            {"name": "Product 0", "product_id": "p-0"})
        path = journal.journal_path(self.home)
        return path, self.read_bytes(path)


class ConfigRenamePlantTests(HomeCase):
    def assert_config_refused(self, plant_at, before=False,
                              replacement=None, symlink_to=None,
                              outside_expected=b""):
        journal.write_config(self.home, "journal_length = 5\n")
        path = journal.config_path(self.home)
        outside = os.path.join(self.tmp.name, "config-out.txt")
        with self.rename_plant(path, outside, plant_at,
                               before=before,
                               replacement=replacement,
                               symlink_to=symlink_to):
            with self.assertRaises(ConfigError) as caught:
                journal.write_config(
                    self.home, "journal_length = 99\n")
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        self.assertFalse(os.path.lexists(path))
        self.assertEqual(self.read_bytes(outside),
                         outside_expected)

    def test_r15_001_config_rename_at_open_judgement_return_refused(self):
        self.assert_config_refused(
            1, outside_expected=b"journal_length = 5\n")

    def test_r15_001_config_rename_at_pre_write_return_refused(self):
        self.assert_config_refused(
            2, outside_expected=b"journal_length = 5\n")

    def test_r15_001_config_rename_at_post_write_return_refused(self):
        self.assert_config_refused(3)

    def test_r15_001_config_rename_at_last_judgement_return_refused(self):
        self.assert_config_refused(8)

    def test_r15_001_config_rename_before_last_judgement_refused(self):
        self.assert_config_refused(8, before=True)

    def test_r15_001_config_rename_before_post_write_refused(self):
        self.assert_config_refused(3, before=True)

    def test_r15_001_config_rename_with_replacement_refused(self):
        self.assert_config_refused(
            3, replacement=b"journal_length = 7\n")

    def test_r15_001_config_rename_with_replacement_before_refused(self):
        self.assert_config_refused(
            3, before=True, replacement=b"journal_length = 7\n")

    def test_r15_001_config_rename_with_symlink_replacement_refused(self):
        victim = os.path.join(self.tmp.name, "victim.txt")
        with open(victim, "wb") as handle:
            handle.write(b"victim text\n")
        self.assert_config_refused(3, symlink_to=victim)
        self.assertEqual(self.read_bytes(victim), b"victim text\n")

    def test_r15_001_config_rename_away_and_back_lands_whole(self):
        journal.write_config(self.home, "journal_length = 5\n")
        path = journal.config_path(self.home)
        outside = os.path.join(self.tmp.name, "config-out.txt")
        away, back = self.away_and_back_plants(path, outside, 3, 4)
        with away, back:
            journal.write_config(self.home, "journal_length = 99\n")
        self.assertEqual(self.read_bytes(path),
                         b"journal_length = 99\n")
        self.assertEqual(os.lstat(path).st_nlink, 1)
        self.assertFalse(os.path.lexists(outside))

    def test_r15_001_config_write_plain_form_lands(self):
        journal.write_config(self.home, "journal_length = 99\n")
        path = journal.config_path(self.home)
        self.assertEqual(self.read_bytes(path),
                         b"journal_length = 99\n")
        self.assertEqual(os.lstat(path).st_nlink, 1)


class AppendRenamePlantTests(HomeCase):
    def assert_append_refused(self, plant_at, before=False):
        path, seed = self.seed_journal()
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        with self.rename_plant(path, outside, plant_at,
                               before=before):
            with self.assertRaises(journal.JournalError) as caught:
                journal.append_entry(
                    self.home, "audit_record", {"tag": "second"})
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        self.assertFalse(os.path.lexists(path))
        self.assertEqual(self.read_bytes(outside), seed)

    def test_r15_001_append_rename_at_open_judgement_return_refused(self):
        self.assert_append_refused(1)

    def test_r15_001_append_rename_before_rejudgement_refused(self):
        self.assert_append_refused(2, before=True)

    def test_r15_001_append_rename_at_rejudgement_return_refused(self):
        self.assert_append_refused(2)

    def test_r15_001_append_rename_at_post_write_return_refused(self):
        self.assert_append_refused(3)

    def test_r15_001_append_rename_before_post_write_refused(self):
        self.assert_append_refused(3, before=True)

    def test_r15_001_append_rename_away_and_back_lands_whole(self):
        path, seed = self.seed_journal()
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        away, back = self.away_and_back_plants(path, outside, 3, 3)
        with away, back:
            entry = journal.append_entry(
                self.home, "audit_record", {"tag": "second"})
        self.assertEqual(entry["sequence"], 2)
        self.assertFalse(os.path.lexists(outside))
        self.assertEqual(len(self.read_bytes(path).splitlines()), 2)
        journal._scan_cache.clear()
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r15_001_append_plain_form_lands(self):
        path, seed = self.seed_journal()
        entry = journal.append_entry(
            self.home, "audit_record", {"tag": "second"})
        self.assertEqual(entry["sequence"], 2)
        journal._scan_cache.clear()
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class IntentRenamePlantTests(HomeCase):
    def standing_intent(self):
        intent_path = journal._batch_intent_path(self.home)
        with open(intent_path, "wb") as handle:
            handle.write(b"{}")
        return intent_path

    def assert_intent_refused(self, plant_at, before=False,
                              outside_expected=b""):
        intent_path = self.standing_intent()
        outside = os.path.join(self.tmp.name, "intent-out.json")
        with self.rename_plant(intent_path, outside, plant_at,
                               before=before):
            written = journal._write_batch_intent(
                self.home, 0, None, None, 1)
        self.assertFalse(written)
        self.assertFalse(os.path.lexists(intent_path))
        self.assertEqual(self.read_bytes(outside),
                         outside_expected)

    def test_r15_001_intent_rename_at_open_judgement_return_refused(self):
        self.assert_intent_refused(1, outside_expected=b"{}")

    def test_r15_001_intent_rename_before_rejudgement_refused(self):
        self.assert_intent_refused(2, before=True)

    def test_r15_001_intent_rename_at_post_write_return_refused(self):
        self.assert_intent_refused(3)

    def test_r15_001_intent_rename_away_and_back_lands_whole(self):
        intent_path = self.standing_intent()
        outside = os.path.join(self.tmp.name, "intent-out.json")
        away, back = self.away_and_back_plants(
            intent_path, outside, 2, 3)
        with away, back:
            written = journal._write_batch_intent(
                self.home, 0, None, None, 1)
        self.assertTrue(written)
        self.assertFalse(os.path.lexists(outside))
        self.assertIn(b"journal_size",
                      self.read_bytes(intent_path))

    def test_r15_001_intent_write_plain_form_lands(self):
        intent_path = journal._batch_intent_path(self.home)
        written = journal._write_batch_intent(
            self.home, 0, None, None, 1)
        self.assertTrue(written)
        self.assertIn(b"journal_size",
                      self.read_bytes(intent_path))


class RestoreRenamePlantTests(HomeCase):
    def standing_journal(self):
        path, seed = self.seed_journal()
        journal.append_entry(
            self.home, "audit_record", {"tag": "second"})
        full = self.read_bytes(path)
        first_size = len(full.split(b"\n")[0]) + 1
        return path, full, first_size

    def test_r15_001_restore_rename_at_open_judgement_return_stands(self):
        path, full, first_size = self.standing_journal()
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        with self.rename_plant(path, outside, 1):
            journal._restore_journal_size(path, first_size)
        self.assertFalse(os.path.lexists(path))
        self.assertEqual(self.read_bytes(outside), full)

    def test_r15_001_restore_rename_before_rejudgement_with_replacement(self):
        path, full, first_size = self.standing_journal()
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        with self.rename_plant(path, outside, 2, before=True,
                               replacement=full):
            journal._restore_journal_size(path, first_size)
        self.assertEqual(self.read_bytes(outside), full)
        self.assertEqual(self.read_bytes(path), full)

    def test_r15_001_restore_rename_at_rejudgement_return_stands(self):
        path, full, first_size = self.standing_journal()
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        with self.rename_plant(path, outside, 2):
            journal._restore_journal_size(path, first_size)
        self.assertFalse(os.path.lexists(path))
        self.assertEqual(self.read_bytes(outside), full)

    def test_r15_001_restore_plain_form_truncates(self):
        path, full, first_size = self.standing_journal()
        journal._restore_journal_size(path, first_size)
        self.assertEqual(os.path.getsize(path), first_size)


class LockRenamePlantBoundedLimbTests(HomeCase):
    def assert_lock_refused(self, plant_at):
        lock_path = journal._lock_path(self.home)
        with open(lock_path, "wb") as handle:
            handle.write(b"")
        outside = os.path.join(self.tmp.name, "lock-out")
        with self.rename_plant(lock_path, outside, plant_at):
            with self.assertRaises(journal.JournalError) as caught:
                with journal._WriteLock(self.home):
                    pass
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        self.assertFalse(os.path.lexists(lock_path))
        self.assertEqual(self.read_bytes(outside), b"")

    def test_r15_001_lock_rename_at_open_judgement_return_refused(self):
        self.assert_lock_refused(1)

    def test_r15_001_lock_rename_at_rejudgement_return_refused(self):
        self.assert_lock_refused(2)


if __name__ == "__main__":
    unittest.main()
