"""Journal family.

Each test pins one register entry from design/audit/ the
register paper on the behaviour the register states. Homes
are scratch homes under a temporary directory. No test
here touches a standing test item or a governed ground."""

import fcntl
import hashlib
import os
import subprocess
import sys
import tempfile
import threading
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


class HomeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def append_product(self, name="Product 0", product_id="p-0", **kw):
        return journal.append_entry(
            self.home, "product_registered",
            product_payload(name, product_id), **kw)

    def journal_bytes(self):
        path = journal.journal_path(self.home)
        if not os.path.exists(path):
            return b""
        with open(path, "rb") as handle:
            return handle.read()

    def journal_lines(self):
        data = self.journal_bytes()
        return data.split(b"\n")[:-1] if data else []

    def write_raw_lines(self, lines, home=None):
        home = home or self.home
        with open(journal.journal_path(home), "wb") as handle:
            for line in lines:
                handle.write(line + b"\n")
        journal._scan_cache.clear()

    def valid_lines(self, other_name="other"):
        other = os.path.join(self.tmp.name, other_name)
        os.makedirs(other)
        journal.append_entry(other, "product_registered",
                             product_payload("Other 0", "p-o0"))
        journal.append_entry(other, "product_registered",
                             product_payload("Other 1", "p-o1"))
        with open(journal.journal_path(other), "rb") as handle:
            return handle.read().split(b"\n")[:-1]

    def hold_lock(self):
        lock_path = os.path.join(self.home, ".citeline-write.lock")
        handle = open(lock_path, "a+")
        self.addCleanup(handle.close)
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle


