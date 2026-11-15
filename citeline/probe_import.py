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
import os
import re
import stat
import unicodedata
from datetime import date, datetime

ENGINE_LABEL_LIMIT = 200
CAPTURE_METHOD_LIMIT = 2000
ERROR_MESSAGE_LIMIT = 500
FRONT_MATTER_BLOCK_LIMIT = 16 * 1024
FRONT_MATTER_KEY_LIMIT = 100
FRONT_MATTER_VALUE_LIMIT = 4096
FRONT_MATTER_JSON_DEPTH_LIMIT = 100
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
        # The error message length limit (limit 33, 500
        # characters) binds every surface the product emits,
        # the message raised to a library caller included, not
        # only the recorded and printed forms (entry
        # S17-R2-088). The token stands at the head of the
        # message, so bounding the message keeps the token and
        # the opening of the detail standing.
        if len(message) > ERROR_MESSAGE_LIMIT:
            message = message[:ERROR_MESSAGE_LIMIT]
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
    if isinstance(value, datetime):
        # A datetime is a date subclass, but it is not the
        # date form the contract states, and comparing one
        # against a plain date raises a raw TypeError on the
        # worksheet seam, outside the recorded vocabulary
        # (entry S17-R2-041). It refuses here, in the
        # vocabulary, on every route alike.
        _fail("IMPORT_VALIDATION_FAILED",
              field_name + " must stand as ISO date text in the "
              "form YYYY-MM-DD or as a date, not as a datetime")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        _fail("IMPORT_VALIDATION_FAILED",
              field_name + " must stand as ISO date text in the "
              "form YYYY-MM-DD, not as a value of another type: "
              + type(value).__name__)
    try:
        return date.fromisoformat(value)
    except ValueError:
        _fail("IMPORT_VALIDATION_FAILED",
              field_name + " is not an ISO date: " + value)


_TEXT_INPUT_FIELDS = ("product", "round", "engine_label", "query",
                      "capture_method")


def _require_text_inputs(values):
    """Refuse a non string text input at validation.

    The adapter contract names its text inputs as text: an
    engine label, a query, a capture method, a product, and a
    round stand as strings, in the forms the record stores.
    A value of any other type (bytes, a number, a list, a
    mapping) fails validation here, before any store write,
    instead of being stringified into a form no operator
    asserted or dying later at the journal write with no
    failure record standing (entries S17-R1-036 and
    S17-R1X-031).
    """
    for name in _TEXT_INPUT_FIELDS:
        value = values.get(name)
        if value is not None and not isinstance(value, str):
            _fail("IMPORT_VALIDATION_FAILED",
                  name + " must stand as text, not as a value "
                  "of type " + type(value).__name__)
    control = values.get("control_designation")
    if control is not None and not isinstance(control, str):
        _fail("IMPORT_VALIDATION_FAILED",
              "control_designation must stand as text, not as "
              "a value of type " + type(control).__name__)
    kind = values.get("kind")
    if kind is not None and not isinstance(kind, str):
        _fail("IMPORT_VALIDATION_FAILED",
              "kind must stand as text, not as a value of "
              "type " + type(kind).__name__)


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
    csv.field_size_limit(ANSWER_FILE_LIMIT)
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


def _is_head_char(char):
    """One character of head material the form tests skip.

    Byte order marks, control bytes, whitespace, and zero
    width format characters stand in this set. The head
    reading removes them in any interleaving and in any
    number, so a mark standing after a control byte or a
    space, a third mark, and a zero width space shield
    nothing behind them (entry S17-R2-033, completing the
    S17-R1-032 cure, which removed one mark and then the
    control bytes in that order and only at the very
    start).
    """
    return (
        char == "\ufeff"
        or ord(char) < 0x20
        or ord(char) == 0x7f
        or char in " \t\n\r\f"
        or unicodedata.category(char) == "Cf")


def _strip_head(text):
    """The text past any interleaved head material."""
    index = 0
    while index < len(text) and _is_head_char(text[index]):
        index += 1
    return text[index:]


def _detection_text(text):
    """The text the form tests read, at the head of a file.

    A byte order mark stripped under item 107 and any
    leading control bytes stand removed for the tests, so a
    mark or a control byte at the head cannot shield the
    material behind it from the tests (entry S17-R1-032).
    The stored text keeps its own form; only the tests read
    through this head.
    """
    return _strip_head(text)


def _raw_variants(raw_bytes):
    """The raw heads the magic tests read.

    The plain bytes, and the bytes past any interleaved
    head material in front of them, so a container
    signature stands found wherever a mark, a control
    byte, or a zero width form stands in front of it, in
    any order and in any number (entry S17-R2-033). The
    raw reading strips the same material the text
    reading strips: the head of the bytes stands decoded
    one character at a time, and every character the
    text head predicate holds, the whole Unicode format
    category among them, stands removed in its encoded
    form, not only the seven byte sequences an earlier
    form of this reading listed, so a format character
    outside that list shields nothing (entry
    S17-R3-024).
    """
    variants = [raw_bytes]
    body = raw_bytes
    while body:
        first = body[0]
        if first < 0x20 or first == 0x7f or first == 0x20:
            body = body[1:]
            continue
        if first < 0x80:
            break
        char = None
        for width in (2, 3, 4):
            try:
                char = body[:width].decode("utf-8")
            except (UnicodeDecodeError, ValueError):
                char = None
                continue
            if len(char) == 1:
                break
            char = None
        if char is None or len(char) != 1:
            break
        if _is_head_char(char):
            body = body[len(char.encode("utf-8")):]
            continue
        break
    if body != raw_bytes:
        variants.append(body)
    return variants


