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
_URL_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\]\)\"']+")
_BRACKET_RE = re.compile(r"\[(\d+)\]")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*$")
_MARKER_RE = re.compile(r"^(?:[-*+]|\d+[.)]|[A-Za-z][.)])\s+(.+)$")
_BARE_HOST_RE = re.compile(
    r"^(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}(?:/\S*)?$")
_REF_ENTRY_RE = re.compile(
    r"^\s*(?:[-*+]\s*)?\[?(\d+)\]?\s*[.)]\s+(\S+)\s*$")


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
    text = text.casefold().lower()
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
    return [(match.start(), match.end(), match.group(2))
            for match in _LINK_RE.finditer(text)]


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
    for match in _LINK_RE.finditer(text):
        open_paren = match.group(0).index("(") + match.start()
        spans.append((open_paren, match.end()))
    masked = _mask_spans(text, spans)
    url_spans = [(start, end) for start, end, _
                 in _bare_url_spans(masked, [])]
    return _mask_spans(masked, url_spans)


def _scan_mentions(masked_text, names):
    """Longest first mention scan over masked text, item 46.

    At each position the longest name is taken first and a span
    consumed by a match is not counted again. A match flanked
    by a letter or a digit on either side does not count. The
    search runs case insensitively for all names. Returns a
    list of (offset, registered name) in file order.
    """
    ordered = sorted(names, key=lambda name: (-len(name), names.index(name)))
    folded = [(name, name.casefold()) for name in ordered if name]
    found = []
    index = 0
    length = len(masked_text)
    while index < length:
        matched = None
        for name, folded_name in folded:
            end = index + len(name)
            if end > length:
                continue
            if masked_text[index:end].casefold() != folded_name:
                continue
            if index > 0 and (masked_text[index - 1].isalpha()
                              or masked_text[index - 1].isdigit()):
                continue
            if end < length and (masked_text[end].isalpha()
                                 or masked_text[end].isdigit()):
                continue
            matched = (index, name, end)
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
    needle = str(domain).casefold()
    found = []
    start = 0
    folded_text = masked_text.casefold()
    while True:
        index = folded_text.find(needle, start)
        if index < 0:
            return found
        end = index + len(needle)
        before_ok = index == 0 or not (
            masked_text[index - 1].isalpha()
            or masked_text[index - 1].isdigit())
        after_ok = end >= len(masked_text) or not (
            masked_text[end].isalpha() or masked_text[end].isdigit())
        if before_ok and after_ok:
            found.append(index)
        start = index + 1


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
    for idx, line in enumerate(lines):
        match = _HEADING_RE.match(line)
        if match:
            cleaned = match.group(2).strip().rstrip("#").strip()
            cleaned = cleaned.rstrip(".:;!").strip().casefold()
            headings[idx] = (len(match.group(1)),
                             cleaned in REFERENCES_HEADINGS)
            continue
        stripped = line.strip()
        cleaned = stripped.rstrip(".:;!").strip().casefold()
        if cleaned in REFERENCES_HEADINGS:
            headings[idx] = (1, True)
    ref_lines = set()
    governing = {}
    current_ref = False
    current_level = None
    current_heading = None
    for idx in range(len(lines)):
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
    if _LINK_RE.fullmatch(stripped):
        return True
    match = _MARKER_RE.match(stripped)
    if match:
        content = match.group(1).strip()
        if _URL_RE.search(content) or _LINK_RE.search(content):
            return True
        if _BARE_HOST_RE.match(content):
            return True
    return False


def _reference_entries(references_text):
    entries = {}
    for line in references_text.split("\n"):
        match = _REF_ENTRY_RE.match(line)
        if match:
            entries[match.group(1)] = _clean_target(match.group(2))
    return entries


def _entity_outcome(chunk_masked_source, chunk_text, entity):
    """Named and cited outcomes for one entity over one chunk.

    chunk_text is the chunk with the other sections masked out;
    mentions are searched on the masked for mentions form of
    the chunk, and citations on its targets.
    """
    names = _names_of(entity)
    domain = _get(entity, "domain", "") or ""
    masked = _masked_for_mentions(chunk_text)
    mentions = _scan_mentions(masked, names)
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
        if scheme in ("http", "https") and _host_matches_domain(
                host, domain):
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
        number = match.group(1)
        if number in entries:
            scheme, host = _host_of(entries[number])
            domain = _get(product, "domain", "") or ""
            if scheme in ("http", "https") and _host_matches_domain(
                    host, domain):
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
                number = match.group(1)
                if number in entries:
                    scheme, host = _host_of(entries[number])
                    if scheme in ("http", "https") and _host_matches_domain(
                            host, comp_domain):
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
        if scheme in ("http", "https") and _host_matches_domain(
                host, domain):
            ref_cited_count += 1
    inline_canonical = {canonical_form(target) for target in prose_targets
                         if _host_of(target)[0] in ("http", "https")}
    ref_canonical = {canonical_form(target) for target in ref_targets
                      if _host_of(target)[0] in ("http", "https")}

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

    for first in range(len(texts)):
        for second in range(first + 1, len(texts)):
            first_set = shingle_sets[first]
            second_set = shingle_sets[second]
            if not first_set or not second_set:
                similar = normalised[first] == normalised[second]
            else:
                shared = len(first_set & second_set)
                union_size = len(first_set | second_set)
                similar = union_size > 0 and shared / union_size >= 0.80
            if similar:
                union(first, second)
    return [find(index) for index in range(len(texts))]
