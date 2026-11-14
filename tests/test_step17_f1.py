"""Step 17 fix seat F1 tests: journal, config, anchor, limit_raise.

Each test pins one register entry from the Step 17 round 1
registers (main S17-R1 and supplementary S17-R1X) assigned
to seat F1 in the combined fix wave charge. Homes are
scratch homes under a temporary directory. No test here
touches a standing test item or a Step 15 qualification
ground.
"""

import fcntl
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from citeline import journal


def product_payload(name="Product 0", product_id="p-0"):
    return {"name": name, "product_id": product_id}


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
        with open(journal.journal_path(self.home), "rb") as handle:
            return handle.read()

    def journal_lines(self):
        data = self.journal_bytes()
        return data.split(b"\n")[:-1] if data else []

    def write_anchor_config(self, anchor_path):
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor_path)

    def anchored_home(self, count=3):
        anchor = os.path.join(self.tmp.name, "anchor.txt")
        self.write_anchor_config(anchor)
        for index in range(count):
            self.append_product("Product %d" % index, "p-%d" % index)
        return anchor

    def truncate_journal(self, keep):
        lines = self.journal_lines()
        with open(journal.journal_path(self.home), "wb") as handle:
            for line in lines[:keep]:
                handle.write(line + b"\n")
        journal._scan_cache.clear()


class ScanCacheAndDepthTests(HomeCase):
    def test_001_same_size_tamper_with_restored_mtime_fails_verify(self):
        self.append_product("Product 0", "p-0")
        self.append_product("Product 1", "p-1")
        self.assertTrue(journal.verify_chain(self.home)["passed"])
        path = journal.journal_path(self.home)
        before = os.stat(path)
        data = bytearray(self.journal_bytes())
        index = data.index(b"Product 0")
        data[index + 8] = ord("X")
        with open(path, "wb") as handle:
            handle.write(bytes(data))
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        result = journal.verify_chain(self.home)
        self.assertFalse(result["passed"])
        self.assertEqual(result["failing_sequence"], 2)
        self.assertEqual(result["token"], "JOURNAL_VERIFY_FAILED")

    def test_002_stored_line_nested_900_deep_fails_cleanly(self):
        nested = 1
        for _ in range(900):
            nested = [nested]
        entry = {"sequence": 1, "entry_kind": "audit_record",
                 "form_version": 1, "payload": {"x": nested},
                 "previous_hash": None}
        with open(journal.journal_path(self.home), "wb") as handle:
            handle.write(json.dumps(entry).encode("utf-8") + b"\n")
        result = journal.verify_chain(self.home)
        self.assertFalse(result["passed"])
        self.assertEqual(result["token"], "JOURNAL_VERIFY_FAILED")
        state = journal.status_snapshot(self.home)
        self.assertTrue(state["chain_fails"])
        with self.assertRaises(journal.JournalError):
            journal.fold(self.home)

    def test_002b_append_payload_nested_5000_deep_refused_as_limit(self):
        nested = 1
        for _ in range(5000):
            nested = [nested]
        with self.assertRaises(journal.JournalError) as caught:
            journal.append_entry(self.home, "audit_record", {"x": nested})
        self.assertEqual(caught.exception.token, "LIMIT_EXCEEDED")

    def test_003_lone_surrogate_payload_refused_with_journal_error(self):
        with self.assertRaises(journal.JournalError):
            journal.append_entry(self.home, "audit_record",
                                 {"x": "\ud800"})
        self.assertFalse(os.path.exists(journal.journal_path(self.home)))

    def test_003b_huge_integer_payload_refused_with_journal_error(self):
        with self.assertRaises(journal.JournalError):
            journal.append_entry(self.home, "audit_record",
                                 {"x": 10 ** 5000})


