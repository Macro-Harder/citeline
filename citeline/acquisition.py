"""Acquisition and extraction for Citeline, slice S2.

Perspective: what a thing is gets decided once, at the
boundary, and never re-decided downstream. This module is
that boundary for supplied pages. It opens one supplied
file once, reads it once, decides its format once (content
first, declared format second, extension last), extracts
its material once, and hands a PageSnapshot and an
ExtractedPage downstream. No later slice re-decides a
format, and this module never fetches, resolves, or
follows a link.

TextSegmentation stands inside this module as a named
sub-module (trade T-1): the segment_text operation and
the TextSegmentation class below are its surface, and
every consumer consumes its output and no other
segmentation.

Shapes stand at plan Section 5.1: PageSnapshot and
ExtractedPage. Input formats stand at plan Section 5.4.
Dates are call inputs (the audit_date argument), never
clock reads.
"""

import hashlib
import os
import re
import stat
import unicodedata
from html.parser import HTMLParser


__all__ = [
    "AcquisitionError",
    "TextSegmentation",
    "segment_text",
    "detect_format",
    "extract_page",
    "extract_page_reporting",
    "word_tokens",
    "count_words",
]


# ----------------------------------------------------------------
# Errors: one value per call, from the closed entry 13 vocabulary.
# ----------------------------------------------------------------

_TOKEN_ROWS = {
    "PAGE_EXTRACTION_FAILED": ("X-14", "usage", 2),
    "LIMIT_EXCEEDED": ("X-3", "integrity", 5),
    "SUPPLIED_PATH_UNSAFE": ("X-4", "integrity", 5),
    "VALIDATION_FAILED": ("X-5", "usage", 2),
}


try:
    from citeline.errors import CitelineError as _BaseError
except Exception:
    _BaseError = Exception


class AcquisitionError(_BaseError):
    """An acquisition refusal carrying its entry 13 token."""

    def __init__(self, token, message):
        row, precedence_class, exit_code = _TOKEN_ROWS.get(
            token, ("X-14", "usage", 2))
        self.precedence_class = precedence_class
        self.error_class = precedence_class
        if _BaseError is Exception:
            self.token = token
            self.error_value = token
            self.row = row
            self.exit_code = exit_code
            super().__init__("%s: %s" % (token, message))
        else:
            super().__init__("%s: %s" % (token, message),
                             row=row, token=token, exit_code=exit_code)


def _fail(token, message):
    raise AcquisitionError(token, message)


# Section 5.11 page side limits, in the units their rows state.
_PAGE_FILE_LIMIT = 2 * 1024 * 1024
_EXTRACTED_TEXT_LIMIT = 500000
_ELEMENT_EVENT_LIMIT = 100000
_NESTING_DEPTH_LIMIT = 100
_ATTRIBUTES_PER_ELEMENT_LIMIT = 100
_ATTRIBUTE_VALUE_LIMIT = 10000
_LINK_COUNT_LIMIT = 10000
_HEADING_COUNT_LIMIT = 10000
_REFERENCE_DEFINITION_LIMIT = 10000
_FRONT_MATTER_BLOCK_LIMIT = 16 * 1024
_FRONT_MATTER_VALUE_LIMIT = 4096

_FORMATS = ("markdown", "html", "text")
_EXTENSION_FORMATS = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
    ".txt": "text",
    ".text": "text",
}


# ----------------------------------------------------------------
# Journal access (slice S0). Snapshot registration and failure
# records write only through the journal append operation.
# ----------------------------------------------------------------

def _journal_or_none():
    try:
        from citeline import journal
    except Exception:
        return None
    return journal


def _journal_append(home, kind, payload, audit_date):
    journal = _journal_or_none()
    if journal is None:
        return None
    append = getattr(journal, "append_entry", None)
    if append is None:
        append = getattr(journal, "append", None)
    if append is None:
        return None
    try:
        return append(home, kind, payload, audit_date=audit_date)
    except TypeError:
        return append(home, kind, payload)


def _next_sequence(home):
    journal = _journal_or_none()
    if journal is not None:
        fold = getattr(journal, "fold", None)
        if fold is not None:
            try:
                entries = fold(home)
                if entries is not None:
                    return len(list(entries)) + 1
            except Exception:
                pass
    key = os.path.abspath(str(home))
    count = _LOCAL_SEQUENCE.get(key, 0) + 1
    _LOCAL_SEQUENCE[key] = count
    return count


_LOCAL_SEQUENCE = {}


# ----------------------------------------------------------------
# Word tokenisation (brief Section 5.1 item 154): words are
# alphanumeric tokens, a hyphenated form counts as its parts,
# and a decimal counts as one word.
# ----------------------------------------------------------------

def word_tokens(text):
    tokens = []
    current = []
    length = len(text)
    for index, ch in enumerate(text):
        if ch.isalnum():
            current.append(ch)
        elif (ch == "." and current and current[-1].isdigit()
              and index + 1 < length and text[index + 1].isdigit()):
            current.append(ch)
        else:
            if current:
                tokens.append("".join(current))
                current = []
    if current:
        tokens.append("".join(current))
    return tokens


def count_words(text):
    return len(word_tokens(text))


# ----------------------------------------------------------------
# TextSegmentation, the named sub-module inside this slice.
#
# Sentences: a sentence ends at a terminal mark plus a
# following space or the end of the text. The closed
# abbreviation list is Dr, Mr, Mrs, Ms, St, vs, e.g., and
# i.e., and a mark inside one of those abbreviations is not
# a boundary. A full stop between digits is not a boundary.
# An ellipsis counts as one terminal mark. Where a closing
# quotation mark intervenes, the boundary falls after the
# closing mark. Link and URL spans are masked before
# splitting, at equal length.
#
# Paragraphs: in Markdown and in text, a paragraph is a
# block of running text separated from the next block by a
# blank line. Leading and trailing blank lines form no
# paragraph, and a text holding no line breaks is one block.
# The HTML paragraph limb stands stopped on L-CC-2 in the
# plan; the block element reading used for HTML extraction
# in this module is recorded in the builder paper and
# claims no plan test for that limb.
#
# Sections: the section map, one entry per heading, with
# heading offset range and heading text as display only,
# plus a references section mark under item 160.
# ----------------------------------------------------------------

