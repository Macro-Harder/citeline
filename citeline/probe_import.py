"""Probe import of supplied answer files, slice S5.

Supplied words are taken exactly as they stand. This module is
the only entry point for sampled answers: it reads a supplied
answer file and the standing records handed to it, and it
never captures, fetches, or queries an answer. The comparison
for duplicates and contradictions runs inside one product
namespace and one kind class only; kind classes are never
pooled and never cross.

The module owns the AnswerRecord shape (plan Section 5.1),
the adapter contract validation (the nine adapter inputs,
validation completing before any store write), validation
check 11 and the uncovered forms rule (item 147), and the
duplicate and contradiction comparison of contracts C2 and
C3. The journal write itself, the round stamp write at
SEAM-ROUND-STAMP, and the failure record append belong to
the journal and service modules; this module returns the
record to store and raises the recorded error value for the
caller to record, on the scoped terms contract C1 states.
Dates are call inputs: the capture date is compared against
the audit_date supplied to the import call, and no clock is
read here.
"""

import csv
import hashlib
import io
import json
import re
import unicodedata
from datetime import date

ENGINE_LABEL_LIMIT = 200
ANSWER_FILE_LIMIT = 1024 * 1024
CONTROL_CAP = 5
KINDS = ("real_sample", "fixture")
CONTROL_KINDS = ("positive", "negative")

_ARCHIVE_MAGICS = (
    bytes.fromhex("504B0304"),
    bytes.fromhex("1F8B"),
    bytes.fromhex("425A68"),
    bytes.fromhex("FD377A585A00"),
    bytes.fromhex("377ABCAF271C"),
    bytes.fromhex("526172211A0700"),
    bytes.fromhex("526172211A070100"),
    bytes.fromhex("28B52FFD"),
)

_SPEAKER_RE = re.compile(
    r"^(?:user|assistant|customer|agent|human|system|speaker\s+\d+"
    r"|interviewer|respondent)\s*:\s", re.IGNORECASE)


class ProbeImportError(Exception):
    """A recorded import error from the closed vocabulary.

    The error_value attribute carries the entry 13 token, and
    the token stands in the message text as well.
    """

    def __init__(self, error_value, detail=""):
        self.error_value = error_value
        message = error_value if not detail else (
            error_value + ": " + detail)
        super().__init__(message)


def _fail(error_value, detail=""):
    raise ProbeImportError(error_value, detail)


def normalise_engine_label(label):
    """The normalised engine label: trimmed and case folded.

    The folding operation is full Unicode case folding, locale
    independent (item 153 as carried to the plan): a sharp s
    folds to ss and a ligature folds to its letters, where
    simple lowering would leave both unchanged.
    """
    normalised = unicodedata.normalize("NFC", str(label))
    return normalised.strip().casefold()


def _parse_date(value, field_name):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        _fail("IMPORT_VALIDATION_FAILED",
              field_name + " is not an ISO date: " + str(value))


def _is_fence_line(line):
    stripped = line.lstrip(" \t")
    return stripped.startswith("```") or stripped.startswith("~~~")


def _is_table_row(line):
    text = line.strip(" \t")
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return "|" in text


def _delimited_test(text):
    """The quote aware delimited structure test of check 11.

    Fields are counted by a quote aware CSV parse with a comma
    delimiter and a double quote quoting character. The test
    is met where at least 90 percent of the records are
    delimited rows of at least three fields, all those rows
    hold the same number of fields, the file holds at least
    three such rows, and no physical line is a Markdown code
    fence line or a Markdown table row. A parse that cannot
    complete returns the string "parse_failed".
    """
    lines = text.splitlines()
    if any(_is_fence_line(line) or _is_table_row(line)
           for line in lines):
        return False
    reader = csv.reader(io.StringIO(text), delimiter=",", quotechar='"',
                        strict=True)
    try:
        records = [record for record in reader if record]
    except csv.Error:
        return "parse_failed"
    if not records:
        return False
    rows = [record for record in records if len(record) >= 3]
    if len(rows) < 3:
        return False
    if len(rows) / len(records) < 0.9:
        return False
    return len({len(record) for record in rows}) == 1


