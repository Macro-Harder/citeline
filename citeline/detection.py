"""Detection for imported answer text, slice S6.

This module consumes imported answer text only, through the
detect_answer input shape: the answer text, the product as
registered, and the competitor list as registered. It reads no
supplied file and holds no form inventory. It owns the
AnswerMetrics per answer fields stated at plan Section 5.1:
named, named_early, cited, first_offset, matched_aliases,
per competitor outcomes, unresolved_form_count, the references
section split counts, and the clustering operation whose
per answer cluster fields the metrics slice consumes.

Rules landed here, each from the brief Section 5.7 items the
plan entry for S6 names: mention detection with masking,
longest alias first, and offsets read from the unmasked text
(item 46); citation detection at domain level with a dot
boundary (items 1, 34, and 44); host normalisation (item 42);
scheme and port handling (item 43); the canonical form
(item 33) built by the T3 tolerance rung (item 40); bracket
resolution (item 31); and the references section rule
(item 160). The three normalisations stay separate named
functions: normalise_host, syntax_normalise_path, and the
query handling inside canonical_form. No shared normalise
helper stands in this module.

List dependent limbs stand stopped at SEAM-LISTS: no tracking
parameter beyond the named position on ref is stripped, no
common word classification is applied to a matched alias, and
no wrapper outcome is produced for a wrapped target, which is
recorded as the target as written.
"""

from bisect import bisect_left, bisect_right
import re
import unicodedata
from urllib.parse import urlsplit

DETECTOR_VERSION = 1

REFERENCES_HEADINGS = frozenset({
    "references",
    "sources",
    "source list",
    "bibliography",
    "further reading",
    "works cited",
})

_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "0123456789-._~")
_HEX = frozenset("0123456789abcdefABCDEF")

_LINK_RE = re.compile(r"\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+[^)]*)?\)")
_LINK_OPEN_RE = re.compile(r"\[[^\]]*\]\(")


def _iter_links(text):
    """Yield (start, end, target) for each markdown link.

    The destination is read as one token, holding any
    balanced parenthesis pairs inside it whole, or as an
    angle bracket form, and an optional title after it is
    read in
    its stated forms: a double quoted title, a single quoted
    title, or a parenthesis title. A title is read to its own
    closing mark, so a closing parenthesis inside a quoted
    title does not end the link, and a parenthesis title ends
    at the parenthesis that stands before the link's own
    closing parenthesis.
    """
    index = 0
    while index < len(text):
        match = _LINK_OPEN_RE.search(text, index)
        if not match:
            return
        position = match.end()
        while position < len(text) and text[position] in " \t":
            position += 1
        if position < len(text) and text[position] == "<":
            close = text.find(">", position + 1)
            if close < 0:
                index = match.start() + 1
                continue
            target = text[position + 1:close]
            position = close + 1
        else:
            start = position
            depth = 0
            while position < len(text):
                char = text[position]
                if char == "\\" and position + 1 < len(text) \
                        and text[position + 1] in "()\\":
                    # An escaped parenthesis or backslash
                    # stands as a destination character, item
                    # 159, and takes no part in the depth
                    # reading: an escaped closing parenthesis
                    # does not end the destination.
                    position += 2
                    continue
                if char in " \t":
                    break
                if char == "(":
                    depth += 1
                elif char == ")":
                    if depth == 0:
                        break
                    depth -= 1
                position += 1
            target = text[start:position]
        while position < len(text) and text[position] in " \t":
            position += 1
        if position < len(text) and text[position] in "\"'(":
            opener = text[position]
            if opener == "(":
                end = -1
                scan = position + 1
                while True:
                    candidate = text.find(")", scan)
                    if candidate < 0:
                        break
                    after = candidate + 1
                    while (after < len(text)
                           and text[after] in " \t"):
                        after += 1
                    if after < len(text) and text[after] == ")":
                        end = candidate
                        break
                    scan = candidate + 1
                if end < 0:
                    index = match.start() + 1
                    continue
                position = end + 1
            else:
                end = text.find(opener, position + 1)
                if end < 0:
                    index = match.start() + 1
                    continue
                position = end + 1
            while position < len(text) and text[position] in " \t":
                position += 1
        if position < len(text) and text[position] == ")":
            yield (match.start(), position + 1, target)
            index = position + 1
        else:
            index = match.start() + 1
_URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\]\)\"']+")
_BRACKET_RE = re.compile(r"\[(\d+)\]")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*$")
_MARKER_RE = re.compile(r"^(?:[-*+]|\d+[.)]|[A-Za-z][.)])\s+(.+)$")
_BARE_HOST_RE = re.compile(
    r"^(?:[A-Za-z0-9-]+[.．。｡])+[A-Za-z]{2,}[.．。｡]?"
    r"(?::[0-9]+)?[.．。｡]?(?:/\S*|[?#]\S*)?$")
_REF_ENTRY_RE = re.compile(
    r"^\s*(?:[-*+]\s*)?\[?(\d+)\]?\s*[.)]\s+(\S+)(?:\s+.*)?$")
_BARE_DOMAIN_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9._．。｡-])(?:[A-Za-z0-9-]+[.．。｡])+[A-Za-z]{2,}"
    r"[.．。｡]?(?::[0-9]+)?[.．。｡]?(?:[/?#]\S*)?")
_REFERENCE_DEFINITION_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*\S+")
_REF_DEF_START_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(.*)$")
_SETEXT_UNDERLINE_RE = re.compile(r"^\s{0,3}(=+|-+)\s*$")
_REF_ENTRY_HEAD_RE = re.compile(
    r"^\s*(?:[-*+]\s*)?(?:\[(\d+)\]\s*(?:[.)]\s*)?|(\d+)\s*[.)]\s+)"
    r"(.+)$")
_BARE_ENTRY_TARGET_RE = re.compile(
    r"^(?:[A-Za-z0-9-]+[.．。｡])+[A-Za-z]{2,}[.．。｡]?"
    r"(?::[0-9]+)?[.．。｡]?$")


def _target_is_valid(target):
    """A target counts only where it parses with a host and a
    well formed port, plan Section 10.4 primitive P4 and brief
    item 155: a malformed port or a missing host makes the
    target malformed, and it counts no citation."""
    try:
        parts = urlsplit(str(target).strip())
    except ValueError:
        return False
    if (parts.scheme or "").casefold() not in ("http", "https"):
        return False
    if not parts.hostname:
        return False
    try:
        _ = parts.port
    except ValueError:
        return False
    return True


def _is_title_text(text):
    """Whether a text stands whole in one of the three title
    forms: double quoted, single quoted, or parenthesised."""
    stripped = text.strip()
    if len(stripped) < 2:
        return False
    return ((stripped[0] == '"' and stripped[-1] == '"')
            or (stripped[0] == "'" and stripped[-1] == "'")
            or (stripped[0] == "(" and stripped[-1] == ")"))


def _definition_tail(text):
    """Read a destination at the head of a text.

    Returns the text standing after the destination where
    the text is a destination with at most a title after it,
    and None where it is not: a destination is one token or
    an angle bracket form, and what follows it may be empty
    or one title in a title form. Anything else standing
    after the destination is prose, not a definition tail.
    """
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("<"):
        close = stripped.find(">")
        if close < 0:
            return None
        rest = stripped[close + 1:].strip()
    else:
        parts = stripped.split(None, 1)
        rest = parts[1].strip() if len(parts) > 1 else ""
    if rest == "" or _is_title_text(rest):
        return rest
    return None


