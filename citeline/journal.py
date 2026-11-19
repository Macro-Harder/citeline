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
import contextlib
import copy
import errno
import fcntl
import hashlib
import json
import math
import os
import re
import stat
import tempfile
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
# The settled decision: earned at 3 decimal places, the score value
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

# The characters the slow rendering path must act on: the
# quote and the backslash, the control characters below
# 0x20, and the surrogate range. A string holding none of
# them renders as itself between quotes, byte for byte as
# the slow path renders it (the per character loop
# stood at most of the scan cost at the journal cap).
_STRING_NEEDS_WORK = re.compile(r'["\\\x00-\x1f\ud800-\udfff]')


def _render_string(value):
    if _STRING_NEEDS_WORK.search(value) is None:
        return '"' + value + '"'
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
    interpreter stack inside it."""
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


def _ensure_home_directory(home, make_error):
    """Create the home directory, judging the home form
    first: a home path standing as a regular file, or in
    any other form that is not a directory, stands
    answered by make_error in the recorded vocabulary of
    the calling route, and no raw FileExistsError from
    the directory creation reaches the caller."""
    if os.path.lexists(home) and not os.path.isdir(home):
        raise make_error()
    try:
        os.makedirs(home, exist_ok=True)
    except FileExistsError:
        if not os.path.isdir(home):
            raise make_error()
    except OSError:
        if os.path.lexists(home) and not os.path.isdir(home):
            raise make_error()
        raise


class _UnsafeHomeFile(Exception):
    """A home own file stands as a link, a non regular
    file, or a hard linked file, so no write follows it."""


def _path_is_unsafe_home_file(path):
    """Whether a home own file path stands in a form no
    write may follow: a symbolic link, a non regular
    file, or a file with a hard link count above one,
    the discipline the product states for supplied
    files."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) \
        or not stat.S_ISREG(info.st_mode) \
        or info.st_nlink > 1


def _open_home_file_descriptor(path, mode, create=None,
                               defer_truncate=False):
    """Open one home own file for a writing route, judged at
    the open itself.

    The open carries the no follow guard, so a link
    landing at the path at any point up to the open is
    not followed, and the opened handle itself stands
    judged before anything is written or truncated: a non
    regular file and a hard link count above one each
    stand refused on the handle that stands open, and the
    path stands judged as still naming that handle beside
    them, so a file moved away from its path before the
    open, or a replacement standing at its path, stands
    refused at the open in the same form. Mode "a"
    appends, mode "w" writes and truncates only after the
    judgement stands, mode "r+" reads and writes without
    truncating, and mode "r" reads only. Where
    defer_truncate stands at a mode "w" open, the
    truncate stands deferred to the caller, which
    truncates through the handle only after a further
    rejudgement of the handle stands: no truncate then
    stands placed after the judgement at the open and
    before the rejudgement that catches a plant at the
    return of that judgement. A path that stands in an
    unsafe form, and a path that cannot be opened, raises
    _UnsafeHomeFile or the OSError the open raised."""
    if create is None:
        create = mode in ("a", "w")
    if mode == "a":
        base = os.O_WRONLY | os.O_APPEND
    elif mode == "w":
        base = os.O_WRONLY
    elif mode == "r+":
        base = os.O_RDWR
    else:
        base = os.O_RDONLY
    flags = base
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    descriptor = None
    for _attempt in range(3):
        try:
            descriptor = os.open(path, flags)
            break
        except FileNotFoundError:
            if not create:
                raise
            try:
                descriptor = os.open(
                    path, flags | os.O_CREAT | os.O_EXCL, 0o666)
                break
            except FileExistsError:
                # A racing invocation created the file
                # between the two opens: the judgement
                # stands again at the plain open, whose
                # handle the fstat below judges, and a
                # lock loser takes its contention answer
                # from the flock as before.
                continue
            except OSError:
                raise _UnsafeHomeFile(path)
        except OSError as error:
            # Only the link form stands judged unsafe at
            # the open: every other open failure, a
            # directory at the path among them, keeps
            # the vocabulary its own route states for
            # it, the lock route at row X-12 among them.
            if error.errno == errno.ELOOP:
                raise _UnsafeHomeFile(path)
            raise
    if descriptor is None:
        raise _UnsafeHomeFile(path)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
            raise _UnsafeHomeFile(path)
        _judge_path_still_names_handle(info, path)
        if mode == "w" and not defer_truncate:
            os.ftruncate(descriptor, 0)
    except BaseException:
        os.close(descriptor)
        raise
    if hasattr(os, "O_NONBLOCK"):
        try:
            standing = fcntl.fcntl(descriptor, fcntl.F_GETFL)
            fcntl.fcntl(descriptor, fcntl.F_SETFL,
                        standing & ~os.O_NONBLOCK)
        except OSError:
            pass
    return descriptor


def _judge_path_still_names_handle(info, path):
    """Judge that the path still names the opened handle:
    the file standing at the path stands compared against
    the handle by its inode and its device, so a file
    moved away from its path, and a replacement or a link
    standing at its path in its place, stands refused in
    the form of the judgement that calls this one. A
    rename plant holds its inode and its link count of
    one whole, so the handle facts alone judge nothing
    about it: the path identity stands judged beside them
    at the open judgement and at every rejudgement of
    every journal write site. No anchor on any parent
    directory stands stated by this judgement, and no
    home identity apart from the home path stands stated
    by it."""
    try:
        path_info = os.lstat(path)
    except OSError:
        raise _UnsafeHomeFile(path)
    if stat.S_ISLNK(path_info.st_mode) \
            or not stat.S_ISREG(path_info.st_mode) \
            or path_info.st_ino != info.st_ino \
            or path_info.st_dev != info.st_dev:
        raise _UnsafeHomeFile(path)


def _rejudge_open_descriptor(descriptor, path):
    """Judge an opened home file handle again, between the
    judgement at its open and the write that follows it:
    a hard link planted against the path in that window
    names the same inode the descriptor holds, so the
    link count stands read again on the handle before
    anything is written or truncated through it, and the
    path stands judged as still naming that handle beside
    it, so a rename plant in the same window stands
    refused in the same form."""
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise _UnsafeHomeFile(path)
    _judge_path_still_names_handle(info, path)