def check11_form(raw_bytes, text):
    """Run the six tests of validation check 11.

    Returns the name of the test met, one of archive, pdf,
    html, json, json_lines, or delimited, or None where no
    test is met. A file meeting one of these tests is not one
    answer and fails import on that ground.
    """
    for magic in _ARCHIVE_MAGICS:
        if raw_bytes.startswith(magic):
            return "archive"
    if raw_bytes.startswith(b"%PDF-"):
        return "pdf"
    first = text.lstrip(" \t\n\r\f")
    lowered = first.casefold()
    if lowered.startswith("<!doctype") and (
            len(lowered) == 9 or lowered[9] in " \t\n\r\f"):
        return "html"
    if lowered.startswith("<html") and (
            len(lowered) == 5 or lowered[5] in " \t\n\r\f/>"):
        return "html"
    stripped = text.strip()
    if stripped:
        try:
            value = json.loads(stripped)
            if isinstance(value, (dict, list)):
                return "json"
        except ValueError:
            pass
        nonempty = [line for line in text.splitlines() if line.strip()]
        if len(nonempty) >= 2:
            try:
                for line in nonempty:
                    json.loads(line)
                return "json_lines"
            except ValueError:
                pass
    delimited = _delimited_test(text)
    if delimited == "parse_failed":
        _fail("IMPORT_VALIDATION_FAILED",
              "delimited parse could not complete")
    if delimited:
        return "delimited"
    return None


def is_transcript_form(text):
    """A Markdown transcript of a whole conversation.

    A form meeting none of the six check 11 tests, rejected as
    a class under the uncovered forms rule at item 147. The
    marks read here are a heading naming a transcript, or two
    or more speaker turns opening lines of the file.
    """
    turns = 0
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if "transcript" in stripped.casefold() and len(stripped) < 80:
            return True
        if _SPEAKER_RE.match(line.strip()):
            turns += 1
    return turns >= 2


def validate_adapter_inputs(*, answer_file=None, product=None,
                            round=None, engine_label=None, query=None,
                            kind=None, captured_on=None,
                            capture_method=None,
                            control_designation=None,
                            audit_date=None, known_round=True,
                            query_set=None, control_count=0):
    """Validate the nine adapter inputs before any store write.

    The nine inputs in operator order: answer file, product,
    round, engine_label, query, kind, captured_on, and
    capture_method required, and control_designation optional.
    The importer declaration is not an import input. Returns a
    dict of the validated values with the normalised engine
    label and the parsed dates.
    """
    required = (
        ("answer_file", answer_file),
        ("product", product),
        ("round", round),
        ("engine_label", engine_label),
        ("query", query),
        ("kind", kind),
        ("captured_on", captured_on),
        ("capture_method", capture_method),
    )
    for name, value in required:
        if value is None or (isinstance(value, str) and value == ""):
            _fail("IMPORT_VALIDATION_FAILED",
                  "missing required input: " + name)
    if audit_date is None or (isinstance(audit_date, str)
                              and audit_date == ""):
        _fail("IMPORT_VALIDATION_FAILED",
              "missing required input: audit_date")
    if not known_round:
        _fail("UNKNOWN_ROUND", "unknown round: " + str(round))
    if query_set is not None and query not in query_set:
        _fail("IMPORT_VALIDATION_FAILED",
              "query is not in the query set for the product: "
              + str(query))
    if kind not in KINDS:
        _fail("IMPORT_VALIDATION_FAILED",
              "kind holds exactly real_sample or fixture, got: "
              + str(kind))
    if len(str(engine_label)) > ENGINE_LABEL_LIMIT:
        _fail("LIMIT_EXCEEDED",
              "engine label length limit is 200 code points")
    captured = _parse_date(captured_on, "captured_on")
    audit = _parse_date(audit_date, "audit_date")
    if captured > audit:
        _fail("IMPORT_VALIDATION_FAILED",
              "captured_on stands after the audit date supplied "
              "to the import call")
    if control_designation is not None:
        if control_designation not in CONTROL_KINDS:
            _fail("IMPORT_VALIDATION_FAILED",
                  "control_designation holds positive or negative, "
                  "got: " + str(control_designation))
        if control_count >= CONTROL_CAP:
            _fail("CONTROL_CAP_EXCEEDED",
                  "cap of 5 designated controls in one round for "
                  "one source kind")
    return {
        "answer_file": answer_file,
        "product": product,
        "round": round,
        "engine_label_original": engine_label,
        "engine_label_normalised": normalise_engine_label(engine_label),
        "query": query,
        "kind": kind,
        "captured_on": captured.isoformat(),
        "capture_method": capture_method,
        "control_designation": control_designation,
        "audit_date": audit.isoformat(),
    }


