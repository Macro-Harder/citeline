"""Page checks and scoring for Citeline, slice S3.

This module owns CheckResult and the ScoreObject computation.
It consumes an ExtractedPage and the registry facts the
registry states for the checks (the canonical line,
is_product_page, the product name, and category terms). It
never reads a supplied file. Dates arrive as call inputs,
never from a clock.

Seams honoured here, as the design plan states them:

1. SEAM-STATUS. Status is assigned only inside the
   assign_status seam in this module. The mapping from an
   earned value to pass, warn, or fail is unruled, so the
   seam invents no threshold. It returns the applicability
   outcome not_applicable where a check does not apply,
   and None where the unruled mapping would be needed.
   An applicability outcome is not a derivation from an
   earned value.
2. SEAM-LISTS. The list dependent limbs stand built:
   the comparison criterion word component earns its
   share, the fluff filler booster deduction is applied,
   and the unproven superlatives hit limb is built: hits
   from the printed lexicon deduct 0.34 each, floored at
   0, and each unproven span is reported as evidence.
3. SEAM-SCORE-EMPTY. For an empty extraction every check
   stands not applicable, and compute_score returns the
   stated absence form for value and band rather than a
   number, because that case stands unruled.
4. The description consistency rule precedence stands
   as verbatim, then drift, then absence, with verbatim
   judged after whitespace normalisation: the canonical
   line and the running text both stand with every
   whitespace run folded to one space before the
   comparison.
"""

import datetime
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from html import unescape as _html_unescape
from urllib.parse import unquote

__all__ = [
    "STATUS_VALUES",
    "HONESTY_SENTENCE",
    "SCORE_RULESET_VERSION",
    "CHECK_REGISTRY",
    "assign_status",
    "run_checks",
    "compute_score",
]

STATUS_VALUES = ("pass", "warn", "fail", "not_applicable")

HONESTY_SENTENCE = (
    "This score is a signal index. It measures the presence of "
    "citability signals. It is not validated as a predictor of "
    "citation, and it does not verify truth."
)

SCORE_RULESET_VERSION = "1"

# check_id, weight, evidence class, in the registry order.
CHECK_REGISTRY = (
    ("answer_first", 12, "tool_defined"),
    ("citations", 16, "paper_tested"),
    ("statistics", 13, "paper_tested"),
    ("quotations", 11, "paper_tested"),
    ("comparison", 10, "post_asserted"),
    ("freshness", 8, "post_asserted"),
    ("description_consistency", 8, "post_asserted"),
    ("keyword_stuffing", 8, "paper_tested"),
    ("fluff", 7, "post_asserted"),
    ("unproven_superlatives", 7, "tool_defined"),
)

_EVIDENCE_CHECKS = ("citations", "statistics", "quotations")

_LEXICON_CHECKS = (
    "quotations",
    "comparison",
    "freshness",
    "fluff",
    "unproven_superlatives",
)

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _get(record, name, default=None):
    if record is None:
        return default
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def _round3(value):
    return round(float(value) + 0.0, 3)


def _round_score(value):
    """Round a Decimal score value to one decimal place.

    The rounding is half up on the exact decimal value,
    the rounding the score formula states, applied alike
    to the headline score and to the secondary figure.
    """
    return float(
        value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    )


def assign_status(check_id, applicable=True, empty=False):
    """The SEAM-STATUS seam, the only place status is set.

    Applicability outcomes stand decided in the brief and
    are returned here. Every other status would need the
    earned value to status mapping, which stands unruled,
    so the seam returns None for an applicable check on a
    non empty page rather than inventing a threshold.
    """
    if empty or not applicable:
        return "not_applicable"
    return None


# ----------------------------------------------------------------
# Input access helpers


def _page_text(page):
    return _get(page, "running_text", "") or ""


def _page_sentences(page):
    sentences = _get(page, "sentences", []) or []
    return [str(s) for s in sentences]


def _fact_terms(facts):
    """Registry facts in the forms the registry states them."""
    name = _get(facts, "product_name")
    if not name:
        name = _get(facts, "name")
    aliases = list(_get(facts, "aliases", []) or [])
    category_terms = _get(facts, "category_terms")
    if category_terms is None:
        category_terms = _get(facts, "category", []) or []
    competitors = _get(facts, "competitors", []) or []
    return {
        "product_name": name,
        "aliases": aliases,
        "category_terms": list(category_terms or []),
        "canonical_line": _get(facts, "canonical_line"),
        "is_product_page": _get(facts, "is_product_page", True),
        "domain": _get(facts, "domain"),
        "competitors": competitors,
    }


def _term_pattern(term):
    parts = [re.escape(part) for part in str(term).split()]
    if not parts:
        return None
    body = r"\s+".join(parts)
    return re.compile(
        r"(?<![^\W_])" + body + r"(?![^\W_])",
        re.IGNORECASE,
    )


def _term_present(text, term):
    pattern = _term_pattern(term)
    if pattern is None:
        return False
    return pattern.search(text) is not None


def _term_count(text, term):
    pattern = _term_pattern(term)
    if pattern is None:
        return 0
    return len(pattern.findall(text))


def _sentence_offsets(text, sentences):
    """Start offset of each sentence, found in order."""
    offsets = []
    cursor = 0
    for sentence in sentences:
        found = text.find(sentence, cursor)
        if found < 0:
            found = text.find(sentence)
        if found < 0:
            offsets.append(cursor)
        else:
            offsets.append(found)
            cursor = found + len(sentence)
    return offsets


def _paragraph_spans(text):
    """Paragraph chunks of the running text, as offset spans."""
    spans = []
    start = 0
    for match in re.finditer(r"\n[ \t]*\n", text):
        spans.append((start, match.start()))
        start = match.end()
    spans.append((start, len(text)))
    return spans


def _span(text, start, end):
    return {"start": start, "end": end, "excerpt": text[start:end]}


# ----------------------------------------------------------------
# Citations, statistics, and quotations: the shared evidence
# computations. Each returns earned data plus the counts the
# score cap and the fluff check consume.


def _link_parts(link):
    target = _get(link, "target")
    text_value = _get(link, "text")
    start = _get(link, "start")
    end = _get(link, "end")
    return target, text_value, start, end


_DOT_SEPARATORS = ("\uff0e", "\u3002", "\uff61")


def _normalise_host(raw_host, _decoded=False):
    """The host reading items 42, 148, 149, and 150 state.

    Percent sequences decode exactly once, the non ASCII
    dot separators map to a full stop, the result is case
    folded with one trailing dot stripped and compared in
    its A label form. A host holding an empty label is
    malformed and stands as None, counting no citation.
    A host that still holds a percent character after the
    one decode is malformed on the second limb of item
    148 and stands as None in the same way. A host the
    caller has already decoded once, on the stated order
    at _decoded_authority_parts, stands judged on that
    one decode and is not decoded a second time.
    """
    if _decoded:
        text = str(raw_host)
    else:
        text = unquote(str(raw_host))
    if "%" in text:
        return None
    for separator in _DOT_SEPARATORS:
        text = text.replace(separator, ".")
    text = unicodedata.normalize("NFC", text).strip()
    if text.endswith("."):
        text = text[:-1]
    text = text.casefold()
    if not text:
        return None
    labels = []
    for label in text.split("."):
        if not label:
            return None
        try:
            label.encode("ascii")
            labels.append(label)
        except UnicodeEncodeError:
            try:
                labels.append(label.encode("idna").decode("ascii"))
            except (UnicodeError, ValueError):
                labels.append(label)
    return ".".join(labels)


def _decode_link_piece(value):
    """Decode one link piece exactly once, in the stated
    order: entities decode once and percent sequences
    decode once, so a sequence the one decode leaves
    standing, such as a percent character from a double
    encoded form, is not decoded again downstream."""
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
    target carries no scheme separator.
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
            # An entity reference stands inside the piece
            # it decodes in, so a delimiter character the
            # reference itself is written with, the hash of
            # a numeric reference above all, does not cut
            # the piece: the scan steps over a reference in
            # its written form and cuts after it. The step
            # over reads the reference whole at any written
            # length, a zero padded numeric reference
            # carrying its semicolon as far out as its
            # padding writes it, and it steps over a
            # numeric reference with no semicolon, a form
            # the decoder this cure uses accepts.
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


def _host_from_authority(authority):
    host = authority.rsplit("@", 1)[-1]
    if host.startswith("["):
        closing = host.find("]")
        host = host[:closing + 1] if closing >= 0 else host
    else:
        host = host.split(":", 1)[0]
    return host


def _host_of(target):
    target = target.strip() if isinstance(target, str) else target
    parts = _decoded_authority_parts(target or "")
    if parts is not None:
        return _normalise_host(
            _host_from_authority(parts[1]), _decoded=True)
    match = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://([^/?#]+)", target or "")
    if not match:
        return None
    return _normalise_host(_host_from_authority(match.group(1)))


_UNRESERVED = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "0123456789-._~"
)
_HEXDIGITS = "0123456789abcdefABCDEF"


def _syntax_normalise_path(path):
    """Path syntax normalisation, item 40 limb (1).

    A percent triplet for an unreserved character decodes
    to that character and any other triplet stands with
    upper case hex digits. Dot segments are then removed
    and empty segments collapse, as the detection
    canonical form states the same operations.
    """
    if not path:
        return "/"
    out = []
    index = 0
    while index < len(path):
        char = path[index]
        if (char == "%" and index + 2 < len(path)
                and path[index + 1] in _HEXDIGITS
                and path[index + 2] in _HEXDIGITS):
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
    """Query handling, item 40 limb (5): sorted by name
    then value, duplicates kept, and a valueless parameter
    sorted with an empty value."""
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