_ABBREVIATIONS = ("e.g.", "i.e.", "Dr.", "Mr.", "Mrs.", "Ms.", "St.", "vs.")
_CLOSING_MARKS = ('"', "'", "”", "’", ")", "]")


def _inline_link_spans(text):
    """Inline link and image spans with balanced targets.

    Returns a list of (start, end, label, target, is_image,
    target_start, target_end), where start and end bound the
    whole span and target_start and target_end bound the
    target inside it. A target may hold balanced
    parentheses, which stand as written; the span ends at
    the closing parenthesis that balances the opening one.
    An optional quoted title after the target is part of
    the span and not of the target.
    """
    spans = []
    index = 0
    length = len(text)
    while index < length:
        is_image = False
        label_start = index
        if text[index] == "!" and index + 1 < length \
                and text[index + 1] == "[":
            is_image = True
            label_start = index + 1
        if text[label_start] != "[":
            index += 1
            continue
        label_end = text.find("]", label_start + 1)
        if label_end < 0 or label_end + 1 >= length \
                or text[label_end + 1] != "(":
            index = label_start + 1
            continue
        depth = 1
        cursor = label_end + 2
        while cursor < length and depth:
            if text[cursor] == "(":
                depth += 1
            elif text[cursor] == ")":
                depth -= 1
            cursor += 1
        if depth:
            index = label_start + 1
            continue
        content = text[label_end + 2:cursor - 1]
        stripped = content.strip()
        target = stripped.split()[0] if stripped.split() else ""
        target_start = label_end + 2 + (
            len(content) - len(content.lstrip()))
        spans.append((index, cursor,
                      text[label_start + 1:label_end], target,
                      is_image, target_start,
                      target_start + len(target)))
        index = cursor
    return spans


def _mask_spans(text, fmt):
    chars = list(text)
    spans = []
    if fmt == "markdown":
        for span in _inline_link_spans(text):
            spans.append((span[5], span[6]))
        for match in re.finditer(r"\[[^\]]*\]\[([^\]]*)\]", text):
            spans.append((match.start(1), match.end(1)))
    for match in re.finditer(r"https?://[^\s<>\)\]]+", text):
        spans.append((match.start(), match.end()))
    for start, end in spans:
        for index in range(start, end):
            if chars[index] not in (" ", "\n", "\t"):
                chars[index] = "x"
    return "".join(chars)


def _split_sentences(text, fmt):
    masked = _mask_spans(text, fmt)
    sentences = []
    length = len(masked)
    start = 0
    index = 0
    while index < length:
        ch = masked[index]
        if ch not in ".!?":
            index += 1
            continue
        # A run of terminal marks, an ellipsis among them,
        # counts as one mark and ends at the run end.
        run_end = index
        while run_end + 1 < length and masked[run_end + 1] in ".!?":
            run_end += 1
        # A full stop between digits is not a boundary.
        if (ch == "." and run_end == index and index > 0
                and masked[index - 1].isdigit()
                and run_end + 1 < length
                and masked[run_end + 1].isdigit()):
            index = run_end + 1
            continue
        # A mark inside a closed abbreviation is not a
        # boundary, except where the abbreviation itself
        # closes the sentence at the end of the text.
        head = masked[max(0, run_end - 5):run_end + 1]
        is_abbrev = False
        for abbrev in _ABBREVIATIONS:
            if head.endswith(abbrev) or head.endswith(abbrev[:-1] + "."):
                if masked[max(0, run_end + 1 - len(abbrev)):run_end + 1] == abbrev:
                    is_abbrev = True
                    break
        tail = run_end + 1
        while tail < length and masked[tail] in _CLOSING_MARKS:
            tail += 1
        at_end = tail >= length
        followed = at_end or masked[tail] in (" ", "\n", "\t")
        if is_abbrev and not at_end:
            index = run_end + 1
            continue
        if not followed:
            index = run_end + 1
            continue
        piece = text[start:tail].strip()
        if piece:
            sentences.append(piece)
        start = tail
        while start < length and masked[start] in (" ", "\n", "\t"):
            start += 1
        index = start
    piece = text[start:].strip()
    if piece:
        sentences.append(piece)
    return sentences


def _clean_markdown_line(line):
    """Remove the Markdown marks of one line, keeping its text.

    Heading marks, blockquote marks, list marks, table pipes,
    link and image syntax (the label stands), reference
    definitions (dropped), and emphasis and code marks all
    stand removed. This cleaning is part of segmentation, so
    a sentence or a paragraph reads the same from a supplied
    Markdown file and from the extracted running text.
    """
    stripped = line.strip()
    if re.match(r"^\s{0,3}\[[^\]]+\]:\s*\S+", line):
        return ""
    stripped = re.sub(r"^#{1,6}[ \t]+", "", stripped)
    stripped = re.sub(r"^>[ \t]?", "", stripped)
    stripped = re.sub(r"^[-*+][ \t]+", "", stripped)
    stripped = re.sub(r"^\d+[.)][ \t]+", "", stripped)
    if stripped.startswith("|"):
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", cell or "---") for cell in cells):
            return ""
        stripped = " ".join(cells)
    for span in reversed(_inline_link_spans(stripped)):
        stripped = stripped[:span[0]] + span[2] + stripped[span[1]:]
    stripped = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", stripped)
    stripped = re.sub(r"`+[^`]*`+", "", stripped)
    stripped = re.sub(r"\*\*([^*]+)\*\*", r"\1", stripped)
    stripped = re.sub(r"__([^_]+)__", r"\1", stripped)
    stripped = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"\1", stripped)
    stripped = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", stripped)
    return stripped