def _mask_non_answer_text(text):
    """Mask text that item 131 keeps out of answer text: HTML
    comments and reference definitions, at equal length so
    offsets stay aligned. An unclosed comment masks to the
    end of the text."""
    spans = []
    start = text.find("<!--")
    while start >= 0:
        end = len(text)
        if text.startswith("<!-->", start):
            end = start + 5
        elif text.startswith("<!--->", start):
            end = start + 6
        else:
            close = text.find("-->", start + 4)
            bang = text.find("--!>", start + 4)
            ends = []
            if close >= 0:
                ends.append(close + 3)
            if bang >= 0:
                ends.append(bang + 4)
            if ends:
                end = min(ends)
        spans.append((start, end))
        start = text.find("<!--", end)
    masked = _mask_spans(text, spans)
    lines = masked.split("\n")
    masked_line_indexes = set()
    for idx, line in enumerate(lines):
        match = _REF_DEF_START_RE.match(line)
        if not match:
            continue
        remainder = match.group(1)
        if remainder.strip():
            # A definition line stands only where what follows
            # the label is a destination with at most a title
            # after it. Prose standing in label form, a
            # destination followed by untitled words, is not a
            # definition and its line stands unmasked.
            tail = _definition_tail(remainder)
            if tail is None:
                continue
            masked_line_indexes.add(idx)
            if tail == "" and idx + 1 < len(lines) \
                    and _is_title_text(lines[idx + 1]):
                masked_line_indexes.add(idx + 1)
            continue
        # The split form: the destination stands on the
        # following line, and it must read as a destination
        # with at most a title after it for either line to
        # stand masked.
        following = idx + 1
        if following >= len(lines) or not lines[following].strip():
            continue
        tail = _definition_tail(lines[following])
        if tail is None:
            continue
        masked_line_indexes.add(idx)
        masked_line_indexes.add(following)
        if tail == "" and following + 1 < len(lines) \
                and _is_title_text(lines[following + 1]):
            masked_line_indexes.add(following + 1)
    position = 0
    line_spans = []
    for idx, line in enumerate(lines):
        if idx in masked_line_indexes:
            line_spans.append((position, position + len(line)))
        position += len(line) + 1
    return _mask_spans(masked, line_spans)


def _get(entity, name, default=None):
    if entity is None:
        return default
    if isinstance(entity, dict):
        return entity.get(name, default)
    return getattr(entity, name, default)


def _names_of(entity):
    names = []
    name = _get(entity, "name")
    if name:
        names.append(name)
    for alias in _get(entity, "aliases", []) or []:
        if alias and alias not in names:
            names.append(alias)
    return names


def normalise_host(host):
    """Host normalisation, item 42 as its own named function.

    The host is normalised to Unicode NFC, the non ASCII dot
    separators U+FF0E, U+3002, and U+FF61 are mapped to a full
    stop (item 149, a limb of the host pipeline), the result is
    case folded and lowercased, one trailing dot is stripped,
    and the host is compared in its A-label form. Www stripping
    never applies inside this function; it applies at domain
    level matching only.
    """
    if host is None:
        return ""
    text = unicodedata.normalize("NFC", str(host))
    for separator in ("\uff0e", "\u3002", "\uff61"):
        text = text.replace(separator, ".")
    text = text.strip()
    if text.endswith("."):
        text = text[:-1]
    text = text.casefold()
    labels = []
    for label in text.split("."):
        if not label:
            labels.append(label)
            continue
        try:
            label.encode("ascii")
            labels.append(label)
        except UnicodeEncodeError:
            try:
                labels.append(label.encode("idna").decode("ascii"))
            except (UnicodeError, ValueError):
                labels.append(label)
    return ".".join(labels)


def syntax_normalise_path(path):
    """Path syntax normalisation, item 40 limb (1), named alone.

    A percent encoded triplet standing for an unreserved
    character is decoded to that character; a triplet for any
    other character stands encoded with upper case hex digits.
    The decoding runs first and dot segment removal runs
    second. An empty path stands as the root path. The path
    letter case stands as written and is never folded.
    """
    if not path:
        return "/"
    out = []
    index = 0
    while index < len(path):
        char = path[index]
        if (char == "%" and index + 2 < len(path)
                and path[index + 1] in _HEX and path[index + 2] in _HEX):
            decoded = chr(int(path[index + 1:index + 3], 16))
            if decoded in _UNRESERVED:
                out.append(decoded)
            else:
                out.append("%" + path[index + 1:index + 3].upper())
            index += 3
        else:
            out.append(char)
            index += 1
    decoded_path = "".join(out)
    segments = []
    for segment in decoded_path.split("/"):
        if segment in ("", "."):
            continue
        if segment == "..":
            if segments:
                segments.pop()
            continue
        segments.append(segment)
    result = "/" + "/".join(segments)
    if decoded_path.endswith("/") and segments:
        result += "/"
    return result


def _normalise_query(query):
    """Query handling, item 40 limb (5).

    The remaining query is sorted by name then value,
    duplicates kept, and a valueless parameter is sorted by
    name with an empty value. No parameter is stripped in
    version 1 on the decided limb: the ref parameter is not a
    tracking parameter, and every other list member stands
    stopped at SEAM-LISTS.
    """
    if not query:
        return ""
    pairs = []
    for part in query.split("&"):
        if "=" in part:
            name, value = part.split("=", 1)
        else:
            name, value = part, ""
        pairs.append((name, value))
    pairs.sort(key=lambda pair: (pair[0], pair[1]))
    return "&".join(name + "=" + value for name, value in pairs)


def canonical_form(target):
    """The canonical form of a target, items 33 and 40.

    Scheme and host are normalised under items 42 and 43, with
    http and https merged, a default port dropped, a non
    default port kept, and userinfo never part of the host.
    The path carries the syntax normalisation of limb (1) with
    a trailing slash removed except for the root path. The
    query stands under limb (5) and no fragment is carried.
    The canonical form is a matching key only.
    """
    text = str(target).strip()
    parts = urlsplit(text)
    host = normalise_host(parts.hostname or "")
    scheme = (parts.scheme or "").casefold()
    try:
        port = parts.port
    except ValueError:
        port = None
    port_part = ""
    if port is not None and port not in (80, 443):
        port_part = ":%d" % port
    path = syntax_normalise_path(parts.path or "")
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    result = "https://" + host + port_part + path
    query = _normalise_query(parts.query or "")
    if query:
        result += "?" + query
    return result


def _host_of(target):
    try:
        parts = urlsplit(str(target).strip())
    except ValueError:
        return "", ""
    return (parts.scheme or "").casefold(), parts.hostname or ""


def _domain_level_host(host):
    normalised = normalise_host(host)
    if normalised.startswith("www."):
        normalised = normalised[4:]
    return normalised


def _host_matches_domain(host, domain):
    if not domain:
        return False
    target_host = _domain_level_host(host)
    registered = _domain_level_host(domain)
    if not target_host or not registered:
        return False
    return target_host == registered or target_host.endswith(
        "." + registered)


def _mask_spans(text, spans):
    chars = list(text)
    for start, end in spans:
        for index in range(start, end):
            if chars[index] not in ("\n", "\r"):
                chars[index] = " "
    return "".join(chars)