def _loads_json(text):
    """One JSON load under the recorded failure forms.

    A nesting depth past the platform recursion bound fails
    validation in the recorded vocabulary, never as a raw
    RecursionError carrying its message as an error value
    (entry S17-R1-033).
    """
    try:
        return json.loads(text), True
    except RecursionError:
        _fail("IMPORT_VALIDATION_FAILED",
              "the file nests JSON deeper than the reader can "
              "hold; save the answer text on its own in a "
              "plain text or Markdown file, then import that "
              "file")
    except ValueError:
        return None, False


def check11_form(raw_bytes, text):
    """Run the six tests of validation check 11.

    Returns the name of the test met, one of archive, pdf,
    html, json, json_lines, or delimited, or None where no
    test is met. A file meeting one of these tests is not one
    answer and fails import on that ground.
    """
    for variant in _raw_variants(raw_bytes):
        for magic in _ARCHIVE_MAGICS:
            if variant.startswith(magic):
                return "archive"
        if variant.startswith(b"%PDF-"):
            return "pdf"
    first = _detection_text(text)
    lowered = first.casefold()
    if lowered.startswith("<!doctype") and (
            len(lowered) == 9 or lowered[9] in " \t\n\r\f"):
        return "html"
    if lowered.startswith("<html") and (
            len(lowered) == 5 or lowered[5] in " \t\n\r\f/>"):
        return "html"
    stripped = first.strip()
    if stripped:
        value, parsed = _loads_json(stripped)
        if parsed and isinstance(value, (dict, list)):
            return "json"
        nonempty = [line for line in first.splitlines() if line.strip()]
        if len(nonempty) >= 2:
            all_json = True
            for line in nonempty:
                _value, ok = _loads_json(line)
                if not ok:
                    all_json = False
                    break
            if all_json:
                return "json_lines"
    delimited = _delimited_test(first)
    if delimited == "parse_failed":
        _fail("IMPORT_VALIDATION_FAILED",
              "delimited parse could not complete")
    if delimited:
        return "delimited"
    return None


_FORM_REFUSAL_TEXT = {
    "archive": (
        "the file is an archive, not answer text. Unpack it "
        "outside the tool, save the answer text on its own "
        "in a plain text or Markdown file, then import that "
        "file"),
    "pdf": (
        "the file is a PDF, not answer text. Save the answer "
        "text on its own in a plain text or Markdown file, "
        "then import that file"),
    "html": (
        "the file is an HTML document, not answer text. Save "
        "the answer text on its own in a plain text or "
        "Markdown file, then import that file"),
    "json": (
        "the file is JSON, not answer text. JSON is never "
        "imported as an answer. Save or paste the answer "
        "text on its own in a plain text or Markdown file, "
        "then import that file"),
    "json_lines": (
        "the file holds one JSON value per line, not answer "
        "text. Save the answer text on its own in a plain "
        "text or Markdown file, then import that file"),
    "delimited": (
        "the file is a table of delimited rows, not one "
        "answer. Save the answer text on its own in a plain "
        "text or Markdown file, then import that file"),
}


def _form_refusal(form):
    """The plain refusal for one form check 11 found.

    The refusal names the form in plain words and states
    the next step, with no internal check vocabulary on the
    operator surface (entry S17-R1-106).
    """
    _fail("IMPORT_VALIDATION_FAILED",
          _FORM_REFUSAL_TEXT.get(
              form, "the file is not answer text in a form "
              "the import accepts"))


def _json_depth(value):
    """The nesting depth of one parsed JSON value, counted
    iteratively so a deep value measures without recursion."""
    depth = 0
    stack = [(value, 1)]
    while stack:
        current, level = stack.pop()
        if isinstance(current, (dict, list)):
            depth = max(depth, level)
            children = current.values() if isinstance(
                current, dict) else current
            for child in children:
                stack.append((child, level + 1))
    return depth


def _front_matter_key_value(line):
    """One front matter line as its key and value, or None.

    A key written in quotes names the same key as its plain
    form: the quoted form and the plain form of one key are
    one key for the duplicate control (entry S17-R2-040).
    The key reading therefore removes one pair of matching
    quote characters around the key, and a colon inside a
    quoted key does not split the line.
    """
    text = line.strip()
    if text[:1] in ("\"", "'"):
        quote = text[0]
        index = 1
        pieces = []
        while index < len(text):
            char = text[index]
            if quote == '"' and char == "\\" and index + 1 < len(text):
                pieces.append(text[index + 1])
                index += 2
                continue
            if char == quote:
                if quote == "'" and text[index + 1:index + 2] == "'":
                    pieces.append("'")
                    index += 2
                    continue
                break
            pieces.append(char)
            index += 1
        rest = text[index + 1:] if index < len(text) else ""
        if not rest.lstrip().startswith(":"):
            return None
        return "".join(pieces), rest.lstrip()[1:].strip()
    if ":" not in line:
        return None
    key, value = line.split(":", 1)
    return key.strip(), value.strip()


