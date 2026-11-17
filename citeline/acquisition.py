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

import bisect
import hashlib
import json
import os
import re
import stat
import unicodedata
from html import unescape as _unescape
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
_FRONT_MATTER_KEY_LIMIT = 100
_FRONT_MATTER_VALUE_LIMIT = 4096
_FRONT_MATTER_JSON_DEPTH_LIMIT = 100

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


def _paren_matches(text):
    """Balanced parenthesis matches over one text, in one
    pass: a map from each opening parenthesis position to
    the position of the closing parenthesis that balances
    it. A backslash escaped character stands outside the
    balance, and a parenthesis inside a quoted span that
    opens after a space inside parentheses stands outside
    it, on the same terms the link target scan states.
    An opening parenthesis with no entry in the map has
    no balanced close anywhere in the text.
    """
    matches = {}
    stack = []
    quote = None
    index = 0
    length = len(text)
    while index < length:
        ch = text[index]
        if ch == "\\" and index + 1 < length:
            index += 2
            continue
        if quote is not None:
            if ch == quote:
                quote = None
            index += 1
            continue
        if ch in ("\"", "'") and stack and index > 0 \
                and text[index - 1] in (" ", "\t"):
            quote = ch
            index += 1
            continue
        if ch == "(":
            stack.append(index)
        elif ch == ")" and stack:
            matches[stack.pop()] = index
        index += 1
    return matches


def _inline_link_spans(text):
    """Inline link and image spans with balanced targets.

    Returns a list of (start, end, label, target, is_image,
    target_start, target_end), where start and end bound the
    whole span and target_start and target_end bound the
    target inside it. A target may hold balanced
    parentheses, which stand as written; the span ends at
    the closing parenthesis that balances the opening one.
    An optional quoted title after the target is part of
    the span and not of the target. A parenthesis inside a
    quoted title, and a parenthesis preceded by a
    backslash, stand outside the balance.
    """
    spans = []
    index = 0
    length = len(text)
    # The closing bracket positions and the balanced
    # parenthesis matches stand computed once, in one
    # pass each, before the scan. A bracket whose label
    # never closes, and a target whose opening parenthesis
    # has no balanced close, are then decided in one
    # lookup each, so a line of unmatched opening brackets
    # costs one pass over the line, not one rescan of the
    # remainder per bracket.
    close_positions = [pos for pos, ch in enumerate(text)
                       if ch == "]"]
    paren_matches = _paren_matches(text)
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
        bracket_pos = bisect.bisect_left(
            close_positions, label_start + 1)
        if bracket_pos >= len(close_positions):
            break
        label_end = close_positions[bracket_pos]
        if label_end + 1 >= length \
                or text[label_end + 1] != "(":
            index = label_start + 1
            continue
        close_paren = paren_matches.get(label_end + 1)
        if close_paren is None:
            index = label_start + 1
            continue
        cursor = close_paren + 1
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


def _reference_link_spans(text, allow_empty_label=False):
    """Reference style link spans, found in one scan.

    Returns a list of (start, end, label, reference,
    reference_start, reference_end), where start and end
    bound the whole span. The search walks closing
    bracket positions by bisection rather than by a
    pattern that rescans the remainder of the text from
    every opening bracket, so a text of unmatched opening
    brackets costs one pass, not one rescan per bracket.
    The span form is the one the pattern form states: a
    label of one or more non bracket characters, then a
    reference in brackets, the reference possibly empty.
    """
    close_positions = [pos for pos, ch in enumerate(text)
                       if ch == "]"]
    spans = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] != "[":
            index += 1
            continue
        label_pos = bisect.bisect_left(close_positions, index + 1)
        if label_pos >= len(close_positions):
            break
        label_end = close_positions[label_pos]
        if (label_end == index + 1 and not allow_empty_label) \
                or label_end + 1 >= length \
                or text[label_end + 1] != "[":
            index += 1
            continue
        ref_pos = bisect.bisect_left(
            close_positions, label_end + 2)
        if ref_pos >= len(close_positions):
            index += 1
            continue
        ref_end = close_positions[ref_pos]
        spans.append((index, ref_end + 1,
                      text[index + 1:label_end],
                      text[label_end + 2:ref_end],
                      label_end + 2, ref_end))
        index = ref_end + 1
    return spans


def _mask_spans(text, fmt):
    chars = list(text)
    spans = []
    if fmt == "markdown":
        for span in _inline_link_spans(text):
            spans.append((span[5], span[6]))
        for span in _reference_link_spans(
                text, allow_empty_label=True):
            spans.append((span[4], span[5]))
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
    for span in reversed(_reference_link_spans(stripped)):
        stripped = stripped[:span[0]] + span[2] + stripped[span[1]:]
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

    A heading carrying a start stands located by that start:
    the start is the position of its own heading block in the
    text under segmentation, carried in extraction order, and
    it governs over any earlier standing of the same words in
    body prose. A heading with no start stands located by its
    text in order, which is a reading of the heading list only.
    """
    sections = []
    cursor = 0
    normalised = []
    for heading in headings:
        carried = None
        if isinstance(heading, dict):
            htext = heading.get("text", heading.get("heading_text", ""))
            carried = heading.get("start")
        else:
            htext = str(heading)
        hstart = None
        if carried is not None:
            try:
                candidate = int(carried)
            except (TypeError, ValueError):
                candidate = None
            if candidate is not None and 0 <= candidate <= len(text):
                hstart = candidate
        if hstart is None:
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
                        "start": match.start(2),
                    })
            elif fmt == "html":
                for match in re.finditer(
                        r"(?is)<h([1-6])[^>]*>(.*?)</h\1>", clean):
                    inner = re.sub(r"<[^>]+>", " ", match.group(2))
                    headings.append({
                        "text": " ".join(inner.split()),
                        "level": int(match.group(1)),
                        "start": match.start(2),
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
    do not count as content for detection.

    A line opening with the blockquote mark stands as a
    blockquote line only where the mark opens a blockquote.
    Where the mark stands as the closing bracket of a tag
    the lines above opened, the line stands as the
    continuation of that tag and counts as content: the
    exclusion reads the text as markup, tracking whether a
    tag stands open at the start of the line, a bracket
    inside a quoted attribute value closing nothing, on
    the terms the container reading states for tags read
    whole (Step 17 round 7 entry S17-R7-008)."""
    out = []
    in_fence = False
    in_tag = False
    quote = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith(">") and not in_tag:
            continue
        out.append(line)
        index = 0
        while index < len(line):
            char = line[index]
            if in_tag:
                if quote is not None:
                    if char == quote:
                        quote = None
                elif char in ("\"", "'"):
                    quote = char
                elif char == ">":
                    in_tag = False
            elif char == "<" and index + 1 < len(line) and (
                    line[index + 1].isalpha()
                    or line[index + 1] in "/!?"):
                in_tag = True
                quote = None
            index += 1
    return "\n".join(out)


_COMMENT_CLOSE_RE = re.compile(r"--!?>")


def _comment_close(text, start):
    """The close of the comment that opens at start, found
    in one search bounded to that comment: the search runs
    from the comment opening to the first closing spelling
    of either form and no further, so a run of comments
    closed in one spelling pays no remainder scan per
    comment for the spelling that is not there (Step 17
    round 3 entry S17-R3-010). Returns the index just past
    the closing spelling, or None where the comment never
    closes."""
    match = _COMMENT_CLOSE_RE.search(text, start + 4)
    if match is None:
        return None
    return match.end()


