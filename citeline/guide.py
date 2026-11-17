"""Guide for Citeline, slice S8.

This module owns GuideDraft, the closed trigger list and
draft rules, the worklist class derivation, and the draft
selection ordering. A guide draft is drafted from records:
one completed audit record or one completed round. This
module never rewrites a page and does not define the status
mapping it consumes. Reporting does not depend on this
module, so no guide call is needed for any report.

Dates are call inputs. No date is read from a clock here.
"""

import re
import unicodedata

FAIL_CODES = [
    "FAIL_CITATIONS",
    "FAIL_STATISTICS",
    "FAIL_QUOTATIONS",
    "FAIL_COMPARISON",
    "FAIL_FRESHNESS",
    "FAIL_DESCRIPTION",
    "FAIL_KEYWORD",
    "FAIL_FLUFF",
    "FAIL_SUPERLATIVES",
    "FAIL_ANSWER_FIRST",
]
WARN_CODES = ["WARN_" + code[len("FAIL_"):] for code in FAIL_CODES]

TRIGGER_CODES = tuple(
    FAIL_CODES
    + WARN_CODES
    + [
        "LOW_CITATIONS",
        "NO_REUSABLE_EVIDENCE",
        "CITATION_ONLY_NO_QUOTABLE_SENTENCE",
        "NOT_NAMED",
        "NOT_NAMED_EARLY",
        "NOT_CITED",
    ]
)

ROUND_TRIGGER_CODES = ("NOT_NAMED", "NOT_NAMED_EARLY", "NOT_CITED")

STANDING_ACTION = "ACT_THIRD_PARTY"

EVIDENCE_CHECK_CODES = {
    "FAIL_CITATIONS",
    "WARN_CITATIONS",
    "LOW_CITATIONS",
    "FAIL_STATISTICS",
    "WARN_STATISTICS",
    "FAIL_QUOTATIONS",
    "WARN_QUOTATIONS",
}

VERSION_KEYS = (
    "registry_version",
    "detector_version",
    "query_set_version",
    "lexicon_version",
    "ruleset_version",
    "crawler_table_version",
)

FIRST_IMPORT_STAMP_KEYS = (
    "registry_version_at_first_import",
    "detector_version_at_first_import",
)

STAMP_KEYS = VERSION_KEYS + FIRST_IMPORT_STAMP_KEYS


def _get(record, name, default=None):
    if record is None:
        return default
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


# The one word token form, in the same shape as the
# reporting module tokeniser: a number stands as one
# token whole, carrying its thousands separators in
# their groups, its decimal parts at every point it
# carries, and a letter suffix standing on its last
# part (Step 17 round 5 entry S17-R5-047). The form
# stands completed on the dressings the round 6 entry
# names, in the same shape as the reporting module: a
# suffix carrying a trailing digit, an exponent part,
# and an underscore grouping (Step 17 round 6 entry
# S17-R6-039). The form stands completed on the dressings
# the round 7 entry names, in the same shape as the
# reporting module: an apostrophe grouping, an underscore
# grouping inside the exponent part, and an underscore
# digit inside the letter suffix (Step 17 round 7 entry
# S17-R7-041), and on the composed suffix dressings of
# round 8, in the same shape as the reporting module
# (Step 17 round 8 entry S17-R8-022).
_WORD_TOKEN_PATTERN = (
    r"\d+(?:[,_']\d{3})*(?:\.\d+)*"
    r"(?:[eE][+-]?\d+(?:_\d+)*)?"
    r"(?:[^\W\d_]+[0-9]*(?:_\d+)*)*"
    r"|[^\W_]+(?:\.\d+)*")


def _word_tokens(text):
    # The same tokeniser form as the reporting module
    # states: a decimal number counts as one word under
    # brief Section 5.1, so a decimal point standing
    # between digits does not split the number it
    # stands in (Step 17 round 4 entry S17-R4-048, the
    # guide side pattern the reporting paper records).
    normalised = unicodedata.normalize("NFC", text or "").casefold()
    return re.findall(
        _WORD_TOKEN_PATTERN, normalised, flags=re.UNICODE)


def _contains_term(sentence, term):
    # The matching form the brief states for its shipped
    # lists: case insensitive over word tokens, words as
    # alphanumeric tokens, a hyphenated form counting as
    # its parts, and a multi word entry matching as a
    # consecutive token sequence. A term standing in no
    # string form stands as no term, in the guard form
    # the module states for its other collections, so no
    # raw error reaches the caller (Step 17 round 15
    # entry S17-R15-008). The sentence argument of the
    # same call stands under the same guard in the same
    # form: a sentence standing in no string form stands
    # as no sentence, so no raw error reaches the caller
    # of the naming test on that argument either (Step
    # 17 round 16 entry S17-R16-014).
    if not isinstance(term, str):
        return False
    if not isinstance(sentence, str):
        return False
    sentence_tokens = _word_tokens(sentence)
    term_tokens = _word_tokens(term)
    if not sentence_tokens or not term_tokens:
        return False
    width = len(term_tokens)
    return any(
        sentence_tokens[index:index + width] == term_tokens
        for index in range(len(sentence_tokens) - width + 1)
    )


