"""Step 20 fix tests, seat FX20-05, journal and status.

Items cured, one class per item: R19-038 (delegated
decision 12, entry_count counts valid entries only),
R19-033 (delegated decision 1, the anchor append bar
goes), R19-036 (delegated decision 2, status over a
missing home at exit 2 and the shipped text correction),
and R19-051 (delegated decision 3, status states when
the head hash recording stands due). Written before the
cure, under the test first rule.
"""

import hashlib
import os
import tempfile
import unittest

import citeline.journal as journal
from citeline import service, shell


def product_payload(name, product_id):
    return {"name": name, "product_id": product_id,
            "canonical_line": name + " line",
            "domain": "example.com", "competitors": [],
            "aliases": [], "query_set": [], "category": []}


class HomeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def append_product(self, name, product_id):
        return journal.append_entry(
            self.home, "product_registered",
            product_payload(name, product_id))

    def journal_lines(self):
        with open(journal.journal_path(self.home), "rb") as handle:
            data = handle.read()
        return data.split(b"\n")[:-1] if data else []

    def append_raw(self, raw):
        with open(journal.journal_path(self.home), "ab") as handle:
            handle.write(raw)
        journal._scan_cache.clear()

    def anchored_home(self, entries=3):
        anchor = os.path.join(self.tmp.name, "anchor.txt")
        journal.write_config(
            self.home, "anchor_path = %s\n" % anchor)
        for index in range(entries):
            self.append_product("P%d" % index, "p-%d" % index)
        journal._scan_cache.clear()
        return anchor


class ValidEntryCountTests(HomeCase):
    """R19-038, decision 12: entry_count counts valid
    entries only. A complete corrupt line is reported as
    corruption in the same output and is not counted as
    an entry, exactly as a torn partial line is not."""

    def test_corrupt_complete_line_not_counted(self):
        self.append_product("A", "p-a")
        self.append_product("B", "p-b")
        self.append_raw(b"this line is not a journal entry\n")
        result = journal.verify_chain(self.home)
        self.assertFalse(result["passed"])
        self.assertEqual(result["entry_count"], 2)
        state = journal.status_snapshot(self.home)
        self.assertTrue(state["chain_fails"])
        self.assertEqual(state["entry_count"], 2)
        self.assertEqual(service.status(home=self.home)["entry_count"], 2)
        self.assertEqual(service.verify(home=self.home)["entry_count"], 2)
        self.assertEqual(service._entry_count(self.home), 2)

    def test_torn_partial_line_not_counted(self):
        self.append_product("A", "p-a")
        self.append_raw(b"{\"sequence\":2,\"entry_kind\":\"prod")
        self.assertEqual(
            journal.verify_chain(self.home)["entry_count"], 1)
        self.assertEqual(
            journal.status_snapshot(self.home)["entry_count"], 1)

    def test_first_entry_corrupt_counts_zero_and_absence_form(self):
        # The restated governed pin case, decided in the
        # seat paper: the distinct absence form stands on
        # the head text, and the count is the valid count.
        self.append_product("A", "p-a")
        line = bytearray(self.journal_lines()[0])
        line[-3] = ord("x")
        with open(journal.journal_path(self.home), "wb") as handle:
            handle.write(bytes(line) + b"\n")
        journal._scan_cache.clear()
        state = service.status(home=self.home)
        self.assertEqual(
            state["head"],
            "no head: the journal does not recompute from its "
            "first entry")
        self.assertNotEqual(state["head"], "no entries")
        self.assertTrue(state["chain_fails"])
        self.assertEqual(state["entry_count"], 0)
        self.assertEqual(
            service.verify(home=self.home)["entry_count"], 0)

    def test_valid_and_empty_counts_stand(self):
        self.assertEqual(
            journal.status_snapshot(self.home)["entry_count"], 0)
        self.assertEqual(
            journal.status_snapshot(self.home)["head"], "no entries")
        for index in range(3):
            self.append_product("P%d" % index, "p-%d" % index)
        self.assertEqual(
            journal.verify_chain(self.home)["entry_count"], 3)
        self.assertEqual(
            journal.status_snapshot(self.home)["entry_count"], 3)


