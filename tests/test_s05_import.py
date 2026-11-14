"""Slice S5 tests: probe import, Step 13, Citeline.

Written before the product exists. Every test imports the product
package named citeline and calls the operation signatures the plan
states (plan Section 1.3 slice S5; module probe_import in the plan
Section 5.3 boundary table; the service layer operation
probe_import on the brief Section 5.4 surface list, with its
adapter contract at brief Section 5.12). Import or attribute
failure is the expected red state (R-20). No stub and no mock of
the product stands in this file.

Dates are call inputs in every test, never clock reads (plan
Section 1.5 date handling). The not in the future validation
compares the answer file asserted capture date against the
audit_date supplied to the import operation, on the statement at
plan Section 1.3 slice S5; no clock read governs a live import.
The timing bound for this slice stands stated in the plan at
Section 1.5: one answer import under the adapter contract, 5
seconds. No scale statement is owed for this slice.

Tests naming error values pin against the plan Part 1 entry 13
joined table as landed: row U-4 token UNKNOWN_ROUND, row U-5
token CONTROL_CAP_EXCEEDED, row I-1 token JOURNAL_CAP_EXCEEDED,
row I-2 token JOURNAL_VERIFY_FAILED, row X-3 token
LIMIT_EXCEEDED, row X-6 token DUPLICATE_IMPORT, row X-7 token
CONTRADICTORY_IMPORT, row X-8 token UNCOVERED_IMPORT_FORM, row
X-10 token WRITE_CONTENDED, and row X-16 token
IMPORT_VALIDATION_FAILED.

The stamp binding rule itself stands blocked on K-18 at plan
Part B entry B6 and no test in this file pins it; the blocked
row stands in blocked-w4.md. Matching copy behaviour depending
on the item 152 removal set stands blocked on L-CC-3 in CL-L-36
and no test in this file pins it; the decided limbs around it,
pipeline order, NFC, and folding, proceed in the F-23 case pair
test at the end of this file, written as the S5 entry pinning
condition states it.
"""

import fcntl
import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from citeline import service

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
PRODUCT = "Acme Ledger"
QUERY = "What is Acme Ledger?"
ROUND = "round-1"


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def make_home(case):
    from citeline import install as install_module
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def seed(case, home, round_label=ROUND, declaration="all captured"):
    service.add_product(
        home=str(home), name=PRODUCT,
        canonical_line="Acme Ledger helps teams track citations.",
        domain="acme.example", audit_date=AUDIT_DATE)
    service.set_query_set(
        home=str(home), product=PRODUCT, query_set=[QUERY],
        audit_date=AUDIT_DATE)
    service.name_round(
        home=str(home), product=PRODUCT, round_label=round_label,
        importer_declaration=declaration,
        supplier_relation="independent party", audit_date=AUDIT_DATE)
    return home


def do_import(home, answer_file, **overrides):
    kwargs = {
        "home": str(home), "answer_file": str(answer_file),
        "product": PRODUCT, "round": ROUND, "engine_label": "Engine A",
        "query": QUERY, "kind": "real_sample",
        "captured_on": "2026-11-10", "capture_method": "manual copy",
        "audit_date": AUDIT_DATE,
    }
    kwargs.update(overrides)
    return service.probe_import(**kwargs)


def entry_count(home):
    return field(service.status(home=str(home)), "entry_count")


def journal_bytes(home):
    """Read the home journal bytes by locating the entry file."""
    best = None
    for path in Path(home).rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            if b"entry_kind" in data or b"answer_imported" in data:
                if best is None or len(data) > len(best[1]):
                    best = (path, data)
    if best is None:
        raise AssertionError("no journal file found in home")
    return best[1]


def journal_entries(home):
    entries = []
    for line in journal_bytes(home).decode("utf-8").splitlines():
        line = line.strip()
        if line:
            entries.append(json.loads(line))
    return entries


def entries_of_kind(home, kind):
    found = []
    for entry in journal_entries(home):
        if entry.get("entry_kind") == kind:
            found.append(entry)
        payload = entry.get("payload") or {}
        if isinstance(payload, dict) and payload.get("entry_kind") == kind:
            found.append(entry)
    return found


def find_key_values(node, key):
    """Every value carried under key, at any depth, in order."""
    found = []
    if isinstance(node, dict):
        for name, value in node.items():
            if name == key:
                found.append(value)
            found.extend(find_key_values(value, key))
    elif isinstance(node, (list, tuple)):
        for value in node:
            found.extend(find_key_values(value, key))
    elif hasattr(node, "__dict__"):
        found.extend(find_key_values(vars(node), key))
    return found


def last_key_value(node, key):
    values = find_key_values(node, key)
    if not values:
        raise AssertionError("no value under key %r" % key)
    return values[-1]


def find_answer_metrics(report):
    """The per answer AnswerMetrics list carried in a report, at
    any depth: a list whose every entry carries named, named_early,
    and cited."""
    if isinstance(report, dict):
        for value in report.values():
            found = find_answer_metrics(value)
            if found is not None:
                return found
    elif isinstance(report, (list, tuple)):
        if report and all(
                isinstance(item, (dict, object))
                and find_key_values(item, "named")
                and find_key_values(item, "named_early")
                and find_key_values(item, "cited")
                for item in report):
            return list(report)
        for value in report:
            found = find_answer_metrics(value)
            if found is not None:
                return found
    return None


