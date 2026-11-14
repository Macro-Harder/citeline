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


def _word_tokens(text):
    normalised = unicodedata.normalize("NFC", text or "").casefold()
    return re.findall(r"[^\W_]+", normalised, flags=re.UNICODE)


def _contains_term(sentence, term):
    # The matching form the brief states for its shipped
    # lists: case insensitive over word tokens, words as
    # alphanumeric tokens, a hyphenated form counting as
    # its parts, and a multi word entry matching as a
    # consecutive token sequence.
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
    terms.extend(aliases or [])
    terms.extend(category_terms or [])
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
    # The Section 5.7 earning rules: a token inside a
    # quoted span, a date fragment, and a version string
    # do not count, and a year between 1900 and 2099
    # standing alone does not count.
    masked = sentence
    masked = _mask_spans(masked, [
        (match.start(), match.end())
        for match in re.finditer(r'"[^"\n]*"', masked)
    ])
    masked = _mask_spans(masked, [
        (match.start(), match.end())
        for match in re.finditer(r"\b\d{4}-\d{2}-\d{2}\b", masked)
    ])
    masked = _mask_spans(masked, [
        (match.start(), match.end())
        for match in re.finditer(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", masked)
    ])
    masked = _mask_spans(masked, [
        (match.start(), match.end())
        for match in re.finditer(
            r"\b(?:" + _MONTH_NAME_PATTERN
            + r")\s+\d{1,2},\s+\d{4}\b", masked)
    ])
    masked = _mask_spans(masked, [
        (match.start(), match.end())
        for match in re.finditer(r"\b\d+(?:\.\d+){2,}\b", masked)
    ])
    masked = _mask_spans(masked, [
        (match.start(), match.end())
        for match in re.finditer(
            r"\bversion\s+\d+(?:\.\d+)+\b", masked, re.IGNORECASE)
    ])
    for match in _STATISTIC_PATTERN.finditer(masked):
        plain = match.group("token").strip()
        if re.fullmatch(r"\d{4}", plain):
            if 1900 <= int(plain) <= 2099:
                continue
        return True
    return False


def _has_attributed_quoted_span(sentence):
    # A quoted span of at least four words, with one of
    # the closed attribution cues in the window after it:
    # said, according to, or a capitalised name standing
    # inside the window and not at the start of a new
    # sentence.
    for match in re.finditer(r'"([^"\n]*)"', sentence):
        if len(match.group(1).split()) < 4:
            continue
        window = sentence[match.end():match.end() + 100]
        if re.search(r"(?<![A-Za-z])said(?![A-Za-z])", window,
                     re.IGNORECASE):
            return True
        if re.search(r"according\s+to", window, re.IGNORECASE):
            return True
        for name_match in re.finditer(r"\b[A-Z][a-z]+\b", window):
            before = window[:name_match.start()].rstrip()
            if not before or before.endswith((".", "!", "?")):
                continue
            return True
    return False


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


def choose_evidence_sentence(sentences, product_name=None, aliases=(),
                             category_terms=()):
    """Choose the draft evidence sentence, in extracted order.

    Preference: the first quotable evidence sentence that
    passes the naming test. Fallback: the first quotable
    evidence sentence in extracted order. Where a caller
    supplies pre filtered evidence sentences, quotability
    stands as supplied and only the ordering runs here.
    """
    candidates = list(sentences or [])
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


def _cited_count_phrase(distinct_cited_target_count):
    if distinct_cited_target_count is None:
        return "the distinct cited target count stands in the audit record"
    return (
        "the distinct cited target count stands at %s"
        % distinct_cited_target_count)


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
    if canonical_line is None:
        canonical_line = _get(record, "canonical_line", "") or ""
    if product_name is None:
        product_name = _get(record, "product_name", None) or _get(record, "name", None)
    run_id = _get(record, "run_id", None)
    product_id = _get(record, "product_id", None)
    if audit_date is None:
        audit_date = _get(record, "audit_date", None)

    if distinct_cited_target_count is None:
        distinct_cited_target_count = _get(
            record, "distinct_cited_target_count", None
        )
    if distinct_cited_target_count is None:
        cited_targets = _get(record, "cited_targets", None)
        if cited_targets is not None:
            distinct_cited_target_count = len(set(cited_targets))

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

    if cap_operates is None:
        score = _get(record, "score", None)
        cap_status = _get(score, "cap_status", None) if score is not None else None
        if cap_status is None:
            cap_status = _get(record, "cap_status", None)
        cap_operates = bool(cap_status)

    if evidence_sentences is not None:
        quotable = list(evidence_sentences)
    elif sentences is not None:
        quotable = [
            sentence for sentence in sentences
            if is_quotable_evidence_sentence(sentence)
        ]
    else:
        stored = _get(record, "evidence_sentences", None)
        if stored is not None:
            quotable = list(stored)
        else:
            stored_sentences = _get(record, "sentences", None) or []
            quotable = [
                sentence for sentence in stored_sentences
                if is_quotable_evidence_sentence(sentence)
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
            return _cited_count_phrase(distinct_cited_target_count)
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
        triggers = []
        if not any_field("named"):
            triggers.append("NOT_NAMED")
        if not any_field("named_early"):
            triggers.append("NOT_NAMED_EARLY")
        if not any_field("cited"):
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
    if control_failed is False:
        control_failed = bool(_get(record, "control_failed", False))

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
        round_evidence = {
            "NOT_NAMED": "%d of %d answers in the round name the product"
            % (sum(1 for item in active if field_value(item, "named")),
               total),
            "NOT_NAMED_EARLY": (
                "%d of %d answers in the round name the product early"
                % (sum(1 for item in active
                       if field_value(item, "named_early")), total)),
            "NOT_CITED": "%d of %d answers in the round cite the product"
            % (sum(1 for item in active if field_value(item, "cited")),
               total),
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
