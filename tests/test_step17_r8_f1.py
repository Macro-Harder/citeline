"""Step 17 round 8 fix seat F1 tests: journal family.

Each test pins one register entry from design/audit/
step-17-r8-findings-register.md (S17-R8-001, S17-R8-002,
and S17-R8-025) on the behaviour the register and the
round 8 disposition state. Homes are scratch homes under
a temporary directory. No test here touches a standing
test item or a governed ground.
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

    def journal_lines(self, home=None):
        path = journal.journal_path(home or self.home)
        if not os.path.exists(path):
            return []
        with open(path, "rb") as handle:
            data = handle.read()
        return data.split(b"\n")[:-1] if data else []

    def intent_standing(self, home=None):
        return os.path.lexists(
            journal._batch_intent_path(home or self.home))

    def read_text(self, path):
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def anchor_home(self):
        anchor_dir = os.path.join(self.tmp.name, "anchors")
        os.makedirs(anchor_dir)
        anchor = os.path.join(anchor_dir, "anchor.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        journal.append_entry(
            self.home, "product_registered",
            {"name": "Product 0", "product_id": "p-0"})
        return anchor_dir, anchor, self.read_text(anchor)

    def swap_anchor_temporary(self, victim):
        real_lstat = os.lstat
        state = {"done": False}

        def swap_lstat(path, *args, **kwargs):
            info = real_lstat(path, *args, **kwargs)
            if not state["done"] \
                    and "anchor.txt.tmp-" in os.fspath(path):
                state["done"] = True
                os.unlink(path)
                os.symlink(victim, path)
            return info

        return mock.patch.object(os, "lstat", swap_lstat)


class AnchorLinkFormRemedyTests(HomeCase):
    def test_r8_001_hard_linked_anchor_recording_survives(self):
        anchor_dir, anchor, standing = self.anchor_home()
        os.link(anchor, os.path.join(anchor_dir, "anchor-copy.txt"))
        victim = os.path.join(self.tmp.name, "victim.txt")
        with open(victim, "w", encoding="utf-8") as handle:
            handle.write("victim text\n")
        with self.swap_anchor_temporary(victim):
            with self.assertRaises(journal.JournalError) as caught:
                journal.append_entry(
                    self.home, "audit_record", {"tag": "second"})
        self.assertEqual(caught.exception.token,
                         "JOURNAL_VERIFY_FAILED")
        self.assertTrue(os.path.lexists(anchor))
        self.assertFalse(os.path.islink(anchor))
        self.assertEqual(self.read_text(anchor), standing)
        self.assertEqual(self.read_text(victim), "victim text\n")
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 1)
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        third = journal.append_entry(
            self.home, "audit_record", {"tag": "third"})
        self.assertEqual(third["sequence"], 2)

    def test_r8_001_symlink_anchor_recording_survives(self):
        _anchor_dir, anchor, standing = self.anchor_home()
        holder = os.path.join(self.tmp.name, "holder.txt")
        with open(holder, "w", encoding="utf-8") as handle:
            handle.write(standing)
        os.unlink(anchor)
        os.symlink(holder, anchor)
        with self.swap_anchor_temporary(holder):
            with self.assertRaises(journal.JournalError) as caught:
                journal.append_entry(
                    self.home, "audit_record", {"tag": "second"})
        self.assertEqual(caught.exception.token,
                         "JOURNAL_VERIFY_FAILED")
        self.assertTrue(os.path.lexists(anchor))
        self.assertEqual(self.read_text(anchor), standing)
        self.assertEqual(self.read_text(holder), standing)
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 1)
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        third = journal.append_entry(
            self.home, "audit_record", {"tag": "third"})
        self.assertEqual(third["sequence"], 2)


class RecoverySizeStateInsideAppendTests(HomeCase):
    def seeded_recovery_home(self):
        journal.write_config(self.home, "journal_length = 10\n")
        journal.append_entry(
            self.home, "product_registered",
            {"name": "Product 0", "product_id": "p-0"})
        with open(journal.journal_path(self.home), "rb") as handle:
            size_before = len(handle.read())
        journal.append_entry(
            self.home, "audit_record", {"tag": "partial"})
        journal._write_batch_intent(
            self.home, size_before, None, None, 1)
        return os.path.join(self.home, "filler.bin")

    def recovery_wrapper(self, filler, plant, remove):
        real_append = journal.append_entry
        state = {"done": False}

        def wrapper(home, kind, payload, audit_date=None,
                    run_id=None):
            if not state["done"] \
                    and isinstance(payload, dict) \
                    and payload.get("operation") == "recovery":
                state["done"] = True
                if plant:
                    with open(filler, "wb") as handle:
                        handle.truncate(1024 ** 3)
                if remove and os.path.exists(filler):
                    os.unlink(filler)
                with open(journal.config_path(home), "w",
                          encoding="utf-8") as handle:
                    handle.write("journal_length = 1\n")
                return real_append(home, kind, payload,
                                   audit_date=audit_date,
                                   run_id=run_id)
            return real_append(home, kind, payload,
                               audit_date=audit_date, run_id=run_id)

        return mock.patch.object(journal, "append_entry", wrapper)

    def test_r8_002_size_cap_landing_inside_append_judged_landed(self):
        filler = self.seeded_recovery_home()
        with self.recovery_wrapper(filler, plant=True, remove=False):
            landed = journal.recover_interrupted_batch(self.home)
        self.assertTrue(landed)
        self.assertFalse(self.intent_standing())
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 1)
        if os.path.exists(filler):
            os.unlink(filler)

    def test_r8_002_size_cap_leaving_inside_append_judged_deferred(self):
        filler = self.seeded_recovery_home()
        with open(filler, "wb") as handle:
            handle.truncate(1024 ** 3)
        with self.recovery_wrapper(filler, plant=False, remove=True):
            landed = journal.recover_interrupted_batch(self.home)
        self.assertFalse(landed)
        self.assertTrue(self.intent_standing())
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 1)

    def test_r8_002_size_cap_leaving_as_append_returns_still_landed(self):
        filler = self.seeded_recovery_home()
        with open(filler, "wb") as handle:
            handle.truncate(1024 ** 3)
        real_append = journal.append_entry
        state = {"done": False}

        def wrapper(home, kind, payload, audit_date=None,
                    run_id=None):
            if not state["done"] \
                    and isinstance(payload, dict) \
                    and payload.get("operation") == "recovery":
                state["done"] = True
                with open(journal.config_path(home), "w",
                          encoding="utf-8") as handle:
                    handle.write("journal_length = 1\n")
                try:
                    return real_append(home, kind, payload,
                                       audit_date=audit_date,
                                       run_id=run_id)
                finally:
                    os.unlink(filler)
            return real_append(home, kind, payload,
                               audit_date=audit_date, run_id=run_id)

        with mock.patch.object(journal, "append_entry", wrapper):
            landed = journal.recover_interrupted_batch(self.home)
        self.assertTrue(landed)
        self.assertFalse(self.intent_standing())
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 1)


class ConfigWritePostWriteJudgementTests(HomeCase):
    def plant_on_second_fstat(self, target, outside):
        real_fstat = os.fstat
        state = {"count": 0}

        def wrapper(fd):
            info = real_fstat(fd)
            try:
                link = os.readlink("/proc/self/fd/%d" % fd)
            except OSError:
                link = None
            if link == target:
                state["count"] += 1
                if state["count"] == 2:
                    os.link(target, outside)
            return info

        return mock.patch.object(os, "fstat", wrapper)

    def test_r8_025_config_write_judged_at_the_write(self):
        journal.write_config(self.home, "journal_length = 5\n")
        path = journal.config_path(self.home)
        outside = os.path.join(self.tmp.name, "config-out.txt")
        with self.plant_on_second_fstat(path, outside):
            with self.assertRaises(ConfigError) as caught:
                journal.write_config(
                    self.home, "journal_length = 99\n")
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        with open(outside, "rb") as handle:
            self.assertNotIn(b"99", handle.read())
        self.assertFalse(os.path.lexists(path))

    def test_r8_025_config_write_plain_form_lands(self):
        journal.write_config(self.home, "journal_length = 99\n")
        path = journal.config_path(self.home)
        self.assertEqual(self.read_text(path), "journal_length = 99\n")
        self.assertEqual(os.lstat(path).st_nlink, 1)


if __name__ == "__main__":
    unittest.main()