def rate_block(metrics, name):
    """One rate block of the authoritative rates object: rate,
    wilson_low, and wilson_high for name, read from a nested rate
    object for that name or from flat fields named for it."""
    nested = find_key_values(metrics, name)
    for value in nested:
        if isinstance(value, dict) and "rate" in value:
            return (value["rate"], value.get("wilson_low"),
                    value.get("wilson_high"))
    flat_rate = find_key_values(metrics, name + "_rate")
    flat_low = find_key_values(metrics, name + "_wilson_low")
    flat_high = find_key_values(metrics, name + "_wilson_high")
    if flat_rate:
        return (flat_rate[0],
                flat_low[0] if flat_low else None,
                flat_high[0] if flat_high else None)
    raise AssertionError("no rate block for %r" % name)


def assert_token(case, caught, token):
    text = str(caught.exception)
    value = getattr(caught.exception, "error_value", None)
    case.assertTrue(token in text or value == token,
                    "expected %s, got %r" % (token, caught.exception))


class ImportBase(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)
        seed(self, self.home)

    def temp_answer(self, text, name="answer.txt"):
        path = Path(self.root) / name
        path.write_text(text, encoding="utf-8")
        return path


class TestAdapterContract(ImportBase):
    """Row plan Section 1.3 S5, adapter contract validation.
    Oracle: brief Section 5.12 adapter contract and brief Section
    5.9 items 147 and 158."""

    def test_valid_import_returns_answer_record_with_stated_fields(self):
        """Pins S5 one file, one answer, record shape. Oracle:
        plan Section 5.1 AnswerRecord entry and contract C1: the
        whole validated answer stands stored with its metadata,
        its content hash over the raw file bytes, and its journal
        entry."""
        fixture = FIXTURES / "w4-answer-plain.txt"
        record = do_import(self.home, fixture)
        self.assertEqual(field(record, "product_id") is not None, True)
        self.assertEqual(field(record, "query"), QUERY)
        self.assertEqual(field(record, "kind"), "real_sample")
        self.assertEqual(str(field(record, "captured_on")), "2026-11-10")
        self.assertEqual(field(record, "capture_method"), "manual copy")
        self.assertEqual(
            field(record, "content_hash"),
            hashlib.sha256(fixture.read_bytes()).hexdigest())
        self.assertEqual(field(record, "engine_label_original"), "Engine A")
        self.assertEqual(field(record, "engine_label_normalised"), "engine a")
        size = field(record, "answer_size")
        text = fixture.read_text(encoding="utf-8")
        characters = size["characters"] if isinstance(size, dict) else size[0]
        words = size["words"] if isinstance(size, dict) else size[1]
        self.assertEqual(characters, len(text))
        self.assertEqual(words, len(text.split()))
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 1)

    def test_nine_adapter_inputs_are_the_contract_inputs(self):
        """Pins S5 the nine adapter inputs. Oracle: brief Section
        5.12 adapter contract in operator order: answer file,
        product, round, engine_label, query, kind, captured_on,
        and capture_method required, and control_designation
        optional; the importer declaration is expressly not an
        import input. A call missing any required input fails
        with the import validation failure value naming the
        field."""
        fixture = FIXTURES / "w4-answer-plain.txt"
        base = {
            "home": str(self.home), "answer_file": str(fixture),
            "product": PRODUCT, "round": ROUND,
            "engine_label": "Engine A", "query": QUERY,
            "kind": "real_sample", "captured_on": "2026-11-10",
            "capture_method": "manual copy", "audit_date": AUDIT_DATE,
        }
        for missing in ("answer_file", "product", "round",
                        "engine_label", "query", "kind", "captured_on",
                        "capture_method"):
            kwargs = {k: v for k, v in base.items() if k != missing}
            with self.assertRaises(Exception) as caught:
                service.probe_import(**kwargs)
            assert_token(self, caught, "IMPORT_VALIDATION_FAILED")
        record = service.probe_import(
            **dict(base, control_designation="positive"))
        self.assertEqual(field(record, "control_kind"), "positive")

    def test_validation_completes_before_any_store_write(self):
        """Pins S5 validation ordering. Oracle: brief Section 5.9
        item 158: validation completes before any store write for
        that import. An import failing validation leaves no
        subject entry; the only journal growth is the one failure
        record."""
        before = entry_count(self.home)
        with self.assertRaises(Exception) as caught:
            do_import(self.home, FIXTURES / "w4-answer-plain.txt",
                      kind="transcript")
        assert_token(self, caught, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(entry_count(self.home), before + 1)
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 0)
        self.assertEqual(len(entries_of_kind(self.home, "failure_record")), 1)

    def test_kind_other_value_fails_validation(self):
        """Pins S5 kind values. Oracle: brief Section 5.9 item
        141: kind holds exactly real_sample or fixture, and any
        other value fails validation with a recorded error and
        nothing stored, on entry 13 row X-16."""
        with self.assertRaises(Exception) as caught:
            do_import(self.home, FIXTURES / "w4-answer-plain.txt",
                      kind="sample")
        assert_token(self, caught, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 0)

    def test_unknown_round_is_usage_error(self):
        """Pins S5 unknown round. Oracle: entry 13 row U-4, token
        UNKNOWN_ROUND, usage class: an import call that names an
        unknown round fails as a usage error naming the missing
        round."""
        with self.assertRaises(Exception) as caught:
            do_import(self.home, FIXTURES / "w4-answer-plain.txt",
                      round="no-such-round")
        assert_token(self, caught, "UNKNOWN_ROUND")

    def test_query_not_in_query_set_fails_and_adds_nothing(self):
        """Pins S5 query set membership. Oracle: brief Section
        5.12 item 132: only a registry operation may add a query
        to a query set; an import may not add a query implicitly,
        and a round is never created by an import call."""
        before = entry_count(self.home)
        with self.assertRaises(Exception):
            do_import(self.home, FIXTURES / "w4-answer-plain.txt",
                      query="A query never registered?")
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 0)
        self.assertEqual(entry_count(self.home), before + 1)

    def test_captured_on_in_future_against_audit_date_fails(self):
        """Pins S5 not in the future validation. Oracle: plan
        Section 1.3 slice S5 comparison date source: the
        validation compares the asserted capture date against
        the audit_date supplied to the import operation."""
        with self.assertRaises(Exception) as caught:
            do_import(self.home, FIXTURES / "w4-answer-plain.txt",
                      captured_on="2026-11-14")
        assert_token(self, caught, "IMPORT_VALIDATION_FAILED")
        record = do_import(self.home, FIXTURES / "w4-answer-other.txt",
                           captured_on="2026-11-13")
        self.assertIsNotNone(record)

    def test_no_clock_read_governs_a_live_import(self):
        """Pins S5 date handling, no clock limb. Oracle: plan
        Section 1.5 date handling and Section 1.3 slice S5: dates
        stand supplied as call inputs and never read from a
        clock. A capture date after the calendar date of this
        test run but before the supplied audit_date imports,
        because only the supplied audit_date governs."""
        record = do_import(self.home, FIXTURES / "w4-answer-plain.txt",
                           captured_on="2026-12-01",
                           audit_date="2027-01-01")
        self.assertIsNotNone(record)

    def test_engine_label_over_length_limit_rejected(self):
        """Pins S5 label length limit. Oracle: entry 13 row X-3,
        token LIMIT_EXCEEDED, with brief Section 5.11 limit 29,
        engine label length 200 code points."""
        with self.assertRaises(Exception) as caught:
            do_import(self.home, FIXTURES / "w4-answer-plain.txt",
                      engine_label="E" * 201)
        assert_token(self, caught, "LIMIT_EXCEEDED")

    def test_control_designation_past_cap_refused(self):
        """Pins S5 control cap. Oracle: entry 13 row U-5, token
        CONTROL_CAP_EXCEEDED: a control designation past the cap
        of 5 designated controls in one round for one source kind
        is refused as a usage error naming the cap, and the import
        writes nothing."""
        for index in range(5):
            path = self.temp_answer("Control answer %d text.\n" % index,
                                    name="control-%d.txt" % index)
            do_import(self.home, path, control_designation="positive",
                      captured_on="2026-11-0%d" % (index + 1))
        before = entry_count(self.home)
        with self.assertRaises(Exception) as caught:
            do_import(self.home,
                      self.temp_answer("Control answer 6 text.\n",
                                       name="control-6.txt"),
                      control_designation="negative",
                      captured_on="2026-11-06")
        assert_token(self, caught, "CONTROL_CAP_EXCEEDED")
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 5)
        self.assertEqual(entry_count(self.home), before + 1)

    def test_empty_answer_is_stored_and_stands_in_its_round(self):
        """Pins S5 empty answer end state. Oracle: brief Section
        5.9 answer side end state and plan Section 5.1
        AnswerRecord entry: an answer whose extracted text is
        empty is stored, stands in its round, and carries named,
        named_early, and cited all false; no extraction_outcome
        field is added to the shape."""
        record = do_import(self.home, FIXTURES / "w4-answer-empty.txt")
        self.assertIsNotNone(record)
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 1)
        if isinstance(record, dict):
            self.assertNotIn("extraction_outcome", record)