class ReaderBarTests(HomeCase):
    def tamper_first_entry(self):
        path = journal.journal_path(self.home)
        data = bytearray(self.journal_bytes())
        index = data.index(b"Product 0")
        data[index + 8] = ord("X")
        with open(path, "wb") as handle:
            handle.write(bytes(data))
        journal._scan_cache.clear()

    def test_004_readers_refuse_a_tampered_chain(self):
        self.append_product("Product 0", "p-0")
        self.append_product("Product 1", "p-1")
        self.tamper_first_entry()
        self.assertFalse(journal.verify_chain(self.home)["passed"])
        with self.assertRaises(journal.JournalError):
            journal.fold(self.home)
        with self.assertRaises(journal.JournalError):
            journal.read_entry(self.home, 1)
        with self.assertRaises(journal.JournalError):
            journal.fold_registry(self.home)

    def test_004b_effective_limits_refuses_raise_on_tampered_chain(self):
        self.append_product("Product 0", "p-0")
        journal.append_entry(
            self.home, "limit_raise",
            {"limit": "limit_39", "raised_value": 5, "run_id": "runX"})
        self.tamper_first_entry()
        with self.assertRaises(journal.JournalError):
            journal.effective_limits(self.home, run_id="runX")

    def test_004c_fold_refuses_a_torn_tail(self):
        self.append_product("Product 0", "p-0")
        with open(journal.journal_path(self.home), "ab") as handle:
            handle.write(b'{"entry_kind":"round_named","form_vers')
        journal._scan_cache.clear()
        with self.assertRaises(journal.JournalError):
            journal.fold(self.home)

    def test_006_journal_path_as_directory_fails_verify(self):
        os.makedirs(journal.journal_path(self.home))
        result = journal.verify_chain(self.home)
        self.assertFalse(result["passed"])
        self.assertEqual(result["token"], "JOURNAL_VERIFY_FAILED")
        state = journal.status_snapshot(self.home)
        self.assertTrue(state["chain_fails"])

    def hold_lock(self):
        lock_path = os.path.join(self.home, ".citeline-write.lock")
        handle = open(lock_path, "a+")
        self.addCleanup(handle.close)
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return handle

    def test_007_garbage_partial_tail_not_hidden_by_lock_holder(self):
        self.append_product("Product 0", "p-0")
        with open(journal.journal_path(self.home), "ab") as handle:
            handle.write(b"\xff\xfeNOT A PREFIX OF ANY ENTRY")
        journal._scan_cache.clear()
        self.hold_lock()
        result = journal.verify_chain(self.home)
        self.assertFalse(result["passed"])

    def test_007b_plausible_partial_tail_of_live_holder_still_ignored(self):
        self.append_product("Product 0", "p-0")
        with open(journal.journal_path(self.home), "ab") as handle:
            handle.write(b'{"entry_kind":"round_named","form_vers')
        journal._scan_cache.clear()
        self.hold_lock()
        result = journal.verify_chain(self.home)
        self.assertTrue(result["passed"])
        self.assertEqual(result["entry_count"], 1)


class ReplayTests(HomeCase):
    def valid_lines(self, other):
        os.makedirs(other)
        journal.append_entry(other, "product_registered",
                             product_payload("Other 0", "p-o0"))
        journal.append_entry(other, "product_registered",
                             product_payload("Other 1", "p-o1"))
        with open(journal.journal_path(other), "rb") as handle:
            return handle.read().split(b"\n")[:-1]

    def test_005_replay_refuses_garbage_lines_and_writes_nothing(self):
        with self.assertRaises(journal.JournalError):
            journal.replay(self.home,
                           [b'{"garbage": true}', b"not json at all"])
        self.assertFalse(os.path.exists(journal.journal_path(self.home)))

    def test_005b_replay_without_resume_refuses_standing_journal(self):
        for index in range(3):
            self.append_product("Product %d" % index, "p-%d" % index)
        before = self.journal_bytes()
        lines = self.valid_lines(os.path.join(self.tmp.name, "other"))
        with self.assertRaises(journal.JournalError):
            journal.replay(self.home, lines)
        self.assertEqual(self.journal_bytes(), before)
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_005c_replay_resume_refuses_restated_sequence(self):
        self.append_product("Product 0", "p-0")
        line = self.journal_lines()[0]
        with self.assertRaises(journal.JournalError):
            journal.replay(self.home, [line], resume=True)
        self.assertEqual(len(self.journal_lines()), 1)
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_005d_replay_checks_the_journal_length_cap(self):
        journal.write_config(self.home, "journal_length = 1\n")
        lines = self.valid_lines(os.path.join(self.tmp.name, "other"))
        with self.assertRaises(journal.JournalError) as caught:
            journal.replay(self.home, lines)
        self.assertEqual(caught.exception.token, "JOURNAL_CAP_EXCEEDED")
        self.assertFalse(os.path.exists(journal.journal_path(self.home)))

    def test_x029_replay_argument_forms_refused(self):
        line = None
        other = os.path.join(self.tmp.name, "other")
        lines = self.valid_lines(other)
        line = lines[0]
        for bad in (line.decode("utf-8"), line, {"a": 1}, None,
                    [line, 65], "one string"):
            with self.assertRaises(journal.JournalError,
                                   msg="entries=%r" % (bad,)):
                journal.replay(self.home, bad)
        self.assertFalse(os.path.exists(journal.journal_path(self.home)))