def extract_front_matter(text):
    """Split a head front matter block from an answer text.

    A block at the head, opened and closed by a line of
    three dashes (a closing line of three dots also closes
    it), stands under the D17 control set: duplicate keys
    are rejected, tag constructs are rejected, a block in
    JSON object form is read with duplicate keys rejected,
    and any failure fails the import closed, with no
    partial metadata read. A passing block is excluded
    from the answer text the record stores, while the
    content hash stands over the whole raw file, as the
    brief states. Returns (body_text, had_front_matter).
    A text with no head block returns itself unchanged.
    """
    # Head material in front of the fence (a control byte,
    # a mark, a zero width form) does not move the block off
    # the head: the block stands read where it stands once
    # that material is skipped, as the check 11 tests read
    # through the same head (entry S17-R2-033, front matter
    # limb). A text whose head holds no fence after that
    # material returns itself unchanged, head included.
    working = _strip_head(text)
    lines = working.splitlines()
    if not lines or lines[0].strip() != "---":
        return text, False
    text = working
    lines = text.splitlines()
    closing = None
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            closing = index
            break
    if closing is None:
        _fail("IMPORT_VALIDATION_FAILED",
              "the front matter block at the head of the file "
              "is not closed; fix the block or remove it, "
              "then import the file again")
    block_lines = lines[1:closing]
    block = "\n".join(block_lines).strip()
    # The Section 5.11 size family of the same control set
    # stands enforced here, in both front matter forms and
    # in worksheet slot bodies, which run through this same
    # reading (entry S17-R2-037): limit 11, block size
    # 16 KiB, measured in bytes as the page side measures
    # it; limit 12, key count 100; limit 17, value length
    # 4,096 characters; and limit 18, JSON nesting depth
    # 100 on the JSON form. The adapter receives no home,
    # so the brief values govern here, as they govern the
    # answer file size at this same seam.
    if len("\n".join(block_lines).encode("utf-8")) \
            > FRONT_MATTER_BLOCK_LIMIT:
        _fail("LIMIT_EXCEEDED",
              "front matter block size limit is 16 KiB, with "
              "rejection and no partial record")
    if block.startswith("{"):
        def _no_duplicates(pairs):
            seen = set()
            for key, _value in pairs:
                if key in seen:
                    _fail("IMPORT_VALIDATION_FAILED",
                          "the front matter block in JSON form "
                          "holds the key " + str(key) + " twice; "
                          "front matter keys stand once each")
                seen.add(key)
            return dict(pairs)
        try:
            parsed = json.loads(
                block, object_pairs_hook=_no_duplicates)
        except ProbeImportError:
            raise
        except (ValueError, RecursionError):
            _fail("IMPORT_VALIDATION_FAILED",
                  "the front matter block in JSON form does "
                  "not read as one JSON object; fix the block "
                  "or remove it, then import the file again")
        if not isinstance(parsed, dict):
            _fail("IMPORT_VALIDATION_FAILED",
                  "the front matter block in JSON form does "
                  "not read as one JSON object; fix the block "
                  "or remove it, then import the file again")
        if len(parsed) > FRONT_MATTER_KEY_LIMIT:
            _fail("LIMIT_EXCEEDED",
                  "front matter key count limit is 100, with "
                  "rejection and no partial record")
        if _json_depth(parsed) > FRONT_MATTER_JSON_DEPTH_LIMIT:
            _fail("LIMIT_EXCEEDED",
                  "JSON nesting depth limit is 100, with "
                  "rejection and no partial record")
        for value in parsed.values():
            if isinstance(value, str):
                measured = len(value)
            elif isinstance(value, (dict, list)):
                measured = len(json.dumps(
                    value, ensure_ascii=False))
            else:
                measured = 0
            if measured > FRONT_MATTER_VALUE_LIMIT:
                _fail("LIMIT_EXCEEDED",
                      "front matter value length limit is "
                      "4,096 characters, with rejection and "
                      "no partial record")
    else:
        seen_keys = set()
        key_count = 0
        current_value_length = None
        for block_line in block_lines:
            if not block_line.strip() or block_line.lstrip() \
                    .startswith("#"):
                continue
            pair = _front_matter_key_value(block_line)
            if pair is None:
                if block_line[0] in " \t" \
                        and current_value_length is not None:
                    # An indented line with no key of its own
                    # stands as a continuation of the value
                    # above it, and the line form checks stand
                    # on it as on a top level line: its text
                    # counts toward that value length, and a
                    # tag construct on it stands refused
                    # (entry S17-R3-027).
                    continuation = block_line.strip()
                    current_value_length += len(continuation)
                    if current_value_length \
                            > FRONT_MATTER_VALUE_LIMIT:
                        _fail("LIMIT_EXCEEDED",
                              "front matter value length limit "
                              "is 4,096 characters, with "
                              "rejection and no partial record")
                    if continuation.startswith(
                            ("!", "&", "*", "%")) or re.search(
                            r"<[A-Za-z][^>]*>", continuation):
                        _fail("IMPORT_VALIDATION_FAILED",
                              "the front matter block holds a "
                              "tag construct, which the front "
                              "matter control set refuses")
                    continue
                _fail("IMPORT_VALIDATION_FAILED",
                      "a front matter line holds no key and "
                      "value: " + block_line.strip()[:60])
            key, value = pair
            key_count += 1
            if key_count > FRONT_MATTER_KEY_LIMIT:
                _fail("LIMIT_EXCEEDED",
                      "front matter key count limit is 100, "
                      "with rejection and no partial record")
            if len(value) > FRONT_MATTER_VALUE_LIMIT:
                _fail("LIMIT_EXCEEDED",
                      "front matter value length limit is "
                      "4,096 characters, with rejection and "
                      "no partial record")
            current_value_length = len(value)
            if not key:
                _fail("IMPORT_VALIDATION_FAILED",
                      "a front matter line holds no key: "
                      + block_line.strip()[:60])
            if key in seen_keys:
                _fail("IMPORT_VALIDATION_FAILED",
                      "the front matter block holds the key "
                      + key + " twice; front matter keys "
                      "stand once each")
            seen_keys.add(key)
            if value.startswith(("!", "&", "*", "%")) or \
                    re.search(r"<[A-Za-z][^>]*>", value):
                _fail("IMPORT_VALIDATION_FAILED",
                      "the front matter block holds a tag "
                      "construct, which the front matter "
                      "control set refuses")
            if (value.count("[") != value.count("]")
                    or value.count("{") != value.count("}")):
                _fail("IMPORT_VALIDATION_FAILED",
                      "a front matter value is not closed: "
                      + value[:60])
    body = "\n".join(lines[closing + 1:])
    return body, True