class TestUncoveredAndCoveredForms(ImportBase):
    """Row plan Section 1.3 S5, validation check 11 and the
    uncovered forms rule, item 147. Oracle: brief Section 5.9
    items 109 and 147 and validation check 11 as stated there."""

    def test_pdf_answer_fails_import(self):
        """Pins S5 PDF limb. Oracle: brief Section 5.9 item 109
        and plan Section 5.4 answer input: a PDF capture fails
        import, with a recorded error and nothing stored."""
        with self.assertRaises(Exception) as caught:
            do_import(self.home, FIXTURES / "w4-answer-pdf.bin")
        assert_token(self, caught, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 0)

    def test_html_answer_fails_import_under_check_11(self):
        """Pins S5 HTML limb. Oracle: brief Section 5.9 item 109:
        an HTML capture is handled under the check 11 position;
        where its tests identify it, it fails import with a
        recorded error. The HTML document start is one of the six
        check 11 tests."""
        with self.assertRaises(Exception) as caught:
            do_import(self.home, FIXTURES / "w4-answer-html.html")
        assert_token(self, caught, "IMPORT_VALIDATION_FAILED")
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 0)

    def test_uncovered_form_rejected_as_a_class(self):
        """Pins S5 uncovered forms rule. Oracle: brief Section
        5.9 item 147 and entry 13 row X-8, token
        UNCOVERED_IMPORT_FORM: a form meeting none of the six
        tests at validation check 11, a Markdown transcript among
        them, is rejected per import with a recorded error and
        nothing stored; it does not import as one answer."""
        with self.assertRaises(Exception) as caught:
            do_import(self.home, FIXTURES / "w4-answer-transcript.md")
        assert_token(self, caught, "UNCOVERED_IMPORT_FORM")
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 0)
        self.assertEqual(len(entries_of_kind(self.home, "failure_record")), 1)