def _link_spans(text):
    return [(start, end, target)
            for start, end, target in _iter_links(text)]


def _bare_url_spans(text, excluded):
    spans = []
    for match in _URL_RE.finditer(text):
        if any(start <= match.start() < end for start, end, _ in excluded):
            continue
        spans.append((match.start(), match.end(), match.group(0)))
    return spans


def _clean_target(raw):
    target = raw.strip()
    while target and target[-1] in ".,;:!?":
        target = target[:-1]
    return target


def _extract_targets(text):
    """Targets as written in a text chunk, in file order.

    Markdown link targets and bare targets both stand as
    targets. The target as written is returned; matching uses
    the canonical form built from it.
    """
    links = _link_spans(text)
    targets = [target for _, _, target in links]
    for _, _, raw in _bare_url_spans(text, links):
        targets.append(_clean_target(raw))
    return targets


def _masked_for_mentions(text):
    """Text with link targets and bare URLs masked at equal
    length, item 46, so masking shifts no later offset."""
    spans = []
    for start, end, _target in _iter_links(text):
        # The target opening parenthesis is the one standing
        # at the link delimiter, judged from the link's own
        # target parenthesis. A parenthesis inside the link
        # text stands before it and is not the mask start, so
        # link text after such a parenthesis stays searched.
        delimiter = text.find("](", start, end)
        open_paren = delimiter + 1 if delimiter >= 0 else start
        spans.append((open_paren, end))
    masked = _mask_spans(text, spans)
    url_spans = [(start, end) for start, end, _
                 in _bare_url_spans(masked, [])]
    return _mask_spans(masked, url_spans)


def _fold_with_map(text):
    """Case fold a text one character at a time, keeping a map
    from each folded position to the position of its source
    character in the supplied text. A character whose fold is
    longer than one character, such as a sharp s folding to
    two letters, would otherwise shift every later position
    when folded positions are read as supplied positions."""
    folded_parts = []
    mapping = []
    for index, char in enumerate(text):
        piece = char.casefold()
        folded_parts.append(piece)
        mapping.extend([index] * len(piece))
    return "".join(folded_parts), mapping


def _scan_mentions(masked_text, names):
    """Longest first mention scan over masked text, item 46.

    At each position the longest name is taken first and a span
    consumed by a match is not counted again. A match flanked
    by a letter or a digit on either side does not count. The
    search runs case insensitively for all names. Returns a
    list of (offset, registered name) in file order.
    """
    supplied_text = unicodedata.normalize("NFC", masked_text)
    folded_text, fold_map = _fold_with_map(supplied_text)
    prepared = []
    for position, name in enumerate(names):
        if not name:
            continue
        folded_name = unicodedata.normalize("NFC", str(name)).casefold()
        if folded_name:
            prepared.append((name, folded_name, position))
    ordered = sorted(
        prepared, key=lambda item: (-len(item[1]), item[2]))
    folded = [(name, folded_name) for name, folded_name, _ in ordered]
    found = []
    index = 0
    length = len(folded_text)
    while index < length:
        matched = None
        for name, folded_name in folded:
            end = index + len(folded_name)
            if end > length:
                continue
            if folded_text[index:end] != folded_name:
                continue
            origin = fold_map[index]
            origin_end = fold_map[end - 1] + 1 if end > index else origin
            if origin > 0 and (supplied_text[origin - 1].isalpha()
                               or supplied_text[origin - 1].isdigit()
                               or supplied_text[origin - 1] == "_"):
                continue
            if origin_end < len(supplied_text) and (
                    supplied_text[origin_end].isalpha()
                    or supplied_text[origin_end].isdigit()
                    or supplied_text[origin_end] == "_"):
                continue
            matched = (origin, name, end)
            break
        if matched is None:
            index += 1
        else:
            found.append((matched[0], matched[1]))
            index = matched[2]
    return found


def _domain_offsets(masked_text, domain):
    if not domain:
        return []
    needle = unicodedata.normalize("NFC", str(domain)).casefold()
    for separator in ("\uff0e", "\u3002", "\uff61"):
        needle = needle.replace(separator, ".")
    found = []
    start = 0
    supplied_text = unicodedata.normalize("NFC", masked_text)
    # The non ASCII dot separators of item 149 are mapped to
    # a full stop before the search, as normalise_host maps
    # them for the URL host reading. Each separator is one
    # character and its mapping is one character, so every
    # position in the searched text stands at its supplied
    # position.
    for separator in ("\uff0e", "\u3002", "\uff61"):
        supplied_text = supplied_text.replace(separator, ".")
    folded_text, fold_map = _fold_with_map(supplied_text)
    while True:
        index = folded_text.find(needle, start)
        if index < 0:
            return found
        end = index + len(needle)
        origin = fold_map[index]
        origin_end = fold_map[end - 1] + 1 if end > index else origin
        before_char = supplied_text[origin - 1] if origin > 0 else ""
        after_char = (supplied_text[origin_end]
                      if origin_end < len(supplied_text) else "")
        before_ok = not (
            before_char.isalpha() or before_char.isdigit()
            or before_char in ("-", "@", "_"))
        if after_char == ".":
            # The boundary is judged on what follows the dot.
            # A label character after the dot continues the
            # host, as in a lookalike host, and bars the hit.
            # Anything else, a space, a slash, or the end of
            # the text, means the dot ends the sentence, the
            # line, or the host itself, and the hit stands.
            following = (supplied_text[origin_end + 1]
                         if origin_end + 1 < len(supplied_text) else "")
            after_ok = not (
                following.isalpha() or following.isdigit()
                or following in ("-", "_"))
        else:
            after_ok = not (
                after_char.isalpha() or after_char.isdigit()
                or after_char in ("-", "_"))
        if before_ok and after_ok:
            found.append(origin)
        start = index + 1


def _clean_heading_text(text):
    """Clean a heading's text for the closed set comparison:
    punctuation of any kind is ignored at the head of the
    heading text as at its tail, item 160, so a heading whose
    text stands wrapped in emphasis marks or quotation marks
    cleans to the same string as the plain heading."""
    cleaned = text.strip()
    while cleaned and not cleaned[-1].isalnum():
        cleaned = cleaned[:-1]
    while cleaned and not cleaned[0].isalnum():
        cleaned = cleaned[1:]
    return cleaned.strip().casefold()