def read_answer_file(answer_file):
    """Read one supplied answer file exactly as it stands.

    Returns (raw_bytes, text, content_hash). The content hash
    stands over the raw file bytes. The text is the file
    decoded as UTF-8; an undecodable file fails validation.
    """
    try:
        with open(answer_file, "rb") as handle:
            raw = handle.read()
    except OSError as error:
        _fail("IMPORT_VALIDATION_FAILED",
              "answer file cannot be read: " + str(error))
    if len(raw) > ANSWER_FILE_LIMIT:
        _fail("LIMIT_EXCEEDED", "answer file limit is 1 MiB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _fail("IMPORT_VALIDATION_FAILED",
              "answer file is not UTF-8 text")
    return raw, text, hashlib.sha256(raw).hexdigest()


def _record_field(record, *names):
    for name in names:
        if isinstance(record, dict) and record.get(name) is not None:
            return record[name]
        if not isinstance(record, dict) and getattr(
                record, name, None) is not None:
            return getattr(record, name)
    return None


def compare_standing(standing_records, candidate):
    """The duplicate and contradiction comparison, contract C2.

    The comparison runs in the same product namespace and the
    same kind class; kind classes do not cross, and a record
    held for a different product stands as neither. Returns
    "duplicate", "contradiction", or None for a new record.
    """
    for record in standing_records or []:
        if _record_field(record, "kind") != candidate["kind"]:
            continue
        product = _record_field(record, "product_id", "product")
        if product is not None and candidate.get("product_id") is not None:
            if product != candidate["product_id"]:
                continue
        elif product is not None and candidate.get("product") is not None:
            if product != candidate["product"]:
                continue
        round_value = _record_field(record, "round_id", "round_label",
                                    "round")
        candidate_round = candidate.get("round_id") or candidate.get(
            "round")
        if round_value is not None and candidate_round is not None:
            if round_value != candidate_round:
                continue
        if _record_field(record, "engine_label_normalised") != (
                candidate["engine_label_normalised"]):
            continue
        if _record_field(record, "query") != candidate["query"]:
            continue
        if _record_field(record, "content_hash") == candidate[
                "content_hash"]:
            return "duplicate"
        standing_captured = _record_field(record, "captured_on")
        if standing_captured is not None and str(
                standing_captured) == candidate["captured_on"]:
            return "contradiction"
    return None


