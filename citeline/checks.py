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
2. SEAM-LISTS. The list dependent limbs that the plan
   stops at this seam are not built: the comparison
   criterion word component earns nothing here, the fluff
   filler booster deduction is not applied, and the
   unproven superlatives hit limb is not applied, so that
   check earns full credit in its list independent form.
3. SEAM-SCORE-EMPTY. For an empty extraction every check
   stands not applicable, and compute_score returns the
   stated absence form for value and band rather than a
   number, because that case stands unruled.
4. The description consistency whitespace normalisation
   operation is a referred stop and is not invented here.
   The rule precedence builds now (verbatim, then drift,
   then absence) on cases that need no normalisation
   judgement: verbatim means the canonical line stands in
   the running text character for character.
"""

import datetime
import re

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
        r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])",
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


def _host_of(target):
    match = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://([^/?#]+)", target or "")
    if not match:
        return None
    host = match.group(1)
    host = host.rsplit("@", 1)[-1]
    host = host.split(":", 1)[0]
    return host.lower()


_TEXT_URL_PATTERN = re.compile(
    r"https?://[^\s<>\"'()\[\]{}]+", re.IGNORECASE
)


def _citation_analysis(page, facts):
    text = _page_text(page)
    domain = (facts.get("domain") or "").lower() or None
    counted = {}
    self_seen = False
    for link in _get(page, "links", []) or []:
        target, link_text, start, end = _link_parts(link)
        if not target:
            continue
        host = _host_of(target)
        if host is None:
            # An anchor link or a relative link is internal.
            continue
        scheme = target.split(":", 1)[0].lower()
        if scheme not in ("http", "https"):
            continue
        if domain and (host == domain or host.endswith("." + domain)):
            self_seen = True
            continue
        if target in counted:
            continue
        if start is None or start < 0:
            start = text.find(link_text or target)
        if start is None or start < 0:
            start = 0
        if end is None or end <= start:
            end = start + len(link_text or target)
        counted[target] = _span(text, start, end)
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
        if target in counted:
            continue
        start = match.start()
        counted[target] = _span(text, start, start + len(target))
    spans = [counted[target] for target in counted]
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
                chunk[0] <= span["start"] < chunk[1] for span in spans
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


def _statistic_analysis(page):
    text = _page_text(page)
    masked = text
    # Any token inside a quoted span is excluded.
    quoted = [
        (match.start(), match.end())
        for match in re.finditer(r'"[^"\n]*"', masked)
    ]
    masked = _mask(masked, quoted)
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
    # A version string counts nothing.
    masked = _mask(
        masked,
        [
            (m.start(), m.end())
            for m in re.finditer(r"\b\d+(?:\.\d+){2,}\b", masked)
        ],
    )
    spans = []
    for match in _STATISTIC_PATTERN.finditer(masked):
        token = match.group("token")
        plain = token.strip()
        if re.fullmatch(r"\d{4}", plain):
            # A year between 1900 and 2099 standing alone.
            if 1900 <= int(plain) <= 2099:
                continue
        start, end = match.start("token"), match.end("token")
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
    for match in re.finditer(r'"[^"\n]*"', text):
        inner = match.group(0)[1:-1]
        if len(inner.split()) < 4:
            continue
        start, end = match.start(), match.end()
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
        cue = (
            re.search(r"(?<![A-Za-z])said(?![A-Za-z])", window,
                      re.IGNORECASE)
            or re.search(r"according\s+to", window, re.IGNORECASE)
            or re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", window)
            or re.search(r"(?<![A-Za-z])[A-Z][a-z]+\s+(?:wrote|said)\b",
                         window)
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
        tokens = re.findall(r"[A-Za-z]+", sentence.lower())
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
        # The criterion word component is a list dependent
        # limb. It stands at SEAM-LISTS and is not built
        # here, so it earns nothing in this form.

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
    r"^\s*(Updated|Last updated|Date)\s*:\s*(.*)$", re.IGNORECASE
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
        audit_value = datetime.date.fromisoformat(str(audit_date))
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
    return set(re.findall(r"[a-z0-9]+", (text_value or "").lower()))


def _description_consistency(page, facts):
    text = _page_text(page)
    canonical = facts.get("canonical_line")
    if not canonical:
        return 0, "DESC_MISSING"
    if canonical in text:
        return 1.0, "DESC_PRESENT"
    canonical_words = _word_set(canonical)
    if canonical_words:
        for sentence in _page_sentences(page):
            if sentence.strip() == canonical.strip():
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


def _fluff(page, context):
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
    # The filler booster deduction is a list dependent
    # limb at SEAM-LISTS and is not built here.
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
    outcomes["fluff"] = (*_fluff(page, context), [], {})
    # The superlative hit limb stands at SEAM-LISTS and is
    # not built here, so the list independent form of the
    # check earns full credit with no hit counted.
    outcomes["unproven_superlatives"] = (1.0, "SUP_OK", [], {})

    results = []
    for check_id, weight, evidence_class in CHECK_REGISTRY:
        earned, reason, spans, counts = outcomes[check_id]
        applicable = True
        if check_id == "description_consistency" and not facts.get(
            "is_product_page", True
        ):
            applicable = False
        result = {
            "check_id": check_id,
            "weight": weight,
            "earned": _round3(earned),
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
    }
    if not applicable or applicable_weight == 0:
        # SEAM-SCORE-EMPTY: the empty case carries the
        # stated absence form, not an invented number.
        score["value"] = None
        score["band"] = None
        return score
    weighted = sum(
        (_get(result, "earned", 0) or 0)
        * (_get(result, "weight", 0) or 0)
        for result in applicable
    )
    value = round(weighted / applicable_weight * 100.0, 1)
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
    score["value"] = value
    if value >= 80:
        score["band"] = "strong"
    elif value >= 60:
        score["band"] = "developing"
    elif value >= 40:
        score["band"] = "thin"
    else:
        score["band"] = "poor"
    return score
