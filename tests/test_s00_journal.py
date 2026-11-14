"""Step 13 tests for slice S0, journal and store foundation.

Written before the product. No product code exists for this
build, so every test here stands red by import or attribute
failure against the absent product package. That is the
correct state under the test first rule.

The product package is citeline. Slice S0 owns the journal
module (plan Part 1, slice S0: Module: journal). The
operations used here stand for the plan operations by their
plan names: append, verify, status, and fold over a home,
the canonical form rendering and entry hash of entry 14,
config parsing and the limits in force of entry 15, the
exclusion of entry 16, the append cost statement, and
replay. The invocation surface operations verify and status
stand at brief Section 5.12. Shapes stand at plan
Section 5.1. Contracts C7 and C1 in their journal limbs
stand at plan Section 9.

Every test method docstring names the matrix row it pins by
section qualified identifier and the oracle passage. Dates
in these tests are call inputs, never clock reads, on plan
Section 1.5 date handling terms. Expectations stand hand
computed from the cited passage. No golden file recorded
from a run stands as a sole expectation source. The entry
14 vectors stand published in the plan at decision
D-KF-14-VECTORS; two of their hashes (V-01 and V-16) were
recomputed by hand with SHA-256 over the stated bytes at
authoring time and matched.

Suite convention recorded for this module (Step 13 test
audit round 1, entries R1-007 and R1-010). The operations
verify and status are called at the service home,
citeline.service.status and citeline.service.verify, with
the keyword input home and no form input (entry R1-090);
formed output of a standing result goes through the
rendering act the reporting slice pins. The journal home,
citeline.journal, keeps the fold level helpers with no
service pair: fold, fold_registry, and read_entry. Every
helper this module requires stands named here, so the
build aligns to them once: journal.append_entry,
journal.canonical_bytes, journal.entry_hash,
journal.parse_entry, journal.read_entry, journal.fold,
journal.fold_registry, journal.replay, journal.append_cost,
journal.effective_limits, journal.parse_config,
journal.journal_path, journal.write_config,
journal.config_keys, journal.limit_for_member, and
journal.start_run. File names and locations on this
convention: journal.journal_path(home) names the journal
file, named journal.jsonl, directly inside the home;
journal.write_config(home, text) writes the config file,
named config.txt, directly inside the home it is given;
the write lock file stands directly inside the home under
the name .citeline-write.lock, as the concurrency tests
already use.

Exact spellings pinned in this module stand on this
convention where no passage states them (entry R1-010):
the status and verify result keys passed, chain_fails,
exit_code, claim, head, head_hash, entry_count, home_path,
home_size, capacity_outlook, anchor, error_value, and row,
and the absence of a last_verify_result key; the capacity
outlook subkeys journal_length_remaining and
total_home_size_remaining; the anchor subkey agreement;
the limit entry keys value, source, and unit; the source
strings brief default, config, and raise; the run record
key config_file and its value absent; the exception types
journal.JournalError and journal.ConfigError, each
carrying row and token attributes; and the parse_config
return form as a values and warnings pair. One alignment
at build time settles all of them.
"""

import hashlib
import json
import os
import tempfile
import time
import unittest

import citeline.journal as journal
import citeline.service as service


HOME_DATE = "2026-11-13"

VECTORS = [
    ("V-01", "product_registered",
     '{"entry_kind":"product_registered","form_version":1,"payload":{"name":"Example Product","product_id":"p-example"},"previous_hash":null,"sequence":1}',
     "13e8d7434330c0f949e6c8a94060ccfb73e4fd0c71e9712f85277098f5e854cd"),
    ("V-02", "registry_change",
     '{"entry_kind":"registry_change","form_version":1,"payload":{"changed_field":"name","product_id":"p-example","value":"Example Product Two"},"previous_hash":null,"sequence":1}',
     "e477e1c564d2e86f8eb5bffce55b6f2d7000c9e1fee9f9b5ed16120bfbe6aecd"),
    ("V-03", "round_named",
     '{"entry_kind":"round_named","form_version":1,"payload":{"product_id":"p-example","round_id":"p-example:r1","round_label":"r1"},"previous_hash":null,"sequence":1}',
     "8109d69e11054f154c31efb78ad7c07e77f3c263711105495a57352f1668b57a"),
    ("V-04", "snapshot_registered",
     '{"entry_kind":"snapshot_registered","form_version":1,"payload":{"product_id":"p-example","snapshot_id":"snap-1"},"previous_hash":null,"sequence":1}',
     "346e7e98793e462605633bdff23b553be168be638edab3a21b9b4cb613477585"),
    ("V-05", "audit_record",
     '{"entry_kind":"audit_record","form_version":1,"payload":{"product_id":"p-example","run_id":"run-1"},"previous_hash":null,"sequence":1}',
     "ea298a73646ff5d9f0877d5a49579a041891967eb354bfa8283299010ff15267"),
    ("V-06", "answer_imported",
     '{"entry_kind":"answer_imported","form_version":1,"payload":{"answer_id":"ans-1","round_id":"p-example:r1","text":"Example answer text"},"previous_hash":null,"sequence":1}',
     "d4a1d1a356e2224369f69b78dff1a2b72ede05a337dace47508af01daba18595"),
    ("V-07", "guide_record",
     '{"entry_kind":"guide_record","form_version":1,"payload":{"product_id":"p-example","refused":false},"previous_hash":null,"sequence":1}',
     "83a1fd05145a3bc03e273adfc50ac9eec3cd76c7d4f894b89310be4481ee47e9"),
    ("V-08", "limit_raise",
     '{"entry_kind":"limit_raise","form_version":1,"payload":{"brief_value":100000,"limit":"limit_39","raised_value":110000,"run_id":"run-1"},"previous_hash":null,"sequence":1}',
     "3f55cfdc439b5302711cb7908ba0599d8f31444a6efb205c9fd3559454efce8b"),
    ("V-09", "failure_record",
     '{"entry_kind":"failure_record","form_version":1,"payload":{"date":"2026-11-13","error_value":"CONFIG_INVALID","operation":"configure","rule_fired":"config parse","subject_identity":"config"},"previous_hash":null,"sequence":1}',
     "cb402b50e795b463c8af3d2f90a5a17e2df0071c4f3a19edabdfc211a066ac88"),
    ("V-10", "correction",
     '{"entry_kind":"correction","form_version":1,"payload":{"corrected_record":{"note":"corrected entry"},"supersedes_sequence":1},"previous_hash":null,"sequence":1}',
     "79f1f90d73ad0c574d2328a54204d332b0078178137bae3cd1055e47c5c0cf98"),
    ("V-11", "answer_imported",
     '{"entry_kind":"answer_imported","form_version":1,"payload":{"answer_id":"ans-2","round_id":"p-example:r1","text":"Réponse café, 日本語の回答"},"previous_hash":null,"sequence":1}',
     "b009909ca32762b0beb81b1f5597cb95b1bd26e782592c8c26be6dfb6d56d238"),
    ("V-12", "audit_record",
     '{"entry_kind":"audit_record","form_version":1,"payload":{"product_id":"p-example","refusal_code":null,"run_id":"run-2"},"previous_hash":null,"sequence":1}',
     "8e50444861d55bf154ae0ec4fd1460574b79188cc38b94ca1f0de9e75f91963f"),
    ("V-13", "product_registered",
     '{"entry_kind":"product_registered","form_version":1,"payload":{"aliases":[],"name":"","product_id":"p-empty"},"previous_hash":null,"sequence":1}',
     "48b5968668dcf7bf8b7d15a1c260e1b86843329ebdfc4c3405ad099d1903d198"),
    ("V-14", "audit_record",
     '{"entry_kind":"audit_record","form_version":1,"payload":{"earned":12.340,"product_id":"p-example","rate":0.500000,"run_id":"run-3","score":9.0},"previous_hash":null,"sequence":1}',
     "4e38d9ebb6b1c47f8fb1040d5e7a40db6c888b64c502d4d0268ee02e28b26d06"),
    ("V-15", "round_named",
     '{"entry_kind":"round_named","form_version":1,"payload":{"product_id":"p-example","round_id":"p-example:r2","round_label":"r2"},"previous_hash":null,"sequence":1}',
     "20b56c8c4fd279f5edd3d12c17cbc981df158c33feeafb3803e1136b5a5754f0"),
    ("V-16", "answer_imported",
     '{"entry_kind":"answer_imported","form_version":1,"payload":{"answer_id":"ans-3","round_id":"p-example:r2","text":"Chain answer"},"previous_hash":"20b56c8c4fd279f5edd3d12c17cbc981df158c33feeafb3803e1136b5a5754f0","sequence":2}',
     "4a9692827ce480f81ebff9a855984e2a7ddba11a2ee6bdda547e06434b0f60ff"),
    ("V-17", "audit_record",
     '{"entry_kind":"audit_record","form_version":1,"payload":{"count":1,"flag":true,"product_id":"p-example","run_id":"run-4","score":1.0},"previous_hash":null,"sequence":1}',
     "eabdbc642ff07075f7b65d476a76d8a1c00e7d8101586901392f6da4e4fcc699"),
    ("V-18", "audit_record",
     '{"entry_kind":"audit_record","form_version":1,"payload":{"product_id":"p-example","run_id":"run-5","zero_value":0},"previous_hash":null,"sequence":1}',
     "ce77d3b78069abbc210fa5149f661c2abf1bfd40e05130727ad5c25dfe021475"),
    ("V-19", "audit_record",
     '{"entry_kind":"audit_record","form_version":1,"payload":{"product_id":"p-example","run_id":"run-6","score":0.0},"previous_hash":null,"sequence":1}',
     "9eb722ecd9fd1d99bfbba5555a0252b6165519432bb70d0a331ffb08b6e65223"),
    ("V-20", "audit_record",
     '{"entry_kind":"audit_record","form_version":1,"payload":{"checks":[{"check_id":"example_check","status":"pass"}],"product_id":"p-example","robots_summary":null,"run_id":"run-7"},"previous_hash":null,"sequence":1}',
     "d58f454eab0a63d0d10af20dc7ffaa03283caa410936a6d4aff3b94f4e155ff7"),
]