class LockReentryTests(HomeCase):
    def test_r2_001_threads_in_one_process_contend(self):
        barrier = threading.Barrier(4)
        outcomes = []
        outcomes_lock = threading.Lock()

        def worker(tag):
            barrier.wait()
            for index in range(10):
                try:
                    entry = journal.append_entry(
                        self.home, "audit_record",
                        {"tag": tag, "index": index})
                    with outcomes_lock:
                        outcomes.append(("ok", entry["sequence"]))
                except journal.JournalError as error:
                    with outcomes_lock:
                        outcomes.append(("error", error.token))

        threads = [threading.Thread(target=worker, args=(n,))
                   for n in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        successes = sorted(seq for kind, seq in outcomes if kind == "ok")
        failures = [token for kind, token in outcomes if kind == "error"]
        self.assertEqual(len(outcomes), 40)
        for token in failures:
            self.assertEqual(token, "WRITE_CONTENDED")
        self.assertEqual(successes,
                         list(range(1, len(successes) + 1)))
        journal._scan_cache.clear()
        result = journal.verify_chain(self.home)
        self.assertTrue(result["passed"])
        self.assertEqual(result["entry_count"], len(successes))

    def test_r2_001_batch_rollback_erases_no_acknowledged_entry(self):
        self.append_product("Product 0", "p-0")
        original_append = journal.append_entry
        state = {"calls": 0, "thread_outcome": None}

        def concurrent_attempt():
            try:
                original_append(self.home, "failure_record",
                                {"operation": "concurrent"})
                state["thread_outcome"] = ("ok", None)
            except journal.JournalError as error:
                state["thread_outcome"] = ("error", error.token)

        def wrapper(home, kind, payload, audit_date=None, run_id=None):
            state["calls"] += 1
            if state["calls"] == 2:
                thread = threading.Thread(target=concurrent_attempt)
                thread.start()
                thread.join()
            return original_append(home, kind, payload,
                                   audit_date=audit_date, run_id=run_id)

        batch = [("audit_record", {"tag": "batch first"}),
                 ("correction", {"supersedes_sequence": 999,
                                 "corrected_record": {"x": 1}})]
        with mock.patch.object(journal, "append_entry", wrapper):
            with self.assertRaises(journal.JournalError):
                journal.append_entries_atomic(self.home, batch)
        self.assertIsNotNone(state["thread_outcome"])
        self.assertEqual(state["thread_outcome"],
                         ("error", "WRITE_CONTENDED"))
        journal._scan_cache.clear()
        self.assertEqual(len(self.journal_lines()), 1)
        self.assertTrue(journal.verify_chain(self.home)["passed"])


class SuppliedChainValidationTests(HomeCase):
    def chain_with_second(self, kind, payload):
        first = crafted_line("product_registered",
                             product_payload("P", "p-0"), 1, None)
        second = crafted_line(
            kind, payload, 2, hashlib.sha256(first).hexdigest())
        return [first, second]

    def test_r2_002_out_of_range_raise_does_not_verify(self):
        for value in (999999999, 0, -50):
            home = os.path.join(self.tmp.name, "h-%s" % value)
            os.makedirs(home)
            lines = self.chain_with_second(
                "limit_raise",
                {"limit": "limit_39", "raised_value": value,
                 "run_id": "runX"})
            self.write_raw_lines(lines, home=home)
            result = journal.verify_chain(home)
            self.assertFalse(result["passed"], msg=repr(value))
            with self.assertRaises(journal.JournalError,
                                   msg=repr(value)):
                journal.effective_limits(home, run_id="runX")

    def test_r2_002_out_of_range_raise_refused_at_replay(self):
        lines = self.chain_with_second(
            "limit_raise",
            {"limit": "limit_39", "raised_value": 999999999,
             "run_id": "runX"})
        with self.assertRaises(journal.JournalError):
            journal.replay(self.home, lines)
        self.assertFalse(os.path.exists(journal.journal_path(self.home)))

    def test_r2_002_raise_with_non_integer_value_does_not_verify(self):
        for value in (True, "999999"):
            home = os.path.join(self.tmp.name, "h-type-%s" % type(value).__name__)
            os.makedirs(home)
            lines = self.chain_with_second(
                "limit_raise",
                {"limit": "limit_39", "raised_value": value,
                 "run_id": "runX"})
            self.write_raw_lines(lines, home=home)
            self.assertFalse(journal.verify_chain(home)["passed"],
                             msg=repr(value))

    def test_r2_002_correction_form_does_not_verify(self):
        lines = self.chain_with_second(
            "correction",
            {"supersedes_sequence": True,
             "corrected_record": "a plain string"})
        self.write_raw_lines(lines)
        self.assertFalse(journal.verify_chain(self.home)["passed"])
        other = os.path.join(self.tmp.name, "replay-home")
        os.makedirs(other)
        with self.assertRaises(journal.JournalError):
            journal.replay(other, lines)
        self.assertFalse(os.path.exists(journal.journal_path(other)))

    def test_r2_002_valid_supplied_raise_and_correction_still_verify(self):
        lines = self.chain_with_second(
            "limit_raise",
            {"limit": "limit_39", "raised_value": 110000,
             "run_id": "run-1"})
        self.write_raw_lines(lines)
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        limits = journal.effective_limits(self.home, run_id="run-1")
        self.assertEqual(limits["journal_length"]["value"], 110000)
        self.assertEqual(limits["journal_length"]["source"], "raise")
        home2 = os.path.join(self.tmp.name, "h-corr")
        os.makedirs(home2)
        lines2 = self.chain_with_second(
            "correction",
            {"supersedes_sequence": 1,
             "corrected_record": product_payload("New Name", "p-0")})
        self.write_raw_lines(lines2, home=home2)
        self.assertTrue(journal.verify_chain(home2)["passed"])


class PlausiblePrefixTests(HomeCase):
    def test_r2_003_ascii_garbage_tail_not_hidden_by_lock_holder(self):
        for tail in (b"NOT A PREFIX OF ANY ENTRY",
                     b"12345 garbage ,,,,"):
            home = os.path.join(
                self.tmp.name, "h-%d" % len(tail))
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

    def test_r2_003_plausible_partial_tail_still_ignored(self):
        self.append_product("Product 0", "p-0")
        with open(journal.journal_path(self.home), "ab") as handle:
            handle.write(b'{"entry_kind":"round_named","form_vers')
        journal._scan_cache.clear()
        self.hold_lock()
        result = journal.verify_chain(self.home)
        self.assertTrue(result["passed"])
        self.assertEqual(result["entry_count"], 1)


class AnchorReaderTests(HomeCase):
    def anchored_home(self, count=2):
        anchor = os.path.join(self.tmp.name, "anchor.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        for index in range(count):
            self.append_product("Product %d" % index, "p-%d" % index)
        return anchor

    def head_hash(self, position=1):
        return hashlib.sha256(
            self.journal_lines()[position - 1]).hexdigest()

    def test_r2_004_huge_digit_sequence_does_not_crash(self):
        anchor = self.anchored_home(2)
        with open(anchor, "w") as handle:
            handle.write("%s %s\n" % (self.head_hash(2), "9" * 5000))
        journal._scan_cache.clear()
        state = journal.status_snapshot(self.home)
        # A recording whose sequence does not parse stands
        # malformed, and a malformed anchor reports the torn
        # form: Step 19 item R19-035 supersedes the divergent
        # form this assertion pinned before that cure.
        self.assertEqual(state["anchor"]["agreement"], "torn")
        # Restated at Step 20 under delegated decision 1
        # (register item R19-033, fix paper
        # step-20-fix-05-journal-status): a malformed
        # anchor no longer bars the append. The append
        # proceeds, reports the torn disagreement in its
        # result, and rewrites the anchor to matching. The
        # no crash limb above stands as it stood.
        result = self.append_product("Product 9", "p-9")
        self.assertEqual(
            result["anchor_disagreement"]["agreement"], "torn")
        self.assertEqual(
            journal.status_snapshot(self.home)["anchor"]["agreement"],
            "matching")

    def test_r2_004_signed_and_padded_sequence_forms_are_not_matching(self):
        for token in ("+2", "002"):
            home = os.path.join(self.tmp.name, "h-%s" % token)
            os.makedirs(home)
            anchor = os.path.join(self.tmp.name,
                                  "anchor-%s" % token.replace("+", "plus"))
            journal.write_config(home, "anchor_path = %s\n" % anchor)
            for index in range(2):
                journal.append_entry(
                    home, "product_registered",
                    product_payload("P%d" % index, "p-%d" % index))
            with open(journal.journal_path(home), "rb") as handle:
                lines = handle.read().split(b"\n")[:-1]
            head2 = hashlib.sha256(lines[1]).hexdigest()
            with open(anchor, "w") as handle:
                handle.write("%s %s\n" % (head2, token))
            journal._scan_cache.clear()
            state = journal.status_snapshot(home)
            # A sequence in a signed or padded form does not
            # parse as a recording, so the anchor stands
            # malformed and reports the torn form: Step 19
            # item R19-035 supersedes the divergent form this
            # assertion pinned before that cure.
            self.assertEqual(state["anchor"]["agreement"], "torn",
                             msg=token)
            # Restated at Step 20 under delegated decision
            # 1 (R19-033): a malformed anchor no longer bars
            # the append; the append proceeds, reports the
            # torn disagreement, and rewrites the anchor.
            result = journal.append_entry(
                home, "product_registered",
                product_payload("P9", "p-9"))
            self.assertEqual(
                result["anchor_disagreement"]["agreement"],
                "torn", msg=token)
            self.assertEqual(
                journal.status_snapshot(home)["anchor"]["agreement"],
                "matching", msg=token)


class ReplayAnchorAndWriteTests(HomeCase):
    def test_r2_005_replay_over_empty_journal_runs_the_anchor_gate(self):
        anchor = os.path.join(self.tmp.name, "anchor.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        self.append_product("Product 0", "p-0")
        self.append_product("Product 1", "p-1")
        with open(journal.journal_path(self.home), "wb") as handle:
            handle.write(b"")
        journal._scan_cache.clear()
        self.assertEqual(journal.status_snapshot(
            self.home)["anchor"]["agreement"], "divergent")
        with self.assertRaises(journal.JournalError):
            self.append_product("Product 9", "p-9")
        with open(anchor, "rb") as handle:
            anchor_before = handle.read()
        lines = self.valid_lines()
        with self.assertRaises(journal.JournalError) as caught:
            journal.replay(self.home, lines)
        self.assertEqual(caught.exception.token, "JOURNAL_VERIFY_FAILED")
        self.assertEqual(self.journal_bytes(), b"")
        with open(anchor, "rb") as handle:
            self.assertEqual(handle.read(), anchor_before)

    def test_r2_005_replay_anchor_write_failure_is_not_swallowed(self):
        anchor_dir = os.path.join(self.tmp.name, "anchor-dir")
        os.makedirs(anchor_dir)
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor_dir)
        lines = self.valid_lines()
        with self.assertRaises(journal.JournalError) as caught:
            journal.replay(self.home, lines)
        self.assertEqual(caught.exception.token, "JOURNAL_VERIFY_FAILED")
        self.assertEqual(self.journal_bytes(), b"")

    def test_r2_005_replay_with_sound_anchor_still_lands(self):
        anchor = os.path.join(self.tmp.name, "anchor.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        lines = self.valid_lines()
        head = journal.replay(self.home, lines)
        self.assertEqual(
            head, hashlib.sha256(lines[-1]).hexdigest())
        state = journal.status_snapshot(self.home)
        self.assertEqual(state["anchor"]["agreement"], "matching")

    def test_r2_006_failed_replacing_replay_write_reports_in_vocabulary(self):
        other = os.path.join(self.tmp.name, "big")
        os.makedirs(other)
        journal.append_entry(other, "audit_record", {"x": "y" * 4100})
        first = None
        with open(journal.journal_path(other), "rb") as handle:
            first = handle.read().split(b"\n")[0]
        second_entry = {"sequence": 2, "entry_kind": "audit_record",
                        "form_version": 1, "payload": {"x": "z" * 4100},
                        "previous_hash": hashlib.sha256(first).hexdigest()}
        second = journal.canonical_bytes(second_entry)
        lines_path = os.path.join(self.tmp.name, "lines.bin")
        with open(lines_path, "wb") as handle:
            handle.write(first + b"\n" + second + b"\n")
        product_root = os.path.dirname(
            os.path.dirname(os.path.abspath(journal.__file__)))
        code = (
            "import resource, signal, sys\n"
            "signal.signal(signal.SIGXFSZ, signal.SIG_IGN)\n"
            "resource.setrlimit(resource.RLIMIT_FSIZE, (3000, 3000))\n"
            "sys.path.insert(0, %r)\n"
            "from citeline import journal\n"
            "with open(%r, 'rb') as handle:\n"
            "    lines = handle.read().split(b'\\n')[:-1]\n"
            "try:\n"
            "    journal.replay(%r, lines)\n"
            "except journal.JournalError as error:\n"
            "    print('JOURNAL_ERROR', error.token, error.row)\n"
            "except OSError as error:\n"
            "    print('RAW_OSERROR', error)\n"
            "else:\n"
            "    print('NO_ERROR')\n"
            % (product_root, lines_path, self.home))
        env = dict(os.environ)
        env["TMPDIR"] = os.environ.get("TMPDIR", "/tmp")
        done = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, env=env,
                              timeout=120)
        self.assertIn("JOURNAL_ERROR JOURNAL_VERIFY_FAILED I-2",
                      done.stdout, msg=done.stdout + done.stderr)
        leftovers = [name for name in os.listdir(self.home)
                     if "replay-" in name]
        self.assertEqual(leftovers, [])
        self.assertEqual(self.journal_bytes(), b"")


class BatchArgumentFormTests(HomeCase):
    def test_r2_007_malformed_batch_arguments_refused_in_vocabulary(self):
        bad_calls = [
            None,
            "ab",
            42,
            [42],
            [("audit_record",)],
            [("audit_record", {}, "extra")],
            ["audit_record"],
        ]
        for bad in bad_calls:
            with self.assertRaises(journal.JournalError,
                                   msg=repr(bad)) as caught:
                journal.append_entries_atomic(self.home, bad)
            self.assertEqual(caught.exception.token, "MALFORMED_CALL",
                             msg=repr(bad))
            self.assertEqual(caught.exception.row, "U-8", msg=repr(bad))
        self.assertFalse(os.path.exists(journal.journal_path(self.home)))

    def test_r2_007_valid_batch_still_appends_all(self):
        appended = journal.append_entries_atomic(
            self.home,
            [("product_registered", product_payload("P0", "p-0")),
             ("product_registered", product_payload("P1", "p-1"))])
        self.assertEqual(len(appended), 2)
        self.assertTrue(journal.verify_chain(self.home)["passed"])


if __name__ == "__main__":
    unittest.main()