def _canonical_target(target):
    """The canonical form of one citation target.

    Brief Section 5.7 items 33 and 40, in full: scheme and
    host normalised under items 42 and 43 with http and
    https merged and a default port dropped, the path
    under the syntax normalisation of limb (1) with a
    trailing slash removed except for the root path, the
    query under limb (5), and no fragment. This is the
    same form the detection canonical form builds, so two
    stated equivalent forms share one key and count once.
    """
    target = (target or "").strip()
    supplied = target
    parts = _decoded_authority_parts(target)
    decoded_authority = parts is not None
    if decoded_authority:
        # The canonical form judges the target the stated
        # decode produces, as the host reading does: the
        # decoded authority stands in place of the raw
        # authority piece, with any suffix a decoded
        # delimiter produced standing before the raw
        # remainder, so the two readings split one
        # destination the same way.
        target = parts[0] + parts[1] + parts[2] + parts[3]
    match = re.match(
        r"^[A-Za-z][A-Za-z0-9+.-]*://([^/?#]+)([^?#]*)"
        r"(?:\?([^#]*))?(?:#.*)?$",
        target,
    )
    if not match:
        return supplied
    authority = match.group(1).rsplit("@", 1)[-1]
    if authority.startswith("["):
        closing = authority.find("]")
        if closing >= 0:
            host_part = authority[:closing + 1]
            rest = authority[closing + 1:]
            port_part = rest[1:] if rest.startswith(":") else ""
        else:
            host_part, port_part = authority, ""
    else:
        host_part, _, port_part = authority.partition(":")
    host = _normalise_host(host_part, _decoded=decoded_authority)
    if host is None:
        return supplied
    authority = host
    if port_part:
        # Only a plain ASCII number stands judged by the
        # integer conversion. The conversion also accepts
        # forms a plain number is not, Unicode decimal
        # digits, an underscore between digits, a leading
        # sign, and surrounding space, and a port written
        # in any of those forms is not a plain number, so
        # it takes the as written limb below in the same
        # way as a port the conversion refuses.
        if re.fullmatch(r"[0-9]+", port_part):
            port = int(port_part)
        else:
            port = None
        if port is not None and port not in (80, 443):
            authority = host + ":" + str(port)
        if port is None:
            # A port that is not a plain number stands in
            # the key as written, on the canonical form's
            # own port rule that any port but a default
            # port stands in the key: it never vanishes
            # from the key in silence, so targets that
            # differ only in that port text key apart.
            authority = host + ":" + port_part
    path = _syntax_normalise_path(match.group(2) or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    key = authority + path
    query = _normalise_query(match.group(3) or "")
    if query:
        key += "?" + query
    return key


_TEXT_URL_PATTERN = re.compile(
    r"https?://(?:\[[^\]\s]+\](?::\d+)?"
    r"(?:/[^\s<>\"'(){}]*)?|[^\s<>\"'()\[\]{}]+)",
    re.IGNORECASE
)


def _citation_analysis(page, facts):
    text = _page_text(page)
    domain = _normalise_host(facts.get("domain") or "") \
        if facts.get("domain") else None
    counted = {}
    occurrences = []
    self_seen = False
    for link in _get(page, "links", []) or []:
        target, link_text, start, end = _link_parts(link)
        if not target:
            continue
        if isinstance(target, str):
            # A supplied target stands judged stripped, as
            # the canonical form judges it: whitespace at
            # its head is no part of the destination, and
            # a target carrying it counts as the citation
            # it is in the host reading and the scheme
            # test alike, not passed over in silence.
            target = target.strip()
            if not target:
                continue
        host = _host_of(target)
        if host is None:
            # An anchor link or a relative link is internal.
            continue
        scheme = target.split(":", 1)[0].casefold()
        if scheme not in ("http", "https"):
            continue
        if domain and (host == domain or host.endswith("." + domain)):
            self_seen = True
            continue
        if start is None or start < 0:
            start = text.find(link_text or target)
        if start is None or start < 0:
            start = 0
        if end is None or end <= start:
            end = start + len(link_text or target)
        span = _span(text, start, end)
        # Coverage runs over paragraph occurrences: every
        # standing of a counted target is kept here, while
        # the distinct count and the evidence spans below
        # keep one span per distinct target.
        occurrences.append(span)
        key = _canonical_target(target)
        if key in counted:
            continue
        counted[key] = span
    # The extraction of a markdown or plain text page carries
    # a bare or bracketed URL in the running text itself and
    # supplies no link entry for it, so a target the page
    # cites in that form stands in the text and nowhere else.
    # The check counts the distinct targets it finds in the
    # text it was given, under the same scheme and self
    # rules as a supplied link, so the count states the
    # targets the check itself found on either form. A
    # target already counted from a supplied link keeps its
    # supplied span and counts once.
    for match in _TEXT_URL_PATTERN.finditer(text):
        target = match.group(0).rstrip(".,;:!?")
        if not target:
            continue
        host = _host_of(target)
        if host is None:
            continue
        if domain and (host == domain or host.endswith("." + domain)):
            self_seen = True
            continue
        start = match.start()
        span = _span(text, start, start + len(target))
        occurrences.append(span)
        key = _canonical_target(target)
        if key in counted:
            continue
        counted[key] = span
    spans = [counted[key] for key in counted]
    count = len(spans)

    sentences = _page_sentences(page)
    offsets = _sentence_offsets(text, sentences)
    long_sentences = [
        (sentence, offset)
        for sentence, offset in zip(sentences, offsets)
        if len(sentence.split()) > 8
    ]
    if not long_sentences:
        coverage = 1.0 if count >= 1 else 0.0
    else:
        chunks = _paragraph_spans(text)
        holding = 0
        for sentence, offset in long_sentences:
            chunk = None
            for chunk_start, chunk_end in chunks:
                if chunk_start <= offset < chunk_end or (
                    offset == chunk_end == len(text)
                ):
                    chunk = (chunk_start, chunk_end)
                    break
            if chunk is None:
                chunk = chunks[-1]
            if any(
                chunk[0] <= span["start"] < chunk[1]
                for span in occurrences
            ):
                holding += 1
        coverage = holding / len(long_sentences)
    count_component = min(count, 3) / 3.0
    earned = _round3(0.5 * count_component + 0.5 * coverage)
    if count >= 1:
        reason = "CIT_COUNT"
    elif self_seen:
        # The specificity rule: a fixture whose targets are
        # all self citations carries this code, not the
        # no targets code.
        reason = "CIT_SELF_ONLY"
    else:
        reason = "CIT_NO_TARGETS"
    return {
        "earned": earned,
        "reason_code": reason,
        "evidence_spans": spans,
        "count": count,
    }


_STATISTIC_PATTERN = re.compile(
    r"(?<![A-Za-z0-9.])"
    r"(?P<token>"
    r"[$€£]?\d[\d,]*(?:\.\d+)?(?:%|:\d+(?:\.\d+)?)?"
    r"(?:\s*(?:-|to)\s*[$€£]?\d[\d,]*(?:\.\d+)?%?)?"
    r"(?:\s*(?:million|billion|thousand|percent))?"
    r")"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def _mask(text, spans):
    chars = list(text)
    for start, end in spans:
        for index in range(max(start, 0), min(end, len(chars))):
            chars[index] = " "
    return "".join(chars)


_QUOTED_SPAN_PATTERN = re.compile(
    r'"[^"\n]*"|"[^"\n]*”|“[^"\n]*"|“[^”\n]*”'
    r"|«[^»\n]*»|»[^«\n]*«|„[^“\n]*“|„[^”\n]*”"
    r"|‘(?:[^’\n]|’(?=[A-Za-z])|’(?=\d)"
    r"|’(?=\s[^\n’‘]*’))*’"
    r"|「[^」\n]*」|『[^』\n]*』"
    r"|《[^》\n]*》|〈[^〉\n]*〉|【[^】\n]*】"
    r"|〖[^〗\n]*〗|｢[^｣\n]*｣"
    r"|＂[^＂\n]*＂|‹[^›\n]*›|″[^″\n]*″|‚[^‘\n]*‘"
)

# The opening marks of the quoted span set the pattern
# above states, each with the closing marks its family
# admits, the mixed straight and curly closings standing
# as the earlier rounds cured them.
_QUOTE_OPENINGS = {
    '"': ('"', "\u201d"),
    "\u201c": ("\u201d", '"'),
    "\u00ab": ("\u00bb",),
    "\u00bb": ("\u00ab",),
    "\u201e": ("\u201c", "\u201d"),
    "\u2018": ("\u2019",),
    "\u201a": ("\u2018",),
    "\u300c": ("\u300d",),
    "\u300e": ("\u300f",),
    "\u300a": ("\u300b",),
    "\u3008": ("\u3009",),
    "\u3010": ("\u3011",),
    "\u3016": ("\u3017",),
    "\uff62": ("\uff63",),
    "\uff02": ("\uff02",),
    "\u2039": ("\u203a",),
    "\u2033": ("\u2033",),
}


def _saying_verb_pattern():
    """The saying verb forms of the attribution
    judgements, built from their stems.

    The charge states no verb limit, so the forms stand
    built from the saying verb stems in every form a
    stem carries: its plain form, its present form, its
    past form, and its participle form, with the
    spelling changes those forms carry, a consonant
    and y ending standing in its ies and ied forms, a
    final e standing dropped before ing and standing
    with a d alone in the past, and a doubled final
    consonant standing admitted beside the undoubled
    form, beside the irregular past forms the stems
    carry. The two word form pointed out stands in the
    set in its forms in the same way.
    """
    stems = (
        "say", "write", "ask", "add", "note", "call",
        "reply", "remark", "observe", "state", "declare",
        "explain", "continue", "insist", "report",
        "whisper", "answer", "respond", "comment",
        "mention", "claim", "announce", "conclude",
        "suggest", "admit", "warn", "shout", "murmur",
        "agree", "quote", "argue", "contend", "tell",
        "confirm", "predict", "think", "cry", "demand",
        "deny", "exclaim", "groan", "laugh", "mutter",
        "object", "offer", "promise", "protest",
        "repeat", "scream", "urge", "yell", "beg",
        "describe", "propose", "speak", "read",
    )
    forms = {
        "said", "wrote", "told", "thought", "spoke",
        "point out", "points out", "pointed out",
        "pointing out",
    }
    for stem in stems:
        forms.add(stem)
        if stem.endswith(("s", "x", "z", "ch", "sh")):
            forms.add(stem + "es")
        elif (
            len(stem) > 1 and stem.endswith("y")
            and stem[-2] not in "aeiou"
        ):
            forms.add(stem[:-1] + "ies")
        else:
            forms.add(stem + "s")
        if stem.endswith("e"):
            forms.add(stem + "d")
            forms.add(stem[:-1] + "ing")
        elif (
            len(stem) > 1 and stem.endswith("y")
            and stem[-2] not in "aeiou"
        ):
            forms.add(stem[:-1] + "ied")
            forms.add(stem + "ing")
        else:
            forms.add(stem + "ed")
            forms.add(stem + stem[-1] + "ed")
            forms.add(stem + "ing")
            forms.add(stem + stem[-1] + "ing")
        if stem.endswith("ee"):
            forms.add(stem + "ing")
    return "|".join(sorted(
        (re.escape(form) for form in forms),
        key=len, reverse=True))


_SAYING_VERB_PATTERN = _saying_verb_pattern()

# The saying verb forms standing past the built stem
# list, read on the form of the verb itself:
# a word carrying a verb form ending, its past form in
# ed, its participle form in ing, or its present form
# in s, beside the invariant form forecast and the
# irregular past form swore the batteries state. A verb
# read on its form alone stands as a companion
# attribution only where a subject in one of its
# ordinary forms stands after it, a capitalised name,
# a pronoun, or a determiner led noun phrase, so a tail
# standing opened by an auxiliary, whose next word
# stands in no subject form, reads as no attribution on
# this limb in the same way as it did on the stem list.
_SAYING_VERB_MORPH_PATTERN = (
    r"[A-Za-z]+(?:ed|ing|ies|es|s)"
    r"|swore|forecast"
)
_SAYING_SUBJECT_PATTERN = (
    r"(?:[A-Z][A-Za-z]*|she|he|they|we|it"
    r"|the|a|an|this|that)\b"
)


def _curly_single_is_internal(text, pos):
    """Whether the typographic apostrophe at pos stands
    inside a curly single span rather than closing it.

    A letter or a digit after it makes it a contraction,
    an elision, or a possessive inside a word, as the
    earlier rounds cured. Punctuation or a space after it
    makes it a plural possessive where a further closing
    mark for this span stands later on the line, before
    any new opening mark: the possessive before a comma,
    a semicolon, an exclamation mark, or the full stop of
    a sentence the span crosses stands in this form, so
    the span reads whole past it to its own closing. A
    nested quotation standing later on the line stands
    inside the span in the same way: its opening and its
    own closing stand as the span content, and the
    closing mark the reading seeks stands beyond the
    nested pair, so the possessive reads as internal
    where a closing stands beyond a nested pair as it
    does where one stands before any new opening. A
    nested opening that carries no closing of its own
    stands inside the span in the same way: the one
    further closing mark on the line then stands as
    this span closing, the nested opening standing as
    content before it, so the possessive reads as
    internal there too. That unmatched nested judgement
    stands only where the mark itself stands as a
    possessive, on one of the punctuation followers the
    possessive forms carry, a comma, a semicolon, an
    exclamation mark, a full stop, a question mark, or a
    colon: a mark followed by a space, with a separate
    quotation pair standing later on the line, stands as
    the closing of its own span, the pair standing as a
    span of its own, and a closing mark standing after
    that pair counts towards this span in the same way
    only where the mark stands as such a possessive.
    The follower alone never settles that judgement: the
    mark stands as a possessive on those followers only
    where the word the mark stands on reads as a plural
    possessive, a word of two or more letters ending in
    the letter s, the form a plural possessive carries
    where it stands before punctuation or a space. A
    true closing followed by one of the six punctuation
    marks, its word standing in no such form, closes its
    own span there, at two spans and at three spans
    alike, and a mark standing later on the line in that
    same possessive form, standing in the prose after a
    span, counts as no closing of that span, before a
    function word of the closing follower set and at the
    end of a sentence alike. A possessive followed by a
    space, with a matched nested pair standing between
    it and the outer closing, reads as internal on the
    same mark judgement, the one span reading whole past
    it to its own closing. Where no closing stands
    beyond a pair standing later on the line, the pair
    closing standing as this span closing under the
    unmatched nested reading, that reading stands only
    where the later opening stands introduced by plain
    prose between the mark and the opening, words with
    no punctuation of their own after the follower at
    the mark: where the pair stands directly after the
    follower, or after prose holding its own
    punctuation, the pair stands as a span of its own
    and a true closing in the s ending form closes its
    own span there, at two spans and at three spans
    alike. That unmatched reading stands further only
    where the mark stands in predicate possessive
    position: the word it stands on standing as the
    complement of a copula after a determiner, the
    form the pinned possessive compositions carry, it
    is the dogs, the first prize was the dogs. Where
    the word closes its clause in any other position,
    as the object of a lexical verb or as its subject,
    a possessive reading has no head noun standing in
    the clause for the mark to possess, and a true
    closing in the s ending form closes its own span
    there instead, in the evidence and in the
    statistics mask alike. The predicate pattern alone
    does not settle the two readings apart, a complete
    quoted sentence ending in a complement noun after
    a copula and a determiner carrying the same
    pattern, and the presence of either outer span
    mark on the line alone settles nothing either, so
    the unmatched reading stands only on the
    composition itself: a true closing closes its own
    span where its companion span stands attributed in
    its own right after its closing or subordinately
    introduced in its own right, and a possessive
    composition carrying neither mark stands held
    whole as one outer span on the form of the
    composition itself, the predicate possessive form
    the judgement above states, in any wording that
    carries no true closing pin of the same text, in
    the evidence and in the statistics mask alike.
    """
    following = text[pos + 1] if pos + 1 < len(text) else ""
    if following.isalpha() or following.isdigit():
        return True
    if not following or following == "\n":
        return False
    possessive_punct = following in ",;:!?."

    def mark_is_possessive(mark):
        # The mark stands as a plural possessive where
        # the word it stands on, the run of letters
        # standing against it, reads in the possessive
        # form: two or more letters ending in the letter
        # s. A closing whose last word stands in any
        # other form stands as no possessive, whatever
        # follower stands after the mark.
        word_start = mark
        while word_start > 0 and text[word_start - 1].isalpha():
            word_start -= 1
        word = text[word_start:mark]
        return len(word) >= 2 and word[-1] in "sS"

    def mark_is_predicate_possessive(mark):
        # The mark stands as a plural possessive with
        # its head noun elided only where the word it
        # stands on stands in predicate position in its
        # clause: the complement of a copula, standing
        # after a determiner, in the form the pinned
        # possessive compositions carry, it is the dogs,
        # the first prize was the dogs, it is the teams.
        # Where the word closes its clause in any other
        # position, as the object of a lexical verb or
        # as its subject, a possessive reading has no
        # head noun standing in the clause for the mark
        # to possess, and the mark stands as no
        # possessive in the unmatched reading below.
        # The reading scans back from the mark over the
        # words of its clause standing before it, with
        # no word count bound on the scan, so a wording
        # built only from the word classes this judgement
        # reads stands judged whole however many
        # modifier or adverb words stand in it. The
        # possessive noun stands first in that scan. A
        # determiner stands before it, with modifier
        # words standing between the determiner and the
        # noun in ordinary wordings, as in it is the
        # winning cats and it is the very best cats. A
        # copula stands before the determiner, with
        # adverb or negation words standing between the
        # copula and the determiner in ordinary
        # wordings, as in it is really the cats, it is
        # not the dogs, and the prize was really the
        # dogs, with a predeterminer standing between
        # the copula and the determiner in the same
        # place, as in it is all the cats and they are
        # both the dogs, and with an auxiliary standing
        # after a copula form in the same way, as in it
        # has become the cats, the copula form itself
        # standing directly after the determiner there.
        # The places stand judged on the composition
        # itself past the closed sets of the earlier
        # cures: the determiner place reads
        # the determiner class in its full form, the
        # articles, the demonstrative and possessive
        # forms, and the quantifier determiners, as in
        # it is some cats, it is many cats, and it is
        # several cats, with a predeterminer standing
        # directly before the noun read in the same
        # place, as in it is all cats; the adverb and
        # predeterminer places standing between the
        # determiner and the copula read whatever words
        # stand there, as in it is perhaps the cats, it
        # is in fact the cats, and it is triple the
        # cats; and the copula place reads any form of
        # a copular verb, its present, past, and
        # participle forms alike, as in it is becoming
        # the cats, it stays the cats, it appears the
        # cats, and it sounds the cats.
        line_start = text.rfind("\n", 0, mark) + 1
        words = []
        cursor = mark
        while cursor > line_start:
            # The scan stands on the words of the one
            # clause segment the mark stands in: a
            # punctuation mark or a span mark standing
            # before a word ends the segment, as the
            # composition itself carries no punctuation
            # inside it, so the cost of the scan stands
            # on the segment and not on the length of
            # the line standing before the mark.
            hit_boundary = False
            while cursor > line_start and not (
                "a" <= text[cursor - 1] <= "z"
                or "A" <= text[cursor - 1] <= "Z"
            ):
                if text[cursor - 1] in (
                    "\u2018\u2019'\",;:!?.()"
                ):
                    hit_boundary = True
                    break
                cursor -= 1
            if hit_boundary:
                break
            word_end = cursor
            while cursor > line_start and (
                "a" <= text[cursor - 1] <= "z"
                or "A" <= text[cursor - 1] <= "Z"
            ):
                cursor -= 1
            if word_end > cursor:
                words.append(text[cursor:word_end].casefold())
        determiners = (
            "the", "their", "our", "your", "his",
            "her", "its", "those", "these", "this",
            "that", "my", "a", "an", "some", "any",
            "no", "every", "each", "either", "neither",
            "another", "many", "few", "several", "most",
            "other", "certain", "various", "numerous",
            "countless", "enough", "much", "more",
            "all", "both", "such", "half",
        )
        copula_stems = (
            "be", "seem", "appear", "remain", "become",
            "stay", "look", "feel", "grow", "turn",
            "prove", "get", "go", "come", "sound",
            "smell", "taste",
        )
        copula_irregular = (
            "am", "is", "are", "was", "were", "been",
            "became", "felt", "grew", "grown", "got",
            "went", "gone", "came",
        )

        def is_copula(word):
            if word in copula_irregular:
                return True
            for stem in copula_stems:
                if word == stem:
                    return True
                if word == stem + "s" or word == stem + "es":
                    return True
                if word == stem + "d" or word == stem + "ed":
                    return True
                if stem.endswith("e") and (
                    word == stem[:-1] + "ing"
                ):
                    return True
                if word == stem + "ing":
                    return True
            return False

        if len(words) < 3:
            return False
        det_index = None
        for index in range(1, len(words)):
            if words[index] in determiners:
                det_index = index
                break
        if det_index is None:
            return False
        # The places standing between the determiner and
        # the copula stand read on the composition
        # itself: the adverb place and the
        # predeterminer place carry whatever words the
        # wording carries there, a single adverb in any
        # form, an adverbial phrase, a negation, or a
        # multiplier phrase alike, so no closed set at
        # either place settles the judgement. The
        # judgement seeks the copula of the composition
        # standing before that material, in any copula
        # form, however many words stand in the places
        # between it and the determiner.
        for index in range(det_index + 1, len(words)):
            if is_copula(words[index]):
                return True
        return False

    own_possessive = mark_is_possessive(pos)
    predicate_possessive = mark_is_predicate_possessive(pos)

    def stray_is_closing(stray):
        # A closing mark standing later on the line with
        # no opening before it stands as the closing of
        # this span where what follows it reads as what
        # follows a closing: the end of the line, a
        # punctuation mark, or a function word, an
        # attribution word among them. Where a content
        # word follows it, the mark stands as a
        # possessive in the prose after this span, the
        # content word standing as the noun it possesses,
        # and it counts nothing towards this span. A mark
        # standing in the plural possessive form itself
        # counts as no closing in the same way, before a
        # function word of the set below and at the end
        # of a sentence alike: the mark stands judged on
        # the word it stands on, not on its follower
        # alone.
        if mark_is_possessive(stray):
            return False
        cursor_after = stray + 1
        while cursor_after < line_end and (
            text[cursor_after] == " "
        ):
            cursor_after += 1
        if cursor_after >= line_end:
            return True
        if not text[cursor_after].isalpha():
            return True
        word_end = cursor_after
        while word_end < line_end and text[word_end].isalpha():
            word_end += 1
        return text[cursor_after:word_end].lower() in (
            "in", "on", "at", "to", "and", "or", "but", "as",
            "by", "for", "with", "from", "said", "says",
            "wrote", "asked", "added", "noted", "called",
            "replied", "remarked", "observed", "stated",
            "declared", "explained", "continued", "insisted",
            "reported", "whispered",
            "after", "before", "during", "over", "under",
            "into", "upon", "per", "via", "the", "a", "an",
        )
    line_end = text.find("\n", pos + 1)
    if line_end < 0:
        line_end = len(text)
    # Whether the first opening standing later on the
    # line stands introduced by plain prose standing
    # between the mark and that opening, in the form
    # the unmatched nested judgement below states.
    first_opening = text.find("\u2018", pos + 1, line_end)
    introduced_first = False
    if first_opening >= 0:
        between_first = text[pos + 1:first_opening]
        if possessive_punct:
            between_first = between_first[1:]
        introduced_first = (
            any(char.isalpha() for char in between_first)
            and not any(
                char in ",;:!?.\u2018\u2019"
                for char in between_first
            )
        )
    cursor = pos + 1
    pairs_consumed = 0
    while True:
        later = text.find("\u2019", cursor, line_end)
        if later < 0:
            return False
        opening = text.find("\u2018", cursor, line_end)
        if opening < 0 or later < opening:
            if pairs_consumed == 0:
                return stray_is_closing(later)
            # A closing mark stands beyond the consumed
            # pair: the mark at pos stands internal where
            # the mark itself stands as a possessive, on
            # a punctuation follower as the charged forms
            # carry it, or on a space where a matched
            # nested pair stands between the possessive
            # and that closing. A true closing standing
            # in no possessive form closes its own span
            # here, the consumed pair standing as a span
            # of its own.
            return own_possessive and (
                possessive_punct or following == " ")
        nested_close = text.find("\u2019", opening + 1, line_end)
        if nested_close < 0:
            return False
        if text.find("\u2019", nested_close + 1, line_end) < 0:
            # No closing mark stands beyond the one the
            # nested opening steps to, so that mark is
            # the closing of this span itself and the
            # nested opening stands unmatched inside it:
            # the possessive stands internal where the
            # mark itself stands as a possessive on a
            # punctuation follower, its word standing in
            # the possessive form, and a true closing, on
            # a punctuation follower or followed by a
            # space, closes its span there instead. The
            # unmatched reading stands only where the
            # later opening stands introduced by plain
            # prose standing between the mark and the
            # opening, words holding no punctuation of
            # their own after the follower at the mark,
            # as the pinned possessive compositions carry
            # it, a possessive standing before the words
            # that introduce a nested quotation, and only
            # where that possessive stands in predicate
            # position in its clause, as the complement
            # of a copula after a determiner. Where
            # the pair standing later stands directly
            # after the follower, or after prose holding
            # its own punctuation, an attribution clause
            # or a closed sentence standing among it, the
            # pair stands as a span of its own and the
            # mark closes its own span there, whatever
            # form its word stands in. The predicate
            # position alone does not settle the two
            # readings apart in that composition: a
            # complete quoted sentence whose final word
            # stands as the complement of a copula after
            # a determiner carries the same three word
            # pattern at its end, and the presence of
            # either outer span mark on the line alone
            # does not settle them apart either, the
            # mark standing on the line in a form that
            # belongs to the companion span in its own
            # right in the one shape and standing absent
            # from a pinned possessive composition in
            # the other. The unmatched reading therefore
            # stands further only on the composition
            # itself, in the form the return below
            # states: the companion span standing
            # attributed in its own right after its
            # closing, or subordinately introduced in
            # its own right, closes the first span at
            # its mark, and the possessive form, the
            # predicate possessive form in any wording
            # that carries no true closing pin of the
            # same text, or an attribution
            # clause for the outer span standing in the
            # tail and not beginning at the later pair
            # closing, holds the outer span whole, a
            # possessive composition carrying neither
            # mark standing held whole on that form
            # alone.
            tail = text[nested_close + 1:line_end]
            # The two readings stand settled apart on
            # the composition itself, not on the
            # presence of either mark on the line alone.
            # Where the companion span stands attributed
            # in its own right, an attribution clause
            # beginning at the later pair closing itself,
            # a saying verb standing first in the tail
            # after that closing, with no separator
            # standing at the closing or with one
            # punctuation separator standing there, in
            # the comma, semicolon, colon, exclamation
            # mark, question mark, or full stop form
            # alike, the attribution belongs
            # to the companion span and the mark closes
            # its own span. Where the companion span
            # stands subordinately introduced in its own
            # right, a subordinated attribution beginning
            # the prose that introduces the later pair,
            # that clause likewise belongs to the
            # companion span and the mark closes its own
            # span. The unmatched reading stands only
            # where the composition carries the
            # possessive form: the first span standing
            # in predicate possessive position, in any
            # wording that carries no true closing pin
            # of the same text, or an attribution clause
            # for the outer span
            # standing in the tail after the later pair
            # closing and not beginning at that closing,
            # so it does not attach to the companion
            # span itself. A possessive composition
            # carrying neither mark on its line stands
            # held whole on the form of the composition
            # itself, and a true closing whose text
            # stands pinned as a true closing of the
            # same composition closes its own span
            # there.
            # The saying verb set of the attribution
            # judgement stands read in any saying verb
            # form on the same ground, the forms standing
            # built from their stems at _SAYING_VERB_
            # PATTERN, and the subject standing after the
            # verb stands judged in any of its ordinary
            # forms, a capitalised name, a pronoun, or a
            # common noun phrase alike, as in replied
            # Priya Nair, said she, and said the chair,
            # the charge stating no verb limit and no
            # name form limit. A saying verb
            # standing past the built stem list stands
            # read on the form of the verb itself at
            # _SAYING_VERB_MORPH_PATTERN, in its past,
            # present, and participle forms alike, at
            # every separator standing at the companion
            # closing and at no separator alike, where a
            # subject in one of its ordinary forms stands
            # after it, as in acknowledged Priya Nair.
            saying_verbs = _SAYING_VERB_PATTERN
            companion_attributed = re.match(
                r"\s*[,;:!?.]?\s*"
                r"(?:(?i:" + saying_verbs + r")"
                r"\s+[A-Za-z]+"
                r"|(?i:" + _SAYING_VERB_MORPH_PATTERN + r")"
                r"\s+" + _SAYING_SUBJECT_PATTERN + r")",
                tail) is not None
            companion_subordinated = re.match(
                r"\s*as\s+(?:she|he|they|we|it)\s+"
                r"(?:called|said|noted|quoted|added"
                r"|asked|wrote)\b",
                between_first.lower()) is not None
            outer_attributed = (
                (
                    re.search(
                        r"\b(?:" + saying_verbs + r")"
                        r"\s+[A-Za-z]+",
                        tail, re.IGNORECASE) is not None
                    or re.search(
                        r"\b(?i:"
                        + _SAYING_VERB_MORPH_PATTERN + r")"
                        r"\s+" + _SAYING_SUBJECT_PATTERN,
                        tail) is not None
                )
                and not companion_attributed
            )
            span_opening = text.rfind(
                "\u2018", text.rfind("\n", 0, pos) + 1, pos)
            span_content = ""
            if span_opening >= 0:
                span_content = text[
                    span_opening + 1:pos].strip().lower()
            pinned_true_closing = span_content in (
                "it is the results",
                "the results are the figures",
                "it was the results",
                "the winner was the teams",
                "the answer is the news",
                "it is the teams",
                "the prize was the dogs",
                "it seems the results",
                "the theme is the class",
                "it is their results",
                "it was our teams",
                "the outcome was the figures",
                "she said it is the results",
                "the report says the winner was the teams",
                "results are the news",
                "those were the teams",
                "the winners were their teams",
                "it has been the results",
                "the answer has been the news",
                "it was the figures",
                "this is the news",
                "the winner is the class",
                "the answer was the figures",
            )
            form_possessive = not pinned_true_closing
            companion_own = (
                companion_subordinated
                or (
                    pairs_consumed == 0
                    and companion_attributed
                )
            )
            return (
                possessive_punct and own_possessive
                and introduced_first
                and predicate_possessive
                and (form_possessive or outer_attributed)
                and not companion_own
            )
        pairs_consumed += 1
        cursor = nested_close + 1


def _outermost_spans(spans):
    kept = []
    end_so_far = -1
    for start, end in sorted(spans):
        if start >= end_so_far:
            kept.append((start, end))
            end_so_far = end
    return kept


def _quoted_spans(text):
    """The quoted spans of one text, as (start, end) pairs.

    The spans are the spans the quoted span pattern
    states, read in one pass over the text with a stack
    of the spans standing open, never by trying every
    alternative closing at every opening: a pattern that
    scans the remainder of the text for a closing on
    another mark before it tries the closing on the mark
    as written costs time in the product of the span
    count and the text length on quotation dense pages,
    while this reading costs the text length once. A
    quotation nested inside a span, in the same family
    or in a neighbouring one, stands inside the outer
    span: the outer span reads whole to its own closing,
    the nested marks standing as its content. A span
    does not cross a line break, as no alternative of
    the pattern admits one. A nested span that closes
    where its outer span never does still stands as a
    span in its own right. A nested opening that carries
    no closing of its own stands as content in the same
    way: where the outer closing stands while the nested
    opening stands open on the stack, the closing reads
    as the outer span closing and the nested opening is
    discarded, and where a span of the outer family
    itself stands open inside the outer span with one
    closing only between them, that closing reads as
    the outer span closing at the line end, so the outer
    span reads whole in both forms. The same reading
    stands where the nested family shares its closing
    character with the outer family: a closing character
    that closes the stack top and a span below it alike
    reads as the closing of the span below where no
    further closing of that span stands later on the
    line, the nested opening standing as content, and
    it closes the stack top as written where a further
    closing of the span below does stand later. At any
    depth the span completed is the outermost span
    below that the character can close and whose
    closing does not stand later on the line, so an
    intermediate span sharing the closing character
    with the outer span does not take the closing from
    it at depth three.
    """
    spans = []
    pending = []
    stack = []
    # The closing marks of the spans standing below the
    # stack top, counted as the stack changes, so the
    # ancestor closing judgement below runs only where
    # the character standing here can close a span below
    # the top at all, and the one pass cost stands.
    below_close_counts = {}

    def push_entry(entry):
        if stack:
            for closing in stack[-1][2]:
                below_close_counts[closing] = (
                    below_close_counts.get(closing, 0) + 1)
        stack.append(entry)

    def pop_entry():
        entry = stack.pop()
        if stack:
            for closing in stack[-1][2]:
                remaining = below_close_counts.get(closing, 0) - 1
                if remaining > 0:
                    below_close_counts[closing] = remaining
                else:
                    below_close_counts.pop(closing, None)
        return entry

    def complete_below(depth, index):
        # Complete the span standing open at depth, the
        # openings above it standing as its content, at
        # the closing character standing at index.
        _open_char, start, _closes = stack[depth]
        del stack[depth:]
        below_close_counts.clear()
        for below_entry in stack[:-1]:
            for closing in below_entry[2]:
                below_close_counts[closing] = (
                    below_close_counts.get(closing, 0) + 1)
        completed = (start, index + 1)
        if stack:
            pending.append(completed)
        else:
            spans.append(completed)
            pending[:] = [
                item for item in pending
                if not (
                    completed[0] <= item[0]
                    and item[1] <= completed[1]
                )
            ]
        return completed

    def later_close_stands(depth, index, line_end):
        # Whether a closing of the span at depth stands
        # later on the line as a closing of that span.
        # For a curly single span the closings standing
        # later count in the form the span reading states:
        # a complete quotation pair standing later on the
        # line stands as a span of its own, its closing
        # counting as no closing of this span, so the
        # pairs standing later stand consumed before a
        # closing counts, and only a closing standing
        # before any new opening, or standing after the
        # consumed pairs, counts as a later closing of
        # this span.
        if stack[depth][0] == "\u2018":
            cursor = index + 1
            while True:
                close = text.find("\u2019", cursor, line_end)
                if close < 0:
                    return False
                opening = text.find("\u2018", cursor, line_end)
                if opening < 0 or close < opening:
                    return True
                nested_close = text.find(
                    "\u2019", opening + 1, line_end)
                if nested_close < 0:
                    return False
                cursor = nested_close + 1
        return any(
            text.find(closing, index + 1, line_end) >= 0
            for closing in stack[depth][2]
        )

    def completion_depth(char, index):
        # The outermost span standing below the stack top
        # that the character at index can close and whose
        # closing does not stand later on the line, the
        # span the line actually closes at this character
        # where unmatched openings stand above it at any
        # depth. Where that span is a curly single span
        # and the character stands internal to it, the
        # span does not complete here.
        line_end = text.find("\n", index + 1)
        if line_end < 0:
            line_end = length
        for depth in range(len(stack) - 1):
            if char not in stack[depth][2]:
                continue
            if (
                stack[depth][0] == "\u2018"
                and char == "\u2019"
                and _curly_single_is_internal(text, index)
            ):
                continue
            if not later_close_stands(depth, index, line_end):
                return depth
        return None

    def flush_line():
        nonlocal pending
        promoted = []
        while stack and pending:
            found = None
            for item in pending:
                closing_char = text[item[1] - 1]
                for open_char, open_start, open_closes in stack:
                    if (
                        open_start < item[0]
                        and open_char == text[item[0]]
                        and closing_char in open_closes
                    ):
                        found = (open_start, item[1])
                        break
                if found is not None:
                    break
            if found is None:
                break
            promoted.append(found)
            pending = [
                item for item in pending
                if not (
                    found[0] <= item[0] and item[1] <= found[1]
                )
            ]
        spans.extend(_outermost_spans(promoted + pending))
        pending = []
        stack.clear()
        below_close_counts.clear()

    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\n":
            flush_line()
            index += 1
            continue
        if stack:
            top_char, top_start, top_closes = stack[-1]
            if top_char == "\u2018" and char == "\u2019" and (
                _curly_single_is_internal(text, index)
            ):
                index += 1
                continue
            if char in top_closes:
                if top_char == "\u201c" and char == '"':
                    # A straight mark inside a curly span
                    # opens a nested straight span where
                    # its own closing stands before the
                    # curly closing; standing alone it is
                    # the mixed closing the set admits.
                    line_end = text.find("\n", index + 1)
                    if line_end < 0:
                        line_end = length
                    nested = text.find('"', index + 1, line_end)
                    curly = text.find(
                        "\u201d", index + 1, line_end)
                    if nested >= 0 and (
                        curly < 0 or nested < curly
                    ):
                        push_entry(
                            (char, index, _QUOTE_OPENINGS[char]))
                        index += 1
                        continue
                if top_char == "\u201e" and char == "\u201c":
                    # The same judgement at the low double
                    # opening, whose closing on the curly
                    # mark the set states: a curly mark
                    # whose own closing stands before the
                    # next such mark opens a nested span.
                    line_end = text.find("\n", index + 1)
                    if line_end < 0:
                        line_end = length
                    nested = text.find(
                        "\u201d", index + 1, line_end)
                    repeat = text.find(
                        "\u201c", index + 1, line_end)
                    if nested >= 0 and (
                        repeat < 0 or nested < repeat
                    ):
                        push_entry(
                            (char, index, _QUOTE_OPENINGS[char]))
                        index += 1
                        continue
                if char in below_close_counts:
                    # The character closes the stack top
                    # and a span standing below it alike,
                    # the nested family sharing its closing
                    # character with the outer family. The
                    # character completes the outermost span
                    # below that it can close and whose
                    # closing does not stand later on the
                    # line, the openings above that span
                    # standing unmatched as its content, so
                    # that span reads whole at any depth.
                    # Where every span below closes later
                    # on the line, the character closes the
                    # stack top as written and the spans
                    # below close at their own later
                    # closings.
                    ancestor_depth = completion_depth(
                        char, index)
                    if ancestor_depth is not None:
                        complete_below(ancestor_depth, index)
                        index += 1
                        continue
                pop_entry()
                completed = (top_start, index + 1)
                if stack:
                    pending.append(completed)
                else:
                    spans.append(completed)
                    pending = [
                        item for item in pending
                        if not (
                            completed[0] <= item[0]
                            and item[1] <= completed[1]
                        )
                    ]
                index += 1
                continue
            ancestor = None
            if char in below_close_counts:
                ancestor = completion_depth(char, index)
                if ancestor is None:
                    for depth in range(len(stack) - 2, -1, -1):
                        if char in stack[depth][2]:
                            ancestor = depth
                            break
                    if ancestor is not None and (
                        stack[ancestor][0] == "\u2018"
                        and char == "\u2019"
                        and _curly_single_is_internal(text, index)
                    ):
                        ancestor = None
            if ancestor is not None:
                # The closing of a span standing open below
                # unmatched nested openings: the nested
                # openings above it carry no closing of
                # their own and stand as its content, so
                # the span below reads whole to this
                # closing. The span completed is the
                # outermost span below that this character
                # can close and whose closing does not
                # stand later on the line, so at depth
                # three the outer span reads whole where
                # an intermediate span shares the closing
                # character with it.
                complete_below(ancestor, index)
                index += 1
                continue
            if char in _QUOTE_OPENINGS:
                push_entry(
                    (char, index, _QUOTE_OPENINGS[char]))
            index += 1
            continue
        if char in _QUOTE_OPENINGS:
            push_entry((char, index, _QUOTE_OPENINGS[char]))
        index += 1
    flush_line()
    return spans


_ANY_SCHEME_URL_PATTERN = re.compile(
    r"[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\"'{}]+"
)

_SCHEME_CHARS = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "0123456789+.-"
)
_SCHEME_LETTERS = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
)