def passes_naming_test(sentence, product_name=None, aliases=(), category_terms=()):
    """Return True where a sentence names the product.

    The test runs over the product name, its aliases, and
    its category terms. Where the category list stands
    empty, the test runs on the name and aliases only.
    """
    terms = []
    if product_name:
        terms.append(product_name)
    terms.extend(_term_collection(aliases))
    terms.extend(_term_collection(category_terms))
    return any(_contains_term(sentence, term) for term in terms)


_CITATION_TARGET_PATTERN = re.compile(
    r"https?://[^\s<>\"'()\[\]{}]+", re.IGNORECASE)
_MARKDOWN_TARGET_PATTERN = re.compile(r"\[([^\]]*)\]\([^)\s]+[^)]*\)")

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

_MONTH_NAME_PATTERN = (
    "January|February|March|April|May|June|July|August|"
    "September|October|November|December"
)


def _mask_spans(text, spans):
    chars = list(text)
    for start, end in spans:
        for index in range(max(start, 0), min(end, len(chars))):
            chars[index] = " "
    return "".join(chars)


def _has_citation_target(sentence):
    # A sentence containing a citation target: the target
    # stands inside a sentence, so words stand in the
    # sentence beside the target. A listing that holds
    # targets and no words is the citations standing
    # themselves, not a sentence containing one, which is
    # the distinction the citation only draft rule at
    # item 137 stands on.
    if not (_MARKDOWN_TARGET_PATTERN.search(sentence)
            or _CITATION_TARGET_PATTERN.search(sentence)):
        return False
    residual = _MARKDOWN_TARGET_PATTERN.sub(
        lambda match: " %s " % match.group(1), sentence)
    residual = _CITATION_TARGET_PATTERN.sub(" ", residual)
    return bool(_word_tokens(residual))


def _has_statistic_token(sentence):
    # The Section 5.7 earning rules stand in one place:
    # the checks module owns them, and this test reads
    # that computation over the sentence as a page of one
    # sentence, so the guide test and the checks can
    # never diverge into two copies of one rule.
    from citeline import checks as _checks
    analysis = _checks._statistic_analysis(
        {"running_text": sentence, "links": []})
    return bool(analysis.get("count"))


def _has_attributed_quoted_span(sentence):
    # The attributed quotation limb of the same earning
    # rules, read from the checks module computation on
    # the same one sentence page form.
    from citeline import checks as _checks
    analysis = _checks._quotation_analysis(
        {"running_text": sentence})
    return bool(analysis.get("attributed"))


def is_quotable_evidence_sentence(sentence):
    """Return True where a sentence is quotable evidence.

    Brief item 137 defines the term: a sentence of the
    extracted page text containing a citation target, a
    statistic token, or an attributed quoted span, under
    the Section 5.7 earning rules.
    """
    if not sentence:
        return False
    return (
        _has_citation_target(sentence)
        or _has_statistic_token(sentence)
        or _has_attributed_quoted_span(sentence)
    )


