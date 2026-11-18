"""Journal family.

Each test pins one settled rule from the findings the settled record on the behaviour the register and
the settled disposition state. Homes are scratch homes
under a temporary directory. No test here touches a
standing test item or a governed ground."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from citeline import journal, registry, service
from citeline.errors import ConfigError


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


class JoinAuthorizationBindingTests(HomeCase):
    def test_r6_001_batch_second_call_cannot_spend_authorization(self):
        sink = []
        state = {"done": False}
        real_append = journal.append_entry

        def wrapper(home, kind, payload, audit_date=None,
                    run_id=None):
            if not state["done"]:
                state["done"] = True
                sink.append(real_append(home, kind, payload))
            return real_append(home, kind, payload,
                               audit_date=audit_date,
                               run_id=run_id)

        with mock.patch.object(journal, "append_entry", wrapper):
            appended = journal.append_entries_atomic(
                self.home,
                [("audit_record", {"tag": "one"}),
                 ("audit_record", {"tag": "two"})])
        self.assertEqual(
            [entry["sequence"] for entry in appended], [1, 2])
        self.assertEqual(sink[0]["sequence"], 1)
        self.assertEqual(appended[0]["entry_hash"],
                         sink[0]["entry_hash"])
        journal._scan_cache.clear()
        self.assertEqual(self.kinds(),
                         ["audit_record", "audit_record"])
        self.assertEqual(len(self.journal_lines()), 2)
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r6_001_payload_hook_cannot_spend_authorization(self):
        sink = []
        state = {"done": False}
        real_append = journal.append_entry

        class HookPayload(dict):
            def values(self):
                if not state["done"]:
                    state["done"] = True
                    try:
                        real_append(self_home, "audit_record",
                                    self)
                        sink.append("ok")
                    except journal.JournalError as error:
                        sink.append(error.token)
                return super().values()

        self_home = self.home
        payload = HookPayload({"tag": "hooked"})
        appended = journal.append_entries_atomic(
            self.home,
            [("audit_record", payload),
             ("audit_record", {"tag": "two"})])
        self.assertEqual(sink, ["WRITE_CONTENDED"])
        self.assertEqual(
            [entry["sequence"] for entry in appended], [1, 2])
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 2)
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r6_001_registry_cycle_append_judged(self):
        sink = []
        state = {"done": False}
        real_append = journal.append_entry

        def wrapper(home, kind, payload, audit_date=None,
                    run_id=None):
            if not state["done"]:
                state["done"] = True
                sink.append(real_append(home, kind, payload))
            return real_append(home, kind, payload,
                               audit_date=audit_date,
                               run_id=run_id)

        payload = {"product_id": "p-1", "name": "Reg"}
        with mock.patch.object(journal, "append_entry", wrapper):
            with registry._append_guard(self.home):
                entry = registry._append_guarded(
                    self.home, "registry_change", payload, None)
        self.assertEqual(entry["sequence"], 1)
        self.assertEqual(sink[0]["sequence"], 1)
        journal._scan_cache.clear()
        self.assertEqual(self.kinds(), ["registry_change"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r6_001_guide_store_append_judged(self):
        basis = {"run_id": "run-1", "product_id": "p-0"}
        journal.append_entry(self.home, "audit_record", basis)
        sink = []
        state = {"done": False}
        real_append = journal.append_entry

        def wrapper(home, kind, payload, audit_date=None,
                    run_id=None):
            if not state["done"] and kind == "guide_record":
                state["done"] = True
                sink.append(real_append(home, kind, payload))
            return real_append(home, kind, payload,
                               audit_date=audit_date,
                               run_id=run_id)

        draft = {"run_id": "run-1", "product_id": "p-0",
                 "guide": "text"}
        with mock.patch.object(journal, "append_entry", wrapper):
            entry = service._store_guide_draft(
                self.home, draft, "run-1", basis, None)
        self.assertEqual(entry["entry_kind"], "guide_record")
        self.assertEqual(sink[0]["sequence"], entry["sequence"])
        journal._scan_cache.clear()
        self.assertEqual(
            self.kinds(), ["audit_record", "guide_record"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])


@unittest.skipUnless(hasattr(os, "fork"), "fork is unavailable")
class ForkLockExitTests(HomeCase):
    def test_r6_002_forked_child_exit_keeps_parent_lock(self):
        self.append_product("P0", "p-0")
        with journal._WriteLock(self.home) as lock:
            pid = os.fork()
            if pid == 0:
                try:
                    lock.__exit__(None, None, None)
                finally:
                    os._exit(0)
            os.waitpid(pid, 0)
            outcome = self.subprocess_append(self.home, "outside")
            self.assertEqual(outcome, "WRITE_CONTENDED")
            entry = journal.append_entry(
                self.home, "audit_record", {"tag": "parent"})
            self.assertEqual(entry["sequence"], 2)
        journal._scan_cache.clear()
        self.assertEqual(
            self.kinds(), ["product_registered", "audit_record"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class LockFileUnlinkTests(HomeCase):
    def test_r6_003_unlink_during_hold_mints_no_second_lock(self):
        self.append_product("P0", "p-0")
        with journal._WriteLock(self.home):
            os.unlink(journal._lock_path(self.home))
            outcome = self.subprocess_append(self.home, "outside")
            self.assertEqual(outcome, "WRITE_CONTENDED")
        entry = journal.append_entry(
            self.home, "audit_record", {"tag": "after"})
        self.assertEqual(entry["sequence"], 2)
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class TemporaryReplaceTests(HomeCase):
    def swap_on_replace(self, victim, marker):
        real_replace = os.replace
        state = {"done": False}

        def wrapper(src, dst):
            if not state["done"] and marker in os.fspath(src):
                state["done"] = True
                os.unlink(src)
                os.symlink(victim, src)
            return real_replace(src, dst)

        return mock.patch.object(os, "replace", wrapper)

    def test_r6_004_anchor_temporary_judged_at_replace(self):
        anchor_dir = os.path.join(self.tmp.name, "anchors")
        os.makedirs(anchor_dir)
        anchor = os.path.join(anchor_dir, "anchor.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        victim = self.victim()
        with self.swap_on_replace(victim, ".tmp-"):
            with self.assertRaises(journal.JournalError):
                self.append_product("P0", "p-0")
        self.assertFalse(os.path.islink(anchor))
        self.assertFalse(os.path.exists(anchor))
        self.assertEqual(self.read_text(victim), "victim text\n")
        self.assertEqual(self.journal_lines(), [])
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r6_004_replay_temporary_judged_at_replace(self):
        source = os.path.join(self.tmp.name, "source")
        os.makedirs(source)
        journal.append_entry(
            source, "audit_record", {"tag": "one"})
        with open(journal.journal_path(source), "rb") as handle:
            lines = handle.read().split(b"\n")[:-1]
        target = os.path.join(self.tmp.name, "target")
        os.makedirs(target)
        victim = self.victim()
        with self.swap_on_replace(victim, ".replay-"):
            with self.assertRaises(journal.JournalError):
                journal.replay(target, lines)
        path = journal.journal_path(target)
        self.assertFalse(os.path.islink(path))
        self.assertEqual(self.read_text(victim), "victim text\n")

    def test_r6_004_anchor_restore_temporary_judged(self):
        anchor_dir = os.path.join(self.tmp.name, "anchors")
        os.makedirs(anchor_dir)
        anchor = os.path.join(anchor_dir, "anchor.txt")
        with open(anchor, "w", encoding="utf-8") as handle:
            handle.write("old 1\n")
        victim = self.victim()
        with self.swap_on_replace(victim, ".tmp-"):
            with self.assertRaises(OSError):
                journal._restore_anchor_bytes(anchor, b"new 2\n")
        self.assertFalse(os.path.islink(anchor))
        self.assertFalse(os.path.exists(anchor))
        self.assertEqual(self.read_text(victim), "victim text\n")


class IntentReaderLinkDirectionTests(HomeCase):
    def seed_partial(self):
        self.append_product("P0", "p-0")
        size_before = len(self.journal_bytes())
        journal.append_entry(
            self.home, "audit_record", {"tag": "partial"})
        journal._write_batch_intent(
            self.home, size_before, None, None, 1)
        return size_before

    def test_r6_005_genuine_record_linked_outward_recovers(self):
        self.seed_partial()
        outside = os.path.join(self.tmp.name, "record-copy.json")
        os.link(journal._batch_intent_path(self.home), outside)
        self.assertTrue(journal.recover_interrupted_batch(self.home))
        self.assertFalse(self.intent_standing())
        self.assertTrue(os.path.exists(outside))
        journal._scan_cache.clear()
        self.assertEqual(
            self.kinds(), ["product_registered", "failure_record"])
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_r6_005_victim_linked_to_intent_path_is_debris(self):
        self.append_product("P0", "p-0")
        victim = self.victim()
        os.link(victim, journal._batch_intent_path(self.home))
        self.assertFalse(journal.recover_interrupted_batch(self.home))
        self.assertFalse(self.intent_standing())
        self.assertEqual(self.read_text(victim), "victim text\n")
        journal._scan_cache.clear()
        self.assertEqual(self.kinds(), ["product_registered"])


class LinkCountRejudgementTests(HomeCase):
    def plant_on_fstat(self, target, outside):
        real_fstat = os.fstat
        state = {"done": False}

        def wrapper(fd):
            info = real_fstat(fd)
            if not state["done"]:
                try:
                    link = os.readlink("/proc/self/fd/%d" % fd)
                except OSError:
                    link = None
                if link == target:
                    state["done"] = True
                    os.link(target, outside)
            return info

        return mock.patch.object(os, "fstat", wrapper)

    def test_r6_006_intent_write_rejudged_before_write(self):
        intent_path = journal._batch_intent_path(self.home)
        outside = os.path.join(self.tmp.name, "intent-out.json")
        with self.plant_on_fstat(intent_path, outside):
            written = journal._write_batch_intent(
                self.home, 0, None, None, 1)
        self.assertFalse(written)
        with open(outside, "rb") as handle:
            self.assertNotIn(b"journal_size", handle.read())

    def test_r6_006_journal_append_rejudged_before_write(self):
        self.append_product("P0", "p-0")
        path = journal.journal_path(self.home)
        outside = os.path.join(self.tmp.name, "journal-out.jsonl")
        with self.plant_on_fstat(path, outside):
            with self.assertRaises(journal.JournalError) as caught:
                journal.append_entry(
                    self.home, "audit_record", {"tag": "second"})
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")
        self.assertEqual(len(self.journal_lines()), 1)
        with open(outside, "rb") as handle:
            self.assertNotIn(b"second", handle.read())


class RecoveryMixedCapTests(HomeCase):
    def test_r6_007_mixed_cap_failure_stands_as_landed(self):
        journal.write_config(self.home, "journal_length = 10\n")
        self.append_product("P0", "p-0")
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
            return real_append(home, kind, payload,
                               audit_date=audit_date,
                               run_id=run_id)

        with mock.patch.object(journal, "append_entry", wrapper):
            landed = journal.recover_interrupted_batch(self.home)
        self.assertTrue(landed)
        self.assertFalse(self.intent_standing())
        self.assertEqual(len(self.journal_lines()), 1)


class ReaderLinkDisciplineTests(HomeCase):
    def test_r6_048_config_reader_refuses_a_symlink(self):
        outside = self.victim(
            "outside-config.txt", "journal_length = 5\n")
        os.symlink(outside, journal.config_path(self.home))
        with self.assertRaises(ConfigError) as caught:
            journal.effective_limits(self.home)
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")

    def test_r6_048_config_reader_refuses_a_hard_link(self):
        outside = self.victim(
            "outside-config.txt", "journal_length = 5\n")
        os.link(outside, journal.config_path(self.home))
        with self.assertRaises(ConfigError) as caught:
            journal.effective_limits(self.home)
        self.assertEqual(caught.exception.token,
                         "SUPPLIED_PATH_UNSAFE")

    def test_r6_048_journal_reader_refuses_a_symlink(self):
        self.append_product("P0", "p-0")
        other = os.path.join(self.tmp.name, "other")
        os.makedirs(other)
        journal.append_entry(other, "audit_record", {"tag": "x"})
        home2 = os.path.join(self.tmp.name, "home2")
        os.makedirs(home2)
        os.symlink(journal.journal_path(other),
                   journal.journal_path(home2))
        self.assertFalse(journal.verify_chain(home2)["passed"])
        with self.assertRaises(journal.JournalError):
            journal.fold(home2)


if __name__ == "__main__":
    unittest.main()
