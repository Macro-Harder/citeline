"""Journal family.

Each test pins one register entry from design/audit/
the register paper on the behaviour the register and
the round 5 disposition state. Homes are scratch
homes under a temporary directory. No test here
touches a standing test item or a governed ground."""

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from citeline import journal


def product_payload(name="Product 0", product_id="p-0"):
    return {"name": name, "product_id": product_id}


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


class BatchIntentOpenRaceTests(HomeCase):
    def test_r5_001_link_landing_after_the_check_is_not_followed(self):
        outside = os.path.join(self.tmp.name, "outside.json")
        intent_path = journal._batch_intent_path(self.home)
        real_islink = os.path.islink

        def wrapper(path):
            answer = real_islink(path)
            if os.fspath(path) == intent_path and not answer:
                os.symlink(outside, intent_path)
            return answer

        with mock.patch.object(os.path, "islink", wrapper):
            appended = journal.append_entries_atomic(
                self.home,
                [("audit_record", {"tag": "one"})])
        self.assertEqual([entry["sequence"] for entry in appended],
                         [1])
        self.assertFalse(os.path.exists(outside))
        self.assertFalse(self.intent_standing())
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class BatchIntentDuplicateKeyTests(HomeCase):
    def test_r5_002_duplicated_key_record_is_refused_as_debris(self):
        self.append_product("P0", "p-0")
        size_before = len(self.journal_bytes())
        journal.append_entry(
            self.home, "audit_record", {"tag": "partial"})
        victim = os.path.join(self.tmp.name, "victim-anchor.txt")
        raw = (
            '{"journal_size": %d, "anchor_path": %s, '
            '"anchor_path": null, "anchor_bytes": null, '
            '"count": 99, "count": 1}'
            % (size_before, json.dumps(victim)))
        with open(journal._batch_intent_path(self.home), "w",
                  encoding="utf-8") as handle:
            handle.write(raw)
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        self.assertFalse(self.intent_standing())
        self.assertFalse(os.path.exists(victim))
        self.assertEqual(len(self.journal_lines()), 2)
        self.assertEqual(self.kinds(),
                         ["product_registered", "audit_record"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class BatchIntentFifoTests(HomeCase):
    def run_script(self, script):
        return subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=20)

    def test_r5_003_fifo_at_intent_path_does_not_wedge_recovery(self):
        self.append_product("P0", "p-0")
        os.mkfifo(journal._batch_intent_path(self.home))
        product_dir = os.path.join(
            os.path.dirname(__file__), "..")
        script = (
            "import sys\n"
            "sys.path.insert(0, %r)\n"
            "from citeline import journal\n"
            "print(journal.recover_interrupted_batch(%r))\n"
            % (product_dir, self.home))
        try:
            result = self.run_script(script)
        except subprocess.TimeoutExpired:
            self.fail("recovery wedged on a FIFO at the intent path")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("False", result.stdout)
        self.assertFalse(self.intent_standing())
        entry = self.append_product("P1", "p-1")
        self.assertEqual(entry["sequence"], 2)

    def test_r5_003_fifo_at_intent_path_does_not_wedge_the_write(self):
        os.mkfifo(journal._batch_intent_path(self.home))
        product_dir = os.path.join(
            os.path.dirname(__file__), "..")
        script = (
            "import sys\n"
            "sys.path.insert(0, %r)\n"
            "from citeline import journal\n"
            "print(journal._write_batch_intent(%r, 0, None, None, 1))\n"
            % (product_dir, self.home))
        try:
            result = self.run_script(script)
        except subprocess.TimeoutExpired:
            self.fail("the intent write wedged on a FIFO")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("False", result.stdout)


class RecoveryHomeSizeCapTests(HomeCase):
    def test_r5_004_home_size_cap_in_flight_is_no_deferral(self):
        self.append_product("P0", "p-0")
        size_before = len(self.journal_bytes())
        journal.append_entry(
            self.home, "audit_record", {"tag": "partial"})
        journal._write_batch_intent(
            self.home, size_before, None, None, 1)
        # The size state stands staged by a product journal
        # temporary left standing in the home: Step 19 item
        # R19-022 charges the home size cap with product
        # created files only, so a foreign file no longer
        # stages this state, and the temporary form this
        # assertion's scenario needs stands in its place.
        filler = os.path.join(self.home, "journal.jsonl.tmp-filler")
        with open(filler, "wb") as handle:
            handle.truncate(1024 ** 3)
        self.assertTrue(journal.recover_interrupted_batch(self.home))
        self.assertFalse(self.intent_standing())
        self.assertEqual(len(self.journal_lines()), 1)
        self.assertEqual(self.kinds(), ["product_registered"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r5_004_journal_length_deferral_still_holds(self):
        journal.write_config(self.home, "journal_length = 3\n")
        for index in range(3):
            self.append_product("P%d" % index, "p-%d" % index)
        journal._write_batch_intent(
            self.home, len(self.journal_bytes()), None, None, 1)
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        self.assertTrue(self.intent_standing())
        self.assertEqual(len(self.journal_lines()), 3)


class HomeFileLinkDisciplineTests(HomeCase):
    def test_r5_061_journal_symlink_is_not_written_through(self):
        victim = self.victim()
        os.symlink(victim, journal.journal_path(self.home))
        with self.assertRaises(journal.JournalError) as caught:
            self.append_product("P0", "p-0")
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(self.read_text(victim), "victim text\n")

    def test_r5_061_journal_hard_link_is_not_written_through(self):
        victim = self.victim()
        os.link(victim, journal.journal_path(self.home))
        with self.assertRaises(journal.JournalError) as caught:
            self.append_product("P0", "p-0")
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(self.read_text(victim), "victim text\n")

    def test_r5_061_config_symlink_is_not_written_through(self):
        victim = self.victim()
        os.symlink(victim, journal.config_path(self.home))
        with self.assertRaises(journal.ConfigError) as caught:
            journal.write_config(self.home, "journal_length = 5\n")
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(self.read_text(victim), "victim text\n")

    def test_r5_061_config_hard_link_is_not_written_through(self):
        victim = self.victim()
        os.link(victim, journal.config_path(self.home))
        with self.assertRaises(journal.ConfigError) as caught:
            journal.write_config(self.home, "journal_length = 5\n")
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(self.read_text(victim), "victim text\n")

    def test_r5_061_lock_symlink_is_not_written_through(self):
        victim = self.victim()
        os.symlink(victim, os.path.join(
            self.home, journal.LOCK_FILENAME))
        with self.assertRaises(journal.JournalError) as caught:
            self.append_product("P0", "p-0")
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(self.read_text(victim), "victim text\n")

    def test_r5_061_lock_hard_link_is_not_written_through(self):
        victim = self.victim()
        os.link(victim, os.path.join(
            self.home, journal.LOCK_FILENAME))
        with self.assertRaises(journal.JournalError) as caught:
            self.append_product("P0", "p-0")
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(self.read_text(victim), "victim text\n")

    def test_r5_061_restore_does_not_truncate_through_a_link(self):
        victim = self.victim(text="victim text standing long\n")
        path = journal.journal_path(self.home)
        os.symlink(victim, path)
        journal._restore_journal_size(path, 3)
        self.assertEqual(self.read_text(victim),
                         "victim text standing long\n")

    def test_r5_061_replay_does_not_replace_a_journal_link(self):
        victim = self.victim(text="")
        os.symlink(victim, journal.journal_path(self.home))
        line = journal.canonical_bytes({
            "sequence": 1, "entry_kind": "product_registered",
            "form_version": 1, "payload": product_payload(),
            "previous_hash": None})
        with self.assertRaises(journal.JournalError) as caught:
            journal.replay(self.home, [line])
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertTrue(os.path.islink(
            journal.journal_path(self.home)))
        self.assertEqual(self.read_text(victim), "")

    def test_r5_061_ordinary_home_files_still_work(self):
        journal.write_config(self.home, "journal_length = 5\n")
        journal.write_config(self.home, "journal_length = 6\n")
        entry = self.append_product("P0", "p-0")
        self.assertEqual(entry["sequence"], 1)
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class BatchIntentHardLinkTests(HomeCase):
    def test_r5_062_hard_link_at_intent_path_is_refused(self):
        victim = self.victim()
        os.link(victim, journal._batch_intent_path(self.home))
        self.assertFalse(journal._write_batch_intent(
            self.home, 0, None, None, 1))
        self.assertEqual(self.read_text(victim), "victim text\n")

    def test_r5_062_batch_over_hard_link_intent_spares_the_victim(self):
        # Control at the batch route: the recovery at the
        # route head meets the hard linked path as debris
        # and clears the link name without reading or
        # writing the victim, and the batch then lands on
        # a fresh intent file of its own. The pin for the
        # entry itself is the direct write test above.
        victim = self.victim()
        os.link(victim, journal._batch_intent_path(self.home))
        appended = journal.append_entries_atomic(
            self.home, [("audit_record", {"tag": "one"})])
        self.assertEqual([entry["sequence"] for entry in appended],
                         [1])
        self.assertEqual(self.read_text(victim), "victim text\n")
        self.assertFalse(self.intent_standing())
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class AnchorTemporaryTests(HomeCase):
    def test_r5_063_planted_anchor_temporary_link_is_not_moved(self):
        anchor_dir = os.path.join(self.tmp.name, "anchors")
        os.makedirs(anchor_dir)
        anchor = os.path.join(anchor_dir, "anchor.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        victim = self.victim()
        planted = os.path.join(
            anchor_dir,
            "anchor.txt.tmp-1-%d" % os.getpid())
        os.symlink(victim, planted)
        entry = self.append_product("P0", "p-0")
        self.assertEqual(entry["sequence"], 1)
        self.assertEqual(self.read_text(victim), "victim text\n")
        self.assertFalse(os.path.islink(anchor))
        self.assertTrue(os.path.islink(planted))
        lines = self.journal_lines()
        self.assertEqual(
            self.read_text(anchor),
            "%s 1\n" % hashlib.sha256(lines[0]).hexdigest())
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class JoinPermitPrologueTests(HomeCase):
    def test_r5_068_ambient_append_at_batch_append_entry_is_contended(self):
        sink = []
        state = {"done": False}
        real_append = journal.append_entry

        def wrapper(home, kind, payload, audit_date=None, run_id=None):
            if not state["done"]:
                state["done"] = True
                try:
                    real_append(home, "audit_record",
                                {"tag": "ambient"})
                    sink.append(("ok", None))
                except journal.JournalError as error:
                    sink.append(("error", error.token))
            return real_append(home, kind, payload,
                               audit_date=audit_date, run_id=run_id)

        with mock.patch.object(journal, "append_entry", wrapper):
            appended = journal.append_entries_atomic(
                self.home,
                [("product_registered", product_payload("P0", "p-0")),
                 ("product_registered", product_payload("P1", "p-1"))])
        self.assertEqual(sink, [("error", "WRITE_CONTENDED")])
        self.assertEqual([entry["sequence"] for entry in appended],
                         [1, 2])
        journal._scan_cache.clear()
        self.assertEqual(self.kinds(),
                         ["product_registered", "product_registered"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r5_068_ambient_append_at_recovery_append_entry_is_contended(self):
        self.append_product("P0", "p-0")
        size_before = len(self.journal_bytes())
        journal.append_entry(
            self.home, "audit_record", {"tag": "partial"})
        journal._write_batch_intent(
            self.home, size_before, None, None, 1)
        sink = []
        state = {"done": False}
        real_append = journal.append_entry

        def wrapper(home, kind, payload, audit_date=None, run_id=None):
            if not state["done"] \
                    and payload.get("operation") == "recovery":
                state["done"] = True
                try:
                    real_append(home, "audit_record",
                                {"tag": "ambient"})
                    sink.append(("ok", None))
                except journal.JournalError as error:
                    sink.append(("error", error.token))
            return real_append(home, kind, payload,
                               audit_date=audit_date, run_id=run_id)

        with mock.patch.object(journal, "append_entry", wrapper):
            self.assertTrue(
                journal.recover_interrupted_batch(self.home))
        self.assertEqual(sink, [("error", "WRITE_CONTENDED")])
        journal._scan_cache.clear()
        self.assertEqual(self.kinds(),
                         ["product_registered", "failure_record"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r5_068_batch_and_recovery_appends_still_land(self):
        appended = journal.append_entries_atomic(
            self.home,
            [("product_registered", product_payload("P0", "p-0"))])
        self.assertEqual([entry["sequence"] for entry in appended],
                         [1])
        self.assertTrue(journal.verify_chain(self.home)["passed"])


@unittest.skipUnless(hasattr(os, "fork"), "fork is unavailable")
class ForkInsideContainerHoldTests(HomeCase):
    def test_r5_069_forked_child_is_contended_inside_a_container_hold(self):
        self.append_product("P0", "p-0")
        read_fd, write_fd = os.pipe()
        with journal._WriteLock(self.home):
            pid = os.fork()
            if pid == 0:
                os.close(read_fd)
                try:
                    journal.append_entry(
                        self.home, "audit_record",
                        {"tag": "child"})
                    outcome = b"ok"
                except journal.JournalError as error:
                    outcome = (error.token or "error").encode("utf-8")
                except Exception as error:
                    outcome = ("raw:%s" % type(error).__name__).encode(
                        "utf-8")
                os.write(write_fd, outcome)
                os._exit(0)
            os.close(write_fd)
            _done, status, _usage = os.wait4(pid, 0)
            outcome = b""
            while True:
                chunk = os.read(read_fd, 4096)
                if not chunk:
                    break
                outcome += chunk
            os.close(read_fd)
            self.assertEqual(outcome, b"WRITE_CONTENDED")
            self.assertEqual(os.waitstatus_to_exitcode(status), 0)
            entry = journal.append_entry(
                self.home, "audit_record", {"tag": "parent"})
            self.assertEqual(entry["sequence"], 2)
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 2)
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r5_069_child_forked_under_no_hold_still_appends(self):
        read_fd, write_fd = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(read_fd)
            try:
                entry = journal.append_entry(
                    self.home, "product_registered",
                    product_payload("P0", "p-0"))
                outcome = ("seq:%d" % entry["sequence"]).encode("utf-8")
            except Exception as error:
                outcome = ("raw:%s" % type(error).__name__).encode(
                    "utf-8")
            os.write(write_fd, outcome)
            os._exit(0)
        os.close(write_fd)
        _done, status, _usage = os.wait4(pid, 0)
        outcome = b""
        while True:
            chunk = os.read(read_fd, 4096)
            if not chunk:
                break
            outcome += chunk
        os.close(read_fd)
        self.assertEqual(outcome, b"seq:1")
        self.assertEqual(os.waitstatus_to_exitcode(status), 0)


if __name__ == "__main__":
    unittest.main()
