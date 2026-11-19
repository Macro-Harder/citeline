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

from html import unescape as _html_unescape
import re
import unicodedata
from urllib.parse import unquote, urlsplit
from citeline.shared import _host_from_authority, _similar_components

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
    # The lookbehind bars a letter, a digit, a dot, or a
    # hyphen before the token. An underscore stands outside
    # it: a domain token glued to the word before it by an
    # underscore is still a domain token for the mention
    # mask of item 46, so a name standing inside such a
    # token is judged as part of that host token and not
    # as a prose mention, while a name flanked by an
    # underscore in prose counts under item 46 as the
    # mention scan states.
    r"(?<![A-Za-z0-9.．。｡-])(?:[A-Za-z0-9-]+[.．。｡])+[A-Za-z]{2,}"
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


def _decode_link_piece(value):
    """Decode one link piece exactly once, in the stated
    order: entities decode once and percent sequences
    decode once, so a sequence the one decode leaves
    standing, such as a percent character from a double
    encoded form, is not decoded again downstream. This is
    the same decoding the checks module applies at its
    _decode_link_piece, under items 148 and 159 and
    decision D22."""
    return unquote(_html_unescape(value))


def _decoded_authority_parts(target):
    """Split one target on its authority, decoded first.

    Items 148 and 159 state the decode order whole:
    percent sequences and entities decode exactly once
    before host parsing. The raw authority piece, the
    text between the scheme separator and the first
    literal path, query, or fragment delimiter, is
    therefore decoded once before any authority cut is
    made, so a delimiter the decode produces, a slash,
    a colon, a fragment or query mark, or an at sign,
    acts as the delimiter it is. Returns the scheme
    prefix, the decoded authority, the decoded suffix
    that stood inside the raw authority piece after a
    decoded delimiter, and the remainder of the target
    after the raw authority piece, or None where the
    target carries no scheme separator. The form stands
    as the checks module states it at its own
    _decoded_authority_parts.
    """
    match = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", target or "")
    if not match:
        return None
    rest = target[match.end():]
    raw_end = len(rest)
    index = 0
    while index < len(rest):
        char = rest[index]
        if char == "&":
            entity = re.match(
                r"&(?:#\d+;?|#[xX][0-9A-Fa-f]+;?"
                r"|[A-Za-z][A-Za-z0-9]+;)",
                rest[index:],
            )
            if entity:
                index += entity.end()
                continue
        if char in "/?#":
            raw_end = index
            break
        index += 1
    decoded = _decode_link_piece(rest[:raw_end])
    split = len(decoded)
    for index, char in enumerate(decoded):
        if char in "/?#":
            split = index
            break
    return (
        match.group(0),
        decoded[:split],
        decoded[split:],
        rest[raw_end:],
    )


def _decoded_target_text(target):
    """The target text after the one decoding items 148
    and 159 state, with the decoded authority standing in
    place of the raw authority piece. A target with no
    scheme separator stands as written."""
    text = str(target).strip()
    parts = _decoded_authority_parts(text)
    if parts is None:
        return text
    return parts[0] + parts[1] + parts[2] + parts[3]


def _target_is_valid(target):
    """A target counts only where it parses with a host and a
    well formed port, plan Section 10.4 primitive P4 and brief
    item 155: a malformed port or a missing host makes the
    target malformed, and it counts no citation. The parse
    stands on the target after the one decoding items 148
    and 159 state, and a host that still holds a percent
    character after that one decode is malformed under
    item 148 in the same way."""
    text = _decoded_target_text(target)
    try:
        parts = urlsplit(text)
    except ValueError:
        return False
    if (parts.scheme or "").casefold() not in ("http", "https"):
        return False
    if not parts.hostname:
        return False
    if "%" in (parts.hostname or ""):
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
    decoded_parts = _decoded_authority_parts(text)
    if decoded_parts is not None:
        # The key judges the target the stated decode
        # produces: the decoded authority stands in place
        # of the raw authority piece, with any suffix a
        # decoded delimiter produced standing before the
        # raw remainder, as the checks canonical form
        # states the same reading.
        effective = (decoded_parts[0] + decoded_parts[1]
                     + decoded_parts[2] + decoded_parts[3])
        authority = decoded_parts[1]
    else:
        effective = text
        authority = ""
        match = re.match(
            r"^[A-Za-z][A-Za-z0-9+.-]*://([^/?#]*)", effective)
        if match:
            authority = match.group(1)
    try:
        parts = urlsplit(effective)
    except ValueError:
        return text
    # The host stands in its authority form, brackets and
    # all, not in urlsplit's hostname form: the hostname
    # form strips the brackets of an IPv6 literal, so a
    # bracketed address at a port and a longer address
    # whose tail reads as that port built one key for two
    # distinct targets, against item 33.
    host = normalise_host(_host_from_authority(authority))
    if "%" in host:
        # A host still holding a percent character after
        # the one decode is malformed under item 148; its
        # key stands as the target as written, never as
        # the key of the host it would decode to twice.
        return text
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
    text = str(target).strip()
    decoded_parts = _decoded_authority_parts(text)
    if decoded_parts is not None:
        scheme = decoded_parts[0][:-3].casefold()
        return scheme, _host_from_authority(decoded_parts[1])
    try:
        parts = urlsplit(text)
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


