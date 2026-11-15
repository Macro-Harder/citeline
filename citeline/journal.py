"""Slice S0: the journal and the store foundation.

The journal is one append only file, one canonical JSON
entry per line, each line terminated by one newline. This
module owns the entry form and its hash chain, the fold,
the home, the limits plumbing over the 42 brief limits as
a shared guard, the config surface, and the concurrency
exclusion. It holds no check, detection, or metric rule.

Dates here are call inputs, never clock reads. Nothing in
this module reads a clock for a record value.
"""

import base64
import copy
import fcntl
import hashlib
import json
import math
import os
import re
import threading
from decimal import Decimal, InvalidOperation

from citeline.errors import ConfigError, JournalError

__all__ = [
    "ConfigError",
    "ENTRY_KINDS",
    "JournalError",
    "append_cost",
    "append_entries_atomic",
    "append_entry",
    "recover_interrupted_batch",
    "canonical_bytes",
    "config_keys",
    "config_path",
    "effective_limits",
    "entry_hash",
    "fold",
    "fold_registry",
    "journal_path",
    "limit_for_member",
    "parse_config",
    "parse_entry",
    "read_entry",
    "replay",
    "start_run",
    "status_snapshot",
    "verify_chain",
    "write_config",
]

ENTRY_KINDS = (
    "product_registered",
    "registry_change",
    "round_named",
    "snapshot_registered",
    "audit_record",
    "answer_imported",
    "guide_record",
    "limit_raise",
    "failure_record",
    "correction",
)

FORM_VERSION = 1
JOURNAL_FILENAME = "journal.jsonl"
CONFIG_FILENAME = "config.txt"
LOCK_FILENAME = ".citeline-write.lock"
MAX_DEPTH = 100

# The 42 brief limits, in the plan Section 5.11 order, as
# (key, brief default value in the row unit, row unit).
_LIMIT_TABLE = [
    ("page_file_size", 2, "MiB"),
    ("answer_file_size", 1, "MiB"),
    ("extracted_text_length_per_page_or_answer", 500000, "characters"),
    ("element_or_tag_events_per_page", 100000, "count"),
    ("nesting_depth", 100, "levels"),
    ("attributes_per_element", 100, "count"),
    ("attribute_value_length", 10000, "characters"),
    ("link_count_per_page", 10000, "count"),
    ("heading_count_per_page", 10000, "count"),
    ("reference_definitions_per_file", 10000, "count"),
    ("front_matter_block_size", 16, "KiB"),
    ("front_matter_key_count", 100, "count"),
    ("front_matter_anchor_count", 20, "count"),
    ("front_matter_alias_use_count", 100, "count"),
    ("front_matter_nesting_depth_of_anchored_values", 10, "levels"),
    ("front_matter_size_after_alias_expansion", 64, "KiB"),
    ("front_matter_value_length_per_key", 4096, "characters"),
    ("json_nesting_depth", 100, "levels"),
    ("evidence_excerpt_length", 120, "characters"),
    ("evidence_spans_per_check", 20, "count"),
    ("evidence_spans_per_report", 200, "count"),
    ("answers_per_round", 10000, "count"),
    ("products_per_home", 1000, "count"),
    ("competitors_per_product", 100, "count"),
    ("aliases_per_product", 100, "count"),
    ("aliases_per_competitor", 100, "count"),
    ("queries_per_product", 1000, "count"),
    ("product_name_length", 200, "code points"),
    ("engine_label_length", 200, "code points"),
    ("round_label_length", 200, "code points"),
    ("capture_method_text_length", 2000, "code points"),
    ("query_text_length", 2000, "code points"),
    ("error_message_length", 500, "characters"),
    ("robots_file_total_size", 512, "KiB"),
    ("robots_line_length", 10000, "characters"),
    ("robots_group_count", 1000, "count"),
    ("robots_rules_per_group", 10000, "count"),
    ("robots_path_argument_length", 2000, "characters"),
    ("journal_length", 100000, "entries"),
    ("total_home_size", 1, "GiB"),
    ("per_run_wall_clock_backstop", 120, "seconds"),
    ("per_file_parse_time", 30, "seconds"),
]

LIMIT_KEYS = [row[0] for row in _LIMIT_TABLE]
_LIMIT_DEFAULT = {row[0]: row[1] for row in _LIMIT_TABLE}
_LIMIT_UNIT = {row[0]: row[2] for row in _LIMIT_TABLE}
_LIMIT_INDEX = {row[0]: index + 1 for index, row in enumerate(_LIMIT_TABLE)}

_SIZE_MULTIPLIERS = {"MiB": 1024 ** 2, "KiB": 1024, "GiB": 1024 ** 3}

# Canonical number scales, by leaf member name, on decision
# D-KF-14-NUM: earned at 3 decimal places, the score value
# at 1, and rates, interval bounds, and shares at 6.
_SCALE_BY_KEY = {
    "earned": 3,
    "score": 1,
    "value": 1,
    "rate": 6,
    "wilson_low": 6,
    "wilson_high": 6,
}


def _scale_for(key):
    if key is None:
        return None
    if key in _SCALE_BY_KEY:
        return _SCALE_BY_KEY[key]
    if key.endswith("_share") or key.endswith("_rate"):
        return 6
    if key.endswith("_low") or key.endswith("_high"):
        return 6
    return None


class ParsedNumber(float):
    """A number carried with the exact lexeme it was read in.

    Parsing keeps the stated lexeme beside the float value,
    so no step carries a hashed value through a container
    in which 1, 1.0, and true would collapse, and the
    renderer can render at the scale the lexeme and the
    member name together state.
    """

    def __new__(cls, lexeme):
        obj = float.__new__(cls, float(lexeme))
        obj.lexeme = lexeme
        return obj

    def __repr__(self):
        return self.lexeme


class _DuplicateKey(Exception):
    pass


class _LineInvalid(Exception):
    pass