def _skip_leading_furniture(text):
    """Step over the leading furniture of a document: HTML
    comments, XML or processing instruction forms, bogus
    declaration forms, and CDATA sections that stand
    before its own content (Step 17 round 3 entry
    S17-R3-015). A comment ends where the
    parser ends it, at the two hyphen close or at the bang
    close, and the two abrupt spellings stand as complete
    comments. An unterminated form steps over nothing and
    the text stands as it stood."""
    index = 0
    length = len(text)
    while True:
        while index < length and text[index] in " \t\r\n":
            index += 1
        if text.startswith("<!--", index):
            if text.startswith("<!-->", index):
                index += 5
                continue
            if text.startswith("<!--->", index):
                index += 6
                continue
            close = _comment_close(text, index)
            if close is None:
                return text[index:]
            index = close
            continue
        if text.startswith("<?", index):
            close = text.find("?>", index + 2)
            if close < 0:
                # A processing instruction form with no
                # closing spelling stands as an HTML bogus
                # comment, which ends at its first closing
                # bracket, so the content after it stands
                # read (Step 17 round 4 entry S17-R4-013).
                bogus_end = _scan_tag_end(text, index)
                if bogus_end < 0:
                    return text[index:]
                index = bogus_end + 1
                continue
            index = close + 2
            continue
        if text.startswith("<![CDATA[", index):
            close = text.find("]]>", index + 9)
            if close < 0:
                return text[index:]
            index = close + 3
            continue
        if text.startswith("<!", index) \
                and text[index:index + 9].casefold() != "<!doctype":
            close = _scan_tag_end(text, index)
            if close < 0:
                return text[index:]
            index = close + 1
            continue
        return text[index:]


def _content_format(text):
    visible = _strip_detection_exclusions(text)
    probe = _skip_leading_furniture(visible.lstrip("\ufeff \t\r\n"))
    low = probe.casefold()
    # A doctype stands judged by its name across the
    # whitespace the doctype form admits between the
    # keyword and the name: any run of whitespace stands
    # there, not one space only (Step 17 round 5 entry
    # S17-R5-007).
    if re.match(r"<!doctype\s+html\b", low) \
            or low.startswith("<html"):
        return "html"
    if re.match(r"(?is)<(head|body|div|p|h[1-6]|table|ul|ol|span|a|"
                r"section|article|main|aside|nav|header|footer|"
                r"blockquote|pre|figure|figcaption|form|fieldset|"
                r"dl|dt|dd|li|thead|tbody|tr|td|th|caption|"
                r"em|strong|small|code|kbd|abbr|cite|q|time|mark|"
                r"sub|sup|i|b|u|s|a|img|video|audio|canvas|svg|"
                r"details|summary|address|hr|br|wbr|button|"
                r"textarea|select|label|iframe|title|hgroup|"
                r"legend|script|style|dialog|template|noscript|"
                r"picture|object|embed|menu|meta|link|base|"
                r"input|source|track|col|area|colgroup|tfoot|"
                r"search|data|meter|progress|output|slot|ruby|"
                r"samp|var|dfn|bdi|bdo|del|ins|datalist|"
                r"optgroup|option|map|param|rp|rt|math|"
                # The child elements of the two vocabularies
                # whose roots stand above, SVG and MathML, stand
                # in the probe list whole, as the roots do: a
                # document led by a child element of either
                # vocabulary is a form the probe exists to
                # decide (Step 17 round 5 entry S17-R5-007,
                # completed at round 6 entry S17-R6-015, and
                # completed on the SVG font face spellings
                # and the two MathML alignment spellings at
                # round 7 entry S17-R7-015; the spelling font
                # stands outside that completion).
                r"altGlyph|altGlyphDef|altGlyphItem|animate|"
                r"animateColor|animateMotion|animateTransform|"
                r"circle|clipPath|color-profile|cursor|"
                r"definition-src|defs|desc|discard|ellipse|"
                r"feBlend|feColorMatrix|feComponentTransfer|"
                r"feComposite|feConvolveMatrix|feDiffuseLighting|"
                r"feDisplacementMap|feDistantLight|feDropShadow|"
                r"feFlood|feFuncA|feFuncB|feFuncG|feFuncR|"
                r"feGaussianBlur|feImage|feMerge|feMergeNode|"
                r"feMorphology|feOffset|fePointLight|"
                r"feSpecularLighting|feSpotLight|feTile|"
                r"feTurbulence|font-face-format|font-face-name|"
                r"font-face-src|font-face-uri|font-face|"
                r"filter|foreignObject|g|glyph|"
                r"glyphRef|handler|hkern|image|line|"
                r"linearGradient|listener|marker|mask|metadata|"
                r"missing-glyph|mpath|path|pattern|polygon|"
                r"polyline|radialGradient|rect|set|solidcolor|"
                r"stop|switch|symbol|text|textPath|tref|tspan|"
                r"use|view|vkern|"
                r"maction|annotation|annotation-xml|maligngroup|"
                r"malignmark|menclose|"
                r"merror|mfenced|mfrac|mi|mlongdiv|"
                r"mmultiscripts|mn|mo|mover|mpadded|mphantom|"
                r"mprescripts|mroot|mrow|ms|mscarries|mscarry|"
                r"msgroup|msline|msrow|mspace|msqrt|mstack|"
                r"mstyle|msub|msubsup|msup|mtable|mtd|mtext|"
                r"mtr|munder|munderover|semantics|none|mglyph)\b",
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
        if _inline_link_spans(stripped):
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

def _scan_tag_end(text, start):
    """The index of the bracket that closes the tag standing
    at start, read as the parser reads a tag: a bracket
    inside a quoted attribute value does not close the tag.

    The reading walks the tag attribute by attribute, on
    the terms HTMLParser walks it. An attribute name stands
    first: its first character is any character that is not
    whitespace, a slash, or a bracket, and its remaining
    characters are any but whitespace, a slash, an equals
    sign, or a bracket, so an equals sign standing where a
    name is expected is name text and opens no value. A run
    of equals signs after a name, with the space the parser
    allows around it, opens the value: a quoted value runs
    to its closing quote wherever that quote stands, and
    where no closing quote stands the quoted form does not
    stand as a value at all, the quote standing as the
    first character of the next attribute name and the tag
    ending where the parser ends it. An unquoted value runs
    to whitespace or to the bracket, and a quote or an
    equals sign inside it is value text. A declaration
    and a processing instruction form stand read as the
    parser reads them, ending at the first bracket, and
    a closing tag stands read on the same attribute
    terms as an opening tag, as round 3 entry S17-R3-014
    states for it (Step 17 round 4 entry S17-R4-011,
    completed
    at round 5 entry S17-R5-005 on the equals sign forms
    that entry names). Returns -1 where no closing bracket
    stands."""
    if text[start:start + 9].casefold() == "<!doctype":
        # A doctype declaration stands read whole across
        # its quoted literals, as the round 2 container
        # reading states: its quoted strings are
        # declaration text, not attribute values, so the
        # attribute reading below does not govern it.
        quote = None
        index = start + 1
        while index < len(text):
            ch = text[index]
            if quote is not None:
                if ch == quote:
                    quote = None
            elif ch in ("\"", "'"):
                quote = ch
            elif ch == ">":
                return index
            index += 1
        return -1
    if text[start + 1:start + 2] in ("!", "?"):
        return text.find(">", start + 1)
    length = len(text)
    index = start + 1
    # The tag name runs to whitespace, a slash, or the
    # bracket, as the parser reads it.
    while index < length and text[index] not in " \t\r\n\f/>":
        index += 1
    while index < length:
        # Separators between attributes: whitespace, and a
        # slash that no bracket follows.
        while index < length and (
                text[index] in " \t\r\n\f"
                or (text[index] == "/"
                    and text[index + 1:index + 2] != ">")):
            index += 1
        if index >= length:
            return -1
        if text[index] == ">":
            return index
        if text[index] == "/":
            return index + 1
        # An attribute name.
        index += 1
        while index < length \
                and text[index] not in " \t\r\n\f/=>":
            index += 1
        while index < length and text[index] in " \t\r\n\f":
            index += 1
        if index < length and text[index] == "=":
            while index < length and text[index] == "=":
                index += 1
            while index < length and text[index] in " \t\r\n\f":
                index += 1
            if index < length and text[index] in ("\"", "'"):
                close = text.find(text[index], index + 1)
                if close >= 0:
                    index = close + 1
                # Where no closing quote stands, the quoted
                # form does not stand as a value: the scan
                # stands on the quote, and the next pass
                # reads it as an attribute name, as the
                # parser does.
            else:
                while index < length \
                        and text[index] not in " \t\r\n\f>":
                    index += 1
    return -1


def _tag_self_closed(chunk, name_end):
    """Whether one opening tag chunk stands self closed, as
    the parser reads it (Step 17 round 3 entries S17-R3-013
    and S17-R3-014). The self closing flag is a slash that
    stands between attributes, immediately before the
    closing bracket. A slash inside a quoted attribute
    value is value text, a slash inside an unquoted
    attribute value is part of that value, and a slash
    separated from the bracket by space is ignored, so in
    each of those forms the element still opens. The scan
    walks the tag once, attribute by attribute, on the
    same terms _scan_tag_end reads a tag whole, the
    missing value and stray equals forms included: an
    equals sign standing where a name is expected is name
    text and opens no value, a run of equals signs after
    a name opens the value, and a quoted form with no
    closing quote stands as no value at all, its quote
    standing as the first character of the next attribute
    name (Step 17 round 5 entry S17-R5-005, completed at
    this sibling scan at round 6 entry S17-R6-008)."""
    index = name_end
    length = len(chunk)
    while index < length:
        while index < length and (
                chunk[index] in " \t\r\n\f"
                or (chunk[index] == "/"
                    and chunk[index + 1:index + 2] != ">")):
            index += 1
        if index >= length or chunk[index] == ">":
            return False
        if chunk[index] == "/":
            return True
        index += 1
        while index < length \
                and chunk[index] not in " \t\r\n\f/=>":
            index += 1
        while index < length and chunk[index] in " \t\r\n\f":
            index += 1
        if index < length and chunk[index] == "=":
            while index < length and chunk[index] == "=":
                index += 1
            while index < length and chunk[index] in " \t\r\n\f":
                index += 1
            if index < length and chunk[index] in ("\"", "'"):
                close = chunk.find(chunk[index], index + 1)
                if close >= 0:
                    index = close + 1
            else:
                while index < length \
                        and chunk[index] not in " \t\r\n\f>":
                    index += 1
    return False


_TAG_OPEN_RE = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9]*)")
_RAW_TEXT_CLOSE_RES = {
    name: re.compile(r"</%s(?=[\s/>])" % name, flags=re.I)
    for name in ("script", "style", "textarea", "title")
}