class AnchorTests(HomeCase):
    def test_x001_sequenceless_anchor_is_divergent_and_bars(self):
        anchor = self.anchored_home(3)
        head1 = hashlib.sha256(self.journal_lines()[0]).hexdigest()
        self.truncate_journal(1)
        with open(anchor, "w") as handle:
            handle.write(head1 + "\n")
        state = journal.status_snapshot(self.home)
        self.assertEqual(state["anchor"]["agreement"], "divergent")
        with self.assertRaises(journal.JournalError):
            self.append_product("Product 9", "p-9")

    def test_x001b_anchor_bad_sequence_forms_and_extra_tokens(self):
        for suffix in ("notanint", "2.0", "1 EXTRA GARBAGE"):
            home = os.path.join(self.tmp.name,
                                "home-" + suffix.split()[0])
            os.makedirs(home)
            anchor = os.path.join(self.tmp.name,
                                  "anchor-" + suffix.split()[0])
            journal.write_config(home, "anchor_path = %s\n" % anchor)
            journal.append_entry(home, "product_registered",
                                 product_payload("A", "p-a"))
            with open(journal.journal_path(home), "rb") as handle:
                head = hashlib.sha256(
                    handle.read().split(b"\n")[0]).hexdigest()
            with open(anchor, "w") as handle:
                handle.write("%s %s\n" % (head, suffix))
            journal._scan_cache.clear()
            state = journal.status_snapshot(home)
            self.assertEqual(state["anchor"]["agreement"], "divergent",
                             msg=suffix)
            with self.assertRaises(journal.JournalError, msg=suffix):
                journal.append_entry(home, "product_registered",
                                     product_payload("B", "p-b"))

    def test_x002_deleted_or_emptied_anchor_bars_append(self):
        anchor = self.anchored_home(3)
        self.truncate_journal(1)
        os.unlink(anchor)
        with self.assertRaises(journal.JournalError):
            self.append_product("Product 9", "p-9")
        with open(anchor, "w") as handle:
            handle.write("")
        with self.assertRaises(journal.JournalError):
            self.append_product("Product 9", "p-9")

    def test_x003_relative_anchor_path_resolves_against_home(self):
        journal.write_config(self.home, "anchor_path = ../outside.txt\n")
        previous = os.getcwd()
        os.chdir(self.tmp.name)
        try:
            self.append_product("Product 0", "p-0")
        finally:
            os.chdir(previous)
        resolved = os.path.join(self.tmp.name, "outside.txt")
        self.assertTrue(os.path.isfile(resolved))
        state = journal.status_snapshot(self.home)
        self.assertEqual(state["anchor"]["agreement"], "matching")

    def test_x003b_relative_anchor_inside_home_refused(self):
        with open(journal.config_path(self.home), "w") as handle:
            handle.write("anchor_path = anchor.txt\n")
        with self.assertRaises(journal.ConfigError) as caught:
            self.append_product("Product 0", "p-0")
        self.assertEqual(caught.exception.token,
                         "ANCHOR_PATH_INSIDE_HOME")

    def test_x004_symlinked_anchor_directory_defeats_no_check(self):
        link = os.path.join(self.tmp.name, "linkhome")
        os.symlink(self.home, link)
        candidate = os.path.join(link, "journal.jsonl")
        with self.assertRaises(journal.ConfigError) as caught:
            journal.parse_config("anchor_path = %s\n" % candidate,
                                 home=self.home)
        self.assertEqual(caught.exception.token,
                         "ANCHOR_PATH_INSIDE_HOME")

    def test_x005_failed_anchor_write_fails_append_and_rolls_back(self):
        anchor = self.anchored_home(1)
        os.unlink(anchor)
        os.makedirs(anchor)
        before = self.journal_bytes()
        with self.assertRaises(journal.JournalError):
            self.append_product("Product 1", "p-1")
        self.assertEqual(self.journal_bytes(), before)
        self.assertTrue(journal.verify_chain(self.home)["passed"])

    def test_x006_stale_anchor_bars_append(self):
        anchor = self.anchored_home(3)
        first_head = hashlib.sha256(self.journal_lines()[0]).hexdigest()
        with open(anchor, "w") as handle:
            handle.write("%s 1\n" % first_head)
        journal._scan_cache.clear()
        state = journal.status_snapshot(self.home)
        self.assertEqual(state["anchor"]["agreement"], "stale")
        with self.assertRaises(journal.JournalError):
            self.append_product("Product 9", "p-9")
        self.assertEqual(len(self.journal_lines()), 3)