def is_transcript_form(text):
    """A Markdown transcript of a whole conversation.

    A form meeting none of the six check 11 tests, rejected as
    a class under the uncovered forms rule at item 147. The
    marks read here are a heading naming a transcript, or two
    or more speaker turns opening lines of the file.
    """
    lines = text.splitlines()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if "transcript" in heading.casefold() and len(heading) < 80:
                return True
    turns = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if _SPEAKER_RE.match(stripped):
            turns += 1
            if turns >= 2:
                return True
            continue
        break
    return False


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
    _require_text_inputs({
        "product": product, "round": round,
        "engine_label": engine_label, "query": query,
        "capture_method": capture_method,
        "control_designation": control_designation, "kind": kind})
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
    if len(engine_label) > ENGINE_LABEL_LIMIT:
        _fail("LIMIT_EXCEEDED",
              "engine label length limit is 200 code points")
    if isinstance(capture_method, str) \
            and len(capture_method) > CAPTURE_METHOD_LIMIT:
        # Limit 31 binds the value that governs the stored
        # record: a slot asserted capture method reaches the
        # record through this validation, so the limit stands
        # checked here, on the asserted value itself, and not
        # only on the value the call carries at the service
        # seam (entry S17-R2-038).
        _fail("LIMIT_EXCEEDED",
              "capture method text length limit is 2,000 "
              "code points")
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
    path_text = str(answer_file)
    try:
        pre = os.lstat(path_text)
    except OSError as error:
        _fail("IMPORT_VALIDATION_FAILED",
              "answer file cannot be read: " + str(error))
    if stat.S_ISLNK(pre.st_mode):
        _fail("SUPPLIED_PATH_UNSAFE",
              "a supplied path that is itself a symbolic link "
              "is rejected")
    if not stat.S_ISREG(pre.st_mode):
        if stat.S_ISDIR(pre.st_mode):
            _fail("IMPORT_VALIDATION_FAILED",
                  "answer file cannot be read: Is a directory: "
                  + path_text)
        _fail("SUPPLIED_PATH_UNSAFE",
              "a supplied path that does not name a regular "
              "file is rejected")
    if pre.st_nlink > 1:
        _fail("SUPPLIED_PATH_UNSAFE",
              "a supplied file with a hard link count above 1 "
              "is rejected; this reading rests on the "
              "filesystem maintaining a truthful link count, "
              "and where a platform cannot give that count the "
              "invocation refuses the supplied file and fails "
              "closed")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(path_text, flags)
    except OSError as error:
        _fail("IMPORT_VALIDATION_FAILED",
              "answer file cannot be read: " + str(error))
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (pre.st_dev, pre.st_ino):
            _fail("SUPPLIED_PATH_UNSAFE",
                  "the opened handle does not match the pre "
                  "open stat")
        if not stat.S_ISREG(opened.st_mode):
            _fail("SUPPLIED_PATH_UNSAFE",
                  "the opened handle does not name a regular file")
        if opened.st_nlink > 1:
            _fail("SUPPLIED_PATH_UNSAFE",
                  "a supplied file with a hard link count above 1 "
                  "is rejected")
        chunks = []
        total = 0
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > ANSWER_FILE_LIMIT:
                _fail("LIMIT_EXCEEDED", "answer file limit is 1 MiB")
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    if len(raw) > ANSWER_FILE_LIMIT:
        _fail("LIMIT_EXCEEDED", "answer file limit is 1 MiB")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _fail("IMPORT_VALIDATION_FAILED",
              "answer file is not UTF-8 text")
    if text.startswith("\ufeff"):
        # Item 107: a single leading byte order mark is
        # stripped once. The content hash above stands over
        # the raw bytes, mark included.
        text = text[1:]
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


def compare_standing_record(standing_records, candidate):
    """The comparison with the standing record it met.

    Returns (outcome, record): the outcome compare_standing
    states and the standing record that produced it, or
    (None, None) for a new record. The record travels so a
    refusal can name the standing answer it conflicts with.
    """
    outcome = compare_standing(standing_records, candidate)
    if outcome is None:
        return None, None
    for record in standing_records or []:
        single = compare_standing([record], candidate)
        if single == outcome:
            return outcome, record
    return outcome, None


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
    if is_worksheet_text(text):
        _fail("IMPORT_VALIDATION_FAILED",
              "the file is a capture worksheet, which holds "
              "one answer per slot. It imports slot by slot "
              "through the worksheet route, not as one "
              "answer; import it with the probe import call "
              "naming its product and round")
    body, _had_front_matter = extract_front_matter(text)
    return _record_from_body(
        validated, body_text=body, raw_bytes=raw,
        content_hash=content_hash,
        standing_records=standing_records, product=product,
        round=round, product_id=product_id, round_id=round_id,
        answer_id=answer_id,
        registry_version_at_import=registry_version_at_import,
        detector_version_at_import=detector_version_at_import)