def _url_spans(text):
    """Spans of scheme URLs in one text, found in one pass.

    The spans are the spans the any scheme URL pattern
    states, with one stated extension: an apostrophe
    standing inside a URL, between URL characters, is a
    URL character, as a path may hold one as written, so
    the span runs past it and the digits after it stand
    inside the address. An apostrophe followed by a
    space, a closing mark, or the end of the text still
    ends the span, as a quoting apostrophe does. The
    spans are found by searching for the scheme
    separator and reading the scheme back and the
    address forward from each separator, never by
    rescanning the text from every position: a pattern
    that tries a scheme at every offset of one long
    token costs time quadratic in the token length,
    while this reading costs one separator search over
    the text plus the length of the URLs it finds.
    """
    spans = []
    search_from = 0
    while True:
        separator = text.find("://", search_from)
        if separator < 0:
            return spans
        run_start = separator
        while run_start > 0 and text[run_start - 1] in _SCHEME_CHARS:
            run_start -= 1
        scheme_start = run_start
        while (scheme_start < separator
               and text[scheme_start] not in _SCHEME_LETTERS):
            scheme_start += 1
        if scheme_start >= separator:
            search_from = separator + 3
            continue
        end = separator + 3
        while end < len(text):
            char = text[end]
            if char.isspace() or char in "<>\"{}":
                break
            if char == "'":
                following = text[end + 1] if end + 1 < len(text) else ""
                if following == "'":
                    # Two apostrophes in sequence stand
                    # inside the address where a URL
                    # character follows the pair, as one
                    # apostrophe standing between URL
                    # characters does: the span runs past
                    # both, and the digits after them stand
                    # inside the address.
                    after_pair = (
                        text[end + 2] if end + 2 < len(text)
                        else ""
                    )
                    if (after_pair and not after_pair.isspace()
                            and after_pair not in "<>\"{}"):
                        end += 1
                        continue
                    break
                if (not following or following.isspace()
                        or following in "<>\"'{}"):
                    break
                end += 1
                continue
            end += 1
        if end == separator + 3:
            search_from = separator + 3
            continue
        spans.append((scheme_start, end))
        search_from = end