VECTOR_BY_ID = {row[0]: row for row in VECTORS}


def canonical_line(payload, sequence, previous_hash, kind="product_registered"):
    """Hand rendering of one canonical line for structural tests.

    Built from plan Part 1 Section 2.1 and decisions
    D-KF-14-ESC, D-KF-14-UNIT, and D-KF-14-HASHSELF: keys
    ordered by Unicode code point, comma and colon with no
    space, minimal escaping, UTF-8, entry_hash omitted,
    previous_hash null at sequence 1. Payloads used with
    this helper hold integers, strings, lists, and objects
    only, so no scaled number rendering is exercised here.
    """
    entry = {"entry_kind": kind, "form_version": 1,
             "payload": payload, "previous_hash": previous_hash,
             "sequence": sequence}
    return json.dumps(entry, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def chain_lines(payloads, kind="product_registered"):
    """Build a valid chain by hand from the stated rules."""
    lines = []
    previous = None
    for index, payload in enumerate(payloads, start=1):
        line = canonical_line(payload, index, previous, kind=kind)
        lines.append(line)
        previous = hashlib.sha256(line).hexdigest()
    return lines, previous


def full_product_record(name, product_id="p-a"):
    """A full product record from the brief Section 5.2
    field list: product_id, name, canonical_line, domain,
    competitors, aliases, query_set, and category, with the
    optional path_prefix absent where the property stands
    on the host alone."""
    return {"product_id": product_id, "name": name,
            "canonical_line": name + " canonical line",
            "domain": "example.com", "competitors": [],
            "aliases": [], "query_set": [], "category": []}


class HomeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def write_journal(self, lines, trailing_newline=True):
        path = journal.journal_path(self.home)
        with open(path, "wb") as handle:
            for line in lines:
                handle.write(line + b"\n")
            if not trailing_newline:
                handle.seek(-1, os.SEEK_END)
                handle.truncate()
        return path

    def journal_bytes(self):
        with open(journal.journal_path(self.home), "rb") as handle:
            return handle.read()


class Entry14FormTests(HomeCase):
    """The entry 14 form test, pinned in this module on
    entry 14 terms (plan Part 1 Section 2.5, pinning
    condition F-21 at plan Section 1.3 entry S0). No pinning
    moves elsewhere. The vector set covers one entry per
    kind: V-01 to V-10 stand one per each of the ten kinds,
    so no shape identity subset argument is needed."""

    def check_vector(self, vector_id):
        _, kind, text, expected_hash = VECTOR_BY_ID[vector_id]
        stated = text.encode("utf-8")
        self.write_journal([stated])
        result = service.verify(home=self.home)
        self.assertTrue(result["passed"], vector_id)
        entry = journal.read_entry(self.home, 1)
        self.assertEqual(entry["entry_kind"], kind)
        self.assertEqual(journal.canonical_bytes(entry), stated)
        self.assertEqual(journal.entry_hash(entry), expected_hash)
        self.assertEqual(
            hashlib.sha256(stated).hexdigest(), expected_hash)

    def test_v01_product_registered(self):
        """Row plan Section 1.3 S0 entry 14 form, vector V-01.
        Oracle: plan Part 1 Section 2.5 and decision
        D-KF-14-VECTORS, vector V-01."""
        self.check_vector("V-01")

    def test_v02_registry_change(self):
        """Row plan Section 1.3 S0 entry 14 form, vector V-02.
        Oracle: plan Part 1 Section 2.5 and decision
        D-KF-14-VECTORS, vector V-02."""
        self.check_vector("V-02")

    def test_v03_round_named(self):
        """Row plan Section 1.3 S0 entry 14 form, vector V-03.
        Oracle: plan Part 1 Section 2.5 and decision
        D-KF-14-VECTORS, vector V-03."""
        self.check_vector("V-03")

    def test_v04_snapshot_registered(self):
        """Row plan Section 1.3 S0 entry 14 form, vector V-04.
        Oracle: plan Part 1 Section 2.5 and decision
        D-KF-14-VECTORS, vector V-04."""
        self.check_vector("V-04")

    def test_v05_audit_record(self):
        """Row plan Section 1.3 S0 entry 14 form, vector V-05.
        Oracle: plan Part 1 Section 2.5 and decision
        D-KF-14-VECTORS, vector V-05."""
        self.check_vector("V-05")

    def test_v06_answer_imported(self):
        """Row plan Section 1.3 S0 entry 14 form, vector V-06.
        Oracle: plan Part 1 Section 2.5 and decision
        D-KF-14-VECTORS, vector V-06."""
        self.check_vector("V-06")

    def test_v07_guide_record(self):
        """Row plan Section 1.3 S0 entry 14 form, vector V-07.
        Oracle: plan Part 1 Section 2.5 and decision
        D-KF-14-VECTORS, vector V-07."""
        self.check_vector("V-07")

    def test_v08_limit_raise(self):
        """Row plan Section 1.3 S0 entry 14 form, vector V-08.
        Oracle: plan Part 1 Section 2.5 and decision
        D-KF-14-VECTORS, vector V-08."""
        self.check_vector("V-08")

    def test_v09_failure_record(self):
        """Row plan Section 1.3 S0 entry 14 form, vector V-09.
        Oracle: plan Part 1 Section 2.5 and decision
        D-KF-14-VECTORS, vector V-09."""
        self.check_vector("V-09")

    def test_v10_correction(self):
        """Row plan Section 1.3 S0 entry 14 form, vector V-10.
        Oracle: plan Part 1 Section 2.5 and decision
        D-KF-14-VECTORS, vector V-10."""
        self.check_vector("V-10")

    def test_v11_non_ascii_escaping(self):
        """Row plan Section 1.3 S0 entry 14 form, collision
        pair class non ASCII escaping, under the second
        status value (writable after entry 14 lands).
        Oracle: decision D-KF-14-ESC, option (a) minimal
        escaping, every non ASCII character as itself in
        UTF-8, and decision D-KF-14-VECTORS, vector V-11."""
        self.check_vector("V-11")

    def test_v12_null_value(self):
        """Row plan Section 1.3 S0 entry 14 form, vector V-12.
        Oracle: decision D-KF-14-RENDER, a null field renders
        as null, and decision D-KF-14-VECTORS, vector V-12."""
        self.check_vector("V-12")

    def test_v13_empty_list_and_empty_string(self):
        """Row plan Section 1.3 S0 entry 14 form, vector V-13.
        Oracle: decision D-KF-14-RENDER, an empty list renders
        as an empty array and an empty string as an empty
        string, the four forms pairwise distinct, and
        decision D-KF-14-VECTORS, vector V-13."""
        self.check_vector("V-13")

    def test_v14_rounding_edges(self):
        """Row plan Section 1.3 S0 entry 14 form, collision
        pair class rounding edges and bare float forms,
        under the second status value. Oracle: decision
        D-KF-14-NUM, earned at 3 decimal places, score at 1,
        rates at 6, trailing zeros kept, and decision
        D-KF-14-VECTORS, vector V-14."""
        self.check_vector("V-14")

    def test_v15_chain_entry_one_alone(self):
        """Row plan Section 1.3 S0 entry 14 form, vector V-15
        rendering limb. Oracle: decision D-KF-14-VECTORS,
        vector V-15. The chain construction itself stands at
        the V-15 and V-16 pair test below, on Section 2.5
        construction terms. Severance recorded (Step 13
        test audit round 1, entry R1-011): this test is a
        rendering limb outside the Section 2.5 construction,
        which states one home per vector with V-15 and V-16
        together in one home, as auditor 02 records at this
        point in its paper; it pins the V-15 rendering only
        and claims no part of that construction."""
        _, _, text, expected_hash = VECTOR_BY_ID["V-15"]
        stated = text.encode("utf-8")
        self.assertEqual(hashlib.sha256(stated).hexdigest(),
                         expected_hash)
        entry = journal.parse_entry(stated)
        self.assertEqual(journal.canonical_bytes(entry), stated)
        self.assertEqual(journal.entry_hash(entry), expected_hash)

    def test_v15_v16_chain_home(self):
        """Row plan Section 1.3 S0 entry 14 form, two entry
        chain case. Oracle: plan Part 1 Section 2.5
        construction: V-15 and V-16 stand together in one
        home as its two entries, V-15 at sequence 1 and V-16
        at sequence 2, V-16 carrying the expected hash of
        V-15 as its previous_hash, and verify passes."""
        lines = [VECTOR_BY_ID["V-15"][2].encode("utf-8"),
                 VECTOR_BY_ID["V-16"][2].encode("utf-8")]
        self.write_journal(lines)
        result = service.verify(home=self.home)
        self.assertTrue(result["passed"])
        self.assertEqual(result["entry_count"], 2)
        head = service.status(home=self.home)
        self.assertEqual(head["head_hash"], VECTOR_BY_ID["V-16"][3])

    def test_v17_collision_cases(self):
        """Row plan Section 1.3 S0 entry 14 form, collision
        pair class bare float forms, under the second status
        value. Oracle: decision D-KF-14-NUM: 1 renders as an
        integer, a score scale value renders as 1.0, and true
        renders as the literal, so the three forms stand in
        distinct bytes, and decision D-KF-14-VECTORS,
        vector V-17."""
        self.check_vector("V-17")

    def test_v18_negative_zero_integer(self):
        """Row plan Section 1.3 S0 entry 14 form, collision
        pair class negative zero, under the second status
        value. Oracle: decision D-KF-14-NUM, a negative zero
        integer renders as 0, and decision D-KF-14-VECTORS,
        vector V-18."""
        self.check_vector("V-18")

    def test_v19_negative_zero_scaled(self):
        """Row plan Section 1.3 S0 entry 14 form, collision
        pair class negative zero at a non integer scale,
        under the second status value. Oracle: decision
        D-KF-14-NUM, a negative zero at 1 decimal place
        renders as 0.0 with no minus sign, and decision
        D-KF-14-VECTORS, vector V-19."""
        self.check_vector("V-19")

    def test_v20_null_and_absent_in_one_entry(self):
        """Row plan Section 1.3 S0 entry 14 form, vector V-20.
        Oracle: decision D-KF-14-RENDER and decision
        D-KF-14-VECTORS, vector V-20: robots_summary stands
        present with a null value, and section_breakdown
        stands omitted from the one CheckResult the payload
        carries, in a single entry."""
        self.check_vector("V-20")
        entry = journal.read_entry(self.home, 1)
        self.assertIn("robots_summary", entry["payload"])
        self.assertIsNone(entry["payload"]["robots_summary"])
        check = entry["payload"]["checks"][0]
        self.assertNotIn("section_breakdown", check)

    def test_byte_changed_limb_fails_verify(self):
        """Row plan Section 1.3 S0 entry 14 form, byte changed
        limb. Oracle: plan Part 1 Section 2.5: verify fails
        over the vector home with one stated byte changed in
        one stated entry, the changed limb running in the
        home of the vector whose entry stands changed. Run
        here over V-01, V-08, and V-16 in its chain home."""
        _, _, text, _ = VECTOR_BY_ID["V-01"]
        changed = text.replace("Example Product", "Example Producu")
        self.write_journal([changed.encode("utf-8")])
        self.assertFalse(service.verify(home=self.home)["passed"])
        _, _, text8, _ = VECTOR_BY_ID["V-08"]
        changed8 = text8.replace("110000", "110001")
        self.write_journal([changed8.encode("utf-8")])
        self.assertFalse(service.verify(home=self.home)["passed"])
        lines = [VECTOR_BY_ID["V-15"][2].encode("utf-8"),
                 VECTOR_BY_ID["V-16"][2].replace(
                     "Chain answer", "Chain answeq").encode("utf-8")]
        self.write_journal(lines)
        self.assertFalse(service.verify(home=self.home)["passed"])

    def test_collision_pairs_at_construction_point(self):
        """Row plan Section 1.3 S0 entry 14 form, typed
        carriage limb. Oracle: decision D-KF-14-NUM, typed
        carriage at construction: no step carries a hashed
        value through an equality based container in which
        1, 1.0, and true, or a negative zero against a
        positive zero at the same scale, would collapse
        before rendering, and the Step 13 form test tests
        those pairs at that construction point."""
        entry = journal.append_entry(
            self.home, "audit_record",
            {"count": 1, "flag": True, "product_id": "p-example",
             "run_id": "run-4", "score": 1.0},
            audit_date=HOME_DATE)
        line = self.journal_bytes().decode("utf-8")
        self.assertIn('"count":1', line)
        self.assertIn('"flag":true', line)
        self.assertIn('"score":1.0', line)
        self.assertEqual(entry["entry_hash"],
                         VECTOR_BY_ID["V-17"][3])

    def test_key_ordering_unit_is_code_point(self):
        """Row plan Section 1.3 S0 entry 14 form, collision
        pair class ordering unit, under the second status
        value. Oracle: decision D-KF-14-UNIT: object key
        ordering compares by Unicode code point, at every
        nesting level, on plan Part 1 Section 2.1 point 1."""
        entry = {"entry_kind": "product_registered", "form_version": 1,
                 "payload": {"b": 1, "A": 2, "a": 3,
                             "nested": {"z": 1, "m": 2}},
                 "previous_hash": None, "sequence": 1}
        rendered = journal.canonical_bytes(entry).decode("utf-8")
        self.assertLess(rendered.index('"A"'), rendered.index('"a"'))
        self.assertLess(rendered.index('"a"'), rendered.index('"b"'))
        self.assertLess(rendered.index('"m"'), rendered.index('"z"'))


class AppendAtomicityTests(HomeCase):
    def test_append_writes_one_line_with_terminator(self):
        """Row plan Section 1.3 S0 append atomicity, framing
        limb. Oracle: trade T-2 at plan Section 4.6: one
        append only file, one entry per line, each line the
        entry canonical JSON form terminated by one
        newline."""
        journal.append_entry(self.home, "product_registered",
                             {"name": "Example Product",
                              "product_id": "p-example"},
                             audit_date=HOME_DATE)
        data = self.journal_bytes()
        self.assertTrue(data.endswith(b"\n"))
        self.assertEqual(data.count(b"\n"), 1)
        self.assertEqual(data.rstrip(b"\n"),
                         VECTOR_BY_ID["V-01"][2].encode("utf-8"))

    def test_append_complete_only_after_flush(self):
        """Row plan Section 1.3 S0 append atomicity, commit
        protocol limb. Oracle: brief Section 5.12 item 138:
        an append is one complete write of the whole entry
        as a single unit, flushed to storage before the
        append is reported complete. On return, a fresh read
        of the file stands whole. The flush and sync step
        order limb stands recorded as blocked at
        blocked-w1.md row 4, with the missing observation
        seam named there, so this test claims completeness
        on return only (Step 13 test audit round 1, entry
        R1-002)."""
        journal.append_entry(self.home, "round_named",
                             {"product_id": "p-example",
                              "round_id": "p-example:r1",
                              "round_label": "r1"},
                             audit_date=HOME_DATE)
        with open(journal.journal_path(self.home), "rb") as handle:
            data = handle.read()
        self.assertTrue(data.endswith(b"\n"))
        entry = journal.parse_entry(data.rstrip(b"\n"))
        self.assertEqual(entry["sequence"], 1)

    def test_sequence_increases_by_exactly_one(self):
        """Row plan Section 1.3 S0 append atomicity, ordering
        limb. Oracle: contract C7 at plan Section 9 and grill
        Q11: sequence starts at 1 and increases by exactly
        1, and each append links its hash to the prior
        head."""
        first = journal.append_entry(
            self.home, "product_registered",
            {"name": "Example Product", "product_id": "p-example"},
            audit_date=HOME_DATE)
        second = journal.append_entry(
            self.home, "round_named",
            {"product_id": "p-example", "round_id": "p-example:r1",
             "round_label": "r1"}, audit_date=HOME_DATE)
        self.assertEqual((first["sequence"], second["sequence"]), (1, 2))
        self.assertIsNone(first["previous_hash"])
        self.assertEqual(second["previous_hash"], first["entry_hash"])

    def test_failed_append_leaves_head_unchanged(self):
        """Row plan Section 1.3 S0 append atomicity, failure
        limb. Oracle: contract C7 at plan Section 9: an
        append either adds one complete entry or adds
        nothing and leaves the head unchanged, and a failed
        append leaves the head as it was."""
        journal.append_entry(self.home, "product_registered",
                             {"name": "Example Product",
                              "product_id": "p-example"},
                             audit_date=HOME_DATE)
        before = self.journal_bytes()
        with self.assertRaises(journal.JournalError):
            journal.append_entry(self.home, "no_such_kind", {},
                                 audit_date=HOME_DATE)
        self.assertEqual(self.journal_bytes(), before)
        self.assertEqual(service.status(home=self.home)["entry_count"], 1)

    def test_torn_tail_without_holder_fails_verify(self):
        """Row plan Section 1.3 S0 append atomicity, torn tail
        limb one. Oracle: brief Section 5.12 item 138
        provenance test: a final partial line that is not
        the live lock holder own partial write is a torn
        tail, verify reports the chain as failing at the
        torn entry, and appends are barred over a torn
        tail."""
        lines, _ = chain_lines([{"name": "Example Product",
                                 "product_id": "p-example"}])
        self.write_journal(lines)
        with open(journal.journal_path(self.home), "ab") as handle:
            handle.write(b'{"entry_kind":"round_named","form_vers')
        result = service.verify(home=self.home)
        self.assertFalse(result["passed"])
        with self.assertRaises(journal.JournalError):
            journal.append_entry(self.home, "round_named",
                                 {"product_id": "p-example",
                                  "round_id": "p-example:r1",
                                  "round_label": "r1"},
                                 audit_date=HOME_DATE)

    def test_partial_line_of_live_holder_is_not_yet_an_entry(self):
        """Row plan Section 1.3 S0 append atomicity, torn tail
        limb two, and entry 16 reader rule. Oracle: brief
        Section 5.12 item 138 provenance test and decision
        D-KF-16-STALE: a final partial line counts as a
        standing holder append in progress only where it is
        the live lock holder own partial write, the lock
        record naming the holder and the holder pending
        entry standing incomplete at exactly that line, and
        such a line stands treated as not yet an entry, with
        no value read from it. The assertions run on both
        sides of the reader and verify join: status as
        above, verify treating the partial line as not yet
        an entry on the same terms, and a fold based reader
        seeing the last complete entry only (Step 13 test
        audit round 1, entry R1-003). The holder state here
        stands built by holding the write lock itself, with
        no lock record bytes hand written in this test; the
        limb that turns on the lock record spelling stands
        blocked at blocked-w1.md row 5 until the plan states
        the record form (entry R1-006)."""
        import fcntl
        lines, head = chain_lines([{"name": "Example Product",
                                    "product_id": "p-example"}])
        self.write_journal(lines)
        lock_path = os.path.join(self.home, ".citeline-write.lock")
        lock_handle = open(lock_path, "a+")
        self.addCleanup(lock_handle.close)
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with open(journal.journal_path(self.home), "ab") as handle:
            handle.write(b'{"entry_kind":"round_named","form_vers')
        state = service.status(home=self.home)
        self.assertEqual(state["entry_count"], 1)
        self.assertEqual(state["head_hash"], head)
        self.assertFalse(state["chain_fails"])
        result = service.verify(home=self.home)
        self.assertTrue(result["passed"])
        self.assertEqual(result["entry_count"], 1)
        folded = journal.fold(self.home)
        self.assertEqual([e["sequence"] for e in folded], [1])
        self.assertEqual(folded[0]["payload"]["name"],
                         "Example Product")

    def test_tool_never_cuts_the_tail(self):
        """Row plan Section 1.3 S0 append atomicity, torn tail
        recovery limb. Oracle: brief Section 5.12 item 138:
        the tool never cuts the tail, and the failed home
        stands not repaired, truncated, or appended to by
        any version 1 operation, on the verify failure
        regime at plan Section 9."""
        lines, _ = chain_lines([{"name": "Example Product",
                                 "product_id": "p-example"}])
        self.write_journal(lines)
        with open(journal.journal_path(self.home), "ab") as handle:
            handle.write(b'{"partial"')
        before = self.journal_bytes()
        service.verify(home=self.home)
        service.status(home=self.home)
        self.assertEqual(self.journal_bytes(), before)


class VerifyAndStatusTests(HomeCase):
    """Convention note (entry R1-010): the exact result
    field, subkey, and exception spellings pinned in this
    class stand on the suite convention recorded in the
    module header, not on a passage, wherever a test
    docstring oracle passage does not itself state the
    spelling."""

    def test_empty_journal_verify_passes(self):
        """Row plan Section 1.3 S0 hash chain verify, empty
        journal limb. Oracle: brief Section 5.12 item 138
        and contract C7: verify over zero entries passes,
        reporting the chain as empty and intact, with entry
        count 0."""
        self.write_journal([])
        result = service.verify(home=self.home)
        self.assertTrue(result["passed"])
        self.assertEqual(result["entry_count"], 0)

    def test_empty_journal_status_absence_form(self):
        """Row plan Section 1.3 S0 hash chain status, empty
        journal absence form. Oracle: brief Section 5.12
        item 138: over a journal with no entries, status
        prints the stated absence form, the words no
        entries, beside the anchor limit sentence, and
        prints no hash."""
        self.write_journal([])
        state = service.status(home=self.home)
        self.assertEqual(state["head"], "no entries")
        self.assertIsNone(state["head_hash"])
        self.assertEqual(state["entry_count"], 0)
        self.assertIn("anchor", state)

    def test_first_entry_failure_distinct_absence_form(self):
        """Row plan Section 1.3 S0 hash chain status, first
        entry failure limb, severed from the empty form.
        Oracle: brief Section 5.12 item 138: where the
        journal holds entries and fails verify at its first
        entry, status prints for the head the distinct head
        only absence form in these exact words: no head: the
        journal does not recompute from its first entry,
        with the true entry count printed as it stands."""
        line = bytearray(canonical_line(
            {"name": "Example Product", "product_id": "p-example"},
            1, None))
        line[-3] = ord("x")
        self.write_journal([bytes(line)])
        state = service.status(home=self.home)
        self.assertEqual(
            state["head"],
            "no head: the journal does not recompute from its "
            "first entry")
        self.assertEqual(state["entry_count"], 1)
        self.assertTrue(state["chain_fails"])

    def test_sequence_gap_repeat_reorder_fail(self):
        """Row plan Section 1.3 S0 hash chain verify, sequence
        limb. Oracle: brief Section 5.12 item 138 and grill
        Q11: a gap, a repeat, or a reordering of sequence
        values makes verify fail. Three severed cases stand
        in one method as three homes."""
        payload = {"name": "Example Product", "product_id": "p-example"}
        lines, _ = chain_lines([payload, payload, payload])
        gap = [lines[0], lines[2]]
        self.write_journal(gap)
        self.assertFalse(service.verify(home=self.home)["passed"])
        repeat = [lines[0], lines[0]]
        self.write_journal(repeat)
        self.assertFalse(service.verify(home=self.home)["passed"])
        reorder = [lines[1], lines[0], lines[2]]
        self.write_journal(reorder)
        self.assertFalse(service.verify(home=self.home)["passed"])

    def test_hash_link_mismatch_fails(self):
        """Row plan Section 1.3 S0 hash chain verify, link
        limb. Oracle: brief Section 5.12 item 138 and
        contract C7: a hash link that does not recompute
        makes verify fail."""
        lines, _ = chain_lines([{"name": "A", "product_id": "p-a"},
                                {"name": "B", "product_id": "p-b"}])
        broken = lines[1].replace(
            lines[0] and hashlib.sha256(lines[0]).hexdigest().encode(),
            b"0" * 64)
        self.write_journal([lines[0], broken])
        self.assertFalse(service.verify(home=self.home)["passed"])

    def test_genesis_previous_hash_must_be_null(self):
        """Row plan Section 1.3 S0 hash chain verify, genesis
        limb. Oracle: decision D-KF-14-HASHSELF and brief
        Section 5.12 item 138: a sequence 1 entry whose
        previous_hash stands at any value other than the
        JSON value null fails verify, at every journal
        length, including a journal of exactly one entry."""
        line = canonical_line({"name": "A", "product_id": "p-a"},
                              1, "0" * 64)
        self.write_journal([line])
        self.assertFalse(service.verify(home=self.home)["passed"])

    def test_noncanonical_spelling_fails_at_last_entry(self):
        """Row plan Section 1.3 S0 hash chain verify,
        canonical rendering comparison limb. Oracle:
        decision D-KF-14-RENDER: verify parses each stored
        line, renders the parsed entry, and compares the
        rendered bytes against the stored bytes, at every
        chain position including the last entry, so a line
        with extra spaces around a separator fails verify
        even where it parses to the same object."""
        lines, _ = chain_lines([{"name": "A", "product_id": "p-a"}])
        spaced = lines[0].replace(b'"sequence":1', b'"sequence": 1')
        self.write_journal([spaced])
        self.assertFalse(service.verify(home=self.home)["passed"])

    def test_form_version_three_cases_fail_on_i2(self):
        """Row plan Section 1.3 S0 hash chain verify, form
        version limb, three severed cases. Oracle: decision
        D-KF-14-VERSION and brief Section 5.12 item 138: a
        stored line whose form_version stands absent, at a
        value other than 1, or in a non integer form fails
        verify as an integrity failure, reported on row I-2
        with error value 5."""
        good = json.loads(canonical_line(
            {"name": "A", "product_id": "p-a"}, 1, None))
        for mutate in (
                lambda e: e.pop("form_version"),
                lambda e: e.update(form_version=2),
                lambda e: e.update(form_version="1")):
            entry = json.loads(json.dumps(good))
            mutate(entry)
            line = json.dumps(entry, ensure_ascii=False,
                              sort_keys=True,
                              separators=(",", ":")).encode("utf-8")
            self.write_journal([line])
            result = service.verify(home=self.home)
            self.assertFalse(result["passed"])
            self.assertEqual(result["error_value"], 5)
            self.assertEqual(result["row"], "I-2")

    def test_depth_100_passes_101_fails(self):
        """Row plan Section 1.3 S0 hash chain verify, depth
        limb, two severed bounds. Oracle: decision
        D-KF-14-RENDER and brief limit 18: the outermost
        container counts as depth 1, a deepest container
        chain at 100 passes the depth limb, and at 101 it
        breaches it and verify fails. Container count
        (Step 13 test audit round 1, entry R1-012): the
        entry object plus the payload object plus the
        nested lists give the deepest chain, so the loop
        parameter 98 gives a chain of 100 and the loop
        parameter 99 gives a chain of 101, and the named
        bounds and the parameters agree."""

        def nested(depth):
            value = 0
            for _ in range(depth):
                value = [value]
            return value

        for depth, expected in ((98, True), (99, False)):
            payload = {"name": "A", "product_id": "p-a",
                       "nest": nested(depth)}
            lines, _ = chain_lines([payload])
            self.write_journal(lines)
            self.assertEqual(
                service.verify(home=self.home)["passed"], expected,
                "payload nesting %d" % depth)

    def test_duplicate_key_line_fails(self):
        """Row plan Section 1.3 S0 hash chain verify,
        duplicate key limb. Oracle: decision D-KF-14-RENDER:
        an object holding a duplicate key is not a canonical
        form, and verify fails over it."""
        line = (b'{"entry_kind":"product_registered",'
                b'"entry_kind":"product_registered",'
                b'"form_version":1,"payload":{},'
                b'"previous_hash":null,"sequence":1}')
        self.write_journal([line])
        self.assertFalse(service.verify(home=self.home)["passed"])

    def test_verify_and_status_change_no_entry(self):
        """Row plan Section 1.3 S0 hash chain verify and
        status, purity limb. Oracle: contract C7 at plan
        Section 9: verify and status change no entry,
        whether they pass or fail."""
        lines, _ = chain_lines([{"name": "A", "product_id": "p-a"}])
        self.write_journal(lines)
        before = self.journal_bytes()
        service.verify(home=self.home)
        service.status(home=self.home)
        self.assertEqual(self.journal_bytes(), before)

    def test_status_fields_and_no_last_verify_result(self):
        """Row plan Section 1.3 S0 status fields. Oracle:
        plan Section 5.1 status and verify fields, item 128:
        head hash or its absence form, entry count, home
        size, home path, capacity outlook figures, and
        anchor figures stand as status fields, and the last
        verify result is not a status field."""
        lines, head = chain_lines([{"name": "A", "product_id": "p-a"}])
        self.write_journal(lines)
        state = service.status(home=self.home)
        self.assertEqual(state["head_hash"], head)
        self.assertEqual(state["entry_count"], 1)
        self.assertEqual(state["home_path"], self.home)
        self.assertIn("home_size", state)
        self.assertIn("capacity_outlook", state)
        self.assertIn("anchor", state)
        self.assertNotIn("last_verify_result", state)

    def test_status_over_failed_journal_reports_and_returns(self):
        """Row plan Section 1.3 S0 status, barred chain
        regime limb. Oracle: plan Section 9 verify failure
        regime: status runs and reports the failure,
        printing the head of the last entry whose link
        recomputes, stating that the chain fails verify, and
        status returns 0 in that case, row I-2 not standing
        as the status call own error value."""
        lines, head = chain_lines([{"name": "A", "product_id": "p-a"},
                                   {"name": "B", "product_id": "p-b"}])
        broken = bytearray(lines[1])
        broken[-3] = ord("x")
        self.write_journal([lines[0], bytes(broken)])
        state = service.status(home=self.home)
        self.assertTrue(state["chain_fails"])
        self.assertEqual(state["head_hash"], head.replace(
            head, hashlib.sha256(lines[0]).hexdigest()))
        self.assertEqual(state["exit_code"], 0)

    def test_barred_chain_refuses_appends_and_records_nothing(self):
        """Row plan Section 1.3 S0 hash chain, barred chain
        regime. Oracle: plan Section 9 verify failure
        regime: audit, registry writes, round naming, and
        import stand barred over a journal that does not
        recompute, fail with a recorded error, and store
        nothing, and over a barred chain no failure record
        can be appended, the recorded error standing as
        caller response only."""
        lines, _ = chain_lines([{"name": "A", "product_id": "p-a"}])
        broken = bytearray(lines[0])
        broken[-3] = ord("x")
        self.write_journal([bytes(broken)])
        before = self.journal_bytes()
        with self.assertRaises(journal.JournalError):
            journal.append_entry(self.home, "round_named",
                                 {"product_id": "p-a",
                                  "round_id": "p-a:r1",
                                  "round_label": "r1"},
                                 audit_date=HOME_DATE)
        self.assertEqual(self.journal_bytes(), before)


class FoldTests(HomeCase):
    def test_fold_yields_entries_in_sequence_order(self):
        """Row plan Section 1.3 S0 fold correctness. Oracle:
        brief Section 5.12 item 138: projections and
        listings are folds over journal entries, and the
        fold runs over the journal as it stands, in
        sequence."""
        journal.append_entry(self.home, "product_registered",
                             {"name": "A", "product_id": "p-a"},
                             audit_date=HOME_DATE)
        journal.append_entry(self.home, "round_named",
                             {"product_id": "p-a", "round_id": "p-a:r1",
                              "round_label": "r1"}, audit_date=HOME_DATE)
        folded = journal.fold(self.home)
        self.assertEqual([e["sequence"] for e in folded], [1, 2])
        self.assertEqual([e["entry_kind"] for e in folded],
                         ["product_registered", "round_named"])

    def test_record_with_no_entry_does_not_exist(self):
        """Row plan Section 1.3 S0 fold correctness, absence
        limb. Oracle: brief Section 5.12 item 138: a record
        no entry folds to does not exist for any reader, and
        no divergence can stand past that read."""
        self.assertEqual(journal.fold(self.home), [])
        journal.append_entry(self.home, "product_registered",
                             {"name": "A", "product_id": "p-a"},
                             audit_date=HOME_DATE)
        products = journal.fold(self.home, kinds=["product_registered"])
        self.assertEqual(len(products), 1)
        self.assertEqual(
            journal.fold(self.home, kinds=["audit_record"]), [])

    def test_fold_to_a_stated_point(self):
        """Row plan Section 1.3 S0 fold correctness, fold
        point limb. Oracle: plan Section 5.2: the fold point
        is stated as a point, a named journal sequence, and
        the fold to that point yields the entries up to
        it."""
        for label in ("r1", "r2", "r3"):
            journal.append_entry(
                self.home, "round_named",
                {"product_id": "p-a", "round_id": "p-a:" + label,
                 "round_label": label}, audit_date=HOME_DATE)
        folded = journal.fold(self.home, to_sequence=2)
        self.assertEqual([e["sequence"] for e in folded], [1, 2])

    def test_correction_governs_reporting_and_superseded_stays(self):
        """Row plan Section 1.3 S0 fold correctness,
        correction limb. Oracle: brief Section 5.12 item
        138: the correction entry governs reporting from
        its append, reporting follows the correction, while
        the superseded entry stays readable."""
        journal.append_entry(
            self.home, "product_registered",
            full_product_record("Old Name"), audit_date=HOME_DATE)
        journal.append_entry(
            self.home, "correction",
            {"supersedes_sequence": 1,
             "corrected_record": full_product_record("New Name")},
            audit_date=HOME_DATE)
        raw = journal.fold(self.home)
        self.assertEqual(len(raw), 2)
        self.assertEqual(raw[0]["payload"]["name"], "Old Name")
        reported = journal.fold(self.home, apply_corrections=True)
        names = [e["payload"].get("name") for e in reported
                 if e["entry_kind"] == "product_registered"]
        self.assertEqual(names, ["New Name"])
        corrected = [e["payload"] for e in reported
                     if e["entry_kind"] == "product_registered"]
        self.assertEqual(corrected,
                         [full_product_record("New Name")])

    def test_registry_change_applies_full_record_at_its_sequence(self):
        """Row plan Section 1.3 S0 fold correctness, registry
        limb. Oracle: plan Section 5.2: a registry_change
        entry payload carries the registry record as changed
        in full record form, so the fold applies that record
        directly at the entry sequence, and the corrected
        record stands in place for every later point."""
        journal.append_entry(
            self.home, "product_registered",
            full_product_record("A"), audit_date=HOME_DATE)
        journal.append_entry(
            self.home, "registry_change",
            full_product_record("A Two"), audit_date=HOME_DATE)
        state = journal.fold_registry(self.home)
        self.assertEqual(state["p-a"]["name"], "A Two")
        self.assertEqual(state["p-a"],
                         full_product_record("A Two"))
        early = journal.fold_registry(self.home, to_sequence=1)
        self.assertEqual(early["p-a"]["name"], "A")
        self.assertEqual(early["p-a"], full_product_record("A"))


LIMIT_DEFAULTS = {
    "page_file_size": 2, "answer_file_size": 1,
    "extracted_text_length_per_page_or_answer": 500000,
    "element_or_tag_events_per_page": 100000, "nesting_depth": 100,
    "attributes_per_element": 100, "attribute_value_length": 10000,
    "link_count_per_page": 10000, "heading_count_per_page": 10000,
    "reference_definitions_per_file": 10000,
    "front_matter_block_size": 16, "front_matter_key_count": 100,
    "front_matter_anchor_count": 20,
    "front_matter_alias_use_count": 100,
    "front_matter_nesting_depth_of_anchored_values": 10,
    "front_matter_size_after_alias_expansion": 64,
    "front_matter_value_length_per_key": 4096,
    "json_nesting_depth": 100, "evidence_excerpt_length": 120,
    "evidence_spans_per_check": 20, "evidence_spans_per_report": 200,
    "answers_per_round": 10000, "products_per_home": 1000,
    "competitors_per_product": 100, "aliases_per_product": 100,
    "aliases_per_competitor": 100, "queries_per_product": 1000,
    "product_name_length": 200, "engine_label_length": 200,
    "round_label_length": 200, "capture_method_text_length": 2000,
    "query_text_length": 2000, "error_message_length": 500,
    "robots_file_total_size": 512, "robots_line_length": 10000,
    "robots_group_count": 1000, "robots_rules_per_group": 10000,
    "robots_path_argument_length": 2000, "journal_length": 100000,
    "total_home_size": 1, "per_run_wall_clock_backstop": 120,
    "per_file_parse_time": 30,
}


class LimitsPlumbingTests(HomeCase):
    def test_all_42_defaults_stand_in_force(self):
        """Row plan Section 1.3 S0 limits plumbing over the
        42 brief limits as a shared guard. Oracle: brief
        Section 5.11, the 42 limits in order, each a local
        default in the unit its row states, and plan Part 1
        Section 3.1: the values in force with no config file
        stand at the brief defaults."""
        limits = journal.effective_limits(self.home)
        for key, expected in LIMIT_DEFAULTS.items():
            self.assertEqual(limits[key]["value"], expected, key)
            self.assertEqual(limits[key]["source"], "brief default", key)
        self.assertEqual(len([k for k in limits
                              if k in LIMIT_DEFAULTS]), 42)

    def test_journal_length_cap_refuses_without_truncation(self):
        """Row plan Section 1.3 S0 limits plumbing, limit 39
        limb. Oracle: brief Section 5.11 limit 39 and item
        138: refusal at the cap, never truncation, with the
        cap value taken from the config in force, so a
        lowered cap binds at its lowered value."""
        journal.write_config(self.home, "journal_length = 3\n")
        for index in range(3):
            journal.append_entry(
                self.home, "round_named",
                {"product_id": "p-a",
                 "round_id": "p-a:r%d" % index,
                 "round_label": "r%d" % index}, audit_date=HOME_DATE)
        before = self.journal_bytes()
        with self.assertRaises(journal.JournalError):
            journal.append_entry(
                self.home, "round_named",
                {"product_id": "p-a", "round_id": "p-a:r3",
                 "round_label": "r3"}, audit_date=HOME_DATE)
        self.assertEqual(self.journal_bytes(), before)
        self.assertTrue(service.verify(home=self.home)["passed"])

    def test_at_cap_no_failure_record_and_reads_still_run(self):
        """Row plan Section 1.3 S0 limits plumbing, cap
        signal limb. Oracle: plan Section 5.1 failure record
        entry and brief Section 5.11: at the cap no failure
        record can be appended, the recorded error stands as
        caller response only, and that absence is the stated
        signal, while verify and status still run at the
        cap."""
        journal.write_config(self.home, "journal_length = 1\n")
        journal.append_entry(self.home, "product_registered",
                             {"name": "A", "product_id": "p-a"},
                             audit_date=HOME_DATE)
        with self.assertRaises(journal.JournalError):
            journal.append_entry(self.home, "round_named",
                                 {"product_id": "p-a",
                                  "round_id": "p-a:r1",
                                  "round_label": "r1"},
                                 audit_date=HOME_DATE)
        kinds = [e["entry_kind"] for e in journal.fold(self.home)]
        self.assertNotIn("failure_record", kinds)
        self.assertTrue(service.verify(home=self.home)["passed"])
        self.assertEqual(service.status(home=self.home)["entry_count"], 1)

    def test_home_size_cap_and_capacity_outlook(self):
        """Row plan Section 1.3 S0 limits plumbing, limit 40
        limb and outlook limb. Oracle: brief Section 5.11:
        any append that would exceed either cap is refused,
        with no append kind excepted, the refusal scope
        covering limits 39 and 40 alike on row I-1 terms at
        plan Part 1 Section 1.2; and plan slice S10 with
        IM2-BRK-18: status carries a capacity outlook
        attributing remaining capacity by entry kind. The
        byte level refusal route for limit 40 stands at the
        same row I-1 as limit 39, whose lowered value route
        the cap tests above exercise; no config key states a
        byte unit for row 40, on decision D-KF-15-RANGE unit
        terms, so no lowered byte cap test stands written
        here. The limit 40 refusal limb stands recorded as
        blocked at blocked-w1.md row 3, with the route gap
        named there, so this test does not claim it as
        pinned (Step 13 test audit round 1, entry R1-001)."""
        journal.write_config(self.home, "journal_length = 2\n")
        journal.append_entry(self.home, "product_registered",
                             {"name": "A", "product_id": "p-a"},
                             audit_date=HOME_DATE)
        state = service.status(home=self.home)
        outlook = state["capacity_outlook"]
        self.assertEqual(outlook["journal_length_remaining"], 1)
        self.assertIn("total_home_size_remaining", outlook)
        journal.append_entry(self.home, "guide_record",
                             {"product_id": "p-a", "refused": False},
                             audit_date=HOME_DATE)
        with self.assertRaises(journal.JournalError) as caught:
            journal.append_entry(self.home, "round_named",
                                 {"product_id": "p-a",
                                  "round_id": "p-a:r1",
                                  "round_label": "r1"},
                                 audit_date=HOME_DATE)
        self.assertEqual(caught.exception.row, "I-1")

    def test_limit_raise_entry_raises_for_its_run(self):
        """Row plan Section 1.3 S0 limits plumbing, raise
        limb. Oracle: decision D-KF-15-PREC: a limit_raise
        journal entry for a run overrides the config value
        for that run only, for the one limit it names, and
        limits_in_force names the source of each value in
        force, config or raise, beside the value."""
        journal.write_config(self.home, "journal_length = 3\n")
        journal.append_entry(
            self.home, "limit_raise",
            {"limit": "limit_39", "brief_value": 100000,
             "raised_value": 5, "run_id": "run-1"},
            audit_date=HOME_DATE)
        limits = journal.effective_limits(self.home, run_id="run-1")
        self.assertEqual(limits["journal_length"]["value"], 5)
        self.assertEqual(limits["journal_length"]["source"], "raise")
        other = journal.effective_limits(self.home, run_id="run-2")
        self.assertEqual(other["journal_length"]["value"], 3)
        self.assertEqual(other["journal_length"]["source"], "config")


EXPECTED_KEYS = [
    "page_file_size", "answer_file_size",
    "extracted_text_length_per_page_or_answer",
    "element_or_tag_events_per_page", "nesting_depth",
    "attributes_per_element", "attribute_value_length",
    "link_count_per_page", "heading_count_per_page",
    "reference_definitions_per_file", "front_matter_block_size",
    "front_matter_key_count", "front_matter_anchor_count",
    "front_matter_alias_use_count",
    "front_matter_nesting_depth_of_anchored_values",
    "front_matter_size_after_alias_expansion",
    "front_matter_value_length_per_key", "json_nesting_depth",
    "evidence_excerpt_length", "evidence_spans_per_check",
    "evidence_spans_per_report", "answers_per_round",
    "products_per_home", "competitors_per_product",
    "aliases_per_product", "aliases_per_competitor",
    "queries_per_product", "product_name_length",
    "engine_label_length", "round_label_length",
    "capture_method_text_length", "query_text_length",
    "error_message_length", "robots_file_total_size",
    "robots_line_length", "robots_group_count",
    "robots_rules_per_group", "robots_path_argument_length",
    "journal_length", "total_home_size",
    "per_run_wall_clock_backstop", "per_file_parse_time",
    "home_path", "anchor_path",
]


class ConfigSurfaceTests(HomeCase):
    """Convention note (entry R1-010): the exact key,
    source string, and exception spellings pinned in this
    class stand on the suite convention recorded in the
    module header, not on a passage, wherever a test
    docstring oracle passage does not itself state the
    spelling."""

    def test_key_table_count_is_exactly_44(self):
        """Row plan Section 1.3 S0 config surface, pinning
        condition F-22 count limb. Oracle: plan Part 1
        Section 3.1 completeness trace and decision
        D-KF-15-STRING: 42 limit keys against the 42 limits,
        plus the home key and the anchor key, 44 rows in
        total, verified here as a count."""
        keys = journal.config_keys()
        self.assertEqual(len(keys), 44)
        self.assertEqual(len(set(keys)), 44)

    def test_key_strings_exact_and_no_watch_key(self):
        """Row plan Section 1.3 S0 config surface, string
        limb. Oracle: decision D-KF-15-STRING, the 44 exact
        strings in table order, and plan Part 1 Section 3.4:
        no watch key stands in this table, and the count
        stands at exactly 44 with watch scoped."""
        self.assertEqual(journal.config_keys(), EXPECTED_KEYS)

    def test_absent_config_file_selects_defaults_and_is_named(self):
        """Row plan Section 1.3 S0 config surface, absence
        limb. Oracle: plan Part 1 Section 3.2 points 2 and
        3: where no config file stands at a run start, the
        run proceeds with every key at its brief value
        default, and the run record names the config file
        as absent."""
        run = journal.start_run(self.home, run_id="run-1",
                                audit_date=HOME_DATE)
        self.assertEqual(run["config_file"], "absent")
        limits = journal.effective_limits(self.home, run_id="run-1")
        self.assertEqual(limits["journal_length"]["value"], 100000)

    def test_valid_config_parses_in_stated_syntax(self):
        """Row plan Section 1.3 S0 config surface, syntax
        limb. Oracle: decision D-KF-15-SYNTAX: one key, one
        space, an equals sign, one space, and the value, per
        line, each line ending in one newline; a blank line
        is ignored, and a line whose first character is the
        hash character is a comment and is ignored."""
        values, warnings = journal.parse_config(
            "# note\n\njournal_length = 5000\npage_file_size = 2\n")
        self.assertEqual(values["journal_length"], 5000)
        self.assertEqual(values["page_file_size"], 2)
        self.assertEqual(warnings, [])

    def test_unknown_key_is_a_warning_not_a_failure(self):
        """Row plan Section 1.3 S0 config surface, unknown key
        limb. Oracle: plan Part 1 Section 3.2 point 4: an
        unknown key is reported as a warning and is not a
        failure."""
        values, warnings = journal.parse_config("no_such_key = 3\n")
        self.assertEqual(len(warnings), 1)
        self.assertIn("no_such_key", warnings[0])

    def test_unparsable_line_fails_on_x1(self):
        """Row plan Section 1.3 S0 config surface, failure
        outcome one. Oracle: decision D-KF-15-SYNTAX and row
        X-1: any line form outside the stated syntax cannot
        be parsed and fails under row X-1, and a config file
        that cannot be parsed is never silently defaulted,
        on plan Part 1 Section 3.2 point 5."""
        with self.assertRaises(journal.ConfigError) as caught:
            journal.parse_config("journal_length 5000\n")
        self.assertEqual(caught.exception.row, "X-1")

    def test_wrong_form_value_fails_on_x1(self):
        """Row plan Section 1.3 S0 config surface, failure
        outcome two. Oracle: plan Part 1 Section 3.2 point 5
        and decision D-KF-15-RANGE: a value of the wrong
        form for its key fails under row X-1."""
        with self.assertRaises(journal.ConfigError) as caught:
            journal.parse_config("journal_length = many\n")
        self.assertEqual(caught.exception.row, "X-1")

    def test_duplicate_key_fails_on_x1(self):
        """Row plan Section 1.3 S0 config surface, failure
        outcome three. Oracle: decision D-KF-15-SYNTAX: a
        repeated key is a duplicate key and fails under row
        X-1. The three failure outcomes decide mechanically
        from the stated syntax, on pinning condition F-22."""
        with self.assertRaises(journal.ConfigError) as caught:
            journal.parse_config(
                "journal_length = 5\njournal_length = 6\n")
        self.assertEqual(caught.exception.row, "X-1")

    def test_two_spaces_before_equals_fails(self):
        """Row plan Section 1.3 S0 config surface, named
        spacing variant one. Oracle: decision D-KF-15-SYNTAX:
        the Step 13 config tests pin the two interior
        spacing variants by name, two spaces before the
        equals sign, each failing under row X-1."""
        with self.assertRaises(journal.ConfigError):
            journal.parse_config("journal_length  = 5000\n")

    def test_two_spaces_after_equals_fails(self):
        """Row plan Section 1.3 S0 config surface, named
        spacing variant two. Oracle: decision D-KF-15-SYNTAX:
        two spaces after the equals sign fails under
        row X-1."""
        with self.assertRaises(journal.ConfigError):
            journal.parse_config("journal_length =  5000\n")

    def test_no_inline_comment_form(self):
        """Row plan Section 1.3 S0 config surface, comment
        limb. Oracle: decision D-KF-15-SYNTAX: no inline
        comment form exists, so trailing comment text stands
        in the value and a numeric key then holds a wrong
        form value under row X-1."""
        with self.assertRaises(journal.ConfigError):
            journal.parse_config("journal_length = 5000 # note\n")

    def test_zero_and_ceiling_and_backstop_range_rules(self):
        """Row plan Section 1.3 S0 config surface, range
        limb, three severed rules. Oracle: decision
        D-KF-15-RANGE: a minimum of 1 for every row of 1 to
        42, so zero stands refused as a wrong form value; a
        hard ceiling of ten times the brief default for rows
        1 to 40; and rows 41 and 42 take a ceiling equal to
        their brief default, so config may lower a backstop
        and may not raise one."""
        with self.assertRaises(journal.ConfigError):
            journal.parse_config("journal_length = 0\n")
        with self.assertRaises(journal.ConfigError):
            journal.parse_config("journal_length = 1000001\n")
        values, _ = journal.parse_config("journal_length = 1000000\n")
        self.assertEqual(values["journal_length"], 1000000)
        with self.assertRaises(journal.ConfigError):
            journal.parse_config("per_run_wall_clock_backstop = 121\n")
        values, _ = journal.parse_config(
            "per_run_wall_clock_backstop = 119\n")
        self.assertEqual(values["per_run_wall_clock_backstop"], 119)

    def test_size_value_stands_in_the_row_unit(self):
        """Row plan Section 1.3 S0 config surface, unit limb.
        Oracle: decision D-KF-15-RANGE: a config value at a
        size row stands in that row stated size unit, not in
        bytes, so a value of 2 at row 1 stands as 2 MiB."""
        journal.write_config(self.home, "page_file_size = 3\n")
        limits = journal.effective_limits(self.home)
        self.assertEqual(limits["page_file_size"]["value"], 3)
        self.assertEqual(limits["page_file_size"]["unit"], "MiB")

    def test_forced_dependencies(self):
        """Row plan Section 1.3 S0 config surface, dependency
        limb, two severed pairs. Oracle: decision
        D-KF-15-RANGE: front_matter_size_after_alias_expansion
        stands at or above front_matter_block_size, and
        evidence_spans_per_report stands at or above
        evidence_spans_per_check, a breach of either standing
        as a wrong form value under row X-1."""
        with self.assertRaises(journal.ConfigError):
            journal.parse_config(
                "front_matter_block_size = 32\n"
                "front_matter_size_after_alias_expansion = 16\n")
        with self.assertRaises(journal.ConfigError):
            journal.parse_config(
                "evidence_spans_per_check = 30\n"
                "evidence_spans_per_report = 20\n")

    def test_anchor_path_inside_home_refused_on_x2(self):
        """Row plan Section 1.3 S0 config surface, anchor
        limb. Oracle: plan Part 1 Section 3.2 point 8 and
        row X-2: config validation refuses an anchor path
        inside the product home, with a recorded error."""
        inside = os.path.join(self.home, "anchor.txt")
        with self.assertRaises(journal.ConfigError) as caught:
            journal.parse_config("anchor_path = %s\n" % inside,
                                 home=self.home)
        self.assertEqual(caught.exception.row, "X-2")

    def test_second_raise_same_limit_same_run_refused(self):
        """Row plan Section 1.3 S0 config surface, precedence
        limb one. Oracle: decision D-KF-15-PREC and row
        X-11: a second limit_raise for the same limit in the
        same run is refused as a usage error, token
        LIMIT_RAISE_REPEATED, and no second raise stands
        appended for that limit in that run."""
        journal.append_entry(
            self.home, "limit_raise",
            {"limit": "limit_39", "brief_value": 100000,
             "raised_value": 110000, "run_id": "run-1"},
            audit_date=HOME_DATE)
        before = self.journal_bytes()
        with self.assertRaises(journal.JournalError) as caught:
            journal.append_entry(
                self.home, "limit_raise",
                {"limit": "limit_39", "brief_value": 100000,
                 "raised_value": 120000, "run_id": "run-1"},
                audit_date=HOME_DATE)
        self.assertEqual(caught.exception.token,
                         "LIMIT_RAISE_REPEATED")
        self.assertEqual(self.journal_bytes(), before)

    def test_precedence_does_not_arise_on_a_barred_chain(self):
        """Row plan Section 1.3 S0 config surface, precedence
        limb two, the barred chain case stated beside the
        precedence rule. Oracle: decision D-KF-15-PREC: on a
        barred chain no writing invocation runs, so no raise
        can be appended and the precedence question does not
        arise."""
        lines, _ = chain_lines([{"name": "A", "product_id": "p-a"}])
        broken = bytearray(lines[0])
        broken[-3] = ord("x")
        self.write_journal([bytes(broken)])
        before = self.journal_bytes()
        with self.assertRaises(journal.JournalError):
            journal.append_entry(
                self.home, "limit_raise",
                {"limit": "limit_39", "brief_value": 100000,
                 "raised_value": 110000, "run_id": "run-1"},
                audit_date=HOME_DATE)
        self.assertEqual(self.journal_bytes(), before)

    def test_limit_member_form_names_the_row_limit(self):
        """Row plan Section 1.3 S0 config surface, limit
        member limb. Oracle: decision D-KF-15-PREC: the
        limit member of a limit_raise entry takes the form
        limit_N, where N is the limit number in the
        Section 5.11 order, so limit_39 names journal_length,
        and rows 43 and 44, the home and anchor keys, are
        not limits and take no limit_N form."""
        self.assertEqual(journal.limit_for_member("limit_39"),
                         "journal_length")
        self.assertEqual(journal.limit_for_member("limit_1"),
                         "page_file_size")
        with self.assertRaises(journal.ConfigError):
            journal.limit_for_member("limit_43")


class ConcurrencyTests(HomeCase):
    def hold_lock(self):
        import fcntl
        lock_path = os.path.join(self.home, ".citeline-write.lock")
        handle = open(lock_path, "a+")
        self.addCleanup(handle.close)
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        handle.write("holder pid %d\n" % os.getpid())
        handle.flush()
        return handle

    def test_contention_fails_and_leaves_no_failure_record(self):
        """Row plan Section 1.3 S0 concurrency exclusion,
        entry 16 named test contention. Oracle: plan Part 1
        Section 6.1 point 2 and decision D-KF-16-MECH: a
        contended writing invocation fails with a recorded
        error, stores nothing, and leaves no failure record,
        the recorded error standing as the caller response
        only, on row X-10."""
        journal.append_entry(self.home, "product_registered",
                             {"name": "A", "product_id": "p-a"},
                             audit_date=HOME_DATE)
        self.hold_lock()
        before = self.journal_bytes()
        with self.assertRaises(journal.JournalError) as caught:
            journal.append_entry(self.home, "round_named",
                                 {"product_id": "p-a",
                                  "round_id": "p-a:r1",
                                  "round_label": "r1"},
                                 audit_date=HOME_DATE)
        self.assertEqual(caught.exception.row, "X-10")
        self.assertEqual(self.journal_bytes(), before)
        kinds = [line for line in before.splitlines()
                 if b"failure_record" in line]
        self.assertEqual(kinds, [])

    def test_contention_applies_to_a_guide_record_append(self):
        """Row plan Section 1.3 S0 concurrency exclusion,
        guide limb. Oracle: plan Part 1 Section 6.1 point 4:
        a guide call is a writing invocation under this
        rule, because it appends a guide_record, so the
        contention terms reach a guide_record append on the
        same terms as any other kind."""
        self.hold_lock()
        with self.assertRaises(journal.JournalError):
            journal.append_entry(self.home, "guide_record",
                                 {"product_id": "p-a", "refused": False},
                                 audit_date=HOME_DATE)
        self.assertFalse(os.path.exists(journal.journal_path(self.home)))

    def test_stale_holder_lock_file_presence_bars_nothing(self):
        """Row plan Section 1.3 S0 concurrency exclusion,
        entry 16 named test stale holder. Oracle: decision
        D-KF-16-STALE: no stale holder recovery act exists,
        the operating system releases the lock when the
        holder process ends, the lock file presence on disk
        after a holder ends is not evidence of a holder and
        bars nothing, and a lock file left in the home is an
        ordinary file the next writing invocation opens for
        its own lock attempt."""
        lock_path = os.path.join(self.home, ".citeline-write.lock")
        with open(lock_path, "w") as handle:
            handle.write("holder pid 999999\n")
        entry = journal.append_entry(
            self.home, "product_registered",
            {"name": "A", "product_id": "p-a"}, audit_date=HOME_DATE)
        self.assertEqual(entry["sequence"], 1)
        self.assertTrue(service.verify(home=self.home)["passed"])

    def test_lock_unavailable_fails_closed_on_x12(self):
        """Row plan Section 1.3 S0 concurrency exclusion,
        fail closed limb. Oracle: decision D-KF-16-MECH and
        row X-12: on a platform or filesystem that cannot
        give the lock, a writing invocation fails closed
        under row X-12, token LOCK_UNAVAILABLE, with a
        recorded error, and writes nothing. The test stands
        in form on a home whose lock file path stands
        occupied by a directory, so no lock file can be
        opened there."""
        os.makedirs(os.path.join(self.home, ".citeline-write.lock"))
        with self.assertRaises(journal.JournalError) as caught:
            journal.append_entry(self.home, "product_registered",
                                 {"name": "A", "product_id": "p-a"},
                                 audit_date=HOME_DATE)
        self.assertEqual(caught.exception.row, "X-12")
        self.assertEqual(caught.exception.token, "LOCK_UNAVAILABLE")
        self.assertFalse(os.path.exists(journal.journal_path(self.home)))


class AppendCostTests(HomeCase):
    """Convention note (entry R1-010): the exact field and
    subkey spellings pinned in this class stand on the
    suite convention recorded in the module header, not on
    a passage, wherever a test docstring oracle passage
    does not itself state the spelling."""

    def test_append_cost_table_names_each_writing_kind(self):
        """Row plan Section 1.3 S0 append cost statement per
        writing invocation kind. Oracle: plan slice S0,
        append cost per writing invocation kind stated beside
        the framing on IM2-BRK-18 scoped limb, and contract
        C7 at plan Section 9: the appending operations are
        import, registry writes, round naming, audit, and
        guide, and each appends its subject entry as one
        entry."""
        table = journal.append_cost()
        for kind in ("import", "registry_write", "round_naming",
                     "audit", "guide"):
            self.assertIn(kind, table)
            self.assertEqual(table[kind]["subject_entries"], 1, kind)

    def test_repeat_guide_calls_each_cost_one_entry(self):
        """Row plan Section 1.3 S0 append cost, repeat guide
        limb. Oracle: trade T-9 at plan Section 4.6: a repeat
        guide call over an unchanged record appends a new
        guide_record, with no no-op form, so two calls cost
        two entries."""
        journal.append_entry(self.home, "guide_record",
                             {"product_id": "p-a", "refused": False},
                             audit_date=HOME_DATE)
        journal.append_entry(self.home, "guide_record",
                             {"product_id": "p-a", "refused": False},
                             audit_date=HOME_DATE)
        self.assertEqual(service.status(home=self.home)["entry_count"], 2)



class ReplayPairTests(HomeCase):
    def test_replay_from_empty_to_a_stated_head_hash(self):
        """Row plan Section 1.3 S0 replay pair, limb one,
        under the second status value, writable after entry
        14 lands. Oracle: plan slice S0 test status and
        Section 1.3 entry S0: replay from empty to a stated
        head hash, the stated hash here standing as the
        V-16 expected hash of decision D-KF-14-VECTORS."""
        entries = [VECTOR_BY_ID["V-15"][2].encode("utf-8"),
                   VECTOR_BY_ID["V-16"][2].encode("utf-8")]
        head = journal.replay(self.home, entries)
        self.assertEqual(head, VECTOR_BY_ID["V-16"][3])
        self.assertTrue(service.verify(home=self.home)["passed"])

    def test_replay_from_mid_chain_with_correction_same_head(self):
        """Row plan Section 1.3 S0 replay pair, limb two,
        under the second status value. Oracle: plan slice
        S0 test status: replay from a mid chain state
        holding a correction entry to the same head hash as
        the full replay. The chain here stands built by hand
        from the stated canonical rules, its head computed
        by hand with SHA-256 over the stated bytes."""
        first = {"name": "Old Name", "product_id": "p-a"}
        correction = {"supersedes_sequence": 1,
                      "corrected_record": {"name": "New Name",
                                           "product_id": "p-a"}}
        third = {"product_id": "p-a", "round_id": "p-a:r1",
                 "round_label": "r1"}
        line1 = canonical_line(first, 1, None)
        hash1 = hashlib.sha256(line1).hexdigest()
        line2 = canonical_line(correction, 2, hash1, kind="correction")
        hash2 = hashlib.sha256(line2).hexdigest()
        line3 = canonical_line(third, 3, hash2, kind="round_named")
        hash3 = hashlib.sha256(line3).hexdigest()
        full = journal.replay(self.home, [line1, line2, line3])
        self.assertEqual(full, hash3)
        other = os.path.join(self.tmp.name, "home2")
        os.makedirs(other)
        journal.replay(other, [line1, line2])
        head = journal.replay(other, [line3], resume=True)
        self.assertEqual(head, hash3)
        reported = journal.fold(other, apply_corrections=True)
        names = [e["payload"].get("name") for e in reported
                 if e["entry_kind"] == "product_registered"]
        self.assertEqual(names, ["New Name"])


class HonestForgeryPairTests(HomeCase):
    def test_branch_one_nonmatching_external_head_bars_writes(self):
        """Row plan Section 1.3 S0 honest forgery pair,
        branch one, writable now. Oracle: plan slice S0 test
        status, the honest forgery pair of IM2-INV-3: branch
        one stands barred on a non matching external head.
        The external head here stands recorded in the anchor
        file the config anchor key names, on brief
        Section 5.12 IM7-BRK-9 landing terms: where the
        anchor recorded head is not the standing head, the
        agreement stands divergent, no record from the chain
        is claimed as verified on that recording, on brief
        Section 5.12 item 138 head hash duty terms, and a
        writing invocation over the home stands barred.
        The anchor file here stands written in the stated
        record form (Step 13 test audit round 1, entry
        R1-008): a head hash with its sequence, the hash
        beside the journal sequence the head was taken at,
        on the IM7-BRK-9 landing terms in brief
        Section 5.12, with the sequence stated as 99, a
        sequence that stands nowhere in this one entry
        chain, so the recorded head stands nowhere in the
        chain and the agreement position is divergent. The
        bar asserted below falls on the round naming append
        named in the test body, on the S0 row passage
        itself, which states branch one as barred on a non
        matching external head."""
        lines, head = chain_lines([{"name": "A", "product_id": "p-a"}])
        self.write_journal(lines)
        anchor = os.path.join(self.tmp.name, "anchor.txt")
        with open(anchor, "w") as handle:
            handle.write("0" * 64 + " 99\n")
        journal.write_config(self.home, "anchor_path = %s\n" % anchor)
        state = service.status(home=self.home)
        self.assertEqual(state["anchor"]["agreement"], "divergent")
        self.assertEqual(state["head_hash"], head)
        with self.assertRaises(journal.JournalError):
            journal.append_entry(self.home, "round_named",
                                 {"product_id": "p-a",
                                  "round_id": "p-a:r1",
                                  "round_label": "r1"},
                                 audit_date=HOME_DATE)

    def test_branch_two_self_consistent_chain_passes_internal_only(self):
        """Row plan Section 1.3 S0 honest forgery pair,
        branch two, writable now. Oracle: plan slice S0 test
        status and brief Section 5.12 item 138: branch two
        passes as internal consistency only, because verify
        recomputes the chain and claims internal consistency
        only, and the checks on the head itself are the
        anchor and the operator recording, not verify."""
        lines, head = chain_lines([{"name": "Forged",
                                    "product_id": "p-forged"}])
        self.write_journal(lines)
        result = service.verify(home=self.home)
        self.assertTrue(result["passed"])
        self.assertEqual(result["claim"], "internal consistency only")
        self.assertEqual(result["head_hash"], head)


class TimingAndDateTests(HomeCase):
    def test_s0_append_and_verify_within_bound_at_stated_scale(self):
        """Row plan Section 1.5 timing bounds, S0. Oracle:
        plan Section 1.5, CQ-D31: S0, journal append and
        verify over a test home, 5 seconds, conditional on a
        test scale Step 13 states on the record. The scale
        stands stated at design/tests/scales-w1.md: a test
        home of 1,000 entries of the stated composition.
        The elapsed measure here is the test harness measure
        of the product calls, not a product date read."""
        start = time.monotonic()
        for index in range(1000):
            journal.append_entry(
                self.home, "round_named",
                {"product_id": "p-a",
                 "round_id": "p-a:r%d" % index,
                 "round_label": "r%d" % index}, audit_date=HOME_DATE)
        result = service.verify(home=self.home)
        elapsed = time.monotonic() - start
        self.assertTrue(result["passed"])
        self.assertEqual(result["entry_count"], 1000)
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
