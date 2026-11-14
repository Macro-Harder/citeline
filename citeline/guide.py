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

CITATIONS_CHECK_CODES = {
    "FAIL_CITATIONS",
    "WARN_CITATIONS",
    "LOW_CITATIONS",
}

VERSION_KEYS = (
    "registry_version",
    "detector_version",
    "query_set_version",
    "lexicon_version",
    "ruleset_version",
    "crawler_table_version",
)


def _get(record, name, default=None):
    if record is None:
        return default
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def _contains_term(sentence, term):
    if not sentence or not term:
        return False
    haystack = unicodedata.normalize("NFC", sentence).casefold()
    needle = unicodedata.normalize("NFC", term).casefold()
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index < 0:
            return False
        before = haystack[index - 1] if index > 0 else ""
        after_pos = index + len(needle)
        after = haystack[after_pos] if after_pos < len(haystack) else ""
        if (before and (before.isalpha() or before.isdigit())) or (
            after and (after.isalpha() or after.isdigit())
        ):
            start = index + 1
            continue
        return True


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


def is_quotable_evidence_sentence(sentence):
    """Return True for a sentence carrying a stated figure.

    The reading taken here, recorded in the builder paper,
    is that a quotable evidence sentence in the pinning
    fixtures is a sentence carrying a numeric figure. The
    plan states the selection ordering over quotable
    evidence sentences and does not define quotability in
    the sections this slice was charged to read, so the
    service layer may supply pre filtered evidence
    sentences, which this module then uses as given.
    """
    if not sentence:
        return False
    return any(character.isdigit() for character in sentence)


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


def _action_text(code):
    return "Action recorded for trigger " + code + "."


def _make_action(code, input_source, source_id, cap_operates=False):
    if input_source == "probe_round":
        worklist_class = None
    elif cap_operates and code in CITATIONS_CHECK_CODES:
        worklist_class = "cap_first"
    else:
        worklist_class = "score_check"
    action = {
        "code": code,
        "text": _action_text(code),
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
    stamps = {}
    for key in VERSION_KEYS:
        value = _get(record, key, None)
        if value is not None:
            stamps[key] = value
    nested = _get(record, "version_stamps", None)
    if isinstance(nested, dict):
        for key in VERSION_KEYS:
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
    citation_only = not quotable and has_cited_targets and distinct_cited_target_count >= 2

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

    actions = [
        _make_action(code, "page_audit", run_id, cap_operates=cap_operates)
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

    actions = []
    if not control_failed:
        actions = [
            _make_action(code, "probe_round", source_round_id)
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