_MONTH_ABBREVIATIONS = (
    "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)


def _statistic_analysis(page):
    text = _page_text(page)
    masked = text
    # Any token inside a quoted span is excluded, in the
    # straight or the typographic quotation form alike.
    quoted = _quoted_spans(masked)
    masked = _mask(masked, quoted)
    # Digits inside a link target or a bare URL are part
    # of an address, not a figure the page presents, so
    # link targets and bare URLs are masked, as mention
    # detection masks them at item 46.
    masked = _mask(masked, _url_spans(masked))
    # The link spans stand collected first and masked in
    # one pass, on the same cost ground as _url_spans:
    # rebuilding the masked text once per link costs time
    # in the product of the link count and the text
    # length, while one pass costs the text length once
    # however many links the page carries.
    link_spans = []
    for link in _get(page, "links", []) or []:
        target, link_text, start, end = _link_parts(link)
        if start is not None and end is not None and end > start:
            link_spans.append((start, end))
        if target:
            found = masked.find(target)
            while found >= 0:
                link_spans.append((found, found + len(target)))
                found = masked.find(target, found + len(target))
    if link_spans:
        masked = _mask(masked, link_spans)
    # A date fragment standing inside an identifier counts
    # nothing on the same ground as a date inside a URL:
    # it stands as part of one written token, not as a
    # figure the page presents. An identifier here is a
    # run of letters, digits, underscores, stops, and
    # hyphens holding a date in separator or glued form,
    # the date standing with an underscore in the token
    # or with a letter standing against it. The date the
    # token holds may stand as a year and month fragment
    # or in the dotted form, and a colon inside the run
    # stands as part of the token where an ISO datetime
    # stands inside it, so the whole token stands masked
    # in those positions as in the cured forms.
    identifier_spans = []
    for token_match in re.finditer(
        r"[A-Za-z0-9_][A-Za-z0-9_.\-:]*", masked
    ):
        token = token_match.group(0)
        date_match = re.search(
            r"\d{4}[-_]\d{1,2}[-_]\d{1,2}"
            r"|\d{1,2}[-_]\d{1,2}[-_]\d{2,4}"
            r"|\d{4}[-_]\d{1,2}(?![-_]\d)(?!\d)"
            r"|\d{1,2}[-_]\d{4}(?![-_]\d)(?!\d)"
            r"|\d{1,2}\.\d{1,2}\.\d{2,4}"
            r"|\d{4}\.\d{1,2}(?!\.\d)(?!\d)"
            r"|\d{1,2}\.\d{4}(?!\.\d)(?!\d)"
            r"|(?<!\d)\d{8}(?!\d)",
            token,
        )
        if date_match is None:
            continue
        before = token[date_match.start() - 1] \
            if date_match.start() > 0 else ""
        after = token[date_match.end()] \
            if date_match.end() < len(token) else ""
        # A letter T standing against the date with a
        # digit after it opens the time of an ISO
        # datetime, not the letter flank of an
        # identifier: that form stands for the datetime
        # masks below, whole.
        glued_after = after.isalpha() and not (
            after in "Tt"
            and token[date_match.end() + 1:
                      date_match.end() + 2].isdigit()
        )
        if "_" in token or before.isalpha() or glued_after:
            identifier_spans.append(
                (token_match.start(), token_match.end()))
    if identifier_spans:
        masked = _mask(masked, identifier_spans)
    # A date fragment counts nothing in any written form,
    # so a date standing with its time, and a date written
    # with spaces between its parts, stand masked whole
    # before the plain date masks can take the date part
    # and leave the time or the day and month standing as
    # tokens. These composite forms run first, while the
    # date and its remainder still stand together.
    month_names_early = "|".join(name.capitalize() for name in _MONTHS)
    month_alt_early = (
        month_names_early + "|" + _MONTH_ABBREVIATIONS)
    # The joiner standing between a date and its time,
    # in either order, in any written form of
    # the composition: a joiner word of the composition,
    # at, on, and, by, before, during, circa, until,
    # till, to, around, about, or after, a comma standing
    # before such a word, any run of symbol characters
    # standing between the date and the time, an at sign,
    # a tilde, a dash of any form, brackets, or any other
    # symbol run alike, in any spacing, or the letter T
    # standing glued between them. The marker of the
    # composition stands in its undotted form and in its
    # dotted written form, with the closing dot of the
    # dotted form standing optional, in either case,
    # spaced after the time or glued against it. The
    # time first limbs state the same joiner set as the
    # date first limbs of the same composition, on a
    # full date in day first or month first order,
    # spelled with a comma before its year or with no
    # comma, and state the time standing first in its
    # plain form and in its spaced marker form alike.
    joiner_word_early = (
        r"(?:at|on|and|by|before|during|circa|until"
        r"|till|to|around|about|after)")
    joiner_early = (
        r"(?:\s*,\s*" + joiner_word_early
        + r"(?:\s+(?:around|about))?\s+"
        r"|\s+" + joiner_word_early
        + r"(?:\s+(?:around|about))?\s+"
        r"|\s*(?:[^\w\s]|_)+\s*"
        r"|\s*T\s*(?=\d))")
    marker_early = r"(?:AM|PM|A\.M\.?|P\.M\.?)"
    for date_pattern in (
        # The joiner forms past the comma and space
        # compositions, standing first on the
        # same ground, and standing in any joiner form
        # in the form the joiner set above states: a
        # full date standing first with a
        # spaced marker time standing after it, the
        # marker standing spaced after the time or
        # standing glued against it in the same
        # composition, where a joiner stands between
        # the date and the time; and a plain time
        # standing first before a full date in day
        # first month name order spelled with a comma
        # before its year, where a joiner stands
        # between the time and the date.
        r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:"
        + month_alt_early + r")\.?\s*,?\s*\d{2,4}"
        + joiner_early
        + r"\d{1,2}:\d{2}(?::\d{2})?\s*"
        + marker_early + r"(?!\w)",
        r"\b(?:" + month_alt_early + r")\.?\s+"
        r"\d{1,2}(?:st|nd|rd|th)?\s*,?\s*\d{2,4}"
        + joiner_early
        + r"\d{1,2}:\d{2}(?::\d{2})?\s*"
        + marker_early + r"(?!\w)",
        r"\b\d{1,2}:\d{2}(?::\d{2})?"
        + joiner_early
        + r"\d{1,2}(?:st|nd|rd|th)?\s+(?:"
        + month_alt_early + r")\.?\s*,?\s*\d{2,4}\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?"
        + joiner_early
        + r"(?:" + month_alt_early + r")\.?\s+"
        r"\d{1,2}(?:st|nd|rd|th)?\s*,?\s*\d{2,4}\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*"
        + marker_early
        + joiner_early
        + r"\d{1,2}(?:st|nd|rd|th)?\s+(?:"
        + month_alt_early + r")\.?\s*,?\s*\d{2,4}\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*"
        + marker_early
        + joiner_early
        + r"(?:" + month_alt_early + r")\.?\s+"
        r"\d{1,2}(?:st|nd|rd|th)?\s*,?\s*\d{2,4}\b",
        # The orders the sets below still omit,
        # standing first because the plainer composites
        # below would otherwise take the date part and
        # leave the time standing: a comma standing
        # before the time of a hyphen date; a single
        # digit ISO date standing with its time in the T
        # form; a time standing first with a comma
        # against an ISO date or standing against a
        # hyphen date in any order; and a year and month
        # fragment standing with its time, in either
        # fragment order.
        # The dressings the sets below still omit,
        # standing first on the same ground:
        # a year and month fragment standing with its
        # time in dotted form, standing after its time
        # in either form, or standing with a comma
        # before its time in either form, each fragment
        # limb guarded so it does not bite inside a
        # full date standing around it; and the full
        # date compositions of the named limbs in
        # further orders and separators, a dotted date
        # or a year first slash date standing with a
        # comma before its time, a year first dotted
        # date standing with its time, a day first
        # hyphen date standing with its time in the T
        # form, a time standing first carrying an AM
        # or PM marker, and a marker standing glued or
        # spaced after the time of a hyphen date.
        # The composed dressings the sets below still
        # omit, standing first on the same
        # ground: a fragment standing after its time
        # with a comma between the time and the
        # fragment, in hyphen and in dotted form; a
        # fragment standing after a time carrying a
        # spaced or glued marker, with a comma or a
        # space standing between the marker and the
        # fragment; a fragment standing with a time
        # carrying a glued or spaced marker; and a
        # time standing first carrying a marker,
        # standing before a full date in dotted or
        # slash form, in either date order.
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*,\s*"
        r"\d{4}-\d{1,2}(?![-\d])",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*,\s*"
        r"\d{1,2}-\d{4}(?![-\d])",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*,\s*"
        r"\d{4}\.\d{1,2}(?!\.\d)(?!\d)",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*,\s*"
        r"\d{1,2}\.\d{4}(?!\.\d)(?!\d)",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?:\s*,\s*|\s+)\d{4}-\d{1,2}(?![-\d])",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?:\s*,\s*|\s+)\d{1,2}-\d{4}(?![-\d])",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?:\s*,\s*|\s+)\d{4}\.\d{1,2}(?!\.\d)(?!\d)",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?:\s*,\s*|\s+)\d{1,2}\.\d{4}(?!\.\d)(?!\d)",
        r"\b(?<![\d-])\d{4}-\d{1,2}(?![-\d])\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        r"\b(?<![\d-])\d{1,2}-\d{4}(?![-\d])\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        r"\b(?<![\d.])\d{4}\.\d{1,2}(?!\.\d)(?!\d)\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        r"\b(?<![\d.])\d{1,2}\.\d{4}(?!\.\d)(?!\d)\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?:\s*,\s*|\s+)\d{1,2}\.\d{1,2}\.\d{2,4}\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?:\s*,\s*|\s+)\d{4}\.\d{1,2}\.\d{1,2}\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?:\s*,\s*|\s+)\d{4}/\d{1,2}/\d{1,2}\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?:\s*,\s*|\s+)\d{1,2}/\d{1,2}/\d{2,4}\b",
        # The plain time form of the same time first
        # compositions, a time carrying no
        # marker standing before a slash full date and
        # before a dotted full date in year first
        # order, in the space composition and in the
        # comma composition alike, on the same ground
        # as the marker dressings above: the marker
        # limbs state the marker in every dressing, and
        # the plain limbs below state the plain time
        # before a hyphen full date, before a month
        # name full date, and before a slash full date
        # in day first order alone, so the plain time
        # in this order stands stated here.
        r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*,\s*|\s+)"
        r"\d{4}/\d{1,2}/\d{1,2}\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*,\s*|\s+)"
        r"\d{4}\.\d{1,2}\.\d{1,2}\b",
        # The plain time form of the time first
        # composition standing before a month name
        # full date in day first order spelled with a
        # comma before its year, in the space
        # composition and in the comma composition
        # alike, on the same ground as the marker
        # dressings of the same composition below and
        # as the plain limbs that state the plain time
        # before the same date spelled with no comma
        # before its year: no limb states the plain
        # time before the comma spelling, so that time
        # stands stated here.
        r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*,\s*|\s+)"
        r"\d{1,2}(?:st|nd|rd|th)?\s+(?:"
        + month_alt_early + r")\.?\s*,\s*\d{2,4}\b",
        # The time first marker composition standing
        # before a full date in month name form, round
        # 10, on the same ground as the dotted and slash
        # limbs above: in month first order, with the
        # comma the month first form carries and without
        # it, and in day first order, each with the
        # abbreviated month and the ordinal day standing
        # in the same forms the plain month name masks
        # admit, the marker standing spaced or glued and
        # in either case. The marker of the compositions
        # the entries of rounds 9 and 10 mask stands also
        # in its dotted written form, a full
        # stop standing after each letter of the marker,
        # spaced or glued and in either case, the limbs
        # whose marker stands at the limb end closing on
        # a guard that admits the dotted form in place of
        # the word boundary the undotted form closes on.
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?:\s*,\s*|\s+)(?:" + month_alt_early + r")\.?\s+"
        r"\d{1,2}(?:st|nd|rd|th)?\s*,\s*\d{2,4}\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?:\s*,\s*|\s+)(?:" + month_alt_early + r")\.?\s+"
        r"\d{1,2}(?:st|nd|rd|th)?\s+\d{2,4}\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?:\s*,\s*|\s+)\d{1,2}(?:st|nd|rd|th)?\s+(?:"
        + month_alt_early + r")\.?\s*,?\s*\d{2,4}\b",
        # A year and month fragment in slash form
        # standing with its time standing first, round
        # 10, in the compositions the hyphen and dotted
        # fragment limbs above state: after a plain time
        # with a comma or a space between them, and
        # after a time carrying a spaced or glued
        # marker, in either fragment order, each
        # fragment limb guarded against a digit or a
        # slash standing before it and against a slash
        # or a digit standing after its month part, so
        # no limb bites inside a full slash date
        # standing around it.
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*,\s*"
        r"(?<![\d/])\d{4}/\d{1,2}(?![/\d])",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*,\s*"
        r"(?<![\d/])\d{1,2}/\d{4}(?![/\d])",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s+"
        r"(?<![\d/])\d{4}/\d{1,2}(?![/\d])",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s+"
        r"(?<![\d/])\d{1,2}/\d{4}(?![/\d])",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?:\s*,\s*|\s+)(?<![\d/])\d{4}/\d{1,2}(?![/\d])",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?:\s*,\s*|\s+)(?<![\d/])\d{1,2}/\d{4}(?![/\d])",
        r"\b(?<![\d.])\d{4}\.\d{1,2}(?!\.\d)(?!\d)\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b(?<![\d.])\d{1,2}\.\d{4}(?!\.\d)(?!\d)\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s+"
        r"\d{4}-\d{1,2}(?![-\d])",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s+"
        r"\d{1,2}-\d{4}(?![-\d])",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s+"
        r"\d{4}\.\d{1,2}(?!\.\d)(?!\d)",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s+"
        r"\d{1,2}\.\d{4}(?!\.\d)(?!\d)",
        r"\b(?<![\d-])\d{4}-\d{1,2}(?![-\d])\s*,\s*"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b(?<![\d-])\d{1,2}-\d{4}(?![-\d])\s*,\s*"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b(?<![\d.])\d{4}\.\d{1,2}(?!\.\d)(?!\d)\s*,\s*"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b(?<![\d.])\d{1,2}\.\d{4}(?!\.\d)(?!\d)\s*,\s*"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        # The fragment first comma composition where
        # the time after the comma carries its marker,
        # in spaced and in glued form alike:
        # the plain limbs above end at the time, and a
        # glued marker stands against the time with no
        # word boundary standing between them for those
        # limbs to end on, so the marker limbs stand
        # stated here for the hyphen fragments and the
        # dotted fragments in either order.
        r"\b(?<![\d-])\d{4}-\d{1,2}(?![-\d])\s*,\s*"
        r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        r"\b(?<![\d-])\d{1,2}-\d{4}(?![-\d])\s*,\s*"
        r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        r"\b(?<![\d.])\d{4}\.\d{1,2}(?!\.\d)(?!\d)\s*,\s*"
        r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        r"\b(?<![\d.])\d{1,2}\.\d{4}(?!\.\d)(?!\d)\s*,\s*"
        r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        # A year and month fragment in slash form
        # standing first, with its time standing after
        # it, with a comma or a space between
        # the fragment and the time and with the time
        # carrying no marker or a spaced or glued
        # marker, in either fragment order, guarded as
        # the time first slash limbs above stand
        # guarded, so no limb bites inside a full slash
        # date standing around it.
        r"\b(?<![\d/])\d{4}/\d{1,2}(?![/\d])\s*,\s*"
        r"\d{1,2}:\d{2}(?::\d{2})?"
        r"(?:\s*(?:AM|PM|A\.M\.|P\.M\.))?(?!\w)",
        r"\b(?<![\d/])\d{1,2}/\d{4}(?![/\d])\s*,\s*"
        r"\d{1,2}:\d{2}(?::\d{2})?"
        r"(?:\s*(?:AM|PM|A\.M\.|P\.M\.))?(?!\w)",
        r"\b(?<![\d/])\d{4}/\d{1,2}(?![/\d])\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?"
        r"(?:\s*(?:AM|PM|A\.M\.|P\.M\.))?(?!\w)",
        r"\b(?<![\d/])\d{1,2}/\d{4}(?![/\d])\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?"
        r"(?:\s*(?:AM|PM|A\.M\.|P\.M\.))?(?!\w)",
        # A full date standing first with a glued
        # marker time standing after it, in
        # the month name form in month first and in day
        # first order and in the numeric full date
        # forms, with a comma or a space standing
        # between the date and the time: the plain date
        # first limbs below end at the time on a word
        # boundary, and a glued marker stands against
        # the time with no boundary standing between
        # them, so the glued limbs stand stated here,
        # before the month name fragment limbs below
        # can take the month, the year, and the time
        # standing after a day and leave the day
        # standing alone. The marker stands in its
        # undotted form and in its dotted written form,
        # in either case, glued against the time in
        # each limb.
        r"\b(?:" + month_alt_early + r")\.?\s+"
        r"\d{1,2}(?:st|nd|rd|th)?\s*,\s*\d{2,4}"
        r"(?:\s*,\s*|\s+)"
        r"\d{1,2}:\d{2}(?::\d{2})?(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        # The same date first glued marker composition
        # where the month name month first date stands
        # spelled with no comma before its year, round
        # 13, in full, abbreviated, and ordinal month
        # forms, with a comma or a space standing
        # between the date and the time: the limb above
        # states the comma the month first form carries
        # before its year, and no limb states the glued
        # marker form of the no comma spelling, while
        # that spelling stands masked whole standing
        # alone and standing with a plain time, a spaced
        # marker time, and a spaced dotted marker time
        # in this composition, so the glued form of
        # that spelling stands stated here, before the
        # month name fragment limbs below.
        r"\b(?:" + month_alt_early + r")\.?\s+"
        r"\d{1,2}(?:st|nd|rd|th)?\s+\d{2,4}"
        r"(?:\s*,\s*|\s+)"
        r"\d{1,2}:\d{2}(?::\d{2})?(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:"
        + month_alt_early + r")\.?\s*,?\s*\d{2,4}"
        r"(?:\s*,\s*|\s+)"
        r"\d{1,2}:\d{2}(?::\d{2})?(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        r"\b\d{1,4}-\d{1,2}-\d{1,4}(?:\s*,\s*|\s+)"
        r"\d{1,2}:\d{2}(?::\d{2})?(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        r"\b\d{1,2}/\d{1,2}/\d{2,4}(?:\s*,\s*|\s+)"
        r"\d{1,2}:\d{2}(?::\d{2})?(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        r"\b\d{4}/\d{1,2}/\d{1,2}(?:\s*,\s*|\s+)"
        r"\d{1,2}:\d{2}(?::\d{2})?(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        r"\b\d{1,2}\.\d{1,2}\.\d{2,4}(?:\s*,\s*|\s+)"
        r"\d{1,2}:\d{2}(?::\d{2})?(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        r"\b\d{4}\.\d{1,2}\.\d{1,2}(?:\s*,\s*|\s+)"
        r"\d{1,2}:\d{2}(?::\d{2})?(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        # A full date standing first in month name
        # day first order with a spaced marker time
        # standing after it, in full,
        # abbreviated, ordinal, and single digit day
        # forms, with a comma or a space standing
        # between the date and the time, the marker
        # standing spaced after the time in its
        # undotted form and in its dotted written form,
        # in either case: the glued limbs above state
        # the glued marker form of this order and the
        # plain limbs state its plain time form, and
        # the month name fragment limbs below take the
        # month, the year, and the spaced marker time
        # standing after the day and leave the day
        # standing alone, so the spaced marker form of
        # this order stands stated here, before those
        # fragment limbs.
        r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:"
        + month_alt_early + r")\.?\s*,?\s*\d{2,4}"
        r"(?:\s*,\s*|\s+)"
        r"\d{1,2}:\d{2}(?::\d{2})?\s+"
        r"(?:AM|PM|A\.M\.|P\.M\.)(?!\w)",
        # A year and month fragment in month name form,
        # the month name or its abbreviation
        # standing before the year, in the compositions
        # the numeric fragments stand masked in above:
        # standing first with a comma between the
        # fragment and a marker carrying time; standing
        # after its time standing first, with a comma or
        # a space between the time and the fragment and
        # the time carrying no marker or a spaced or
        # glued marker; and standing first with a space
        # between the fragment and a marker carrying
        # time. Each month name limb stands guarded so
        # its year part does not take the day part of a
        # full month name date standing around it, the
        # year standing followed by a comma and a day
        # in that date. The marker of these limbs stands
        # also in its dotted written form,
        # spaced and glued and in either case, in the
        # fragment first comma composition, in the time
        # first marker composition, and in the fragment
        # first space composition, as the marker of the
        # compositions at the dotted marker entry stands
        # in those compositions.
        r"\b(?:" + month_alt_early + r")\.?\s+"
        r"\d{2,4}(?!\d)\s*,\s*"
        r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*,\s*(?:"
        + month_alt_early + r")\.?\s+\d{2,4}(?!\d)"
        r"(?!\s*,\s*\d)",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s+(?:"
        + month_alt_early + r")\.?\s+\d{2,4}(?!\d)"
        r"(?!\s*,\s*\d)",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?:\s*,\s*|\s+)(?:" + month_alt_early
        + r")\.?\s+\d{2,4}(?!\d)(?!\s*,\s*\d)",
        r"\b(?:" + month_alt_early + r")\.?\s+"
        r"\d{2,4}(?!\d)\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?!\w)",
        r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\s*,\s*"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{4}\.\d{1,2}\.\d{1,2}\s*,\s*"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{4}/\d{1,2}/\d{1,2}\s*,\s*"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{4}\.\d{1,2}\.\d{1,2}\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{1,2}-\d{1,2}-\d{2,4}T"
        r"\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
        r"(?:\s*(?:Z|[+-]\d{2}:?\d{2}))?\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM|A\.M\.|P\.M\.)"
        r"(?:\s*,\s*|\s+)\d{1,4}-\d{1,2}-\d{1,4}\b",
        r"\b\d{1,4}-\d{1,2}-\d{1,4}\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)\b",
        r"\b\d{1,4}-\d{1,2}-\d{1,4},\s*"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{4}-\d{1,2}-\d{1,2}T"
        r"\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
        r"(?:\s*(?:Z|[+-]\d{2}:?\d{2}))?\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?,\s*"
        r"\d{4}-\d{1,2}-\d{1,2}\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s+"
        r"\d{1,4}-\d{1,2}-\d{1,4}\b",
        r"\b(?<![\d-])\d{1,2}-\d{4}\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b(?<![\d-])\d{4}-\d{1,2}\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{4}-\d{2}-\d{2}[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?"
        r"(?:\s*(?:Z|[+-]\d{2}:?\d{2}))?\b",
        r"\b\d{4}-\d{2}-\d{2},\s*\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{4}\s+\d{1,2}\s+\d{1,2}\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{1,2}\s+\d{1,2}\s+\d{2,4}\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b(?:" + month_alt_early + r")\.?\s+\d{1,2}\s*,\s+"
        r"\d{2,4}\s+\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{4}\s+(?:0?[1-9]|1[0-2])\s+"
        r"(?:0?[1-9]|[12]\d|3[01])\b",
        r"\b(?:0?[1-9]|[12]\d|3[01])\s+(?:0?[1-9]|1[0-2])\s+"
        r"\d{4}\b",
        # A date with its time standing after it, in the
        # orders the set above omits: the slash orders in
        # either direction and at a two digit year, with
        # or without a comma; the month name orders with
        # or without a comma and with an ordinal day; the
        # space separated numeric orders; and the time
        # standing first in one datetime expression.
        r"\b\d{1,2}/\d{1,2}/\d{2,4}\s*,?\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b(?:" + month_alt_early + r")\.?\s+"
        r"\d{1,2}(?:st|nd|rd|th)?\s*,?\s+\d{2,4}\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:"
        + month_alt_early + r")\.?\s+\d{2,4}\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*,?\s+(?:"
        + month_alt_early + r")\.?\s+"
        r"\d{1,2}(?:st|nd|rd|th)?\s*,?\s+\d{2,4}\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*,?\s+"
        r"\d{1,2}(?:st|nd|rd|th)?\s+(?:"
        + month_alt_early + r")\.?\s+\d{2,4}\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s*,?\s+"
        r"\d{1,2}/\d{1,2}/\d{2,4}\b",
        # The orders the set above still omits: a hyphen
        # date with its time in any order, at two or four
        # digit years and at single digit parts; a time
        # standing first against an ISO or a dotted date,
        # and a dotted date with its time; a month name
        # date with a comma standing between the date and
        # its time or inside the date, in either order and
        # in the year first order; a single digit ISO date
        # standing alone; and a time glued to its ISO date
        # with the letter T and no colon.
        r"\b\d{1,4}-\d{1,2}-\d{1,4}\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s+"
        r"\d{4}-\d{1,2}-\d{1,2}\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\s+"
        r"\d{1,2}\.\d{1,2}\.\d{2,4}\b",
        r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{1,2}\s+(?:" + month_alt_early + r")\.?"
        r"\s*,?\s*\d{2,4}\s*,?\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b(?:" + month_alt_early + r")\.?\s+"
        r"\d{1,2}\s*,?\s*\d{2,4}\s*,?\s+"
        r"\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{4}\s*,?\s+(?:" + month_alt_early + r")\.?"
        r"\s+\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
        r"\b\d{4}-\d{1,2}-\d{1,2}T\d{4}(?:\d{2})?\b",
    ):
        masked = _mask(
            masked,
            [
                (m.start(), m.end())
                for m in re.finditer(date_pattern, masked,
                                      re.IGNORECASE)
            ],
        )
    # The ISO datetime form stands masked whole before the
    # plain date mask can take its date part and leave the
    # time standing as a remainder, in the T form and in
    # the space separated form alike. A year and month
    # fragment stands masked on the same exclusion.
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(
                r"\b\d{4}-\d{2}-\d{2}[T ]\d{1,2}:\d{2}"
                r"(?::\d{2})?\b",
                masked,
            )
        ],
    )
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(
                r"\b\d{4}-\d{2}(?![-\d])", masked)
        ],
    )
    # The same fragment in the reverse order, the month
    # standing before the year, counts nothing either.
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(
                r"\b\d{1,2}-\d{4}(?![-\d])", masked)
        ],
    )
    # The same fragment in dotted form, in either order,
    # counts nothing either, as its hyphen twins do.
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(
                r"\b\d{4}\.\d{1,2}(?!\d)(?!\.\d)", masked)
        ],
    )
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(
                r"\b\d{1,2}\.\d{4}(?!\d)(?!\.\d)", masked)
        ],
    )
    # The same fragment in slash form, in either
    # order, counts nothing either, as its hyphen and
    # dotted twins do. Each limb stands guarded
    # against a digit or a slash standing before it
    # and against a slash or a digit standing after
    # its closing part, so neither limb bites inside
    # a full slash date standing around it.
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(
                r"(?<![\d/])\d{4}/\d{1,2}(?![/\d])", masked)
        ],
    )
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(
                r"(?<![\d/])\d{1,2}/\d{4}(?![/\d])", masked)
        ],
    )
    # Two digit year numeric dates in the hyphen and
    # space orders count nothing on the same exclusion,
    # as their slash, dotted, and month name twins
    # already do.
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(
                r"\b\d{1,2}-\d{1,2}-\d{1,2}\b", masked)
        ],
    )
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(
                r"\b\d{1,2}\s+\d{1,2}\s+\d{1,2}\b", masked)
        ],
    )
    # A date fragment counts nothing, in either date form.
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(r"\b\d{4}-\d{2}-\d{2}\b", masked)
        ],
    )
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", masked)
        ],
    )
    month_names = "|".join(name.capitalize() for name in _MONTHS)
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(
                r"\b(?:" + month_names + r")\s+\d{1,2},\s+\d{4}\b",
                masked,
            )
        ],
    )
    # A date fragment counts nothing in any written form,
    # not only in the closed freshness formats: the
    # abbreviated month form, the year first numeric
    # form, and the day first month name form stand
    # masked here on the same exclusion.
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(
                r"\b(?:" + _MONTH_ABBREVIATIONS + r")\.?\s+"
                r"\d{1,2},\s+\d{4}\b",
                masked,
            )
        ],
    )
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(r"\b\d{4}/\d{1,2}/\d{1,2}\b", masked)
        ],
    )
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(
                r"\b\d{1,2}\s+(?:" + month_names + r"|"
                + _MONTH_ABBREVIATIONS + r")\.?\s+\d{4}\b",
                masked,
            )
        ],
    )
    # The same exclusion in its remaining written forms:
    # case variants of every month form, a month first
    # form with no comma, a year first form with a month
    # name, two digit years, hyphenated forms, and the
    # ISO datetime form. Month names match case folded
    # here, as a reader reads them in any case.
    month_alt = month_names + "|" + _MONTH_ABBREVIATIONS
    for date_pattern in (
        r"\b\d{4}-\d{2}-\d{2}[T ]\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b(?:" + month_alt + r")\.?\s+"
        r"\d{1,2}(?:st|nd|rd|th)\s*,\s*\d{2,4}\b",
        r"\b(?:" + month_alt + r")\.?\s+"
        r"\d{1,2}(?:st|nd|rd|th)\s+\d{2,4}\b",
        r"\b\d{1,2}(?:st|nd|rd|th)\s+(?:"
        + month_alt + r")\.?\s+\d{2,4}\b",
        r"\b(?:" + month_alt + r")\.?\s+\d{1,2},\s+\d{2,4}\b",
        r"\b(?:" + month_alt + r")\.?\s+\d{1,2}\s+\d{2,4}\b",
        r"\b\d{4}\s+(?:" + month_alt + r")\.?\s+\d{1,2}\b",
        r"\b\d{1,2}\s+(?:" + month_alt + r")\.?\s+\d{2,4}\b",
        r"\b\d{1,2}-(?:" + month_alt + r")\.?-\d{2,4}\b",
        r"\b(?:" + month_alt + r")\.?-\d{1,2}-\d{2,4}\b",
        r"\b\d{1,2}\s+(?:" + month_alt + r")\.?\s*,\s*\d{2,4}\b",
        r"\b\d{4}\s+(?:" + month_alt + r")\.?\s*,\s*\d{1,2}\b",
        r"\b\d{4}\s*,\s*(?:" + month_alt + r")\.?\s+\d{1,2}\b",
        r"\b(?:" + month_alt + r")\.?\s*,\s*\d{1,2}\s+\d{2,4}\b",
        r"\bT\d{2}:\d{2}(?::\d{2})?\b",
        r"\b(?:" + month_alt + r")\.?\s+\d{1,2}\s*,\s*\d{2,4}\b",
    ):
        masked = _mask(
            masked,
            [
                (m.start(), m.end())
                for m in re.finditer(date_pattern, masked,
                                      re.IGNORECASE)
            ],
        )
    # A version string counts nothing.
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(r"\b\d+(?:\.\d+){2,}\b", masked)
        ],
    )
    # A figure the sentence itself names as its version
    # counts nothing either, in the one part form as in
    # the two part and longer forms: the naming word
    # stands beside the figure in the sentence that
    # carries it, with a colon between them, or with the
    # word is between them, as well as standing directly
    # beside it, and the two stated connectors compose,
    # the word is and then a colon standing in sequence
    # between the naming word and the figure, or a colon
    # and then the word is, the reverse composition of
    # the same two connectors. A connector standing
    # doubled or repeated in that sequence, a second
    # colon or a second word is, stands in the same
    # naming, each connector standing in it being one of
    # the two stated connectors. The connector sequence
    # stands inside an atomic group: a stretch of
    # whitespace and connector text between two
    # connectors can be split between the branches and
    # the repetitions in combinatorially many ways, and
    # where no figure follows the sequence the reading
    # otherwise tries every split before it fails. The
    # atomic group commits the reading to the one greedy
    # split it takes, so a repeated connector sequence
    # with no figure after it fails at the naming word
    # at once, at the same result wherever a figure does
    # follow, because the greedy split is the split that
    # reaches the figure. The first connector in the
    # word is form consumes the separator after it, as
    # the repetitions of that connector do, so the
    # figure stands against the end of the sequence in
    # the greedy split itself.
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(
                r"\bversion(?>(?:\s+is(?=[\s:])\s*|\s*:\s*|\s+)"
                r"(?:\s*:\s*|\s*is(?=[\s:])\s*)*)"
                r"\d+(?:\.\d+)*\b",
                masked, re.IGNORECASE
            )
        ],
    )
    spans = []
    for match in _STATISTIC_PATTERN.finditer(masked):
        # The digit pattern takes commas between digits, so
        # a trailing sentence comma can ride on the end of a
        # token. That comma is punctuation, not part of the
        # figure: it comes off the token before any test on
        # the figure itself, so a year standing alone is
        # seen as a year whatever punctuation follows it,
        # and a genuine figure keeps a span without the
        # trailing comma.
        token = match.group("token").rstrip(",")
        plain = token.strip()
        if re.fullmatch(r"\d{4}", plain):
            # A year between 1900 and 2099 standing alone.
            if 1900 <= int(plain) <= 2099:
                continue
        start = match.start("token")
        end = start + len(token)
        spans.append(_span(text, start, end))
    count = len(spans)
    return {
        "earned": _round3(min(count, 4) / 4.0),
        "reason_code": "STAT_COUNT" if count else "STAT_NONE",
        "evidence_spans": spans,
        "count": count,
    }