class LimitRaiseTests(HomeCase):
    def raise_entry(self, limit, value, run_id="run-1", **extra):
        payload = {"limit": limit, "run_id": run_id}
        if value is not _MISSING:
            payload["raised_value"] = value
        payload.update(extra)
        return journal.append_entry(self.home, "limit_raise", payload)

    def test_081_raise_past_hard_ceiling_refused(self):
        with self.assertRaises(journal.JournalError):
            self.raise_entry("limit_39", 10 ** 12)
        self.assertFalse(os.path.exists(journal.journal_path(self.home)))

    def test_081b_backstop_raise_past_its_default_refused(self):
        with self.assertRaises(journal.JournalError):
            self.raise_entry("limit_42", 9999)
        with self.assertRaises(journal.JournalError):
            self.raise_entry("limit_41", 121)

    def test_x007_raise_zero_or_negative_refused(self):
        for value in (-5, 0, -100):
            with self.assertRaises(journal.JournalError, msg=str(value)):
                self.raise_entry("limit_39", value)
        self.assertFalse(os.path.exists(journal.journal_path(self.home)))

    def test_x009_raise_non_integer_value_refused(self):
        for value in ("999999", True, _MISSING, 5.5):
            with self.assertRaises(journal.JournalError,
                                   msg=repr(value)):
                self.raise_entry("limit_39", value)
        self.assertFalse(os.path.exists(journal.journal_path(self.home)))

    def test_x010_supplied_chain_duplicate_raise_fails_verify(self):
        self.raise_entry("limit_39", 500)
        first = journal.fold(self.home)[0]
        second = {"sequence": 2, "entry_kind": "limit_raise",
                  "form_version": 1,
                  "payload": {"limit": "limit_39", "raised_value": 7,
                              "run_id": "run-1"},
                  "previous_hash": first["entry_hash"]}
        line = journal.canonical_bytes(second)
        with open(journal.journal_path(self.home), "ab") as handle:
            handle.write(line + b"\n")
        journal._scan_cache.clear()
        result = journal.verify_chain(self.home)
        self.assertFalse(result["passed"])

    def test_raise_within_range_still_lands(self):
        self.raise_entry("limit_39", 110000)
        limits = journal.effective_limits(self.home, run_id="run-1")
        self.assertEqual(limits["journal_length"]["value"], 110000)
        self.assertEqual(limits["journal_length"]["source"], "raise")


class _Missing:
    pass


_MISSING = _Missing()


class ConfigTests(HomeCase):
    def write_raw_config(self, data):
        mode = "wb" if isinstance(data, bytes) else "w"
        with open(journal.config_path(self.home), mode) as handle:
            handle.write(data)

    def test_073_non_utf8_config_is_config_invalid(self):
        self.write_raw_config(b"journal_length = 5\xff\n")
        with self.assertRaises(journal.ConfigError) as caught:
            journal.status_snapshot(self.home)
        self.assertEqual(caught.exception.token, "CONFIG_INVALID")

    def test_073b_non_utf8_anchor_does_not_crash_status(self):
        anchor = self.anchored_home(1)
        with open(anchor, "wb") as handle:
            handle.write(b"\xff\xfe and text")
        journal._scan_cache.clear()
        state = journal.status_snapshot(self.home)
        self.assertEqual(state["anchor"]["agreement"], "divergent")

    def test_076_bom_does_not_disable_first_config_line(self):
        self.write_raw_config(b"\xef\xbb\xbfjournal_length = 5\n")
        limits = journal.effective_limits(self.home)
        self.assertEqual(limits["journal_length"]["value"], 5)
        self.assertEqual(limits["journal_length"]["source"], "config")

    def test_x012_huge_digit_value_is_config_invalid(self):
        self.write_raw_config("journal_length = " + "9" * 5000 + "\n")
        with self.assertRaises(journal.ConfigError) as caught:
            journal.status_snapshot(self.home)
        self.assertEqual(caught.exception.token, "CONFIG_INVALID")

    def test_x013_config_path_as_directory_is_config_invalid(self):
        os.makedirs(journal.config_path(self.home))
        with self.assertRaises(journal.ConfigError) as caught:
            journal.status_snapshot(self.home)
        self.assertEqual(caught.exception.token, "CONFIG_INVALID")

    def test_x014_home_path_key_carries_a_warning(self):
        _values, warnings = journal.parse_config("home_path = /tmp/evil\n")
        self.assertTrue(any("home_path" in item for item in warnings))

    def test_x015_write_config_applies_the_read_parse(self):
        for text in ("journal_length = 999999999\n",
                     "journal_length = 5\njournal_length = 6\n",
                     "anchor_path = %s\n" % os.path.join(
                         self.home, "anchor.txt")):
            with self.assertRaises(journal.ConfigError, msg=text):
                journal.write_config(self.home, text)
            self.assertFalse(
                os.path.exists(journal.config_path(self.home)))