def _leading_structure(text):
    """Read the file's own leading structure as markup.

    Returns the doctype declarations that stand before the
    root element, each read whole across quoted brackets,
    and the root element opening tag, read whole on the
    same terms, or None where no root element stands. A
    spelling inside a comment, inside a declaration, or
    inside the raw text of a script, style, textarea, or
    title element is not structure: it claims no root
    position and shadows nothing, and a marker spelling in
    those places counts for nothing. The scan walks the
    file once, in file order."""
    doctypes = []
    index = 0
    length = len(text)
    while index < length:
        lt = text.find("<", index)
        if lt < 0:
            break
        if text.startswith("<!--", lt):
            if text.startswith("<!-->", lt):
                index = lt + 5
                continue
            if text.startswith("<!--->", lt):
                index = lt + 6
                continue
            close = _comment_close(text, lt)
            if close is None:
                break
            index = close
            continue
        if text.startswith("<![CDATA[", lt):
            end = text.find("]]>", lt + 9)
            if end < 0:
                break
            index = end + 3
            continue
        if text.startswith("<!", lt) or text.startswith("<?", lt):
            end = _scan_tag_end(text, lt)
            if end < 0:
                break
            chunk = text[lt:end + 1]
            if chunk.casefold().startswith("<!doctype"):
                doctypes.append(chunk)
            index = end + 1
            continue
        # The tag match and the raw text close search run
        # with a position argument on the whole text, never
        # on a slice of its remainder: a slice copies the
        # remainder once per tag, which costs superlinear
        # time on a page of many small tags at the governed
        # file limit (Step 17 round 4 entry S17-R4-010).
        match = _TAG_OPEN_RE.match(text, lt)
        if not match:
            index = lt + 1
            continue
        end = _scan_tag_end(text, lt)
        if end < 0:
            break
        chunk = text[lt:end + 1]
        closing = match.group(1) == "/"
        name = match.group(2).casefold()
        if not closing and name == "html":
            return doctypes, chunk
        if not closing and name in (
                "script", "style", "textarea", "title") \
                and not _tag_self_closed(
                    chunk, 1 + len(match.group(2))):
            close_match = _RAW_TEXT_CLOSE_RES[name].search(
                text, end + 1)
            if close_match is None:
                break
            close_start = close_match.start()
            close_end = _scan_tag_end(text, close_start)
            if close_end < 0:
                break
            index = close_end + 1
            continue
        index = end + 1
    return doctypes, None


def _root_tag_xmlns(chunk):
    """The value of the xmlns attribute of one root tag
    chunk, or None where the tag declares no namespace.

    The attributes stand read as the parser reads them,
    attribute by attribute on the terms _scan_tag_end
    states, so a namespace string standing as the value
    of any other attribute of the tag is that attribute
    text and declares nothing: the judgement at entry
    S17-R5-008 stands on the namespace the root element
    declares, in its xmlns attribute, and on no other
    text of the tag."""
    length = len(chunk)
    index = 1
    while index < length and chunk[index] not in " \t\r\n\f/>":
        index += 1
    while index < length:
        while index < length and (
                chunk[index] in " \t\r\n\f"
                or (chunk[index] == "/"
                    and chunk[index + 1:index + 2] != ">")):
            index += 1
        if index >= length or chunk[index] == ">":
            return None
        if chunk[index] == "/":
            return None
        name_start = index
        index += 1
        while index < length \
                and chunk[index] not in " \t\r\n\f/=>":
            index += 1
        name = chunk[name_start:index].casefold()
        while index < length and chunk[index] in " \t\r\n\f":
            index += 1
        value = None
        if index < length and chunk[index] == "=":
            # The value opens at the one equals sign, as the
            # parser reads it: a second equals sign stands
            # as the first character of the value itself,
            # and no equals run stands consumed on the
            # attribute (Step 17 round 6 entry S17-R6-009).
            # The equals run term belongs to the tag end
            # reading in _scan_tag_end, which finds where a
            # tag ends, and states no term for the value a
            # reader takes from the tag.
            index += 1
            while index < length and chunk[index] in " \t\r\n\f":
                index += 1
            if index < length and chunk[index] in ("\"", "'"):
                close = chunk.find(chunk[index], index + 1)
                if close < 0:
                    return None
                value = chunk[index + 1:close]
                index = close + 1
            else:
                value_start = index
                while index < length \
                        and chunk[index] not in " \t\r\n\f>":
                    index += 1
                value = chunk[value_start:index]
        if name == "xmlns":
            return value
    return None