class TestDuplicatesAndContradictions(ImportBase):
    """Row plan Section 1.3 S5, duplicate and contradiction
    behaviour under contracts C2 and C3. Oracle: plan Section 9
    contracts C2 and C3 and brief Section 5.9 items 114 and 146."""

    def test_exact_duplicate_rejected_and_never_counted_twice(self):
        """Pins C2 duplicate limb. Oracle: contract C2 and entry
        13 row X-6, token DUPLICATE_IMPORT, domain class: a
        standing record on the duplicate key (product, round,
        normalised engine label, query, and content hash) makes
        the import a duplicate."""
        do_import(self.home, FIXTURES / "w4-answer-plain.txt")
        with self.assertRaises(Exception) as caught:
            do_import(self.home, FIXTURES / "w4-answer-plain.txt")
        assert_token(self, caught, "DUPLICATE_IMPORT")
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 1)

    def test_duplicate_despite_different_capture_date_or_method(self):
        """Pins C2 duplicate key date limb. Oracle: plan contract
        C2: a standing record with the same round, the same
        normalised engine label, and the same query, and with the
        same content hash and a different capture date or capture
        method, stands as a duplicate, whatever its capture date
        does."""
        do_import(self.home, FIXTURES / "w4-answer-plain.txt")
        with self.assertRaises(Exception) as caught:
            do_import(self.home, FIXTURES / "w4-answer-plain.txt",
                      captured_on="2026-11-11",
                      capture_method="browser save")
        assert_token(self, caught, "DUPLICATE_IMPORT")

    def test_engine_label_normalised_in_duplicate_key(self):
        """Pins C2 normalisation limb on decided ground. Oracle:
        contract C2 duplicate key over the normalised engine
        label, with the label trimmed and case folded under
        grill Q19 as plan Section 5.1 states: a label differing
        only in surrounding whitespace and letter case hits the
        same duplicate key."""
        do_import(self.home, FIXTURES / "w4-answer-plain.txt")
        with self.assertRaises(Exception) as caught:
            do_import(self.home, FIXTURES / "w4-answer-plain.txt",
                      engine_label="  ENGINE A ")
        assert_token(self, caught, "DUPLICATE_IMPORT")

    def test_contradiction_rejected_and_nothing_overwritten(self):
        """Pins C2 contradiction limb. Oracle: contract C2 and
        entry 13 row X-7, token CONTRADICTORY_IMPORT: same round,
        same normalised engine label, same query, and same
        captured_on, with a different content hash, is a
        contradiction and fails with a recorded error and nothing
        overwritten."""
        first = do_import(self.home, FIXTURES / "w4-answer-plain.txt")
        with self.assertRaises(Exception) as caught:
            do_import(self.home, FIXTURES / "w4-answer-other.txt")
        assert_token(self, caught, "CONTRADICTORY_IMPORT")
        stored = entries_of_kind(self.home, "answer_imported")
        self.assertEqual(len(stored), 1)
        self.assertEqual(field(first, "content_hash"),
                         hashlib.sha256((FIXTURES / "w4-answer-plain.txt")
                                        .read_bytes()).hexdigest())

    def test_same_text_into_second_round_stands_as_new_record(self):
        """Pins C2 worked case. Oracle: contract C2 worked case
        and brief Section 5.9 item 146: the same answer text
        imported into a second round on a second date is a new
        record and the import succeeds, because the round
        differs."""
        service.name_round(
            home=str(self.home), product=PRODUCT, round_label="round-2",
            importer_declaration="all captured",
            supplier_relation="independent party", audit_date=AUDIT_DATE)
        do_import(self.home, FIXTURES / "w4-answer-plain.txt")
        record = do_import(self.home, FIXTURES / "w4-answer-plain.txt",
                           round="round-2", captured_on="2026-11-11")
        self.assertIsNotNone(record)
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 2)

    def test_record_for_different_product_is_neither(self):
        """Pins C2 product scope. Oracle: plan contract C2: a
        record held for a different product stands as neither
        duplicate nor contradiction."""
        service.add_product(
            home=str(self.home), name="Other Product",
            canonical_line="Other Product line.", domain="other.example",
            audit_date=AUDIT_DATE)
        service.set_query_set(
            home=str(self.home), product="Other Product",
            query_set=[QUERY], audit_date=AUDIT_DATE)
        service.name_round(
            home=str(self.home), product="Other Product",
            round_label=ROUND, importer_declaration="all captured",
            supplier_relation="independent party", audit_date=AUDIT_DATE)
        do_import(self.home, FIXTURES / "w4-answer-plain.txt")
        record = do_import(self.home, FIXTURES / "w4-answer-plain.txt",
                           product="Other Product")
        self.assertIsNotNone(record)

    def test_kind_classes_never_cross_in_comparison(self):
        """Pins C2 kind segregation. Oracle: contract C2 and
        brief Section 5.9 item 146: the comparison runs in the
        same product namespace and the same kind class, and kind
        classes do not cross. The same file imported as fixture
        after a real_sample import of the same key fields is a
        new record, and a differing file in the other kind class
        on the contradiction fields is no contradiction."""
        do_import(self.home, FIXTURES / "w4-answer-plain.txt")
        record = do_import(self.home, FIXTURES / "w4-answer-plain.txt",
                           kind="fixture")
        self.assertIsNotNone(record)
        record2 = do_import(self.home, FIXTURES / "w4-answer-other.txt",
                            kind="fixture", captured_on="2026-11-11")
        self.assertIsNotNone(record2)

    def test_kind_class_contradiction_limb_isolated_on_same_date(self):
        """Pins C2 kind segregation, contradiction limb isolated.
        Oracle: contract C2 and brief Section 5.9 item 146: a
        differing file in the other kind class on the same
        captured_on as the standing record, with kind the only
        differing field beside the content hash the contradiction
        form itself varies, is no contradiction and stands as a
        new record."""
        do_import(self.home, FIXTURES / "w4-answer-plain.txt")
        record = do_import(self.home, FIXTURES / "w4-answer-other.txt",
                           kind="fixture", captured_on="2026-11-10")
        self.assertIsNotNone(record)
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 2)

    def test_corrected_retry_after_failure_is_a_fresh_import(self):
        """Pins C3 retry limb. Oracle: contract C3 and brief
        Section 5.9 item 114: a corrected retry of a failed
        import is a new import call against the standing records;
        a failed import stored nothing, so the retry never meets
        its own earlier attempt as a record and is treated as
        neither a duplicate nor a contradiction of it."""
        with self.assertRaises(Exception):
            do_import(self.home, FIXTURES / "w4-answer-plain.txt",
                      kind="transcript")
        record = do_import(self.home, FIXTURES / "w4-answer-plain.txt")
        self.assertIsNotNone(record)
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 1)