def _sentence_collection(value):
    """One sentence input in its collection form.

    A string value is one sentence, never its characters.
    A list or tuple stands as its items. Any other shape
    stands as no collection the draft can read.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _term_collection(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        # The items inside a term list stand under the
        # same form guard as the collection whole: a non
        # string item stands skipped, as a non string
        # sentence item stands skipped at the choosing
        # reading, so no raw error reaches the caller of
        # the naming test or of the draft (Step 17 round
        # 15 entry S17-R15-008).
        return [item for item in value if isinstance(item, str)]
    return []


def choose_evidence_sentence(sentences, product_name=None, aliases=(),
                             category_terms=()):
    """Choose the draft evidence sentence, in extracted order.

    Preference: the first quotable evidence sentence that
    passes the naming test. Fallback: the first quotable
    evidence sentence in extracted order. Every candidate
    stands under the quotable evidence test of item 137,
    however it reached this module: a supplied sentence
    that is not quotable evidence is no candidate at all.
    """
    candidates = [
        sentence for sentence in _sentence_collection(sentences)
        if isinstance(sentence, str)
        and is_quotable_evidence_sentence(sentence)
    ]
    if not candidates:
        return None
    for sentence in candidates:
        if passes_naming_test(sentence, product_name, aliases, category_terms):
            return sentence
    return candidates[0]


_CHECK_WORDS = {
    "CITATIONS": "citations check",
    "STATISTICS": "statistics check",
    "QUOTATIONS": "quotations check",
    "COMPARISON": "comparison check",
    "FRESHNESS": "freshness check",
    "DESCRIPTION": "description consistency check",
    "KEYWORD": "keyword stuffing check",
    "FLUFF": "fluff check",
    "SUPERLATIVES": "unproven superlatives check",
    "ANSWER_FIRST": "answer first check",
}

_CHECK_STEPS = {
    "CITATIONS": "add citation targets from a named source to the page",
    "STATISTICS": "add statistic figures from a named source to the page",
    "QUOTATIONS": "add quoted spans attributed to a named source to the page",
    "COMPARISON": "add comparison material that names its source to the page",
    "FRESHNESS": "show a current date on the page, drawn from a named source",
    "DESCRIPTION": (
        "make the page description match the product record, and name "
        "the source of any claim added"),
    "KEYWORD": "reduce repeated keyword phrasing so the page reads as plain prose",
    "FLUFF": "remove filler wording that names no source from the page",
    "SUPERLATIVES": (
        "remove superlative claims that name no source, or name the "
        "source that supports each one"),
    "ANSWER_FIRST": "move the direct answer to the reader question to the start of the page",
}

_STEM_BY_CHECK_ID = {
    "citations": "CITATIONS",
    "statistics": "STATISTICS",
    "quotations": "QUOTATIONS",
    "comparison": "COMPARISON",
    "freshness": "FRESHNESS",
    "description_consistency": "DESCRIPTION",
    "keyword_stuffing": "KEYWORD",
    "fluff": "FLUFF",
    "unproven_superlatives": "SUPERLATIVES",
    "answer_first": "ANSWER_FIRST",
}

_ROUND_TEXTS = {
    "NOT_NAMED": (
        "no answer in the round names the product",
        "add the product name or an alias from the product record to "
        "the page opening"),
    "NOT_NAMED_EARLY": (
        "no answer in the round names the product early",
        "place the product name or an alias from the product record "
        "near the start of the page"),
    "NOT_CITED": (
        "no answer in the round cites the product",
        "add a citation target from a named source to the page"),
}


def _check_result_for(record, stem):
    checks = _get(record, "checks", None) or []
    for result in checks:
        check_id = str(_get(result, "check_id", "") or "")
        if _STEM_BY_CHECK_ID.get(check_id) == stem:
            return result
    return None


def _check_evidence_phrase(result):
    if result is None:
        return "the audit record shows this outcome"
    parts = []
    counts = _get(result, "detail_counts", None)
    if isinstance(counts, dict):
        for key, value in counts.items():
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                parts.append(
                    "%s stands at %s"
                    % (str(key).replace("_", " "), value))
    earned = _get(result, "earned", None)
    weight = _get(result, "weight", None)
    if earned is not None and weight is not None:
        parts.append("the check earned %s of %s" % (earned, weight))
    if parts:
        return "; ".join(parts)
    return "the audit record shows this outcome"


def _cited_count_phrase(distinct_cited_target_count,
                        record=None):
    if distinct_cited_target_count is None:
        return "the distinct cited target count stands in the audit record"
    phrase = (
        "the distinct cited target count stands at %s"
        % distinct_cited_target_count)
    # Where the count stands at 0 because the audit record
    # citations check carries the self only reason, the
    # phrase states that reason beside the count: the page
    # targets point at the product own domain, so the count
    # of outside targets stands at 0 (Step 19 register
    # entry R19-060).
    if distinct_cited_target_count == 0 and record is not None:
        for result in _get(record, "checks", None) or []:
            if str(_get(result, "check_id", "") or "") == \
                    "citations" and \
                    _get(result, "reason_code", None) == \
                    "CIT_SELF_ONLY":
                return (
                    phrase + ", because every citation "
                    "target on the page points at the "
                    "product own domain and no target "
                    "stands outside it")
    return phrase


def _action_text(code, evidence=None):
    # One plain sentence per action, on the brief item 137
    # rendering rule: the check or round outcome that
    # produced the action named in words, the evidence
    # that produced it, and the next step at signal level,
    # with a named source where guard G6 requires one. No
    # text here presents a step as a promised result.
    if code.startswith("FAIL_") or code.startswith("WARN_"):
        stem = code[len("FAIL_"):] if code.startswith("FAIL_") \
            else code[len("WARN_"):]
        words = _CHECK_WORDS.get(stem, "page check")
        step = _CHECK_STEPS.get(
            stem, "revise the page on this check, naming the source "
            "of any evidence added")
        outcome = "failed" if code.startswith("FAIL_") else "gave a warning"
        return (
            "The %s %s on the page, on this evidence: %s; the next "
            "step is to %s." % (words, outcome, evidence or
                                "the audit record shows this outcome",
                                step))
    if code == "LOW_CITATIONS":
        return (
            "The page carries too few citations, on this evidence: "
            "%s, under the threshold of 2; the next step is to add "
            "citation targets from a named source to the page."
            % (evidence or _cited_count_phrase(None)))
    if code == "CITATION_ONLY_NO_QUOTABLE_SENTENCE":
        return (
            "Citations stand on the page and no quotable evidence "
            "sentence stands, on this evidence: %s; the next step "
            "is to add a quotable evidence sentence from a named "
            "source, a sentence carrying a citation target, a "
            "statistic figure, or an attributed quoted span."
            % (evidence or _cited_count_phrase(None)))
    if code == "NO_REUSABLE_EVIDENCE":
        return (
            "No reusable evidence stands on the page, on this "
            "evidence: no citation target, statistic figure, or "
            "attributed quoted span stands in the record; the next "
            "step is to add evidence of one of those kinds from a "
            "named source to the page.")
    if code in _ROUND_TEXTS:
        outcome_words, step = _ROUND_TEXTS[code]
        return (
            "In this round, %s, on this evidence: %s; the next step "
            "is to %s." % (outcome_words, evidence or
                           "the round record shows this outcome", step))
    return (
        "The guide records this outcome, on this evidence: %s; the "
        "next step is to revise the page at signal level, naming "
        "the source of any evidence added."
        % (evidence or "the record shows this outcome"))


def _make_action(code, input_source, source_id, cap_operates=False,
                 evidence=None):
    if input_source == "probe_round":
        worklist_class = None
    elif cap_operates and code in EVIDENCE_CHECK_CODES:
        worklist_class = "cap_first"
    else:
        worklist_class = "score_check"
    action = {
        "code": code,
        "text": _action_text(code, evidence=evidence),
        "input_source": input_source,
        "check_or_outcome": code,
        "worklist_class": worklist_class,
    }
    if input_source == "page_audit":
        action["page_audit"] = source_id
    else:
        action["probe_round"] = source_id
    return action


def _stamps_from(record):
    # The draft carries the version stamps the input record
    # carries, as it carries them: the six flat version keys,
    # and the round record stamps under the names the Round
    # shape states, registry_version_at_first_import and
    # detector_version_at_first_import.
    stamps = {}
    for key in STAMP_KEYS:
        value = _get(record, key, None)
        if value is not None:
            stamps[key] = value
    nested = _get(record, "version_stamps", None)
    if isinstance(nested, dict):
        for key in STAMP_KEYS:
            if key not in stamps and nested.get(key) is not None:
                stamps[key] = nested[key]
    return stamps


def draft_from_audit_record(record, canonical_line=None, audit_date=None,
                            product_name=None, aliases=(),
                            category_terms=(), sentences=None,
                            evidence_sentences=None,
                            distinct_cited_target_count=None,
                            trigger_codes=(), cap_operates=None):
    """Draft a GuideDraft from one completed audit record.

    The record supplies provenance, product, stamps, and
    the audit date it carries, unless a call input states
    them. Trigger codes stand as consumed from the record
    or the caller, never derived from a status mapping
    defined here. FAIL_ and WARN_ codes in the closed list
    pass through as actions on those terms.

    Draft rules, on the brief items this slice owns:
    a page with no firing trigger returns the canonical
    line alone, with an empty action list, not a refusal.
    A page with a firing trigger and a quotable evidence
    sentence returns the canonical line plus the chosen
    sentence, attributed as the page gives it, with no
    joining space invented beyond one space between the
    two sentences as the page tests state the form.
    A citation only page, with cited targets standing but
    no quotable sentence, returns the canonical line alone
    and records CITATION_ONLY_NO_QUOTABLE_SENTENCE.
    A page with no reusable evidence refuses with
    NO_REUSABLE_EVIDENCE, a null opening text, and an
    action list that still stands produced.
    """
    # The draft stands on the run as stored: where the
    # record itself carries the canonical line or the
    # product name, those stored values govern, and a
    # caller supplied value stands only where the record
    # carries none. A draft assembled from a later
    # registry state over an earlier run would stand on
    # no page and in no record.
    stored_line = _get(record, "canonical_line", None)
    if stored_line:
        canonical_line = stored_line
    elif canonical_line is None:
        canonical_line = ""
    stored_name = _get(record, "product_name", None) or _get(
        record, "name", None)
    if stored_name:
        product_name = stored_name
    # The selection inputs of a draft from a stored run
    # stand on the stored record: the aliases and category
    # terms the record itself carries govern, and where a
    # stored run carries none, a caller supplied list
    # drawn from a later registry state does not enter
    # the draft. A record carrying no run identity is a
    # direct draft input, and caller values stand for it
    # as they stand for the canonical line.
    stored_aliases = _get(record, "aliases", None)
    if stored_aliases is not None:
        aliases = _term_collection(stored_aliases)
    elif _get(record, "run_id", None):
        aliases = ()
    stored_terms = _get(record, "category_terms", None)
    if stored_terms is None:
        stored_terms = _get(record, "category", None)
    if stored_terms is not None:
        category_terms = _term_collection(stored_terms)
    elif _get(record, "run_id", None):
        category_terms = ()
    run_id = _get(record, "run_id", None)
    product_id = _get(record, "product_id", None)
    if audit_date is None:
        audit_date = _get(record, "audit_date", None)

    if distinct_cited_target_count is None:
        distinct_cited_target_count = _get(
            record, "distinct_cited_target_count", None
        )
    # The count stands judged for form before it stands
    # compared: a count standing in string form stands
    # read as the whole number it writes, and a string
    # standing in no such form stands as no count, so no
    # raw comparison error reaches the caller (Step 17
    # round 7 entry S17-R7-043).
    if isinstance(distinct_cited_target_count, bool):
        distinct_cited_target_count = None
    elif isinstance(distinct_cited_target_count, str):
        written = distinct_cited_target_count.strip()
        if written.isascii() and written.isdigit():
            distinct_cited_target_count = int(written)
        else:
            distinct_cited_target_count = None
    elif distinct_cited_target_count is not None and not isinstance(
            distinct_cited_target_count, int):
        distinct_cited_target_count = None
    if distinct_cited_target_count is None:
        cited_targets = _get(record, "cited_targets", None)
        if cited_targets is not None:
            # The cited targets stand read under the
            # module collection discipline: a string value
            # is one item, never its characters, and a
            # list or tuple stands as its items (Step 17
            # round 7 entry S17-R7-043).
            distinct_cited_target_count = len(set(
                _term_collection(cited_targets)))

    triggers = []
    for code in trigger_codes or []:
        if code in TRIGGER_CODES and code not in triggers:
            triggers.append(code)
    recorded_triggers = _get(record, "trigger_codes", None) or _get(
        record, "triggers", None
    )
    for code in recorded_triggers or []:
        if code in TRIGGER_CODES and code not in triggers:
            triggers.append(code)
    if not triggers:
        # A check that earned nothing stands failed in
        # plain words: its FAIL_ trigger fires from the
        # stored check result itself, so the draft
        # selection rule of item 137 can run on a page
        # whose checks earned nothing on a named check.
        # No threshold for partial earnings stands
        # derived here: the earned value to status
        # mapping for a partial earning stands unruled
        # (CL-16), and a not applicable check fires
        # nothing (Step 19 queue addition U-05).
        for result in _get(record, "checks", None) or []:
            earned = _get(result, "earned", None)
            if earned is None or isinstance(earned, bool):
                continue
            if _get(result, "status", None) == "not_applicable":
                continue
            if earned != 0:
                continue
            stem = _STEM_BY_CHECK_ID.get(
                str(_get(result, "check_id", "") or ""))
            if stem is not None:
                code = "FAIL_" + stem
                if code not in triggers:
                    triggers.append(code)

    if cap_operates is None:
        score = _get(record, "score", None)
        cap_status = _get(score, "cap_status", None) if score is not None else None
        if cap_status is None:
            cap_status = _get(record, "cap_status", None)
        cap_operates = bool(cap_status)

    if evidence_sentences is not None:
        quotable = [
            sentence for sentence in _sentence_collection(
                evidence_sentences)
            if isinstance(sentence, str)
            and is_quotable_evidence_sentence(sentence)
        ]
    elif sentences is not None:
        quotable = [
            sentence for sentence in _sentence_collection(sentences)
            if isinstance(sentence, str)
            and is_quotable_evidence_sentence(sentence)
        ]
    else:
        stored = _get(record, "evidence_sentences", None)
        if stored is not None:
            quotable = [
                sentence for sentence in _sentence_collection(stored)
                if isinstance(sentence, str)
                and is_quotable_evidence_sentence(sentence)
            ]
        else:
            stored_sentences = _get(record, "sentences", None) or []
            quotable = [
                sentence for sentence in _sentence_collection(
                    stored_sentences)
                if isinstance(sentence, str)
                and is_quotable_evidence_sentence(sentence)
            ]

    low_citations = (
        distinct_cited_target_count is not None
        and distinct_cited_target_count < 2
    )
    if low_citations and "LOW_CITATIONS" not in triggers:
        triggers.append("LOW_CITATIONS")

    has_cited_targets = bool(
        distinct_cited_target_count and distinct_cited_target_count > 0
    )
    citation_only = not quotable and has_cited_targets

    refused = False
    refusal_code = None
    opening_text = None
    selection_basis = None
    codes_for_actions = list(triggers)

    if not quotable and not has_cited_targets:
        refused = True
        refusal_code = "NO_REUSABLE_EVIDENCE"
        opening_text = None
        if "NO_REUSABLE_EVIDENCE" not in codes_for_actions:
            codes_for_actions.append("NO_REUSABLE_EVIDENCE")
    elif citation_only:
        opening_text = canonical_line
        if "CITATION_ONLY_NO_QUOTABLE_SENTENCE" not in codes_for_actions:
            codes_for_actions.append("CITATION_ONLY_NO_QUOTABLE_SENTENCE")
    elif not triggers and not low_citations:
        opening_text = canonical_line
        codes_for_actions = []
    elif quotable:
        chosen = choose_evidence_sentence(
            quotable, product_name, aliases, category_terms
        )
        if chosen:
            opening_text = canonical_line + " " + chosen
            # The draft records the basis its selection
            # stood on, in the form the reporting limb
            # reads, so the fixed selection statement of
            # the IM7-BRK-13 landing prints in every form.
            if passes_naming_test(
                    chosen, product_name, aliases,
                    category_terms):
                selection_basis = "preference"
            else:
                selection_basis = "fallback"
        else:
            opening_text = canonical_line
    else:
        opening_text = canonical_line

    def evidence_for(code):
        if code.startswith("FAIL_") or code.startswith("WARN_"):
            return _check_evidence_phrase(
                _check_result_for(record, code[5:]))
        if code in ("LOW_CITATIONS",
                    "CITATION_ONLY_NO_QUOTABLE_SENTENCE"):
            return _cited_count_phrase(
                distinct_cited_target_count, record)
        return None

    actions = [
        _make_action(code, "page_audit", run_id,
                     cap_operates=cap_operates,
                     evidence=evidence_for(code))
        for code in codes_for_actions
    ]

    draft = {
        "provenance": "page_audit",
        "source_run_id": run_id,
        "source_round_id": None,
        "product_id": product_id,
        "opening_text": opening_text,
        "refused": refused,
        "refusal_code": refusal_code,
        "actions": actions,
        "standing_action": STANDING_ACTION,
        "audit_date": audit_date,
    }
    if selection_basis is not None:
        draft["selection_basis"] = selection_basis
    # The run's own cap position stands on the draft, so
    # the guide artefact can state it in the audit's words
    # beside the worklist groups.
    draft["cap_status"] = bool(cap_operates)
    draft.update(_stamps_from(record))
    return draft


def compute_round_triggers(answers=None, round_metrics=None):
    """Compute the three round triggers over non control answers.

    The guide consumes no control as evidence, so round
    triggers compute over the round non control answers
    only. Where round metrics stand supplied instead, the
    named, named early, and cited rates of that computation
    govern, a null or zero rate firing its trigger.
    """
    if answers is not None:
        answers = list(answers)
        active = []
        for item in answers or []:
            control = False
            if isinstance(item, dict):
                control = bool(item.get("control") or item.get("control_flag"))
            else:
                control = bool(
                    getattr(item, "control", False)
                    or getattr(item, "control_flag", False)
                )
            if not control:
                active.append(item)
        def any_field(name):
            for item in active:
                if isinstance(item, dict):
                    if item.get(name):
                        return True
                elif getattr(item, name, False):
                    return True
            return False

        def any_cited():
            # An answer stands cited for the round trigger
            # where it holds at least one citation instance,
            # the gross reading the brief states for a citing
            # answer, as well as where its cited outcome for
            # the product domain stands (Step 19 queue
            # addition U-06).
            for item in active:
                if isinstance(item, dict):
                    if item.get("cited"):
                        return True
                    instances = item.get("citation_instances")
                    if instances is None:
                        instances = item.get("citation_instance_count")
                    if instances:
                        return True
                else:
                    if getattr(item, "cited", False):
                        return True
                    instances = getattr(
                        item, "citation_instances", None)
                    if instances is None:
                        instances = getattr(
                            item, "citation_instance_count", None)
                    if instances:
                        return True
            return False
        triggers = []
        if not any_field("named"):
            triggers.append("NOT_NAMED")
        if not any_field("named_early"):
            triggers.append("NOT_NAMED_EARLY")
        if not any_cited():
            triggers.append("NOT_CITED")
        return triggers
    rates = _get(round_metrics, "rates", None) or {}
    def rate_of(name):
        block = rates.get(name) if isinstance(rates, dict) else _get(rates, name, None)
        if block is None:
            return None
        return block.get("rate") if isinstance(block, dict) else _get(block, "rate", None)
    triggers = []
    if not rate_of("named"):
        triggers.append("NOT_NAMED")
    if not rate_of("named_early"):
        triggers.append("NOT_NAMED_EARLY")
    cited_rate = rate_of("cited")
    if cited_rate is None:
        cited_rate = _get(round_metrics, "cited_rate_gross", None)
    if not cited_rate:
        triggers.append("NOT_CITED")
    return triggers


_FAILED_CONTROL_COMPONENTS = (
    ("control", "failed"), ("control", "failure"),
    ("control", "flag"))


def _record_states_failed_control(record):
    # The draft suppression reading stands on the same
    # terms the rendering pass judges, as the reporting
    # module states the shared reading in its own text:
    # the flag stands judged by truthiness, and the three
    # flag names stand judged as the same failed control
    # under the component reading that module states for
    # field names, so a case shifted, camel, separator, or
    # doubled separator form of one of those names states
    # the failed control as the exact name does, at the
    # top level and at any depth, over the walked objects
    # (Step 17 round 5 entry S17-R5-043, round 6 entry
    # S17-R6-037, round 7 entry S17-R7-039, and round 15
    # entry S17-R15-007). The component reading itself
    # stands read from the reporting module, so the two
    # readings stand as one reading and not as two copies.
    # The field set the walk judges on an attribute
    # carrying record stands on the rendering conversion
    # terms of that module, in its own order: a record
    # carrying an _asdict form stands judged on the
    # fields that form states, in place of its object
    # dict, and an object dict stands judged on its
    # public attribute names only, a private attribute
    # name and everything held under it standing dropped
    # as the conversion drops them, so a record states a
    # failed control at the draft exactly where it states
    # one at the rendering (Step 17 round 16 entries
    # S17-R16-012 and S17-R16-013). A plain record stands
    # judged on its member names as written, in the
    # standing form: the conversion drops private names
    # on object records only.
    # The walk stands on the conversion terms whole, in
    # the order that module states them. A value the
    # conversion passes through as a scalar, standing as
    # a bool, an int, a float, or a str, states nothing
    # past itself: a str, int, or float subclass carrier
    # stands judged on that pass, its public attributes
    # and its _asdict form standing in no part judged
    # (Step 17 round 17 entry S17-R17-006). A mapping
    # returned by an _asdict form stands judged on its
    # items, in whatever mapping form it stands, dict or
    # not, as the conversion reads it (Step 17 round 17
    # entry S17-R17-007). And the value standing under a
    # flag name stands judged on its converted form, as
    # the conversion states it, not on its raw form: a
    # non finite float or Decimal standing as no figure,
    # and an attribute carrying value standing as the
    # plain form of its public fields, empty where it
    # carries none (Step 17 round 17 entry S17-R17-008).
    # The conversion itself stands read from the
    # reporting module, so the two readings stand as one
    # reading on the value as on the field set.
    from citeline import reporting

    def walk(node):
        if isinstance(node, dict):
            yield node
            for item in node.values():
                yield from walk(item)
        elif isinstance(node, (list, tuple)):
            for item in node:
                yield from walk(item)
        elif isinstance(node, (bool, int, float, str)):
            return
        elif hasattr(node, "_asdict"):
            returned = node._asdict()
            if hasattr(returned, "items"):
                yield from walk(dict(returned.items()))
            else:
                yield from walk(returned)
        elif hasattr(node, "__dict__"):
            yield from walk({
                key: item for key, item in vars(node).items()
                if not key.startswith("_")})

    for obj in walk(record):
        for key, value in obj.items():
            if tuple(reporting._key_components(key)) in \
                    _FAILED_CONTROL_COMPONENTS \
                    and reporting._plain(value):
                return True
    return False


def draft_from_round(round_record=None, canonical_line=None, audit_date=None,
                     answers=None, round_metrics=None, trigger_codes=None,
                     control_failed=False, source_round_id=None,
                     product_id=None):
    """Draft a GuideDraft from one completed round.

    A firing round trigger gives the canonical line alone,
    refused false, and a null refusal code. A round with no
    firing trigger gives the same opening with an empty
    action list. Round actions carry no worklist class.
    A round holding a failed control produces no action
    from that round, and the draft carries a control
    failure notice field stating that standing.
    """
    record = round_record or {}
    # The answers input stands materialised once, in the
    # form the triggers compute on, so every later reading
    # in this draft, the empty round notice included,
    # derives from that same basis and no second reading
    # of a one pass input can state a different round.
    if answers is not None:
        answers = list(answers)
    if canonical_line is None:
        canonical_line = _get(record, "canonical_line", "") or ""
    if source_round_id is None:
        source_round_id = (
            _get(record, "source_round_id", None)
            or _get(record, "round_id", None)
            or _get(record, "round_label", None)
        )
    if product_id is None:
        product_id = _get(record, "product_id", None)
    if audit_date is None:
        audit_date = _get(record, "audit_date", None)
    control_failed = bool(control_failed) or \
        _record_states_failed_control(record)
    if not control_failed and answers is not None:
        # The failed control state also stands in the
        # round's own control answers: a control whose
        # outcome contradicts its asserted kind, a
        # positive control standing not named or not
        # cited, or a negative control standing named or
        # cited, under the IM7-ANA-2 landing (Step 19
        # queue addition U-04).
        for item in answers:
            if isinstance(item, dict):
                is_ctl = bool(item.get("control")
                              or item.get("control_flag"))
                kind = item.get("control_kind")
                named = bool(item.get("named"))
                cited = bool(item.get("cited")) or bool(
                    item.get("citation_instances")
                    or item.get("citation_instance_count"))
            else:
                is_ctl = bool(getattr(item, "control", False)
                              or getattr(item, "control_flag", False))
                kind = getattr(item, "control_kind", None)
                named = bool(getattr(item, "named", False))
                cited = bool(getattr(item, "cited", False)) or bool(
                    getattr(item, "citation_instances", None)
                    or getattr(item, "citation_instance_count", None))
            if not is_ctl:
                continue
            if kind == "positive" and not (named and cited):
                control_failed = True
            elif kind == "negative" and (named or cited):
                control_failed = True

    if control_failed:
        triggers = []
    elif trigger_codes is not None:
        triggers = [code for code in trigger_codes if code in ROUND_TRIGGER_CODES]
    else:
        triggers = compute_round_triggers(
            answers=answers, round_metrics=round_metrics
        )

    def is_control(item):
        if isinstance(item, dict):
            return bool(item.get("control") or item.get("control_flag"))
        return bool(
            getattr(item, "control", False)
            or getattr(item, "control_flag", False))

    def field_value(item, name):
        if isinstance(item, dict):
            return item.get(name)
        return getattr(item, name, False)

    round_evidence = {}
    if answers is not None:
        active = [item for item in (answers or []) if not is_control(item)]
        total = len(active)
        # The round contents stand stated from the stored
        # record, control answers counted as answers: where
        # the round holds control answers beside its sampled
        # answers, or instead of them, the evidence phrases
        # say so, and no phrase states the round as empty
        # while controls stand in it (Step 19 register
        # entry R19-086).
        control_total = len(answers or []) - total
        if control_total:
            control_clause = (
                "; the round holds %d control answer%s "
                "beside them, counted as answers in the "
                "round and consumed as controls, not as "
                "evidence"
                % (control_total,
                   "" if control_total == 1 else "s"))
        else:
            control_clause = ""

        def stands_cited(item):
            if field_value(item, "cited"):
                return True
            instances = field_value(item, "citation_instances")
            if instances is None:
                instances = field_value(item, "citation_instance_count")
            return bool(instances)
        noun = "sampled answers" if control_total else "answers"
        round_evidence = {
            "NOT_NAMED": "%d of %d %s in the round name the product%s"
            % (sum(1 for item in active if field_value(item, "named")),
               total, noun, control_clause),
            "NOT_NAMED_EARLY": (
                "%d of %d %s in the round name the product early%s"
                % (sum(1 for item in active
                       if field_value(item, "named_early")), total,
                   noun, control_clause)),
            "NOT_CITED": "%d of %d %s in the round cite the product%s"
            % (sum(1 for item in active if stands_cited(item)),
               total, noun, control_clause),
        }
    elif round_metrics is not None:
        rates = _get(round_metrics, "rates", None) or {}
        block_names = {
            "NOT_NAMED": ("named", "name the product"),
            "NOT_NAMED_EARLY": ("named_early", "name the product early"),
            "NOT_CITED": ("cited", "cite the product"),
        }
        for code, (block_name, phrase) in block_names.items():
            block = rates.get(block_name) if isinstance(rates, dict) \
                else _get(rates, block_name, None)
            if block is None:
                continue
            count = _get(block, "count", None)
            total = _get(block, "n", None)
            if count is not None and total is not None:
                round_evidence[code] = (
                    "%s of %s answers in the round %s"
                    % (count, total, phrase))

    actions = []
    if not control_failed:
        actions = [
            _make_action(code, "probe_round", source_round_id,
                         evidence=round_evidence.get(code))
            for code in triggers
        ]

    draft = {
        "provenance": "probe_round",
        "source_run_id": None,
        "source_round_id": source_round_id,
        "product_id": product_id,
        "opening_text": canonical_line,
        "refused": False,
        "refusal_code": None,
        "actions": actions,
        "standing_action": STANDING_ACTION,
        "audit_date": audit_date,
    }
    if control_failed:
        draft["control_failure_notice"] = (
            "a control in this round failed, and no action "
            "stands produced from this round"
        )
    empty_basis = False
    controls_only = 0
    if answers is not None:
        non_control = [
            item for item in (answers or [])
            if not is_control(item)]
        empty_basis = not (answers or [])
        if not non_control and (answers or []):
            # The round holds answers, every one a control
            # answer: the notice states those contents, and
            # never states the round holds no answers
            # (Step 19 register entry R19-086).
            controls_only = len(answers or [])
    elif round_metrics is not None:
        # A round supplied as metrics alone states its
        # basis in the rates the triggers computed on:
        # where every rate block stands at zero of zero,
        # that basis holds no answer, and the notice
        # derives from it in the same words.
        rates = _get(round_metrics, "rates", None) or {}
        totals = []
        if isinstance(rates, dict):
            for block in rates.values():
                total = _get(block, "n", None)
                if total is not None:
                    totals.append(total)
        empty_basis = bool(totals) and all(
            total == 0 for total in totals)
    if controls_only:
        draft["empty_round_notice"] = (
            "This round holds %d answers, every one a "
            "control answer, so the actions in this "
            "draft rest on no sampled answer in the "
            "round." % controls_only)
    elif empty_basis:
        # The round holds no answers: the draft states
        # that empty basis in plain words on its own
        # face, so no action in it reads as a finding
        # on evidence the round does not hold.
        draft["empty_round_notice"] = (
            "This round holds no answers, so the "
            "actions in this draft rest on no answer "
            "in the round.")
    draft.update(_stamps_from(record))
    return draft


def build_guide_draft(record=None, **kwargs):
    """Draft a GuideDraft from an audit record or a round.

    Dispatch stands on the input form: a record carrying a
    run_id, or an explicit input_source of page_audit, goes
    to the audit draft. Any other form goes to the round
    draft. The service layer states which form it calls.
    """
    input_source = kwargs.pop("input_source", None)
    if input_source == "page_audit" or (
        input_source is None
        and record is not None
        and _get(record, "run_id", None)
    ):
        return draft_from_audit_record(record, **kwargs)
    return draft_from_round(record, **kwargs)


# A short alias, stated for callers that name the operation
# by its product noun.
guide_draft = build_guide_draft