def _check_containers(raw, text):
    visible = _strip_detection_exclusions(text)
    # The container rule reads the file's own leading
    # structure, however long that structure stands: a
    # doctype declaration in the material before the root
    # element, the root element opening tag itself (whose
    # attributes may run to any length), and, for a mail
    # container, the header block that runs to the first
    # blank line. No fixed character window bounds any of
    # those, so padding inside the leading structure
    # cannot push a marker past the rule. The structure
    # stands read as markup, on the file's own structure:
    # tags stand read whole across quoted brackets, and a
    # spelling inside a comment or inside raw text is not
    # the file's doctype and is not its root element.
    doctypes, root_tag = _leading_structure(visible)
    for doctype in doctypes:
        if "xhtml" in doctype.casefold():
            _fail("PAGE_EXTRACTION_FAILED",
                  "container failure: the file stands marked as XHTML")
    if root_tag is not None:
        declared = _root_tag_xmlns(root_tag)
        if declared is not None \
                and _unescape(declared) \
                == "http://www.w3.org/1999/xhtml":
            # The namespace the root element declares stands
            # judged as the parser decodes it, not by its raw
            # spelling: character references in the xmlns
            # value decode before the reading, as HTMLParser
            # decodes them (Step 17 round 4 entry S17-R4-012),
            # and the judgement stands on that declared value
            # alone, not on a namespace string standing in
            # any other attribute of the tag (Step 17 round
            # 5 entry S17-R5-008).
            _fail("PAGE_EXTRACTION_FAILED",
                  "container failure: the file stands marked as XHTML")
    header_block = re.split(r"\r?\n[ \t]*\r?\n", visible,
                            maxsplit=1)[0]
    low_header = header_block.casefold()
    if ("multipart/" in low_header
            and ("mime-version:" in low_header
                 or "content-type: multipart" in low_header)):
        _fail("PAGE_EXTRACTION_FAILED",
              "container failure: the file is an MHTML container")
    if visible.lstrip(" \t\r\n").startswith("WARC/"):
        _fail("PAGE_EXTRACTION_FAILED",
              "container failure: the file is a WARC container")


# ----------------------------------------------------------------
# The supplied file open protocol (boundary B1), in operating
# system terms: a stat that does not follow the final
# component, a non blocking no follow open, a device and
# inode match against the pre open stat, a hard link count
# of at most one, and one read of the opened handle.
# ----------------------------------------------------------------

def _read_supplied_file(page_path, size_limit_bytes=None):
    # The page file size limit in force over the run, in
    # bytes, where the caller states one (Step 17 round 2
    # entry S17-R2-085): one reading of the limits in force
    # governs this gate and the service preflight gate, so
    # the brief default constant stands only where no
    # value in force reaches this reading.
    limit_bytes = size_limit_bytes if isinstance(
        size_limit_bytes, (int, float)) else _PAGE_FILE_LIMIT
    limit_label = "%s MiB" % (
        "%g" % (limit_bytes / (1024 * 1024)),)
    path_text = str(page_path)
    if "\x00" in path_text:
        _fail("SUPPLIED_PATH_UNSAFE",
              "a supplied path holding a NUL byte cannot be "
              "stated and is rejected")
    try:
        pre = os.lstat(path_text)
    except (OSError, ValueError) as exc:
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
    except (OSError, ValueError) as exc:
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
        if opened.st_nlink > 1:
            _fail("SUPPLIED_PATH_UNSAFE",
                  "a supplied file with a hard link count above 1 "
                  "is rejected")
        if opened.st_size > limit_bytes:
            _fail("LIMIT_EXCEEDED",
                  "page file size limit is %s, with rejection "
                  "and no partial record" % (limit_label,))
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
                      "page file size limit is %s, with "
                      "rejection and no partial record"
                      % (limit_label,))
        return b"".join(chunks)
    finally:
        os.close(descriptor)


# ----------------------------------------------------------------
# Decoding. UTF-8 strictly, one leading byte order mark
# stripped once and noted, any further mark standing as an
# ordinary U+FEFF character in the decoded text.
# ----------------------------------------------------------------

def _front_matter_key_value(line):
    """One front matter line as its key and value, or None.

    This reading stands as the one reading with the import
    side reading in probe_import.py, in the form that
    module states at its own _front_matter_key_value: a
    line opening with a quoted string whose closing quote
    is not followed by a colon holds no key of its own,
    and a colon inside a quoted key does not split the
    line (Step 17 round 5 entries S17-R5-010 and
    S17-R5-011)."""
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


