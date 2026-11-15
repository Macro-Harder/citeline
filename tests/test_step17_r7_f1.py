"""Step 17 round 7 fix seat F1 tests: journal family.

Each test pins one register entry from design/audit/
step-17-r7-findings-register.md (S17-R7-001 to
S17-R7-007) on the behaviour the register and the
round 7 disposition state. Homes are scratch homes
under a temporary directory. No test here touches a
standing test item or a governed ground. Entry
S17-R7-002 stands refused on the ground recorded in
the seat paper, and its test stands as an expected
failure pinning the defect, in the form the refused
entry S17-R3-051 stands pinned.
"""

import os
import subprocess
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

    def journal_bytes(self, home=None):
        path = journal.journal_path(home or self.home)
        if not os.path.exists(path):
            return b""
        with open(path, "rb") as handle:
            return handle.read()

    def journal_lines(self, home=None):
        data = self.journal_bytes(home)
        return data.split(b"\n")[:-1] if data else []

    def intent_standing(self, home=None):
        return os.path.lexists(
            journal._batch_intent_path(home or self.home))

    def kinds(self, home=None):
        return [entry["entry_kind"]
                for entry in journal.fold(home or self.home)]

    def victim(self, name="victim.txt", text="victim text\n"):
        path = os.path.join(self.tmp.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def read_text(self, path):
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def subprocess_append(self, home, tag):
        code = (
            "import sys\n"
            "sys.path.insert(0, %r)\n"
            "from citeline import journal\n"
            "try:\n"
            "    journal.append_entry(%r, 'audit_record',"
            " {'tag': %r})\n"
            "    print('ok')\n"
            "except journal.JournalError as error:\n"
            "    print(error.token or 'error')\n"
            % (os.path.join(os.path.dirname(__file__), ".."),
               home, tag))
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, timeout=60)
        return result.stdout.strip()


class SpentAuthorizationHeadMovedTests(HomeCase):
    def test_r7_001_spent_answer_survives_head_moving_past(self):
        payload = {"name": "Product 0", "product_id": "p-0"}
        with journal._join_authorization(
                journal._lock_path(self.home),
                "product_registered", payload):
            first = journal.append_entry(
                self.home, "product_registered", payload)
            self.assertEqual(first["sequence"], 1)
            journal.append_entry(
                self.home, "round_named", {"label": "round one"})
            repeat = journal.append_entry(
                self.home, "product_registered", payload)
        self.assertEqual(repeat["sequence"], 1)
        self.assertEqual(repeat["entry_hash"], first["entry_hash"])
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 2)
        self.assertEqual(
            self.kinds(), ["product_registered", "round_named"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class HomeRenameExclusionTests(HomeCase):
    @unittest.expectedFailure
    def test_r7_002_renamed_and_recreated_home_stays_contended(self):
        journal.append_entry(
            self.home, "product_registered",
            {"name": "Product 0", "product_id": "p-0"})
        aside = os.path.join(self.tmp.name, "home-aside")
        with journal._WriteLock(self.home):
            outcome = self.subprocess_append(self.home, "control")
            self.assertEqual(outcome, "WRITE_CONTENDED")
            os.rename(self.home, aside)
            os.makedirs(self.home)
            outcome = self.subprocess_append(self.home, "outside")
            self.assertEqual(outcome, "WRITE_CONTENDED")


class AnchorPostReplaceRemedyTests(HomeCase):
    def test_r7_003_anchor_recording_survives_post_replace_swap(self):
        anchor_dir = os.path.join(self.tmp.name, "anchors")
        os.makedirs(anchor_dir)
        anchor = os.path.join(anchor_dir, "anchor.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        journal.append_entry(
            self.home, "product_registered",
            {"name": "Product 0", "product_id": "p-0"})
        standing_anchor = self.read_text(anchor)
        victim = self.victim()
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

        with mock.patch.object(os, "lstat", swap_lstat):
            with self.assertRaises(journal.JournalError) as caught:
                journal.append_entry(
                    self.home, "audit_record", {"tag": "second"})
        self.assertEqual(caught.exception.token,
                         "JOURNAL_VERIFY_FAILED")
        self.assertTrue(os.path.exists(anchor))
        self.assertFalse(os.path.islink(anchor))
        self.assertEqual(self.read_text(anchor), standing_anchor)
        self.assertEqual(self.read_text(victim), "victim text\n")
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 1)
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        third = journal.append_entry(
            self.home, "audit_record", {"tag": "third"})
        self.assertEqual(third["sequence"], 2)


class PostRejudgementLinkPlantTests(HomeCase):
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

    def test_r7_004_journal_append_judged_at_the_write(self):
        journal.append_entry(
            self.home, "product_registered",
            {"name": "Product 0", "product_id": "p-0"})
        path = journal.journal_path(self.home)
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        with self.plant_on_second_fstat(path, outside):
            with self.assertRaises(journal.JournalError) as caught:
                journal.append_entry(
                    self.home, "audit_record", {"tag": "second"})
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 1)
        with open(outside, "rb") as handle:
            self.assertNotIn(b"second", handle.read())
        os.unlink(outside)
        journal._scan_cache.clear()
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r7_004_intent_write_judged_at_the_write(self):
        intent_path = journal._batch_intent_path(self.home)
        outside = os.path.join(self.tmp.name, "intent-out.json")
        with self.plant_on_second_fstat(intent_path, outside):
            written = journal._write_batch_intent(
                self.home, 0, None, None, 1)
        self.assertFalse(written)
        with open(outside, "rb") as handle:
            self.assertNotIn(b"journal_size", handle.read())