_ZERO_WIDTH = frozenset(
    ("\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"))


def _remove_zero_width(text):
    """Remove the zero width characters of item 152 from a
    matching copy, keeping a map from each kept position to
    its position in the supplied text. The zero width class
    only stands removed here: the wider removal set of item
    152 stands referred at SEAM-LISTS and no character
    outside this class is removed by this function."""
    kept = []
    mapping = []
    for index, char in enumerate(text):
        if char in _ZERO_WIDTH:
            continue
        kept.append(char)
        mapping.append(index)
    return "".join(kept), mapping


def _scan_mentions(masked_text, names):
    """Longest first mention scan over masked text, item 46.

    At each position the longest name is taken first and a span
    consumed by a match is not counted again. A match flanked
    by a letter or a digit on either side does not count. The
    search runs case insensitively for all names. Returns a
    list of (offset, registered name) in file order.

    The matching copy is built under items 151 and 152: NFC
    first, then the zero width characters of item 152 are
    removed, then case folding, on the text side and on the
    name side alike. Offsets are read back through the two
    position maps to the supplied text, and the flank
    judgement stands on the matching copy, the text the
    removal leaves standing.
    """
    supplied_text = unicodedata.normalize("NFC", masked_text)
    cleaned_text, clean_map = _remove_zero_width(supplied_text)
    folded_text, fold_map = _fold_with_map(cleaned_text)
    prepared = []
    for position, name in enumerate(names):
        if not name:
            continue
        cleaned_name, _ = _remove_zero_width(
            unicodedata.normalize("NFC", str(name)))
        folded_name = cleaned_name.casefold()
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
            clean_origin = fold_map[index]
            clean_end = fold_map[end - 1] + 1 if end > index \
                else clean_origin
            if clean_origin > 0 and (
                    cleaned_text[clean_origin - 1].isalpha()
                    or cleaned_text[clean_origin - 1].isdigit()):
                continue
            if clean_end < len(cleaned_text) and (
                    cleaned_text[clean_end].isalpha()
                    or cleaned_text[clean_end].isdigit()):
                continue
            origin = clean_map[clean_origin] if clean_map else 0
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
    # A bare destination stands under the same one
    # decoding as a destination in URL form, items 148
    # and 159, applied before its host is cut out, so a
    # delimiter the decode produces acts as the delimiter
    # it is in this form as in the URL form.
    text = _decode_link_piece(text)
    host_part = re.split(r"[/?#]", text, maxsplit=1)[0]
    host_part = host_part.rsplit("@", 1)[-1]
    if "%" in host_part:
        return False
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


def _is_hangul_jamo(char):
    return "\u1100" <= char <= "\u11ff"


def _nfc_with_map(text):
    """NFC normalise a text, keeping a map from each position
    of the normalised form to the position of its source in
    the supplied text, with one sentinel entry mapping the
    end of the normalised form to the end of the supplied
    text.

    Normalisation is applied cluster by cluster: a cluster
    is one starter together with the combining characters
    that follow it, with a Hangul jamo sequence standing as
    one cluster, and canonical composition and reordering
    stand inside a cluster and never across one, so the
    normalised form of the whole text is the join of the
    normalised forms of its clusters.
    """
    clusters = []
    for char in text:
        if clusters and (
                unicodedata.combining(char) != 0
                or (_is_hangul_jamo(char)
                    and (_is_hangul_jamo(clusters[-1][-1])
                         or "\uac00" <= clusters[-1][-1] <= "\ud7a3"))):
            clusters[-1] += char
        else:
            clusters.append(char)
    parts = []
    mapping = []
    supplied_position = 0
    for cluster in clusters:
        normalised = unicodedata.normalize("NFC", cluster)
        parts.append(normalised)
        for offset in range(len(normalised)):
            mapping.append(
                supplied_position + min(offset, len(cluster) - 1))
        supplied_position += len(cluster)
    mapping.append(len(text))
    return "".join(parts), mapping


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
    supplied_text = str(text)
    text, nfc_map = _nfc_with_map(supplied_text)
    text = _mask_non_answer_text(text)
    product = product or {}
    competitors = competitors or []
    prose_text, references_text = _split_sections(text)

    outcome = _entity_outcome(None, prose_text, product)
    named = outcome["named"]
    first_offset = outcome["first_offset"]
    if first_offset is not None:
        # Offsets inside the pipeline stand in the
        # coordinates of the normalised matching text;
        # first_offset is reported in the coordinates of
        # the text as supplied, items 46 and 151, read
        # back through the normalisation map.
        first_offset = nfc_map[first_offset]
    named_early = False
    if named and first_offset is not None:
        word_position = len(supplied_text[:first_offset].split()) + 1
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