def _record_from_body(validated, *, body_text, raw_bytes,
                      content_hash, standing_records, product,
                      round, product_id=None, round_id=None,
                      answer_id=None,
                      registry_version_at_import=None,
                      detector_version_at_import=None,
                      standing_id_resolver=None):
    """Build one AnswerRecord from one answer body.

    The body stands already split from any front matter.
    Validation check 11 and the uncovered forms rule run
    on the body exactly as they run on a standalone file,
    so material a standalone file refuses stands refused
    here too, in a worksheet slot as in a file.
    """
    form = check11_form(raw_bytes, body_text)
    if form is not None:
        _form_refusal(form)
    if is_transcript_form(body_text):
        _fail("UNCOVERED_IMPORT_FORM",
              "the answer is a transcript of a whole "
              "conversation, which imports as no answer. "
              "Split it into one file per answer outside "
              "the tool, then import each file on its own")
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
    outcome, standing = compare_standing_record(
        standing_records, candidate)
    if outcome == "duplicate":
        _fail("DUPLICATE_IMPORT",
              "the same answer already stands imported for "
              "this round, engine, and query, so this import "
              "would count it twice and stands refused")
    if outcome == "contradiction":
        standing_id = _record_field(standing, "answer_id")
        if standing_id is not None and standing_id_resolver is not None:
            # The refusal names the standing answer by the
            # identity it stands under in the journal, never
            # by an unresolved marker the batch append would
            # have resolved at its storing sequence (entry
            # S17-R2-097).
            standing_id = standing_id_resolver(standing_id)
        name = (" (standing answer " + str(standing_id) + ")"
                if standing_id is not None else "")
        _fail("CONTRADICTORY_IMPORT",
              "a different answer already stands for the "
              "same round, engine, query, and capture date"
              + name + ". Only one answer stands for that "
              "combination, so this import stores nothing. "
              "To import this answer, give it a different "
              "capture date, or import it under a different "
              "round, engine, or query")
    return build_answer_record(
        validated, text=body_text, content_hash=content_hash,
        form_marks=[], product_id=product_id, round_id=round_id,
        answer_id=answer_id,
        registry_version_at_import=registry_version_at_import,
        detector_version_at_import=detector_version_at_import)


WORKSHEET_HEADER = "Citeline capture worksheet"

_SLOT_FIELD_MARKERS = (" query= ", " engine_label= ", " kind= ",
                       " captured_on= ", " capture_method= ")
_SLOT_FIELDS = ("query", "engine_label", "kind", "captured_on",
               "capture_method")


def _worksheet_lines(text):
    """The lines of a worksheet text, past its head material.

    A blank line or a control byte saved in front of the
    header does not move the sheet off its head: leading
    lines that hold nothing but head material stand
    skipped, whether that material stands on its own line
    or mixed with spaces, and head material standing on
    the header line itself stands stripped, so the sheet
    reads as the sheet it is (entry S17-R2-034, completed
    at entry S17-R3-025 for head material on its own
    line). The header line stands first in the returned
    list, where one stands.
    """
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if all(_is_head_char(char) for char in line):
            index += 1
            continue
        stripped = line
        cut = 0
        while cut < len(stripped) and _is_head_char(stripped[cut]):
            cut += 1
        lines[index] = stripped[cut:]
        break
    return lines[index:]


def is_worksheet_text(text):
    """True where a text is a capture worksheet.

    The worksheet carries its own header line, written by
    the export in this module. That header is the mark the
    import route reads a returned sheet by. A sheet
    standing behind a blank line or a control byte reads
    as a sheet here, so it meets the worksheet route or
    its refusal, and never the plain answer path (entry
    S17-R2-034).
    """
    if not isinstance(text, str):
        return False
    lines = _worksheet_lines(text)
    return bool(lines) and lines[0].strip() == WORKSHEET_HEADER


def is_worksheet_file(answer_file):
    """True where a supplied file reads as a worksheet.

    A file that cannot be read stands as no worksheet here;
    the import route raises its own recorded error for it
    on the ordinary path.
    """
    try:
        _raw, text, _hash = read_answer_file(answer_file)
    except Exception:
        return False
    return is_worksheet_text(text)


def _slot_value(raw):
    """One slot field value as asserted, or None.

    The exported slot line carries each field with a
    parenthesised description and example where no value
    stands asserted yet. A value in that template form
    asserts nothing; any other value stands as asserted.
    """
    value = raw.strip()
    if not value or value.startswith("("):
        return None
    return value


def _parse_slot_line(line):
    """Parse one slot line into its field values.

    Fields stand in the exported order: query, engine
    label, kind, captured_on, capture_method. A line that
    does not carry the fields in that order is no slot
    line this parser reads, and returns None.
    """
    match = re.match(r"^slot (\d+):(.*)$", line)
    if not match:
        return None
    rest = match.group(2)
    values = {}
    position = 0
    starts = {}
    for field in _SLOT_FIELDS:
        marker = " " + field + "= "
        start = rest.find(marker, position)
        if start < 0:
            return None
        if field == _SLOT_FIELDS[0] and start != 0:
            return None
        starts[field] = start
        position = start + len(marker)
    ordered = [starts[field] for field in _SLOT_FIELDS]
    for index, field in enumerate(_SLOT_FIELDS):
        start = starts[field] + len(" " + field + "= ")
        end = ordered[index + 1] if index + 1 < len(ordered) \
            else len(rest)
        values[field] = _slot_value(rest[start:end])
    return {"index": int(match.group(1)), "fields": values}