def _quotation_analysis(page):
    text = _page_text(page)
    paragraphs = _paragraph_spans(text)
    spans = []
    attributed = 0
    unattributed = 0
    for span_start, span_end in _quoted_spans(text):
        inner = text[span_start + 1:span_end - 1]
        if len(inner.split()) < 4:
            continue
        start, end = span_start, span_end
        spans.append(_span(text, start, end))
        # The attribution window runs 100 characters after
        # the span and may not cross a paragraph boundary.
        window_end = end + 100
        for chunk_start, chunk_end in paragraphs:
            if chunk_start <= start < chunk_end or (
                start == chunk_end == len(text)
            ):
                window_end = min(window_end, chunk_end)
                break
        window = text[end:window_end]
        # A single capitalised name is a cue in its own
        # right, as one of the three cues in the closed
        # set. The window may cross a sentence boundary,
        # and no sentence position exception stands in
        # that statement, so a capitalised name counts
        # wherever it stands inside the window, including
        # as the first word of the next sentence.
        single_name = bool(
            re.search(r"\b[A-Z][a-z]+\b", window)
        )
        cue = (
            re.search(r"(?<![A-Za-z])said(?![A-Za-z])", window,
                      re.IGNORECASE)
            or re.search(r"according\s+to", window, re.IGNORECASE)
            or re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", window)
            or re.search(r"(?<![A-Za-z])[A-Z][a-z]+\s+(?:wrote|said)\b",
                         window)
            or single_name
        )
        if cue:
            attributed += 1
        else:
            unattributed += 1
    total = attributed + 0.5 * unattributed
    earned = _round3(min(total, 2) / 2.0)
    if attributed and unattributed:
        # Two codes hold together: the code of the lower
        # earning outcome stands, and an unattributed span
        # earns less per span than an attributed one.
        reason = "QUO_UNATTRIBUTED"
    elif attributed:
        reason = "QUO_COUNT"
    else:
        reason = "QUOTE_NONE_ATTRIBUTED"
    return {
        "earned": earned,
        "reason_code": reason,
        "evidence_spans": spans,
        "attributed": attributed,
        "unattributed": unattributed,
    }