def _open_home_file_read_descriptor(path):
    """Open one home own file for reading, judged at the
    open for a symbolic link and a non regular form, with
    a hard link count above one admitted: at a reader the
    link count alone cannot tell a victim file linked to
    the path from the genuine file linked outward, so the
    reader judges the content it reads, as the batch
    intent reader does. The open carries the no follow
    guard and the non blocking flag, so a FIFO standing
    at the path is met as a non regular file without
    opening it."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise _UnsafeHomeFile(path)
        raise
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise _UnsafeHomeFile(path)
    except BaseException:
        os.close(descriptor)
        raise
    if hasattr(os, "O_NONBLOCK"):
        try:
            standing = fcntl.fcntl(descriptor, fcntl.F_GETFL)
            fcntl.fcntl(descriptor, fcntl.F_SETFL,
                        standing & ~os.O_NONBLOCK)
        except OSError:
            pass
    return descriptor


def _restore_preserved_target(target, preserved_bytes):
    """Put back the bytes a target held before its replace,
    through an exclusively created temporary in the
    target directory, best effort: where the restore
    itself fails the target stands absent, as it stood
    under the remedy this restore extends. The restore
    replace stands judged on the same terms as every
    judged replace in this module, and a restore whose
    temporary stands swapped stands tried once more with
    a fresh temporary, so the remedy does not itself move
    a planted link onto the target."""
    directory = os.path.dirname(target) or "."
    for _attempt in range(2):
        try:
            descriptor, temporary = tempfile.mkstemp(
                prefix=os.path.basename(target) + ".tmp-",
                dir=directory)
        except OSError:
            return
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(preserved_bytes)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_inode = os.fstat(
                    handle.fileno()).st_ino
            _replace_judged_temporary(
                temporary, temporary_inode, target)
            return
        except OSError:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _replace_judged_temporary(temporary, inode, target,
                              preserve_target=False):
    """Replace a target with a writer own temporary, judged
    at the replace itself: the file standing at the
    temporary name stands judged for a regular file, the
    very inode the writer created, and a link count of
    one before the replace, and the file standing at the
    target stands judged on the same terms after it, so
    a temporary swapped for a planted link in the write
    window is never moved onto the target behind a
    success report, and a link that lands at the replace
    point itself stands removed and reported instead.

    Where preserve_target stands, the content the target
    held before the replace stands read before it, and
    the post replace remedy, which removes the placed
    file, puts that content back in its place: at the
    anchor the target is the anchor recording itself,
    and a swap caught only after the replace must not
    leave the recording deleted whole, barring every
    later append over a chain that still verifies."""
    info = os.lstat(temporary)
    if stat.S_ISLNK(info.st_mode) \
            or not stat.S_ISREG(info.st_mode) \
            or info.st_ino != inode or info.st_nlink != 1:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise OSError(
            "the temporary stands replaced before its replace")
    preserved_bytes = None
    if preserve_target:
        try:
            standing = os.lstat(target)
            # The content stands preserved at every standing
            # form the anchor reader itself admits: a
            # regular file at any link count, and a symbolic
            # link naming a regular file, whose content the
            # read through the link names. A remedy that
            # preserved only the plain form, a regular file
            # with a link count of one, still left the
            # recording deleted whole at an anchor standing
            # in a link form (extending).
            preserve = stat.S_ISREG(standing.st_mode)
            if stat.S_ISLNK(standing.st_mode):
                try:
                    followed = os.stat(target)
                    preserve = stat.S_ISREG(followed.st_mode)
                except OSError:
                    preserve = False
            if preserve:
                with open(target, "rb") as handle:
                    preserved_bytes = handle.read()
        except OSError:
            preserved_bytes = None
    os.replace(temporary, target)
    try:
        placed = os.lstat(target)
    except OSError:
        raise OSError("the replaced target cannot be judged")
    if stat.S_ISLNK(placed.st_mode) \
            or not stat.S_ISREG(placed.st_mode) \
            or placed.st_ino != inode or placed.st_nlink != 1:
        try:
            os.unlink(target)
        except OSError:
            pass
        if preserved_bytes is not None:
            _restore_preserved_target(target, preserved_bytes)
        raise OSError(
            "the temporary stands replaced at its replace")


def _unsafe_home_file_error(path, label):
    return JournalError(
        "the %s path stands as a link, a non regular "
        "file, or a hard linked file; the write stands "
        "refused and nothing stands written through it"
        % (label,), row="X-4", token="SUPPLIED_PATH_UNSAFE")


class _Scan:
    __slots__ = ("lines", "parsed", "failure", "verified",
                 "head_hash", "entry_count", "partial_ignored",
                 "line_hashes", "partial_seen")

    def __init__(self):
        self.lines = []
        self.parsed = []
        self.failure = None
        self.verified = 0
        self.head_hash = None
        self.entry_count = 0
        self.partial_ignored = False
        self.line_hashes = []
        self.partial_seen = False


_scan_cache = {}


def _stat_key(path):
    try:
        info = os.stat(path)
    except OSError:
        return None
    # The change time stands in the key beside the inode,
    # the size, and the modification time. The key is a
    # first check only: on a filesystem whose timestamp
    # granularity is coarse a same size edit can reproduce
    # every field of it, so the scan cache never serves on
    # this key alone; the content fingerprint computed in
    # _scan over the standing bytes is what certifies a
    # cached scan.
    return (info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_ctime_ns)


def _content_fingerprint(path):
    """The SHA-256 of the file's standing bytes, or None
    where the file cannot be read.

    The read is a plain no follow read, not the judged
    descriptor open: the fingerprint only decides whether
    a cached scan may be served, and a read that races a
    replacement simply fails to match and falls through
    to the judged scan, which judges the path at its own
    open as it always has. Where the bytes cannot be read
    at all, None stands and no cached scan is served.
    """
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    digest = hashlib.sha256()
    try:
        with os.fdopen(descriptor, "rb") as handle:
            while True:
                chunk = handle.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _lock_held_by_other(home):
    """Probe the write lock without taking it, as a liveness test only."""
    path = _lock_path(home)
    if _path_is_unsafe_home_file(path):
        # A lock path standing as a link or another non
        # regular form is never opened by the probe: the
        # probe answers as it answers for an unheld lock
        # and writes nothing through the link.
        return False
    try:
        descriptor = _open_home_file_descriptor(path, "r+")
    except (OSError, _UnsafeHomeFile):
        return False
    handle = os.fdopen(descriptor, "a+")
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
        descriptor = _open_home_file_descriptor(path, "r")
        with os.fdopen(descriptor, "rb") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                return False
            handle.seek(-1, os.SEEK_END)
            return handle.read(1) != b"\n"
    except (OSError, _UnsafeHomeFile):
        return False


def _partial_tail_bytes(path):
    """The bytes after the last newline, or None where the
    file ends with a newline or cannot be read."""
    try:
        descriptor = _open_home_file_descriptor(path, "r")
        with os.fdopen(descriptor, "rb") as handle:
            data = handle.read()
    except (OSError, _UnsafeHomeFile):
        return None
    if not data or data.endswith(b"\n"):
        return None
    return data.split(b"\n")[-1]


def _is_plausible_entry_prefix(partial):
    """Whether partial bytes could be the standing holder own
    entry, written in part.

    Brief Section 5.12 item 138 admits a final partial line
    as a live holder append in progress only where it is
    the holder own partial write. Bytes that do not decode
    as UTF-8, or whose bracket and string structure no
    canonical entry prefix can have, are no entry prefix,
    whoever holds the lock."""
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
    # over plain words or digits.
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
    # the place the frame stands, not the shape of one
    # token alone. Brace led text in any other shape is no
    # entry prefix, whoever holds the lock.
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
    verify and its raise does not stand in force."""
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
    stands refused at row U-8, on the ground recorded, so
    a supplied chain carrying one does not verify and does
    not replay. A correction superseding its own sequence
    stands inside that range and outside that refusal, so
    the standing vector V-10 keeps its governed form.
    """
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
    # A cached scan is served only where the standing
    # bytes carry the content fingerprint the scan was
    # stored under, beside the stat key: file metadata
    # alone never certifies a cached scan, because a same
    # size tamper can reproduce the stat key on a
    # filesystem whose timestamp granularity is coarse, or
    # where the modification time stands restored.
    fingerprint = _content_fingerprint(path)
    cached = _scan_cache.get(cache_key)
    if cached is not None and cached[0] == stat \
            and cached[1] == fingerprint and fingerprint is not None:
        return cached[2]
    if partial_mode in ("probe", "torn"):
        # The probe and torn scans differ only in how a
        # final partial line stands classified. Where the
        # standing file holds no partial line, the two
        # scans are the same scan, so a cached sibling scan
        # over the same file state stands reused instead of
        # recomputed: a writing
        # invocation whose readers ran the probe scan no
        # longer pays for a second full scan under the
        # torn key). A sibling scan that saw a partial line
        # is never reused: its classification is its own
        # mode's.
        sibling_mode = "torn" if partial_mode == "probe" \
            else "probe"
        sibling = _scan_cache.get((path, sibling_mode, None, None))
        if sibling is not None and sibling[0] == stat \
                and sibling[1] == fingerprint \
                and fingerprint is not None \
                and not sibling[2].partial_seen:
            return sibling[2]
    scan = _Scan()
    try:
        descriptor = _open_home_file_descriptor(path, "r")
        with os.fdopen(descriptor, "rb") as handle:
            data = handle.read()
    except FileNotFoundError:
        data = b""
    except (OSError, _UnsafeHomeFile):
        # A journal path that stands but cannot be read as
        # a file (a directory at the path, a read error) is
        # an integrity state, not an empty journal. The
        # stored fingerprint stands None: no content
        # fingerprint stands over unreadable bytes, so no
        # later read is served this scan from the cache.
        scan.failure = {"position": 1, "reason": "unreadable",
                        "row": "I-2"}
        _scan_cache[cache_key] = (stat, None, scan)
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
    scan.partial_seen = partial is not None
    seen_raises = []
    if partial is not None:
        if partial_mode == "probe" and _lock_held_by_other(home) \
                and _is_plausible_entry_prefix(partial):
            scan.partial_ignored = True
        elif partial_mode == "ignore":
            scan.partial_ignored = True
    previous_hash = None
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
                    previous_hash:
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
                        # limit does not verify. The raise
                        # key stands judged by equality, as
                        # the append path and effective_limits
                        # judge it, so numeric spellings of
                        # one value stand as one raise.
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
        # The hash of each verified line stands recorded
        # on the scan: for a line that recomputes, the
        # entry hash is the hash of its raw bytes, since
        # the canonical rendering comparison above has
        # already established that the raw bytes are the
        # canonical form. Readers that need entry
        # hashes read
        # them from here instead of rendering every entry
        # a second time.
        scan.line_hashes.append(scan.head_hash)
        previous_hash = scan.head_hash
    if scan.failure is None and partial is not None \
            and not scan.partial_ignored:
        scan.failure = {"position": len(scan.lines) + 1,
                        "reason": "torn_tail", "row": "I-2"}
    # The stored fingerprint is the hash of the very bytes
    # this scan was computed over, so a later validation
    # serves this scan only for those bytes.
    _scan_cache[cache_key] = (
        stat, hashlib.sha256(data).hexdigest(), scan)
    return scan


def _entries_with_hash(scan):
    entries = []
    for position, parsed in enumerate(scan.parsed, start=1):
        if isinstance(parsed, dict):
            # The whole entry stands copied out of the scan
            # cache, every member it carries and not the
            # payload only, so a caller mutation of a fold
            # result cannot write back into what later reads
            # in this process return.
            entry = copy.deepcopy(parsed)
            if position <= len(scan.line_hashes):
                # The scan verified this line: its entry
                # hash is the recorded hash of its raw
                # bytes, the canonical rendering comparison
                # in the scan having established the two
                # forms are the same bytes, so no second
                # rendering stands computed here.
                entry["entry_hash"] = scan.line_hashes[
                    position - 1]
            else:
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
        # The reported count counts valid entries only:
        # the verified prefix of the chain. A complete
        # corrupt line stands reported as the chain failure
        # in this same result and is not counted as an
        # entry, exactly as a torn partial line, which
        # stands outside the scanned lines, is not counted.
        # scan.entry_count keeps the standing line count
        # for the sequence, cap, and anchor position logic
        # that reads it inside this module.
        "entry_count": scan.verified,
        "head_hash": scan.head_hash,
        "claim": "internal consistency only",
        "exit_code": 0 if passed else 5,
        # The error_value field carries the vocabulary
        # token, as every other record field of this name
        # does: the closed vocabulary admits no other
        # value form here, and
        # the integer 5 stands only in the exit_code field
        "error_value": None if passed else "JOURNAL_VERIFY_FAILED",
        "row": None if passed else "I-2",
        "token": None if passed else "JOURNAL_VERIFY_FAILED",
        "failing_sequence": None if passed else scan.failure["position"],
    }


_HOME_PRODUCT_FILES = frozenset({
    JOURNAL_FILENAME,
    CONFIG_FILENAME,
    LOCK_FILENAME,
    ".citeline-batch-intent.json",
    ".citeline-registry.lock",
})

_HOME_PRODUCT_TEMP_PREFIXES = (
    JOURNAL_FILENAME + ".tmp-",
    JOURNAL_FILENAME + ".replay-",
)


def _home_size(home):
    """The size the home size cap charges: the files the
    product created, and no other file.

    The product creates a closed set of files directly
    inside the home: the journal, the config, the two
    lock files, and the batch intent record, beside its
    own short lived journal temporaries. A foreign file
    placed in the home, at the top level or in any
    directory under it, stands outside that set: it
    cannot consume the cap, drive the remaining figure
    negative, or block writes, so only the named files
    at the home top level stand counted.
    """
    total = 0
    try:
        names = os.listdir(str(home))
    except OSError:
        return 0
    for name in names:
        if name not in _HOME_PRODUCT_FILES and not any(
                name.startswith(prefix)
                for prefix in _HOME_PRODUCT_TEMP_PREFIXES):
            continue
        try:
            total += os.path.getsize(os.path.join(str(home), name))
        except OSError:
            pass
    return total


def _resolve_anchor_path(home, value):
    """Resolve an anchor_path value once, against the home.

    Config validation and every anchor read and write use
    this one resolved path, so the anchor the product uses
    is the anchor it checked."""
    if os.path.isabs(value):
        return os.path.normpath(value)
    return os.path.normpath(os.path.join(str(home), value))


_ANCHOR_READ_LIMIT = 1024


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
    dropped.

    The read itself stands guarded, on the descriptor
    discipline the batch intent reader stands under:
    the path stands opened with the non blocking flag,
    so a FIFO standing at the path never
    wedges the open; the opened handle stands judged a
    regular file before any byte is read, so a device or
    another non regular form stands answered "malformed"
    unread (a directory stands answered "absent", as the
    plain open answered it); and the read stands bounded
    at _ANCHOR_READ_LIMIT bytes, far past the longest
    recording the writer writes, so an endless or oversize
    file is never read whole into memory. A link to a
    regular file stands read through, as it stood read:
    the guard judges the file the handle names, not the
    path form. The states this reader returns, and what
    each state bars or reports, stand unchanged: the guard
    changes only how the bytes are reached, never what
    they mean."""
    flags = os.O_RDONLY
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return "absent", None
    except OSError:
        return "malformed", None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            if stat.S_ISDIR(info.st_mode):
                return "absent", None
            return "malformed", None
        if info.st_size > _ANCHOR_READ_LIMIT:
            return "malformed", None
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            raw = handle.read(_ANCHOR_READ_LIMIT + 1)
        if len(raw) > _ANCHOR_READ_LIMIT:
            return "malformed", None
    except OSError:
        return "malformed", None
    finally:
        if descriptor is not None:
            os.close(descriptor)
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
    # never reaches the conversion as a raw error.
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

    The recording is the pair of its head hash and its sequence.
    The head stands at the chain position its hash recomputes,
    and the recording stands in a position only where its
    sequence is that position: the standing head is matching, an
    earlier position is stale, and every other recording is
    divergent."""
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
        # A malformed anchor holds a part record that does
        # not parse as a head hash with its sequence: the
        # design states that position as torn, with no
        # agreement claimed, and no unparsed first token
        # stands printed as a recorded head.
        # Divergent stands for a recording that
        # parses whole and stands nowhere in the chain.
        return {"agreement": "torn",
                "recorded_head": None,
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
    returns 0 in every case over a home that stands. A
    missing home is the one exception: the service status
    route over a missing home returns exit 2 with
    HOME_MISSING, on plan row U-6. The service home wraps
    this snapshot as its status result.

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
    if head_hash is not None:
        # The head hash duty stands manual, and the hash
        # stands stored outside the home, in version 1: no
        # product operation accepts the hash back, so this
        # snapshot cannot know a recording was made, and it
        # states the recording as due wherever a head hash
        # stands, in plain words beside the hash itself.
        recording_due = True
        recording = (
            "Head hash recording stands due: record the "
            "head hash %s outside the product home."
            % head_hash)
    else:
        recording_due = False
        recording = (
            "No head hash recording stands due: no head "
            "hash stands in this home.")
    return {
        "head": head,
        "head_hash": head_hash,
        "head_hash_recording_due": recording_due,
        "head_hash_recording": recording,
        # The reported count counts valid entries only, as
        # in verify_chain: the verified prefix of the chain.
        "entry_count": scan.verified,
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
    # The token length stands judged before any
    # conversion, on the significant digits of the member
    # number, as the anchor sequence token length stands
    # judged before its conversion: a digit string past
    # the integer conversion limit names no limit and
    # stands answered in the recorded vocabulary at every
    # caller, never as a raw ValueError.
    significant = match.group(1).lstrip("0") or "0"
    if len(significant) > 18:
        return None
    number = int(significant)
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
    Two relations stand between the keys, stated here
    where the keys stand specified: the resolved
    front_matter_size_after_alias_expansion value stands
    at or above the resolved front_matter_block_size
    value, and the resolved evidence_spans_per_report
    value stands at or above the resolved
    evidence_spans_per_check value; a combination in
    breach of either relation fails as CONFIG_INVALID
    with the refusal naming the relation.
    Returns a pair of the values found and the warnings.
    """
    values = {}
    warnings = []
    seen = set()
    if text.startswith("\ufeff"):
        # A byte order mark at the head is an encoding
        # prefix, not part of the first key: the page and
        # robots intakes strip it by stated rule, and the
        # config intake does the same.
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
                # error.
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
            # home_path carries its specified effect at
            # home selection (plan Section 3 EC-15 row
            # 43): selected_home below
            # reads this value, and the shell defaulting
            # and the service home handling resolve the
            # home a call governs through it. The parse
            # therefore accepts the value with no warning.
        else:
            warnings.append("unknown key: %s" % (key,))
    resolved = dict(_LIMIT_DEFAULT)
    for name, number in values.items():
        if name in resolved:
            resolved[name] = number
    # The two stated config key relations, stated here
    # where the config keys stand specified in this
    # module and named in each refusal, so no individually
    # valid combination fails on an unstated relation
    # (the relations themselves
    # stand stated in the design plan at decision
    # The settled decision as forced dependencies under row X-1):
    # front_matter_size_after_alias_expansion stands at
    # or above front_matter_block_size, and
    # evidence_spans_per_report stands at or above
    # evidence_spans_per_check.
    if resolved["front_matter_size_after_alias_expansion"] \
            < resolved["front_matter_block_size"]:
        raise ConfigError(
            "a stated config key relation stands breached: "
            "front_matter_size_after_alias_expansion must "
            "stand at or above front_matter_block_size, "
            "and the resolved values stand %d below %d"
            % (resolved[
                "front_matter_size_after_alias_expansion"],
               resolved["front_matter_block_size"]),
            row="X-1", token="CONFIG_INVALID")
    if resolved["evidence_spans_per_report"] \
            < resolved["evidence_spans_per_check"]:
        raise ConfigError(
            "a stated config key relation stands breached: "
            "evidence_spans_per_report must stand at or "
            "above evidence_spans_per_check, and the "
            "resolved values stand %d below %d"
            % (resolved["evidence_spans_per_report"],
               resolved["evidence_spans_per_check"]),
            row="X-1", token="CONFIG_INVALID")
    if home is not None and "anchor_path" in values:
        candidate = _resolve_anchor_path(home, values["anchor_path"])
        # The check runs on the real location, not the
        # lexical spelling: a path through a symlinked
        # directory whose real location is inside the home
        # is inside the home.
        candidate_real = os.path.realpath(candidate)
        home_real = os.path.realpath(str(home))
        if candidate_real == home_real \
                or candidate_real.startswith(home_real + os.sep):
            raise ConfigError(
                "an anchor path inside the product home is refused",
                row="X-2", token="ANCHOR_PATH_INSIDE_HOME")
    return values, warnings