def _split_sections(text):
    """Split the text into prose and references chunks.

    Returns (prose_text, references_text), each the full text
    with the other part masked by spaces at equal length, so
    offsets stay aligned with the extracted text. The heading
    set is closed, matched case insensitively ignoring
    trailing punctuation, item 160. A references section runs
    to the next heading of the same or higher level or to the
    end of the text. An unheaded trailing list of two or more
    item lines at the end of the text, standing under no
    heading, is a references section; a target list under any
    other heading is prose.
    """
    lines = text.split("\n")
    offsets = []
    position = 0
    for line in lines:
        offsets.append(position)
        position += len(line) + 1
    headings = {}
    setext_underlines = set()
    for idx, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match:
            cleaned = match.group(2).strip().rstrip("#").strip()
            cleaned = _clean_heading_text(cleaned)
            headings[idx] = (len(match.group(1)),
                             cleaned in REFERENCES_HEADINGS)
            continue
        if line.strip() and idx + 1 < len(lines):
            underline = _SETEXT_UNDERLINE_RE.match(lines[idx + 1])
            if underline:
                cleaned = _clean_heading_text(line.strip())
                level = 1 if underline.group(1).startswith("=") else 2
                headings[idx] = (level,
                                 cleaned in REFERENCES_HEADINGS)
                setext_underlines.add(idx + 1)
    ref_lines = set()
    governing = {}
    current_ref = False
    current_level = None
    current_heading = None
    for idx in range(len(lines)):
        if idx in setext_underlines:
            governing[idx] = current_heading
            if current_ref:
                ref_lines.add(idx)
            continue
        if idx in headings:
            level, is_ref = headings[idx]
            if current_level is None or level <= current_level:
                current_ref = is_ref
                current_level = level
                current_heading = idx
                if is_ref:
                    ref_lines.add(idx)
            elif is_ref and not current_ref:
                current_ref = True
                current_level = level
                current_heading = idx
                ref_lines.add(idx)
            governing[idx] = current_heading
            continue
        governing[idx] = current_heading
        if current_ref:
            ref_lines.add(idx)
    trailing = []
    idx = len(lines) - 1
    while idx >= 0 and lines[idx].strip() == "":
        idx -= 1
    while (idx >= 0 and idx not in ref_lines
           and governing.get(idx) is None
           and _is_item_line(lines[idx])):
        trailing.append(idx)
        idx -= 1
    if len(trailing) >= 2:
        for line_idx in trailing:
            ref_lines.add(line_idx)
    prose_chars = list(text)
    ref_chars = list(text)
    for idx, line in enumerate(lines):
        start = offsets[idx]
        end = start + len(line)
        if idx in ref_lines:
            for pos in range(start, end):
                if prose_chars[pos] != "\n":
                    prose_chars[pos] = " "
        else:
            for pos in range(start, end):
                if ref_chars[pos] != "\n":
                    ref_chars[pos] = " "
    return "".join(prose_chars), "".join(ref_chars)


def _is_item_line(line):
    stripped = line.strip()
    if not stripped:
        return False
    if _URL_RE.fullmatch(stripped):
        return True
    if _BARE_HOST_RE.match(stripped):
        return True
    links = list(_iter_links(stripped))
    if (len(links) == 1 and links[0][0] == 0
            and links[0][1] == len(stripped)):
        return True
    match = _MARKER_RE.match(stripped)
    if match:
        content = match.group(1).strip()
        if _URL_RE.search(content) or list(_iter_links(content)):
            return True
        if _BARE_HOST_RE.match(content):
            return True
    return False


def _entry_target(rest):
    """The target an entry gives, in its stated entry forms:
    a markdown link gives its destination, an angle bracket
    form gives the target inside the brackets, and any other
    form gives its first token."""
    rest = rest.strip()
    if not rest:
        return ""
    link = next(_iter_links(rest), None)
    if link:
        return link[2]
    angle = re.search(r"<([^>\s]+)>", rest)
    if angle:
        return angle.group(1)
    return _clean_target(rest.split()[0].strip("<>"))


def _reference_entries(references_text):
    entries = {}
    for line in references_text.split("\n"):
        match = _REF_ENTRY_HEAD_RE.match(line)
        if not match:
            continue
        number = match.group(1) or match.group(2)
        try:
            key = str(int(number))
        except ValueError:
            key = number
        target = _entry_target(match.group(3))
        if target:
            entries[key] = target
    return entries


def _bracket_number_key(number):
    try:
        return str(int(number))
    except (TypeError, ValueError):
        return number


def _resolved_target_cited(target, domain):
    """Whether a resolved references entry target counts as a
    citation to the domain, item 31 with item 1. A target in
    URL form stands under the ordinary validity gate. A bare
    domain target in a reference position counts as cited to
    its own host."""
    if not target or not domain:
        return False
    text = str(target).strip().strip("<>")
    if "://" in text:
        scheme, host = _host_of(text)
        return scheme in ("http", "https") \
            and _target_is_valid(text) \
            and _host_matches_domain(host, domain)
    host_part = re.split(r"[/?#]", text, maxsplit=1)[0]
    host_part = host_part.rsplit("@", 1)[-1]
    if not _BARE_ENTRY_TARGET_RE.match(host_part):
        return False
    host = host_part.split(":", 1)[0]
    return _host_matches_domain(host, domain)


def _entity_outcome(chunk_masked_source, chunk_text, entity):
    """Named and cited outcomes for one entity over one chunk.

    chunk_text is the chunk with the other sections masked out;
    mentions are searched on the masked for mentions form of
    the chunk, and citations on its targets.
    """
    names = _names_of(entity)
    domain = _get(entity, "domain", "") or ""
    masked = _masked_for_mentions(chunk_text)
    mention_masked = _mask_spans(masked, [
        (match.start(), match.end())
        for match in _BARE_DOMAIN_TOKEN_RE.finditer(masked)])
    mentions = _scan_mentions(mention_masked, names)
    domain_hits = _domain_offsets(masked, domain) if domain else []
    if domain_hits and mentions:
        domain_spans = [(offset, offset + len(str(domain)))
                        for offset in domain_hits]
        mentions = [
            (offset, name) for offset, name in mentions
            if not any(offset < span_end and span_start < offset + len(name)
                       for span_start, span_end in domain_spans)
        ]
    named = bool(mentions) or bool(domain_hits)
    first_offset = None
    candidates = [offset for offset, _ in mentions] + domain_hits
    if candidates:
        first_offset = min(candidates)
    matched_aliases = []
    for _, name in mentions:
        if name not in matched_aliases:
            matched_aliases.append(name)
    cited = False
    for target in _extract_targets(chunk_text):
        scheme, host = _host_of(target)
        if scheme in ("http", "https") and _target_is_valid(target) \
                and _host_matches_domain(host, domain):
            cited = True
            break
    return {
        "named": named,
        "first_offset": first_offset,
        "matched_aliases": matched_aliases,
        "cited": cited,
        "mention_count": len(mentions) + len(domain_hits),
    }