class TestFailureRecordScoping(ImportBase):
    """Row plan Section 1.3 S5, failed import leaving exactly one
    failure record and no subject entry on its scoped terms.
    Oracle: brief Section 5.9 item 158, plan Section 5.1 failure
    record entry, and contracts C1 and C3."""

    def test_failed_import_leaves_exactly_one_failure_record(self):
        """Pins S5 failure record claim. Oracle: item 158 scoped
        claim: a failed operation the process lives to report
        leaves exactly one failure record entry, in the fixed
        shape (operation, error_value, subject_identity or hash,
        date, rule_fired), and no subject entry."""
        before = entry_count(self.home)
        with self.assertRaises(Exception):
            do_import(self.home, FIXTURES / "w4-answer-transcript.md")
        self.assertEqual(entry_count(self.home), before + 1)
        failures = entries_of_kind(self.home, "failure_record")
        self.assertEqual(len(failures), 1)
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 0)

    def test_barred_chain_import_leaves_no_failure_record(self):
        """Pins S5 barred chain limb. Oracle: item 158 scope and
        entry 13 row I-2, token JOURNAL_VERIFY_FAILED: on a
        barred chain the import leaves no failure record and no
        subject entry; the caller response is the only record,
        and the journal bytes stand unchanged by the attempt."""
        do_import(self.home, FIXTURES / "w4-answer-plain.txt")
        journal_path = None
        for path in Path(self.home).rglob("*"):
            if path.is_file() and b"answer_imported" in path.read_bytes():
                journal_path = path
        self.assertIsNotNone(journal_path)
        with open(journal_path, "ab") as handle:
            handle.write(b"this line is not a journal entry\n")
        tampered = journal_path.read_bytes()
        with self.assertRaises(Exception) as caught:
            do_import(self.home, FIXTURES / "w4-answer-other.txt",
                      captured_on="2026-11-11")
        assert_token(self, caught, "JOURNAL_VERIFY_FAILED")
        self.assertEqual(journal_path.read_bytes(), tampered)

    def test_chain_at_cap_import_leaves_no_failure_record(self):
        """Pins S5 chain at cap limb. Oracle: item 158 scope and
        entry 13 row I-1, token JOURNAL_CAP_EXCEEDED: at the cap
        no failure record can be appended and the recorded error
        is the caller response only. The cap is reached here by
        lowering limit 39, journal_length, to the standing entry
        count through the flat key and value config file the
        entry 15 table keys, at the install location in the form
        writer 7 install tests use."""
        current = entry_count(self.home)
        location = Path(self.root) / "install"
        (location / "config.txt").write_text(
            "journal_length = %d\n" % current, encoding="utf-8")
        before = journal_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            do_import(self.home, FIXTURES / "w4-answer-plain.txt")
        assert_token(self, caught, "JOURNAL_CAP_EXCEEDED")
        self.assertEqual(journal_bytes(self.home), before)

    def test_contended_invocation_leaves_no_failure_record(self):
        """Pins S5 contended invocation limb. Oracle: item 158
        scope and entry 13 row X-10, token WRITE_CONTENDED: a
        contended invocation likewise leaves no failure record;
        the returned recorded error is its only record. Contention
        is produced by holding the advisory write lock the plan
        entry 16 mechanism states, the file .citeline-write.lock
        in the home, under flock."""
        lock_path = Path(self.home) / ".citeline-write.lock"
        lock_path.touch()
        before = journal_bytes(self.home)
        with open(lock_path, "r+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(Exception) as caught:
                do_import(self.home, FIXTURES / "w4-answer-plain.txt")
            fcntl.flock(handle, fcntl.LOCK_UN)
        assert_token(self, caught, "WRITE_CONTENDED")
        self.assertEqual(journal_bytes(self.home), before)
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 0)