def parse_worksheet(text):
    """Parse a capture worksheet into its stated parts.

    Returns a dict with the stated product and round, the
    stated query and engine lists, and the slots, each
    slot holding its field values (None where the slot
    asserts none) and the body text standing below its
    slot line, up to the next slot line.
    """
    lines = _worksheet_lines(text)
    sheet = {"product": None, "round": None, "queries": [],
             "engines": [], "slots": []}
    section = None
    current = None
    slots_open = False
    expected_index = 1
    for line in lines[1:]:
        if line.startswith("slots to fill"):
            section = "slots"
            slots_open = True
            if current is not None:
                current["body_lines"].append(line)
            continue
        slot_match = re.match(r"^slot (\d+):", line)
        if slot_match and slots_open:
            # Slot lines stand judged against the sheet the
            # export wrote (entry S17-R2-036): a slot line
            # the export wrote stands in the slots section,
            # carries its five fields in the exported order,
            # and carries the next index in the sequence the
            # export wrote. A line in slot form that meets
            # none of that stands as answer text where a
            # slot body stands open, and as no slot anywhere
            # else, so captured text can neither forge a
            # slot nor destroy the sheet for standing in
            # slot form.
            parsed = _parse_slot_line(line)
            if parsed is not None and parsed["index"] == expected_index:
                current = {"index": parsed["index"],
                           "fields": parsed["fields"],
                           "body_lines": []}
                sheet["slots"].append(current)
                section = "slots"
                expected_index += 1
                continue
        if current is not None:
            current["body_lines"].append(line)
            continue
        if line.startswith("product: "):
            sheet["product"] = line[len("product: "):].strip()
        elif line.startswith("round: "):
            sheet["round"] = line[len("round: "):].strip()
        elif line.strip() == "queries to attempt:":
            section = "queries"
        elif line.strip() == "engine labels to attempt:":
            section = "engines"
        elif line.startswith("slots to fill"):
            section = "slots"
        elif section == "queries" and line.startswith("query: "):
            sheet["queries"].append(line[len("query: "):].strip())
        elif section == "engines" and line.startswith("engine: "):
            sheet["engines"].append(line[len("engine: "):].strip())
    for slot in sheet["slots"]:
        slot["body"] = "\n".join(slot.pop("body_lines")).strip("\n")
    return sheet


def prepare_worksheet_import(*, answer_file=None, product=None,
                             round=None, engine_label=None,
                             query=None, kind=None,
                             captured_on=None, capture_method=None,
                             control_designation=None,
                             audit_date=None, known_round=True,
                             query_set=None, standing_records=(),
                             control_count=0, product_id=None,
                             round_id=None, answer_id_prefix=None,
                             registry_version_at_import=None,
                             detector_version_at_import=None,
                             answer_sequence_base=None):
    """Validate one returned worksheet and build its records.

    The sheet binds the import: its stated product and
    round must match the call, or the import stands
    refused. Each filled slot stands as one answer. A
    slot field the sheet asserts governs that slot; a
    field it asserts nothing for takes the call value.
    A slot whose query stands asserted nowhere (not on
    the slot, and not as the one query the sheet states)
    refuses the import, because its answer cannot be
    placed. An unfilled sheet stores nothing: where no
    slot holds any answer text, the import stands
    refused. Validation of every filled slot completes
    before any record returns, so a refused sheet stores
    nothing at all.
    """
    _raw, text, _hash = read_answer_file(answer_file)
    if not is_worksheet_text(text):
        _fail("IMPORT_VALIDATION_FAILED",
              "the file is not a capture worksheet")
    sheet = parse_worksheet(text)
    if query is not None and sheet["queries"] \
            and query not in sheet["queries"]:
        _fail("IMPORT_VALIDATION_FAILED",
              "the worksheet states queries "
              + ", ".join(sheet["queries"])
              + " and the import call names " + str(query)
              + ", which stands in none of them; the sheet "
              "queries bind the import")
    if sheet["product"] is not None and product is not None \
            and sheet["product"] != str(product):
        _fail("IMPORT_VALIDATION_FAILED",
              "the worksheet states product " + sheet["product"]
              + " and the import call names " + str(product)
              + "; a worksheet imports only for the product "
              "it states")
    if sheet["round"] is not None and round is not None \
            and sheet["round"] != str(round):
        _fail("IMPORT_VALIDATION_FAILED",
              "the worksheet states round " + sheet["round"]
              + " and the import call names " + str(round)
              + "; a worksheet imports only into the round "
              "it states")
    filled = [slot for slot in sheet["slots"]
              if slot["body"].strip()]
    if not filled:
        _fail("IMPORT_VALIDATION_FAILED",
              "the worksheet holds no filled slot: no slot "
              "carries any answer text, so nothing stands "
              "to import. Fill at least one slot below its "
              "slot line, then import the sheet again")
    records = []
    running_standing = list(standing_records or [])
    running_controls = control_count
    for slot in filled:
        fields = slot["fields"]
        slot_query = fields.get("query")
        if slot_query is None:
            if len(sheet["queries"]) == 1:
                slot_query = sheet["queries"][0]
            else:
                _fail("IMPORT_VALIDATION_FAILED",
                      "slot " + str(slot["index"]) + " names "
                      "no query and the worksheet states "
                      + str(len(sheet["queries"])) + " queries, "
                      "so the slot answer cannot be placed. "
                      "Write the query the slot answers on "
                      "its slot line, then import again")
        slot_validated = validate_adapter_inputs(
            answer_file=answer_file, product=product, round=round,
            engine_label=fields.get("engine_label") or engine_label,
            query=slot_query,
            kind=fields.get("kind") or kind,
            captured_on=fields.get("captured_on") or captured_on,
            capture_method=fields.get("capture_method")
            or capture_method,
            control_designation=control_designation,
            audit_date=audit_date, known_round=known_round,
            query_set=query_set, control_count=running_controls)
        body, _fm = extract_front_matter(slot["body"].strip())
        body_bytes = body.encode("utf-8")
        answer_id = None
        if answer_id_prefix is not None:
            answer_id = "%s-%d" % (answer_id_prefix, len(records) + 1)

        def resolve_standing_id(value, _base=answer_sequence_base):
            text = str(value)
            if "{sequence}" not in text:
                return text
            match = re.search(r"-(\d+)$", text)
            slot_number = int(match.group(1)) if match else 1
            # The prefix and its base stand tied together on
            # this surface as on the service route: where no
            # base stands supplied, the marker resolves
            # against the batch position itself, the sequence
            # this module surface knows, so the refusal names
            # a resolved identity and never the unresolved
            # marker (entry S17-R3-028).
            base = _base if _base is not None else 1
            return text.replace(
                "{sequence}", str(base + slot_number - 1))

        record = _record_from_body(
            slot_validated, body_text=body, raw_bytes=body_bytes,
            content_hash=hashlib.sha256(body_bytes).hexdigest(),
            standing_records=running_standing, product=product,
            round=round, product_id=product_id, round_id=round_id,
            answer_id=answer_id,
            registry_version_at_import=registry_version_at_import,
            detector_version_at_import=detector_version_at_import,
            standing_id_resolver=resolve_standing_id)
        records.append(record)
        running_standing.append(record)
        if record.get("control_flag"):
            running_controls += 1
    return records


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
    except RecursionError:
        _fail("IMPORT_VALIDATION_FAILED",
              "the file nests deeper than the reader can "
              "hold; save the answer text on its own in a "
              "plain text or Markdown file, then import "
              "that file")
    except TypeError as error:
        _fail("IMPORT_VALIDATION_FAILED",
              "adapter call does not match the contract inputs: "
              + str(error))