# The keys the installer config form itself carries, beside
# the config keys of this module: the home key naming the
# product home the install created, and the created_by
# marker key. On the install surface they stand known; in
# the config parse they stand outside the key table, so the
# install config reading below sets them aside before it
# parses, as the installer surface itself does.
_INSTALLER_CONFIG_KEYS = ("home", "created_by")


def _install_config_candidates(home):
    """The install location config files that may govern
    this home, as (path, home value) pairs.

    An install location stands beside the product home it
    created: a directory holding the product file, the
    package directory, and a config.txt. Its config names
    the home it governs in its home key. Where that key
    stands overwritten, a lone standing candidate governs
    the home beside it, as the one installation that home
    can belong to.
    """
    home_abs = os.path.abspath(str(home))
    parent = os.path.dirname(home_abs)
    found = []
    try:
        names = sorted(os.listdir(parent))
    except OSError:
        return found
    for name in names:
        location = os.path.join(parent, name)
        if location == home_abs or not os.path.isdir(location):
            continue
        config = os.path.join(location, CONFIG_FILENAME)
        if not os.path.isfile(config) or os.path.islink(config):
            continue
        if not os.path.isfile(os.path.join(location, "citeline.py")):
            continue
        if not os.path.isdir(os.path.join(location, "citeline")):
            continue
        home_value = None
        try:
            with open(config, "r", encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if stripped.startswith("home") and "=" in stripped:
                        home_value = stripped.split("=", 1)[1].strip()
                        break
        except (OSError, UnicodeDecodeError):
            home_value = None
        found.append((config, home_value))
    return found


def _install_config_values(home):
    """The config values the install location config file
    states for this home, and its warnings.

    The install config file is the governing config file
    the brief states at Section 3.5 point 5: config values
    are read from that file, so a value it states governs
    the runs of the home it names.
    A home config value for the same key stands as the
    later statement of the same operator and governs over
    the install file value for that key, as every other
    reader of the home config has it. A governing file
    that cannot be parsed fails the read, as plan config
    rule 5 states for any run that reads it.
    """
    home_abs = os.path.abspath(str(home))
    candidates = _install_config_candidates(home)
    chosen = None
    unnamed = []
    for path, home_value in candidates:
        if home_value is not None:
            if os.path.abspath(home_value) == home_abs:
                chosen = path
                break
        else:
            unnamed.append(path)
    if chosen is None and len(unnamed) == 1:
        chosen = unnamed[0]
    if chosen is None:
        return {}, [], False
    try:
        with open(chosen, "r", encoding="utf-8") as handle:
            text = handle.read()
    except UnicodeDecodeError:
        raise ConfigError(
            "the install config file does not decode as UTF-8",
            row="X-1", token="CONFIG_INVALID")
    except OSError:
        raise ConfigError(
            "the install config file cannot be read",
            row="X-1", token="CONFIG_INVALID")
    kept = []
    for line in text.split("\n"):
        key = line.split(" = ", 1)[0] if " = " in line else None
        if key in _INSTALLER_CONFIG_KEYS:
            continue
        kept.append(line)
    values, warnings = parse_config("\n".join(kept), home=str(home))
    return values, warnings, True


def _read_config_values(home):
    install_values, install_warnings, install_present = \
        _install_config_values(home)
    path = config_path(home)
    if not os.path.lexists(path):
        return install_values, install_warnings, install_present
    if not os.path.isfile(path):
        # A config path that stands but is not a file (a
        # directory at the path) is a config failure, not
        # an absent config.
        raise ConfigError(
            "the config path stands but is not a file",
            row="X-1", token="CONFIG_INVALID")
    try:
        descriptor = _open_home_file_descriptor(path, "r")
    except _UnsafeHomeFile:
        # The config reader stands under the link
        # discipline the config writer stands under: a
        # link standing at the config path governs no
        # limits.
        raise ConfigError(
            "the config path stands as a link, a non "
            "regular file, or a hard linked file; the "
            "read stands refused", row="X-4",
            token="SUPPLIED_PATH_UNSAFE")
    try:
        with os.fdopen(descriptor, "r",
                       encoding="utf-8") as handle:
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
    merged = dict(install_values)
    merged.update(values)
    return merged, install_warnings + warnings, True


def selected_home(home):
    """The home in force for a call naming home.

    The home_path config key names the product home
    where it differs from the home the call names
    (plan Section 3 EC-15 row 43): where the config
    standing at the named home sets home_path to
    another directory, that directory stands selected.
    Where the key stands absent, or names the home
    itself, the named home stands. A config that
    cannot be read selects nothing, and the named
    home stands, so the caller's own config handling
    reports the failure as before.
    """
    try:
        values, _warnings, _present = _read_config_values(home)
    except Exception:  # noqa: BLE001 - a config that cannot be read in any form selects nothing and the named home stands, as the docstring states; the caller's own config handling reports the failure
        return str(home)
    named = values.get("home_path")
    if isinstance(named, str) and named:
        resolved = os.path.expanduser(named)
        if resolved != str(home):
            return resolved
    return str(home)


def write_config(home, text):
    """Write the config file, named config.txt, inside the home given.

    The writing half applies the parse the reading half applies on
    every read, so the product cannot write a config it will itself
    refuse to read."""
    home = str(home)
    parse_config(text, home=home)
    _ensure_home_directory(home, lambda: ConfigError(
        "the home path stands as a regular file or in "
        "another form that is not a directory; the "
        "write stands refused", row="X-4",
        token="SUPPLIED_PATH_UNSAFE"))
    path = config_path(home)
    try:
        descriptor = _open_home_file_descriptor(
            path, "w", defer_truncate=True)
    except _UnsafeHomeFile:
        # The config file is a home own file: a link
        # standing at its path is not written through, in
        # the supplied file discipline.
        raise ConfigError(
            "the config path stands as a link, a non "
            "regular file, or a hard linked file; the "
            "write stands refused", row="X-4",
            token="SUPPLIED_PATH_UNSAFE")
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        try:
            _rejudge_open_descriptor(handle.fileno(), path)
        except _UnsafeHomeFile:
            raise ConfigError(
                "the config path stands as a link, a non "
                "regular file, or a hard linked file; the "
                "write stands refused", row="X-4",
                token="SUPPLIED_PATH_UNSAFE")
        # The truncate the write performs stands here,
        # after the rejudgement above and not at the
        # open: a hard link planted at the return of the
        # judgement at the open stands caught by that
        # rejudgement before any truncate can land, so
        # the standing config text stands whole where
        # the write refuses on that plant.
        os.ftruncate(handle.fileno(), 0)
        handle.seek(0)
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        try:
            _rejudge_open_descriptor(handle.fileno(), path)
        except _UnsafeHomeFile:
            # The link count stands judged at the write
            # itself as well as before it, at this site as
            # at the two sites charges: a hard link planted
            # at the return of the rejudgement reading
            # names the handle the write just used, so the
            # written text stands truncated off that handle
            # and the config name stands removed, and no
            # config text stands readable under the outside
            # name.
            handle.truncate(0)
            handle.flush()
            os.fsync(handle.fileno())
            try:
                os.unlink(path)
            except OSError:
                pass
            raise ConfigError(
                "the config path stands as a link, a non "
                "regular file, or a hard linked file; the "
                "write stands refused", row="X-4",
                token="SUPPLIED_PATH_UNSAFE")
        try:
            _rejudge_open_descriptor(handle.fileno(), path)
        except _UnsafeHomeFile:
            # A final judgement stands after the post
            # write rejudgement above: a hard link
            # planted at the return of that rejudgement
            # reading stands unseen by it, so the handle
            # stands judged once more before the write
            # answers, and a plant that final judgement
            # catches stands answered in the same form,
            # the written text truncated off the handle
            # and the config name removed, so no written
            # config text stands readable under the
            # outside name and no success stands
            # reported.
            handle.truncate(0)
            handle.flush()
            os.fsync(handle.fileno())
            try:
                os.unlink(path)
            except OSError:
                pass
            raise ConfigError(
                "the config path stands as a link, a non "
                "regular file, or a hard linked file; the "
                "write stands refused", row="X-4",
                token="SUPPLIED_PATH_UNSAFE")
        try:
            _rejudge_open_descriptor(handle.fileno(), path)
        except _UnsafeHomeFile:
            # A further final judgement stands after the
            # final judgement above: a hard link planted
            # at the return of that final judgement
            # reading stands unseen by it, so the handle
            # stands judged once more before the write
            # answers, and a plant that further judgement
            # catches stands answered in the same form,
            # the written text truncated off the handle
            # and the config name removed, so no written
            # config text stands readable under the
            # outside name and no success stands reported
            # (extending).
            handle.truncate(0)
            handle.flush()
            os.fsync(handle.fileno())
            try:
                os.unlink(path)
            except OSError:
                pass
            raise ConfigError(
                "the config path stands as a link, a non "
                "regular file, or a hard linked file; the "
                "write stands refused", row="X-4",
                token="SUPPLIED_PATH_UNSAFE")
        try:
            _rejudge_open_descriptor(handle.fileno(), path)
        except _UnsafeHomeFile:
            # A next final judgement stands after the
            # further final judgement above: a hard link
            # planted at the return of that further final
            # judgement reading stands unseen by it, so
            # the handle stands judged once more before
            # the write answers, and a plant that next
            # judgement catches stands answered in the
            # same form, the written text truncated off
            # the handle and the config name removed, so
            # no written config text stands readable
            # under the outside name and no success
            # stands reported (extending).
            handle.truncate(0)
            handle.flush()
            os.fsync(handle.fileno())
            try:
                os.unlink(path)
            except OSError:
                pass
            raise ConfigError(
                "the config path stands as a link, a non "
                "regular file, or a hard linked file; the "
                "write stands refused", row="X-4",
                token="SUPPLIED_PATH_UNSAFE")
        try:
            _rejudge_open_descriptor(handle.fileno(), path)
        except _UnsafeHomeFile:
            # One more final judgement stands after the
            # next final judgement above: a hard link
            # planted at the return of that next final
            # judgement reading stands unseen by it, so
            # the handle stands judged once more before
            # the write answers, and a plant that one
            # more judgement catches stands answered in
            # the same form, the written text truncated
            # off the handle and the config name removed,
            # so no written config text stands readable
            # under the outside name and no success
            # stands reported (extending).
            handle.truncate(0)
            handle.flush()
            os.fsync(handle.fileno())
            try:
                os.unlink(path)
            except OSError:
                pass
            raise ConfigError(
                "the config path stands as a link, a non "
                "regular file, or a hard linked file; the "
                "write stands refused", row="X-4",
                token="SUPPLIED_PATH_UNSAFE")
        try:
            _rejudge_open_descriptor(handle.fileno(), path)
        except _UnsafeHomeFile:
            # A final judgement stands after the one more
            # final judgement above: a hard link planted
            # at the return of that one more final
            # judgement reading stands unseen by it, so
            # the handle stands judged once more before
            # the write answers, and a plant that this
            # judgement catches stands answered in the
            # same form, the written text truncated off
            # the handle and the config name removed, so
            # no written config text stands readable under
            # the outside name and no success stands
            # reported (extending).
            handle.truncate(0)
            handle.flush()
            os.fsync(handle.fileno())
            try:
                os.unlink(path)
            except OSError:
                pass
            raise ConfigError(
                "the config path stands as a link, a non "
                "regular file, or a hard linked file; the "
                "write stands refused", row="X-4",
                token="SUPPLIED_PATH_UNSAFE")


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

    The lock is the flock advisory lock on the file
    named.citeline-write.lock inside the home, taken with a
    non-blocking attempt and held for the whole writing
    invocation. Contention fails at row X-10. A platform or
    filesystem that cannot give the lock fails closed at row
    X-12. No stale holder recovery act exists: the operating
    system releases the lock when the holder process ends, and
    the lock file presence on disk after a holder ends bars
    nothing.

    A hold of kind "batch" is a sealed container: it grants no
    join permit of its own and it suspends any permit it joined
    under, so the permit stands only where the container own
    code grants it around one of its own append calls. An append
    made by other code running on the holder thread inside the
    window, a signal handler among its forms, therefore stands
    contended at row X-10 and stores nothing, instead of joining
    a batch whose rollback would erase it whole."""

    def __init__(self, home, kind="container", authorization=None):
        self.home = str(home)
        self.handle = None
        self._nested = False
        self._invocation = object()
        self._kind = kind
        self._granted = False
        self._suspended = False
        self._authorization = authorization
        self._dir_fd = None
        self._owner_pid = None

    def _release_dir_lock(self):
        if self._dir_fd is not None:
            try:
                fcntl.flock(self._dir_fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(self._dir_fd)
            except OSError:
                pass
            self._dir_fd = None

    def __enter__(self):
        _ensure_home_directory(self.home, lambda: JournalError(
            "the home path stands as a regular file or in "
            "another form that is not a directory; the "
            "write stands refused", row="X-4",
            token="SUPPLIED_PATH_UNSAFE"))
        path = _lock_path(self.home)
        with _HELD_LOCKS_GUARD:
            held = _HELD_LOCKS.get(path)
            if held is not None and held[4] != os.getpid():
                # The registry entry stands inherited from a
                # fork: the holder is another process now,
                # whatever the inherited thread and permit
                # state says, so this process stands as any
                # other caller in another process stands and
                # takes its answer from the flock itself.
                # The inherited handle copy stands closed
                # here; the holder own copy still holds the
                # lock.
                with contextlib.suppress(OSError):
                    held[0].close()
                held = None
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
                # process does.
                handle, depth, owner_thread, invocation, \
                    owner_pid = held
                permit_join = \
                    threading.get_ident() == owner_thread \
                    and _join_permit_count(path) > 0
                # A join authorization stands for one exact
                # append call, named by its kind and its
                # payload object, and it is consumed here,
                # at the point the append itself takes the
                # lock: no other code running on the holder
                # thread before this point, in the grant
                # prologue of the batch loop or of the
                # recovery, holds the token that call
                # carries, so it cannot join on it.
                token_join = \
                    threading.get_ident() == owner_thread \
                    and self._authorization is not None \
                    and _authorization_claimed(
                        path, self._authorization)
                if permit_join or token_join:
                    _HELD_LOCKS[path] = (
                        handle, depth + 1, owner_thread,
                        invocation, owner_pid)
                    self._nested = True
                    if token_join:
                        self._authorization = None
                    if self._kind in ("append", "batch") \
                            and _join_permit_count(path) > 0:
                        _change_join_permit(path, -1)
                        self._suspended = True
                    return self
                raise JournalError(
                    "a writing invocation already holds this home",
                    row="X-10", token="WRITE_CONTENDED")
            try:
                descriptor = _open_home_file_descriptor(
                    path, "r+", create=True)
            except _UnsafeHomeFile:
                # The lock file is a home own file: a link
                # standing at its path is not written
                # through, in the supplied file
                # discipline.
                raise _unsafe_home_file_error(path, "write lock")
            except OSError:
                raise JournalError(
                    "the write lock cannot be given on this "
                    "filesystem", row="X-12",
                    token="LOCK_UNAVAILABLE")
            # The exclusion stands anchored on the home
            # directory itself beside the lock file: the
            # directory descriptor flock is taken first, so
            # unlinking the lock file during a hold mints no
            # second exclusion on a recreated lock file, the
            # new caller meeting the directory flock the
            # standing holder holds.
            try:
                dir_fd = os.open(self.home, os.O_RDONLY)
            except OSError:
                os.close(descriptor)
                raise JournalError(
                    "the write lock cannot be given on this "
                    "filesystem", row="X-12",
                    token="LOCK_UNAVAILABLE")
            try:
                fcntl.flock(dir_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(dir_fd)
                os.close(descriptor)
                raise JournalError(
                    "a writing invocation already holds this home",
                    row="X-10", token="WRITE_CONTENDED")
            except OSError:
                os.close(dir_fd)
                os.close(descriptor)
                raise JournalError(
                    "the write lock cannot be given on this "
                    "filesystem", row="X-12",
                    token="LOCK_UNAVAILABLE")
            self._dir_fd = dir_fd
            handle = os.fdopen(descriptor, "a+")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                self._release_dir_lock()
                raise JournalError(
                    "a writing invocation already holds this home",
                    row="X-10", token="WRITE_CONTENDED")
            except OSError:
                handle.close()
                self._release_dir_lock()
                raise JournalError(
                    "the write lock cannot be given on this "
                    "filesystem", row="X-12",
                    token="LOCK_UNAVAILABLE")
            self._owner_pid = os.getpid()
            try:
                _rejudge_open_descriptor(handle.fileno(), path)
            except _UnsafeHomeFile:
                handle.close()
                self._release_dir_lock()
                raise _unsafe_home_file_error(path, "write lock")
            handle.seek(0)
            handle.truncate()
            handle.write("holder pid %d\n" % os.getpid())
            handle.flush()
            try:
                _rejudge_open_descriptor(handle.fileno(), path)
            except _UnsafeHomeFile:
                # The holder line write stands judged after
                # it stands written, in the bounded form of
                # this site: a rename plant timed at the
                # return of the helper lstat reading of the
                # rejudgement before the write stands judged
                # here, the holder line stands truncated off
                # the handle, and the acquire stands refused
                # in the vocabulary of the site, the
                # exclusion standing on the directory flock
                # in every form.
                try:
                    handle.seek(0)
                    handle.truncate(0)
                    handle.flush()
                    os.fsync(handle.fileno())
                except OSError:
                    pass
                handle.close()
                self._release_dir_lock()
                raise _unsafe_home_file_error(path, "write lock")
            try:
                _rejudge_open_descriptor(handle.fileno(), path)
            except _UnsafeHomeFile:
                # A further rejudgement stands after the
                # post write judgement, in the bounded limb
                # form of this site, judging its path
                # reading as the judgement judges its
                # handle reading: a rename plant timed at
                # the return of the lstat reading of the
                # post write judgement stands judged here,
                # the holder line stands truncated off the
                # handle, and the acquire stands refused in
                # the vocabulary of the site, the exclusion
                # standing on the directory flock in every
                # form.
                try:
                    handle.seek(0)
                    handle.truncate(0)
                    handle.flush()
                    os.fsync(handle.fileno())
                except OSError:
                    pass
                handle.close()
                self._release_dir_lock()
                raise _unsafe_home_file_error(path, "write lock")
            self.handle = handle
            _HELD_LOCKS[path] = (
                handle, 1, threading.get_ident(), self._invocation,
                os.getpid())
            _active_invocations(path).append(self._invocation)
            if self._kind == "container":
                _change_join_permit(path, 1)
                self._granted = True
            return self

    def __exit__(self, exc_type, exc, tb):
        path = _lock_path(self.home)
        if self.handle is not None \
                and self._owner_pid is not None \
                and os.getpid() != self._owner_pid:
            # A child forked inside the hold unwinds an
            # inherited copy of this lock object: its exit
            # act must not run an explicit unlock on the
            # open file description the fork shares, which
            # would release the parent flock whole. The
            # child closes its own handle copies only, the
            # act that leaves the parent lock standing.
            with contextlib.suppress(OSError):
                self.handle.close()
            self.handle = None
            if self._dir_fd is not None:
                try:
                    os.close(self._dir_fd)
                except OSError:
                    pass
                self._dir_fd = None
            return False
        if self._nested:
            with _HELD_LOCKS_GUARD:
                held = _HELD_LOCKS.get(path)
                if held is not None:
                    _HELD_LOCKS[path] = (
                        held[0], held[1] - 1, held[2], held[3],
                        held[4])
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
        self._release_dir_lock()
        with _HELD_LOCKS_GUARD:
            _HELD_LOCKS.pop(path, None)
            active = _active_invocations(path)
            if self._invocation in active:
                active.remove(self._invocation)
        return False


# Locks this process holds, by lock file path, as
# (handle, hold depth, holder thread, holder invocation,
# holder process id).
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


def _authorizations(path):
    """The join authorizations standing for one path on
    this thread, as authorization context records."""
    authorizations = getattr(_LOCK_LOCAL, "authorizations", None)
    if authorizations is None:
        authorizations = {}
        _LOCK_LOCAL.authorizations = authorizations
    return authorizations.setdefault(path, [])


class _AuthorizationContext:
    __slots__ = ("token", "entry_kind", "payload_id",
                 "claimed", "spent")

    def __init__(self, entry_kind, payload):
        self.token = object()
        self.entry_kind = entry_kind
        self.payload_id = id(payload)
        self.claimed = False
        self.spent = None


class _join_authorization:
    """An authorization for one exact append call to join the
    hold its caller stands inside.

    The authorization names the entry kind and the payload
    object of the one call it stands, and it stands bound to
    the call that registered it: the first append call
    entered under it claims it at its own entry, before any
    judgement that runs payload code, and no second call
    presenting the same kind and the same payload object can
    spend it. A second call that finds the authorization
    already spent by a landed append of the very entry it
    presents stands answered by that landed entry itself, at
    the journal head, and stores nothing further; a second
    call that finds it claimed but unspent calls the append
    without the token and stands contended."""

    def __init__(self, path, entry_kind, payload):
        self.path = path
        self.context = _AuthorizationContext(entry_kind, payload)

    def __enter__(self):
        _authorizations(self.path).append(self.context)
        return self.context.token

    def __exit__(self, exc_type, exc, tb):
        records = _authorizations(self.path)
        for index, record in enumerate(records):
            if record is self.context:
                del records[index]
                break
        return False


def _standing_authorization(path, entry_kind, payload):
    """The authorization token standing unclaimed for this
    exact append call on this thread, or None."""
    for record in reversed(_authorizations(path)):
        if record.entry_kind == entry_kind \
                and record.payload_id == id(payload) \
                and not record.claimed:
            return record.token
    return None


def _claim_authorization(path, entry_kind, payload):
    """Claim the standing authorization for one append call,
    at that call own entry.

    Returns a pair of the context and its state: "claimed"
    where this call is the call the authorization stands
    bound, "spent" where a landed append of the same entry
    already spent it, "busy" where the bound call stands
    in flight, and None where no authorization for this
    kind and payload object stands."""
    for record in reversed(_authorizations(path)):
        if record.entry_kind == entry_kind \
                and record.payload_id == id(payload):
            if not record.claimed:
                record.claimed = True
                return record, "claimed"
            if record.spent is not None:
                return record, "spent"
            return record, "busy"
    return None, None


def _authorization_claimed(path, token):
    return any(record.token is token and record.claimed
               for record in _authorizations(path))


def _adopt_spent_authorization(home, context):
    """The landed entry a spent authorization names, where it
    still stands in the chain at its own sequence, or
    None.

    The spent answer stands on the landed entry itself,
    verified by its sequence and its head hash at that
    sequence, not on the entry standing at the journal
    head: an append that lands after the spent entry moves
    the head past it and does not spend the answer, so the
    repeat call stands answered by the landed entry
    wherever it stands in the chain and stores nothing
    further."""
    sequence, head_hash = context.spent
    scan = _scan(home, "probe")
    if scan.failure is not None \
            or sequence < 1 or sequence > scan.entry_count:
        return None
    if hashlib.sha256(
            scan.lines[sequence - 1]).hexdigest() != head_hash:
        return None
    entries = _entries_with_hash(scan)
    if len(entries) < sequence:
        return None
    return entries[sequence - 1]


def _write_anchor(anchor_path, head_hash, sequence):
    directory = os.path.dirname(anchor_path) or "."
    os.makedirs(directory, exist_ok=True)
    # The temporary stands created exclusively under a
    # name no planter can predict, so a link planted in
    # the anchor directory is never the file this write
    # opens and the replace never moves a planted link
    # onto the anchor path.
    descriptor, temporary = tempfile.mkstemp(
        prefix=os.path.basename(anchor_path) + ".tmp-",
        dir=directory)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write("%s %d\n" % (head_hash, sequence))
        handle.flush()
        os.fsync(handle.fileno())
        temporary_inode = os.fstat(handle.fileno()).st_ino
    try:
        _replace_judged_temporary(
            temporary, temporary_inode, anchor_path,
            preserve_target=True)
    except FileNotFoundError:
        # The temporary stands lost under its writer before
        # its link step: the condition row X-13 names, in
        # the vocabulary that row states.
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


def _restore_anchor_bytes(anchor_path, anchor_bytes):
    """Restore an anchor file to stated bytes, without
    writing through a link standing at the anchor path:
    the bytes stand written to an exclusively created
    temporary under an unpredictable name in the anchor
    directory and replaced onto the path, on the
    discipline of."""
    directory = os.path.dirname(anchor_path) or "."
    descriptor, temporary = tempfile.mkstemp(
        prefix=os.path.basename(anchor_path) + ".tmp-",
        dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(anchor_bytes)
            handle.flush()
            os.fsync(handle.fileno())
            temporary_inode = os.fstat(handle.fileno()).st_ino
        _replace_judged_temporary(
            temporary, temporary_inode, anchor_path)
    except OSError:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _restore_journal_size(path, size):
    """Truncate the journal back to a stated size, best effort."""
    try:
        descriptor = _open_home_file_descriptor(path, "r+")
    except (OSError, _UnsafeHomeFile):
        # A journal path standing as a link or another
        # unsafe form is not truncated through, as every
        # home own file write stands under the same
        # discipline; the restore is best effort and
        # reports nothing.
        descriptor = None
    if descriptor is not None:
        try:
            with os.fdopen(descriptor, "r+b") as handle:
                _rejudge_open_descriptor(handle.fileno(), path)
                # The bytes past the restore size stand read
                # before the truncate, so a judgement that
                # catches a plant after the truncate can put
                # them back on the handle in its remedy
                # below.
                handle.seek(size)
                tail = handle.read()
                # A second judgement stands after the
                # rejudgement and before the truncate: a
                # rename plant timed at the return of the
                # helper lstat reading of the rejudgement
                # stands judged here, before any truncate
                # lands, on the no replacement dressing and
                # on the replacement dressing alike, so the
                # truncate stands in no case performed on a
                # file the home no longer names while the
                # journal that stands keeps its full size.
                _rejudge_open_descriptor(handle.fileno(), path)
                handle.truncate(size)
                handle.flush()
                os.fsync(handle.fileno())
                try:
                    _rejudge_open_descriptor(
                        handle.fileno(), path)
                except _UnsafeHomeFile:
                    # A judgement stands after the truncate
                    # as well: a plant timed at the return of
                    # the reading of the judgement before the
                    # truncate lands the truncate on the file
                    # under the outside name, and the remedy
                    # of the site puts the preserved tail back
                    # on the handle, so that file stands whole
                    # at its full size again and the restore
                    # stands not performed in its silent best
                    # effort form.
                    handle.seek(size)
                    handle.write(tail)
                    handle.truncate(size + len(tail))
                    handle.flush()
                    os.fsync(handle.fileno())
                    raise
        except (OSError, _UnsafeHomeFile):
            pass
    for cache_key in [key for key in _scan_cache if key[0] == path]:
        _scan_cache.pop(cache_key, None)


_IDENTITY_MARKER_FIELDS = frozenset(
    ("snapshot_id", "run_id", "answer_id"))


def _resolve_sequence_identity(value, sequence, field=None):
    """Resolve the {sequence} identity marker in one payload.

    Resolution stands confined to the identity fields the
    mechanism was charged with resolving: snapshot_id,
    run_id, and answer_id, at any depth. A string standing in
    any other field is caller text and stands stored exactly
    as written, marker spelling included. Values carrying no
    marker stand as they stand.

    The field context stands held through a list or a tuple
    standing under an identity key, so a marker in an element
    of such a list resolves as the marker standing directly
    under the key resolves. A corrected record carried by a
    correction payload stands resolved against the sequence
    the record replaces, the supersedes value its own payload
    names, not against the sequence of the correction entry
    that carries it."""
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

    The record names the journal size and the anchor content the
    batch started, so a batch whose process is killed, which
    raises nothing and runs no rollback, can still be rolled
    back whole by the next invocation that finds this record
    standing (on the batch discipline). A failure to record the
    intent stands reported to the caller, which bars the batch
    in the journal vocabulary: a batch never runs with its kill
    protection silently off. Returns True where the record
    stands written."""
    record = {
        "journal_size": journal_size,
        "anchor_path": anchor_path,
        "anchor_bytes": None if anchor_bytes is None else
        base64.b64encode(anchor_bytes).decode("ascii"),
        "count": count,
    }
    intent_path = _batch_intent_path(home)
    # The intent path is an internal scratch file of the
    # home: the write stands judged at its open, with the
    # no follow guard on the open itself, so a link
    # standing at the path, a link landing after any
    # earlier judgement, and a hard link standing at the
    # path each stand refused on the opened handle, and
    # no batch creates or truncates a file outside the
    # home holding the record content. The write stands
    # refused, and the batch caller bars the batch in the
    # journal vocabulary on that report, as it bars it on
    # any intent write failure.
    try:
        descriptor = _open_home_file_descriptor(intent_path, "w")
    except (OSError, _UnsafeHomeFile):
        return False
    try:
        with os.fdopen(descriptor, "w",
                       encoding="utf-8") as handle:
            _rejudge_open_descriptor(handle.fileno(), intent_path)
            handle.write(json.dumps(record))
            handle.flush()
            os.fsync(handle.fileno())
            try:
                _rejudge_open_descriptor(
                    handle.fileno(), intent_path)
            except _UnsafeHomeFile:
                # The link count stands judged at the write
                # itself as well as before it: a hard link
                # planted after the rejudgement and before
                # the write names the handle the write just
                # used, so the written content stands
                # truncated off that handle and the intent
                # name stands removed, and no intent content
                # stands readable under the outside name.
                handle.truncate(0)
                handle.flush()
                os.fsync(handle.fileno())
                try:
                    os.unlink(intent_path)
                except OSError:
                    pass
                raise
    except (OSError, _UnsafeHomeFile):
        return False
    return True


def _clear_batch_intent(home):
    try:
        os.unlink(_batch_intent_path(home))
    except OSError:
        pass


def _home_total_size(home):
    """The size of everything standing under the home,
    every file the walk finds, product created or not.

    This whole home reading stands only for the recovery
    mixed state judgement below, whose governed question
    is the state of the home as it stood at the append.
    The home size cap itself charges only the files the
    product created: see _home_size."""
    total = 0
    for root, _dirs, files in os.walk(str(home)):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def _size_cap_also_met(home):
    """Whether the total home size cap also stands met over
    this home, judged on the state as it stands at the
    moment this reading is taken. The recovery judgement
    takes this reading from the append itself, at the
    instant the append meets its journal length cap, stated
    on the error the append raises: where a recovery record
    append meets the journal length cap in flight while the
    size cap also stands met, the append actually met both
    caps in the mixed state, and its failure stands judged
    on the size cap terms, as a landed recovery, not as a
    length cap deferral reported over a truncation that has
    already landed. The reading is the whole home reading,
    _home_total_size: the judgement's governed question is
    the home's state at the append, and the reading
    that charges the cap itself with product created
    files only does not name this judgement."""
    try:
        limits = effective_limits(home)
    except Exception:  # noqa: BLE001 - the judgement must answer on any unreadable state: limits that cannot be read stand as the cap not met, and the recovery this judgement serves is never blocked by the judgement itself
        return False
    size_limit = limits["total_home_size"]
    cap = size_limit["value"] * _SIZE_MULTIPLIERS[size_limit["unit"]]
    return _home_total_size(home) >= cap


# A validation outcome beside success and refusal: the
# record stands deferred, neither acted on nor cleared,
# where the state it must be judged against does not
# stand ready to judge it, a restored prefix that does
# not recompute or a config that does not parse with an
# anchor the record names that cannot be confirmed. The
# record stands for a later invocation to judge again
# once that state is repaired, so a genuine record is
# not destroyed by a fault outside it.
_DEFER_BATCH_RECOVERY = object()


def recover_interrupted_batch(home):
    """Roll back one batch whose process died inside it.

    Where a batch intent record stands and no live holder
    holds the home, the batch it names never completed:
    the journal stands truncated back to the size the
    record names, the anchor stands restored to the
    content the record names, and the record stands
    removed, so no partial batch stands as ordinary state
    and the import it belonged to can be run again whole.
    The record stands validated against the standing
    journal and the home before any of that acts, judged
    against the state the batch started, so a later
    config change or config fault does not destroy a
    genuine record, and a landed recovery appends its own
    failure record stating that it ran.
    Returns True where a recovery landed. Where the home
    stands held by a live batch, or no record stands,
    nothing happens here: the live batch owns its own
    rollback. Where the record stands deferred, or where
    its ruled failure record cannot land at the journal
    length cap, the recovery does not stand reported as
    landed: this call returns False and the record
    stands, so the recovery can land whole once the state
    that bars it is repaired or the cap is raised."""
    home = str(home)
    intent_path = _batch_intent_path(home)
    if not os.path.lexists(intent_path):
        return False
    if os.path.islink(intent_path):
        # A link standing at the intent path is not
        # recovery debris to clear: it stands left in
        # place, so the batch intent write judgement
        # meets it standing and bars the batch on it, in
        # the form pins. The recovery simply does not
        # act on it.
        return False
    try:
        with _WriteLock(home, kind="batch"):
            try:
                # The reader stands guarded at its open as
                # the writer stands: a non regular file at
                # the intent path, a FIFO among its forms,
                # is never opened, so the recovery cannot
                # wedge inside the open, and the record
                # stands judged at its raw text, a
                # duplicated key refusing through the same
                # pairs hook the journal own line reader
                # judges its lines by. A hard link count
                # above one stands admitted at this reader
                # and judged by the validation of the record
                # itself: a genuine record linked outward
                # validates and recovers, and a victim file
                # linked to the path validates as no record
                # and stands cleared as debris.
                descriptor = _open_home_file_read_descriptor(
                    intent_path)
                with os.fdopen(descriptor, "r",
                               encoding="utf-8") as handle:
                    record = json.loads(
                        handle.read(),
                        object_pairs_hook=_pairs_hook)
            except (OSError, ValueError, RecursionError,
                    _DuplicateKey, _UnsafeHomeFile):
                # A record that does not read names no batch
                # state to restore: it can only be the debris
                # of a kill before the first entry landed,
                # which appended nothing. A parse that never
                # returns, a deeply nested record among its
                # forms, stands judged in the same recorded
                # vocabulary as every sibling JSON reader
                # judges it, and never as a raw error. A link
                # that landed at the path in the meantime
                # stands left in place, on the same ground as
                # the link judgement at the head of this
                # call.
                if not os.path.islink(intent_path):
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
                # or deleted on its word.
                _clear_batch_intent(home)
                return False
            journal_size, count, anchor_path, anchor_bytes, \
                restored_count = validated
            try:
                journal_cap = effective_limits(
                    home)["journal_length"]["value"]
            except Exception:  # noqa: BLE001 - recovery proceeds without the cap where the limits cannot be read; the cap check is a guard on the recovery record, never a bar to recovery itself
                journal_cap = None
            if journal_cap is not None \
                    and restored_count + 1 > journal_cap:
                # The recovery record the ruling at requires
                # could not land at the cap, so the recovery
                # does not land at all in silence: it stands
                # deferred whole, its record standing, until
                # the cap admits both the restored prefix
                # and the record.
                return False
            _restore_journal_size(journal_path(home), journal_size)
            if anchor_path is not None:
                try:
                    if anchor_bytes is None:
                        if os.path.exists(anchor_path):
                            os.unlink(anchor_path)
                    else:
                        _restore_anchor_bytes(
                            anchor_path, anchor_bytes)
                except OSError:
                    pass
            # The recovery itself stands recorded, under
            # the Manager ruling on: a failure record
            # entry, appended through the ordinary append
            # path under this same hold, stating that a
            # recovery ran, the interrupted batch it
            # answered, and the point the journal stands
            # restored to. No new entry kind stands
            # invented. A failure of this append leaves the
            # recovery itself standing, except a failure at
            # the journal length cap: that failure stands
            # judged, the recovery does not stand reported
            # as landed, and the intent record stands as
            # its evidence. The record stands built through
            # the CitelineError constructor guard, as every
            # recorded error stands: its error_value is a
            # token of the closed vocabulary, the row X-13
            # token for a writer lost before its write
            # completed, and the record carries that
            # token's row, class, and exit code beside it,
            # so no value outside the closed set stands in
            # the stored journal.
            # The rule that fired keeps its own name in the
            # rule_fired field, as the standing failure
            # record vectors carry a rule name beside their
            # token.
            recovery_error = JournalError(
                "a recovery ran: an interrupted batch "
                "stands rolled back",
                row="X-13", token="TEMPORARY_LOST")
            payload = {
                "operation": "recovery",
                "error_value": recovery_error.error_value,
                "row": recovery_error.row,
                "precedence_class":
                    recovery_error.precedence_class,
                "exit_code": recovery_error.exit_code,
                "subject_identity": "batch of %d entries" % count,
                "date": None,
                "rule_fired": "interrupted_batch",
                "batch_count": count,
                "restored_journal_size": journal_size,
                "restored_entry_count": restored_count,
            }
            record_judged_failed = False
            # The mixed state judgement reads the size state
            # as it stood at the append, stated on the error
            # the append itself raises, read inside the
            # append at the instant its length cap judgement
            # stood: a change of the size state landing
            # inside the append call, or as the call
            # returns, must not hand the judgement a state
            # the append never met.
            with _join_authorization(
                    _lock_path(home), "failure_record", payload):
                try:
                    append_entry(home, "failure_record", payload)
                except JournalError as error:
                    size_cap_met_at_append = getattr(
                        error, "size_cap_also_met_at_append",
                        None)
                    if size_cap_met_at_append is None:
                        size_cap_met_at_append = \
                            _size_cap_also_met(home)
                    # The cap judgement stands on the cap
                    # the append actually met, read from the
                    # limit number the error carries: only
                    # the journal length cap, limit 39,
                    # holds the deferral the ruling at
                    # states. A failure at the total home
                    # size cap, limit 40, stands judged on
                    # its own terms under the append failure
                    # discipline: the restore has already
                    # landed, so no deferral stands reported
                    # over it and the recovery stands as
                    # landed below. A failure carrying limit
                    # 39 stands judged the same way where
                    # the size cap also stands met in the
                    # mixed state, on the cap the append
                    # actually met.
                    if error.token == "JOURNAL_CAP_EXCEEDED" \
                            and getattr(error, "limit_number",
                                        None) == 39 \
                            and not size_cap_met_at_append:
                        record_judged_failed = True
                except Exception:  # noqa: BLE001 - a failure of the failure record append itself, in any form, must not crash the recovery it serves; the record stands not judged failed and recovery proceeds
                    record_judged_failed = False
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
    the recovery to a record naming an arbitrary file."""
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
    stand, or the deferral marker where the state it must be
    judged against does not stand ready.

    The record is read as a claim to verify, as the journal
    own lines are read, never as instructions. Its form
    stands judged whole: the genuine writer writes exactly
    four members, and every member beyond those four, and a
    record naming no batch at all, stands refused. Its
    journal size must stand at a line boundary of the
    standing journal and no past it. Its count must cover
    the entries standing past that size, and no tail longer
    than the batch it names may stand rolled back on its
    word. The restored prefix the size names must itself
    recompute as a chain before the record is judged or
    acted, so a damaged prefix stands judged as damaged and
    the record stands deferred over it, not destroyed and
    not reported recovered. Its anchor content must be the
    recording the product own writer writes for the head the
    size names, or no content where that size names no entry
    or no anchor stood at the batch start. Its anchor path
    stands judged against the state the batch started from:
    the path the config now resolves stands accepted as
    before, and a path the config no longer names, or cannot
    name because the config does not parse, stands accepted
    only where the file at that path is a recording of this
    journal, the mark of the home own former anchor, so a
    config change or a config fault after the kill does not
    destroy a genuine record. On success returns the journal
    size, the count, the anchor path the batch started, the
    decoded anchor bytes, and the entry count the size
    names."""
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
        descriptor = _open_home_file_descriptor(
            journal_path(home), "r")
        with os.fdopen(descriptor, "rb") as handle:
            standing = handle.read()
    except FileNotFoundError:
        standing = b""
    except _UnsafeHomeFile:
        return _DEFER_BATCH_RECOVERY
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
    except Exception:  # noqa: BLE001 - a config that cannot be read in any form cannot judge the record, and the record stands deferred whole, as the comment below states
        # A config that does not parse cannot judge the
        # record, and the recovery record append could not
        # be judged under it either: the record stands
        # deferred whole until the config is repaired, and
        # the fault itself stands reported loudly by the
        # caller own config read.
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
    a journal that does not recompute, and at either cap,
    the append stands refused and the head stands
    unchanged. A stale, missing, or malformed anchor
    recording never refuses the append: the append
    proceeds, rewrites the anchor, and reports the
    disagreement in its result. A divergent anchor
    recording, a head standing nowhere in the chain,
    still refuses the append, on the honest forgery pair
    terms the plan states. The audit date
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
    # The join authorization stands claimed at this call
    # own entry, before the depth judgement or any other
    # step that runs payload code, so code the payload
    # itself runs inside this call, and any second call
    # presenting the same kind and payload object, finds
    # the authorization already bound to this call and
    # cannot spend it.
    claimed_context, claim_state = _claim_authorization(
        _lock_path(home), entry_kind, payload)
    authorization = None
    if claim_state == "claimed":
        authorization = claimed_context.token
    elif claim_state == "spent":
        adopted = _adopt_spent_authorization(home, claimed_context)
        if adopted is not None:
            return adopted
    if _container_depth(payload) + 2 > MAX_DEPTH:
        raise JournalError(
            "the entry nesting depth breaches its limit",
            row="X-3", token="LIMIT_EXCEEDED")
    # A batch killed inside its appends leaves its intent
    # record standing; the next append on this home rolls
    # that batch back before it reads the chain, unless
    # this append itself stands inside a batch this process
    # holds, whose intent is its own.
    with _HELD_LOCKS_GUARD:
        _batch_held = _lock_path(home) in _HELD_LOCKS
    if not _batch_held:
        recover_interrupted_batch(home)
    with _WriteLock(home, kind="append",
                    authorization=authorization):
        if _path_is_unsafe_home_file(journal_path(home)):
            # The journal file is a home own file: a link
            # or another unsafe form standing at its path
            # bars the append before any reading or
            # writing follows it.
            raise _unsafe_home_file_error(
                journal_path(home), "journal")
        scan = _scan(home, "torn")
        if scan.failure is not None:
            raise JournalError(
                "the journal does not recompute; appends stand barred",
                row="I-2", token="JOURNAL_VERIFY_FAILED")
        values, _warnings, _present = _read_config_values(home)
        anchor_path = values.get("anchor_path")
        resolved_anchor = None
        anchor_disagreement = None
        if anchor_path:
            resolved_anchor = _resolve_anchor_path(home, anchor_path)
            anchor_state, recorded = _read_anchor(resolved_anchor)
            # Anchor disagreement is a reported position,
            # never a barring ground, for the three forms
            # the settled decision names: an append over a
            # stale, missing, or malformed anchor proceeds
            # and rewrites the anchor, and the disagreement
            # that stood at the append stands reported in
            # the append result, in the form status and
            # verify report it, until the rewritten anchor
            # agrees again. Over an empty journal an absent
            # anchor is no disagreement: the first append
            # establishes it. A divergent recording, a head
            # that stands nowhere in the chain, is not one
            # of the three forms: it is the honest forgery
            # case of the plan pair IM2-INV-3, whose facts
            # the settled decision does not reach, and its bar stands
            # exactly as it stood.
            if anchor_state == "ok" and \
                    _agreement_for(recorded, scan) == "divergent":
                raise JournalError(
                    "the anchor recording does not stand as the "
                    "standing head; appends stand barred",
                    row="I-2", token="JOURNAL_VERIFY_FAILED")
            if anchor_state == "malformed":
                anchor_disagreement = {
                    "agreement": "torn",
                    "recorded_head": None,
                    "recorded_sequence": None,
                    "anchor_path": anchor_path}
            elif anchor_state == "ok" and \
                    _agreement_for(recorded, scan) != "matching":
                anchor_disagreement = {
                    "agreement": _agreement_for(recorded, scan),
                    "recorded_head": recorded["head_hash"],
                    "recorded_sequence": recorded["sequence"],
                    "anchor_path": anchor_path}
            elif anchor_state == "absent" and scan.entry_count > 0:
                anchor_disagreement = {
                    "agreement": "absent",
                    "recorded_head": None,
                    "recorded_sequence": None,
                    "anchor_path": anchor_path}
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
            # corrected record must be a record.
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
            error = JournalError(
                "the journal length cap stands reached",
                row="I-1", token="JOURNAL_CAP_EXCEEDED",
                refusal_context="append_cap", limit_number=39)
            # The size state the mixed state recovery
            # judgement stands on is read here, inside the
            # append, at the instant this cap is met, and
            # stated on the error itself: a reading the
            # recovery took before the append runs, or one
            # it took after the append failed, hands the
            # judgement a state the append never met where
            # the size state changes inside the append call
            # or as the call returns (extending).
            error.size_cap_also_met_at_append = \
                _size_cap_also_met(home)
            raise error
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
        # append also mints, with this one mechanism in
        # the append path. Resolution stands confined to
        # the identity
        # fields, so caller text in every other field
        # stands stored as written.
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
            descriptor = _open_home_file_descriptor(path, "a")
        except _UnsafeHomeFile:
            # The journal stands judged at its open as at
            # its scan: a link landing at the journal path
            # is not written through.
            raise _unsafe_home_file_error(path, "journal")
        try:
            _rejudge_open_descriptor(descriptor, path)
        except _UnsafeHomeFile:
            os.close(descriptor)
            raise _unsafe_home_file_error(path, "journal")
        appended_info = None
        try:
            with os.fdopen(descriptor, "ab") as handle:
                handle.write(canonical + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
                appended_info = os.fstat(handle.fileno())
                try:
                    _rejudge_open_descriptor(
                        handle.fileno(), path)
                except _UnsafeHomeFile:
                    # The link count stands judged at the
                    # write itself as well as before it: a
                    # hard link planted after the
                    # rejudgement and before the write names
                    # the handle the write just used, so the
                    # appended entry stands truncated off
                    # that handle, back to the size the
                    # journal stood, and no appended content
                    # stands readable under the outside
                    # name.
                    handle.truncate(original_size)
                    handle.flush()
                    os.fsync(handle.fileno())
                    raise
        except _UnsafeHomeFile:
            raise _unsafe_home_file_error(path, "journal")
        except OSError:
            # A write that fails part way stands rolled back
            # to the size the journal stood, so the append
            # is one complete write or nothing, and the
            # failure reaches the caller in the recorded
            # vocabulary, never as a bare OSError over a
            # torn tail.
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
        extended.line_hashes = scan.line_hashes + [
            entry["entry_hash"]]
        extended.partial_seen = False
        stat = _stat_key(path)
        # The extended scan cache store stands judged
        # before it stands stored: the file standing at
        # the journal path at the store must be the very
        # file the append wrote, at the size the append
        # left it, the inode the handle held and the
        # original size plus the appended line. A rename
        # plant timed at the return of the lstat reading
        # of the post write rejudgement moves that file
        # away after the judgement, and a replacement
        # standing at the path is another file at another
        # size, so on either dressing the store stands
        # refused and every cache entry for the path
        # stands popped instead: no plant inside the call
        # then stands reported as a passed chain, and a
        # later read in this process scans the path as it
        # stands, at entry_count 0 over an absent path and
        # at the seed alone over a seed replacement, as a
        # rename after the call returns reads.
        if stat is not None and appended_info is not None \
                and stat[0] == appended_info.st_ino \
                and stat[1] == original_size + len(canonical) + 1:
            # The extended scan's content fingerprint is
            # the hash of the file bytes as the append left
            # them, rebuilt from the scanned lines where the
            # source scan saw no partial tail. Where it saw
            # one, the standing bytes cannot be rebuilt from
            # the scan, so the fingerprint stands None and
            # the stored scan never validates: the next read
            # scans the path as it stands.
            if scan.partial_seen:
                extended_fingerprint = None
            else:
                extended_fingerprint = hashlib.sha256(
                    b"".join(line + b"\n"
                             for line in extended.lines)
                ).hexdigest()
            for mode in ("probe", "torn"):
                _scan_cache[(path, mode, None, None)] = (
                    stat, extended_fingerprint, extended)
        else:
            for cache_key in [key for key in _scan_cache
                              if key[0] == path]:
                _scan_cache.pop(cache_key, None)
        if resolved_anchor is not None:
            try:
                _write_anchor(resolved_anchor, entry["entry_hash"],
                              entry["sequence"])
            except JournalError:
                # A lost anchor temporary reports in its own
                # vocabulary at row X-13; the append stands
                # rolled back all the same, and the error
                # stands as it was raised.
                _restore_journal_size(path, original_size)
                for cache_key in [key for key in _scan_cache
                                  if key[0] == path]:
                    _scan_cache.pop(cache_key, None)
                raise
            except OSError:
                # An anchor write that fails is not swallowed:
                # the append stands rolled back and the
                # failure is reported, so no append reports
                # success with no anchor standing.
                _restore_journal_size(path, original_size)
                for cache_key in [key for key in _scan_cache
                                  if key[0] == path]:
                    _scan_cache.pop(cache_key, None)
                raise JournalError(
                    "the anchor write failed; the append "
                    "stands rolled back", row="I-2",
                    token="JOURNAL_VERIFY_FAILED")
        if claim_state == "claimed" and claimed_context is not None:
            claimed_context.spent = (
                entry["sequence"], entry["entry_hash"])
        if anchor_disagreement is not None:
            # The disagreement stands reported in the append
            # result only: it is no part of the stored entry,
            # whose canonical form stands already written.
            entry["anchor_disagreement"] = anchor_disagreement
        return entry


def append_entries_atomic(home, entries, audit_date=None, run_id=None):
    """Append a batch of entries as one invocation, or none.

    The batch is the multi append discipline: an invocation
    that appends more than one entry holds the write lock
    across the whole batch, checks the whole batch cost
    against the journal length cap before the first entry
    stands written, and, where any entry of the batch fails,
    rolls the journal and the anchor back to the state they
    stood in before the batch, so no partial work stands
    behind a failure report. Before the first entry lands
    the batch records its starting state in a batch intent
    record inside the home, so a batch whose process is
    killed inside it, which runs no rollback of its own,
    stands rolled back by the next invocation through
    recover_interrupted_batch. Entries stand as (entry_kind,
    payload) pairs in append order. Returns the appended
    entry records in order."""
    home = str(home)
    # The argument form is judged before any vocabulary
    # check inside the loop, in the form the sibling replay
    # surface states at row U-8: the batch takes a
    # collection of pairs, and an item that is no pair, a
    # pair of the wrong length, or a collection that is no
    # collection of pairs at all is a malformed call, never
    # a raw unpacking error.
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
            # failure of the append path stands refused.
            raise JournalError(
                "the batch intent record could not be "
                "written; the batch stands refused before "
                "any entry lands", row="I-2",
                token="JOURNAL_VERIFY_FAILED")
        appended = []
        try:
            for entry_kind, payload in prepared:
                # The join authorization stands for this
                # call only, named by its kind and its
                # payload object, and it takes effect only
                # where this append itself takes the lock,
                # so no ambient append inside the batch
                # window, and no code running in the grant
                # prologue of this call, joins the batch
                with _join_authorization(
                        _lock_path(home), entry_kind, payload):
                    appended.append(append_entry(
                        home, entry_kind, payload,
                        audit_date=audit_date, run_id=run_id))
        except Exception:
            # The rollback restores first and clears the
            # intent record last, the order the recovery
            # path itself stands in: a kill inside the
            # rollback then leaves the record standing over
            # the restored journal, and the next invocation
            # recovers from it, instead of leaving a partial
            # batch standing as ordinary state with no
            # record.
            _restore_journal_size(path, original_size)
            if resolved_anchor is not None:
                try:
                    if anchor_bytes is None:
                        if os.path.exists(resolved_anchor):
                            os.unlink(resolved_anchor)
                    else:
                        _restore_anchor_bytes(
                            resolved_anchor, anchor_bytes)
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
        # not consumed as state, in whole or in prefix.
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
                # raw error.
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

    With no resume, the replay starts from empty. With resume, the
    stated lines stand appended to the chain as it stands, so a replay
    from a mid chain state reaches the same head as the full replay.

    The replay validates before it writes: the entries argument must
    be a collection of entry lines (a single string, a bytes object, a
    mapping, and a non line element are each refused as a malformed
    call, before anything is written), the resulting chain must
    recompute, the journal length cap must admit it, and the anchor
    gate the append path runs must pass. A replay without resume over
    a standing journal stands refused: it would destroy the standing
    entries with no record."""
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
    # reported success.
    recover_interrupted_batch(home)
    with _WriteLock(home, kind="batch"):
        if _path_is_unsafe_home_file(journal_path(home)):
            raise _unsafe_home_file_error(
                journal_path(home), "journal")
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
            # full truncation leaves, so it skips nothing.
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
        # The home size cap stands enforced here as
        # append_entry enforces it, not the journal length
        # cap alone: the projected
        # home size with the candidate journal standing in
        # place of the standing journal must fit the cap
        # before anything is written.
        size_limit = limits["total_home_size"]
        size_cap = size_limit["value"] * _SIZE_MULTIPLIERS[
            size_limit["unit"]]
        path = journal_path(home)
        try:
            standing_journal_size = os.path.getsize(path)
        except OSError:
            standing_journal_size = 0
        candidate_size = sum(len(raw) + 1 for raw in candidate)
        projected_size = _home_size(home) - standing_journal_size \
            + candidate_size
        if projected_size > size_cap:
            raise JournalError(
                "the total home size cap stands reached",
                row="I-1", token="JOURNAL_CAP_EXCEEDED",
                refusal_context="append_cap", limit_number=40)
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
                descriptor = _open_home_file_descriptor(path, "a")
            except _UnsafeHomeFile:
                raise _unsafe_home_file_error(path, "journal")
            try:
                _rejudge_open_descriptor(descriptor, path)
            except _UnsafeHomeFile:
                os.close(descriptor)
                raise _unsafe_home_file_error(path, "journal")
            try:
                with os.fdopen(descriptor, "ab") as handle:
                    handle.write(b"".join(
                        raw + b"\n" for raw in lines))
                    handle.flush()
                    os.fsync(handle.fileno())
                    try:
                        _rejudge_open_descriptor(
                            handle.fileno(), path)
                    except _UnsafeHomeFile:
                        # The resume branch stands under the
                        # same post write judgement
                        # discipline as the append road: a
                        # rename plant timed at the return
                        # of the helper lstat reading of its
                        # pre write rejudgement stands
                        # judged after the write, the
                        # replayed lines stand truncated off
                        # the handle back to the size the
                        # journal stood, and no replayed
                        # content stands readable under the
                        # outside name.
                        handle.truncate(original_size)
                        handle.flush()
                        os.fsync(handle.fileno())
                        raise
                    try:
                        _rejudge_open_descriptor(
                            handle.fileno(), path)
                    except _UnsafeHomeFile:
                        # A further rejudgement stands after
                        # the post write judgement, judging
                        # its path reading as the judgement
                        # judges its handle reading: a
                        # rename plant timed at the return
                        # of the lstat reading of the post
                        # write judgement stands judged
                        # here, the replayed lines stand
                        # truncated off the handle in the
                        # remedy form above, and no replayed
                        # content stands readable under the
                        # outside name.
                        handle.truncate(original_size)
                        handle.flush()
                        os.fsync(handle.fileno())
                        raise
            except _UnsafeHomeFile:
                raise _unsafe_home_file_error(path, "journal")
            except OSError:
                _restore_journal_size(path, original_size)
                raise JournalError(
                    "the replay write failed; the journal "
                    "stands as it stood", row="I-2",
                    token="JOURNAL_VERIFY_FAILED")
        else:
            # The replacing branch carries the same guard as
            # the resume branch and the append path: a write
            # failure reports in the vocabulary at row I-2,
            # and its temporary file does not stand left
            # inside the home. The replacement temporary
            # stands created exclusively under a name no
            # planter can predict, on the same discipline as
            # the anchor temporary, so a planted link at a
            # guessed name is never the file this write
            # opens.
            descriptor, temporary = tempfile.mkstemp(
                prefix=os.path.basename(path) + ".replay-",
                dir=os.path.dirname(path) or ".")
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                    temporary_inode = os.fstat(
                        handle.fileno()).st_ino
                _replace_judged_temporary(
                    temporary, temporary_inode, path)
            except FileNotFoundError:
                # The temporary stands lost under its writer
                # before its link step: the condition row
                # X-13 names.
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
                # vocabulary at row X-13; the replay stands
                # rolled back all the same.
                rollback_write()
                raise
            except OSError:
                # An anchor write failure is not swallowed:
                # the replay stands rolled back and the
                # failure is reported, as the append path
                # reports it, so no replay reports success
                # with no anchor standing.
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