def _pairs_hook(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise _DuplicateKey(key)
        seen[key] = value
    return seen


def _bad_constant(name):
    raise _LineInvalid(name)


def _parse_line(raw):
    """Parse one stored line, or return None where it does not parse."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_hook,
            parse_float=ParsedNumber,
            parse_constant=_bad_constant,
        )
    except (ValueError, _DuplicateKey, _LineInvalid, RecursionError):
        return None


_SHORT_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def _render_string(value):
    parts = ['"']
    for char in value:
        if 0xD800 <= ord(char) <= 0xDFFF:
            raise JournalError(
                "a lone surrogate cannot stand in hashed material")
        escaped = _SHORT_ESCAPES.get(char)
        if escaped is not None:
            parts.append(escaped)
        elif ord(char) < 0x20:
            parts.append("\\u%04x" % ord(char))
        else:
            parts.append(char)
    parts.append('"')
    return "".join(parts)


def _quantize(value, scale):
    quantum = Decimal(1).scaleb(-scale)
    try:
        result = value.quantize(quantum)
    except InvalidOperation:
        raise JournalError("number outside the renderable range")
    if result == 0:
        result = abs(result)
    return format(result, "f")


def _integral_float_form(value):
    text = format(value.to_integral_value(), "f")
    if value == 0 and text.startswith("-"):
        text = text[1:]
    return text + ".0"


def _render_decimal(value, key):
    scale = _scale_for(key)
    if scale is not None:
        return _quantize(value, scale)
    if value != value.to_integral_value():
        raise JournalError(
            "a non integer value whose member defines no scale "
            "cannot stand in hashed material")
    return _integral_float_form(value)


def _render_parsed(number, key):
    try:
        value = Decimal(number.lexeme)
    except InvalidOperation:
        raise JournalError("number outside the renderable range")
    if not value.is_finite():
        raise JournalError("number outside the renderable range")
    if abs(value.adjusted()) > 10000:
        raise JournalError("number outside the renderable range")
    scale = _scale_for(key)
    if scale is not None:
        return _quantize(value, scale)
    if value != value.to_integral_value():
        raise JournalError(
            "a non integer value whose member defines no scale "
            "cannot stand in hashed material")
    return _integral_float_form(value)


def _render_float(value, key):
    if math.isnan(value) or math.isinf(value):
        raise JournalError("a non finite number cannot stand in hashed material")
    return _render_decimal(Decimal(str(value)), key)


def _render(value, key=None):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _render_string(value)
    if isinstance(value, ParsedNumber):
        return _render_parsed(value, key)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        scale = _scale_for(key)
        if scale is not None:
            return _quantize(Decimal(int(value)), scale)
        try:
            return str(int(value))
        except ValueError:
            raise JournalError("number outside the renderable range")
    if isinstance(value, float):
        return _render_float(value, key)
    if isinstance(value, Decimal):
        return _render_decimal(value, key)
    if isinstance(value, dict):
        members = []
        for name in sorted(value.keys()):
            if not isinstance(name, str):
                raise JournalError("an object key in hashed material must be a string")
            members.append(_render_string(name) + ":" + _render(value[name], name))
        return "{" + ",".join(members) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_render(item) for item in value) + "]"
    raise JournalError("a value of this type cannot stand in hashed material")


def canonical_bytes(entry):
    """Render an entry in the canonical form entry 14 fixes.

    Keys order by Unicode code point at every nesting
    level, the separators carry no space, escaping is
    minimal, the encoding is UTF-8, and the entry_hash
    field stands outside its own representation.
    """
    if not isinstance(entry, dict):
        raise JournalError("an entry must be an object")
    body = {name: value for name, value in entry.items()
            if name != "entry_hash"}
    try:
        return _render(body).encode("utf-8")
    except UnicodeEncodeError:
        raise JournalError(
            "a value that cannot encode as UTF-8 cannot stand "
            "in hashed material")


def entry_hash(entry):
    """The SHA-256 digest of the canonical bytes, in lowercase hex."""
    return hashlib.sha256(canonical_bytes(entry)).hexdigest()


def parse_entry(data):
    """Parse one stored line into an entry, with its hash stated."""
    if isinstance(data, str):
        raw = data.encode("utf-8")
    else:
        raw = bytes(data)
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    parsed = _parse_line(raw)
    if parsed is None or not isinstance(parsed, dict):
        raise JournalError(
            "the line does not parse as one entry",
            row="I-2", token="JOURNAL_VERIFY_FAILED")
    entry = dict(parsed)
    entry["entry_hash"] = entry_hash(entry)
    return entry


def _container_depth(value):
    """The nesting depth of a value, counted iteratively.

    The count walks an explicit stack and stops as soon as
    the depth passes MAX_DEPTH, so a hostile depth is
    judged by this test instead of exhausting the
    interpreter stack inside it (Step 17 entry S17-R1-002).
    """
    depth = 0
    stack = [(value, 1)]
    while stack:
        item, level = stack.pop()
        if isinstance(item, dict):
            if level > depth:
                depth = level
            if depth > MAX_DEPTH:
                return depth
            for child in item.values():
                stack.append((child, level + 1))
        elif isinstance(item, (list, tuple)):
            if level > depth:
                depth = level
            if depth > MAX_DEPTH:
                return depth
            for child in item:
                stack.append((child, level + 1))
    return depth


def journal_path(home):
    """The journal file path: journal.jsonl directly inside the home."""
    return os.path.join(str(home), JOURNAL_FILENAME)


def config_path(home):
    """The config file path: config.txt directly inside the home."""
    return os.path.join(str(home), CONFIG_FILENAME)


def _lock_path(home):
    return os.path.join(str(home), LOCK_FILENAME)


class _Scan:
    __slots__ = ("lines", "parsed", "failure", "verified",
                 "head_hash", "entry_count", "partial_ignored")

    def __init__(self):
        self.lines = []
        self.parsed = []
        self.failure = None
        self.verified = 0
        self.head_hash = None
        self.entry_count = 0
        self.partial_ignored = False


_scan_cache = {}


def _stat_key(path):
    try:
        info = os.stat(path)
    except OSError:
        return None
    # The change time stands in the key beside the inode,
    # the size, and the modification time: a same size edit
    # can restore its modification time, and no ordinary
    # call restores the change time, so a tampered file
    # never reproduces the key of the scan it would be
    # served from (Step 17 entry S17-R1-001).
    return (info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns)


def _lock_held_by_other(home):
    """Probe the write lock without taking it, as a liveness test only."""
    path = _lock_path(home)
    try:
        handle = open(path, "a+")
    except OSError:
        return False
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        except OSError:
            return False
        fcntl.flock(handle, fcntl.LOCK_UN)
        return False
    finally:
        handle.close()


def _has_partial_tail(path):
    try:
        with open(path, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                return False
            handle.seek(-1, os.SEEK_END)
            return handle.read(1) != b"\n"
    except OSError:
        return False


def _partial_tail_bytes(path):
    """The bytes after the last newline, or None where the
    file ends with a newline or cannot be read."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    if not data or data.endswith(b"\n"):
        return None
    return data.split(b"\n")[-1]


def _is_plausible_entry_prefix(partial):
    """Whether partial bytes could be the standing holder
    own entry, written in part.

    Brief Section 5.12 item 138 admits a final partial line
    as a live holder append in progress only where it is
    the holder own partial write. Bytes that do not decode
    as UTF-8, or whose bracket and string structure no
    canonical entry prefix can have, are no entry prefix,
    whoever holds the lock (Step 17 entry S17-R1-007).
    """
    if not partial:
        return False
    try:
        text = partial.decode("utf-8")
    except UnicodeDecodeError:
        return False
    # Every canonical entry opens with an object brace and
    # a quoted key, and the canonical rendering carries no
    # space and no character outside a string except the
    # structural characters, the number characters, and the
    # letters of the three literal values. Text standing
    # outside that form anywhere is no prefix of any
    # canonical entry, so the test does not pass vacuously
    # over plain words or digits (Step 17 round 2 entry
    # S17-R2-003).
    if not text.startswith("{"):
        return False
    if len(text) > 1 and text[1] != '"':
        return False
    # The admitted characters must also stand in an order a
    # canonical token can stand in, token by token and
    # between tokens alike: a number carries at most one
    # decimal point, one exponent, signs only where the
    # number grammar places them, and no leading zero; a
    # literal value stands only as a prefix of true, false,
    # or null, complete before any delimiter closes it; a
    # colon stands only between a key and its value, a
    # comma only between two members or two elements, and
    # no second value starts directly after a completed
    # value with no delimiter at all. The test therefore
    # tracks the container frame each token stands in and
    # the place the frame stands at, not the shape of one
    # token alone. Brace led text in any other shape is no
    # entry prefix, whoever holds the lock (Step 17 round 3
    # entry S17-R3-006, reopened at round 4 entry
    # S17-R4-001).
    stack = []
    root_done = False
    in_string = False
    string_is_key = False
    token = None
    number_state = None
    literal_word = None
    literal_target = None

    def complete_value():
        nonlocal root_done
        if not stack:
            root_done = True
        else:
            stack[-1][1] = "sep"

    index = 0
    while index < len(text):
        char = text[index]
        if root_done:
            return False
        if in_string:
            if char == "\\":
                if index + 1 >= len(text):
                    break
                following = text[index + 1]
                if following in '"\\/bfnrt':
                    index += 2
                    continue
                if following == "u":
                    digits = text[index + 2:index + 6]
                    if any(c not in "0123456789abcdefABCDEF"
                           for c in digits):
                        return False
                    index += 2 + len(digits)
                    if len(digits) < 4:
                        break
                    continue
                return False
            if char == '"':
                in_string = False
                if string_is_key:
                    stack[-1][1] = "colon"
                else:
                    complete_value()
                index += 1
                continue
            if ord(char) < 0x20:
                return False
            index += 1
            continue
        if token == "literal":
            if char.isalpha():
                literal_word += char
                if not literal_target.startswith(literal_word):
                    return False
                index += 1
                continue
            if literal_word != literal_target:
                return False
            token = None
            literal_word = None
            literal_target = None
            complete_value()
        elif token == "number":
            if char.isdigit():
                if number_state == "minus":
                    number_state = "int_zero" if char == "0" \
                        else "int"
                elif number_state == "int_zero":
                    return False
                elif number_state == "frac_start":
                    number_state = "frac"
                elif number_state in ("exp_start", "exp_sign"):
                    number_state = "exp"
                index += 1
                continue
            if char == "." and number_state in ("int", "int_zero"):
                number_state = "frac_start"
                index += 1
                continue
            if char in "eE" and number_state in (
                    "int", "int_zero", "frac"):
                number_state = "exp_start"
                index += 1
                continue
            if char in "+-" and number_state == "exp_start":
                number_state = "exp_sign"
                index += 1
                continue
            if number_state in ("minus", "frac_start",
                                "exp_start", "exp_sign"):
                return False
            if char not in ",}]":
                return False
            token = None
            number_state = None
            complete_value()
        if not stack:
            if char == "{":
                stack.append(["object", "key", True])
                index += 1
                continue
            return False
        frame = stack[-1]
        if frame[0] == "object":
            if frame[1] == "key":
                if char == '"':
                    in_string = True
                    string_is_key = True
                    index += 1
                    continue
                if char == "}" and frame[2]:
                    stack.pop()
                    complete_value()
                    index += 1
                    continue
                return False
            if frame[1] == "colon":
                if char == ":":
                    frame[1] = "value"
                    index += 1
                    continue
                return False
            if frame[1] == "sep":
                if char == ",":
                    frame[1] = "key"
                    frame[2] = False
                    index += 1
                    continue
                if char == "}":
                    stack.pop()
                    complete_value()
                    index += 1
                    continue
                return False
        else:
            if frame[1] == "sep":
                if char == ",":
                    frame[1] = "value"
                    frame[2] = False
                    index += 1
                    continue
                if char == "]":
                    stack.pop()
                    complete_value()
                    index += 1
                    continue
                return False
            if frame[1] == "value" and char == "]" and frame[2]:
                stack.pop()
                complete_value()
                index += 1
                continue
        if char == '"':
            in_string = True
            string_is_key = False
        elif char == "{":
            stack.append(["object", "key", True])
        elif char == "[":
            stack.append(["array", "value", True])
        elif char == "-":
            token = "number"
            number_state = "minus"
        elif char.isdigit():
            token = "number"
            number_state = "int_zero" if char == "0" else "int"
        elif char in "tfn":
            token = "literal"
            literal_word = char
            literal_target = {"t": "true", "f": "false",
                              "n": "null"}[char]
        else:
            return False
        index += 1
    return True


def _raise_value_in_range(payload):
    """Whether a limit_raise payload carries a raise the
    append path could have written.

    The append path checks the limit member, the value
    type, and the value range at row X-1. A supplied chain
    is judged by the same checks at scan and at replay, so
    a chain the append path could never write does not
    verify and its raise does not stand in force (Step 17
    round 2 entry S17-R2-002).
    """
    key = _member_to_key(payload.get("limit"))
    if key is None:
        return False
    raised = payload.get("raised_value")
    if type(raised) is not int:
        return False
    index = _LIMIT_INDEX[key]
    ceiling = _LIMIT_DEFAULT[key] * 10 if index <= 40 \
        else _LIMIT_DEFAULT[key]
    return 1 <= raised <= ceiling


def _correction_form_ok(payload, position=None, target_kind=None):
    """Whether a correction payload carries the form the
    append path requires: a whole number supersedes value
    and a corrected record that is a record. Where the
    correction own position in the chain stands known, at
    scan and at replay, the supersedes value must also
    name an entry standing at or before the correction
    itself, the range the append path judges at row U-8,
    and the entry it names must stand in a kind the append
    path accepts as a target: a correction of a correction
    stands refused at row U-8, on the ground recorded at
    entry S17-R1X-028, so a supplied chain carrying one
    does not verify and does not replay. A correction
    superseding its own sequence stands inside that range
    and outside that refusal, so the standing vector V-10
    keeps its governed form (Step 17 round 2 entry
    S17-R2-002, reopened at round 3 entry S17-R3-007 and
    at round 4 entry S17-R4-005)."""
    supersedes = payload.get("supersedes_sequence")
    if type(supersedes) is not int:
        return False
    if position is not None and not 1 <= supersedes <= position:
        return False
    if target_kind == "correction" and supersedes != position:
        return False
    return isinstance(payload.get("corrected_record"), dict)


def _special_payload_reason(parsed, position=None, chain=None):
    """The scan reason a special payload form fails, or None."""
    kind = parsed.get("entry_kind")
    payload = parsed.get("payload") or {}
    if kind == "limit_raise" and not _raise_value_in_range(payload):
        return "raise_value"
    if kind == "correction":
        target_kind = None
        supersedes = payload.get("supersedes_sequence")
        if chain is not None and type(supersedes) is int \
                and 1 <= supersedes <= len(chain):
            target = chain[supersedes - 1]
            if isinstance(target, dict):
                target_kind = target.get("entry_kind")
        if not _correction_form_ok(payload, position, target_kind):
            return "correction_form"
    return None


def _scan(home, partial_mode="probe"):
    """Read the journal as it stands and recompute its chain.

    partial_mode "probe" classifies a final partial line on
    the provenance test: it counts as a standing holder
    append in progress only where a live holder holds the
    write lock, and any other final partial line is a torn
    tail. partial_mode "torn" classifies any final partial
    line as a torn tail, for a caller that has just taken
    the lock itself and so holds no other holder pending.
    """
    home = str(home)
    path = journal_path(home)
    stat = _stat_key(path)
    lock_key = None
    plausible_key = None
    if partial_mode == "probe" and _has_partial_tail(path):
        lock_key = _lock_held_by_other(home)
        plausible_key = _is_plausible_entry_prefix(
            _partial_tail_bytes(path))
    cache_key = (path, partial_mode, lock_key, plausible_key)
    cached = _scan_cache.get(cache_key)
    if cached is not None and cached[0] == stat:
        return cached[1]
    scan = _Scan()
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except FileNotFoundError:
        data = b""
    except OSError:
        # A journal path that stands but cannot be read as
        # a file (a directory at the path, a read error) is
        # an integrity state, not an empty journal (Step 17
        # entry S17-R1-006).
        scan.failure = {"position": 1, "reason": "unreadable",
                        "row": "I-2"}
        _scan_cache[cache_key] = (stat, scan)
        return scan
    partial = None
    if data:
        if data.endswith(b"\n"):
            body = data[:-1]
            scan.lines = body.split(b"\n") if body else [b""]
            if data == b"\n":
                scan.lines = [b""]
        else:
            segments = data.split(b"\n")
            scan.lines = segments[:-1]
            partial = segments[-1]
    scan.entry_count = len(scan.lines)
    scan.parsed = [_parse_line(raw) for raw in scan.lines]
    seen_raises = []
    if partial is not None:
        if partial_mode == "probe" and _lock_held_by_other(home) \
                and _is_plausible_entry_prefix(partial):
            scan.partial_ignored = True
        elif partial_mode == "ignore":
            scan.partial_ignored = True
    previous_raw = None
    for index, raw in enumerate(scan.lines, start=1):
        parsed = scan.parsed[index - 1]
        reason = None
        if parsed is None or not isinstance(parsed, dict):
            reason = "parse"
        else:
            form_version = parsed.get("form_version")
            if type(form_version) is not int or form_version != FORM_VERSION:
                reason = "form_version"
            elif _container_depth(parsed) > MAX_DEPTH:
                reason = "depth"
            elif parsed.get("entry_kind") not in ENTRY_KINDS:
                reason = "entry_kind"
            elif not isinstance(parsed.get("payload"), dict):
                reason = "payload"
            elif type(parsed.get("sequence")) is not int \
                    or parsed.get("sequence") != index:
                reason = "sequence"
            elif index == 1 and parsed.get("previous_hash") is not None:
                reason = "genesis"
            elif index > 1 and parsed.get("previous_hash") != \
                    hashlib.sha256(previous_raw).hexdigest():
                reason = "link"
            else:
                try:
                    rendered = canonical_bytes(parsed)
                except (JournalError, ValueError, ArithmeticError):
                    reason = "render"
                else:
                    if rendered != raw:
                        reason = "noncanonical"
                    elif _special_payload_reason(
                            parsed, index, scan.parsed) is not None:
                        reason = _special_payload_reason(
                            parsed, index, scan.parsed)
                    elif parsed.get("entry_kind") == "limit_raise":
                        # The one raise per run and limit rule
                        # is a property of the chain, not of
                        # one writing route: a supplied chain
                        # carrying two raises for one run and
                        # limit does not verify (Step 17 entry
                        # S17-R1X-010). The raise key stands
                        # judged by equality, as the append
                        # path and effective_limits judge it,
                        # so numeric spellings of one value
                        # stand as one raise (Step 17 round 3
                        # entry S17-R3-005).
                        payload = parsed.get("payload") or {}
                        raise_key = (payload.get("run_id"),
                                     payload.get("limit"))
                        if any(raise_key == seen
                               for seen in seen_raises):
                            reason = "duplicate_raise"
                        else:
                            seen_raises.append(raise_key)
        if reason is not None:
            scan.failure = {"position": index, "reason": reason,
                            "row": "I-2"}
            break
        scan.verified = index
        scan.head_hash = hashlib.sha256(raw).hexdigest()
        previous_raw = raw
    if scan.failure is None and partial is not None \
            and not scan.partial_ignored:
        scan.failure = {"position": len(scan.lines) + 1,
                        "reason": "torn_tail", "row": "I-2"}
    _scan_cache[cache_key] = (stat, scan)
    return scan


def _entries_with_hash(scan):
    entries = []
    for parsed in scan.parsed:
        if isinstance(parsed, dict):
            # The whole entry stands copied out of the scan
            # cache, every member it carries and not the
            # payload only, so a caller mutation of a fold
            # result cannot write back into what later reads
            # in this process return (Step 17 round 3 entry
            # S17-R3-008, reopened at round 4 entry
            # S17-R4-006).
            entry = copy.deepcopy(parsed)
            try:
                entry["entry_hash"] = entry_hash(entry)
            except (JournalError, ValueError, ArithmeticError):
                entry["entry_hash"] = None
            entries.append(entry)
    return entries


def verify_chain(home):
    """Recompute the chain over the journal as it stands.

    This is the journal limb of the verify operation. The
    service home wraps it as its verify result. The claim
    is internal consistency only: the checks on the head
    itself are the anchor and the operator recording.
    """
    scan = _scan(home, "probe")
    passed = scan.failure is None
    return {
        "passed": passed,
        "chain_fails": not passed,
        "entry_count": scan.entry_count,
        "head_hash": scan.head_hash,
        "claim": "internal consistency only",
        "exit_code": 0 if passed else 5,
        "error_value": None if passed else 5,
        "row": None if passed else "I-2",
        "token": None if passed else "JOURNAL_VERIFY_FAILED",
        "failing_sequence": None if passed else scan.failure["position"],
    }


def _home_size(home):
    total = 0
    for root, _dirs, files in os.walk(str(home)):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def _resolve_anchor_path(home, value):
    """Resolve an anchor_path value once, against the home.

    Config validation and every anchor read and write use
    this one resolved path, so the anchor the product uses
    is the anchor it checked (Step 17 entry S17-R1X-003).
    """
    if os.path.isabs(value):
        return os.path.normpath(value)
    return os.path.normpath(os.path.join(str(home), value))


def _read_anchor(path):
    """Read one anchor recording, strictly.

    Returns a pair of a state and a recording. The state
    is "ok" only where the file holds exactly the pair the
    product own writer writes: one 64 character hex head
    hash and one integer sequence. An absent, emptied, or
    directory replaced anchor reports "absent"; a standing
    file in any other form (an undecodable byte, a missing
    or non integer sequence, trailing extra tokens)
    reports "malformed", and no part of it is silently
    dropped (Step 17 entries S17-R1X-001, S17-R1X-002, and
    S17-R1-073).
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except FileNotFoundError:
        return "absent", None
    except IsADirectoryError:
        return "absent", None
    except OSError:
        return "malformed", None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return "malformed", None
    parts = text.split()
    if not parts:
        return "absent", None
    if len(parts) != 2:
        return "malformed", {"head_hash": parts[0], "sequence": None}
    head_hash, sequence_token = parts
    if re.fullmatch(r"[0-9a-fA-F]{64}", head_hash) is None:
        return "malformed", {"head_hash": head_hash, "sequence": None}
    # The writer writes the sequence in plain decimal form:
    # no sign, no leading zero padding, and a length far
    # inside the integer conversion limit. A token in any
    # other form reads as malformed here, and its length is
    # judged before any conversion, so an over long token
    # never reaches the conversion as a raw error (Step 17
    # round 2 entry S17-R2-004).
    if re.fullmatch(r"0|[1-9][0-9]*", sequence_token) is None \
            or len(sequence_token) > 18:
        return "malformed", {"head_hash": head_hash, "sequence": None}
    try:
        sequence = int(sequence_token)
    except ValueError:
        return "malformed", {"head_hash": head_hash, "sequence": None}
    return "ok", {"head_hash": head_hash,
                  "sequence": sequence}


def _agreement_for(recorded, scan):
    """Classify one anchor recording against the standing chain.

    The recording is the pair of its head hash and its
    sequence. The head stands at the chain position its
    hash recomputes to, and the recording stands in a
    position only where its sequence is that position:
    the standing head is matching, an earlier position
    is stale, and every other recording is divergent.
    """
    position = None
    for index, raw in enumerate(scan.lines, start=1):
        if hashlib.sha256(raw).hexdigest() == recorded["head_hash"]:
            position = index
            break
    if position is None:
        return "divergent"
    if recorded["sequence"] != position:
        return "divergent"
    if position == scan.entry_count:
        return "matching"
    return "stale"


def _anchor_status(home, scan):
    values, _warnings, _present = _read_config_values(home)
    anchor_path = values.get("anchor_path")
    if not anchor_path:
        return {"agreement": "not recorded", "recorded_head": None,
                "recorded_sequence": None, "anchor_path": None}
    state, recorded = _read_anchor(
        _resolve_anchor_path(home, anchor_path))
    if state == "absent":
        return {"agreement": "absent", "recorded_head": None,
                "recorded_sequence": None, "anchor_path": anchor_path}
    if state == "malformed":
        return {"agreement": "divergent",
                "recorded_head": recorded["head_hash"] if recorded
                else None,
                "recorded_sequence": None,
                "anchor_path": anchor_path}
    return {
        "agreement": _agreement_for(recorded, scan),
        "recorded_head": recorded["head_hash"],
        "recorded_sequence": recorded["sequence"],
        "anchor_path": anchor_path,
    }


def status_snapshot(home):
    """The journal limb of the status operation.

    Status runs and reports over a journal that does not
    recompute, printing the head of the last entry whose
    link recomputes, or the distinct absence forms, and it
    returns 0 in every case. The service home wraps this
    snapshot as its status result.

    The warnings the home config parse formed stand in the
    snapshot as config_warnings, in the parse form (an
    unknown key warning names its key), so a warning the
    parse computes reaches the routes built on this
    snapshot instead of standing discarded at this reader.
    """
    home = str(home)
    scan = _scan(home, "probe")
    limits = effective_limits(home)
    _values, config_warnings, _present = _read_config_values(home)
    size = _home_size(home)
    length_remaining = limits["journal_length"]["value"] - scan.entry_count
    size_cap = limits["total_home_size"]["value"] * _SIZE_MULTIPLIERS[
        limits["total_home_size"]["unit"]]
    size_remaining = size_cap - size
    if scan.entry_count == 0 and scan.failure is None:
        head = "no entries"
        head_hash = None
    elif scan.failure is not None and scan.verified == 0:
        head = ("no head: the journal does not recompute from its "
                "first entry")
        head_hash = None
    else:
        head_hash = scan.head_hash
        head = scan.head_hash
    return {
        "head": head,
        "head_hash": head_hash,
        "entry_count": scan.entry_count,
        "home_path": home,
        "home_size": size,
        "capacity_outlook": {
            "journal_length_remaining": length_remaining,
            "total_home_size_remaining": size_remaining,
            "entries_remaining": length_remaining,
            "bytes_remaining": size_remaining,
        },
        "anchor": _anchor_status(home, scan),
        "config_warnings": list(config_warnings),
        "chain_fails": scan.failure is not None,
        "exit_code": 0,
    }


def config_keys():
    """The 44 config key strings, in the plan table order."""
    return list(LIMIT_KEYS) + ["home_path", "anchor_path"]


def _member_to_key(member):
    if not isinstance(member, str):
        return None
    match = re.fullmatch(r"limit_([0-9]+)", member)
    if match is None:
        return None
    number = int(match.group(1))
    if number < 1 or number > len(_LIMIT_TABLE):
        return None
    return LIMIT_KEYS[number - 1]


def limit_for_member(member):
    """Name the limit key a limit member of the form limit_N names."""
    key = _member_to_key(member)
    if key is None:
        raise ConfigError(
            "the limit member %r names no limit: rows 43 and 44 are "
            "not limits and take no limit_N form" % (member,),
            row="X-1", token="CONFIG_INVALID")
    return key


def parse_config(text, home=None):
    """Parse config text in the stated flat syntax.

    The syntax is one key, one space, an equals sign, one
    space, and the value, per line. A blank line is ignored
    and a line whose first character is the hash character
    is a comment and is ignored. No inline comment form
    exists. An unknown key is a warning, not a failure.
    Returns a pair of the values found and the warnings.
    """
    values = {}
    warnings = []
    seen = set()
    if text.startswith("\ufeff"):
        # A byte order mark at the head is an encoding
        # prefix, not part of the first key: the page and
        # robots intakes strip it by stated rule, and the
        # config intake does the same (Step 17 entry
        # S17-R1-076).
        text = text[1:]
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    for line in lines:
        if line == "":
            continue
        if line.startswith("#"):
            continue
        if line != line.strip() or "\t" in line or "\r" in line:
            raise ConfigError(
                "a config line stands outside the stated syntax: %r"
                % (line,), row="X-1", token="CONFIG_INVALID")
        parts = line.split(" = ")
        if len(parts) != 2 or not parts[0] or not parts[1] \
                or " " in parts[0] or "=" in parts[0]:
            raise ConfigError(
                "a config line stands outside the stated syntax: %r"
                % (line,), row="X-1", token="CONFIG_INVALID")
        key, raw_value = parts
        if key in seen:
            raise ConfigError(
                "a duplicate config key: %s" % (key,),
                row="X-1", token="CONFIG_INVALID")
        seen.add(key)
        if key in _LIMIT_DEFAULT:
            if re.fullmatch(r"[0-9]+", raw_value) is None:
                raise ConfigError(
                    "a value of the wrong form for its key: %s"
                    % (key,), row="X-1", token="CONFIG_INVALID")
            try:
                number = int(raw_value)
            except ValueError:
                # A digit string past the integer conversion
                # limit is a value far past its hard ceiling,
                # refused in the vocabulary, never a raw
                # error (Step 17 entry S17-R1X-012).
                raise ConfigError(
                    "a config value past its hard ceiling: %s"
                    % (key,), row="X-1", token="CONFIG_INVALID")
            index = _LIMIT_INDEX[key]
            default = _LIMIT_DEFAULT[key]
            if number < 1:
                raise ConfigError(
                    "a config value below the minimum of 1: %s"
                    % (key,), row="X-1", token="CONFIG_INVALID")
            ceiling = default * 10 if index <= 40 else default
            if number > ceiling:
                raise ConfigError(
                    "a config value past its hard ceiling: %s"
                    % (key,), row="X-1", token="CONFIG_INVALID")
            values[key] = number
        elif key in ("home_path", "anchor_path"):
            values[key] = raw_value
            if key == "home_path":
                # The home is fixed by the call that names
                # it; this key governs nothing, and the parse
                # says so instead of accepting it silently
                # (Step 17 entry S17-R1X-014).
                warnings.append(
                    "home_path has no effect: the home is the "
                    "directory the call names")
        else:
            warnings.append("unknown key: %s" % (key,))
    resolved = dict(_LIMIT_DEFAULT)
    for name, number in values.items():
        if name in resolved:
            resolved[name] = number
    if resolved["front_matter_size_after_alias_expansion"] \
            < resolved["front_matter_block_size"]:
        raise ConfigError(
            "front_matter_size_after_alias_expansion stands below "
            "front_matter_block_size",
            row="X-1", token="CONFIG_INVALID")
    if resolved["evidence_spans_per_report"] \
            < resolved["evidence_spans_per_check"]:
        raise ConfigError(
            "evidence_spans_per_report stands below "
            "evidence_spans_per_check",
            row="X-1", token="CONFIG_INVALID")
    if home is not None and "anchor_path" in values:
        candidate = _resolve_anchor_path(home, values["anchor_path"])
        # The check runs on the real location, not the
        # lexical spelling: a path through a symlinked
        # directory whose real location is inside the home
        # is inside the home (Step 17 entry S17-R1X-004).
        candidate_real = os.path.realpath(candidate)
        home_real = os.path.realpath(str(home))
        if candidate_real == home_real \
                or candidate_real.startswith(home_real + os.sep):
            raise ConfigError(
                "an anchor path inside the product home is refused",
                row="X-2", token="ANCHOR_PATH_INSIDE_HOME")
    return values, warnings


def _read_config_values(home):
    path = config_path(home)
    if not os.path.lexists(path):
        return {}, [], False
    if not os.path.isfile(path):
        # A config path that stands but is not a file (a
        # directory at the path) is a config failure, not
        # an absent config (Step 17 entry S17-R1X-013).
        raise ConfigError(
            "the config path stands but is not a file",
            row="X-1", token="CONFIG_INVALID")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except UnicodeDecodeError:
        raise ConfigError(
            "the config file does not decode as UTF-8",
            row="X-1", token="CONFIG_INVALID")
    except OSError:
        raise ConfigError(
            "the config file cannot be read",
            row="X-1", token="CONFIG_INVALID")
    values, warnings = parse_config(text, home=str(home))
    return values, warnings, True


def write_config(home, text):
    """Write the config file, named config.txt, inside the home given.

    The writing half applies the parse the reading half
    applies on every read, so the product cannot write a
    config it will itself refuse to read (Step 17 entry
    S17-R1X-015).
    """
    home = str(home)
    parse_config(text, home=home)
    os.makedirs(home, exist_ok=True)
    with open(config_path(home), "w", encoding="utf-8") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())


def effective_limits(home, run_id=None):
    """The limits in force over a home, each with value, source, unit.

    The config file sets a run starting values. A
    limit_raise journal entry for a run overrides the
    config value for that run only, for the one limit it
    names, and the source names which act set the value.
    """
    values, _warnings, _present = _read_config_values(home)
    limits = {}
    for key in LIMIT_KEYS:
        if key in values:
            limits[key] = {"value": values[key], "source": "config",
                           "unit": _LIMIT_UNIT[key]}
        else:
            limits[key] = {"value": _LIMIT_DEFAULT[key],
                           "source": "brief default",
                           "unit": _LIMIT_UNIT[key]}
    if run_id is not None:
        scan = _scan(home, "probe")
        if scan.failure is not None:
            raise JournalError(
                "the journal does not recompute; its limits "
                "stand unread", row="I-2",
                token="JOURNAL_VERIFY_FAILED")
        for entry in _entries_with_hash(scan):
            if entry.get("entry_kind") != "limit_raise":
                continue
            payload = entry.get("payload") or {}
            if payload.get("run_id") != run_id:
                continue
            key = _member_to_key(payload.get("limit"))
            raised = payload.get("raised_value")
            if key is not None and type(raised) is int:
                limits[key] = {"value": raised, "source": "raise",
                               "unit": _LIMIT_UNIT[key]}
    return limits


def start_run(home, run_id=None, audit_date=None):
    """Open a run over a home, on the config in force at its start.

    Where no config file stands, the run proceeds with
    every key at its brief value default, and the run
    record names the config file as absent. The audit date
    is the call input given, never a clock read.
    """
    home = str(home)
    _values, _warnings, present = _read_config_values(home)
    return {
        "run_id": run_id,
        "audit_date": audit_date,
        "home": home,
        "config_file": config_path(home) if present else "absent",
        "limits_in_force": effective_limits(home, run_id=run_id),
    }


class _WriteLock:
    """The exclusion: an advisory exclusive lock, held per home.

    The lock is the flock advisory lock on the file named
    .citeline-write.lock inside the home, taken with a
    non-blocking attempt and held for the whole writing
    invocation. Contention fails at row X-10. A platform
    or filesystem that cannot give the lock fails closed
    at row X-12. No stale holder recovery act exists: the
    operating system releases the lock when the holder
    process ends, and the lock file presence on disk after
    a holder ends bars nothing.

    A hold of kind "batch" is a sealed container: it
    grants no join permit of its own and it suspends any
    permit it joined under, so the permit stands only
    where the container own code grants it around one of
    its own append calls. An append made by other code
    running on the holder thread inside the window, a
    signal handler among its forms, therefore stands
    contended at row X-10 and stores nothing, instead of
    joining a batch whose rollback would erase it whole
    (Step 17 round 4 entry S17-R4-003).
    """

    def __init__(self, home, kind="container"):
        self.home = str(home)
        self.handle = None
        self._nested = False
        self._invocation = object()
        self._kind = kind
        self._granted = False
        self._suspended = False

    def __enter__(self):
        os.makedirs(self.home, exist_ok=True)
        path = _lock_path(self.home)
        with _HELD_LOCKS_GUARD:
            held = _HELD_LOCKS.get(path)
            if held is not None:
                # Re-entry is judged by thread and by join
                # permit, not by process or thread alone. A
                # caller joins a standing hold only where it
                # runs on the holder thread while a join
                # permit stands for this home on this thread.
                # A permit stands only inside a container
                # hold: a batch append, a recovery, a replay,
                # or a caller that took the lock to judge
                # appends it then makes, as the service import
                # judgement does. A single entry append takes
                # the lock as a leaf and grants no permit, and
                # an append that joins under a permit suspends
                # that permit for its own duration, so no
                # invocation that runs inside an append, a
                # payload deepcopy hook among them, can join:
                # it stands contended at row X-10 and stores
                # nothing, exactly as a caller in another
                # process does (Step 17 round 2 entry
                # S17-R2-001, reopened at round 3 entry
                # S17-R3-001).
                handle, depth, owner_thread, invocation = held
                if threading.get_ident() == owner_thread \
                        and _join_permit_count(path) > 0:
                    _HELD_LOCKS[path] = (
                        handle, depth + 1, owner_thread, invocation)
                    self._nested = True
                    if self._kind in ("append", "batch"):
                        _change_join_permit(path, -1)
                        self._suspended = True
                    return self
                raise JournalError(
                    "a writing invocation already holds this home",
                    row="X-10", token="WRITE_CONTENDED")
            try:
                handle = open(path, "a+")
            except OSError:
                raise JournalError(
                    "the write lock cannot be given on this "
                    "filesystem", row="X-12",
                    token="LOCK_UNAVAILABLE")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                raise JournalError(
                    "a writing invocation already holds this home",
                    row="X-10", token="WRITE_CONTENDED")
            except OSError:
                handle.close()
                raise JournalError(
                    "the write lock cannot be given on this "
                    "filesystem", row="X-12",
                    token="LOCK_UNAVAILABLE")
            handle.seek(0)
            handle.truncate()
            handle.write("holder pid %d\n" % os.getpid())
            handle.flush()
            self.handle = handle
            _HELD_LOCKS[path] = (
                handle, 1, threading.get_ident(), self._invocation)
            _active_invocations(path).append(self._invocation)
            if self._kind == "container":
                _change_join_permit(path, 1)
                self._granted = True
            return self

    def __exit__(self, exc_type, exc, tb):
        path = _lock_path(self.home)
        if self._nested:
            with _HELD_LOCKS_GUARD:
                held = _HELD_LOCKS.get(path)
                if held is not None:
                    _HELD_LOCKS[path] = (
                        held[0], held[1] - 1, held[2], held[3])
                if self._suspended:
                    _change_join_permit(path, 1)
                    self._suspended = False
            self._nested = False
            return False
        if self._granted:
            with _HELD_LOCKS_GUARD:
                _change_join_permit(path, -1)
            self._granted = False
        if self.handle is not None:
            try:
                fcntl.flock(self.handle, fcntl.LOCK_UN)
            finally:
                self.handle.close()
                self.handle = None
        with _HELD_LOCKS_GUARD:
            _HELD_LOCKS.pop(path, None)
            active = _active_invocations(path)
            if self._invocation in active:
                active.remove(self._invocation)
        return False


# Locks this process holds, by lock file path, as
# (handle, hold depth, holder thread, holder invocation).
# A depth above one stands for the single entry appends
# inside one batch append joining that batch invocation
# hold on its own thread. The guard serialises the check
# and the registration across threads, so two threads of
# one process cannot both read the lock as free.
_HELD_LOCKS = {}
_HELD_LOCKS_GUARD = threading.Lock()
_LOCK_LOCAL = threading.local()


def _active_invocations(path):
    """The lock invocations active on this thread, for one path."""
    active = getattr(_LOCK_LOCAL, "active", None)
    if active is None:
        active = {}
        _LOCK_LOCAL.active = active
    return active.setdefault(path, [])


def _join_permit_count(path):
    """The join permits standing for one path on this thread."""
    permits = getattr(_LOCK_LOCAL, "permits", None)
    if permits is None:
        return 0
    return permits.get(path, 0)


def _change_join_permit(path, delta):
    permits = getattr(_LOCK_LOCAL, "permits", None)
    if permits is None:
        permits = {}
        _LOCK_LOCAL.permits = permits
    permits[path] = permits.get(path, 0) + delta


def _write_anchor(anchor_path, head_hash, sequence):
    directory = os.path.dirname(anchor_path) or "."
    os.makedirs(directory, exist_ok=True)
    temporary = os.path.join(
        directory,
        os.path.basename(anchor_path) + ".tmp-%d-%d"
        % (sequence, os.getpid()))
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write("%s %d\n" % (head_hash, sequence))
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, anchor_path)
    except FileNotFoundError:
        # The temporary stands lost under its writer before
        # its link step: the condition row X-13 names, in
        # the vocabulary that row states (Step 17 round 3
        # entry S17-R3-062).
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise JournalError(
            "the anchor temporary was lost before its link "
            "step", row="X-13", token="TEMPORARY_LOST")
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _restore_journal_size(path, size):
    """Truncate the journal back to a stated size, best effort."""
    try:
        with open(path, "r+b") as handle:
            handle.truncate(size)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        pass
    for cache_key in [key for key in _scan_cache if key[0] == path]:
        _scan_cache.pop(cache_key, None)


_IDENTITY_MARKER_FIELDS = frozenset(
    ("snapshot_id", "run_id", "answer_id"))


def _resolve_sequence_identity(value, sequence, field=None):
    """Resolve the {sequence} identity marker in one payload.

    Resolution stands confined to the identity fields the
    mechanism was charged with resolving: snapshot_id,
    run_id, and answer_id, at any depth. A string standing
    in any other field is caller text and stands stored
    exactly as written, marker spelling included (Step 17
    round 3 entry S17-R3-009). Values carrying no marker
    stand as they stand.

    The field context stands held through a list or a tuple
    standing under an identity key, so a marker in an
    element of such a list resolves as the marker standing
    directly under the key resolves (Step 17 round 4 entry
    S17-R4-071). A corrected record carried by a correction
    payload stands resolved against the sequence the record
    replaces, the supersedes value its own payload names,
    not against the sequence of the correction entry that
    carries it (Step 17 round 4 entry S17-R4-015).
    """
    if isinstance(value, str):
        if field in _IDENTITY_MARKER_FIELDS:
            return value.replace("{sequence}", str(sequence))
        return value
    if isinstance(value, dict):
        supersedes = value.get("supersedes_sequence")
        corrected = value.get("corrected_record")
        if isinstance(corrected, dict) and type(supersedes) is int:
            return {
                name: _resolve_sequence_identity(
                    item,
                    supersedes if name == "corrected_record"
                    else sequence,
                    field=name)
                for name, item in value.items()}
        return {name: _resolve_sequence_identity(item, sequence,
                                                 field=name)
                for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_resolve_sequence_identity(item, sequence,
                                           field=field)
                for item in value]
    return value


BATCH_INTENT_FILENAME = ".citeline-batch-intent.json"


def _batch_intent_path(home):
    return os.path.join(str(home), BATCH_INTENT_FILENAME)


def _write_batch_intent(home, journal_size, anchor_path, anchor_bytes,
                        count):
    """Record one batch in flight, before its first entry lands.

    The record names the journal size and the anchor content
    the batch started from, so a batch whose process is
    killed, which raises nothing and runs no rollback, can
    still be rolled back whole by the next invocation that
    finds this record standing (Step 17 round 2 entry
    S17-R2-083, on the S17-R1-089 batch discipline). A
    failure to record the intent stands reported to the
    caller, which bars the batch in the journal vocabulary:
    a batch never runs with its kill protection silently
    off (Step 17 round 3 entry S17-R3-053). Returns True
    where the record stands written.
    """
    record = {
        "journal_size": journal_size,
        "anchor_path": anchor_path,
        "anchor_bytes": None if anchor_bytes is None else
        base64.b64encode(anchor_bytes).decode("ascii"),
        "count": count,
    }
    intent_path = _batch_intent_path(home)
    if os.path.islink(intent_path):
        # The intent path is an internal scratch file of
        # the home: a link standing at it names a file
        # outside the home, and the write does not follow
        # it, so no batch creates a file outside the home
        # holding the record content. The write stands
        # refused, and the batch caller bars the batch in
        # the journal vocabulary on that report, as it
        # bars it on any intent write failure (Step 17
        # round 4 entry S17-R4-009).
        return False
    try:
        with open(intent_path, "w",
                  encoding="utf-8") as handle:
            handle.write(json.dumps(record))
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        return False
    return True


def _clear_batch_intent(home):
    try:
        os.unlink(_batch_intent_path(home))
    except OSError:
        pass


# A validation outcome beside success and refusal: the
# record stands deferred, neither acted on nor cleared,
# where the state it must be judged against does not
# stand ready to judge it, a restored prefix that does
# not recompute or a config that does not parse with an
# anchor the record names that cannot be confirmed. The
# record stands for a later invocation to judge again
# once that state is repaired, so a genuine record is
# not destroyed by a fault outside it (Step 17 round 4
# entries S17-R4-002 and S17-R4-004).
_DEFER_BATCH_RECOVERY = object()


def recover_interrupted_batch(home):
    """Roll back one batch whose process died inside it.

    Where a batch intent record stands and no live holder
    holds the home, the batch it names never completed:
    the journal stands truncated back to the size the
    record names, the anchor stands restored to the
    content the record names, and the record stands
    removed, so no partial batch stands as ordinary state
    and the import it belonged to can be run again whole
    (entry S17-R2-083). The record stands validated
    against the standing journal and the home before any
    of that acts (round 3 entry S17-R3-002), judged
    against the state the batch started from, so a later
    config change or config fault does not destroy a
    genuine record (round 4 entry S17-R4-002), and a
    landed recovery appends its own failure record
    stating that it ran (round 3 entry S17-R3-065, under
    the Manager ruling recorded in the step record).
    Returns True where a recovery landed. Where the home
    stands held by a live batch, or no record stands,
    nothing happens here: the live batch owns its own
    rollback. Where the record stands deferred, or where
    its ruled failure record cannot land at the journal
    length cap, the recovery does not stand reported as
    landed: this call returns False and the record
    stands, so the recovery can land whole once the
    state that bars it is repaired or the cap is raised
    (round 4 entries S17-R4-004 and S17-R4-069, the
    second on the terms of the round 4 disposition
    ruling (d)).
    """
    home = str(home)
    intent_path = _batch_intent_path(home)
    if not os.path.exists(intent_path):
        return False
    try:
        with _WriteLock(home, kind="batch"):
            try:
                with open(intent_path, "r",
                          encoding="utf-8") as handle:
                    record = json.loads(handle.read())
            except (OSError, ValueError, RecursionError):
                # A record that does not read names no batch
                # state to restore: it can only be the debris
                # of a kill before the first entry landed,
                # which appended nothing. A parse that never
                # returns, a deeply nested record among its
                # forms, stands judged in the same recorded
                # vocabulary as every sibling JSON reader
                # judges it, and never as a raw error (Step
                # 17 round 4 entry S17-R4-063).
                _clear_batch_intent(home)
                return False
            validated = _validate_batch_intent(home, record)
            if validated is _DEFER_BATCH_RECOVERY:
                # The record stands unjudged, not refused:
                # it is left standing for a later invocation,
                # and nothing is truncated, written, or
                # deleted on its word.
                return False
            if validated is None:
                # A record whose fields do not stand against
                # the standing journal and the home names no
                # batch this recovery may act on: it stands
                # cleared and nothing is truncated, written,
                # or deleted on its word (Step 17 round 3
                # entry S17-R3-002).
                _clear_batch_intent(home)
                return False
            journal_size, count, anchor_path, anchor_bytes, \
                restored_count = validated
            try:
                journal_cap = effective_limits(
                    home)["journal_length"]["value"]
            except Exception:
                journal_cap = None
            if journal_cap is not None \
                    and restored_count + 1 > journal_cap:
                # The recovery record the ruling at entry
                # S17-R3-065 requires could not land at the
                # cap, so the recovery does not land at all
                # in silence: it stands deferred whole, its
                # record standing, until the cap admits both
                # the restored prefix and the record (Step
                # 17 round 4 entry S17-R4-069).
                return False
            _restore_journal_size(journal_path(home), journal_size)
            if anchor_path is not None:
                try:
                    if anchor_bytes is None:
                        if os.path.exists(anchor_path):
                            os.unlink(anchor_path)
                    else:
                        with open(anchor_path, "wb") as handle:
                            handle.write(anchor_bytes)
                            handle.flush()
                            os.fsync(handle.fileno())
                except OSError:
                    pass
            # The recovery itself stands recorded, under
            # the Manager ruling on entry S17-R3-065: a
            # failure record entry, appended through the
            # ordinary append path under this same hold,
            # stating that a recovery ran, the interrupted
            # batch it answered, and the point the journal
            # stands restored to. No new entry kind stands
            # invented. A failure of this append leaves the
            # recovery itself standing, except a failure at
            # the journal length cap: that failure stands
            # judged, the recovery does not stand reported
            # as landed, and the intent record stands as
            # its evidence (Step 17 round 4 entry
            # S17-R4-069).
            payload = {
                "operation": "recovery",
                "error_value": "interrupted_batch",
                "subject_identity": "batch of %d entries" % count,
                "date": None,
                "rule_fired": "interrupted_batch",
                "batch_count": count,
                "restored_journal_size": journal_size,
                "restored_entry_count": restored_count,
            }
            record_judged_failed = False
            _change_join_permit(_lock_path(home), 1)
            try:
                append_entry(home, "failure_record", payload)
            except JournalError as error:
                if error.token == "JOURNAL_CAP_EXCEEDED":
                    record_judged_failed = True
            except Exception:
                pass
            finally:
                _change_join_permit(_lock_path(home), -1)
            if record_judged_failed:
                return False
            _clear_batch_intent(home)
            return True
    except JournalError:
        # A live holder stands on the home, or the lock
        # cannot be given: the batch, if any, is not this
        # caller's to recover.
        return False


def _record_anchor_plausible(home, anchor_path, standing):
    """Whether a file standing at a path a batch intent
    record names as its anchor is a recording of this
    journal: an anchor recording in the writer form whose
    head hash and sequence name one standing line. This
    is the guard that lets a genuine record be judged
    against the state its batch started from where the
    config no longer names that anchor, without opening
    the recovery to a record naming an arbitrary file
    (Step 17 round 4 entry S17-R4-002)."""
    state, recorded = _read_anchor(anchor_path)
    if state != "ok":
        return False
    for index, raw in enumerate(standing.split(b"\n"), start=1):
        if not raw:
            continue
        if hashlib.sha256(raw).hexdigest() == recorded["head_hash"]:
            return recorded["sequence"] == index
    return False


def _validate_batch_intent(home, record):
    """Validate one batch intent record against the standing
    journal and the home, or return None where it does not
    stand, or the deferral marker where the state it must
    be judged against does not stand ready.

    The record is read as a claim to verify, as the journal
    own lines are read, never as instructions (Step 17
    round 3 entry S17-R3-002). Its form stands judged
    whole: the genuine writer writes exactly four members,
    and every member beyond those four, and a record
    naming no batch at all, stands refused (Step 17 round
    4 entries S17-R4-008 and S17-R4-068). Its journal size
    must stand at a line boundary of the standing journal
    and no past it. Its count must cover the entries
    standing past that size, and no tail longer than the
    batch it names may stand rolled back on its word. The
    restored prefix the size names must itself recompute
    as a chain before the record is judged or acted on,
    so a damaged prefix stands judged as damaged and the
    record stands deferred over it, not destroyed and not
    reported recovered (Step 17 round 4 entry S17-R4-004).
    Its anchor content must be the recording the product
    own writer writes for the head the size names, or no
    content where that size names no entry or no anchor
    stood at the batch start. Its anchor path stands
    judged against the state the batch started from: the
    path the config now resolves stands accepted as
    before, and a path the config no longer names, or
    cannot name because the config does not parse, stands
    accepted only where the file at that path is a
    recording of this journal, the mark of the home own
    former anchor, so a config change or a config fault
    after the kill does not destroy a genuine record
    (Step 17 round 4 entry S17-R4-002). On success returns
    the journal size, the count, the anchor path the
    batch started from, the decoded anchor bytes, and the
    entry count the size names.
    """
    if not isinstance(record, dict):
        return None
    if set(record.keys()) != {"journal_size", "anchor_path",
                              "anchor_bytes", "count"}:
        return None
    journal_size = record.get("journal_size")
    count = record.get("count")
    if type(journal_size) is not int or journal_size < 0:
        return None
    if type(count) is not int or count < 1:
        return None
    anchor_bytes_field = record.get("anchor_bytes")
    anchor_bytes = None
    if anchor_bytes_field is not None:
        if not isinstance(anchor_bytes_field, str):
            return None
        try:
            anchor_bytes = base64.b64decode(
                anchor_bytes_field, validate=True)
        except ValueError:
            return None
    record_anchor = record.get("anchor_path")
    if record_anchor is not None \
            and not isinstance(record_anchor, str):
        return None
    try:
        with open(journal_path(home), "rb") as handle:
            standing = handle.read()
    except FileNotFoundError:
        standing = b""
    except OSError:
        return None
    if journal_size > len(standing):
        return None
    if journal_size > 0 and not standing[:journal_size].endswith(b"\n"):
        return None
    prefix = standing[:journal_size]
    restored_count = prefix.count(b"\n") if prefix else 0
    total_count = standing.count(b"\n")
    if standing and not standing.endswith(b"\n"):
        total_count += 1
    beyond = total_count - restored_count
    if beyond < 0 or beyond > count:
        return None
    if journal_size > 0:
        prefix_lines = prefix[:-1].split(b"\n")
        if _validate_chain_lines(prefix_lines) is not None:
            return _DEFER_BATCH_RECOVERY
    if record_anchor is None:
        if anchor_bytes is not None:
            return None
        return (journal_size, count, None, None, restored_count)
    if restored_count == 0:
        if anchor_bytes is not None:
            return None
    else:
        head_line = prefix[:-1].split(b"\n")[restored_count - 1]
        expected_bytes = ("%s %d\n" % (
            hashlib.sha256(head_line).hexdigest(),
            restored_count)).encode("utf-8")
        if anchor_bytes != expected_bytes:
            return None
    try:
        values, _warnings, _present = _read_config_values(home)
    except Exception:
        # A config that does not parse cannot judge the
        # record, and the recovery record append could not
        # be judged under it either: the record stands
        # deferred whole until the config is repaired, and
        # the fault itself stands reported loudly by the
        # caller own config read (Step 17 round 4 entry
        # S17-R4-002).
        return _DEFER_BATCH_RECOVERY
    configured = values.get("anchor_path")
    expected_anchor = _resolve_anchor_path(home, configured) \
        if configured else None
    if record_anchor == expected_anchor:
        return (journal_size, count, record_anchor, anchor_bytes,
                restored_count)
    if _record_anchor_plausible(home, record_anchor, standing):
        return (journal_size, count, record_anchor, anchor_bytes,
                restored_count)
    return None


def append_entry(home, entry_kind, payload, audit_date=None, run_id=None):
    """Append one entry, as one complete write, or nothing.

    The append recomputes the chain before it writes: over
    a journal that does not recompute, over a divergent
    anchor recording, and at either cap, the append stands
    refused and the head stands unchanged. The audit date
    input names the calling run date where a caller states
    one; the entry form itself carries no date field, and
    no clock is read here.
    """
    home = str(home)
    if entry_kind not in ENTRY_KINDS:
        raise JournalError(
            "an unknown entry kind: %r" % (entry_kind,),
            row="U-8", token="MALFORMED_CALL")
    if not isinstance(payload, dict):
        raise JournalError(
            "an entry payload must be an object",
            row="U-8", token="MALFORMED_CALL")
    if _container_depth(payload) + 2 > MAX_DEPTH:
        raise JournalError(
            "the entry nesting depth breaches its limit",
            row="X-3", token="LIMIT_EXCEEDED")
    # A batch killed inside its appends leaves its intent
    # record standing; the next append on this home rolls
    # that batch back before it reads the chain, unless
    # this append itself stands inside a batch this process
    # holds, whose intent is its own (entry S17-R2-083).
    with _HELD_LOCKS_GUARD:
        _batch_held = _lock_path(home) in _HELD_LOCKS
    if not _batch_held:
        recover_interrupted_batch(home)
    with _WriteLock(home, kind="append"):
        scan = _scan(home, "torn")
        if scan.failure is not None:
            raise JournalError(
                "the journal does not recompute; appends stand barred",
                row="I-2", token="JOURNAL_VERIFY_FAILED")
        values, _warnings, _present = _read_config_values(home)
        anchor_path = values.get("anchor_path")
        resolved_anchor = None
        if anchor_path:
            resolved_anchor = _resolve_anchor_path(home, anchor_path)
            anchor_state, recorded = _read_anchor(resolved_anchor)
            # A configured anchor that is absent, emptied,
            # unreadable, malformed, stale, or divergent
            # over a standing journal is an integrity state
            # that bars the append: the append is the act
            # that would rewrite the anchor and erase the
            # signal (Step 17 entries S17-R1X-001, S17-R1X-002,
            # and S17-R1X-006). Over an empty journal an
            # absent anchor bars nothing: the first append
            # establishes it.
            if anchor_state == "malformed" or (
                    anchor_state == "ok"
                    and _agreement_for(recorded, scan) != "matching"
            ) or (
                    anchor_state == "absent" and scan.entry_count > 0
            ):
                raise JournalError(
                    "the anchor recording does not stand as the "
                    "standing head; appends stand barred",
                    row="I-2", token="JOURNAL_VERIFY_FAILED")
        if entry_kind == "limit_raise":
            key = _member_to_key(payload.get("limit"))
            if key is None:
                raise JournalError(
                    "a limit raise names no limit: %r"
                    % (payload.get("limit"),),
                    row="U-8", token="MALFORMED_CALL")
            raised = payload.get("raised_value")
            if type(raised) is not int:
                raise JournalError(
                    "a limit raise value must be a whole number: %r"
                    % (raised,), row="U-8", token="MALFORMED_CALL")
            index = _LIMIT_INDEX[key]
            ceiling = _LIMIT_DEFAULT[key] * 10 if index <= 40 \
                else _LIMIT_DEFAULT[key]
            if raised < 1 or raised > ceiling:
                raise JournalError(
                    "a limit raise outside the range a config "
                    "value for the same limit must stand in: %r"
                    % (raised,), row="X-1", token="CONFIG_INVALID")
            for entry in _entries_with_hash(scan):
                if entry.get("entry_kind") != "limit_raise":
                    continue
                other = entry.get("payload") or {}
                if other.get("limit") == payload.get("limit") \
                        and other.get("run_id") == payload.get("run_id"):
                    raise JournalError(
                        "a second limit raise for the same limit in "
                        "the same run is refused",
                        row="X-11", token="LIMIT_RAISE_REPEATED")
        if entry_kind == "correction":
            # A correction is validated at append, as the
            # other special payload kind is: its target must
            # be a whole sequence naming a standing entry
            # that is not itself a correction, and its
            # corrected record must be a record (Step 17
            # entry S17-R1X-028).
            supersedes = payload.get("supersedes_sequence")
            corrected = payload.get("corrected_record")
            if type(supersedes) is not int \
                    or supersedes < 1 \
                    or supersedes > scan.entry_count \
                    or not isinstance(corrected, dict):
                raise JournalError(
                    "a correction names no standing record it "
                    "can govern: %r" % (payload,),
                    row="U-8", token="MALFORMED_CALL")
            target = scan.parsed[supersedes - 1]
            if not isinstance(target, dict) \
                    or target.get("entry_kind") == "correction":
                raise JournalError(
                    "a correction of a correction stands "
                    "refused: the fold governs records, not "
                    "corrections",
                    row="U-8", token="MALFORMED_CALL")
        limits = effective_limits(home, run_id=run_id)
        if scan.entry_count + 1 > limits["journal_length"]["value"]:
            raise JournalError(
                "the journal length cap stands reached",
                row="I-1", token="JOURNAL_CAP_EXCEEDED",
                refusal_context="append_cap", limit_number=39)
        entry = {
            "sequence": scan.entry_count + 1,
            "entry_kind": entry_kind,
            "form_version": FORM_VERSION,
            "payload": copy.deepcopy(payload),
            "previous_hash": scan.head_hash,
        }
        # Identity derivation, on the plan identifier
        # derivation table: a payload string carrying the
        # {sequence} marker in an identity field stands for
        # the identity derived from the journal sequence of
        # the entry that stores the record, and the marker
        # is resolved here, under the write lock, at the
        # moment the sequence stands assigned, so no caller
        # side count read can mint an identity another
        # append also mints (Step 17 entry S17-R1-077,
        # cured at the service seam in seat F7 with this
        # one mechanism in the append path). Resolution
        # stands confined to the identity fields, so caller
        # text in every other field stands stored as
        # written (Step 17 round 3 entry S17-R3-009).
        entry["payload"] = _resolve_sequence_identity(
            entry["payload"], entry["sequence"])
        if _container_depth(entry) > MAX_DEPTH:
            raise JournalError(
                "the entry nesting depth breaches its limit",
                row="X-3", token="LIMIT_EXCEEDED")
        canonical = canonical_bytes(entry)
        size_cap = limits["total_home_size"]["value"] * _SIZE_MULTIPLIERS[
            limits["total_home_size"]["unit"]]
        if _home_size(home) + len(canonical) + 1 > size_cap:
            raise JournalError(
                "the total home size cap stands reached",
                row="I-1", token="JOURNAL_CAP_EXCEEDED",
                refusal_context="append_cap", limit_number=40)
        path = journal_path(home)
        try:
            original_size = os.path.getsize(path)
        except OSError:
            original_size = 0
        try:
            with open(path, "ab") as handle:
                handle.write(canonical + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            # A write that fails part way stands rolled
            # back to the size the journal stood at, so the
            # append is one complete write or nothing, and
            # the failure reaches the caller in the recorded
            # vocabulary, never as a bare OSError over a
            # torn tail (Step 17 entry S17-R1-090).
            _restore_journal_size(path, original_size)
            raise JournalError(
                "the entry write failed; the journal stands "
                "as it stood", row="I-2",
                token="JOURNAL_VERIFY_FAILED")
        entry["entry_hash"] = hashlib.sha256(canonical).hexdigest()
        extended = _Scan()
        extended.lines = scan.lines + [canonical]
        extended.parsed = scan.parsed + [_parse_line(canonical)]
        extended.failure = None
        extended.verified = scan.verified + 1
        extended.head_hash = entry["entry_hash"]
        extended.entry_count = scan.entry_count + 1
        stat = _stat_key(path)
        for mode in ("probe", "torn"):
            _scan_cache[(path, mode, None, None)] = (stat, extended)
        if resolved_anchor is not None:
            try:
                _write_anchor(resolved_anchor, entry["entry_hash"],
                              entry["sequence"])
            except JournalError:
                # A lost anchor temporary reports in its own
                # vocabulary at row X-13 (entry S17-R3-062);
                # the append stands rolled back all the same,
                # and the error stands as it was raised.
                _restore_journal_size(path, original_size)
                for cache_key in [key for key in _scan_cache
                                  if key[0] == path]:
                    _scan_cache.pop(cache_key, None)
                raise
            except OSError:
                # An anchor write that fails is not swallowed:
                # the append stands rolled back and the
                # failure is reported, so no append reports
                # success with no anchor standing (Step 17
                # entry S17-R1X-005).
                _restore_journal_size(path, original_size)
                for cache_key in [key for key in _scan_cache
                                  if key[0] == path]:
                    _scan_cache.pop(cache_key, None)
                raise JournalError(
                    "the anchor write failed; the append "
                    "stands rolled back", row="I-2",
                    token="JOURNAL_VERIFY_FAILED")
        return entry


def append_entries_atomic(home, entries, audit_date=None, run_id=None):
    """Append a batch of entries as one invocation, or none.

    The batch is the multi append discipline (Step 17
    entry S17-R1-089): an invocation that appends more
    than one entry holds the write lock across the whole
    batch, checks the whole batch cost against the
    journal length cap before the first entry stands
    written, and, where any entry of the batch fails,
    rolls the journal and the anchor back to the state
    they stood in before the batch, so no partial work
    stands behind a failure report. Before the first
    entry lands the batch records its starting state in
    a batch intent record inside the home, so a batch
    whose process is killed inside it, which runs no
    rollback of its own, stands rolled back by the next
    invocation through recover_interrupted_batch (entry
    S17-R2-083). Entries stand as
    (entry_kind, payload) pairs in append order. Returns
    the appended entry records in order.
    """
    home = str(home)
    # The argument form is judged before any vocabulary
    # check inside the loop, in the form the sibling replay
    # surface states at row U-8: the batch takes a
    # collection of pairs, and an item that is no pair, a
    # pair of the wrong length, or a collection that is no
    # collection of pairs at all is a malformed call, never
    # a raw unpacking error (Step 17 round 2 entry
    # S17-R2-007).
    if entries is None or isinstance(entries, (str, bytes, bytearray,
                                               dict)):
        raise JournalError(
            "a batch takes a collection of entry pairs",
            row="U-8", token="MALFORMED_CALL")
    try:
        items = list(entries)
    except TypeError:
        raise JournalError(
            "a batch takes a collection of entry pairs",
            row="U-8", token="MALFORMED_CALL")
    prepared = []
    for item in items:
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise JournalError(
                "a batch item must be one entry kind and "
                "payload pair: %r" % (item,),
                row="U-8", token="MALFORMED_CALL")
        entry_kind, payload = item
        if entry_kind not in ENTRY_KINDS:
            raise JournalError(
                "an unknown entry kind: %r" % (entry_kind,),
                row="U-8", token="MALFORMED_CALL")
        if not isinstance(payload, dict):
            raise JournalError(
                "an entry payload must be an object",
                row="U-8", token="MALFORMED_CALL")
        prepared.append((entry_kind, payload))
    if not prepared:
        return []
    recover_interrupted_batch(home)
    path = journal_path(home)
    with _WriteLock(home, kind="batch"):
        scan = _scan(home, "torn")
        if scan.failure is not None:
            raise JournalError(
                "the journal does not recompute; appends "
                "stand barred", row="I-2",
                token="JOURNAL_VERIFY_FAILED")
        limits = effective_limits(home, run_id=run_id)
        if scan.entry_count + len(prepared) > limits[
                "journal_length"]["value"]:
            raise JournalError(
                "the journal length cap stands reached",
                row="I-1", token="JOURNAL_CAP_EXCEEDED",
                refusal_context="append_cap", limit_number=39)
        try:
            original_size = os.path.getsize(path)
        except OSError:
            original_size = 0
        values, _warnings, _present = _read_config_values(home)
        anchor_path = values.get("anchor_path")
        resolved_anchor = None
        anchor_bytes = None
        if anchor_path:
            resolved_anchor = _resolve_anchor_path(home, anchor_path)
            try:
                with open(resolved_anchor, "rb") as handle:
                    anchor_bytes = handle.read()
            except OSError:
                anchor_bytes = None
        if not _write_batch_intent(home, original_size,
                                   resolved_anchor, anchor_bytes,
                                   len(prepared)):
            # The intent record stands unwritten, so the
            # batch would run with its kill protection off:
            # it stands refused before any entry lands, in
            # the journal vocabulary, as the anchor intent
            # failure of the append path stands refused
            # (Step 17 round 3 entry S17-R3-053).
            raise JournalError(
                "the batch intent record could not be "
                "written; the batch stands refused before "
                "any entry lands", row="I-2",
                token="JOURNAL_VERIFY_FAILED")
        appended = []
        try:
            for entry_kind, payload in prepared:
                # The join permit stands for this call
                # only: it is granted around the batch own
                # append and withdrawn as soon as the append
                # returns, so no ambient append inside the
                # batch window joins the batch (Step 17
                # round 4 entry S17-R4-003).
                _change_join_permit(_lock_path(home), 1)
                try:
                    appended.append(append_entry(
                        home, entry_kind, payload,
                        audit_date=audit_date, run_id=run_id))
                finally:
                    _change_join_permit(_lock_path(home), -1)
        except Exception:
            # The rollback restores first and clears the
            # intent record last, the order the recovery
            # path itself stands in: a kill inside the
            # rollback then leaves the record standing over
            # the restored journal, and the next invocation
            # recovers from it, instead of leaving a partial
            # batch standing as ordinary state with no
            # record (Step 17 round 3 entry S17-R3-004).
            _restore_journal_size(path, original_size)
            if resolved_anchor is not None:
                try:
                    if anchor_bytes is None:
                        if os.path.exists(resolved_anchor):
                            os.unlink(resolved_anchor)
                    else:
                        with open(resolved_anchor, "wb") as handle:
                            handle.write(anchor_bytes)
                            handle.flush()
                            os.fsync(handle.fileno())
                except OSError:
                    pass
            _clear_batch_intent(home)
            raise
        _clear_batch_intent(home)
        return appended


def fold(home, kinds=None, to_sequence=None, apply_corrections=False):
    """Fold the journal as it stands, in sequence.

    A record no entry folds to does not exist for any
    reader. A final partial line classified as a standing
    holder append in progress stands treated as not yet an
    entry, and no value is read from it. With corrections
    applied, a correction entry governs reporting from its
    sequence: the corrected record stands in place of the
    superseded entry record, while the superseded entry
    itself stays readable in the plain fold.
    """
    scan = _scan(home, "probe")
    if scan.failure is not None:
        # The reader family runs the barred check its own
        # append path runs: a chain that fails verify is
        # not consumed as state, in whole or in prefix
        # (Step 17 entry S17-R1-004).
        raise JournalError(
            "the journal does not recompute; reads stand barred",
            row="I-2", token="JOURNAL_VERIFY_FAILED")
    for parsed in scan.parsed:
        if parsed is None or not isinstance(parsed, dict):
            raise JournalError(
                "the journal holds a line that does not parse as "
                "one entry", row="I-2", token="JOURNAL_VERIFY_FAILED")
    entries = _entries_with_hash(scan)
    selected = []
    by_sequence = {}
    for entry in entries:
        sequence = entry.get("sequence")
        if to_sequence is not None and type(sequence) is int \
                and sequence > to_sequence:
            continue
        if apply_corrections and entry.get("entry_kind") == "correction":
            payload = entry.get("payload") or {}
            supersedes = payload.get("supersedes_sequence")
            target = by_sequence.get(supersedes) \
                if type(supersedes) is int else None
            if target is not None \
                    and isinstance(payload.get("corrected_record"), dict):
                target["payload"] = copy.deepcopy(
                    payload["corrected_record"])
            continue
        selected.append(entry)
        if type(sequence) is int:
            by_sequence[sequence] = entry
    if kinds is not None:
        selected = [entry for entry in selected
                    if entry.get("entry_kind") in kinds]
    return selected


def fold_registry(home, to_sequence=None):
    """Fold the registry state: the standing record per product.

    A registry change payload carries the registry record
    as changed in full record form, so the fold applies
    that record directly at the entry sequence, and a
    correction of a registry entry stands in place for
    every later point.
    """
    state = {}
    for entry in fold(home, to_sequence=to_sequence,
                      apply_corrections=True):
        if entry.get("entry_kind") not in (
                "product_registered", "registry_change"):
            continue
        payload = entry.get("payload") or {}
        product_id = payload.get("product_id")
        if product_id is not None:
            try:
                hash(product_id)
            except TypeError:
                # A registry entry whose product id stands
                # in no hashable form meets this reader in
                # the journal vocabulary, as its sibling
                # readers meet a hostile chain, and not as a
                # raw error (Step 17 round 4 entry
                # S17-R4-007).
                raise JournalError(
                    "the journal holds a registry entry whose "
                    "product id stands in no hashable form; "
                    "reads stand barred", row="I-2",
                    token="JOURNAL_VERIFY_FAILED")
            state[product_id] = payload
    return state


def read_entry(home, sequence):
    """Read one complete entry by its sequence."""
    scan = _scan(home, "probe")
    if scan.failure is not None:
        raise JournalError(
            "the journal does not recompute; reads stand barred",
            row="I-2", token="JOURNAL_VERIFY_FAILED")
    for entry in _entries_with_hash(scan):
        if entry.get("sequence") == sequence:
            return entry
    raise JournalError(
        "no entry stands at sequence %r" % (sequence,),
        row="I-2", token="JOURNAL_VERIFY_FAILED")


def _validate_chain_lines(lines):
    """Validate stated lines as one chain, in scan terms.

    Returns the position of the first failing line, or
    None where the lines form a chain that recomputes.
    The checks are the scan checks: parse, form version,
    depth, entry kind, payload form, sequence, genesis and
    link hashes, canonical rendering, and the duplicate
    limit raise discipline.
    """
    previous_raw = None
    seen_raises = []
    chain = []
    for index, raw in enumerate(lines, start=1):
        parsed = _parse_line(raw)
        if parsed is None or not isinstance(parsed, dict):
            return index
        if type(parsed.get("form_version")) is not int \
                or parsed.get("form_version") != FORM_VERSION:
            return index
        if _container_depth(parsed) > MAX_DEPTH:
            return index
        if parsed.get("entry_kind") not in ENTRY_KINDS:
            return index
        if not isinstance(parsed.get("payload"), dict):
            return index
        if type(parsed.get("sequence")) is not int \
                or parsed.get("sequence") != index:
            return index
        if index == 1 and parsed.get("previous_hash") is not None:
            return index
        if index > 1 and parsed.get("previous_hash") != \
                hashlib.sha256(previous_raw).hexdigest():
            return index
        try:
            rendered = canonical_bytes(parsed)
        except (JournalError, ValueError, ArithmeticError):
            return index
        if rendered != raw:
            return index
        chain.append(parsed)
        if _special_payload_reason(parsed, index, chain) is not None:
            return index
        if parsed.get("entry_kind") == "limit_raise":
            payload = parsed.get("payload") or {}
            raise_key = (payload.get("run_id"),
                         payload.get("limit"))
            if any(raise_key == seen for seen in seen_raises):
                return index
            seen_raises.append(raise_key)
        previous_raw = raw
    return None


def replay(home, entries, resume=False):
    """Replay stated entry lines into a home, returning the head hash.

    With no resume, the replay starts from empty. With
    resume, the stated lines stand appended to the chain
    as it stands, so a replay from a mid chain state
    reaches the same head as the full replay.

    The replay validates before it writes (Step 17 entries
    S17-R1-005 and S17-R1X-029): the entries argument must
    be a collection of entry lines (a single string, a
    bytes object, a mapping, and a non line element are
    each refused as a malformed call, before anything is
    written), the resulting chain must recompute, the
    journal length cap must admit it, and the anchor gate
    the append path runs must pass. A replay without
    resume over a standing journal stands refused: it
    would destroy the standing entries with no record.
    """
    home = str(home)
    if entries is None or isinstance(entries, (str, bytes, bytearray,
                                               dict)):
        raise JournalError(
            "a replay takes a collection of entry lines",
            row="U-8", token="MALFORMED_CALL")
    try:
        iterator = iter(entries)
    except TypeError:
        raise JournalError(
            "a replay takes a collection of entry lines",
            row="U-8", token="MALFORMED_CALL")
    lines = []
    for raw in iterator:
        if isinstance(raw, str):
            try:
                raw = raw.encode("utf-8")
            except UnicodeEncodeError:
                raise JournalError(
                    "a replay line must be one entry line",
                    row="U-8", token="MALFORMED_CALL")
        elif isinstance(raw, (bytes, bytearray)):
            raw = bytes(raw)
        else:
            raise JournalError(
                "a replay line must be one entry line",
                row="U-8", token="MALFORMED_CALL")
        if raw.endswith(b"\n"):
            raw = raw[:-1]
        lines.append(raw)
    # Replay is a writing invocation, and it stands inside
    # the recovery discipline as the other writing paths
    # do: a batch intent standing over this home stands
    # recovered before the replay validates or writes, so
    # no replayed entry lands on a partial batch the next
    # append recovery would erase after the replay
    # reported success (Step 17 round 3 entry S17-R3-003).
    recover_interrupted_batch(home)
    with _WriteLock(home, kind="batch"):
        scan = _scan(home, "torn")
        if scan.failure is not None:
            raise JournalError(
                "the journal does not recompute; a replay "
                "stands barred", row="I-2",
                token="JOURNAL_VERIFY_FAILED")
        if not resume and scan.entry_count > 0:
            raise JournalError(
                "a replay without resume over a standing "
                "journal stands refused: it would destroy "
                "the standing entries",
                row="U-8", token="MALFORMED_CALL")
        values, _warnings, _present = _read_config_values(home)
        anchor_path = values.get("anchor_path")
        resolved_anchor = None
        if anchor_path:
            resolved_anchor = _resolve_anchor_path(home, anchor_path)
            # The gate is the append path gate, over every
            # standing journal including an empty one: a
            # malformed recording bars, a recording that
            # does not stand as the standing head bars, and
            # an absent recording over a standing journal
            # bars. An empty journal is the exact state a
            # full truncation leaves, so it skips nothing
            # (Step 17 round 2 entry S17-R2-005).
            anchor_state, recorded = _read_anchor(resolved_anchor)
            if anchor_state == "malformed" or (
                    anchor_state == "ok"
                    and _agreement_for(recorded, scan) != "matching"
            ) or (
                    anchor_state == "absent" and scan.entry_count > 0
            ):
                raise JournalError(
                    "the anchor recording does not stand "
                    "as the standing head; a replay stands "
                    "barred", row="I-2",
                    token="JOURNAL_VERIFY_FAILED")
        candidate = (scan.lines if resume else []) + lines
        failing = _validate_chain_lines(candidate)
        if failing is not None:
            raise JournalError(
                "the stated lines do not recompute as a "
                "chain; the failing line stands at position "
                "%d" % failing, row="I-2",
                token="JOURNAL_VERIFY_FAILED")
        limits = effective_limits(home)
        if len(candidate) > limits["journal_length"]["value"]:
            raise JournalError(
                "the journal length cap stands reached",
                row="I-1", token="JOURNAL_CAP_EXCEEDED",
                refusal_context="append_cap", limit_number=39)
        path = journal_path(home)
        content = b"".join(raw + b"\n" for raw in candidate)
        try:
            original_size = os.path.getsize(path)
            original_exists = True
        except OSError:
            original_size = 0
            original_exists = False

        def rollback_write():
            if original_exists:
                _restore_journal_size(path, original_size)
            else:
                try:
                    os.unlink(path)
                except OSError:
                    pass
                for cache_key in [key for key in _scan_cache
                                  if key[0] == path]:
                    _scan_cache.pop(cache_key, None)

        if resume:
            try:
                with open(path, "ab") as handle:
                    handle.write(b"".join(
                        raw + b"\n" for raw in lines))
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError:
                _restore_journal_size(path, original_size)
                raise JournalError(
                    "the replay write failed; the journal "
                    "stands as it stood", row="I-2",
                    token="JOURNAL_VERIFY_FAILED")
        else:
            # The replacing branch carries the same guard
            # as the resume branch and the append path: a
            # write failure reports in the vocabulary at
            # row I-2, and its temporary file does not stand
            # left inside the home (Step 17 round 2 entry
            # S17-R2-006).
            temporary = path + ".replay-%d" % os.getpid()
            try:
                with open(temporary, "wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            except FileNotFoundError:
                # The temporary stands lost under its writer
                # before its link step: the condition row
                # X-13 names (Step 17 round 3 entry
                # S17-R3-062).
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
                raise JournalError(
                    "the replay temporary was lost before "
                    "its link step", row="X-13",
                    token="TEMPORARY_LOST")
            except OSError:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass
                raise JournalError(
                    "the replay write failed; the journal "
                    "stands as it stood", row="I-2",
                    token="JOURNAL_VERIFY_FAILED")
        for cache_key in [key for key in _scan_cache
                          if key[0] == path]:
            _scan_cache.pop(cache_key, None)
        if resolved_anchor is not None and candidate:
            try:
                _write_anchor(resolved_anchor,
                              hashlib.sha256(candidate[-1]).hexdigest(),
                              len(candidate))
            except JournalError:
                # A lost anchor temporary reports in its own
                # vocabulary at row X-13 (entry S17-R3-062);
                # the replay stands rolled back all the same.
                rollback_write()
                raise
            except OSError:
                # An anchor write failure is not swallowed:
                # the replay stands rolled back and the
                # failure is reported, as the append path
                # reports it, so no replay reports success
                # with no anchor standing (Step 17 round 2
                # entry S17-R2-005).
                rollback_write()
                raise JournalError(
                    "the anchor write failed; the replay "
                    "stands rolled back", row="I-2",
                    token="JOURNAL_VERIFY_FAILED")
    if candidate:
        return hashlib.sha256(candidate[-1]).hexdigest()
    return None


def append_cost():
    """The append cost per writing invocation kind, in entries.

    Each appending operation appends its subject entry as
    one entry. A repeat call costs one entry again: no
    no-op form stands.
    """
    return {
        "import": {"subject_entries": 1},
        "registry_write": {"subject_entries": 1},
        "round_naming": {"subject_entries": 1},
        "audit": {"subject_entries": 1},
        "guide": {"subject_entries": 1},
    }