def _worksheet_limits_in_force(home):
    """The worksheet count bounds in force for one home.

    Returns (answers bound, queries bound) for limits 22
    and 27 as the home states them, through the journal
    limits in force, or the brief defaults where no home
    stands named or its limits cannot be read (entry
    S17-R2-084).
    """
    answers = WORKSHEET_ANSWERS_LIMIT
    queries = WORKSHEET_QUERIES_LIMIT
    if home is None:
        return answers, queries
    try:
        from citeline import journal
        limits = journal.effective_limits(str(home))
    except Exception:
        return answers, queries
    try:
        answers = int(limits["answers_per_round"]["value"])
        queries = int(limits["queries_per_product"]["value"])
    except Exception:
        return WORKSHEET_ANSWERS_LIMIT, WORKSHEET_QUERIES_LIMIT
    return answers, queries


def build_worksheet_text(*, product=None, round=None, queries=(),
                         engine_labels=(), planned_answers=0,
                         answers_limit=None):
    """The capture worksheet text for one named round.

    One slot stands per planned answer, and each slot carries
    the metadata fields the import format will later require,
    named once in that slot and nowhere else in the worksheet,
    so a slot count can be read from the field names. The
    worksheet states the round label, the query list, and the
    engine labels to attempt. Each slot line states, beside
    each field, the value or form a filled slot carries and
    one example value, drawn from the adapter contract and
    the labelled fixture example in the usage text. The
    operator captures by hand against the worksheet and
    fills the slots; the completed worksheet imports back
    through the import route above.
    """
    if type(planned_answers) is not int or planned_answers < 0:
        _fail("MALFORMED_CALL",
              "planned_answers must stand as a whole non "
              "negative count")
    if answers_limit is None:
        answers_limit = WORKSHEET_ANSWERS_LIMIT
    if planned_answers > answers_limit:
        _fail("LIMIT_EXCEEDED",
              "planned_answers stands past the bound of "
              "limit 22, answers per round, which is "
              + format(answers_limit, ","))
    lines = [
        "Citeline capture worksheet",
        "product: " + _sheet_line_text(product),
        "round: " + _sheet_line_text(round),
        "queries to attempt:",
    ]
    for query in queries:
        lines.append("query: " + _sheet_line_text(query))
    lines.append("engine labels to attempt:")
    for label in engine_labels:
        lines.append("engine: " + _sheet_line_text(label))
    lines.append("slots to fill by hand, one answer per slot:")
    lines.append("| slot | answer text stands below its slot line |")
    for index in range(1, int(planned_answers) + 1):
        lines.append(
            "slot %d: query= (the query this slot answers; "
            "example What is Acme Ledger?) engine_label= "
            "(the label as asserted, up to 200 code points; "
            "example Fixture Engine) kind= (real_sample or "
            "fixture; example fixture) captured_on= (an ISO "
            "date in the form YYYY-MM-DD, a real calendar "
            "date not in the future; example 2026-08-16) "
            "capture_method= (not empty, up to 2,000 code "
            "points; example manual copy)" % index)
    return "\n".join(lines) + "\n"


WORKSHEET_ANSWERS_LIMIT = 10000
WORKSHEET_QUERIES_LIMIT = 1000


def _sheet_line_text(value):
    """One value as worksheet line text.

    Newlines, carriage returns, and control or format
    characters stand replaced by a space, so a value can
    never forge a worksheet line, a slot line, or a second
    product or round line, and no control byte reaches the
    sheet (entry S17-R1X-024).
    """
    text = "" if value is None else str(value)
    out = []
    for char in text:
        if ord(char) < 0x20 or ord(char) == 0x7f or unicodedata.category(
                char) in ("Cc", "Cf", "Zl", "Zp"):
            # The separator categories stand replaced beside
            # the control and format categories: the line
            # separator and the paragraph separator are line
            # breaks to the worksheet parser, so a value
            # carrying one would otherwise write a new sheet
            # line of its own (entry S17-R2-035).
            out.append(" ")
        else:
            out.append(char)
    return "".join(out)


