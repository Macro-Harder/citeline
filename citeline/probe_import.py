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
    bytes.fromhex("504B0708"),
    bytes.fromhex("504B0506"),
    bytes.fromhex("504B0606"),
    bytes.fromhex("1F8B"),
    bytes.fromhex("425A68"),
    bytes.fromhex("FD377A585A00"),
    bytes.fromhex("377ABCAF271C"),
    bytes.fromhex("526172211A0700"),
    bytes.fromhex("526172211A070100"),
    bytes.fromhex("28B52FFD"),
    b"!<arch>\n",
    b"070707",
    b"\xc7\x71",
)

_ZIP_MAGICS = (
    bytes.fromhex("504B0304"),
    bytes.fromhex("504B0708"),
    bytes.fromhex("504B0506"),
    bytes.fromhex("504B0606"),
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
        # only the recorded and printed forms. The token
        # stands at the head of the message, so bounding the
        # message keeps the token and the opening of the
        # detail standing.
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
        # It refuses here, in the
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
    failure record standing.
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


_DEFAULT_IGNORABLE_RANGES = (
    (0x034F, 0x034F),
    (0x0610, 0x061A),
    (0x115F, 0x1160),
    (0x17B4, 0x17B5),
    (0x180B, 0x180D),
    (0x180F, 0x180F),
    (0x3164, 0x3164),
    (0xFE00, 0xFE0F),
    (0xFFA0, 0xFFA0),
    (0x1D173, 0x1D182),
    (0xE0100, 0xE01EF),
    (0x2060, 0x206F),
    (0xFFF0, 0xFFF8),
    (0xE0000, 0xE0FFF),
)


def _is_default_ignorable(char):
    """One default ignorable character outside the format
    category and the whitespace set.

    Variation selectors, the combining grapheme joiner,
    and their kin in the Unicode default ignorable set
    stand here. They render as nothing in stored text,
    so a file whose only head material renders as
    nothing holds no visible mark in front of the
    material behind it.
    """
    code = ord(char)
    return any(low <= code <= high
               for low, high in _DEFAULT_IGNORABLE_RANGES)


def _is_head_char(char):
    """One character of head material the form tests skip.

    Byte order marks, control bytes, whitespace, and zero
    width format characters stand in this set. The head
    reading removes them in any interleaving and in any
    number, so a mark standing after a control byte or a
    space, a third mark, and a zero width space shield
    nothing behind them (the reading removed one mark
    and then the control bytes in that order and only at
    the very start). Whitespace in this set stands as the
    whole Unicode space separator category, as this
    docstring has always stated it, not the ASCII space
    forms only, and the default ignorable forms stand in
    the set on the ground stated.
    """
    return (
        char == "\ufeff"
        or ord(char) < 0x20
        or ord(char) == 0x7f
        or 0x80 <= ord(char) <= 0x9f
        or char in " \t\n\r\f"
        or unicodedata.category(char) in ("Cf", "Zs", "Zl", "Zp")
        or _is_default_ignorable(char))


def _strip_head(text):
    """The text past any interleaved head material."""
    index = 0
    while index < len(text) and _is_head_char(text[index]):
        index += 1
    return text[index:]


def _strip_head_edges(text):
    """The text with head material removed at both edges.

    Head material standing behind a key or after its name,
    and head material standing at the end of a fence line,
    stands removed on the completed head predicate, as
    head material standing in front of a judged text
    stands removed by _strip_head.
    """
    start = 0
    while start < len(text) and _is_head_char(text[start]):
        start += 1
    end = len(text)
    while end > start and _is_head_char(text[end - 1]):
        end -= 1
    return text[start:end]


def _remove_interior_head(text):
    """The text with head material removed at any position.

    Head material standing inside a judged form, between
    the letters of a key name or between the dashes of a
    fence, stands removed as head material at an edge
    stands removed, while whitespace standing inside the
    form stands as written, so a form whose parts stand
    separated by spaces stands in its written form.
    """
    return "".join(
        char for char in text
        if not _is_head_char(char) or char.isspace())


def _judged_key(key):
    """One front matter key as the duplicate judgement
    reads it: head material removed at both edges and at
    any position inside the name."""
    return _remove_interior_head(_strip_head_edges(key))


def _judged_fence(line):
    """One fence line as the fence judgement reads it:
    head material removed at both edges and between the
    fence characters themselves."""
    return _remove_interior_head(_strip_head_edges(line))


def _detection_text(text):
    """The text the form tests read, at the head of a file.

    A byte order mark stripped under item 107 and any
    leading control bytes stand removed for the tests, so a
    mark or a control byte at the head cannot shield the
    material behind it from the tests.
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
    any order and in any number. The
    raw reading strips the same material the text
    reading strips: the head of the bytes stands decoded
    one character at a time, and every character the
    text head predicate holds, the whole Unicode format
    category among them, stands removed in its encoded
    form, not only the seven byte sequences an earlier
    form of this reading listed, so a format character
    outside that list shields nothing.
    """
    variants = [raw_bytes]
    body = raw_bytes
    while body:
        if body.startswith(_ARCHIVE_MAGICS):
            # The stripping stops at a signature it stands
            # in front of: a signature opening with a byte
            # the byte level stripping removes, the gzip
            # signature opening with 0x1F among them, stands
            # whole in the stripped variant, so a container
            # behind head material stands found in its own
            # form.
            break
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
    RecursionError carrying its message as an error value.
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


def _is_tar_header(variant):
    """True where the first 512 bytes stand as a tar header.

    A pre POSIX V7 tar carries no ustar marker and no head
    magic: its header stands judged by its own checksum
    field, the stored octal sum standing against the sum
    of the header bytes with that field held as spaces.
    """
    if len(variant) < 512:
        return False
    block = variant[:512]
    if block[0] == 0:
        return False
    field = block[148:156].strip(b"\x00 ")
    if not field:
        return False
    try:
        stored = int(field, 8)
    except ValueError:
        return False
    unsigned = sum(block[:148]) + 8 * 0x20 + sum(block[156:512])
    signed = sum(
        byte if byte < 0x80 else byte - 0x100 for byte in block[:148]) \
        + 8 * 0x20 + sum(
            byte if byte < 0x80 else byte - 0x100
            for byte in block[156:512])
    if stored not in (unsigned, signed):
        return False
    # The judgement stands on more of the header than the
    # checksum field alone: the mode, size, and mtime fields
    # stand in the octal form a tar header carries, and the
    # type flag stands as a V7 type, so a plain text block
    # that satisfies the checksum alone, its remaining
    # fields standing as prose letters, reads as no tar
    # The uid and gid fields stand in
    # the same octal form beside them.
    return (
        _is_octal_field(block[100:108])
        and _is_octal_field(block[108:116])
        and _is_octal_field(block[116:124])
        and _is_octal_field(block[124:136])
        and _is_octal_field(block[136:148])
        and block[156] in b"01234567\x00 ")


def _is_octal_field(field):
    """True where one tar numeric field stands in octal form.

    The field stands as octal digits closed by a NUL or a
    space, the two terminators the tar forms write.
    """
    text = field.strip(b"\x00 ")
    return bool(text) and all(byte in b"01234567" for byte in text)


def _is_cpio_odc_header(variant):
    """True where the bytes behind a cpio odc signature
    stand as its header.

    The odc header stands as fields of octal digits
    closed by NUL bytes behind the six signature
    characters, the fields from the device field through
    the file size field occupying the seventy characters
    behind the signature. The judgement reads those
    characters as octal digits, NUL bytes, or spaces, so
    plain text that opens with the signature characters
    as prose, its following characters standing as prose
    letters, reads as the text it is, and it reads the
    field structure behind the signature, each field
    standing closed by a NUL byte at its stated field
    end.
    """
    if len(variant) < 76:
        return False
    if not all(
            byte in b"01234567\x00 "
            for byte in variant[6:76]):
        return False
    # The judgement stands on the field structure of the
    # header, not on the character class alone: each field
    # of the odc header, the device field through the file
    # size field at their stated widths of six, six, six,
    # six, six, six, six, eleven, six, and eleven
    # characters, stands closed by a NUL byte at its field
    # end, so prose holding digits and spaces alone for
    # seventy characters, with no field boundary and no
    # NUL terminator at any field position, reads as the
    # text it is.
    field_ends = (11, 17, 23, 29, 35, 41, 47, 58, 64, 75)
    if not all(variant[end] == 0 for end in field_ends):
        return False
    # The judgement stands on the stated values of the
    # fields, not on their terminators and character class
    # alone: each field holds an octal value, its characters
    # before the closing NUL standing as octal digits beside
    # any space padding, so a field holding spaces alone,
    # with no octal digit in it, holds no value a header
    # field can hold and reads as the text it is. A field
    # standing wholly as NUL bytes holds the empty value of
    # the signature pin form and stands under the reading
    # above as it stood.
    field_starts = (6, 12, 18, 24, 30, 36, 42, 48, 59, 65)
    values = []
    name_size_field_all_nul = False
    for position, (start, end) in enumerate(
            zip(field_starts, field_ends)):
        field = variant[start:end]
        if all(byte == 0 for byte in variant[start:end + 1]):
            if position == 8:
                name_size_field_all_nul = True
            values.append(0)
            continue
        digits = field.strip(b" ")
        if not digits or not all(
                byte in b"01234567" for byte in digits):
            return False
        values.append(int(digits, 8))
    # The name size and file size fields stand read as the
    # lengths they state: the bytes standing hold the
    # member name and the member data of those lengths
    # behind the header, so a header whose stated sizes
    # stand past the bytes standing reads as text.
    name_size = values[8]
    file_size = values[9]
    # The judgement stands on the member name the stated
    # sizes name, as the newc limb of this family states:
    # a header stating a name size of zero in its stated
    # octal form states no member at all, a header stating
    # a name size of one holds a name of no character but
    # a single byte standing unclosed or its terminator
    # alone, and a stated name stands closed by the NUL
    # byte the format writes at its end, so a name
    # standing open in prose letters reads as the text it
    # is. The signature pin form,
    # whose name size field stands wholly as NUL bytes and
    # holds the empty value of that form, stands under the
    # reading above as it stood.
    if name_size == 0 and not name_size_field_all_nul:
        return False
    if name_size == 1:
        return False
    if name_size >= 2:
        if len(variant) < 76 + name_size:
            return False
        if variant[76 + name_size - 1] != 0:
            return False
        # The stated name stands as a string closed by
        # its first NUL byte, as the newc limb of this
        # family states: a name opening on its own
        # terminator holds no name, and a name holding a
        # character past its first terminator inside the
        # stated size holds bytes no header of this
        # format writes there, the NUL padding standing
        # behind a name in this format holding NUL bytes
        # alone past that terminator.
        stated_name = variant[76:76 + name_size]
        first_nul = stated_name.find(b"\x00")
        if first_nul < 1:
            return False
        if any(byte != 0 for byte in stated_name[first_nul:]):
            return False
    return len(variant) >= 76 + name_size + file_size


def _is_cpio_newc_header(variant):
    """True where the bytes behind a cpio newc signature
    stand as its header.

    The newc header stands as fields of eight ASCII
    hexadecimal characters each behind the six signature
    characters. The judgement reads the twelve fields
    from the inode field through the name size field,
    characters 6 to 102, each standing as hexadecimal
    text, so plain text that opens with the signature
    characters as prose, its following characters
    standing outside the hexadecimal form in the first
    field itself, reads as the text it is.
    """
    if len(variant) < 110:
        return False
    if not all(
            byte in b"0123456789abcdefABCDEF"
            for byte in variant[6:102]):
        return False
    # The judgement stands on fields behind the twelve it
    # reads as hexadecimal text: the name size field and
    # the file size field stand read as the lengths they
    # state, and the bytes standing behind the header
    # stand long enough to hold the member name and the
    # member data those lengths name, so a run of
    # hexadecimal prose carrying no member name and no
    # member data reads as the text it is.
    name_size = int(variant[94:102], 16)
    file_size = int(variant[54:62], 16)
    # The signature pin allowance stands on the pin form
    # itself, in its own terms: the pin form states no
    # field, its twelve fields standing as zero values,
    # and holds its name size at zero, so a check field
    # standing as no hexadecimal text stands under the
    # allowance on that form alone, and a complete header
    # standing in stated form, stating a field value of
    # its own, stands judged on the field values it
    # states and reads as text where its check field
    # stands as no hexadecimal text.
    check_field_is_hex = all(
        byte in b"0123456789abcdefABCDEF"
        for byte in variant[102:110])
    if not check_field_is_hex and variant[6:102] != b"0" * 96:
        return False
    # The judgement stands on the check field and on the
    # member name behind the fields it reads as lengths:
    # where the check field at characters 102 to 110
    # stands as hexadecimal text, the header stands
    # complete in its stated form, and a complete header
    # stating a name size of zero holds no member name
    # and no member at all, so it reads as the text it
    # is; and where the name size field states a name,
    # the bytes behind the header hold that name closed
    # by the NUL byte the format writes at its end, so a
    # name standing open in prose letters reads as text
    # The signature pin form, whose
    # check field does not stand as hexadecimal text,
    # stands under the reading above as it stood.
    if all(
            byte in b"0123456789abcdefABCDEF"
            for byte in variant[102:110]) and name_size == 0:
        return False
    if name_size >= 1:
        if len(variant) < 110 + name_size:
            return False
        if variant[110 + name_size - 1] != 0:
            return False
        if name_size >= 2 and variant[110] == 0:
            # A member name in this format stands as a
            # string closed by its first NUL byte, so a
            # stated name whose first byte stands as that
            # terminator holds no name: the member name
            # stands empty in the reading the format
            # states, in the form the name size of one
            # stands refused on below.
            return False
        if name_size >= 2:
            # The stated name stands judged whole, not at
            # its opening and closing bytes alone: a name
            # holding a character past its first
            # terminator inside the stated size holds
            # bytes no header of this format writes
            # there, the padding standing behind a name
            # inside the stated size holding NUL bytes
            # alone past that terminator.
            stated_name = variant[110:110 + name_size]
            first_nul = stated_name.find(b"\x00")
            if first_nul >= 0 and any(
                    byte != 0
                    for byte in stated_name[first_nul:]):
                return False
    if all(
            byte in b"0123456789abcdefABCDEF"
            for byte in variant[102:110]) and name_size == 1:
        # A complete header stating a name size of one
        # holds a member name of no character but its
        # terminator: the member name stands empty, no
        # member stands named, and the prose standing
        # behind the header where a member name with
        # content or a trailer would stand reads as the
        # text it is.
        return False
    if all(
            byte in b"0123456789abcdefABCDEF"
            for byte in variant[102:110]):
        # The judgement stands on the value the check
        # field states where the header stands complete:
        # the check field of the format states a value,
        # zero for the 070701 signature and the sum of
        # the member data for the 070702 signature, so a
        # complete header whose check field states a
        # value its signature and its member data do not
        # hold reads as the text it is. The signature pin
        # form, whose check field does not stand as
        # hexadecimal text, stands under the reading
        # above as it stood.
        check_value = int(variant[102:110], 16)
        if variant[:6] == b"070702":
            if len(variant) < 110 + name_size + file_size:
                return False
            # The member data stands behind the padding
            # that brings the header and the name field
            # to a multiple of four bytes counted from
            # the head of the header, in the format as
            # written, so the sum stands computed over
            # the data standing at that padded position,
            # beside the direct position the earlier
            # reading computed and the standing controls
            # pin.
            direct_sum = sum(variant[
                110 + name_size:
                110 + name_size + file_size])
            padding = (-(110 + name_size)) % 4
            padded_start = 110 + name_size + padding
            # The padded sum stands computed only where
            # the stream holds its stated member data
            # whole at the padded position: a stream too
            # short to hold that data there holds a
            # truncated slice at that position, and a sum
            # over data that does not stand in the stream
            # states no sum of the member data, so no
            # padded sum stands beside the direct sum on
            # such a stream.
            padded_sum = None
            if len(variant) >= padded_start + file_size:
                padded_sum = sum(variant[
                    padded_start:padded_start + file_size])
            if check_value != direct_sum \
                    and check_value != padded_sum:
                return False
        elif check_value != 0:
            return False
    return len(variant) >= 110 + name_size + file_size


def _is_cab_header(variant):
    """True where the bytes behind a CAB signature stand
    as its header.

    The cabinet header carries two reserved fields, at
    offsets 4 and 12, that stand as zero in the form the
    format writes, so plain text that opens with the
    signature characters as prose, its following words
    standing in those fields, reads as the text it is.
    """
    if len(variant) < 36:
        return False
    if not (
            variant[4:8] == b"\x00\x00\x00\x00"
            and variant[12:16] == b"\x00\x00\x00\x00"):
        return False
    # The judgement stands on fields behind the two
    # reserved fields: the cabinet size field and the
    # first file offset field stand read as the little
    # endian lengths they state, each standing at zero in
    # the signature pin form or within the bytes standing
    # here, so prose letters standing in those fields,
    # stating lengths no standing bytes hold, read as the
    # text they are. The judgement stands on the remaining
    # header fields beside the lengths: the third reserved
    # field at offset 20 stands as zero in the form the
    # format writes, and the version bytes at offsets 24
    # and 25 stand as the zero bytes of the signature pin
    # form or as the version the format writes, a minor of
    # 3 and a major of 1, so prose standing in the
    # remaining header fields reads as the text it is.
    if variant[20:24] != b"\x00\x00\x00\x00":
        return False
    if not ((variant[24] == 0 and variant[25] == 0)
            or (variant[24] == 3 and variant[25] == 1)):
        return False
    cabinet_size = int.from_bytes(variant[8:12], "little")
    first_file_offset = int.from_bytes(variant[16:20], "little")
    if not (
            (cabinet_size == 0 or cabinet_size <= len(variant))
            and (first_file_offset == 0
                 or 36 <= first_file_offset <= len(variant))):
        return False
    # The judgement stands the stated cabinet size
    # against the header itself beside the counts and the
    # bytes standing: a cabinet stating a size below 36
    # states a cabinet that cannot hold its own 36 byte
    # header, so such a stated size reads as the text it
    # is. The signature pin form,
    # whose cabinet size stands at zero, stands under the
    # reading above as it stood.
    if 0 < cabinet_size < 36:
        return False
    # The judgement stands on the tail fields of the
    # header, at offsets 26 to 36: the folder count and
    # the file count stand read as the counts they state,
    # each folder holding an eight byte entry standing
    # before the first file entry and each file a sixteen
    # byte entry standing from that offset, both inside
    # the cabinet size the header states, and the flags
    # field stands in the bits the format defines, the
    # previous cabinet, next cabinet, and reserve present
    # bits alone, so prose letters standing in those
    # fields, stating counts no cabinet of the stated
    # size holds and flag bits no header carries, read
    # as the text they are. The set
    # identifier and cabinet index fields carry no value
    # set a judgement can stand on and stand read for
    # their place in the header alone. The signature pin
    # form, whose counts and flags stand at zero and
    # whose cabinet size stands at zero, stands under
    # the reading above as it stood.
    folder_count = int.from_bytes(variant[26:28], "little")
    file_count = int.from_bytes(variant[28:30], "little")
    flags = int.from_bytes(variant[30:32], "little")
    if flags & ~0x0007:
        return False
    # The signature pin allowance stands on the pin
    # form itself, in its own terms: the pin form holds
    # its cabinet size and its counts at zero together,
    # so a cabinet stating a size of zero while its
    # counts stand states a cabinet holding entries
    # inside a size that holds nothing, and stands
    # judged on the counts it states.
    if cabinet_size == 0 and (folder_count or file_count):
        return False
    if cabinet_size:
        if folder_count and (
                first_file_offset == 0
                or 36 + 8 * folder_count > first_file_offset
                or 36 + 8 * folder_count > cabinet_size):
            # The folder entries stand judged against
            # the cabinet size the header states beside
            # the first file offset: a folder entry
            # standing partly past the stated cabinet
            # size stands inside a cabinet that cannot
            # hold the entry its own count names.
            return False
        if file_count and (
                first_file_offset == 0
                or first_file_offset + 16 * file_count
                > cabinet_size):
            return False
        # The judgement stands on the entries the counts
        # name, standing behind the header at their stated
        # sizes and offsets inside the cabinet size the
        # header states, each entry standing read for what
        # it states: a folder entry states the offset of
        # its data inside the cabinet, the count of its
        # data blocks, and a compression type standing in
        # the set the format defines, the none, MSZIP,
        # Quantum, and LZX values, and a file entry states
        # the folder it stands in by its index, an index
        # naming one of the folders the header counts or
        # one of the continuation values the format
        # defines, so entries standing wholly as prose
        # letters, stating an offset no cabinet of the
        # stated size holds, a compression type no folder
        # carries, and a folder index naming no folder,
        # read as the text they are.
        # The set identifier and cabinet index fields
        # stand in no part of this reading, carrying no
        # value set a judgement can stand on, as the
        # reading above states.
        for folder in range(folder_count):
            entry = variant[36 + 8 * folder:44 + 8 * folder]
            data_offset = int.from_bytes(entry[0:4], "little")
            block_count = int.from_bytes(entry[4:6], "little")
            compression = int.from_bytes(entry[6:8], "little")
            if compression not in (0, 1, 2, 3):
                return False
            if block_count and data_offset >= cabinet_size:
                return False
        for item in range(file_count):
            start = first_file_offset + 16 * item
            entry = variant[start:start + 16]
            folder_index = int.from_bytes(entry[8:10], "little")
            if folder_index >= folder_count and folder_index \
                    not in (0xFFFD, 0xFFFE, 0xFFFF):
                return False
    return True


_LINE_TERMINATORS = frozenset(
    chr(code) for code in (
        0x0A, 0x0D, 0x0B, 0x0C, 0x1C, 0x1D, 0x1E, 0x85, 0x2028, 0x2029))


def _pdf_header_at_line_start(variant):
    """True where a PDF header stands at the start of a line
    within the first 1,024 bytes of one raw variant.

    A line stands closed by any line terminator the text
    reading itself uses, and head material standing on the
    line itself, between the break and the header, stands
    skipped as the head reading skips it at the head of a
    file. The header stands judged by
    where it starts, so a header starting inside the
    window stands found whole even where its own bytes
    run past the window end.
    """
    index = 0
    at_line_start = False
    total = len(variant)
    while index < total:
        first = variant[index]
        if first < 0x80:
            char = chr(first)
            width = 1
        else:
            char = None
            width = 1
            for candidate_width in (2, 3, 4):
                try:
                    decoded = variant[index:index + candidate_width] \
                        .decode("utf-8")
                except (UnicodeDecodeError, ValueError):
                    continue
                if len(decoded) == 1:
                    char = decoded
                    width = candidate_width
                    break
            if char is None:
                at_line_start = False
                index += 1
                continue
        if char in _LINE_TERMINATORS:
            at_line_start = True
            index += width
            continue
        if at_line_start:
            if index <= 1024 and variant[index:index + 5] == b"%PDF-":
                return True
            if _is_head_char(char):
                index += width
                continue
            at_line_start = False
        index += width
    return False


def _is_html_opening(lowered):
    """True where a casefolded text opens a complete HTML
    document, by its doctype or by its html element."""
    if lowered.startswith("<!doctype") and (
            len(lowered) == 9 or lowered[9] in " \t\n\r\f"):
        return True
    if lowered.startswith("<html") and (
            len(lowered) == 5 or lowered[5] in " \t\n\r\f/>"):
        return True
    return False


def _is_markup_unit(lowered):
    """True where a casefolded text opens with a markup unit:
    a markup declaration, an element opening, or an element
    closing. The unit stands judged by its shape alone, an
    angle bracket, an element name of letters, digits, and
    hyphens (a custom element name carries a hyphen), and a
    name boundary, never by which element the name states."""
    if lowered.startswith("<!") and len(lowered) > 2 \
            and lowered[2].isalpha():
        return True
    match = re.match(r"</?([a-z][a-z0-9-]*)", lowered)
    if match:
        rest = lowered[match.end():]
        if rest == "" or rest[0] in " \t\n\r\f/>":
            return True
    return False


def _is_html_text(first):
    """True where the head text stands as an HTML capture.

    The judgement stands on the kind of the document, not on
    a list of element names. A capture is a markup document
    or a markup fragment: its first content unit, past any
    XML prolog, processing instruction, comment, or CDATA
    wrapper standing in front of it, is a markup unit, a
    doctype, an element opening, an element closing, or a
    markup declaration. A file whose first content unit
    stands as one of those is HTML in every spelling, the
    head and raw text elements (script, style, meta, link,
    base, template, noscript, textarea among them) and any
    element a later spelling opens with alike, where a
    fragment list named on one day falls to the spelling of
    the next. Plain answer text opens with prose, not with
    a markup unit, so prose stands untouched by this
    reading. A complete document standing behind one
    framing line, as an export header line stands in front
    of a document, stands judged on the document opening
    standing on a line just behind the head as well.
    """
    text = first.strip()
    while True:
        lowered = text.casefold()
        if lowered.startswith("<?"):
            end = lowered.find("?>")
            if end < 0:
                break
            text = text[end + 2:].lstrip()
            continue
        if lowered.startswith("<!--"):
            end = lowered.find("-->")
            if end < 0:
                break
            text = text[end + 3:].lstrip()
            continue
        if lowered.startswith("<![cdata["):
            text = text[9:].lstrip()
            continue
        break
    lowered = text.casefold()
    if _is_html_opening(lowered) or _is_markup_unit(lowered):
        return True
    for line in lowered.splitlines()[1:4]:
        if _is_html_opening(line.strip()):
            return True
    return False


def check11_form(raw_bytes, text):
    """Run the six tests of validation check 11.

    Returns the name of the test met, one of archive, pdf,
    html, json, json_lines, or delimited, or None where no
    test is met. A file meeting one of these tests is not one
    answer and fails import on that ground.
    """
    for variant in _raw_variants(raw_bytes):
        for magic in _ARCHIVE_MAGICS:
            if magic == b"070707":
                # The odc signature stands judged on the
                # header behind it, in the branch below, as
                # the newc and CAB signatures stand judged
                # on theirs.
                continue
            if variant.startswith(magic):
                return "archive"
        if variant.startswith(b"070707") \
                and _is_cpio_odc_header(variant):
            return "archive"
        if variant.startswith((b"070701", b"070702")) \
                and _is_cpio_newc_header(variant):
            # The cpio newc forms stand judged on the
            # header behind their signature, as the V7
            # limb judges its header, so signature
            # characters alone refuse no plain text
            # The odc signature of the
            # same family stands judged on its header in
            # the branch above, and the
            # binary magic stands in the archive magic set
            # itself.
            return "archive"
        if variant.startswith(b"MSCF") \
                and _is_cab_header(variant):
            return "archive"
        for magic in _ZIP_MAGICS:
            if magic in variant:
                # A zip archive preceded by arbitrary data
                # stands as the self extracting form, and a
                # standard reader locates the archive behind
                # the prefix, so the zip family stands read
                # behind a prefix as no other family does
                return "archive"
        if len(variant) >= 262 and variant[257:262] == b"ustar":
            # A tar archive carries no head magic: its
            # ustar marker stands at offset 257 of the
            # first header block.
            return "archive"
        if _is_tar_header(variant):
            return "archive"
        if variant.startswith(b"%PDF-"):
            return "pdf"
        if _pdf_header_at_line_start(variant):
            # A PDF header standing at the start of a
            # line near the head of the file, after a
            # junk first line, stands as a PDF
            # header.
            return "pdf"
    first = _detection_text(text)
    lowered = first.casefold()
    if lowered.startswith("<!doctype") and (
            len(lowered) == 9 or lowered[9] in " \t\n\r\f"):
        return "html"
    if lowered.startswith("<html") and (
            len(lowered) == 5 or lowered[5] in " \t\n\r\f/>"):
        return "html"
    if _is_html_text(first):
        return "html"
    stripped = first.strip()
    if stripped:
        value, parsed = _loads_json(stripped)
        if parsed and isinstance(value, (dict, list)):
            return "json"
        nonempty = [line for line in first.splitlines() if line.strip()]
        if len(nonempty) >= 2:
            json_count = 0
            for line in nonempty:
                _value, ok = _loads_json(line)
                if ok:
                    json_count += 1
            bad = len(nonempty) - json_count
            # A JSON lines export stands judged on the shape of
            # the whole file, not on unanimity and not on any
            # fixed share of damaged lines: one framing header
            # line or one truncated final line does not return
            # fifty JSON lines to plain answer reading, and
            # neither do the two framing lines of a small
            # export, the two fences of a fenced copy, or a
            # header and a footer, each of which stands past a
            # tenth of a small file while the file stands as
            # JSON lines in substance. Where at least two
            # lines parse as JSON and the JSON lines outnumber
            # the lines that do not, the substance of the file
            # is one JSON value per line, and the file stands
            # as JSON lines and fails import on that ground.
            # Plain prose, where no line or a lone line parses,
            # and prose carrying an incidental JSON example
            # among more prose lines than JSON lines, stands
            # untouched by this reading.
            if json_count >= 2 and json_count > bad:
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
    operator surface.
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
    one key for the duplicate control.
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


class _WrittenNumber(str):
    """A JSON number carrying its written form.

    The JSON form value length check measures a numeric
    value by its written form, as it measures a string
    by its length. Parsing a number
    into a plain int or float loses that form, a float
    in particular rendering far shorter than it stands
    written, so the reader holds the token text itself.
    """


def _remove_interior_head_except_marks(text):
    """The text with head material removed at any position
    except a mark of the union of general category Mn,
    Mc, or Me, which stands as written: the reading the
    follower judgement of _holds_tag_construct stands
    on before the interior head reading, so a mark of
    the union standing after a construct character
    stands judged as the follower it stands as in the
    written text even where the interior head reading
    would remove it, whitespace standing as written as
    on that reading.
    """
    return "".join(
        char for char in text
        if not _is_head_char(char) or char.isspace()
        or unicodedata.category(char) in ("Mn", "Mc", "Me"))


_JUDGED_POSITION_CHARS = set(
    "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")

_WIDENED_FOLLOWER_CHARS = set("-.+$~;/=@^`?\\()<:") | {
    "\u203f"}


def _position_scan_holds(text):
    """True where a construct stands held on the position
    scan, judged on the text as
    written, one construct position at a time, so no
    match pass consumes a position a later construct
    needs. A construct position stands judged where,
    reading back from the construct over head material
    that is not whitespace, the scan reaches the start
    of the text, a whitespace character, or a character
    of the judged position punctuation set. The follower
    at such a position stands judged where the character
    standing immediately after the construct character
    is a mark of the union of general category Mn, Mc,
    or Me, or stands as head material and stands in the
    follower set through a word character or through
    one of the widened follower characters. The
    follower judgement stands reached past head gap
    material standing between the construct character
    and its follower: where the character standing
    immediately after the construct character stands as
    head material that is not whitespace and stands
    judged on no limb of the follower judgement, the
    scan reads forward over head material characters
    that are not whitespace and that stand judged on no
    such limb, and judges the construct on the first
    character standing past that run where that
    character stands judged as a follower on the
    standing limbs; where no such character stands past
    the run, the construct stands unjudged on that
    follower ground.
    """
    def follower_judged(char):
        return unicodedata.category(char) in (
            "Mn", "Mc", "Me") or (
                _is_head_char(char) and (
                    char.isalnum() or char == "_"
                    or char in _WIDENED_FOLLOWER_CHARS))

    for index, char in enumerate(text):
        if char not in "&*%!":
            continue
        if index + 1 >= len(text):
            continue
        follower = text[index + 1]
        if follower_judged(follower):
            pass
        elif _is_head_char(follower) \
                and not follower.isspace():
            ahead = index + 2
            while ahead < len(text) \
                    and _is_head_char(text[ahead]) \
                    and not text[ahead].isspace() \
                    and not follower_judged(text[ahead]):
                ahead += 1
            if ahead < len(text) \
                    and follower_judged(text[ahead]):
                pass
            else:
                continue
        else:
            continue
        back = index - 1
        while back >= 0 and _is_head_char(text[back]) \
                and not text[back].isspace():
            back -= 1
        if back < 0 or text[back].isspace() \
                or text[back] in _JUDGED_POSITION_CHARS:
            return True
    return False


def _holds_tag_construct(text):
    """True where a key or value text holds a tag construct.

    The D17 control set states no allowance for a tag
    construct in front matter, at any position: a construct
    standing at the start of the text, a construct spelling
    standing as its own word later in the text (an anchor,
    an alias, a tag, or a directive spelling after the
    first word), an angle bracket tag spelling anywhere in
    the text, and a block scalar opening standing as the
    value all stand refused.
    """
    # The judgement stands on the text with head material
    # standing at any interior position removed, on the
    # interior head reading the duplicate judgement and
    # the fence judgement of this module apply: a head
    # character standing between a judged position and the
    # construct, between the construct character and its
    # letter, or between an angle bracket and its opening
    # character, stands removed before the positions stand
    # judged, so such a character moves no construct off
    # its judged position. The follower judgement stands
    # reached on a sole follower mark of the union even
    # where the interior head reading would remove that
    # mark: the helper first judges the follower on the
    # text with head material removed at any position
    # except a mark of the union, which stands as written,
    # so a construct whose name opens on one of the union
    # marks that also stand as head material, standing as
    # sole follower with nothing judged standing after it,
    # at the end of the judged text or before only
    # whitespace or head material, stands judged on that
    # reading, the interior head reading then standing as
    # it stood for every other judgement of the helper.
    # The follower judgement stands reached on the text as
    # written at every construct position in turn, on the
    # position scan at _position_scan_holds: a construct
    # standing behind head material at a judged position
    # stands judged as the scan reads back over that
    # material, a second construct standing after a first
    # stands judged at its own position, and a sole
    # follower character of the follower set that also
    # stands as head material stands judged in the word
    # character form as in the mark form, the follower
    # judgement of the scan standing reached past head gap
    # material standing between the construct character
    # and its follower.
    if _position_scan_holds(text):
        return True
    for match in re.finditer(
            r"(?:^|[\s!\"#\$%&'\(\)\*\+,\-\./:;<=>\?@\[\\\]\^_`{|}~])"
            r"[&*%!](.)", _remove_interior_head_except_marks(text)):
        if unicodedata.category(match.group(1)) in (
                "Mn", "Mc", "Me"):
            return True
    text = _remove_interior_head(text)
    if text.startswith(("!", "&", "*", "%")):
        return True
    if re.search(
            r"<[A-Za-z0-9\-._;/?:@&=+$,!~*'()%\[\]\^#][^>]*>", text):
        # An angle bracket spelling opens on any URI
        # character, a digit, a hyphen, or an underscore
        # among them, as a verbatim tag spelling admits,
        # the caret among them as a verbatim tag spelling
        # admits it, and the hash among them, standing as
        # the fragment delimiter of the same character
        # set.
        return True
    if re.search(
            r"(?:^|[\s!\"#\$%&'\(\)\*\+,\-\./:;<=>\?@\[\\\]\^_`{|}~])"
            r"[&*%!][\w\-\.\+\$~;/=@\^`\u0300-\u036f\u203f"
            r"\?\\\(\)<:]", text):
        # A construct stands judged at the start of the
        # text, after whitespace, and directly after a
        # flow opening bracket, the flow positions
        # standing inside a flow collection, and directly
        # after the separator standing between two flow
        # items, after the colon of a flow mapping, after
        # a semicolon, after a quote, and after an opening
        # parenthesis, and directly after a closing
        # bracket, the closing square bracket, the closing
        # curly brace, and the closing parenthesis
        # standing as judged positions beside their
        # opening counterparts, and directly after any
        # remaining punctuation character, the position
        # set standing whole as the whole punctuation set
        # beside whitespace. The character standing after
        # the construct character stands judged as the
        # opening of the name the construct spells: an
        # anchor spelling, an alias spelling, and a tag
        # spelling name their target in characters wider
        # than the plain alphabet, a name opening on a
        # digit, on an underscore, on a hyphen, and on
        # letters outside the plain alphabet, so the
        # follower set stands as any word character or a
        # hyphen. The names those spellings state open on
        # characters standing outside that set as well,
        # none of them standing as a flow indicator and
        # none standing reserved, so the follower set
        # stands widened to those openings: a full stop, a
        # plus sign, a dollar sign, a tilde, a semicolon,
        # a slash, an equals sign, an at sign, a caret, a
        # backtick, a combining mark, and an undertie. The
        # names those spellings state open on six further
        # characters standing on the same ground, none of
        # them standing as a flow indicator and none
        # standing reserved, so the follower set stands
        # widened to those openings as well: a question
        # mark, a backslash, an opening parenthesis, a
        # closing parenthesis, a less than sign, and a
        # colon.
        return True
    for match in re.finditer(
            r"(?:^|[\s!\"#\$%&'\(\)\*\+,\-\./:;<=>\?@\[\\\]\^_`{|}~])"
            r"[&*%!](.)", text):
        # The combining mark opening the governing
        # statement names stands as a combining mark as
        # such, with no range standing in that statement,
        # so the follower stands judged on its general
        # category: a character of general category Mn
        # standing after the construct character at a
        # judged position stands as that opening, at any
        # code point, beside the range the earlier cure
        # landed and beside the word character set, each
        # of which the reading above already refuses. The
        # generic term stands as the union of the mark
        # categories, so a character of general category
        # Mc or of general category Me standing at the
        # same position stands as that opening in the same
        # form, at any code point.
        if unicodedata.category(match.group(1)) in (
                "Mn", "Mc", "Me"):
            return True
    if re.match(r"^[|>](?:[+-]?[0-9]?|[0-9][+-])?(?:\s|$)", text):
        # A block scalar header admits both indicator
        # orders, the chomping sign before the indentation
        # digit and the digit before the sign.
        return True
    return False


def _json_holds_tag_construct(value):
    """True where any string in a JSON form value, at any
    depth, in a key or in a value, holds a tag construct.

    The JSON form of a front matter block stands under the
    same control set as the line form, whole.
    """
    if isinstance(value, _WrittenNumber):
        return False
    if isinstance(value, str):
        return _holds_tag_construct(_strip_head(value.strip()))
    if isinstance(value, dict):
        return any(
            _holds_tag_construct(_strip_head(str(key).strip()))
            or _json_holds_tag_construct(item)
            for key, item in value.items())
    if isinstance(value, list):
        return any(_json_holds_tag_construct(item) for item in value)
    return False


def _render_written(value):
    """One parsed JSON value rendered with its numbers in
    written form.

    A container value stands measured by this rendering, so
    a number standing inside a container stands measured by
    its written form as a number standing as a whole value
    does, and no conversion of the number, to an integer, to
    a float, or to infinity, discards that form.
    """
    if isinstance(value, _WrittenNumber):
        return str(value)
    if isinstance(value, str):
        # A string stands rendered by its own characters
        # between its quote marks, not by its JSON escaped
        # form, so a string standing inside a container
        # stands measured by its length in characters, the
        # one measure a string standing as a whole value
        # stands measured by, while a number inside a
        # container keeps its written form above.
        return '"' + value + '"'
    if isinstance(value, dict):
        return "{" + ", ".join(
            json.dumps(str(key), ensure_ascii=False) + ": "
            + _render_written(item)
            for key, item in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(
            _render_written(item) for item in value) + "]"
    return json.dumps(value)


def _container_value_measure(value):
    """The length a container value stands measured by.

    A string standing inside a container stands measured
    by its length in characters, the one measure a string
    standing as a whole value stands measured by, and a
    number standing inside a container stands measured
    by its written form, as a number standing as a whole
    value does: the container marks, the quote marks,
    and the separators of the rendering count for
    nothing in the measure.
    """
    if isinstance(value, _WrittenNumber):
        return len(value)
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        # A string standing as a key inside a container
        # stands measured by its length in characters, as
        # a string standing as a value inside a container
        # stands measured, at any depth.
        return sum(
            _container_value_measure(key)
            + _container_value_measure(item)
            for key, item in value.items())
    if isinstance(value, list):
        return sum(
            _container_value_measure(item) for item in value)
    return 0


def _plain_json_value(value):
    """One parsed JSON value with its numbers restored
    to plain numeric form, for rendered measurement of
    a container value."""
    if isinstance(value, _WrittenNumber):
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return str(value)
    if isinstance(value, dict):
        return {key: _plain_json_value(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [_plain_json_value(item) for item in value]
    return value


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
    # Head material in front of the fence (a control byte, a
    # mark, a zero width form) does not move the block off
    # the head: the block stands read where it stands once
    # that material is skipped, as the check 11 tests read
    # through the same head. A text whose head holds no
    # fence after that material returns itself unchanged,
    # head included.
    working = _strip_head(text)
    lines = working.splitlines()
    if not lines or _judged_fence(lines[0]) != "---":
        # The opening fence stands judged on the completed
        # head predicate, not on whitespace stripping
        # alone, so an opening fence carrying head
        # material at its end reads as the block it opens
        return text, False
    text = working
    lines = text.splitlines()
    closing = None
    for index in range(1, len(lines)):
        if _judged_fence(lines[index]) in ("---", "..."):
            # The closing fence stands judged on the
            # completed head predicate at both edges, as
            # the opening fence stands judged, so a closing
            # fence carrying head material at its trailing
            # edge stands read as a closing fence.
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
    # reading: limit 11, block size
    # 16 KiB, measured in bytes as the page side measures
    # it; limit 12, key count 100; limit 17, value length
    # 4,096 characters; and limit 18, JSON nesting depth
    # 100 on the JSON form. The adapter receives no home,
    # so the brief values govern here, as they govern the
    # answer file size at this same seam.
    # The block size stands measured on the block as it
    # stands in the file: the lines between the fences
    # with the terminators the file closes them with, at
    # their file width, so a terminator wider than one
    # byte counts at its width on every block line
    kept_lines = text.splitlines(keepends=True)
    block_in_file = "".join(kept_lines[1:closing])
    if len(block_in_file.encode("utf-8")) \
            > FRONT_MATTER_BLOCK_LIMIT:
        _fail("LIMIT_EXCEEDED",
              "front matter block size limit is 16 KiB, with "
              "rejection and no partial record")
    if block.startswith("{"):
        def _no_duplicates(pairs):
            seen = set()
            for key, _value in pairs:
                judged = _judged_key(str(key))
                if judged in seen:
                    _fail("IMPORT_VALIDATION_FAILED",
                          "the front matter block in JSON form "
                          "holds the key " + judged + " twice; "
                          "front matter keys stand once each")
                seen.add(judged)
            return dict(pairs)
        try:
            parsed = json.loads(
                block, object_pairs_hook=_no_duplicates,
                parse_int=_WrittenNumber,
                parse_float=_WrittenNumber)
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
        if _json_holds_tag_construct(parsed):
            _fail("IMPORT_VALIDATION_FAILED",
                  "the front matter block holds a tag "
                  "construct, which the front matter "
                  "control set refuses")
        for top_key, value in parsed.items():
            # A string standing as a key of the top level
            # object stands measured by its length in
            # characters, as a string standing as a value
            # stands measured: the loop over the members of
            # the object measures each key beside the
            # measure of its value, so a key past the limit
            # stands refused at that position. The key
            # positions inside a container stand measured
            # as stated, and the seam refusal stands in
            # its exact stated form beside this reading,
            # untouched.
            if isinstance(top_key, str) \
                    and len(top_key) > FRONT_MATTER_VALUE_LIMIT:
                _fail("LIMIT_EXCEEDED",
                      "front matter value length limit is "
                      "4,096 characters, with rejection and "
                      "no partial record")
            if isinstance(value, _WrittenNumber):
                measured = len(value)
            elif isinstance(value, str):
                measured = len(value)
            elif isinstance(value, (dict, list)):
                measured = _container_value_measure(value)
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
                    continuation = block_line.strip()
                    current_value_length += len(continuation)
                    if current_value_length \
                            > FRONT_MATTER_VALUE_LIMIT:
                        _fail("LIMIT_EXCEEDED",
                              "front matter value length limit "
                              "is 4,096 characters, with "
                              "rejection and no partial record")
                    if _holds_tag_construct(
                            _strip_head(continuation)):
                        _fail("IMPORT_VALIDATION_FAILED",
                              "the front matter block holds a "
                              "tag construct, which the front "
                              "matter control set refuses")
                    if (continuation.count("[")
                            != continuation.count("]")
                            or continuation.count("{")
                            != continuation.count("}")):
                        # The not closed bracket check the
                        # key line path runs stands on
                        # continuation lines whole.
                        _fail("IMPORT_VALIDATION_FAILED",
                              "a front matter value is not "
                              "closed: " + continuation[:60])
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
            # The duplicate judgement stands on the judged
            # key, head material removed at both edges, as
            # the construct judgements stand, so a second
            # key dressed with head material behind its
            # name or after it stands as the key it is,
            # and head material standing inside the key
            # name stands removed on the same predicate.
            judged_key = _judged_key(key)
            if judged_key in seen_keys:
                _fail("IMPORT_VALIDATION_FAILED",
                      "the front matter block holds the key "
                      + judged_key + " twice; front matter keys "
                      "stand once each")
            seen_keys.add(judged_key)
            # The construct and bracket judgements stand on
            # the key and on the value with any head material
            # standing in front of the judged text removed, so
            # one such character, or a space inside a quoted
            # key, does not move a construct off the judged
            # position, and the bracket
            # judgement stands on the key as on the value
            judged_value = _strip_head(value)
            if _holds_tag_construct(judged_key) \
                    or _holds_tag_construct(_strip_head(key)):
                # The key construct judgement stands on the
                # key with head material standing in front of
                # it removed beside the judged key the
                # duplicate judgement reads, in the form the
                # page side reading states for its key
                # position: the judged key stands on the
                # interior head reading whole, so a union
                # mark standing as sole follower in a key
                # stands removed in that text before the
                # follower judgement runs, and the judgement
                # stands reached on it in the key as written
                # past its head. The line form checks stand
                # on the key position as on the value side.
                _fail("IMPORT_VALIDATION_FAILED",
                      "the front matter block holds a tag "
                      "construct, which the front matter "
                      "control set refuses")
            if (judged_key.count("[") != judged_key.count("]")
                    or judged_key.count("{")
                    != judged_key.count("}")):
                _fail("IMPORT_VALIDATION_FAILED",
                      "a front matter key is not closed: "
                      + judged_key[:60])
            if _holds_tag_construct(judged_value):
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
    missing = [
        name for name, value in required
        if value is None or (isinstance(value, str) and value == "")]
    if audit_date is None or (isinstance(audit_date, str)
                              and audit_date == ""):
        missing.append("audit_date")
    if missing:
        # One refusal names every missing required input, so an
        # operator fixes the whole call in one run instead of
        # one input per run.
        _fail("IMPORT_VALIDATION_FAILED",
              "missing required inputs: " + ", ".join(missing))
    _require_text_inputs({
        "product": product, "round": round,
        "engine_label": engine_label, "query": query,
        "capture_method": capture_method,
        "control_designation": control_designation, "kind": kind})
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
        # seam.
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


def _answer_file_limit_bytes(home):
    """The answer file size limit in force, in bytes.

    Where a home stands named, the limit the home config
    publishes governs, read through the journal limits in
    force. Where no home stands named or its limits cannot
    be read, the brief value governs, as before. Returns
    (limit_bytes, limit_value_in_mib).
    """
    if home is not None:
        try:
            from citeline import journal
            limits = journal.effective_limits(str(home))
            value = (limits.get("answer_file_size") or {}).get("value")
            if isinstance(value, (int, float)) and value > 0:
                return int(value * 1024 * 1024), value
        except Exception:
            pass
    return ANSWER_FILE_LIMIT, ANSWER_FILE_LIMIT // (1024 * 1024)


def read_answer_file(answer_file, home=None):
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
    limit_bytes, limit_value = _answer_file_limit_bytes(home)
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
            if total > limit_bytes:
                _fail("LIMIT_EXCEEDED",
                      "answer file limit is %s MiB in force "
                      "for this home" % ("%g" % (limit_value,)))
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    if len(raw) > limit_bytes:
        _fail("LIMIT_EXCEEDED",
              "answer file limit is %s MiB in force "
              "for this home" % ("%g" % (limit_value,)))
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
    """The duplicate comparison, contract C2 as relaxed.

    The comparison runs in the same product namespace and the
    same kind class; kind classes do not cross, and a record
    held for a different product stands as neither. Returns
    "duplicate" or None for a new record. A standing record
    holding a different answer for the same round, engine,
    query, and capture date stands as no bar: repeated
    sampling admits it, and the candidate stands as a new
    record under its own identity.
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
    return None


def compare_standing_record(standing_records, candidate):
    """The comparison with the standing record it met.

    Returns (outcome, record): the outcome compare_standing
    states and the standing record that produced it, or
    (None, None) for a new record. The record travels so a
    refusal can name the standing answer it conflicts with.
    """
    for record in standing_records or []:
        single = compare_standing([record], candidate)
        if single is not None:
            return single, record
    return None, None


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


def _resolve_standing_marker(value, base=None, record=None):
    """Resolve the sequence marker in one standing identity.

    The marker resolves against the batch position the
    identity carries as its trailing number: where a
    base stands supplied, the position counts from that
    base, and where none stands supplied it counts from
    the batch position itself, the sequence the module
    surface knows, as the worksheet cure at states. An identity holding no marker
    stands as it stands.
    """
    text = str(value)
    if "{sequence}" not in text:
        return text
    match = re.search(r"-([0-9]+)$", text)
    position = 1
    if match and len(match.group(1)) <= 10:
        position = int(match.group(1))
    effective = base if base is not None else 1
    return text.replace(
        "{sequence}", str(effective + position - 1))


def prepare_import(*, answer_file=None, product=None, round=None,
                   engine_label=None, query=None, kind=None,
                   captured_on=None, capture_method=None,
                   control_designation=None, audit_date=None,
                   known_round=True, query_set=None,
                   standing_records=(), control_count=0,
                   product_id=None, round_id=None, answer_id=None,
                   registry_version_at_import=None,
                   detector_version_at_import=None, home=None):
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
    raw, text, content_hash = read_answer_file(answer_file, home=home)
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
        detector_version_at_import=detector_version_at_import,
        standing_id_resolver=_resolve_standing_marker)


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
    if form is None:
        # The body stands judged as the body, as this
        # reading states its own rule: check 11 runs on
        # the body exactly as it runs on a standalone
        # file, so a container standing behind a front
        # matter block stands at the positions the tests
        # read in the body itself, and material a
        # standalone file refuses stands refused here
        form = check11_form(body_text.encode("utf-8"), body_text)
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
    reads as the sheet it is. The header line stands first in the returned
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
        candidate = stripped[cut:]
        # The header line stands judged with its head
        # material stripped, as the lines before it are
        # judged: head material standing after the header
        # text, or inside it, stands removed for the
        # judgement, and a line that reads as the header
        # once that material stands removed stands as
        # the header line itself.
        # The word structure of the header stands judged:
        # head material that is not the ordinary space
        # stands removed for the judgement, and the spaces
        # that separate the header words stand as written,
        # so a line the export never wrote, with no
        # separation, with doubled spaces, with a space
        # between letters, or with tabs in place of the
        # spaces, reads as no header.
        judged = "".join(
            char for char in candidate
            if not _is_head_char(char) or char == " ")
        if judged == WORKSHEET_HEADER:
            lines[index] = WORKSHEET_HEADER
        else:
            lines[index] = candidate
        break
    return lines[index:]


def is_worksheet_text(text):
    """True where a text is a capture worksheet.

    The worksheet carries its own header line, written by
    the export in this module. That header is the mark the
    import route reads a returned sheet by. A sheet
    standing behind a blank line or a control byte reads
    as a sheet here, so it meets the worksheet route or
    its refusal, and never the plain answer path.
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
    line this parser reads, and returns None. The index
    stands in the form the export writes, plain ASCII
    digits with no leading zero, and no field marker
    stands twice on a slot line.
    """
    match = re.match(r"^slot ([0-9]+):(.*)$", line)
    if not match:
        return None
    digits = match.group(1)
    if len(digits) > 1 and digits.startswith("0"):
        # The export writes no leading zero.
        return None
    if len(digits) > 10:
        # An index in a form no sheet the export writes
        # can carry stands unread as an index, without
        # the raw conversion error a very long digit
        # string raises. The line
        # stands as answer text where a slot body stands
        # open, on the judgement limb of.
        return None
    rest = match.group(2)
    # A field marker stands counted in every separator
    # dressing, not only in the one exact form the export
    # writes: a marker separated by a tab or by no break
    # spaces in place of the plain spaces stands as the
    # marker it is, so a second copy dressed in another
    # separator stands counted, and a line whose markers
    # do not stand exactly once each, in the exported
    # order, is no slot line. The separator set the
    # count reads stands completed on the head predicate:
    # a character of the completed head set standing in
    # front of a field name, standing on either side of
    # its equals sign, or standing inside the field name
    # itself, stands as the separator it is, and the
    # marker stands counted in that dressing too.
    assignments = _slot_assignments(rest)
    if [name for name, _start, _end in assignments] \
            != list(_SLOT_FIELDS):
        return None
    values = {}
    for index, (name, _start, end) in enumerate(assignments):
        stop = assignments[index + 1][1] \
            if index + 1 < len(assignments) else len(rest)
        values[name] = _slot_value(rest[end:stop])
    return {"index": int(digits), "fields": values}


_SLOT_SEPARATOR_PUNCTUATION = frozenset(
    "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")


def _slot_assignments(rest):
    """The field assignments of one slot line, in order.

    Each assignment stands as (field name, start, end),
    the end standing past the equals sign and the
    separator characters that follow it. A field name
    stands found where a separator stands in front of
    it, the separator set standing as the completed
    head set beside the whitespace forms, and head
    characters standing inside the name or between the
    name and its equals sign stand skipped as the
    separators they are.
    """
    assignments = []
    index = 0
    while index < len(rest):
        if index > 0 and not (
                _is_head_char(rest[index - 1])
                or rest[index - 1].isspace()
                or rest[index - 1] in _SLOT_SEPARATOR_PUNCTUATION):
            # A separator drawn from the punctuation forms
            # stands as a separator beside the completed
            # head set and the whitespace forms: a
            # semicolon, a comma, an opening parenthesis, a
            # double quote, an underscore, a hyphen, a
            # slash, a vertical bar, a colon, an equals
            # sign, or a full stop standing in front of a
            # field name counts the marker it stands in
            # front of, and the remaining punctuation forms
            # stand in the same set, the closing brackets,
            # the single quote, the question and exclamation
            # marks, the at sign, the hash, the dollar and
            # percent signs, the caret, the ampersand, the
            # asterisk, the plus sign, the tilde, the grave
            # accent, the backslash, the angle brackets, and
            # the opening square bracket and curly brace.
            index += 1
            continue
        matched = None
        for name in _SLOT_FIELDS:
            cursor = index
            position = 0
            while position < len(name):
                if cursor < len(rest) \
                        and rest[cursor] == name[position]:
                    cursor += 1
                    position += 1
                    continue
                if cursor < len(rest) \
                        and _is_head_char(rest[cursor]):
                    cursor += 1
                    continue
                break
            if position < len(name):
                continue
            after = cursor
            while after < len(rest) and (
                    _is_head_char(rest[after])
                    or rest[after].isspace()):
                after += 1
            if after < len(rest) and rest[after] == "=":
                end = after + 1
                while end < len(rest) and (
                        _is_head_char(rest[end])
                        or rest[end].isspace()):
                    end += 1
                matched = (name, index, end)
                break
        if matched is None:
            index += 1
            continue
        assignments.append(matched)
        index = matched[2]
    return assignments


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
        slot_match = re.match(r"^slot ([0-9]+):", line)
        if slot_match and slots_open:
            # Slot lines stand judged against the sheet the
            # export wrote: a slot line
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
                             answer_sequence_base=None, home=None):
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
    _raw, text, _hash = read_answer_file(answer_file, home=home)
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
    prepared_records = []
    # The standing records stand bucketed by the three
    # fields the comparison judges before any outcome
    # can stand: kind, normalised engine label, and
    # query. Inside a bucket, a candidate can stand as a
    # duplicate only of a record holding its own content
    # hash, and as a contradiction only of a record
    # holding its own capture date, on the comparison
    # rule itself, so each bucket stands sub-indexed by
    # content hash and by capture date and the
    # comparison for each slot reads only the records
    # standing under its own hash or its own date, in
    # their standing order. A record whose bucket key
    # cannot be keyed stands in the overflow list and
    # stands read on the bucket field equality reading
    # at the selection below. Preparation therefore
    # costs time near linear in the number of filled
    # slots on the spread shapes entry measures and on
    # the single bucket distribution a returned sheet
    # presents, where every slot shares one bucket, and
    # its duplicate and contradiction judgements stand
    # exactly as the whole list comparison stood, as the
    # same engine controls pin.
    sub_by_hash = {}
    sub_by_date = {}
    overflow = []
    standing_index = 0

    def _index_key_component(value):
        # A bucket field standing as a string stands keyed
        # by its plain string form, so a string subclass
        # whose hash stands removed keys by the value it
        # stands equal to, and a field standing in a form
        # that cannot be hashed and stands equal to no
        # candidate field keys under a form no candidate
        # key carries.
        if isinstance(value, str):
            try:
                return str(value)
            except Exception:
                # A string form whose string reading
                # raises stands keyed under a placeholder
                # no candidate key carries, as a field
                # whose hash raises stands keyed below, so
                # the raising stands answered inside the
                # recorded error vocabulary at the
                # selection below and never as a raw error
                # to the caller at the keying.
                return ("citeline-unhashable",
                        type(value).__name__,
                        "citeline-unreadable-string")
        try:
            hash(value)
        except Exception:
            # A field whose hash raises in any form, a
            # TypeError or any other error, keys under the
            # same placeholder, so the raising stands
            # answered inside the recorded error vocabulary
            # at the selection below and never as a raw
            # error to the caller. The placeholder stands
            # built without a reading that can itself
            # raise: a field whose repr raises beside its
            # hash keys under a fixed marker in place of
            # its repr.
            try:
                shown = repr(value)
            except Exception:
                shown = "citeline-unrepresentable"
            return ("citeline-unhashable", type(value).__name__,
                    shown)
        return value

    def _bucket_key(record):
        return tuple(_index_key_component(_record_field(
            record, name)) for name in (
                "kind", "engine_label_normalised", "query"))

    def _unkeyable_field(value):
        # A field standing in a form that cannot be hashed
        # and is no string subclass stands keyed under a
        # placeholder no candidate key carries, so a key
        # reading alone never compares it, whatever its
        # equality test answers.
        if isinstance(value, str):
            return False
        try:
            hash(value)
        except Exception:
            return True
        return False

    def _overflow_field(value):
        # A field standing in any form but a plain string
        # form stands in the overflow list beside its sub
        # index entries, string forms standing keyed by
        # the plain string they stand equal to on the
        # reading above: a form that is no string can hold
        # a hash standing apart from its equality, keyed
        # under its own hash where no candidate key
        # reaches it, or a hash raising outside TypeError,
        # so the key reading alone never compares it,
        # whatever its equality test answers, and the
        # bucket field equality reading at the selection
        # below runs on it in every such form.
        # A string form standing as a subclass of the
        # plain string form stands in the overflow list on
        # the same ground: it stands keyed by the
        # characters it carries, and a subclass whose
        # equality answers apart from the string it stands
        # keyed under, answering as a target string its
        # characters do not stand as or answering true
        # against any candidate, stands reached by no
        # candidate key, so the equality reading stands to
        # run on it in the overflow list as it runs on
        # every other such form.
        if isinstance(value, str):
            return type(value) is not str
        if value is None:
            return False
        return True

    def _index_standing(record, bucket_key, index):
        raw_bucket = tuple(_record_field(record, name) for name in (
            "kind", "engine_label_normalised", "query"))
        entry = (index, record, raw_bucket)
        content_hash = _index_key_component(
            _record_field(record, "content_hash"))
        captured = _record_field(record, "captured_on")
        if captured is None:
            date_key = None
        else:
            try:
                date_key = str(captured)
            except Exception:
                # A capture date whose string reading
                # raises, through a repr that raises,
                # stands entered under a fixed marker no
                # candidate date carries, so the raising
                # stands answered inside the recorded
                # error vocabulary at the selection and
                # never as a raw error to the caller at
                # the indexing.
                date_key = "citeline-unreadable-date"
        # Each sub index stands entered on its own: a
        # record whose content hash cannot be hashed
        # stands outside the hash index and still stands
        # in the date index, where a contradiction can
        # meet it, and a record whose bucket key cannot
        # be hashed stands in neither index and falls to
        # the overflow list.
        indexed = False
        try:
            sub_by_hash.setdefault(
                (bucket_key, content_hash), []).append(entry)
            indexed = True
        except Exception:
            pass
        try:
            sub_by_date.setdefault(
                (bucket_key, date_key), []).append(entry)
            indexed = True
        except Exception:
            pass
        if not indexed:
            overflow.append(entry)
        elif any(_overflow_field(value) for value in raw_bucket) \
                or _overflow_field(
                    _record_field(record, "content_hash")):
            # A record carrying a bucket field, or its
            # content hash, in a form that cannot be hashed
            # and is no string subclass stands in the
            # overflow list beside its sub index entries, so
            # the bucket field equality reading at the
            # selection below runs on it: its placeholder
            # key stands in the indexes, and no candidate
            # key carries that placeholder, so the indexes
            # alone would never compare it, while its
            # equality test can answer as the candidate, and
            # a record carrying such a field in a form whose
            # hash stands apart from its equality, or whose
            # hash raises outside TypeError, stands in the
            # overflow list on the same ground, its key
            # standing under its own hash or under the
            # placeholder where no candidate key reaches it.
            overflow.append(entry)

    for standing in running_standing:
        try:
            _index_standing(standing, _bucket_key(standing),
                            standing_index)
        except ProbeImportError:
            raise
        except Exception:
            # A keying reading at the indexing of the
            # standing records that raises in any form
            # stands answered inside the recorded error
            # vocabulary at the indexing itself, and
            # never as a raw error to the caller.
            _fail("DUPLICATE_IMPORT",
                  "a standing record keying reading raised "
                  "at the indexing of the standing records, "
                  "so the standing record stands answered "
                  "as a duplicate inside the recorded error "
                  "vocabulary and this import stores nothing")
        standing_index += 1
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
        body_hash = hashlib.sha256(body_bytes).hexdigest()
        answer_id = None
        if answer_id_prefix is not None:
            answer_id = "%s-%d" % (answer_id_prefix, len(records) + 1)

        def resolve_standing_id(value, record=None,
                                _base=answer_sequence_base,
                                _prepared=prepared_records):
            text = str(value)
            if "{sequence}" not in text:
                return text
            if record is None or not any(
                    record is item for item in _prepared):
                # The resolver judges only the identities
                # its own batch prepared, judged on the
                # record itself, never on its identity
                # string: a supplied standing identity
                # carrying the marker spelling stands as
                # supplied, even where a record this batch
                # prepared carries the same string, so no
                # supplied identity stands rewritten
                # against this batch base into a name no
                # entry stands under.
                return text
            # The prefix and its base stand tied together on
            # this surface as on the service route: where no
            # base stands supplied, the marker resolves
            # against the batch position itself, the sequence
            # this module surface knows, so the refusal names
            # a resolved identity and never the unresolved
            # marker.
            return _resolve_standing_marker(text, _base)

        candidate_raw = (
            slot_validated["kind"],
            slot_validated["engine_label_normalised"],
            slot_validated["query"])
        candidate_key = tuple(
            _index_key_component(value) for value in candidate_raw)
        selected = {}
        for entry in sub_by_hash.get((candidate_key, body_hash), ()):
            selected[entry[0]] = entry[1]
        for entry in sub_by_date.get(
                (candidate_key, slot_validated["captured_on"]), ()):
            selected[entry[0]] = entry[1]
        for entry in overflow:
            # A record standing in the overflow list in a
            # form the key reading cannot key stands
            # compared on its bucket fields by equality, so
            # a field standing equal to the candidate under
            # a form that cannot be hashed stands compared
            # as a plain field stands compared. The raw
            # bucket fields stand carried on the entry
            # itself, taken once at indexing, so the
            # reading costs one equality test per field per
            # slot.
            record = entry[1]
            raw_bucket = entry[2]
            try:
                bucket_matches = (
                    raw_bucket[0] == candidate_raw[0]
                    and raw_bucket[1] == candidate_raw[1]
                    and raw_bucket[2] == candidate_raw[2])
            except Exception:
                # A field whose equality test raises stands
                # answered inside the recorded error
                # vocabulary at the selection, as a field
                # whose hash raises stands answered on the
                # reading above, and never as a raw error
                # to the caller.
                _fail("DUPLICATE_IMPORT",
                      "a standing record bucket field equality "
                      "test raised, so the standing record "
                      "stands answered as a duplicate inside "
                      "the recorded error vocabulary and this "
                      "import stores nothing")
            if bucket_matches:
                selected[entry[0]] = record
        # The overflow list stands outside the sub index
        # selection, and a slot reads it only on the
        # bucket field equality reading above. A record
        # stands in the overflow list only where its
        # bucket key cannot be keyed even in the keyed
        # form the index reading states, and a record
        # whose bucket key keys stands in one index or
        # the other whatever its content hash form, so
        # its duplicate and contradiction judgements
        # stand exactly as they stood. The list and
        # mapping forms stand equal to no candidate
        # bucket field, which validation stands as
        # strings in every case, and the equality reading
        # passes over them at that unequal field in every
        # case.
        try:
            record = _record_from_body(
                slot_validated, body_text=body,
                raw_bytes=body_bytes,
                content_hash=body_hash,
                standing_records=[selected[index]
                                  for index in sorted(selected)],
                product=product,
                round=round, product_id=product_id,
                round_id=round_id,
                answer_id=answer_id,
                registry_version_at_import=
                registry_version_at_import,
                detector_version_at_import=
                detector_version_at_import,
                standing_id_resolver=resolve_standing_id)
        except ProbeImportError:
            raise
        except Exception:
            # The comparison the selection hands its
            # records runs the equality readings of the
            # standing records against the candidate, and a
            # field whose equality test raises there stands
            # answered inside the recorded error vocabulary
            # at the comparison, as it stands answered at
            # the selection above, and never as a raw error
            # to the caller.
            _fail("DUPLICATE_IMPORT",
                  "a standing record field equality test "
                  "raised at the duplicate comparison, so "
                  "the standing record stands answered as a "
                  "duplicate inside the recorded error "
                  "vocabulary and this import stores nothing")
        records.append(record)
        running_standing.append(record)
        prepared_records.append(record)
        record_key = tuple(_index_key_component(
            record.get(name)) for name in (
                "kind", "engine_label_normalised", "query"))
        _index_standing(record, record_key, standing_index)
        standing_index += 1
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
                 detector_version_at_import=None, home=None):
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
            detector_version_at_import=detector_version_at_import,
            home=home)
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
    stands named or its limits cannot be read.
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
    sheet.
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
            # line of its own.
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
    the cause named, never the occupied token.
    """
    # The count bounds read the limits in force for the
    # home the sheet is written for, in both directions, as
    # the import side of the same limits reads them. With
    # no home named, the brief defaults govern, as they
    # governed before this plumbing.
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