def build_answer_record(validated, *, text, content_hash, form_marks,
                        product_id=None, round_id=None, answer_id=None,
                        registry_version_at_import=None,
                        detector_version_at_import=None):
    """Build the AnswerRecord for one validated answer.

    The record carries the whole validated answer with its
    metadata, its content hash over the raw file bytes, and
    its integrity note: the hash recorded at import and any
    container marks validation check 11 found. No wrapper
    marks stand in the note; wrapper contamination is not
    detected in version 1. An answer whose text is empty is
    stored on the same shape; no extraction_outcome field is
    added to this shape.
    """
    if form_marks:
        marks = "container marks found at validation check 11: " \
            + ", ".join(form_marks)
    else:
        marks = "no container marks found at validation check 11"
    return {
        "answer_id": answer_id,
        "product_id": product_id,
        "product": validated["product"],
        "round_id": round_id,
        "round": validated["round"],
        "query": validated["query"],
        "registry_version_at_import": registry_version_at_import,
        "detector_version_at_import": detector_version_at_import,
        "engine_label_original": validated["engine_label_original"],
        "engine_label_normalised": validated[
            "engine_label_normalised"],
        "kind": validated["kind"],
        "captured_on": validated["captured_on"],
        "capture_method": validated["capture_method"],
        "content_hash": content_hash,
        "integrity_note": "content hash recorded at import: "
        + content_hash + "; " + marks,
        "control_flag": validated["control_designation"] is not None,
        "control_kind": validated["control_designation"],
        "answer_text": text,
        "answer_size": {
            "characters": len(text),
            "words": len(text.split()),
        },
    }


def prepare_import(*, answer_file=None, product=None, round=None,
                   engine_label=None, query=None, kind=None,
                   captured_on=None, capture_method=None,
                   control_designation=None, audit_date=None,
                   known_round=True, query_set=None,
                   standing_records=(), control_count=0,
                   product_id=None, round_id=None, answer_id=None,
                   registry_version_at_import=None,
                   detector_version_at_import=None):
    """Validate one import and build its AnswerRecord.

    Validation completes before any store write: this function
    writes nothing. It returns the record for the caller to
    store as one journal entry, or raises ProbeImportError
    carrying the entry 13 token for the recorded error the
    caller appends as the one failure record, on the scoped
    terms contract C1 states. The round stamps at first import
    are written by the caller through the journal, from the
    registry and detector versions this record carries, at
    SEAM-ROUND-STAMP; this module is their sole computing
    source and writes no stamp itself.
    """
    validated = validate_adapter_inputs(
        answer_file=answer_file, product=product, round=round,
        engine_label=engine_label, query=query, kind=kind,
        captured_on=captured_on, capture_method=capture_method,
        control_designation=control_designation,
        audit_date=audit_date, known_round=known_round,
        query_set=query_set, control_count=control_count)
    raw, text, content_hash = read_answer_file(answer_file)
    form = check11_form(raw, text)
    if form is not None:
        _fail("IMPORT_VALIDATION_FAILED",
              "answer file meets validation check 11 test: " + form)
    if is_transcript_form(text):
        _fail("UNCOVERED_IMPORT_FORM",
              "a form meeting none of the six tests at validation "
              "check 11, a Markdown transcript among them, is "
              "rejected as a class")
    candidate = {
        "kind": validated["kind"],
        "product_id": product_id,
        "product": product,
        "round_id": round_id,
        "round": round,
        "engine_label_normalised": validated[
            "engine_label_normalised"],
        "query": validated["query"],
        "captured_on": validated["captured_on"],
        "content_hash": content_hash,
    }
    outcome = compare_standing(standing_records, candidate)
    if outcome == "duplicate":
        _fail("DUPLICATE_IMPORT",
              "a standing record holds the duplicate key for this "
              "import")
    if outcome == "contradiction":
        _fail("CONTRADICTORY_IMPORT",
              "a standing record holds the same round, normalised "
              "engine label, query, and captured_on with a "
              "different content hash")
    return build_answer_record(
        validated, text=text, content_hash=content_hash,
        form_marks=[], product_id=product_id, round_id=round_id,
        answer_id=answer_id,
        registry_version_at_import=registry_version_at_import,
        detector_version_at_import=detector_version_at_import)


FAILURE_RECORD_BARRED_TOKENS = (
    "JOURNAL_VERIFY_FAILED",
    "JOURNAL_CAP_EXCEEDED",
    "WRITE_CONTENDED",
)