class RecoverySizeStateAtAppendTests(HomeCase):
    def test_r7_005_size_state_judged_as_it_stood_at_the_append(self):
        journal.write_config(self.home, "journal_length = 10\n")
        journal.append_entry(
            self.home, "product_registered",
            {"name": "Product 0", "product_id": "p-0"})
        size_before = len(self.journal_bytes())
        journal.append_entry(
            self.home, "audit_record", {"tag": "partial"})
        journal._write_batch_intent(
            self.home, size_before, None, None, 1)
        filler = os.path.join(self.home, "filler.bin")
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
                               audit_date=audit_date,
                               run_id=run_id)

        with mock.patch.object(journal, "append_entry", wrapper):
            landed = journal.recover_interrupted_batch(self.home)
        self.assertTrue(landed)
        self.assertFalse(self.intent_standing())
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 1)


class LimitMemberConversionTests(HomeCase):
    def long_member(self, digits=5000):
        return "limit_" + "9" * digits

    def crafted_line(self, member):
        entry = {
            "sequence": 1,
            "entry_kind": "limit_raise",
            "form_version": 1,
            "payload": {"limit": member, "raised_value": 5,
                        "run_id": "run-1"},
            "previous_hash": None,
        }
        return journal.canonical_bytes(entry)

    def test_r7_006_stored_long_member_answered_in_vocabulary(self):
        home = os.path.join(self.tmp.name, "crafted")
        os.makedirs(home)
        with open(journal.journal_path(home), "wb") as handle:
            handle.write(self.crafted_line(self.long_member()) + b"\n")
        result = journal.verify_chain(home)
        self.assertFalse(result["passed"])
        self.assertEqual(result["token"], "JOURNAL_VERIFY_FAILED")
        with self.assertRaises(journal.JournalError):
            journal.fold(home)
        target = os.path.join(self.tmp.name, "replayed")
        os.makedirs(target)
        with self.assertRaises(journal.JournalError):
            journal.replay(
                target, [self.crafted_line(self.long_member())])

    def test_r7_006_call_side_long_member_answered_in_vocabulary(self):
        journal.append_entry(
            self.home, "product_registered",
            {"name": "Product 0", "product_id": "p-0"})
        with self.assertRaises(journal.JournalError) as caught:
            journal.append_entry(
                self.home, "limit_raise",
                {"limit": self.long_member(), "raised_value": 5,
                 "run_id": "run-1"})
        self.assertEqual(caught.exception.token, "MALFORMED_CALL")
        with self.assertRaises(ConfigError):
            journal.limit_for_member(self.long_member())

    def test_r7_006_control_member_of_100_digits_in_vocabulary(self):
        with self.assertRaises(ConfigError) as caught:
            journal.limit_for_member(self.long_member(100))
        self.assertEqual(caught.exception.token, "CONFIG_INVALID")


class HomePathAsFileTests(HomeCase):
    def file_home(self):
        path = os.path.join(self.tmp.name, "file-home")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("not a home\n")
        return path

    def test_r7_007_append_answers_in_vocabulary(self):
        home = self.file_home()
        with self.assertRaises(journal.JournalError) as caught:
            journal.append_entry(
                home, "audit_record", {"tag": "x"})
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        self.assertEqual(self.read_text(home), "not a home\n")

    def test_r7_007_write_config_answers_in_vocabulary(self):
        home = self.file_home()
        with self.assertRaises(ConfigError) as caught:
            journal.write_config(home, "journal_length = 5\n")
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(caught.exception.row, "X-4")
        self.assertEqual(self.read_text(home), "not a home\n")

    def test_r7_007_replay_answers_in_vocabulary(self):
        source = os.path.join(self.tmp.name, "source")
        os.makedirs(source)
        journal.append_entry(source, "audit_record", {"tag": "one"})
        with open(journal.journal_path(source), "rb") as handle:
            lines = handle.read().split(b"\n")[:-1]
        home = self.file_home()
        with self.assertRaises(journal.JournalError) as caught:
            journal.replay(home, lines)
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(self.read_text(home), "not a home\n")


if __name__ == "__main__":
    unittest.main()