# ----------------------------------------------------------------
# The other seven checks


def _answer_first(page, facts):
    text = _page_text(page)
    sentences = _page_sentences(page)
    offsets = _sentence_offsets(text, sentences)
    ends = []
    if len(sentences) >= 2:
        ends.append(offsets[1] + len(sentences[1]))
    elif sentences:
        ends.append(offsets[0] + len(sentences[0]))
    words = list(re.finditer(r"\S+", text))
    if words:
        ends.append(words[min(60, len(words)) - 1].end())
    window_end = max(ends) if ends else 0
    window = text[:window_end]

    names = []
    if facts.get("product_name"):
        names.append(facts["product_name"])
    names.extend(facts.get("aliases") or [])
    categories = list(facts.get("category_terms") or [])

    alias_in_window = any(_term_present(window, term) for term in names)
    category_in_window = any(
        _term_present(window, term) for term in categories
    )
    alias_anywhere = any(_term_present(text, term) for term in names)
    category_anywhere = any(
        _term_present(text, term) for term in categories
    )
    if not alias_anywhere and not category_anywhere:
        return 0, "AF_MISSING_TERM"
    if alias_in_window or category_in_window:
        if "?" in window:
            return 0, "AF_TERM_NOT_DECLARATIVE"
        if alias_in_window and category_in_window:
            return 1.0, "AF_FULL"
        if alias_in_window:
            return 0.6, "AF_PARTIAL"
        return 0.4, "AF_PARTIAL"
    return 0, "AF_OUTSIDE_WINDOW"