class TestWorksheetExport(ImportBase):
    """Row plan Section 1.3 S5, the capture worksheet export.
    Oracle: plan Section 1.3 slice S5 family statement and plan
    Section 5.4 answer input passage."""

    def test_export_writes_worksheet_from_named_round_definition(self):
        """Pins S5 worksheet export. Oracle: slice S5 family: one
        export operation writing a worksheet file from a named
        round definition, the query list, the engine labels to
        attempt, the round label, and one empty slot per planned
        answer, each slot carrying the metadata fields the import
        format will later require."""
        target = Path(self.root) / "worksheet.txt"
        result = service.export_capture_worksheet(
            home=str(self.home), product=PRODUCT, round=ROUND,
            queries=[QUERY], engine_labels=["Engine A", "Engine B"],
            planned_answers=3, output_path=str(target),
            audit_date=AUDIT_DATE)
        self.assertTrue(target.is_file())
        text = target.read_text(encoding="utf-8")
        self.assertIn(QUERY, text)
        self.assertIn("Engine A", text)
        self.assertIn("Engine B", text)
        self.assertIn(ROUND, text)
        for name in ("engine_label", "kind", "captured_on",
                     "capture_method"):
            self.assertIn(name, text)
        self.assertEqual(text.count("captured_on"), 3)
        self.assertIsNotNone(result)

    def test_completed_worksheet_imports_back_through_import_route(self):
        """Pins S5 worksheet round trip. Oracle: slice S5 family:
        the operator captures by hand against the worksheet,
        fills the slots, and the completed worksheet is imported
        back through the existing import route; the product
        captures nothing, fetches nothing, and queries
        nothing."""
        target = Path(self.root) / "worksheet.txt"
        service.export_capture_worksheet(
            home=str(self.home), product=PRODUCT, round=ROUND,
            queries=[QUERY], engine_labels=["Engine A"],
            planned_answers=1, output_path=str(target),
            audit_date=AUDIT_DATE)
        worksheet_text = target.read_text(encoding="utf-8")
        self.assertEqual(worksheet_text.count("captured_on"), 1)
        filled_text = worksheet_text.rstrip() + (
            "\nThe worksheet answer about Acme Ledger and ferries.\n")
        target.write_text(filled_text, encoding="utf-8")
        record = do_import(self.home, target)
        self.assertIsNotNone(record)
        self.assertEqual(len(entries_of_kind(self.home, "answer_imported")), 1)


class TestRoundStamps(ImportBase):
    """Row plan Section 1.3 S5, sole writing of the Round two at
    first import stamps, through the journal, at
    SEAM-ROUND-STAMP. Oracle: plan Part B entry B6 proceeding
    tests and brief Section 5.2 Round entry. The binding rule
    itself stands blocked on K-18 and no test here pins it."""

    def round_state(self):
        report = service.probe_report(
            home=str(self.home), product=PRODUCT, round=ROUND,
            audit_date=AUDIT_DATE)
        return report

    def test_round_stamps_null_before_first_import(self):
        """Pins S5 stamp absence limb. Oracle: brief Section 5.2
        Round entry: registry_version_at_first_import and
        detector_version_at_first_import stand null before any
        import."""
        entries = entries_of_kind(self.home, "round_named")
        self.assertEqual(len(entries), 1)
        payload = entries[0].get("payload") or {}
        for stamp in ("registry_version_at_first_import",
                      "detector_version_at_first_import"):
            values = find_key_values(payload, stamp)
            if not values:
                values = find_key_values(entries[0], stamp)
            self.assertTrue(values, "no stamp field %r" % stamp)
            self.assertIsNone(values[-1])

    def test_first_import_writes_round_stamps_through_journal(self):
        """Pins S5 sole writing limb. Oracle: slice S5 family and
        entry B6 proceeding tests: S5 stands as sole writer of
        the two stamps, through the journal, at
        SEAM-ROUND-STAMP. After the first import the round
        carries both stamps, and each AnswerRecord carries its
        own import stamps beside them."""
        record = do_import(self.home, FIXTURES / "w4-answer-plain.txt")
        report = self.round_state()
        text = json.dumps(report, default=str, ensure_ascii=False)
        self.assertIn(str(field(record, "registry_version_at_import")),
                      text)
        self.assertIn(str(field(record, "detector_version_at_import")),
                      text)
        entries = journal_entries(self.home)
        self.assertEqual(
            last_key_value(entries, "registry_version_at_first_import"),
            field(record, "registry_version_at_import"))
        self.assertEqual(
            last_key_value(entries, "detector_version_at_first_import"),
            field(record, "detector_version_at_import"))

    def test_second_import_does_not_rewrite_round_stamps(self):
        """Pins S5 stamps written once limb. Oracle: slice S5
        sole writing statement: the stamps stand written at
        first import; a later import into the same round, after
        a registry change, leaves the round stamps at their
        first import values, while the later AnswerRecord
        carries its own import stamps. This test pins the
        writing act and the disclosure values only; which
        registry version a report figure binds to stands blocked
        on K-18 and no assertion here touches it."""
        first = do_import(self.home, FIXTURES / "w4-answer-plain.txt")
        service.set_aliases(
            home=str(self.home), product=PRODUCT,
            aliases=["AcmeLedger"], audit_date=AUDIT_DATE)
        second = do_import(self.home, FIXTURES / "w4-answer-other.txt",
                           captured_on="2026-11-11")
        report = self.round_state()
        text = json.dumps(report, default=str, ensure_ascii=False)
        self.assertIn(str(field(first, "registry_version_at_import")),
                      text)
        self.assertNotEqual(
            field(second, "registry_version_at_import"),
            field(first, "registry_version_at_import"))
        entries = journal_entries(self.home)
        self.assertEqual(
            last_key_value(entries, "registry_version_at_first_import"),
            field(first, "registry_version_at_import"))
        self.assertEqual(
            last_key_value(entries, "detector_version_at_first_import"),
            field(first, "detector_version_at_import"))