def detect_answer(text, product, competitors):
    """Detect the AnswerMetrics outcomes for one answer.

    The one named input shape: the imported answer text, the
    product as registered (name, aliases, and domain), and the
    competitors as registered. Headline outcomes use the prose
    part only; mentions and citations in a references section
    are reported separately under item 160.
    """
    if text is None:
        text = ""
    text = unicodedata.normalize("NFC", str(text))
    text = _mask_non_answer_text(text)
    product = product or {}
    competitors = competitors or []
    prose_text, references_text = _split_sections(text)

    outcome = _entity_outcome(None, prose_text, product)
    named = outcome["named"]
    first_offset = outcome["first_offset"]
    named_early = False
    if named and first_offset is not None:
        word_position = len(text[:first_offset].split()) + 1
        named_early = word_position <= 100

    entries = _reference_entries(references_text)
    unresolved = 0
    cited = outcome["cited"]
    prose_targets = _extract_targets(prose_text)
    for match in _BRACKET_RE.finditer(prose_text):
        if prose_text[match.end():match.end() + 1] == "(":
            continue
        number = _bracket_number_key(match.group(1))
        if number in entries:
            domain = _get(product, "domain", "") or ""
            if _resolved_target_cited(entries[number], domain):
                cited = True
        else:
            unresolved += 1

    per_competitor = []
    for competitor in competitors:
        comp_outcome = _entity_outcome(None, prose_text, competitor)
        comp_cited = comp_outcome["cited"]
        comp_domain = _get(competitor, "domain", "") or ""
        if not comp_cited:
            for match in _BRACKET_RE.finditer(prose_text):
                if prose_text[match.end():match.end() + 1] == "(":
                    continue
                number = _bracket_number_key(match.group(1))
                if number in entries:
                    if _resolved_target_cited(
                            entries[number], comp_domain):
                        comp_cited = True
                        break
        if comp_domain == "":
            cited_value = None
            cited_reason = "domain empty: cited is not applicable"
        else:
            cited_value = comp_cited
            cited_reason = None
        per_competitor.append({
            "name": _get(competitor, "name"),
            "named": comp_outcome["named"],
            "cited": cited_value,
            "cited_reason": cited_reason,
        })

    ref_outcome = _entity_outcome(None, references_text, product)
    ref_targets = _extract_targets(references_text)
    ref_cited_count = 0
    domain = _get(product, "domain", "") or ""
    for target in ref_targets:
        scheme, host = _host_of(target)
        if scheme in ("http", "https") and _target_is_valid(target) \
                and _host_matches_domain(host, domain):
            ref_cited_count += 1
    inline_canonical = {canonical_form(target) for target in prose_targets
                         if _target_is_valid(target)}
    ref_canonical = {canonical_form(target) for target in ref_targets
                      if _target_is_valid(target)}

    return {
        "named": named,
        "named_early": named_early,
        "cited": cited,
        "first_offset": first_offset,
        "matched_aliases": outcome["matched_aliases"],
        "per_competitor": per_competitor,
        "unresolved_form_count": unresolved,
        "references_named_count": ref_outcome["mention_count"],
        "references_cited_count": ref_cited_count,
        "references_target_count": len(ref_canonical),
        "inline_target_count": len(inline_canonical),
        "references_section_split_counts": {
            "references_named_count": ref_outcome["mention_count"],
            "references_cited_count": ref_cited_count,
            "references_target_count": len(ref_canonical),
            "inline_target_count": len(inline_canonical),
        },
    }


def _normalised_cluster_text(text):
    folded = unicodedata.normalize("NFC", str(text)).casefold()
    return " ".join(folded.split())


def _shingles(normalised_text):
    words = normalised_text.split()
    return {tuple(words[index:index + 5])
            for index in range(len(words) - 4)} if len(words) >= 5 else set()