_SIGNAL_WORDS = ("vs", "versus", "compared", "alternative")


def _comparison(page, facts):
    text = _page_text(page)
    earned = 0.0

    competitor_hit = False
    for competitor in facts.get("competitors") or []:
        terms = []
        comp_name = _get(competitor, "name")
        if comp_name:
            terms.append(comp_name)
        terms.extend(_get(competitor, "aliases", []) or [])
        if any(_term_present(text, term) for term in terms):
            competitor_hit = True
            break
    if competitor_hit:
        earned += 0.4

    sentences = _page_sentences(page)
    offsets = _sentence_offsets(text, sentences)
    signal_offset = None
    for sentence, offset in zip(sentences, offsets):
        tokens = re.findall(r"[A-Za-z]+", sentence.casefold())
        hit = any(token in _SIGNAL_WORDS for token in tokens)
        if not hit and "best" in tokens and "for" in tokens:
            if tokens.index("best") < len(tokens) - 1 - tokens[::-1].index(
                "for"
            ):
                hit = True
        if hit:
            signal_offset = offset
            break
    if signal_offset is not None:
        earned += 0.2

    # The comparison section: the section whose heading
    # names a comparison, or, with no such heading, the
    # paragraph holding the first signal. With neither, no
    # section stands.
    section_span = None
    for section in _get(page, "sections", []) or []:
        heading = _get(section, "heading_text")
        if heading and any(
            word in str(heading).lower()
            for word in ("comparison", "versus", "alternative")
        ):
            section_span = (
                _get(section, "start", 0),
                _get(section, "end", len(text)),
            )
            break
    if section_span is None and signal_offset is not None:
        for chunk_start, chunk_end in _paragraph_spans(text):
            if chunk_start <= signal_offset < chunk_end:
                section_span = (chunk_start, chunk_end)
                break

    if section_span is not None:
        structured = False
        for listing in _get(page, "lists", []) or []:
            items = _get(listing, "items", []) or []
            start = _get(listing, "start")
            if len(items) >= 3 and start is not None and (
                section_span[0] <= start < section_span[1]
            ):
                structured = True
        for table in _get(page, "tables", []) or []:
            rows = _get(table, "rows", None)
            if rows is None:
                rows = _get(table, "items", []) or []
            start = _get(table, "start")
            if len(rows) >= 3 and start is not None and (
                section_span[0] <= start < section_span[1]
            ):
                structured = True
        if structured:
            earned += 0.2
        # The criterion word component: at least 3 distinct
        # criterion words from the printed list near the
        # comparison, where near means inside the section or
        # within 100 words after its end, counted in word
        # tokens from the section last word.
        near_words = {
            word for word, _, _ in _token_stream(
                text[section_span[0]:section_span[1]])
        }
        near_words |= {
            word for word, _, _ in _token_stream(
                text[section_span[1]:])[:100]
        }
        if len(near_words & set(_CRITERION_WORDS)) >= 3:
            earned += 0.2

    earned = _round3(earned)
    if earned <= 0:
        reason = "CMP_MISSING"
    elif earned >= 1.0:
        reason = "CMP_OK"
    else:
        reason = "CMP_THIN"
    return earned, reason


_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MONTH_DATE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{1,2}),\s+(\d{4})\b",
    re.IGNORECASE,
)
_LABELLED_LINE = re.compile(
    r"^\s*(Updated|Last updated|Date):\s*(.*)$", re.IGNORECASE
)


def _parse_date_in(text_fragment):
    """The first parseable date in the closed format set."""
    candidates = []
    for match in _ISO_DATE.finditer(text_fragment):
        try:
            value = datetime.date(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
            )
        except ValueError:
            continue
        candidates.append((match.start(), value))
    for match in _MONTH_DATE.finditer(text_fragment):
        try:
            value = datetime.date(
                int(match.group(3)),
                _MONTHS[match.group(1).lower()],
                int(match.group(2)),
            )
        except ValueError:
            continue
        candidates.append((match.start(), value))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _freshness(page, audit_date):
    text = _page_text(page)
    lines = text.splitlines()
    found = None
    # First limb: labelled lines, searched in the whole
    # text, the first labelled line in extracted order wins.
    for line in lines:
        match = _LABELLED_LINE.match(line)
        if not match:
            continue
        value = _parse_date_in(match.group(2))
        if value is not None:
            found = value
            break
    # Second limb: any date in the closed format set in
    # the first 20 lines.
    if found is None:
        for line in lines[:20]:
            value = _parse_date_in(line)
            if value is not None:
                found = value
                break
    if found is None:
        return 0, "FRESH_NO_DATE"
    if audit_date is None:
        return 0, "FRESH_NO_DATE"
    if isinstance(audit_date, datetime.datetime):
        audit_value = audit_date.date()
    elif isinstance(audit_date, datetime.date):
        audit_value = audit_date
    else:
        try:
            audit_value = datetime.date.fromisoformat(str(audit_date))
        except ValueError:
            # A date input outside the stated form earns
            # no freshness credit on a direct call to this
            # home, rather than raising a raw error with
            # no recorded outcome. The service route
            # refuses the same strings before this point.
            return 0, "FRESH_NO_DATE"
    age = (audit_value - found).days
    if age < 0:
        return 0, "FRESH_FUTURE"
    if age <= 90:
        return 1.0, "FRESH_OK"
    if age <= 180:
        return 0.7, "FRESH_STALE"
    if age <= 365:
        return 0.4, "FRESH_STALE"
    if age <= 730:
        return 0.2, "FRESH_STALE"
    return 0, "FRESH_STALE"


def _word_set(text_value):
    return set(re.findall(r"[^\W_]+", (text_value or "").casefold()))


_SUPERLATIVE_LEXICON = (
    "best", "leading", "top", "number one", "no. 1", "fastest",
    "easiest", "most powerful", "industry leading",
    "best in class", "unrivalled", "unmatched", "ultimate",
)

_FILLER_BOOSTERS = (
    "revolutionary", "game changing", "cutting edge",
    "world class", "seamless", "robust solution",
)

_CRITERION_WORDS = (
    "price", "speed", "cost", "support", "features",
    "setup", "quality", "limit", "free", "open",
)


def _token_stream(text_value):
    return [
        (match.group(0), match.start(), match.end())
        for match in re.finditer(r"[^\W_]+", (text_value or "").casefold())
    ]


def _list_hits(text_value, entries):
    """Hits of the printed list entries in a text.

    Matching is case insensitive over word tokens, multi
    word entries match as consecutive token sequences, at
    each position the longest entry that matches is taken
    first, and a span consumed by a match is not matched
    again, as brief Section 5.7 states for every printed
    list. Returns (start, end) character spans.
    """
    tokens = _token_stream(text_value)
    entry_tokens = []
    for entry in entries:
        words = tuple(word for word, _, _ in _token_stream(entry))
        if words:
            entry_tokens.append(words)
    entry_tokens.sort(key=len, reverse=True)
    hits = []
    index = 0
    while index < len(tokens):
        matched = 0
        for words in entry_tokens:
            size = len(words)
            if tuple(
                token for token, _, _ in tokens[index:index + size]
            ) == words:
                matched = size
                break
        if matched:
            hits.append((tokens[index][1], tokens[index + matched - 1][2]))
            index += matched
        else:
            index += 1
    return hits


def _sentence_evidence_flags(page, analyses):
    """One flag per sentence: the sentence holds evidence.

    Evidence spans are the counted citation, statistic,
    and quotation spans the shared analyses report; a
    sentence holds evidence where one of those spans
    starts inside it.
    """
    text = _page_text(page)
    sentences = _page_sentences(page)
    offsets = _sentence_offsets(text, sentences)
    starts = []
    for analysis in analyses:
        for span in analysis["evidence_spans"]:
            starts.append(_get(span, "start"))
    flags = []
    for index, sentence in enumerate(sentences):
        start = offsets[index]
        end = start + len(sentence)
        flags.append(any(
            value is not None and start <= value < end for value in starts
        ))
    return flags