class TestReproductionFixture(ImportBase):
    """Row plan Section 1.3 S5, the reproduction fixture family.
    Oracle: plan Section 5.2 AnswerMetrics and RoundMetrics
    recomputation rows and the catalogue entry at plan Section
    1.6 for the reproduction fixture (CQ-D10)."""

    def load_fixture(self):
        return json.loads((FIXTURES / "w4-reproduction-fixture.json")
                          .read_text(encoding="utf-8"))

    def test_fixture_holds_the_stated_round_as_journal_entries(self):
        """Pins the reproduction fixture holding. Oracle: plan
        Section 1.6 catalogue entry: a stated round of
        answer_imported entries held as journal entries, authored
        synthetic, recorded from no run, standing at slices S5
        and S7."""
        fixture = self.load_fixture()
        kinds = [e["entry_kind"] for e in fixture["journal_entries"]]
        self.assertEqual(kinds.count("answer_imported"), 4)
        self.assertEqual(fixture["round"]["round_label"], "repro-round")
        for entry in fixture["journal_entries"]:
            if entry["entry_kind"] == "answer_imported":
                payload = entry["payload"]
                name = payload["answer_file"]
                self.assertEqual(
                    payload["content_hash"],
                    hashlib.sha256((FIXTURES / name)
                                   .read_bytes()).hexdigest())

    def test_recomputed_metrics_match_hand_computed_expectations(self):
        """Pins the reproduction proof at S5. Oracle: plan
        Section 5.2: a stated round of answer_imported entries,
        folded and recomputed from the journal alone, must yield
        the hand computed AnswerMetrics the catalogue states, and
        the hand computed RoundMetrics through them. The round is
        reproduced here by importing the four fixture answer
        files into the fixture round definition, and the report
        over that round must carry the catalogue values: named
        rate 0.5, named early rate 0.25, cited rate gross 0.25,
        cited rate net 0.0, effective n 4, cluster count 4, and
        the Wilson intervals the catalogue records. Per answer,
        the catalogue states R1 named true, named early true,
        cited true, first offset 0; R2 all false, first offset
        null; R3 named true only, first offset 1050; and R4, the
        empty answer, all false, first offset null. The omitted
        RoundMetrics values stand at named rate 0.5 with Wilson
        interval 0.150036 to 0.849964, named early rate 0.25 with
        Wilson interval 0.045586 to 0.699364, largest cluster
        share 0.25, chained cluster count 0, and no name share
        0.5."""
        fixture = self.load_fixture()
        service.add_product(
            home=str(self.home), name="Repro Product",
            canonical_line="Acme Ledger helps teams track citations.",
            domain="acme.example", audit_date=AUDIT_DATE)
        service.set_query_set(
            home=str(self.home), product="Repro Product",
            query_set=[QUERY], audit_date=AUDIT_DATE)
        service.name_round(
            home=str(self.home), product="Repro Product",
            round_label="repro-round",
            importer_declaration="all captured",
            supplier_relation="independent party", audit_date=AUDIT_DATE)
        for label in ("R1", "R2", "R3", "R4"):
            entry = [e for e in fixture["journal_entries"]
                     if e["entry_kind"] == "answer_imported"
                     and e["payload"]["fixture_answer_label"] == label][0]
            service.probe_import(
                home=str(self.home),
                answer_file=str(FIXTURES / entry["payload"]["answer_file"]),
                product="Repro Product", round="repro-round",
                engine_label="Engine A", query=QUERY,
                kind="real_sample",
                captured_on=entry["payload"]["captured_on"],
                capture_method="manual copy", audit_date=AUDIT_DATE)
        report = service.probe_report(
            home=str(self.home), product="Repro Product",
            round="repro-round", audit_date=AUDIT_DATE)
        expected = fixture["hand_computed_round_metrics_real_sample"]
        text = json.dumps(report, default=str, ensure_ascii=False)
        self.assertIn(str(expected["imported_count"]), text)
        metrics = (field(report, "round_metrics")
                   if isinstance(report, dict) and "round_metrics" in report
                   else report)
        self.assertAlmostEqual(field(metrics, "cited_rate_gross"), 0.25)
        self.assertAlmostEqual(field(metrics, "cited_rate_net"), 0.0)
        self.assertAlmostEqual(field(metrics, "self_citation_share"), 1.0)
        self.assertEqual(field(metrics, "effective_n"), 4)
        self.assertEqual(field(metrics, "cluster_count"), 4)
        self.assertEqual(field(metrics, "empty_answer_count"), 1)
        self.assertEqual(field(metrics, "citing_answer_count"), 1)
        self.assertEqual(field(metrics, "citation_instance_count"), 1)
        self.assertEqual(field(metrics, "no_name_count"), 2)
        named_rate, named_low, named_high = rate_block(metrics, "named")
        self.assertAlmostEqual(named_rate, 0.5, places=6)
        self.assertAlmostEqual(named_low, 0.150036, places=4)
        self.assertAlmostEqual(named_high, 0.849964, places=4)
        early_rate, early_low, early_high = rate_block(
            metrics, "named_early")
        self.assertAlmostEqual(early_rate, 0.25, places=6)
        self.assertAlmostEqual(early_low, 0.045586, places=4)
        self.assertAlmostEqual(early_high, 0.699364, places=4)
        self.assertAlmostEqual(field(metrics, "largest_cluster_share"),
                               0.25)
        self.assertEqual(field(metrics, "chained_cluster_count"), 0)
        self.assertAlmostEqual(field(metrics, "no_name_share"), 0.5)
        per_answer = find_answer_metrics(report)
        self.assertIsNotNone(per_answer)
        self.assertEqual(len(per_answer), 4)
        expected_answers = [
            (True, True, True, 0, ["Acme Ledger"]),
            (False, False, False, None, []),
            (True, False, False, 1050, ["Acme Ledger"]),
            (False, False, False, None, []),
        ]
        clusters = []
        for answer, expected in zip(per_answer, expected_answers):
            named, named_early, cited, offset, aliases = expected
            self.assertEqual(last_key_value(answer, "named"), named)
            self.assertEqual(last_key_value(answer, "named_early"),
                             named_early)
            self.assertEqual(last_key_value(answer, "cited"), cited)
            self.assertEqual(last_key_value(answer, "first_offset"),
                             offset)
            self.assertEqual(last_key_value(answer, "matched_aliases"),
                             aliases)
            self.assertEqual(
                last_key_value(answer, "unresolved_form_count"), 0)
            self.assertEqual(last_key_value(answer, "near_duplicate"),
                             False)
            clusters.append(last_key_value(answer, "cluster_id"))
        self.assertEqual(len(set(clusters)), 4)