class AnchorAppendTests(HomeCase):
    """R19-033, decision 1: appends proceed over a stale,
    missing, or malformed anchor and rewrite the anchor.
    The disagreement stands reported in the append result
    and in status and verify until the anchor agrees."""

    def check_proceeds(self, agreement):
        result = self.append_product("P9", "p-9")
        self.assertEqual(
            result["anchor_disagreement"]["agreement"], agreement)
        self.assertEqual(len(self.journal_lines()), 4)
        state = journal.status_snapshot(self.home)
        self.assertEqual(state["anchor"]["agreement"], "matching")
        self.assertEqual(state["entry_count"], 4)
        return result

    def test_stale_anchor_append_proceeds(self):
        anchor = self.anchored_home(3)
        first_head = hashlib.sha256(self.journal_lines()[0]).hexdigest()
        with open(anchor, "w") as handle:
            handle.write("%s 1\n" % first_head)
        journal._scan_cache.clear()
        self.assertEqual(
            journal.status_snapshot(self.home)["anchor"]["agreement"],
            "stale")
        self.assertEqual(
            service.verify(home=self.home)["anchor"]["agreement"],
            "stale")
        self.check_proceeds("stale")
        with open(anchor) as handle:
            recorded = handle.read().split()
        self.assertEqual(recorded[0], journal.status_snapshot(
            self.home)["head_hash"])
        self.assertEqual(recorded[1], "4")

    def test_missing_anchor_append_proceeds(self):
        anchor = self.anchored_home(3)
        os.unlink(anchor)
        journal._scan_cache.clear()
        self.assertEqual(
            journal.status_snapshot(self.home)["anchor"]["agreement"],
            "absent")
        self.check_proceeds("absent")
        self.assertTrue(os.path.isfile(anchor))

    def test_malformed_anchor_append_proceeds(self):
        anchor = self.anchored_home(3)
        with open(anchor, "w") as handle:
            handle.write("garbage partial\n")
        journal._scan_cache.clear()
        self.assertEqual(
            journal.status_snapshot(self.home)["anchor"]["agreement"],
            "torn")
        self.assertEqual(
            service.verify(home=self.home)["anchor"]["agreement"],
            "torn")
        self.check_proceeds("torn")

    def test_divergent_anchor_append_stands_barred(self):
        # Decision 1 names stale, missing, and malformed.
        # A divergent recording, a head standing nowhere
        # in the chain, is the honest forgery case of plan
        # pair IM2-INV-3, whose facts decision 1 does not
        # reach: its bar stands exactly as it stood, and
        # the disagreement stands reported in status.
        anchor = self.anchored_home(3)
        other_head = hashlib.sha256(b"another chain").hexdigest()
        with open(anchor, "w") as handle:
            handle.write("%s 2\n" % other_head)
        journal._scan_cache.clear()
        self.assertEqual(
            journal.status_snapshot(self.home)["anchor"]["agreement"],
            "divergent")
        with self.assertRaises(journal.JournalError):
            self.append_product("P9", "p-9")
        self.assertEqual(len(self.journal_lines()), 3)
        self.assertEqual(
            journal.status_snapshot(self.home)["anchor"]["agreement"],
            "divergent")

    def test_matching_anchor_append_reports_no_disagreement(self):
        self.anchored_home(2)
        result = self.append_product("P9", "p-9")
        self.assertNotIn("anchor_disagreement", result)
        self.assertEqual(
            journal.status_snapshot(self.home)["anchor"]["agreement"],
            "matching")

    def test_service_add_product_over_stale_anchor(self):
        anchor = self.anchored_home(3)
        first_head = hashlib.sha256(self.journal_lines()[0]).hexdigest()
        with open(anchor, "w") as handle:
            handle.write("%s 1\n" % first_head)
        journal._scan_cache.clear()
        record = service.add_product(
            home=self.home, name="Service Product",
            canonical_line="Service Product line",
            domain="example.com")
        self.assertIsNotNone(record)
        self.assertEqual(
            journal.status_snapshot(self.home)["anchor"]["agreement"],
            "matching")


class StatusMissingHomeTests(HomeCase):
    """R19-036, decision 2: status over a missing home
    returns exit 2 with HOME_MISSING. The shipped sentence
    that status returns 0 in every case is corrected to
    except a missing home."""

    def test_status_missing_home_exit_2(self):
        missing = os.path.join(self.tmp.name, "no-home")
        self.assertEqual(shell.main(["status", "--home", missing]), 2)

    def test_status_missing_home_token(self):
        missing = os.path.join(self.tmp.name, "no-home")
        with self.assertRaises(Exception) as caught:
            service.status(home=missing)
        self.assertEqual(
            getattr(caught.exception, "token", None), "HOME_MISSING")
        self.assertEqual(
            getattr(caught.exception, "exit_code", None), 2)

    def test_status_standing_and_broken_home_exit_0(self):
        self.append_product("A", "p-a")
        self.assertEqual(
            shell.main(["status", "--home", self.home]), 0)
        line = bytearray(self.journal_lines()[0])
        line[-3] = ord("x")
        with open(journal.journal_path(self.home), "wb") as handle:
            handle.write(bytes(line) + b"\n")
        journal._scan_cache.clear()
        self.assertEqual(
            shell.main(["status", "--home", self.home]), 0)

    def test_shipped_text_excepts_missing_home(self):
        import citeline.journal as journal_module
        source = os.path.join(
            os.path.dirname(journal_module.__file__), "journal.py")
        with open(source, encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn("returns 0 in every case.", text)
        self.assertIn(
            "returns 0 in every case over a home that stands",
            text)
        self.assertIn("HOME_MISSING", text)


class HeadHashRecordingTests(HomeCase):
    """R19-051, decision 3: the head hash duty stays
    manual and the hash stays stored outside the home in
    version 1. Status output states plainly when the
    recording stands due."""

    def test_status_states_recording_due_over_standing_head(self):
        self.append_product("A", "p-a")
        state = service.status(home=self.home)
        self.assertTrue(state["head_hash_recording_due"])
        self.assertIn("stands due", state["head_hash_recording"])
        self.assertIn("outside the product home",
                      state["head_hash_recording"])
        self.assertIn(state["head_hash"],
                      state["head_hash_recording"])

    def test_status_no_recording_due_without_a_head(self):
        state = service.status(home=self.home)
        self.assertFalse(state["head_hash_recording_due"])
        state = journal.status_snapshot(self.home)
        self.assertFalse(state["head_hash_recording_due"])

    def test_simple_form_prints_the_due_statement(self):
        self.append_product("A", "p-a")
        state = service.status(home=self.home)
        rendered = shell.format_record(state, form="simple")
        self.assertIn("stands due", rendered)


if __name__ == "__main__":
    unittest.main()