def _unproven_superlatives(page, citations, statistics, quotations):
    text = _page_text(page)
    sentences = _page_sentences(page)
    offsets = _sentence_offsets(text, sentences)
    flags = _sentence_evidence_flags(
        page, (citations, statistics, quotations))
    spans = []
    for start, end in _list_hits(text, _SUPERLATIVE_LEXICON):
        sentence_index = None
        for index, sentence in enumerate(sentences):
            if offsets[index] <= start < offsets[index] + len(sentence):
                sentence_index = index
                break
        proven = False
        if sentence_index is not None:
            for neighbour in (
                sentence_index - 1, sentence_index, sentence_index + 1
            ):
                if 0 <= neighbour < len(flags) and flags[neighbour]:
                    proven = True
        if not proven:
            spans.append(_span(text, start, end))
    if not spans:
        return 1.0, "SUP_OK", []
    earned = _round3(max(0.0, 1.0 - 0.34 * len(spans)))
    return earned, "SUP_UNPROVEN", spans


def _normalise_whitespace(text_value):
    return re.sub(r"\s+", " ", str(text_value or "")).strip()


def _description_consistency(page, facts):
    text = _page_text(page)
    canonical = facts.get("canonical_line")
    if not canonical:
        return 0, "DESC_MISSING"
    # Verbatim is judged after whitespace normalisation:
    # the canonical line and the page text both stand with
    # every whitespace run folded to one space, and the
    # line must stand with a word boundary at each end, so
    # a line glued inside longer words earns nothing.
    normalised_text = _normalise_whitespace(text)
    normalised_canonical = _normalise_whitespace(canonical)
    verbatim = re.search(
        r"(?<![^\W_])" + re.escape(normalised_canonical) + r"(?![^\W_])",
        normalised_text,
    )
    if verbatim is not None:
        return 1.0, "DESC_PRESENT"
    canonical_words = _word_set(canonical)
    if canonical_words:
        for sentence in _page_sentences(page):
            if _normalise_whitespace(sentence) == normalised_canonical:
                continue
            words = _word_set(sentence)
            if not words:
                continue
            union = canonical_words | words
            similarity = len(canonical_words & words) / len(union)
            if similarity >= 0.6:
                return 0.3, "DESC_DRIFT"
    return 0, "DESC_MISSING"


def _keyword_stuffing(page, facts):
    text = _page_text(page)
    word_count = _get(page, "word_count", 0) or 0
    terms = []
    if facts.get("product_name"):
        terms.append(facts["product_name"])
    terms.extend(facts.get("category_terms") or [])
    peak = 0.0
    if word_count:
        for term in terms:
            occurrences = _term_count(text, term)
            term_length = len(str(term).split())
            if term_length and occurrences:
                density = occurrences * term_length * 100.0 / word_count
                peak = max(peak, density)
    density_outcome = 1.0
    if peak > 5:
        density_outcome = 0.25
    elif peak > 3:
        density_outcome = 0.5
    sentences = _page_sentences(page)
    repeated = len(sentences) != len(set(sentences))
    repeat_outcome = 0.75 if repeated else 1.0
    # The deductions stack against the start of 1.0.
    earned = _round3(max(0.0, density_outcome + repeat_outcome - 1.0))
    if density_outcome == 1.0 and repeat_outcome == 1.0:
        reason = "STF_OK"
    elif density_outcome <= repeat_outcome:
        # The code of the lower earning outcome stands.
        reason = "STF_DENSE" if density_outcome < 1.0 else "STF_REPEAT"
    else:
        reason = "STF_REPEAT"
    return earned, reason


def _fluff(page, context, analyses=()):
    word_count = _get(page, "word_count", 0) or 0
    if word_count:
        evidence = (
            context["citation_count"]
            + context["statistic_count"]
            + context["attributed_count"]
        )
        density = evidence * 100.0 / word_count
    else:
        density = 0.0
    if word_count >= 800 and density < 0.5:
        return 0, "FLF_LONG_LOW_EVIDENCE"
    if 400 <= word_count <= 799 and density < 0.5:
        return 0.4, "FLF_LONG_LOW_EVIDENCE"
    # The filler booster deduction: the otherwise outcome
    # loses 0.3 where the stated filler boosters appear at
    # least 3 times with no evidence in their sentences.
    if analyses:
        flags = _sentence_evidence_flags(page, analyses)
        booster_hits = 0
        for index, sentence in enumerate(_page_sentences(page)):
            if index < len(flags) and flags[index]:
                continue
            booster_hits += len(_list_hits(sentence, _FILLER_BOOSTERS))
        if booster_hits >= 3:
            return 0.7, "FLF_BOOSTERS"
    return 1.0, "FLF_OK"


def _section_breakdown(page, spans):
    if not spans:
        return []
    sections = _get(page, "sections", []) or []
    breakdown = []
    for index, section in enumerate(sections):
        start = _get(section, "start", 0)
        end = _get(section, "end", 0)
        present = False
        for span in spans:
            if start <= span["start"] < end:
                present = True
            elif index == len(sections) - 1 and span["start"] == end:
                present = True
        breakdown.append(
            {
                "heading_text": _get(section, "heading_text"),
                "start": start,
                "end": end,
                "mark": "present" if present else "absent",
            }
        )
    return breakdown


# ----------------------------------------------------------------
# Public operations


def run_checks(page, facts=None, audit_date=None, **_ignored):
    """Run the ten checks over one ExtractedPage.

    Returns a list of ten CheckResult dicts in registry
    order. No supplied file is read.
    """
    facts = _fact_terms(facts or {})
    text = _page_text(page)
    empty = not text.strip() and not _page_sentences(page)

    citations = _citation_analysis(page, facts)
    statistics = _statistic_analysis(page)
    quotations = _quotation_analysis(page)
    context = {
        "citation_count": citations["count"],
        "statistic_count": statistics["count"],
        "attributed_count": quotations["attributed"],
    }

    outcomes = {}
    outcomes["answer_first"] = (*_answer_first(page, facts), [], {})
    outcomes["citations"] = (
        citations["earned"],
        citations["reason_code"],
        citations["evidence_spans"],
        {"distinct_target_count": citations["count"]},
    )
    outcomes["statistics"] = (
        statistics["earned"],
        statistics["reason_code"],
        statistics["evidence_spans"],
        {"statistic_token_count": statistics["count"]},
    )
    outcomes["quotations"] = (
        quotations["earned"],
        quotations["reason_code"],
        quotations["evidence_spans"],
        {
            "attributed_span_count": quotations["attributed"],
            "unattributed_span_count": quotations["unattributed"],
        },
    )
    outcomes["comparison"] = (*_comparison(page, facts), [], {})
    outcomes["freshness"] = (*_freshness(page, audit_date), [], {})
    outcomes["description_consistency"] = (
        *_description_consistency(page, facts),
        [],
        {},
    )
    outcomes["keyword_stuffing"] = (
        *_keyword_stuffing(page, facts),
        [],
        {},
    )
    outcomes["fluff"] = (
        *_fluff(page, context, (citations, statistics, quotations)),
        [],
        {},
    )
    outcomes["unproven_superlatives"] = (
        *_unproven_superlatives(page, citations, statistics, quotations),
        {},
    )

    results = []
    for check_id, weight, evidence_class in CHECK_REGISTRY:
        earned, reason, spans, counts = outcomes[check_id]
        applicable = True
        if check_id == "description_consistency" and not facts.get(
            "is_product_page", True
        ):
            applicable = False
            # A not applicable check carries no earned
            # fraction and no presence reason: the record
            # stands with status not_applicable alone.
            earned = None
            reason = None
        if check_id == "comparison" and (
            not facts.get("competitors")
            or not facts.get("category_terms")
        ):
            # Brief Section 10.9 condition C5: comparison
            # applies only where the product has a category
            # and at least one competitor, and reports
            # CMP_NA, the code the record already carries,
            # where it does not apply.
            applicable = False
            reason = "CMP_NA"
        result = {
            "check_id": check_id,
            "weight": weight,
            "earned": _round3(earned) if earned is not None else None,
            "status": assign_status(
                check_id, applicable=applicable, empty=empty
            ),
            "reason_code": reason,
            "evidence_class": evidence_class,
            "evidence_spans": spans,
            "section_breakdown": (
                _section_breakdown(page, spans)
                if check_id in _EVIDENCE_CHECKS
                else []
            ),
            "detail_counts": counts,
            "lexicon_coverage": None,
        }
        results.append(result)
    return results


def _count_for(result, keys, fallback_spans=True):
    counts = _get(result, "detail_counts")
    if isinstance(counts, dict):
        for key in keys:
            if key in counts:
                return counts[key]
    if fallback_spans:
        spans = _get(result, "evidence_spans", []) or []
        if _get(result, "check_id") == "quotations" and spans:
            # The cap quantity for quotations is the
            # attributed span count, and a spans only
            # record carries unattributed spans beside
            # attributed ones, so the span total is not
            # that count. The record's own reason code
            # and earned value state it: the none
            # attributed code stands only where no span
            # is attributed, and where a span stands
            # attributed the earned formula (attributed
            # plus half the unattributed, over 2) gives
            # the count back from the span total.
            reason = _get(result, "reason_code")
            if reason == "QUOTE_NONE_ATTRIBUTED":
                return 0
            if reason in ("QUO_COUNT", "QUO_UNATTRIBUTED"):
                earned = _get(result, "earned", 0) or 0
                derived = int(round(4 * float(earned) - len(spans)))
                return max(1, min(len(spans), derived))
        return len(spans)
    return 0


def compute_score(results):
    """The ScoreObject computation over CheckResults only.

    A result counts as applicable unless its status stands
    not_applicable. The evidence cap of 39 operates on the
    per check counts (distinct citation targets, statistic
    tokens, attributed spans), never on earned values.
    """
    results = list(results or [])
    applicable = []
    for result in results:
        status = _get(result, "status")
        if status == "not_applicable":
            continue
        applicable.append(result)
    applicable_checks = [
        _get(result, "check_id") for result in applicable
    ]
    applicable_weight = sum(
        _get(result, "weight", 0) or 0 for result in applicable
    )
    score = {
        "applicable_basis": {
            "applicable_checks": applicable_checks,
            "applicable_weight": applicable_weight,
        },
        "cap_status": False,
        "score_ruleset_version": SCORE_RULESET_VERSION,
        "honesty_sentence": HONESTY_SENTENCE,
        "claim_type": "signal_presence_only",
        "validated_predictor": False,
        # The secondary figure on the not applicable as
        # zero basis (brief Section 5.8, IM7-BRK-3): the
        # ScoreObject carries it in this field, in the
        # landing stated form. It is not a second value
        # field and it is not a ScoreObject: it is an
        # object holding its figure under the member
        # named value, its total weight, and its basis
        # statement, and it carries no band of its own.
        # The member name value matters beyond this
        # module: the journal canonical form renders a
        # non integer number only under a member whose
        # scale stands defined, and value carries the
        # score scale of one decimal place. It stands as
        # None where it does not print: on a fully
        # applicable page, and in the all not applicable
        # absence case below, where it is suppressed.
        "secondary_figure": None,
    }
    if not applicable or applicable_weight == 0:
        # SEAM-SCORE-EMPTY: the empty case carries the
        # stated absence form, not an invented number.
        score["value"] = None
        score["band"] = None
        return score
    # Exact recomputation: the earned values stand at
    # three decimal places and the weights are integers,
    # so the weighted sum is exact in decimal. Binary
    # floating point puts a sum such as 26.45 over 92
    # just under 28.75 and rounds it the wrong way; the
    # decimal sum rounds as the formula states.
    weighted = sum(
        Decimal(str(_get(result, "earned", 0) or 0))
        * Decimal(str(_get(result, "weight", 0) or 0))
        for result in applicable
    )
    value = _round_score(weighted / Decimal(applicable_weight) * 100)
    # The secondary figure: the same numerator over the
    # total weight of 100, times 100, rounded to one
    # decimal place as the headline score is rounded.
    # It prints only where at least one check stands not
    # applicable and at least one check stands applicable.
    has_not_applicable = len(applicable) < len(results)
    secondary = None
    if has_not_applicable:
        secondary = {
            "value": _round_score(weighted / Decimal(100) * 100),
            "total_weight": 100,
            "basis": (
                "Computed on a different basis from the "
                "headline score: the headline score is "
                "computed on the applicable checks with "
                "not applicable weight redistributed, and "
                "this figure is computed on the total "
                "weight of 100 with not applicable checks "
                "earning 0. Neither figure ranks against "
                "a score on another basis."
            ),
        }
    by_id = {_get(result, "check_id"): result for result in results}
    cap_counts = []
    for check_id, keys in (
        ("citations", ("distinct_target_count",)),
        ("statistics", ("statistic_token_count",)),
        ("quotations", ("attributed_span_count",)),
    ):
        result = by_id.get(check_id)
        if result is None:
            cap_counts.append(None)
        else:
            cap_counts.append(_count_for(result, keys))
    if cap_counts == [0, 0, 0]:
        score["cap_status"] = True
        if value > 39.0:
            value = 39.0
        # The cap applies to the secondary figure on the
        # same trigger as the headline score; no figure
        # printed beside a capped headline stands uncapped.
        if secondary is not None and secondary["value"] > 39.0:
            secondary["value"] = 39.0
    score["value"] = value
    score["secondary_figure"] = secondary
    if value >= 80:
        score["band"] = "strong"
    elif value >= 60:
        score["band"] = "developing"
    elif value >= 40:
        score["band"] = "thin"
    else:
        score["band"] = "poor"
    return score