def _clean_blocks(text, fmt):
    """Split a text into blank line blocks and clean each line.

    Returns a list of (block_text, is_heading) pairs, where
    block_text stands with its lines joined by a space and
    its whitespace collapsed. A Markdown block whose lines
    all stand as headings is a heading block.
    """
    source = text or ""
    if fmt == "markdown":
        kept = []
        in_fence = False
        for source_line in source.splitlines():
            marker = source_line.strip()
            if marker.startswith("```") or marker.startswith("~~~"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            kept.append(source_line)
        source = "\n".join(kept)
    raw_blocks = re.split(r"\r?\n[ \t]*\r?\n", source)
    blocks = []
    for raw in raw_blocks:
        lines = raw.splitlines()
        cleaned_lines = []
        heading_flags = []
        for line in lines:
            if fmt == "markdown":
                is_heading = bool(
                    re.match(r"^\s{0,3}#{1,6}[ \t]+\S", line))
                cleaned = _clean_markdown_line(line)
            elif fmt == "html":
                is_heading = False
                cleaned = re.sub(r"<[^>]+>", " ", line).strip()
            else:
                is_heading = False
                cleaned = line.strip()
            if cleaned:
                cleaned_lines.append(cleaned)
                heading_flags.append(is_heading)
        if not cleaned_lines:
            continue
        block_text = " ".join(" ".join(cleaned_lines).split())
        is_heading = bool(heading_flags) and all(heading_flags)
        blocks.append((block_text, is_heading))
    return blocks


def _split_paragraphs(text, fmt="text"):
    return [block for block, _flag in _clean_blocks(text, fmt)]


def _is_references_heading(text):
    return str(text).strip().casefold() in (
        "references", "reference", "bibliography", "sources",
        "works cited", "citations")


def _sections_from_headings(text, headings):
    """Headings carry text, and a start offset where one stands.

    A heading with no start stands located by its text in
    order, which is a reading of the heading list only.
    """
    sections = []
    cursor = 0
    normalised = []
    for heading in headings:
        if isinstance(heading, dict):
            htext = heading.get("text", heading.get("heading_text", ""))
        else:
            htext = str(heading)
        # A heading stands located by its text in the text
        # under segmentation, in order. Offsets a caller
        # carried from another text do not govern here,
        # because what a thing is stands decided in the
        # text segmentation actually runs over.
        found = text.find(str(htext), cursor) if htext else -1
        hstart = found if found >= 0 else cursor
        normalised.append((str(htext), int(hstart)))
        cursor = int(hstart) + len(str(htext))
    for index, (htext, hstart) in enumerate(normalised):
        hend = (normalised[index + 1][1] if index + 1 < len(normalised)
                else len(text))
        sections.append({
            "heading_text": htext if htext else None,
            "start": hstart,
            "end": hend,
            "references_section": _is_references_heading(htext),
        })
    if not sections:
        sections.append({
            "heading_text": None,
            "start": 0,
            "end": len(text),
            "references_section": False,
        })
    return sections


class TextSegmentation:
    """The one segmentation rule set, as a named sub-module."""

    @staticmethod
    def segment(text, format="text", headings=None):
        fmt = format if format in _FORMATS else "text"
        clean = text or ""
        blocks = _clean_blocks(clean, fmt)
        paragraphs = [block for block, _flag in blocks]
        heading_texts = set()
        if headings:
            for heading in headings:
                if isinstance(heading, dict):
                    heading_texts.add(str(
                        heading.get("text",
                                    heading.get("heading_text", ""))))
                else:
                    heading_texts.add(str(heading))
        sentences = []
        for block, is_heading in blocks:
            if is_heading or block in heading_texts:
                # A heading is not a sentence, and its text
                # never merges into the sentence that follows
                # it, because segmentation runs per block.
                continue
            sentences.extend(_split_sentences(block, fmt))
        if headings is None:
            headings = []
            if fmt == "markdown":
                for match in re.finditer(
                        r"(?m)^(#{1,6})[ \t]+(.+?)[ \t]*$", clean):
                    headings.append({
                        "text": match.group(2).strip(),
                        "level": len(match.group(1)),
                        "start": match.start(),
                    })
            elif fmt == "html":
                for match in re.finditer(
                        r"(?is)<h([1-6])[^>]*>(.*?)</h\1>", clean):
                    inner = re.sub(r"<[^>]+>", " ", match.group(2))
                    headings.append({
                        "text": " ".join(inner.split()),
                        "level": int(match.group(1)),
                        "start": match.start(),
                    })
        sections = _sections_from_headings(clean, headings)
        return {
            "sentences": sentences,
            "paragraphs": paragraphs,
            "sections": sections,
            "headings": headings,
        }


def segment_text(text, format="text", **kwargs):
    """Segment one text. The operation name the suite calls,
    standing over the TextSegmentation sub-module."""
    if "fmt" in kwargs:
        format = kwargs["fmt"]
    headings = kwargs.get("headings")
    return TextSegmentation.segment(text, format=format, headings=headings)


# ----------------------------------------------------------------
# Format detection. Content first, declared format second,
# extension last (plan Section 5.4). Detection looks at the
# file's own leading content, in file order, outside any
# fenced code block and outside any blockquote.
# ----------------------------------------------------------------

def _strip_detection_exclusions(text):
    """Remove fenced code blocks and blockquote lines, which
    do not count as content for detection."""
    out = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith(">"):
            continue
        out.append(line)
    return "\n".join(out)


def _content_format(text):
    visible = _strip_detection_exclusions(text)
    probe = visible.lstrip("\ufeff \t\r\n")
    low = probe.casefold()
    if low.startswith("<!doctype html") or low.startswith("<html"):
        return "html"
    if re.match(r"(?is)<(head|body|div|p|h[1-6]|table|ul|ol|span|a)\b",
                probe):
        return "html"
    for line in visible.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return "markdown"
        if stripped.startswith("|") and stripped.endswith("|"):
            return "markdown"
        if re.match(r"^[-*+]\s+\S", stripped):
            return "markdown"
        if re.search(r"\[[^\]]+\]\([^)]+\)", stripped):
            return "markdown"
        if stripped.startswith(">"):
            return "markdown"
        break
    return None


def _looks_binary(raw):
    if b"\x00" in raw:
        return True
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def detect_format(content, declared_format=None, filename=None, **kwargs):
    """Decide the format of one supplied page, once.

    Content stands first, an operator declared format
    second, and the file name extension last. Where no
    route decides, or the content stands ambiguous,
    detection fails on row X-14.
    """
    if declared_format is None:
        declared_format = kwargs.get("declared")
    if filename is None:
        filename = kwargs.get("name", kwargs.get("path"))
    if isinstance(content, (bytes, bytearray)):
        raw = bytes(content)
        if _looks_binary(raw):
            _fail("PAGE_EXTRACTION_FAILED",
                  "ambiguous format detection: the content is not "
                  "decodable page text in an admitted format")
        text = raw.decode("utf-8", errors="replace")
        if text.startswith("\ufeff"):
            text = text[1:]
    else:
        text = str(content)
    detected = _content_format(text)
    declared = None
    if declared_format is not None:
        declared = str(declared_format).strip().casefold()
        if declared in ("md", "markdown"):
            declared = "markdown"
        elif declared in ("htm", "html"):
            declared = "html"
        elif declared in ("txt", "text", "plain", "plain_text"):
            declared = "text"
        elif declared == "":
            declared = None
        else:
            _fail("PAGE_EXTRACTION_FAILED",
                  "ambiguous format detection: declared format %r "
                  "is not an admitted format" % (declared_format,))
    if detected is None and declared is not None:
        detected = declared
    if detected is None and filename:
        extension = os.path.splitext(str(filename))[1].casefold()
        detected = _EXTENSION_FORMATS.get(extension)
    if detected is None:
        _fail("PAGE_EXTRACTION_FAILED",
              "ambiguous format detection: content, declared "
              "format, and extension together decide no format")
    return {
        "detected_format": detected,
        "format": detected,
        "declared_format": declared,
    }


# ----------------------------------------------------------------
# Container rule. The container rule stands ahead of content
# detection (plan Section 5.4). XHTML stands marked where a
# doctype declaration naming XHTML, or the XHTML namespace
# on the root element, stands in the file's own leading
# structure, outside any fence and outside any blockquote.
# ----------------------------------------------------------------

def _check_containers(raw, text):
    visible = _strip_detection_exclusions(text)
    head = visible[:4096]
    if re.search(r"(?is)<!doctype[^>]*xhtml", head):
        _fail("PAGE_EXTRACTION_FAILED",
              "container failure: the file stands marked as XHTML")
    root = re.search(r"(?is)<html\b([^>]*)>", head)
    if root and "http://www.w3.org/1999/xhtml" in root.group(1):
        _fail("PAGE_EXTRACTION_FAILED",
              "container failure: the file stands marked as XHTML")
    low_head = head.casefold()
    if ("multipart/" in low_head
            and ("mime-version:" in low_head
                 or "content-type: multipart" in low_head)):
        _fail("PAGE_EXTRACTION_FAILED",
              "container failure: the file is an MHTML container")
    if text.startswith("WARC/"):
        _fail("PAGE_EXTRACTION_FAILED",
              "container failure: the file is a WARC container")


# ----------------------------------------------------------------
# The supplied file open protocol (boundary B1), in operating
# system terms: a stat that does not follow the final
# component, a non blocking no follow open, a device and
# inode match against the pre open stat, a hard link count
# of at most one, and one read of the opened handle.
# ----------------------------------------------------------------

def _read_supplied_file(page_path):
    path_text = str(page_path)
    try:
        pre = os.lstat(path_text)
    except OSError as exc:
        _fail("SUPPLIED_PATH_UNSAFE",
              "supplied path cannot be stated: %s" % (exc,))
    if stat.S_ISLNK(pre.st_mode):
        _fail("SUPPLIED_PATH_UNSAFE",
              "a supplied path that is itself a symbolic link "
              "is rejected")
    if not stat.S_ISREG(pre.st_mode):
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
    except OSError as exc:
        _fail("SUPPLIED_PATH_UNSAFE",
              "supplied path cannot be opened: %s" % (exc,))
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (pre.st_dev, pre.st_ino):
            _fail("SUPPLIED_PATH_UNSAFE",
                  "the opened handle does not match the pre "
                  "open stat")
        if not stat.S_ISREG(opened.st_mode):
            _fail("SUPPLIED_PATH_UNSAFE",
                  "the opened handle does not name a regular file")
        if opened.st_size > _PAGE_FILE_LIMIT:
            _fail("LIMIT_EXCEEDED",
                  "page file size limit is 2 MiB, with rejection "
                  "and no partial record")
        chunks = []
        total = 0
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > _PAGE_FILE_LIMIT:
                _fail("LIMIT_EXCEEDED",
                      "page file size limit is 2 MiB, with "
                      "rejection and no partial record")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


# ----------------------------------------------------------------
# Decoding. UTF-8 strictly, one leading byte order mark
# stripped once and noted, any further mark standing as an
# ordinary U+FEFF character in the decoded text.
# ----------------------------------------------------------------

def _front_matter(text, fmt, notes):
    """Front matter handling. Front matter that fails the
    D17 control set fails closed: a tag construct standing
    in front matter is that failure in this module."""
    if fmt != "markdown":
        return text
    if not text.startswith("---"):
        return text
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for index in range(1, len(lines)):
        if lines[index].strip() in ("---", "..."):
            block = "\n".join(lines[1:index])
            if len(block.encode("utf-8")) > _FRONT_MATTER_BLOCK_LIMIT:
                _fail("LIMIT_EXCEEDED",
                      "front matter block size limit is 16 KiB, "
                      "with rejection and no partial record")
            for block_line in lines[1:index]:
                if ":" in block_line:
                    value = block_line.split(":", 1)[1].strip()
                    if len(value) > _FRONT_MATTER_VALUE_LIMIT:
                        _fail("LIMIT_EXCEEDED",
                              "front matter value length per key "
                              "limit is 4,096 characters, with "
                              "rejection and no partial record")
            if re.search(r"(?m)^[^#\n]*:\s*(!|&|\*|%)", block) or \
                    re.search(r"<[A-Za-z][^>]*>", block):
                _fail("PAGE_EXTRACTION_FAILED",
                      "front matter fails the D17 control set")
            notes.append("front_matter")
            return "\n".join(lines[index + 1:])
    return text


# ----------------------------------------------------------------
# Date strings. Each stands with its position in the
# running text.
# ----------------------------------------------------------------

_DATE_PATTERNS = (
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{4}/\d{2}/\d{2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b"),
    re.compile(r"\b(?:January|February|March|April|May|June|July|"
               r"August|September|October|November|December) "
               r"\d{1,2}, \d{4}\b"),
    re.compile(r"\b\d{1,2} (?:January|February|March|April|May|June|"
               r"July|August|September|October|November|December) "
               r"\d{4}\b"),
)


def _date_strings(text):
    found = []
    seen = set()
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            key = (match.start(), match.end())
            if key in seen:
                continue
            seen.add(key)
            found.append({
                "text": match.group(0),
                "start": match.start(),
                "end": match.end(),
                "position": match.start(),
            })
    found.sort(key=lambda item: item["start"])
    return found


# ----------------------------------------------------------------
# HTML extraction, over the standard library parser.
# ----------------------------------------------------------------

_VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
_BLOCK_ELEMENTS = {
    "p", "div", "section", "article", "header", "footer", "main",
    "aside", "nav", "h1", "h2", "h3", "h4", "h5", "h6", "li",
    "blockquote", "pre", "td", "th", "caption", "figcaption",
    "figure", "dd", "dt",
}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _check_script_style(text):
    low = text.casefold()
    for tag in ("script", "style"):
        opens = len(re.findall(r"<%s(\s[^>]*)?>" % tag, low))
        closes = len(re.findall(r"</%s\s*>" % tag, low))
        if opens > closes:
            _fail("PAGE_EXTRACTION_FAILED",
                  "an unclosed %s element fails closed" % tag)
        if closes > opens:
            _fail("PAGE_EXTRACTION_FAILED",
                  "content inside a %s element stands ambiguous "
                  "and fails closed" % tag)
        # A closing tag inside a script or style body, in a
        # string or otherwise, leaves the body ambiguous
        # where material follows the first close and then a
        # second close stands. The count rule above covers
        # that case; a lone close with trailing markup and
        # no second close stands read as written.


class _PageHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.events = 0
        self.max_depth = 0
        self.stack = []
        self.notes = []
        self.blocks = []
        self.headings = []
        self.links = []
        self.blockquotes = []
        self.lists = []
        self.tables = []
        self.canonical_link_element = None
        self.meta_robots = None
        self._buffer = []
        self._buffer_kind = None
        self._heading = None
        self._link = None
        self._quote_stack = []
        self._list_stack = []
        self._table = None
        self._row = None
        self._cell = None
        self._table_contexts = []
        self._skip_depth = 0
        self._title_depth = 0

    def _check_attrs(self, attrs):
        if len(attrs) > _ATTRIBUTES_PER_ELEMENT_LIMIT:
            _fail("LIMIT_EXCEEDED",
                  "attributes per element limit is 100, with "
                  "rejection and no partial record")
        for _name, value in attrs:
            if value is not None and len(value) > _ATTRIBUTE_VALUE_LIMIT:
                _fail("LIMIT_EXCEEDED",
                      "attribute value length limit is 10,000 "
                      "characters, with rejection and no "
                      "partial record")

    def _note_break(self):
        if self._heading is not None:
            self._heading["parts"].append(" ")
        if self._link is not None:
            self._link["parts"].append(" ")
        for quote in self._quote_stack:
            quote["parts"].append(" ")
        if self._list_stack and self._list_stack[-1]["current"] is not None:
            self._list_stack[-1]["current"].append(" ")
        if self._cell is not None:
            self._cell.append(" ")
        if self._buffer is not None:
            self._buffer.append(" ")

    def _flush_block(self):
        if self._buffer is None:
            return
        text = " ".join("".join(self._buffer).split())
        if text:
            self.blocks.append(text)
        self._buffer = []
        self._buffer_kind = None

    def handle_starttag(self, tag, attrs):
        self.events += 1
        if self.events > _ELEMENT_EVENT_LIMIT:
            _fail("LIMIT_EXCEEDED",
                  "element or tag events per page limit is 100,000")
        self._check_attrs(attrs)
        if tag == "br":
            if not self._skip_depth and not self._title_depth:
                self._note_break()
            return
        attr = {}
        for name, value in attrs:
            attr[name] = value
            if value is None:
                self.notes.append("attribute_without_value")
        if tag not in _VOID_ELEMENTS:
            self.stack.append(tag)
            if len(self.stack) > _NESTING_DEPTH_LIMIT:
                _fail("LIMIT_EXCEEDED", "nesting depth limit is 100")
            self.max_depth = max(self.max_depth, len(self.stack))
        if tag in ("script", "style"):
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._title_depth += 1
            return
        if tag == "link":
            rel = (attr.get("rel") or "").casefold()
            if "canonical" in rel.split():
                self.canonical_link_element = {
                    "rel": attr.get("rel"),
                    "href": attr.get("href"),
                    "target": attr.get("href"),
                    "text": attr.get("href"),
                }
            return
        if tag == "meta":
            if (attr.get("name") or "").casefold() == "robots":
                self.meta_robots = attr.get("content")
            return
        if self._title_depth:
            return
        if tag in _BLOCK_ELEMENTS:
            self._flush_block()
            self._buffer_kind = tag
        if tag in _HEADING_TAGS:
            self._heading = {"level": int(tag[1]), "parts": []}
        elif tag == "a":
            self._link = {"target": attr.get("href"), "parts": []}
        elif tag == "blockquote":
            self._quote_stack.append({"parts": []})
        elif tag in ("ul", "ol"):
            self._list_stack.append({"items": [], "current": None})
        elif tag == "li":
            if self._list_stack:
                self._list_stack[-1]["current"] = []
        elif tag == "table":
            self._table_contexts.append(
                (self._table, self._row, self._cell))
            self._table = {"rows": [], "start": len(self.blocks)}
            self._row = None
            self._cell = None
        elif tag == "tr":
            if self._table is not None:
                self._row = []
        elif tag in ("td", "th"):
            if self._row is not None:
                self._cell = []

    def handle_startendtag(self, tag, attrs):
        self.events += 1
        if self.events > _ELEMENT_EVENT_LIMIT:
            _fail("LIMIT_EXCEEDED",
                  "element or tag events per page limit is 100,000")
        self._check_attrs(attrs)
        if tag == "br":
            if not self._skip_depth and not self._title_depth:
                self._note_break()
            return
        if tag in _VOID_ELEMENTS:
            attr = dict(attrs)
            if tag == "link":
                rel = (attr.get("rel") or "").casefold()
                if "canonical" in rel.split():
                    self.canonical_link_element = {
                        "rel": attr.get("rel"),
                        "href": attr.get("href"),
                        "target": attr.get("href"),
                        "text": attr.get("href"),
                    }
            if tag == "meta" and (attr.get("name") or "").casefold() == "robots":
                self.meta_robots = attr.get("content")

    def handle_endtag(self, tag):
        self.events += 1
        if self.events > _ELEMENT_EVENT_LIMIT:
            _fail("LIMIT_EXCEEDED",
                  "element or tag events per page limit is 100,000")
        if tag in ("script", "style"):
            if self._skip_depth:
                self._skip_depth -= 1
            if tag in self.stack:
                while self.stack and self.stack[-1] != tag:
                    self.stack.pop()
                if self.stack:
                    self.stack.pop()
            return
        if self._skip_depth:
            return
        if tag == "title":
            if self._title_depth:
                self._title_depth -= 1
            if tag in self.stack:
                while self.stack and self.stack[-1] != tag:
                    self.stack.pop()
                if self.stack:
                    self.stack.pop()
            return
        if self._title_depth:
            return
        if tag in _HEADING_TAGS and self._heading is not None:
            text = " ".join("".join(self._heading["parts"]).split())
            if text:
                self.headings.append({
                    "text": text,
                    "level": self._heading["level"],
                })
            self._heading = None
        elif tag == "a" and self._link is not None:
            text = " ".join("".join(self._link["parts"]).split())
            if self._link["target"] is not None:
                self.links.append({
                    "text": text,
                    "target": self._link["target"],
                })
            self._link = None
        elif tag == "blockquote" and self._quote_stack:
            quote = self._quote_stack.pop()
            text = " ".join("".join(quote["parts"]).split())
            if text:
                self.blockquotes.append({"text": text})
        elif tag == "li":
            if self._list_stack and self._list_stack[-1]["current"] is not None:
                item = " ".join(
                    "".join(self._list_stack[-1]["current"]).split())
                if item:
                    self._list_stack[-1]["items"].append(item)
                self._list_stack[-1]["current"] = None
        elif tag in ("ul", "ol"):
            if self._list_stack:
                done = self._list_stack.pop()
                if done["items"]:
                    self.lists.append({"items": done["items"]})
        elif tag in ("td", "th"):
            if self._cell is not None and self._row is not None:
                self._row.append(" ".join("".join(self._cell).split()))
                self._cell = None
        elif tag == "tr":
            if self._row is not None and self._table is not None:
                if self._row:
                    self._table["rows"].append(self._row)
                self._row = None
        elif tag == "table":
            if self._table is not None:
                if self._table["rows"]:
                    rows = self._table["rows"]
                    self.tables.append({
                        "rows": rows,
                        "text": "\n".join(" ".join(row) for row in rows),
                    })
                if self._table_contexts:
                    self._table, self._row, self._cell = \
                        self._table_contexts.pop()
                else:
                    self._table = None
                    self._row = None
                    self._cell = None
        if tag in _BLOCK_ELEMENTS:
            self._flush_block()
        if tag in _VOID_ELEMENTS:
            return
        if tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.stack.pop()
                self.notes.append("unclosed_inline_element")
            if self.stack:
                self.stack.pop()
        else:
            self.notes.append("stray_closing_tag")

    def handle_data(self, data):
        if self._skip_depth or self._title_depth:
            return
        if self._heading is not None:
            self._heading["parts"].append(data)
        if self._link is not None:
            self._link["parts"].append(data)
        for quote in self._quote_stack:
            quote["parts"].append(data)
        if self._list_stack and self._list_stack[-1]["current"] is not None:
            self._list_stack[-1]["current"].append(data)
        if self._cell is not None:
            self._cell.append(data)
        if self._buffer is not None:
            self._buffer.append(data)


def _extract_html(text, notes):
    _check_script_style(text)
    parser = _PageHTMLParser()
    parser.feed(text)
    parser.close()
    parser._flush_block()
    notes.extend(parser.notes)
    running_text = "\n\n".join(parser.blocks)
    headings = []
    cursor = 0
    for heading in parser.headings:
        found = running_text.find(heading["text"], cursor)
        start = found if found >= 0 else cursor
        headings.append({
            "text": heading["text"],
            "level": heading["level"],
            "start": start,
        })
        cursor = start + len(heading["text"])
    links = []
    cursor = 0
    for link in parser.links:
        found = running_text.find(link["text"], cursor) if link["text"] else -1
        start = found if found >= 0 else cursor
        links.append({
            "text": link["text"],
            "target": link["target"],
            "start": start,
            "end": start + len(link["text"]),
        })
        if found >= 0:
            cursor = start + len(link["text"])
    blockquotes = []
    cursor = 0
    for quote in parser.blockquotes:
        found = running_text.find(quote["text"], cursor)
        start = found if found >= 0 else cursor
        blockquotes.append({
            "text": quote["text"],
            "start": start,
            "end": start + len(quote["text"]),
        })
        if found >= 0:
            cursor = start + len(quote["text"])
    lists = []
    for item_list in parser.lists:
        first = item_list["items"][0] if item_list["items"] else ""
        found = running_text.find(first) if first else -1
        lists.append({
            "items": item_list["items"],
            "start": found if found >= 0 else 0,
        })
    return {
        "running_text": running_text,
        "headings": headings,
        "links": links,
        "blockquotes": blockquotes,
        "lists": lists,
        "tables": parser.tables,
        "canonical_link_element": parser.canonical_link_element,
        "meta_robots": parser.meta_robots,
        "segmentation_headings": headings,
    }


# ----------------------------------------------------------------
# Markdown extraction.
# ----------------------------------------------------------------

def _extract_markdown(text, notes):
    lines = text.splitlines()
    headings = []
    links = []
    blockquotes = []
    lists = []
    tables = []
    blocks = []
    references = {}
    reference_count = 0
    for line in lines:
        match = re.match(r"^\s{0,3}\[([^\]]+)\]:\s*(\S+)", line)
        if match:
            reference_count += 1
            if reference_count > _REFERENCE_DEFINITION_LIMIT:
                _fail("LIMIT_EXCEEDED",
                      "reference definitions per file limit is "
                      "10,000, with rejection and no partial record")
            key = match.group(1)
            if key in references:
                notes.append("duplicate_markdown_reference")
            else:
                references[key] = match.group(2)
    in_fence = False
    current_list = None
    current_table = []
    offset = 0
    line_offsets = []
    for line in lines:
        line_offsets.append(offset)
        offset += len(line) + 1

    def flush_list():
        nonlocal current_list
        if current_list:
            lists.append(current_list)
        current_list = None

    def flush_table():
        nonlocal current_table
        if current_table:
            rows = []
            for row_line in current_table:
                cells = [cell.strip() for cell in
                         row_line.strip().strip("|").split("|")]
                if all(re.fullmatch(r":?-{3,}:?", cell or "---")
                       for cell in cells):
                    continue
                rows.append(cells)
            if rows:
                tables.append({
                    "rows": rows,
                    "text": "\n".join(" ".join(row) for row in rows),
                })
        current_table = []

    # Blocks stand grouped as the source groups them: a
    # blank line closes a block, a heading stands as its
    # own block, and list and table lines join the block
    # they stand in. Segmentation over the running text
    # then yields the same paragraphs as segmentation over
    # the supplied file, which the pinned before checks
    # rule requires.
    current_block = []

    def flush_block():
        nonlocal current_block
        if current_block:
            blocks.append("\n".join(current_block))
        current_block = []

    skip_until = -1
    for idx, line in enumerate(lines):
        if idx <= skip_until:
            continue
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            flush_list()
            flush_table()
            continue
        if in_fence:
            continue
        if not stripped:
            flush_list()
            flush_table()
            flush_block()
            continue
        if re.match(r"^</?[A-Za-z][A-Za-z0-9]*(\s[^>]*)?>", stripped):
            flush_list()
            flush_table()
            html_lines = [line]
            ahead = idx + 1
            while ahead < len(lines) and lines[ahead].strip():
                html_lines.append(lines[ahead])
                ahead += 1
            html_parts = _extract_html("\n".join(html_lines), notes)
            for html_link in html_parts["links"]:
                links.append({"text": html_link["text"],
                              "target": html_link["target"]})
            for html_heading in html_parts["headings"]:
                headings.append({
                    "text": html_heading["text"],
                    "level": html_heading["level"],
                    "start": line_offsets[idx],
                })
            blockquotes.extend(html_parts["blockquotes"])
            lists.extend(html_parts["lists"])
            tables.extend(html_parts["tables"])
            if html_parts["running_text"]:
                current_block.append(html_parts["running_text"])
            skip_until = ahead - 1
            continue
        heading = re.match(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$", line)
        if heading:
            flush_list()
            flush_table()
            flush_block()
            htext = heading.group(2).strip()
            headings.append({
                "text": htext,
                "level": len(heading.group(1)),
                "start": line_offsets[idx],
            })
            blocks.append(htext)
            continue
        if re.match(r"^\s{0,3}\[[^\]]+\]:\s*\S+", line):
            continue
        if stripped.startswith(">"):
            quote_text = stripped.lstrip(">").strip()
            quote_text = _markdown_inline(
                quote_text, links, references, notes, line_offsets[idx])
            blockquotes.append({"text": quote_text})
            current_block.append(quote_text)
            continue
        item = re.match(r"^\s*[-*+]\s+(.+)$", line) or \
            re.match(r"^\s*\d+[.)]\s+(.+)$", line)
        if item:
            flush_table()
            if current_list is None:
                current_list = {"items": [], "start": line_offsets[idx]}
            item_text = _markdown_inline(item.group(1), links, references,
                                         notes, line_offsets[idx])
            current_list["items"].append(item_text)
            current_block.append(item_text)
            continue
        if stripped.startswith("|") and stripped.endswith("|") and "|" in stripped[1:]:
            flush_list()
            current_table.append(line)
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", cell or "---")
                       for cell in cells):
                current_block.append(" ".join(cells))
            continue
        flush_list()
        flush_table()
        current_block.append(_markdown_inline(
            stripped, links, references, notes, line_offsets[idx]))
    flush_list()
    flush_table()
    flush_block()
    running_text = "\n\n".join(blocks)
    # Link offsets stand read against the running text, in
    # order, after the blocks stand joined.
    ordered_links = []
    cursor = 0
    for link in links:
        found = running_text.find(link["text"], cursor) if link["text"] else -1
        start = found if found >= 0 else cursor
        ordered_links.append({
            "text": link["text"],
            "target": link["target"],
            "start": start,
            "end": start + len(link["text"]),
        })
        if found >= 0:
            cursor = start + len(link["text"])
    ordered_quotes = []
    cursor = 0
    for quote in blockquotes:
        found = running_text.find(quote["text"], cursor)
        start = found if found >= 0 else cursor
        ordered_quotes.append({
            "text": quote["text"],
            "start": start,
            "end": start + len(quote["text"]),
        })
        if found >= 0:
            cursor = start + len(quote["text"])
    return {
        "running_text": running_text,
        "headings": headings,
        "links": ordered_links,
        "blockquotes": ordered_quotes,
        "lists": lists,
        "tables": tables,
        "canonical_link_element": None,
        "meta_robots": None,
        "segmentation_headings": headings,
    }


def _markdown_inline(text, links, references, notes, offset):
    cleaned = re.sub(r"`+[^`]*`+", "", text)
    if cleaned != text:
        text = " ".join(cleaned.split())
    spans = _inline_link_spans(text)
    if spans:
        pieces = []
        cursor = 0
        for span in spans:
            pieces.append(text[cursor:span[0]])
            pieces.append(span[2])
            if not span[4]:
                links.append({"text": span[2], "target": span[3]})
            cursor = span[1]
        pieces.append(text[cursor:])
        text = "".join(pieces)

    def ref_repl(match):
        label, ref = match.group(1), match.group(2)
        key = ref if ref else label
        if key in references:
            links.append({"text": label, "target": references[key]})
        else:
            notes.append("unresolved_markdown_reference")
        return match.group(0) if key not in references else label

    text = re.sub(r"\[([^\]]+)\]\[([^\]]*)\]", ref_repl, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)
    return text


# ----------------------------------------------------------------
# Text extraction: the file as written, with no structure.
# ----------------------------------------------------------------

def _extract_text(text, notes):
    return {
        "running_text": text.strip(),
        "headings": [],
        "links": [],
        "blockquotes": [],
        "lists": [],
        "tables": [],
        "canonical_link_element": None,
        "meta_robots": None,
        "segmentation_headings": [],
    }


# ----------------------------------------------------------------
# Extraction end states and the page operations.
# ----------------------------------------------------------------

def _build_extracted(fmt, text, notes):
    if fmt == "html":
        parts = _extract_html(text, notes)
    elif fmt == "markdown":
        parts = _extract_markdown(text, notes)
    else:
        parts = _extract_text(text, notes)
    running_text = parts["running_text"]
    if len(running_text) > _EXTRACTED_TEXT_LIMIT:
        _fail("LIMIT_EXCEEDED",
              "extracted text length per page limit is 500,000 "
              "characters, with rejection and no partial record")
    if len(parts["links"]) > _LINK_COUNT_LIMIT:
        _fail("LIMIT_EXCEEDED",
              "link count per page limit is 10,000, with "
              "rejection and no partial record")
    headings = parts["headings"]
    if len(headings) > _HEADING_COUNT_LIMIT:
        _fail("LIMIT_EXCEEDED",
              "heading count per page limit is 10,000, with "
              "rejection and no partial record")
    seen_texts = []
    for heading in headings:
        if heading["text"] in seen_texts:
            notes.append("duplicate_heading")
        seen_texts.append(heading["text"])
    segmentation = TextSegmentation.segment(
        running_text, format=fmt, headings=parts["segmentation_headings"])
    extracted = {
        "running_text": running_text,
        "sentences": segmentation["sentences"],
        "paragraphs": segmentation["paragraphs"],
        "sections": segmentation["sections"],
        "headings": headings,
        "links": parts["links"],
        "blockquotes": parts["blockquotes"],
        "lists": parts["lists"],
        "tables": parts["tables"],
        "date_strings": _date_strings(running_text),
        "canonical_link_element": parts["canonical_link_element"],
        "meta_robots": parts["meta_robots"],
        "word_count": count_words(running_text),
        "extracted_text_length": len(running_text),
        "extraction_notes": list(notes),
    }
    return extracted


def _extract_inner(home, product_id, page_path, declared_format,
                   audit_date, evaluated_page_path,
                   capture_date_asserted, capture_method_asserted):
    raw = _read_supplied_file(page_path)
    notes = []
    if raw.startswith(b"\xef\xbb\xbf"):
        notes.append("bom_stripped")
    try:
        decoded_once = raw.decode("utf-8")
    except UnicodeDecodeError:
        _fail("PAGE_EXTRACTION_FAILED",
              "undecodable bytes and invalid UTF-8 fail closed")
    text = decoded_once
    if text.startswith("\ufeff"):
        text = text[1:]
    _check_containers(raw, text)
    detection = detect_format(
        raw, declared_format=declared_format, filename=str(page_path))
    fmt = detection["detected_format"]
    declared = detection["declared_format"]
    if declared is not None and declared != fmt:
        notes.append("format_disagreement")
    text = _front_matter(text, fmt, notes)
    extracted = _build_extracted(fmt, text, notes)
    running = extracted["running_text"]
    if running.strip() == "":
        outcome = "empty"
        reason_code = "EXT_EMPTY"
    else:
        outcome = "ok"
        reason_code = None
    sequence = _next_sequence(home)
    snapshot = {
        "snapshot_id": "snap-%d" % sequence,
        "product_id": product_id,
        "supplied_path": str(page_path),
        "evaluated_page_path": evaluated_page_path or "/",
        "path_defaulted": evaluated_page_path is None,
        "format": fmt,
        "declared_format": declared,
        "detected_format": fmt,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "byte_size": len(raw),
        "capture_date_asserted": capture_date_asserted,
        "capture_method_asserted": capture_method_asserted,
        "source_or_conversion_status": (
            "source" if fmt == "markdown" else None),
        "converter": None,
        "html_variant_claim": None,
        "extraction_outcome": outcome,
        "reason_code": reason_code,
        "is_product_page": False,
    }
    if outcome == "empty":
        snapshot["extraction_outcome"] = "empty"
        snapshot["reason_code"] = "EXT_EMPTY"
    return {"snapshot": snapshot, "extracted": extracted}


def extract_page(home, product_id=None, page_path=None, audit_date=None,
                 **kwargs):
    """Extract one supplied page file, once.

    On success the snapshot stands registered through the
    journal, where a journal stands available, and the
    return carries the snapshot and the extracted page. On
    failure nothing stands stored and the call fails with
    a recorded error value on the raised error.
    """
    if page_path is None:
        page_path = kwargs.get("page_file", kwargs.get("path"))
    if product_id is None:
        product_id = kwargs.get("product", kwargs.get("product_name"))
    declared_format = kwargs.get("declared_format", kwargs.get("declared"))
    evaluated_page_path = kwargs.get("evaluated_page_path")
    result = _extract_inner(
        home, product_id, page_path, declared_format, audit_date,
        evaluated_page_path,
        kwargs.get("capture_date_asserted"),
        kwargs.get("capture_method_asserted"))
    snapshot = result["snapshot"]
    if _journal_or_none() is not None:
        _journal_append(home, "snapshot_registered",
                        dict(snapshot), audit_date)
    return result


def extract_page_reporting(home, product_id=None, page_path=None,
                           audit_date=None, **kwargs):
    """The reporting form of extraction.

    A success returns the snapshot and the extracted page
    with an empty failure record list. A failure the process
    lives to report returns exactly one failure record and
    no snapshot, where the chain accepts appends; on the
    excepted cases (a barred chain, a chain at cap, and a
    contended invocation) no failure record can stand, and
    the failure record list stands empty.
    """
    try:
        result = extract_page(home, product_id=product_id,
                              page_path=page_path, audit_date=audit_date,
                              **kwargs)
    except Exception as exc:
        token = getattr(exc, "error_value", None) or \
            getattr(exc, "token", None) or "PAGE_EXTRACTION_FAILED"
        record = {
            "operation": "extract_page",
            "error_value": token,
            "subject_identity": str(page_path),
            "date": audit_date,
            "rule_fired": token,
        }
        journal = _journal_or_none()
        if journal is None:
            return {"snapshot": None, "extracted": None,
                    "failure_records": [record]}
        try:
            _journal_append(home, "failure_record", dict(record),
                            audit_date)
        except Exception:
            return {"snapshot": None, "extracted": None,
                    "failure_records": []}
        return {"snapshot": None, "extracted": None,
                "failure_records": [record]}
    result = dict(result)
    result["failure_records"] = []
    return result