class CorrectionTests(HomeCase):
    def test_x028_degenerate_corrections_refused_at_append(self):
        self.append_product("Product 0", "p-0")
        record = product_payload("New Name", "p-0")
        bad_payloads = [
            {},
            {"supersedes_sequence": 999, "corrected_record": record},
            {"supersedes_sequence": 1, "corrected_record": "not-a-record"},
            {"supersedes_sequence": "1", "corrected_record": record},
            {"supersedes_sequence": None, "corrected_record": record},
            {"supersedes_sequence": True, "corrected_record": record},
        ]
        for payload in bad_payloads:
            with self.assertRaises(journal.JournalError,
                                   msg=repr(payload)) as caught:
                journal.append_entry(self.home, "correction", payload)
            self.assertEqual(caught.exception.token, "MALFORMED_CALL")
        self.assertEqual(len(self.journal_lines()), 1)

    def test_x028b_correction_of_a_correction_refused(self):
        self.append_product("Product 0", "p-0")
        journal.append_entry(
            self.home, "correction",
            {"supersedes_sequence": 1,
             "corrected_record": product_payload("New Name", "p-0")})
        with self.assertRaises(journal.JournalError):
            journal.append_entry(
                self.home, "correction",
                {"supersedes_sequence": 2,
                 "corrected_record": product_payload("Third", "p-0")})

    def test_x028c_valid_correction_still_governs(self):
        self.append_product("Old Name", "p-0")
        journal.append_entry(
            self.home, "correction",
            {"supersedes_sequence": 1,
             "corrected_record": product_payload("New Name", "p-0")})
        state = journal.fold_registry(self.home)
        self.assertEqual(state["p-0"]["name"], "New Name")


class FailedWriteTests(HomeCase):
    def test_090_write_failure_rolls_back_and_reports_in_vocabulary(self):
        self.append_product("Product 0", "p-0")
        before = self.journal_bytes()
        product_root = os.path.dirname(
            os.path.dirname(os.path.abspath(journal.__file__)))
        size = len(before) + 4096
        code = (
            "import resource, signal, sys\n"
            "signal.signal(signal.SIGXFSZ, signal.SIG_IGN)\n"
            "resource.setrlimit(resource.RLIMIT_FSIZE, (%d, %d))\n"
            "sys.path.insert(0, %r)\n"
            "from citeline import journal\n"
            "try:\n"
            "    journal.append_entry(%r, 'audit_record',\n"
            "                         {'x': 'y' * 9000})\n"
            "except journal.JournalError as error:\n"
            "    print('JOURNAL_ERROR', error.token)\n"
            "except OSError as error:\n"
            "    print('RAW_OSERROR', error)\n"
            "else:\n"
            "    print('NO_ERROR')\n" % (size, size, product_root,
                                       self.home))
        env = dict(os.environ)
        env["TMPDIR"] = os.environ.get("TMPDIR", "/tmp")
        done = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True, env=env,
                              timeout=120)
        self.assertIn("JOURNAL_ERROR", done.stdout, msg=done.stdout)
        journal._scan_cache.clear()
        self.assertEqual(self.journal_bytes(), before)
        self.assertTrue(journal.verify_chain(self.home)["passed"])


if __name__ == "__main__":
    unittest.main()