def failure_record_allowed(error_value=None, *, chain_barred=False,
                           chain_at_cap=False, contended=False):
    """The failure record scoping rule, contract C1 and item 158.

    A failed import leaves exactly one failure record where
    the chain accepts appends. On a barred chain, at the
    chain cap, or under contention, no failure record stands:
    the recorded error is the caller response only. This
    module appends no failure record itself; it states the
    rule in one named place for the caller that appends, so
    the scoped terms travel with the import validation that
    raises the recorded error. Returns True where a failure
    record may be appended, and False on any barred term or
    where the error value itself is one of the three barred
    tokens, whatever flags the caller also supplies.
    """
    if chain_barred or chain_at_cap or contended:
        return False
    if error_value is not None and str(
            error_value) in FAILURE_RECORD_BARRED_TOKENS:
        return False
    return True


def probe_import(*, answer_file=None, product=None, round=None,
                 engine_label=None, query=None, kind=None,
                 captured_on=None, capture_method=None,
                 control_designation=None, audit_date=None,
                 known_round=True, query_set=None,
                 standing_records=(), control_count=0,
                 product_id=None, round_id=None, answer_id=None,
                 registry_version_at_import=None,
                 detector_version_at_import=None):
    """The service facing adapter for one import.

    The nine adapter inputs are the contract inputs, in
    operator order: answer_file, product, round,
    engine_label, query, kind, captured_on, and
    capture_method required, and control_designation
    optional. Every input stands optional in this signature
    on purpose: an omitted input stands as None here, so a
    call missing any required input reaches validation and
    fails with the recorded error value
    IMPORT_VALIDATION_FAILED naming the field, as a
    ProbeImportError the caller receives. A missing input
    never raises a TypeError out of this seam, and a
    TypeError raised inside validation on a malformed input
    set stands converted to the same recorded error value.
    On a valid input set this adapter returns exactly what
    prepare_import returns, and it writes nothing itself.
    """
    try:
        return prepare_import(
            answer_file=answer_file, product=product, round=round,
            engine_label=engine_label, query=query, kind=kind,
            captured_on=captured_on, capture_method=capture_method,
            control_designation=control_designation,
            audit_date=audit_date, known_round=known_round,
            query_set=query_set, standing_records=standing_records,
            control_count=control_count, product_id=product_id,
            round_id=round_id, answer_id=answer_id,
            registry_version_at_import=registry_version_at_import,
            detector_version_at_import=detector_version_at_import)
    except ProbeImportError:
        raise
    except TypeError as error:
        _fail("IMPORT_VALIDATION_FAILED",
              "adapter call does not match the contract inputs: "
              + str(error))


def build_worksheet_text(*, product=None, round=None, queries=(),
                         engine_labels=(), planned_answers=0):
    """The capture worksheet text for one named round.

    One slot stands per planned answer, and each slot carries
    the metadata fields the import format will later require,
    named once in that slot and nowhere else in the worksheet,
    so a slot count can be read from the field names. The
    worksheet states the round label, the query list, and the
    engine labels to attempt. The operator captures by hand
    against the worksheet and fills the slots; the completed
    worksheet imports back through the import route above.
    """
    lines = [
        "Citeline capture worksheet",
        "product: " + str(product),
        "round: " + str(round),
        "queries to attempt:",
    ]
    for query in queries:
        lines.append("query: " + str(query))
    lines.append("engine labels to attempt:")
    for label in engine_labels:
        lines.append("engine: " + str(label))
    lines.append("slots to fill by hand, one answer per slot:")
    lines.append("| slot | answer text stands below its slot line |")
    for index in range(1, int(planned_answers) + 1):
        lines.append(
            "slot %d: engine_label= kind= captured_on= "
            "capture_method=" % index)
    return "\n".join(lines) + "\n"


def export_capture_worksheet(*, output_path, product=None, round=None,
                             queries=(), engine_labels=(),
                             planned_answers=0):
    """Write one capture worksheet file from a named round.

    Returns the worksheet text written. This operation
    captures nothing, fetches nothing, and queries nothing.
    """
    text = build_worksheet_text(
        product=product, round=round, queries=queries,
        engine_labels=engine_labels, planned_answers=planned_answers)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return text