def _validate_worksheet_inputs(*, output_path, queries,
                               engine_labels, planned_answers,
                               answers_limit=None, queries_limit=None):
    """Validate the export inputs in recorded error values.

    The destination must stand stated as one sane path,
    the counts must stand as whole non negative counts
    within the stated bounds, and the lists must stand as
    lists of text. Every refusal here carries a recorded
    token; no raw interpreter exception escapes this seam
    and no file stands written on a refused call.
    """
    if output_path is None or not isinstance(output_path, str) \
            or not output_path.strip():
        _fail("MALFORMED_CALL",
              "the worksheet export names no destination: "
              "an output path stands required")
    if any(ord(char) < 0x20 or ord(char) == 0x7f
           for char in output_path):
        _fail("MALFORMED_CALL",
              "the worksheet destination holds a control "
              "character and names no sane path")
    parts = re.split(r"[\\/]", output_path)
    if ".." in parts:
        _fail("MALFORMED_CALL",
              "the worksheet destination climbs out of its "
              "directory with a parent step; name the "
              "destination directly instead")
    if type(planned_answers) is not int:
        _fail("MALFORMED_CALL",
              "planned_answers must stand as a whole count, "
              "not as a value of type "
              + type(planned_answers).__name__)
    if planned_answers < 0:
        _fail("MALFORMED_CALL",
              "planned_answers must stand as a non negative "
              "count, not a negative one")
    if answers_limit is None:
        answers_limit = WORKSHEET_ANSWERS_LIMIT
    if queries_limit is None:
        queries_limit = WORKSHEET_QUERIES_LIMIT
    if planned_answers > answers_limit:
        _fail("LIMIT_EXCEEDED",
              "planned_answers stands past the bound of "
              "limit 22, answers per round, which is "
              + format(answers_limit, ","))
    if isinstance(queries, (str, bytes)) \
            or not isinstance(queries, (list, tuple)):
        _fail("MALFORMED_CALL",
              "queries must stand as a list of query texts")
    if isinstance(engine_labels, (str, bytes)) \
            or not isinstance(engine_labels, (list, tuple)):
        _fail("MALFORMED_CALL",
              "engine_labels must stand as a list of engine "
              "label texts")
    for value in list(queries) + list(engine_labels):
        if not isinstance(value, str):
            _fail("MALFORMED_CALL",
                  "every query and engine label must stand "
                  "as text, not as a value of type "
                  + type(value).__name__)
    if len(queries) > queries_limit:
        _fail("LIMIT_EXCEEDED",
              "the query list stands past the bound of "
              "limit 27, queries per product, which is "
              + format(queries_limit, ","))
    return output_path


def export_capture_worksheet(*, output_path=None, product=None,
                             round=None, queries=(), engine_labels=(),
                             planned_answers=0, home=None):
    """Write one capture worksheet file from a named round.

    Returns the worksheet text written. This operation
    captures nothing, fetches nothing, and queries nothing.
    The destination stands validated before any write: an
    omitted or unsane destination writes nothing, a
    destination inside the product home stands refused
    where the home is named, an occupied destination
    stands refused as DESTINATION_EXISTS, and any other
    write failure carries DESTINATION_WRITE_FAILED with
    the cause named, never the occupied token (entries
    S17-R1X-023 and S17-R1X-025).
    """
    # The count bounds read the limits in force for the
    # home the sheet is written for, in both directions, as
    # the import side of the same limits reads them (entry
    # S17-R2-084). With no home named, the brief defaults
    # govern, as they governed before this plumbing.
    answers_limit, queries_limit = _worksheet_limits_in_force(home)
    output_text = _validate_worksheet_inputs(
        output_path=output_path, queries=queries,
        engine_labels=engine_labels,
        planned_answers=planned_answers,
        answers_limit=answers_limit, queries_limit=queries_limit)
    if home is not None:
        # The destination stands judged on its resolved
        # path: a symbolic link in a parent component that
        # lands inside the home stands inside the home
        # (entry S17-R2-039).
        home_abs = os.path.realpath(str(home))
        target_abs = os.path.realpath(output_text)
        if target_abs == home_abs or target_abs.startswith(
                home_abs + os.sep):
            _fail("MALFORMED_CALL",
                  "the worksheet destination stands inside "
                  "the product home; name a destination "
                  "outside the home")
    if os.path.isdir(output_text):
        _fail("MALFORMED_CALL",
              "the worksheet destination names a directory, "
              "not a file")
    text = build_worksheet_text(
        product=product, round=round, queries=queries,
        engine_labels=engine_labels, planned_answers=planned_answers,
        answers_limit=answers_limit)
    if os.path.lexists(output_text):
        _fail("DESTINATION_EXISTS",
              "the worksheet output path stands occupied and "
              "stands never replaced: " + output_text)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(output_text, flags, 0o666)
    except FileExistsError:
        _fail("DESTINATION_EXISTS",
              "the worksheet output path stands occupied and "
              "stands never replaced: " + output_text)
    except OSError as error:
        _fail("DESTINATION_WRITE_FAILED",
              "the worksheet write failed at its destination: "
              + str(error))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
    except OSError as error:
        _fail("DESTINATION_WRITE_FAILED",
              "the worksheet write failed at its destination: "
              + str(error))
    return text