def _similar_components(type_sets):
    """The components of the similarity graph over distinct
    non empty shingle sets, computed exactly.

    Two sets are similar where their shared count stands at
    the 0.80 Jaccard bound, judged in integers as shared
    times 9 standing at least 4 times the sum of the sizes.
    No structure grows with the number of pairs and no subset
    of a set is ever stored: an inverted index over single
    shingles stands in place of both.

    Each component grows from one seed set. The seed pass
    stands in prefix form: the seed shingles stand ordered
    by their posting counts, a set similar to the seed must
    share a shingle of the seed prefix at the rare end of
    that ordering, and the candidates those postings name
    stand judged exactly against the seed, so every set
    similar to the seed joins at once, which settles a
    clique shape in that one pass, at a price set by the
    prefix postings in place of the postings of the whole
    seed. Where the exact judgement of the candidates
    stands priced past a counted reading, the seed pass
    stands in that counted form instead, at any seed size
    and at any prefix posting total: the shared count of
    every unvisited set with the seed stands counted in
    parallel bit planes in batches of the seed shingles
    in their rare first order, the planes standing loaded
    with the allowance its size carries for each set, so
    a set whose counted misses stand past its allowance
    holds a plane value standing below the count of
    shingles counted and stands excluded in full and
    counted no further, the survivor judgement standing
    as one comparison of the planes against the counted
    total for every size together, and the sets standing
    live at the end of the counting stand at exactly the
    sets whose full count reaches the threshold for their
    size, the same exact judgement at a price set by the
    batches the live sets survive and by one allowance
    plane build per distinct seed size.
    The component then grows
    layer by layer from the sets that joined last, the
    frontier. A set can join through a frontier member only
    where it shares a shingle with one, so the candidates of
    a layer are the unvisited sets standing in the postings
    of the distinct frontier shingles, each posting holding
    unvisited sets only. A candidate stands counted against
    each frontier member on that member's own threshold:
    its shared count with the seed plus the part of the
    member standing outside the seed bounds it, and so does
    its shared count with the frontier, counted from the
    light postings with the heavy shingles counted as a
    bound per member, and a member whose size cannot reach
    the bound for the candidate's size stands impossible
    for it. A candidate excluded on every member's own
    threshold stands excluded in bulk for the layer, which
    holds a reject pool sharing one small common part out
    of every layer even where the frontier mixes sizes.
    The candidates the bounds leave open are judged
    exactly, against the frontier members that share one
    of a small picked set of the candidate shingles: a
    similar member misses at most the allowance of the
    candidate shingles that its threshold fixes, so it
    shares at least one of any allowance plus one of them.
    A chain shape, where each layer adds the next link or
    two, therefore costs a small candidate scan per layer
    in place of a scan of the whole component per pass.
    The layer work stands in the first queue, processed
    first and to exhaustion, and a candidate sharing only
    heavy shingles with the frontier, excluded on every
    member's own threshold, passes to a second queue and
    stands judged once against the whole component when
    the first queue stands exhausted, as the body of the
    computation states in full.
    """
    count = len(type_sets)
    # Shingles stand interned to small integers for the
    # whole computation, so the index, the postings, and
    # every count work on integers alone. The postings
    # stand as built, and a posting count per shingle,
    # lowered as sets stand marked, stands in place of a
    # posting rebuilt at every mark: a reader of a posting
    # judges the visited flag of each member it meets.
    shingle_ids = {}
    sets = []
    postings = []
    for index, shingle_set in enumerate(type_sets):
        id_set = set()
        for shingle in shingle_set:
            ident = shingle_ids.get(shingle)
            if ident is None:
                ident = len(shingle_ids)
                shingle_ids[shingle] = ident
                postings.append([])
            id_set.add(ident)
            postings[ident].append(index)
        sets.append(id_set)
    unvisited_count = [len(members) for members in postings]
    visited = [False] * count
    by_size = {}
    for index, id_set in enumerate(sets):
        by_size.setdefault(len(id_set), set()).add(index)
    remaining = count
    components = []
    # One ordering of the shingles for the whole
    # computation, by posting count, rare shingles first.
    # The seed pass reads the rare end of a seed as its
    # prefix, and the ordering stands fixed while it runs,
    # which is all the prefix argument the seed pass states
    # needs. Each set stands sorted once, at the first seed
    # pass that reads it, and the sorted form stands kept.
    shingle_rank = {}
    for rank, ident in enumerate(sorted(
            range(len(postings)),
            key=unvisited_count.__getitem__)):
        shingle_rank[ident] = rank
    ordered_cache = {}
    # Posting bitsets over the set indices, built lazily
    # per shingle the first time the counted seed reading
    # needs one and kept for the computation: bit position
    # index stands for the set of that index, in a byte
    # array read as a little endian integer. The size masks
    # stand built once, and the visited mask stands kept
    # by mark below, so the counted reading names its sets
    # from the masks alone.
    bit_width = (count + 7) // 8
    all_mask = (1 << count) - 1 if count else 0
    bit_postings = {}
    size_masks = {}
    for mask_index, mask_set in enumerate(sets):
        size_masks[len(mask_set)] = size_masks.get(
            len(mask_set), 0) | (1 << mask_index)
    visited_mask = 0
    sorted_sizes = sorted(size_masks)
    size_prefix = [0]
    for sorted_size in sorted_sizes:
        size_prefix.append(size_prefix[-1] | size_masks[sorted_size])

    def bit_posting(ident):
        posting = bit_postings.get(ident)
        if posting is None:
            packed = bytearray(bit_width)
            for other in postings[ident]:
                packed[other >> 3] |= 1 << (other & 7)
            posting = int.from_bytes(packed, "little")
            bit_postings[ident] = posting
        return posting

    allowance_planes_cache = {}

    band_sizes_cache = {}
    band_pointer_cache = {}

    def band_lowest_threshold(seed_size):
        # The lowest threshold standing at a seed size:
        # the threshold of the smallest size in the
        # threshold band of the seed size that still
        # holds an unvisited set, the threshold standing
        # nondecreasing in the size, or None where no
        # band size stands. The band sizes stand built
        # once per distinct seed size as a slice of the
        # sorted distinct sizes, and the pointer over
        # them stands kept per seed size and only
        # advances, a size whose sets all stand visited
        # never standing unvisited again, so the seed
        # pass reads this judgement in a step or two in
        # place of rebuilding the thresholds of every
        # distinct size standing at every seed.
        sizes = band_sizes_cache.get(seed_size)
        if sizes is None:
            band_lo = -(-4 * seed_size // 5)
            band_hi = 5 * seed_size // 4
            sizes = sorted_sizes[
                bisect_left(sorted_sizes, band_lo):
                bisect_right(sorted_sizes, band_hi)]
            band_sizes_cache[seed_size] = sizes
            band_pointer_cache[seed_size] = 0
        pointer = band_pointer_cache[seed_size]
        while pointer < len(sizes) and not by_size[sizes[pointer]]:
            pointer += 1
        band_pointer_cache[seed_size] = pointer
        if pointer == len(sizes):
            return None
        size = sizes[pointer]
        return -(-4 * (seed_size + size) // 9)

    def allowance_planes(seed_size):
        # The bit planes of the allowance of every set at
        # this seed size: plane bit b holds the sets whose
        # size stands in the threshold band of the seed
        # size and whose allowance at that size carries
        # bit b. The allowance of a size stands as the
        # seed size less the threshold for its size, a
        # nonincreasing step function of the size, so the
        # sizes carrying one bit of it stand as a union of
        # size intervals, each interval read from the
        # prefix masks over the sorted distinct sizes in
        # two lookups. The planes stand built once per
        # distinct seed size and kept for the computation,
        # so their price stands at the allowance range of
        # the seed size, never at the product of the batch
        # count and the distinct size count.
        cached = allowance_planes_cache.get(seed_size)
        if cached is not None:
            return cached
        band_lo = -(-4 * seed_size // 5)
        band_hi = 5 * seed_size // 4
        band_mask = size_prefix[bisect_right(sorted_sizes, band_hi)] ^ \
            size_prefix[bisect_left(sorted_sizes, band_lo)]
        top_allowance = seed_size - -(-4 * (seed_size + band_lo) // 9)
        planes = [0] * max(1, top_allowance.bit_length())
        if top_allowance:
            lo_index = bisect_left(sorted_sizes, band_lo)
            hi_index = bisect_right(sorted_sizes, band_hi)
            bit = 0
            while (1 << bit) <= top_allowance:
                width = 1 << bit
                step = width << 1
                plane = 0
                low_a = width
                while low_a <= top_allowance:
                    high_a = low_a + width - 1
                    if high_a > top_allowance:
                        high_a = top_allowance
                    # The sizes whose allowance stands in
                    # [low_a, high_a]: the allowance of a
                    # size stands at least a exactly where
                    # the size stands at most
                    # (5 * seed_size - 9 * a) // 4, and at
                    # most a exactly where the size stands
                    # past (5 * seed_size - 9 * a - 9) // 4.
                    s_high = (5 * seed_size - 9 * low_a) // 4
                    s_low = (5 * seed_size - 9 * high_a - 9) // 4 + 1
                    if s_low < band_lo:
                        s_low = band_lo
                    if s_high > band_hi:
                        s_high = band_hi
                    if s_low <= s_high:
                        first = bisect_left(
                            sorted_sizes, s_low, lo_index, hi_index)
                        last = bisect_right(
                            sorted_sizes, s_high, lo_index, hi_index)
                        if first < last:
                            plane |= size_prefix[last] ^ \
                                size_prefix[first]
                    low_a += step
                planes[bit] = plane
                bit += 1
        cached = (planes, band_mask)
        allowance_planes_cache[seed_size] = cached
        return cached

    def counted_seed_layer():
        # The shared count of every unvisited set with the
        # seed, counted in parallel in batches of the seed
        # shingles in their rare first order: one bit plane
        # per bit of the count, each seed shingle posting
        # added into the planes in turn, the postings
        # standing masked to the sets that stand live after
        # the batch before. The planes stand loaded at the
        # start with the allowance of each set at the seed
        # size, so the value they hold for a set stands at
        # its counted shared count plus its allowance, and
        # a set similar to the seed, whose misses stand at
        # most its allowance, holds a value standing at
        # least the count of shingles counted so far at
        # every point of the counting, while a set standing
        # below that mark at any point can never reach the
        # seed size the value must reach at the end. The
        # survivor judgement therefore stands as one
        # comparison of the planes against the counted
        # total, read in bitwise form once per batch for
        # every size together, in place of one comparison
        # per distinct size per batch, and the sets
        # standing live at the end of the counting stand
        # at exactly the sets whose full count reaches the
        # threshold for their size, the same exact
        # judgement the prefix form makes, so no candidate
        # stands judged set against set on this reading
        # and no set the rule names stands lost.
        planes, band_mask = allowance_planes(seed_size)
        active = band_mask & all_mask & ~visited_mask
        if not active:
            return []
        ordered = ordered_set(seed)
        planes = list(planes)
        counted = 0
        index = 0
        while index < len(ordered):
            batch = ordered[index:index + 128]
            index += len(batch)
            for ident in batch:
                carry = bit_posting(ident) & active
                level = 0
                while carry:
                    if level == len(planes):
                        planes.append(0)
                    next_carry = planes[level] & carry
                    planes[level] ^= carry
                    carry = next_carry
                    level += 1
            counted += len(batch)
            equal = all_mask
            greater = 0
            top = max(len(planes), counted.bit_length())
            for bit in range(top - 1, -1, -1):
                plane = planes[bit] if bit < len(planes) else 0
                if (counted >> bit) & 1:
                    equal &= plane
                else:
                    greater |= equal & plane
                    equal &= all_mask ^ plane
            active = (greater | equal) & active
            if not active:
                return []
            if counted < len(ordered):
                planes = [plane & active for plane in planes]
        layer = []
        mask = active
        while mask:
            lowest = mask & -mask
            layer.append(lowest.bit_length() - 1)
            mask ^= lowest
        return sorted(layer)

    def ordered_set(index):
        ordered = ordered_cache.get(index)
        if ordered is None:
            ordered = sorted(
                sets[index], key=shingle_rank.__getitem__)
            ordered_cache[index] = ordered
        return ordered

    def mark(index):
        nonlocal remaining, visited_mask
        visited[index] = True
        visited_mask |= 1 << index
        remaining -= 1
        by_size[len(sets[index])].discard(index)
        for ident in sets[index]:
            unvisited_count[ident] -= 1

    for seed in range(count):
        if visited[seed]:
            continue
        seed_set = sets[seed]
        seed_size = len(seed_set)
        component = [seed]
        mark(seed)
        # The seed pass in prefix form. A set similar to the
        # seed shares at least the threshold count of the
        # seed shingles for its size, so where the prefix
        # stands longer than the seed size less the smallest
        # threshold any unvisited size can carry, a similar
        # set shares at least one prefix shingle and stands
        # in that shingle posting. The candidates the prefix
        # postings name stand judged exactly, set against
        # set, and no other unvisited set can stand similar
        # to the seed. The counting form this replaces read
        # the posting of every seed shingle at every seed,
        # which a pool shared in varying subsets priced at
        # the product of the set count and the unvisited
        # count, no pool shingle standing universal and the
        # base standing at zero while every set stood
        # counted in full. The frontier bound that read the
        # counting pass results now reads the exact shared
        # count with the seed at the place it stands used,
        # in possible_positions below.
        first_layer = []
        if remaining:
            lowest_threshold = band_lowest_threshold(seed_size)
            if lowest_threshold is not None:
                prefix_length = seed_size - lowest_threshold + 1
                if prefix_length < 1:
                    prefix_length = 1
                if prefix_length > seed_size:
                    prefix_length = seed_size
                prefix = ordered_set(seed)[:prefix_length]
                # The counted reading stands taken where
                # the wide reading itself stood taken in
                # full, and beside it wherever the exact form
                # judgement of the prefix form stands priced
                # past it: that price stands at the candidate
                # count the prefix postings can name, bounded
                # by the posting total and by the unvisited
                # count, times the seed size, and a price
                # past 50,000 stands counted instead, at any
                # seed size and at any prefix posting total.
                # The counted reading stands exact on every
                # family it stands taken on, as its own
                # statement states, naming the same layer, so
                # no guard on the seed size and no guard on
                # the posting total stands between a family
                # and the backstop on this pass.
                prefix_total = sum(unvisited_count[shingle]
                                   for shingle in prefix)
                take_counted = (remaining >= 256
                                and seed_size <= 2000
                                and prefix_total > 1024) \
                    or min(remaining, prefix_total) * seed_size \
                    > 50000
                if take_counted:
                    first_layer = counted_seed_layer()
                else:
                    candidates = set()
                    for shingle in prefix:
                        for other in postings[shingle]:
                            if not visited[other]:
                                candidates.add(other)
                    for other in sorted(candidates):
                        shared = len(sets[other] & seed_set)
                        if shared * 9 >= 4 * (
                                seed_size + len(sets[other])):
                            first_layer.append(other)
        frontier = []
        for other in first_layer:
            if not visited[other]:
                mark(other)
                component.append(other)
                frontier.append(other)
        # The work of one component stands organised in two
        # queues. The first queue is the frontier itself:
        # layer by layer, candidates standing in the light
        # postings of the frontier stand counted against
        # each frontier member on that member's own
        # threshold, and the ones the per member bounds
        # leave open stand judged exactly at once. The
        # first queue stands processed first and to
        # exhaustion. A candidate standing in no light
        # posting shares only heavy shingles with the
        # frontier; where the per member bounds exclude it
        # for every member of the layer it does not stand
        # judged, sorted, and rescanned at the next layer
        # in the old form. It passes to the second queue,
        # deferred in a form that can still complete: the
        # set itself, named once, judged once against the
        # whole component when the first queue stands
        # exhausted. A deferred set that later stands in a
        # light posting has a frontier partner in hand, a
        # solution path already standing, so it leaves the
        # second queue and stands worked in the first
        # queue ahead of the second queue's own turn. A
        # deferred set that joins from the second queue
        # becomes frontier, the first queue resumes ahead
        # of the deferred sets still waiting, and the
        # deferred sets already judged in that pass stand
        # judged again against the grown component, so no
        # join through a deferred set is ever lost.
        deferred = set()
        deferred_order = []
        deferred_judged = {}
        while True:
            while frontier and remaining:
                frontier_shingles = set()
                for node in frontier:
                    frontier_shingles.update(sets[node])
                frontier_by_shingle = {}
                for position, node in enumerate(frontier):
                    for shingle in sets[node]:
                        frontier_by_shingle.setdefault(
                            shingle, []).append(position)
                # The candidates of a layer stand counted
                # against each frontier member on that
                # member's own terms before any one of them
                # stands judged. A shingle whose posting
                # holds more unvisited sets than the heavy
                # bound is a heavy shingle: a candidate
                # shares at most every heavy shingle of a
                # member with that member, so its light
                # count plus the smaller of its heavy count
                # and the member's heavy count bounds its
                # shared count with that member, and its
                # shared count with the seed plus the part
                # of the member standing outside the seed
                # bounds it again. A member whose size
                # alone cannot reach the bound for the
                # candidate's size stands impossible for
                # that candidate whatever the counts say.
                # A candidate excluded on every member's
                # own threshold stands excluded in bulk for
                # this layer, where the old form priced
                # every candidate against the smallest
                # frontier member alone and a mixed size
                # frontier let a reject pool through at
                # every layer.
                heavy = {
                    shingle for shingle in frontier_shingles
                    if unvisited_count[shingle] > 96}
                member_sizes = [len(sets[node]) for node in frontier]
                member_heavy = [
                    len(sets[node] & heavy) if heavy else 0
                    for node in frontier]
                member_added = [
                    len(sets[node] - seed_set) for node in frontier]
                light_counts = {}
                for shingle in frontier_shingles:
                    if shingle in heavy:
                        continue
                    for other in postings[shingle]:
                        if not visited[other]:
                            light_counts[other] = \
                                light_counts.get(other, 0) + 1

                def possible_positions(other, light_shared,
                                       heavy_shared):
                    other_size = len(sets[other])
                    shared_seed = len(sets[other] & seed_set)
                    positions = []
                    for position in range(len(frontier)):
                        size = member_sizes[position]
                        if min(other_size, size) * 9 < \
                                4 * (other_size + size):
                            continue
                        threshold = -(-4 * (other_size + size) // 9)
                        if light_shared + min(
                                heavy_shared,
                                member_heavy[position]) < threshold:
                            continue
                        if shared_seed + member_added[position] < \
                                threshold:
                            continue
                        positions.append(position)
                    return positions

                candidates = {}
                for other, light_shared in light_counts.items():
                    if other in deferred:
                        deferred.discard(other)
                    heavy_shared = \
                        len(sets[other] & heavy) if heavy else 0
                    positions = possible_positions(
                        other, light_shared, heavy_shared)
                    if positions:
                        candidates[other] = positions
                if heavy:
                    # A set standing in no light posting
                    # shares at most the heavy part of a
                    # member with it, so the heavy part alone
                    # must reach the smallest threshold that
                    # member can carry, at the smallest
                    # candidate size that member can stand
                    # similar to, before any such set can
                    # join at this layer. Where no member
                    # passes that test the enumeration does
                    # not stand run at all.
                    def heavy_can_reach(position):
                        size = member_sizes[position]
                        smallest = -(-4 * size // 5)
                        threshold = -(-4 * (smallest + size) // 9)
                        return member_heavy[position] >= threshold

                    if any(heavy_can_reach(position)
                           for position in range(len(frontier))):
                        for size, members in list(by_size.items()):
                            for other in members:
                                if other in light_counts:
                                    continue
                                if other in deferred:
                                    continue
                                heavy_shared = len(sets[other] & heavy)
                                if not heavy_shared:
                                    continue
                                positions = possible_positions(
                                    other, 0, heavy_shared)
                                if positions:
                                    candidates[other] = positions
                                else:
                                    deferred.add(other)
                                    deferred_order.append(other)
                if not candidates:
                    break
                new_frontier = []
                for other, positions in candidates.items():
                    if visited[other]:
                        continue
                    other_size = len(sets[other])
                    allowance = max(
                        other_size - -(
                            -4 * (other_size + member_sizes[position])
                            // 9)
                        for position in positions)
                    if allowance < 0:
                        continue
                    picked = sorted(
                        sets[other],
                        key=lambda shingle: len(
                            frontier_by_shingle.get(shingle, ()))
                    )[:allowance + 1]
                    position_set = set(positions)
                    picked_positions = set()
                    for shingle in picked:
                        for position in frontier_by_shingle.get(
                                shingle, ()):
                            if position in position_set:
                                picked_positions.add(position)
                    joined = False
                    for position in picked_positions:
                        node = frontier[position]
                        shared = len(sets[other] & sets[node])
                        if shared * 9 >= 4 * (
                                other_size + len(sets[node])):
                            joined = True
                            break
                    if joined:
                        mark(other)
                        component.append(other)
                        new_frontier.append(other)
                frontier = new_frontier
            if not deferred:
                break
            # The second queue, worked only where the first
            # queue stands exhausted, apart from the
            # promotion the first queue itself grants above.
            # Each deferred set stands judged against the
            # whole component, by size class first: a class
            # whose members the set's shared count with the
            # whole component union cannot reach, or whose
            # size the set's size cannot stand similar to,
            # stands excluded whole, and only a class the
            # bounds leave open stands judged exactly,
            # member by member.
            snapshot = [other for other in deferred_order
                        if other in deferred]
            deferred = set()
            deferred_order = []
            # A deferred set stands judged in this pass
            # against the part of the component that stands
            # new to it, and against no part it already
            # failed. No set changes as the component grows,
            # so a set that failed against the members of an
            # earlier pass cannot join through those members
            # in a later one, and deferred_judged records the
            # component length through which each waiting
            # set stands judged. The snapshot stands grouped
            # by that length, each group judged against the
            # members past its length alone, by size class
            # first in the form this pass has always stated.
            # The form this replaces rebuilt the component
            # union and read every waiting set against the
            # whole component at every pass, which a chain
            # joining one link per pass priced at the
            # product of the pass count and the deferred
            # count. The queue order stands untouched: this
            # pass stands worked only where the first queue
            # stands exhausted, a set that joins here stands
            # as frontier with the first queue resuming ahead
            # of the sets still waiting, and a waiting set
            # the first queue promotes stands worked there
            # ahead of this turn.
            component_at_pass = list(component)
            pass_length = len(component_at_pass)
            by_watermark = {}
            for other in snapshot:
                if visited[other]:
                    continue
                by_watermark.setdefault(
                    deferred_judged.get(other, 0), []).append(other)
            failures = []
            joined_list = []
            for watermark, group in by_watermark.items():
                check_members = component_at_pass[watermark:]
                if not check_members:
                    failures.extend(group)
                    continue
                if len(check_members) == 1:
                    node = check_members[0]
                    node_set = sets[node]
                    node_size = len(node_set)
                    for other in group:
                        other_size = len(sets[other])
                        shared = len(sets[other] & node_set)
                        if shared * 9 >= 4 * (other_size + node_size):
                            mark(other)
                            component.append(other)
                            joined_list.append(other)
                            deferred_judged.pop(other, None)
                        else:
                            failures.append(other)
                            deferred_judged[other] = pass_length
                    continue
                check_union = set()
                for node in check_members:
                    check_union.update(sets[node])
                check_by_size = {}
                for node in check_members:
                    check_by_size.setdefault(
                        len(sets[node]), []).append(node)
                for other in group:
                    other_size = len(sets[other])
                    union_shared = len(sets[other] & check_union)
                    joined = False
                    for size, members in check_by_size.items():
                        if min(other_size, size) * 9 < \
                                4 * (other_size + size):
                            continue
                        threshold = -(-4 * (other_size + size) // 9)
                        if union_shared < threshold:
                            continue
                        for node in members:
                            shared = len(sets[other] & sets[node])
                            if shared * 9 >= 4 * (other_size + size):
                                joined = True
                                break
                        if joined:
                            break
                    if joined:
                        mark(other)
                        component.append(other)
                        joined_list.append(other)
                        deferred_judged.pop(other, None)
                    else:
                        failures.append(other)
                        deferred_judged[other] = pass_length
            if not joined_list:
                break
            deferred_order = failures
            deferred = set(failures)
            frontier = joined_list
        components.append(component)
    return components

def cluster_answers(texts):
    """Cluster answers by the shingle rule, item 20 of Section 5.8.

    Each answer text is normalised to NFC, case folded, and
    whitespace collapsed before its word 5 gram shingle set is
    built. Two answers are similar where the Jaccard
    similarity of their shingle sets is at least 0.80. Where
    either shingle set is empty, identical normalised texts
    are similar and every other such pair is not. Clusters are
    the groups formed by joining every similar pair, with no
    transitivity required. Returns one cluster id per answer,
    the index of the first member of its cluster.
    """
    normalised = [_normalised_cluster_text(text) for text in texts]
    shingle_sets = [_shingles(text) for text in normalised]
    parent = list(range(len(texts)))

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(first, second):
        root_first, root_second = find(first), find(second)
        if root_first != root_second:
            parent[max(root_first, root_second)] = min(
                root_first, root_second)

    # Identical shingle sets are similar, and for an empty set
    # the normalised text decides, so answers are first grouped
    # by the pair of both and the pair work runs over groups.
    groups = {}
    group_of = []
    for index in range(len(texts)):
        key = (frozenset(shingle_sets[index]),
               normalised[index] if not shingle_sets[index] else None)
        if key not in groups:
            groups[key] = []
        groups[key].append(index)
        group_of.append(key)
    keys = list(groups)
    for key in keys:
        members = groups[key]
        for index in members[1:]:
            union(members[0], index)
    # A group with an empty shingle set is similar only to a
    # group with the same normalised text, and identical
    # empty groups already stand joined by their group key,
    # so the component search runs over the non empty groups
    # only and every other group stands as its own cluster.
    nonempty_keys = [key for key in keys if key[0]]
    if nonempty_keys:
        type_sets = [key[0] for key in nonempty_keys]
        for component in _similar_components(type_sets):
            first_member = groups[nonempty_keys[component[0]]][0]
            for other in component[1:]:
                union(first_member, groups[nonempty_keys[other]][0])
    return [find(index) for index in range(len(texts))]