class TestImportTiming(ImportBase):
    """Row plan Section 1.3 S5, timing. Oracle: plan Section 1.5
    timing bounds."""

    def test_import_timing_bound_five_seconds(self):
        """Pins S5 timing bound. Oracle: plan Section 1.5: S5,
        one answer import under the adapter contract, 5 seconds,
        a plan design value at the stated test scale of one
        answer import."""
        start = time.monotonic()
        do_import(self.home, FIXTURES / "w4-answer-plain.txt")
        self.assertLess(time.monotonic() - start, 5.0)


class TestF23CasePairDesign(ImportBase):
    """Row plan Section 1.3 S5, pinning condition from F-23, as a
    test design written now. Oracle: plan Section 1.3 slice S5
    pinning condition and plan Part 1 EC-153 points 1 to 5.

    Standing of this class, stated exactly: this is a test
    design, writable now in that form, for the case pair that
    distinguishes full folding from simple lowering. Its version
    referent stands pinned in the test data below for the
    detector version to record, and the items 151 to 153 order,
    NFC then item 152 removal then item 153 folding, stands
    restated here at this pipeline home. The pair runs over the
    decided limbs only: pipeline order, NFC, and folding. No
    assertion in this class pins which characters the item 152
    removal removes: that behaviour stands blocked on L-CC-3 in
    CL-L-36 and stands in blocked-w4.md. The pair becomes a
    proceeding test when the plan names the folding operation,
    on the pinning condition terms; until then its assertions
    stand as the design this entry charges."""

    # Case pair data. Full folding maps the German sharp s
    # (U+00DF) to the two letters ss and maps the Latin ligature
    # ff (U+FB00) to the two letters ff. Simple lowering leaves
    # U+00DF unchanged and leaves U+FB00 unchanged. A label
    # carrying U+00DF therefore normalises to a form holding ss
    # under full folding and to a form still holding U+00DF
    # under simple lowering, so the two operations stand
    # distinguished by this pair.
    LABEL_WITH_SHARP_S = "Stra\u00dfe Engine"
    LABEL_FOLDED_FORM = "strasse engine"
    LABEL_WITH_LIGATURE = "\ufb00 Engine"
    LABEL_LIGATURE_FOLDED_FORM = "ff engine"

    def test_f23_pair_engine_label_full_folding(self):
        """Pins F-23 case pair, folding limb, as a test design on
        the standing stated above. Oracle: plan EC-153 point 1:
        the operation character is full Unicode case folding,
        locale independent; a call delivering only simple or
        locale sensitive lowering does not meet this character.
        The engine label normalisation at probe import (trimmed
        and case folded under grill Q19) is a named consumer of
        the one folding operation."""
        record = do_import(
            self.home, FIXTURES / "w4-answer-plain.txt",
            engine_label=self.LABEL_WITH_SHARP_S)
        self.assertEqual(field(record, "engine_label_normalised"),
                         self.LABEL_FOLDED_FORM)
        record2 = do_import(
            self.home, FIXTURES / "w4-answer-other.txt",
            engine_label=self.LABEL_WITH_LIGATURE,
            captured_on="2026-11-11")
        self.assertEqual(field(record2, "engine_label_normalised"),
                         self.LABEL_LIGATURE_FOLDED_FORM)

    def test_f23_pair_duplicate_key_uses_folded_form(self):
        """Pins F-23 case pair, duplicate key limb, as a test
        design on the standing stated above. Oracle: contract C2
        duplicate key over the normalised engine label: a second
        import whose label differs from the first only in the
        sharp s spelling against its folded ss spelling lands on
        the same duplicate key only under full folding."""
        do_import(self.home, FIXTURES / "w4-answer-plain.txt",
                  engine_label=self.LABEL_WITH_SHARP_S)
        with self.assertRaises(Exception) as caught:
            do_import(self.home, FIXTURES / "w4-answer-plain.txt",
                      engine_label="STRASSE ENGINE")
        assert_token(self, caught, "DUPLICATE_IMPORT")


if __name__ == "__main__":
    unittest.main()
