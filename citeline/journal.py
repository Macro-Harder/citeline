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

import copy
import fcntl
import hashlib
import json
import math
import os
import re
from decimal import Decimal, InvalidOperation

from citeline.errors import ConfigError, JournalError

__all__ = [
    "ConfigError",
    "ENTRY_KINDS",
    "JournalError",
    "append_cost",
    "append_entries_atomic",
    "append_entry",
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
    stack = []
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            elif ord(char) < 0x20:
                return False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char in "}]":
            if not stack:
                return False
            opener = stack.pop()
            if (opener == "{") != (char == "}"):
                return False
        elif ord(char) < 0x20:
            return False
    return True


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
    if partial is not None:
        if partial_mode == "probe" and _lock_held_by_other(home) \
                and _is_plausible_entry_prefix(partial):
            scan.partial_ignored = True
        elif partial_mode == "ignore":
            scan.partial_ignored = True
    previous_raw = None
    seen_raises = set()
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
                    elif parsed.get("entry_kind") == "limit_raise":
                        # The one raise per run and limit rule
                        # is a property of the chain, not of
                        # one writing route: a supplied chain
                        # carrying two raises for one run and
                        # limit does not verify (Step 17 entry
                        # S17-R1X-010).
                        payload = parsed.get("payload") or {}
                        raise_key = (repr(payload.get("run_id")),
                                     repr(payload.get("limit")))
                        if raise_key in seen_raises:
                            reason = "duplicate_raise"
                        else:
                            seen_raises.add(raise_key)
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
            entry = dict(parsed)
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
    if re.fullmatch(r"[+-]?[0-9]+", sequence_token) is None:
        return "malformed", {"head_hash": head_hash, "sequence": None}
    return "ok", {"head_hash": head_hash,
                  "sequence": int(sequence_token)}


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
    """

    def __init__(self, home):
        self.home = str(home)
        self.handle = None
        self._nested = False

    def __enter__(self):
        os.makedirs(self.home, exist_ok=True)
        path = _lock_path(self.home)
        held = _HELD_LOCKS.get(path)
        if held is not None and held[0] is not None:
            # A lock this process already holds for this
            # home stands re-entered, not re-taken: a batch
            # append (append_entries_atomic) holds the one
            # lock across its entries, and the single entry
            # appends inside it join that hold instead of
            # contending with it.
            _HELD_LOCKS[path] = (held[0], held[1] + 1)
            self._nested = True
            return self
        try:
            self.handle = open(path, "a+")
        except OSError:
            raise JournalError(
                "the write lock cannot be given on this filesystem",
                row="X-12", token="LOCK_UNAVAILABLE")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close()
            self.handle = None
            raise JournalError(
                "a writing invocation already holds this home",
                row="X-10", token="WRITE_CONTENDED")
        except OSError:
            self.handle.close()
            self.handle = None
            raise JournalError(
                "the write lock cannot be given on this filesystem",
                row="X-12", token="LOCK_UNAVAILABLE")
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write("holder pid %d\n" % os.getpid())
        self.handle.flush()
        _HELD_LOCKS[path] = (self.handle, 1)
        return self

    def __exit__(self, exc_type, exc, tb):
        path = _lock_path(self.home)
        if self._nested:
            held = _HELD_LOCKS.get(path)
            if held is not None:
                _HELD_LOCKS[path] = (held[0], held[1] - 1)
            self._nested = False
            return False
        _HELD_LOCKS.pop(path, None)
        if self.handle is not None:
            try:
                fcntl.flock(self.handle, fcntl.LOCK_UN)
            finally:
                self.handle.close()
                self.handle = None
        return False


# Locks this process holds, by lock file path, as
# (handle, hold depth). A depth above one stands for a
# batch append holding the lock across its entries.
_HELD_LOCKS = {}


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
    os.replace(temporary, anchor_path)


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


def _resolve_sequence_identity(value, sequence):
    """Resolve the {sequence} identity marker in one payload.

    Every string value in the payload, at any depth, has
    the marker replaced by the sequence the append assigns,
    in decimal form. Values carrying no marker stand as
    they stand.
    """
    if isinstance(value, str):
        return value.replace("{sequence}", str(sequence))
    if isinstance(value, dict):
        return {name: _resolve_sequence_identity(item, sequence)
                for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_resolve_sequence_identity(item, sequence)
                for item in value]
    return value


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
    with _WriteLock(home):
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
        # {sequence} marker stands for the identity derived
        # from the journal sequence of the entry that stores
        # the record, and the marker is resolved here, under
        # the write lock, at the moment the sequence stands
        # assigned, so no caller side count read can mint an
        # identity another append also mints (Step 17 entry
        # S17-R1-077, cured at the service seam in seat F7
        # with this one mechanism in the append path).
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
    stands behind a failure report. Entries stand as
    (entry_kind, payload) pairs in append order. Returns
    the appended entry records in order.
    """
    home = str(home)
    prepared = []
    for item in entries:
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
    path = journal_path(home)
    with _WriteLock(home):
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
        appended = []
        try:
            for entry_kind, payload in prepared:
                appended.append(append_entry(
                    home, entry_kind, payload,
                    audit_date=audit_date, run_id=run_id))
        except Exception:
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
            raise
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
    seen_raises = set()
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
        if parsed.get("entry_kind") == "limit_raise":
            payload = parsed.get("payload") or {}
            raise_key = (repr(payload.get("run_id")),
                         repr(payload.get("limit")))
            if raise_key in seen_raises:
                return index
            seen_raises.add(raise_key)
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
    with _WriteLock(home):
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
            if scan.entry_count > 0:
                anchor_state, recorded = _read_anchor(resolved_anchor)
                if anchor_state != "ok" or _agreement_for(
                        recorded, scan) != "matching":
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
        if resume:
            try:
                original_size = os.path.getsize(path)
            except OSError:
                original_size = 0
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
            temporary = path + ".replay-%d" % os.getpid()
            with open(temporary, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        for cache_key in [key for key in _scan_cache
                          if key[0] == path]:
            _scan_cache.pop(cache_key, None)
        if resolved_anchor is not None and candidate:
            try:
                _write_anchor(resolved_anchor,
                              hashlib.sha256(candidate[-1]).hexdigest(),
                              len(candidate))
            except OSError:
                pass
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