_FM_DEFAULT_IGNORABLE_RANGES = (
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


def _fm_is_head_char(char):
    """One character of head material, on the completed
    head predicate the import side reading states at its
    _is_head_char: byte order marks, control characters,
    whitespace, invisible format or space separator
    characters, and the default ignorable forms, variation
    selectors and the combining grapheme joiner among
    them, which render as nothing in stored text (Step 17
    round 7 entry S17-R7-011)."""
    code = ord(char)
    return (
        char == "\ufeff"
        or code < 0x20
        or code == 0x7f
        or 0x80 <= code <= 0x9f
        or char in " \t\n\r\f"
        or unicodedata.category(char) in ("Cf", "Zs", "Zl", "Zp")
        or any(low <= code <= high
               for low, high in _FM_DEFAULT_IGNORABLE_RANGES))


def _fm_strip_head(text):
    """The text past any leading head material, on the
    terms the import side reading states for its judged
    key and value positions: byte order marks, control
    characters, whitespace, and invisible format or space
    separator characters standing at the head of the text
    are not part of the judged text, and the default
    ignorable forms stand in the set on the completed
    head predicate (Step 17 round 7 entry S17-R7-011)."""
    index = 0
    while index < len(text) and _fm_is_head_char(text[index]):
        index += 1
    return text[index:]


def _fm_strip_head_edges(text):
    """The text with head material removed at both edges,
    on the completed head predicate, as the import side
    reading states at its _strip_head_edges (Step 17
    round 7 entries S17-R7-010 and S17-R7-014)."""
    start = 0
    while start < len(text) and _fm_is_head_char(text[start]):
        start += 1
    end = len(text)
    while end > start and _fm_is_head_char(text[end - 1]):
        end -= 1
    return text[start:end]


def _fm_remove_interior_head(text):
    """The text with head material removed at any position,
    as the import side reading states at its
    _remove_interior_head: head material standing inside
    a judged form, between the letters of a key name or
    between the dashes of a fence, stands removed, while
    whitespace standing inside the form stands as written
    (Step 17 round 8 entries S17-R8-004 and S17-R8-005)."""
    return "".join(
        char for char in text
        if not _fm_is_head_char(char) or char.isspace())


def _fm_judged_key(key):
    """One front matter key as the duplicate judgement
    reads it: head material removed at both edges and at
    any position inside the name, as the import side
    reading states at its _judged_key (Step 17 round 8
    entry S17-R8-004)."""
    return _fm_remove_interior_head(_fm_strip_head_edges(key))


def _fm_judged_fence(line):
    """One fence line as the fence judgement reads it:
    head material removed at both edges and between the
    fence characters themselves, as the import side
    reading states at its _judged_fence (Step 17 round 8
    entry S17-R8-005)."""
    return _fm_remove_interior_head(_fm_strip_head_edges(line))


def _fm_holds_tag_construct(text):
    """True where a key or value text holds a tag
    construct, on the terms the import side reading
    states in probe_import.py at its _holds_tag_construct:
    a construct standing at the start of the text, a
    construct spelling standing as its own word later in
    the text, an angle bracket tag spelling anywhere in
    the text, and a block scalar opening standing as the
    value (Step 17 round 6 entry S17-R6-012, completed at
    round 7 entry S17-R7-009 on the three limbs the
    import side completions of round 6 landed: an angle
    bracket spelling opens on any URI character, a digit,
    a hyphen, or an underscore among them; a block scalar
    header admits both indicator orders, the chomping
    sign before the indentation digit and the digit
    before the sign; and a construct stands judged
    directly after a flow opening bracket, as after the
    start of the text and after whitespace, completed at
    round 8 entry S17-R8-003 to the import side landed
    forms of round 7 entry S17-R7-030: an angle bracket
    spelling opens on the caret, and a construct stands
    judged directly after the separator standing between
    two flow items, after the colon of a flow mapping,
    after a semicolon, after a quote, and after an
    opening parenthesis, completed at round 9 entry
    S17-R9-002 to the import side forms cured at round 8
    entry S17-R8-015: an angle bracket spelling opens on
    the hash, and a construct stands judged directly
    after a closing bracket, the closing square bracket,
    the closing curly brace, and the closing parenthesis,
    and completed at round 9 entry S17-R9-019 at the
    remaining punctuation positions, so a construct
    stands judged directly after any punctuation
    character, the position set standing whole, and
    completed at round 10 entry S17-R10-012 on the
    interior head reading the duplicate judgement and
    the fence judgement apply: the judgement stands on
    the text with head material removed at any position,
    whitespace standing as written, so a construct
    standing behind interior head material at a judged
    position, between the construct character and its
    letter, or between an angle bracket and its opening
    character stands judged as the construct it
    spells, completed at round 11 entry S17-R11-001 on
    the follower set: the character standing after the
    construct character stands judged as any word
    character or a hyphen, the import side set the cure
    at round 10 entry S17-R10-007 landed, so a name
    opening on a digit, on an underscore, on a hyphen,
    or on a letter outside the plain alphabet stands
    judged at every judged position, completed at
    round 12 entry S17-R12-001 on the widened set the
    cure at round 11 entry S17-R11-010 landed at the
    import side reading: the character standing after
    the construct character stands judged beside any
    word character or a hyphen on a full stop, a plus
    sign, a dollar sign, a tilde, a semicolon, a slash,
    an equals sign, an at sign, a caret, a backtick, a
    combining mark, and an undertie, as the import side
    set stands cured, and completed at the same entry
    on the page side limb of round 12 entry
    S17-R12-008 on the six further openings that entry
    names: a question mark, a backslash, an opening
    parenthesis, a closing parenthesis, a less than
    sign, and a colon, completed at round 13 entry
    S17-R13-001 on the combining mark opening in the
    generic form the cure at round 11 entry S17-R11-010
    names: the character standing after the construct
    character stands judged as that opening where it
    stands as a combining mark as such, a mark of
    general category Mn, Mc, or Me at any code point,
    beside the range the earlier cure landed and beside
    the word character set, each of which the reading
    above already refuses, the page side limb of round
    13 entry S17-R13-004 standing inside the same
    completion on the category Mc and Me marks)."""
    text = _fm_remove_interior_head(text)
    if text.startswith(("!", "&", "*", "%")):
        return True
    if re.search(
            r"<[A-Za-z0-9\-._;/?:@&=+$,!~*'()%\[\]\^#][^>]*>", text):
        return True
    if re.search(
            r"(?:^|[\s!\"#\$%&'\(\)\*\+,\-\./:;<=>\?@\[\\\]\^_`{|}~])"
            r"[&*%!][\w\-\.\+\$~;/=@\^`\u0300-\u036f\u203f\?\\\(\)<:]", text):
        return True
    for match in re.finditer(
            r"(?:^|[\s!\"#\$%&'\(\)\*\+,\-\./:;<=>\?@\[\\\]\^_`{|}~])"
            r"[&*%!](.)", text):
        if unicodedata.category(match.group(1)) in (
                "Mn", "Mc", "Me"):
            return True
    if re.match(r"^[|>](?:[+-]?[0-9]?|[0-9][+-])?(?:\s|$)", text):
        return True
    return False


class _FmWrittenNumber(str):
    """A JSON number carrying its written form, as the
    import side reading holds it at its _WrittenNumber.

    The JSON form value length check measures a numeric
    value by its written form, as it measures a string by
    its length. Parsing a number into a plain int or
    float loses that form, a float in particular rendering
    far shorter than it stands written, so the reader
    holds the token text itself (Step 17 round 8 entry
    S17-R8-006)."""


def _fm_json_holds_tag_construct(value):
    """True where any string in a JSON form front matter
    value, at any depth, in a key or in a value, holds a
    tag construct, as the import side reading judges the
    JSON form whole (Step 17 round 6 entry S17-R6-012)."""
    if isinstance(value, _FmWrittenNumber):
        return False
    if isinstance(value, str):
        return _fm_holds_tag_construct(_fm_strip_head(value.strip()))
    if isinstance(value, dict):
        return any(
            _fm_holds_tag_construct(_fm_strip_head(str(key).strip()))
            or _fm_json_holds_tag_construct(item)
            for key, item in value.items())
    if isinstance(value, list):
        return any(_fm_json_holds_tag_construct(item) for item in value)
    return False


def _fm_json_depth(value):
    """The nesting depth of one parsed JSON value, counted
    iteratively, as the import side reading counts it at
    its _json_depth (Step 17 round 7 entry S17-R7-013)."""
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


def _fm_container_value_measure(value):
    """The length a container value stands measured by,
    as the import side reading states at its
    _container_value_measure: a string standing inside a
    container stands measured by its length in characters,
    the one measure a string standing as a whole value
    stands measured by, and a number standing inside a
    container stands measured by its written form, as a
    number standing as a whole value does, and the
    container marks, the quote marks, and the separators
    of the rendering count for nothing in the measure
    (Step 17 round 8 entry S17-R8-028, on the cure at
    round 7 entry S17-R7-032, completed at round 9 entry
    S17-R9-003 at the key position, on the form the
    import side cure at round 8 entry S17-R8-016 states:
    a string standing as a key inside a container stands
    measured by its length in characters beside the
    measure of its value, at any depth)."""
    if isinstance(value, _FmWrittenNumber):
        return len(value)
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return sum(
            _fm_container_value_measure(key)
            + _fm_container_value_measure(item)
            for key, item in value.items())
    if isinstance(value, list):
        return sum(
            _fm_container_value_measure(item) for item in value)
    return 0


def _fm_json_value_length(value):
    """The measured length of one JSON form value, on the
    measure the import side reading states: a string
    stands measured by its length in characters, a number
    by its written form, held at parse time as
    _FmWrittenNumber, and a container by the sum of its
    member measures on _fm_container_value_measure, with
    the container marks counting for nothing (Step 17
    round 7 entry S17-R7-013, completed at round 8 entries
    S17-R8-006 and S17-R8-028)."""
    if isinstance(value, _FmWrittenNumber):
        return len(value)
    if isinstance(value, str):
        return len(value)
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return len(str(value))
    if isinstance(value, (dict, list)):
        return _fm_container_value_measure(value)
    return 0


def _fm_json_rendered(value):
    """One JSON value rendered for the container measure
    at _fm_json_value_length."""
    if isinstance(value, _FmWrittenNumber):
        return str(value)
    if isinstance(value, str):
        return '"' + value + '"'
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return "{" + ", ".join(
            '"' + str(key) + '": ' + _fm_json_rendered(item)
            for key, item in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(
            _fm_json_rendered(item) for item in value) + "]"
    return str(value)


def _fm_brackets_closed(text):
    """True where the bracket forms in one front matter
    text stand balanced, the not closed bracket judgement
    the import side reading runs on keys, on values, and
    on continuation lines whole (Step 17 round 6 entry
    S17-R6-013)."""
    return text.count("[") == text.count("]") \
        and text.count("{") == text.count("}")


def _front_matter(text, fmt, notes, block_limit_bytes=None,
                  value_limit=None):
    """Front matter handling. Front matter that fails the
    D17 control set fails closed: a tag construct standing
    in front matter is that failure in this module.

    This reading stands as the one reading with the import
    side reading in probe_import.py, whole: the tag
    construct judgement at every position, in the line
    form and in the JSON form alike, the bracket judgement
    on keys, on values, and on continuation lines, and
    the key discipline, each key standing once and the
    key count limit standing enforced in both forms
    (Step 17 round 6 entries S17-R6-012, S17-R6-013, and
    S17-R6-014).

    The block size and value length limits stand as the
    limits in force for the run where the caller states
    them (Step 17 round 3 entry S17-R3-068): one reading
    of the limits in force governs the audit record's
    statement and this enforcement, so the brief default
    constants stand only where no value in force reaches
    this reading, as at the page size gate.
    """
    if not isinstance(block_limit_bytes, (int, float)):
        block_limit_bytes = _FRONT_MATTER_BLOCK_LIMIT
    if not isinstance(value_limit, (int, float)):
        value_limit = _FRONT_MATTER_VALUE_LIMIT
    if fmt != "markdown":
        return text
    # The fence judgement stands on the completed head
    # predicate at both fences, not on whitespace
    # stripping alone: head material standing before the
    # opening fence, or at either edge of either fence
    # line, does not move the block off the reading, as
    # the import side reading states for its opening
    # fence (Step 17 round 7 entry S17-R7-014), completed
    # at round 8 entry S17-R8-005 on head material
    # standing between the fence characters themselves,
    # through _fm_judged_fence at both fences.
    working = _fm_strip_head(text)
    lines = working.splitlines()
    if not lines or _fm_judged_fence(lines[0]) != "---":
        return text
    for index in range(1, len(lines)):
        if _fm_judged_fence(lines[index]) in ("---", "..."):
            block = "\n".join(lines[1:index])
            # The block size stands measured on the block
            # as it stands in the file, the lines between
            # the fences with the terminators the file
            # closes them with, at their file width, so a
            # carriage return standing in a terminator
            # counts at its width on every block line, as
            # the import side reading cured at round 7
            # entry S17-R7-033 measures it (Step 17 round
            # 8 entry S17-R8-007).
            kept_lines = working.splitlines(keepends=True)
            block_in_file = "".join(kept_lines[1:index])
            if len(block_in_file.encode("utf-8")) \
                    > block_limit_bytes:
                _fail("LIMIT_EXCEEDED",
                      "front matter block size limit is %s KiB, "
                      "with rejection and no partial record"
                      % ("%g" % (block_limit_bytes / 1024),))
            # Values stand measured as the governing
            # readings state them (Step 17 round 4 entry
            # S17-R4-062): a comment line stands as no
            # value at all, and an indented continuation
            # line stands accumulated into the value above
            # it, as the import side reading cured at
            # S17-R3-027 accumulates it. The line form
            # stands judged by the one reading the import
            # side stands on, _front_matter_key_value
            # above: a line holding no key of its own, an
            # indented line opening with a quoted string
            # whose closing quote no colon follows among
            # them, stands as a continuation where it
            # stands indented, and a line holding no key
            # and no indentation stands refused here as
            # the import side reading refuses it, in this
            # module own vocabulary (Step 17 round 5
            # entries S17-R5-010 and S17-R5-011).
            if block.strip().startswith("{"):
                # The JSON form of the block stands under
                # the same control set whole, as the import
                # side reading states it: duplicate keys
                # stand refused, the key count limit stands
                # enforced, and a tag construct standing in
                # a key or a value at any depth stands
                # refused (Step 17 round 6 entries
                # S17-R6-012 and S17-R6-014).
                def _no_duplicates(pairs):
                    seen = set()
                    for key, _value in pairs:
                        judged = _fm_judged_key(str(key))
                        if judged in seen:
                            _fail("PAGE_EXTRACTION_FAILED",
                                  "the front matter block in "
                                  "JSON form holds the key "
                                  + judged + " twice; front "
                                  "matter keys stand once each")
                        seen.add(judged)
                    return dict(pairs)

                try:
                    parsed = json.loads(
                        block.strip(),
                        object_pairs_hook=_no_duplicates,
                        parse_int=_FmWrittenNumber,
                        parse_float=_FmWrittenNumber)
                except AcquisitionError:
                    raise
                except (ValueError, RecursionError):
                    _fail("PAGE_EXTRACTION_FAILED",
                          "the front matter block in JSON "
                          "form does not read as one JSON "
                          "object")
                if not isinstance(parsed, dict):
                    _fail("PAGE_EXTRACTION_FAILED",
                          "the front matter block in JSON "
                          "form does not read as one JSON "
                          "object")
                if len(parsed) > _FRONT_MATTER_KEY_LIMIT:
                    _fail("LIMIT_EXCEEDED",
                          "front matter key count limit is "
                          "100, with rejection and no partial "
                          "record")
                # The JSON form stands under the value
                # length limit and the nesting depth limit
                # its own line form and the import side
                # reading enforce on the same block (Step
                # 17 round 7 entry S17-R7-013).
                if _fm_json_depth(parsed) \
                        > _FRONT_MATTER_JSON_DEPTH_LIMIT:
                    _fail("LIMIT_EXCEEDED",
                          "JSON nesting depth limit is 100, "
                          "with rejection and no partial "
                          "record")
                for json_key, json_value in parsed.items():
                    # A string standing as a key of the top
                    # level object stands measured by its
                    # length in characters, as a string
                    # standing as a value stands measured
                    # (Step 17 round 9 entry S17-R9-020).
                    if len(str(json_key)) > value_limit \
                            or _fm_json_value_length(json_value) \
                            > value_limit:
                        _fail("LIMIT_EXCEEDED",
                              "front matter value length per "
                              "key limit is %s characters, "
                              "with rejection and no partial "
                              "record"
                              % ("%g" % (value_limit,),))
                if _fm_json_holds_tag_construct(parsed):
                    _fail("PAGE_EXTRACTION_FAILED",
                          "front matter fails the D17 "
                          "control set")
                notes.append("front_matter")
                return "\n".join(lines[index + 1:])
            current_value_length = None
            seen_keys = set()
            key_count = 0
            for block_line in lines[1:index]:
                if not block_line.strip() or block_line.lstrip() \
                        .startswith("#"):
                    continue
                pair = _front_matter_key_value(block_line)
                if pair is None:
                    if block_line[0] in " \t" \
                            and current_value_length is not None:
                        continuation = block_line.strip()
                        current_value_length += len(continuation)
                        # A continuation line stands judged
                        # as a top level line stands judged:
                        # a tag construct standing on it, at
                        # any position, and an unbalanced
                        # bracket standing on it whole, each
                        # fail the block (Step 17 round 6
                        # entries S17-R6-012 and S17-R6-013).
                        if _fm_holds_tag_construct(
                                _fm_strip_head(continuation)):
                            _fail("PAGE_EXTRACTION_FAILED",
                                  "front matter fails the "
                                  "D17 control set")
                        if not _fm_brackets_closed(continuation):
                            _fail("PAGE_EXTRACTION_FAILED",
                                  "a front matter value is "
                                  "not closed: "
                                  + continuation[:60])
                    else:
                        _fail("PAGE_EXTRACTION_FAILED",
                              "a front matter line holds no "
                              "key and value: "
                              + block_line.strip()[:60])
                else:
                    current_value_length = len(pair[1])
                    # The key discipline of the one
                    # reading: a key stands once each, and
                    # the key count limit of 100 stands
                    # enforced, as the import side reading
                    # enforces both on the same block (Step
                    # 17 round 6 entry S17-R6-014).
                    key_count += 1
                    if key_count > _FRONT_MATTER_KEY_LIMIT:
                        _fail("LIMIT_EXCEEDED",
                              "front matter key count limit "
                              "is 100, with rejection and no "
                              "partial record")
                    # A line whose key stands empty stands
                    # refused, as the import side reading
                    # refuses it (Step 17 round 7 entry
                    # S17-R7-012).
                    if not pair[0]:
                        _fail("PAGE_EXTRACTION_FAILED",
                              "a front matter line holds no "
                              "key: "
                              + block_line.strip()[:60])
                    # The duplicate judgement stands on
                    # the judged key, head material removed
                    # at both edges and at any position
                    # inside the name on the completed head
                    # predicate, as the import side reading
                    # states at its _judged_key (Step 17
                    # round 7 entry S17-R7-010, completed
                    # at round 8 entry S17-R8-004).
                    duplicate_key = _fm_judged_key(pair[0])
                    if duplicate_key in seen_keys:
                        _fail("PAGE_EXTRACTION_FAILED",
                              "the front matter block holds "
                              "the key " + duplicate_key
                              + " twice; "
                              "front matter keys stand once "
                              "each")
                    seen_keys.add(duplicate_key)
                    # The construct judgement stands on
                    # the key and on the value at every
                    # position, as the import side reading
                    # states the construct rule (Step 17
                    # round 6 entry S17-R6-012), and the
                    # bracket judgement stands on the key
                    # and on the value alike (Step 17
                    # round 6 entry S17-R6-013).
                    judged_key = _fm_strip_head(pair[0])
                    judged_value = _fm_strip_head(pair[1])
                    if _fm_holds_tag_construct(judged_key) \
                            or _fm_holds_tag_construct(
                                judged_value):
                        _fail("PAGE_EXTRACTION_FAILED",
                              "front matter fails the D17 "
                              "control set")
                    if not _fm_brackets_closed(judged_key):
                        _fail("PAGE_EXTRACTION_FAILED",
                              "a front matter key is not "
                              "closed: " + judged_key[:60])
                    if not _fm_brackets_closed(pair[1]):
                        _fail("PAGE_EXTRACTION_FAILED",
                              "a front matter value is not "
                              "closed: " + pair[1][:60])
                if current_value_length > value_limit:
                    _fail("LIMIT_EXCEEDED",
                          "front matter value length per key "
                          "limit is %s characters, with "
                          "rejection and no partial record"
                          % ("%g" % (value_limit,),))
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


class _ScriptStyleScanner(HTMLParser):
    """Count script and style elements as the parser reads
    them. The parser itself decides what stands inside a
    comment, what stands inside a quoted attribute value,
    where a comment ends, which closing spellings close an
    element, and where the raw text of an open element
    ends, so the count and the extraction parser can no
    longer read the same material two ways."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.open_tag = None
        self.stray = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style") and self.open_tag is None:
            self.open_tag = tag

    def handle_startendtag(self, tag, attrs):
        # A self closed element is complete with no body
        # and no closing tag: it counts as no opening.
        pass

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            if self.open_tag == tag:
                self.open_tag = None
            else:
                self.stray.append(tag)


def _check_script_style(text):
    # The count reads the elements in file order, through
    # the same parser the extraction reads: an element the
    # parser leaves open at the end of the file stands
    # unclosed, and a closing spelling the parser reads
    # with no element open for it leaves the content
    # ambiguous, as a closing tag standing inside a script
    # body does when a second closing spelling follows it.
    scanner = _ScriptStyleScanner()
    scanner.feed(text)
    scanner.close()
    if scanner.open_tag is not None:
        _fail("PAGE_EXTRACTION_FAILED",
              "an unclosed %s element fails closed"
              % scanner.open_tag)
    if scanner.stray:
        _fail("PAGE_EXTRACTION_FAILED",
              "content inside a %s element stands ambiguous "
              "and fails closed" % scanner.stray[0])


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
                    "_block_index": len(self.blocks),
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
    block_starts = []
    block_cursor = 0
    for block in parser.blocks:
        block_starts.append(block_cursor)
        block_cursor += len(block) + 2
    headings = []
    cursor = 0
    for heading in parser.headings:
        start = None
        block_index = heading.get("_block_index")
        if block_index is not None and 0 <= block_index < len(parser.blocks):
            block_text = parser.blocks[block_index]
            within = block_text.find(heading["text"])
            start = block_starts[block_index] + (
                within if within >= 0 else 0)
        if start is None:
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
            for cells in current_table:
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
    heading_positions = {}
    current_block_headings = []

    def flush_block():
        nonlocal current_block, current_block_headings
        if current_block:
            block_index = len(blocks)
            element_starts = []
            element_cursor = 0
            for element in current_block:
                element_starts.append(element_cursor)
                element_cursor += len(element) + 1
            for heading_index, element_index, within in \
                    current_block_headings:
                if 0 <= element_index < len(element_starts):
                    heading_positions[heading_index] = (
                        block_index,
                        element_starts[element_index] + within)
            blocks.append("\n".join(current_block))
        current_block = []
        current_block_headings = []

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
                heading_index = len(headings)
                headings.append({
                    "text": html_heading["text"],
                    "level": html_heading["level"],
                    "start": line_offsets[idx],
                })
                if html_parts["running_text"]:
                    current_block_headings.append((
                        heading_index, len(current_block),
                        html_heading["start"]))
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
            htext = _markdown_inline(
                heading.group(2).strip(), links, references, notes,
                line_offsets[idx])
            heading_index = len(headings)
            headings.append({
                "text": htext,
                "level": len(heading.group(1)),
                "start": line_offsets[idx],
            })
            blocks.append(htext)
            heading_positions[heading_index] = (len(blocks) - 1, 0)
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
            raw_cells = [cell.strip() for cell in
                         stripped.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", cell or "---")
                   for cell in raw_cells):
                current_table.append(raw_cells)
            else:
                cells = [_markdown_inline(
                    cell, links, references, notes,
                    line_offsets[idx]) for cell in raw_cells]
                current_table.append(cells)
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
    # Heading offsets stand in extracted text coordinates,
    # as every neighbouring positional field does: a heading
    # entry start locates its own heading block in the running
    # text. Each heading carries the position of the block it
    # stood in, recorded in extraction order as the blocks
    # were walked, so an earlier standing of the same words
    # in body prose never locates a heading. The start is not
    # read in the supplied source file, whose Markdown marks
    # the running text does not carry.
    block_starts = []
    block_cursor = 0
    for block in blocks:
        block_starts.append(block_cursor)
        block_cursor += len(block) + 2
    ordered_headings = []
    cursor = 0
    for heading_index, heading in enumerate(headings):
        start = None
        if heading_index in heading_positions:
            block_index, within = heading_positions[heading_index]
            if 0 <= block_index < len(block_starts):
                start = block_starts[block_index] + within
        if start is None:
            found = running_text.find(heading["text"], cursor) \
                if heading["text"] else -1
            start = found if found >= 0 else cursor
        ordered_headings.append({
            "text": heading["text"],
            "level": heading["level"],
            "start": start,
        })
        cursor = start + len(heading["text"])
    headings = ordered_headings
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

    pieces = []
    cursor = 0
    for span in _reference_link_spans(text):
        label, ref = span[2], span[3]
        key = ref if ref else label
        pieces.append(text[cursor:span[0]])
        if key in references:
            links.append({"text": label, "target": references[key]})
            pieces.append(label)
        else:
            notes.append("unresolved_markdown_reference")
            pieces.append(text[span[0]:span[1]])
        cursor = span[1]
    pieces.append(text[cursor:])
    text = "".join(pieces)
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

def _build_extracted(fmt, text, notes,
                     extracted_text_limit=_EXTRACTED_TEXT_LIMIT):
    if fmt == "html":
        parts = _extract_html(text, notes)
    elif fmt == "markdown":
        parts = _extract_markdown(text, notes)
    else:
        parts = _extract_text(text, notes)
    running_text = parts["running_text"]
    if len(running_text) > extracted_text_limit:
        _fail("LIMIT_EXCEEDED",
              "extracted text length per page limit is %s "
              "characters, with rejection and no partial record"
              % (extracted_text_limit,))
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
                   capture_date_asserted, capture_method_asserted,
                   run_id=None, limits_in_force=None):
    # One reading of the limits in force for this run
    # governs every extraction gate below (Step 17 round 2
    # entry S17-R2-085): the reading stands taken under
    # the run identity the service states for the run, so
    # a raise for that run and a config value both reach
    # the page size gate and the extracted text gate here,
    # as they reach the service preflight. Where the
    # service caller hands its own start reading in, that
    # one reading governs the whole run (Step 17 round 4
    # entry S17-R4-061): the audit statement and the
    # extraction enforcement then stand on the same
    # values, and no second reading of the config file
    # limb can move the enforcement away from the values
    # the record states.
    if limits_in_force is None:
        try:
            from citeline import journal as journal_module
            limits_in_force = journal_module.effective_limits(
                str(home), run_id=run_id) or {}
        except Exception:
            limits_in_force = {}
    page_size_value = (
        limits_in_force.get("page_file_size") or {}).get("value")
    size_limit_bytes = page_size_value * 1024 * 1024 if isinstance(
        page_size_value, (int, float)) else None
    raw = _read_supplied_file(
        page_path, size_limit_bytes=size_limit_bytes)
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
    fm_block_value = (
        limits_in_force.get("front_matter_block_size")
        or {}).get("value")
    fm_block_bytes = fm_block_value * 1024 if isinstance(
        fm_block_value, (int, float)) else None
    fm_value_limit = (
        limits_in_force.get("front_matter_value_length_per_key")
        or {}).get("value")
    text = _front_matter(
        text, fmt, notes, block_limit_bytes=fm_block_bytes,
        value_limit=fm_value_limit)
    # The extracted text limit in force over this home
    # governs the extraction, not only the brief default:
    # a config set value reaches this path through the
    # journal limits in force (Step 17 entry S17-R1-080,
    # cured at the service seam in seat F7 with this one
    # reading in the extraction path). Where no limit can
    # be read, the brief default constant governs, as
    # before.
    extracted_text_limit = _EXTRACTED_TEXT_LIMIT
    stated_text_limit = (
        limits_in_force.get(
            "extracted_text_length_per_page_or_answer")
        or {}).get("value")
    if isinstance(stated_text_limit, (int, float)):
        extracted_text_limit = stated_text_limit
    extracted = _build_extracted(
        fmt, text, notes, extracted_text_limit=extracted_text_limit)
    running = extracted["running_text"]
    if running.strip() == "":
        outcome = "empty"
        reason_code = "EXT_EMPTY"
    else:
        outcome = "ok"
        reason_code = None
    # The snapshot identity derives from the journal
    # sequence of the entry that stores the record, on the
    # plan identifier derivation table: the marker stands
    # in the payload in place of any count read taken here,
    # and the journal append resolves it under its write
    # lock at the moment the sequence stands assigned, in
    # the form the S17-R1-077 cure established for the
    # answer and run limbs, so no count read outside the
    # lock can mint an identity another append also mints.
    snapshot = {
        "snapshot_id": "snap-{sequence}",
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
        kwargs.get("capture_method_asserted"),
        run_id=kwargs.get("run_id"),
        limits_in_force=kwargs.get("limits_in_force"))
    snapshot = result["snapshot"]
    if kwargs.get("register_snapshot", True) is False:
        # The caller registers the snapshot itself, in the
        # same batch as the record the snapshot belongs to
        # (Step 17 round 2 entry S17-R2-072): the snapshot
        # stands returned with its sequence marker
        # unresolved, for the caller's batch append to
        # resolve under its lock.
        return result
    if _journal_or_none() is not None:
        appended = _journal_append(home, "snapshot_registered",
                                   dict(snapshot), audit_date)
        stored = appended.get("payload") \
            if isinstance(appended, dict) else None
        if isinstance(stored, dict) and stored.get("snapshot_id"):
            # The returned snapshot is the stored record, so
            # the identity it carries is the one the append
            # resolved from its storing sequence.
            result = {"snapshot": dict(stored),
                      "extracted": result["extracted"]}
        else:
            snapshot["snapshot_id"] = "snap-%d" % _next_sequence(home)
    else:
        snapshot["snapshot_id"] = "snap-%d" % _next_sequence(home)
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
