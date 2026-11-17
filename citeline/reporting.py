"""Reporting: the one rendering pipeline and the artefacts it owns.

Reporting owns no stored shape. It renders ReportArtefact,
ProbeTrend, QuerySetReport, and RobotsPreview artefacts from
stored records, and, for a ReportArtefact, from supplied files
and standing records on the terms the plan states for that
artefact. It adds no number: every figure in an artefact is a
value the stored record already carries, or a fixed text the
plan states, or the one permitted rendering derivation (a stored
rate restated as a plain range in percent in the Simple form).
It depends on no guide module: a GuideDraft reaches this module
only as a stored record like any other, and renders the same
with no guide call made.

The three reading forms come from one canonical record through
this one pipeline. Simple is prose only. Advanced is the stored
report object as JSON data. Agentic wraps that same payload
under the one named report key, with the presence only scope
value standing as a field level property of any object that
carries a score, a rate, or a tier.

Escaping sits at the pipeline's one point, by field type. In the
JSON forms a text field stands exact as stored, because the JSON
encoding the caller applies is the escaping for that form, and
no second encoding is applied here. In the Simple form a text
field stands as plain text characters in prose. A numeric field
stays a number in the JSON forms, and a code field stays a
verbatim string.

Dates are call inputs and record fields only. Nothing in this
module reads a clock.

Real stored records arrive with caller carry folded around
them: an audit result the service layer hands over carries
the stored AuditRun under its own audit_run key, beside a
snapshot object the caller assembled, and may carry the
requested form name folded in by the home that returned it.
This pipeline renders the record as handed and drops no
field of it: the shell boundary check pins that formatting
adds no field of its own and removes none, so the carry
stands in the artefact exactly as it stands in the record,
and the questions its presence raises for the trace field
set stand recorded in this seat's fix paper, not settled by
dropping fields here.
"""

import copy
import math
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP

__all__ = [
    "HONESTY_SENTENCE",
    "ANCHOR_LIMIT_SENTENCE",
    "SCOPE_VALUE",
    "SCHEMA_STAMP",
    "AGENTIC_STATUS_OK",
    "THIRD_PARTY_SCOPE_LINE",
    "REFUSAL_SENTENCE",
    "CITATION_ONLY_SENTENCE",
    "FALLBACK_STATEMENT",
    "PREFERENCE_STATEMENT",
    "SMALL_SAMPLE_WARNING",
    "CONTROL_FAILURE_NOTICE",
    "EMPTY_ANSWER_WARNING",
    "GROUP_NO_ACTION_LINE",
    "render",
    "format_record",
    "bounds_for",
    "derive_query_set_report",
    "query_set_report",
    "assemble_robots_preview",
    "robots_preview",
]

HONESTY_SENTENCE = (
    "This score is a signal index. It measures the presence of "
    "citability signals. It is not validated as a predictor of "
    "citation, and it does not verify truth."
)

ANCHOR_LIMIT_SENTENCE = (
    "Verify proves internal consistency only. A writer who "
    "replaces the whole product home can replace the chain with "
    "it. Record the head hash outside the product home."
)

SCOPE_VALUE = "signal_presence_only"

# The Agentic envelope contract fields of brief Section 5.5
# item 122: the schema stamp naming the response schema and
# its version, and the status token a successful response
# carries. A failure response carries an error token from
# the closed vocabulary in the same status field, produced
# by the layer that raises the failure, before any rendering
# stands.
SCHEMA_STAMP = "citeline-agentic-1"
AGENTIC_STATUS_OK = "ok"

THIRD_PARTY_SCOPE_LINE = (
    "Third party mentions stand outside version 1 measurement, "
    "and no figure in this artefact speaks for them."
)

REFUSAL_SENTENCE = (
    "The guide drafts no opening for this page, because no "
    "reusable evidence stands on it."
)

CITATION_ONLY_SENTENCE = (
    "This page carries citations and no quotable evidence "
    "sentence, so the draft opening is the canonical line alone."
)

SMALL_SAMPLE_WARNING = (
    "Small sample warning: this rate may change as "
    "more answers are added."
)

CONTROL_FAILURE_NOTICE = (
    "Control failure notice: a control outcome in this "
    "round contradicts its asserted kind. The notice "
    "stands in its own form and is not a warning."
)

EMPTY_ANSWER_WARNING = (
    "Empty answer warning: %d answers in this round are "
    "empty, with no answer text."
)

GROUP_NO_ACTION_LINE = (
    "No action stands in this group for this run."
)

# The importer declaration in its three values in words, as
# brief Section 5.8 item 19 guard G1 states them, keyed by the
# stored code form. The Simple form states the declaration in
# these words, marked as asserted, because the declaration is
# operator asserted metadata; the Advanced code form carries
# the stored code unchanged.
DECLARATION_WORDS = {
    "all_captured": "all captured answers imported",
    "all_captured_answers_imported": "all captured answers imported",
    "all_captured_answers": "all captured answers imported",
    "all_answers_imported": "all captured answers imported",
    "operator": "all captured answers imported",
    "stated_subset": "a stated subset imported",
    "a_stated_subset": "a stated subset imported",
    "a_stated_subset_imported": "a stated subset imported",
    "stated_subset_imported": "a stated subset imported",
    "subset": "a stated subset imported",
    "selection_rule_unknown": "selection rule unknown",
    "unknown": "selection rule unknown",
}
DECLARATION_WORDS.update({
    "all captured answers imported": "all captured answers imported",
    "a stated subset imported": "a stated subset imported",
    "selection rule unknown": "selection rule unknown",
})

DECLARATION_UNVERIFIABLE_STATEMENT = (
    "The declaration is unverifiable by the tool."
)

# The basis statement of the secondary figure on the not
# applicable as zero basis, in the words the IM7-BRK-3
# landing and the stored figure object both carry.
SECONDARY_FIGURE_BASIS = (
    "Computed on a different basis from the headline "
    "score: the headline score is computed on the "
    "applicable checks with not applicable weight "
    "redistributed, and this figure is computed on the "
    "total weight of 100 with not applicable checks "
    "earning 0. Neither figure ranks against a score "
    "on another basis."
)

FALLBACK_STATEMENT = "The evidence sentence does not name the product."

PREFERENCE_STATEMENT = (
    "The draft opening uses the first quotable sentence that "
    "names the product, an alias, or a category term. It was "
    "chosen by naming only, and what it states is the page's own "
    "statement."
)

LABEL_CAP_FIRST = (
    "First: actions on citations, statistics, or quotations, "
    "while the evidence cap holds the score at 39. This is an "
    "order of work, not a promised result."
)

LABEL_SCORE_CHECK = (
    "Next: actions on the checks that earn the score, where the "
    "evidence cap does not hold. This is an order of work, not a "
    "promised result."
)

LABEL_DEFECT = (
    "Separate: actions on a defect that is not a score matter. "
    "This is an order of work, not a promised result."
)

TIER_CLAUSES = {
    "count only": (
        "count only means no rate is given, only the count "
        "of answers"),
    "exploratory": (
        "exploratory means a rate is shown as an early "
        "indication that carries little weight"),
    "provisional": (
        "provisional means a rate is shown as a working "
        "figure that may still change as more answers are "
        "added"),
    "reportable": (
        "reportable means a rate is shown as a figure that "
        "may be reported as the round's result, a statement "
        "of the presence found in the sampled answers and "
        "nothing more"),
}

TIER_CLAUSES_LINE = (
    "Tier clauses: count only means no rate is given, only "
    "the count of answers; exploratory means a rate is shown "
    "as an early indication that carries little weight; "
    "provisional means a rate is shown as a working figure "
    "that may still change as more answers are added; "
    "reportable means a rate is shown as a figure that may "
    "be reported as the round's result, a statement of the "
    "presence found in the sampled answers and nothing more."
)

CITED_RATE_DEFINITIONS_LINE = (
    "Cited figures: the cited rate counts the share of "
    "answers whose citations point at the product own "
    "domain; cited_rate_gross is the share of answers "
    "holding at least one citation instance of any kind, "
    "self citations included; cited_rate_net is the share "
    "holding at least one citation instance that is not a "
    "self citation; self_citation_share is the share of "
    "all citation instances in the round that point at "
    "the product own domain."
)

DEFINITIONS_LINE = (
    "Definitions: a tier is the label that states how much "
    "weight a rate can carry, set by effective n; an "
    "interval is a cluster adjusted range computed by the "
    "Wilson formula at effective n, and no coverage "
    "probability is claimed for it; effective n is the "
    "cluster count a rate effectively rests on, after near "
    "duplicate answers are clustered together."
)

SCORE_BAND_SCALE_LINE = (
    "Score band scale: 80 and over is strong, 60 and over "
    "is developing, 40 and over is thin, and below 40 is "
    "poor."
)

COMPUTED_FIGURES_ESTABLISHES = (
    "This artefact states the figures this invocation "
    "computed over the home as it stands, and no stored "
    "record of a run stands behind them."
)

FORMS = ("simple", "advanced", "agentic")

_ABSENCE_STATE = "not_recorded"

_REPORT_MARKERS = (
    "score",
    "checks",
    "opening_text",
    "actions",
    "rates",
    "round_metrics",
    "metrics",
    "entries",
    "outcome_counts",
    "head_hash",
)


def _plain(value):
    """Convert a stored record to plain JSON shaped data.

    Dicts, sequences, and attribute carrying records convert by
    their own fields, in their own order. Scalars pass through
    unchanged. Nothing is computed and nothing is dropped except
    private attribute names on object records.
    """
    if isinstance(value, float) and not math.isfinite(value):
        # A figure that is not a finite number stands as
        # no figure in every form: the JSON forms hold no
        # token a strict parse refuses, and the Simple
        # form prints no claim no evidence holds.
        return None
    if isinstance(value, Decimal) and not value.is_finite():
        return None
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        plain = {}
        for key, item in value.items():
            text_key = str(key)
            if text_key in plain:
                # Two distinct keys sharing one string form
                # cannot both stand in a JSON object. The
                # record is refused in the open rather than
                # one field dropping in silence.
                raise ValueError(
                    "record keys %r and %r share the string "
                    "form %r and cannot both stand in the "
                    "rendered record" % (
                        next(
                            standing for standing in value
                            if str(standing) == text_key),
                        key, text_key))
            plain[text_key] = _plain(item)
        return plain
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "_asdict"):
        return {str(key): _plain(item)
                for key, item in value._asdict().items()}
    if hasattr(value, "__dict__"):
        return {str(key): _plain(item)
                for key, item in vars(value).items()
                if not key.startswith("_")}
    return str(value)


def _walk(node):
    """Yield every dict inside a plain structure, itself first."""
    if isinstance(node, dict):
        yield node
        for item in node.values():
            yield from _walk(item)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _is_absence(node):
    return (
        isinstance(node, dict)
        and node.get("recorded") is False
        and node.get("state") == _ABSENCE_STATE
    )


def _is_report_like(node):
    return isinstance(node, dict) and any(
        key in node for key in _REPORT_MARKERS)


def _find_bounds(node):
    for obj in _walk(node):
        if "establishes" in obj and "does_not_establish" in obj:
            return obj
    return None


def _is_invocation_computed(plain):
    """True for the status and verify records: artefacts whose
    figures are computed in the invocation over the home, with
    no stored record of a run behind them. A run artefact
    carries a score, checks, or rates; these carry a chain
    result and a home path and none of those."""
    return (
        isinstance(plain, dict)
        and "chain_result" in plain
        and "home_path" in plain
        and "score" not in plain
        and "checks" not in plain
        and "rates" not in plain
    )


def bounds_for(record):
    """The bounds section for a record, in its one shared form.

    Where the record already carries a bounds section, that
    section stands as stored. Where none stands, the section is
    stated from the fixed scope lines and from what a rendering
    of a stored record establishes by its nature. The section
    states two lists of equal standing and duplicates no figure.
    """
    plain = _plain(record)
    found = _find_bounds(plain)
    if found is not None:
        if _is_invocation_computed(plain):
            corrected = copy.deepcopy(found)
            corrected["establishes"] = [
                COMPUTED_FIGURES_ESTABLISHES]
            return corrected
        return found
    if _is_invocation_computed(plain):
        establishes = [COMPUTED_FIGURES_ESTABLISHES]
        does_not_establish = [
            "This artefact does not establish the truth of any "
            "statement the audited page or a sampled answer makes.",
            THIRD_PARTY_SCOPE_LINE,
        ]
        return {
            "establishes": establishes,
            "does_not_establish": does_not_establish,
        }
    establishes = [
        "This artefact renders the stored record of this run, "
        "with its figures as stored and no figure added.",
    ]
    does_not_establish = [
        "This artefact does not establish the truth of any "
        "statement the audited page or a sampled answer makes.",
        THIRD_PARTY_SCOPE_LINE,
    ]
    return {
        "establishes": establishes,
        "does_not_establish": does_not_establish,
    }


def _apply_anchor_limit(body):
    """Stand the anchor limit sentence beside any head hash.

    The sentence is a fixed text: the fixed words stand,
    and a stored copy under the same field never replaces
    them.
    """
    for obj in _walk(body):
        if obj.get("head_hash"):
            obj["anchor_limit"] = ANCHOR_LIMIT_SENTENCE


def _apply_fixed_texts(body):
    """Hold the fixed texts fixed inside the payload.

    The honesty sentence stands in its fixed words in
    every report like payload, and the presence only
    scope value stands as the claim type of every object
    that carries one beside its value, with no validated
    predictor claim standing beside it. A stored copy of
    either text never overrides the fixed text.
    """
    if _is_report_like(body):
        body["honesty_sentence"] = HONESTY_SENTENCE
    for obj in _walk(body):
        if "claim_type" in obj and "value" in obj:
            obj["claim_type"] = SCOPE_VALUE
            if obj.get("validated_predictor"):
                obj["validated_predictor"] = False


def _failure_record_payloads(body):
    """The failure record payloads a record carries, in
    the forms they travel in: a failure_records list of
    payloads, a single failure_record payload, or journal
    entries of the failure_record kind carrying their
    payload, at the top level or inside an entries list.

    One stored record may travel in two of those forms at
    once, and it stands collected once: the forms stand
    merged by multiplicity, so the count a payload stands
    at is the greatest count it stands at in any one
    form, never the sum over forms. Two identical stored
    records inside one form still stand as two, as a
    retried failure stands (Step 17 round 3 entry
    S17-R3-063, and round 4 entry S17-R4-049 for the
    composition over forms).

    The gathering stands by position, blind to nothing:
    a payload standing inside another carry form stands
    collected in the form it stands in, so an entry
    shaped wrapper standing in the list form or the
    single form contributes its payload to that form,
    and only an entry standing inside an entries list
    stands in the entries form (Step 17 round 5 entry
    S17-R5-048). An entries list standing inside a
    failure payload carried by the list form or the
    single form stands in no entries form, and an
    entries list standing under the entries name in any
    case stands collected (Step 17 round 6 entry
    S17-R6-040). The entries name and the carry keys
    stand judged under the module component reading, so
    a camel or separator form of either name stands as
    the same name (Step 17 round 7 entry S17-R7-042).
    """
    # The names this collector judges stand judged under
    # the component reading this module states for field
    # names, so a camel, capitalised camel, hyphen, or
    # space form of a name stands as the same name as its
    # underscore form (Step 17 round 7 entry S17-R7-042).
    def components_of(key):
        return tuple(_key_components(key))

    def payload_of(item):
        if not isinstance(item, dict):
            return None
        for key, value in item.items():
            if components_of(key) == ("payload",):
                return value
        return None

    def is_carry_key(key):
        return components_of(key) in (
            ("payload",), ("failure", "record"),
            ("failure", "records"))

    def is_entries_key(key):
        parts = components_of(key)
        if not parts:
            return False
        return parts[-1] == "entries" or parts[-2:] == (
            "entries", "list")

    def unwrap(item):
        # A payload standing inside an entry shaped
        # wrapper stands collected as the payload it is,
        # in the form the wrapper stands in: the wrapper
        # is a carry form, not a payload, and its payload
        # does not stand in the entries form merely
        # because a wrapper carries it there (Step 17
        # round 5 entry S17-R5-048).
        while isinstance(item, dict) \
                and item.get("entry_kind") == "failure_record" \
                and isinstance(payload_of(item), dict):
            item = payload_of(item)
        return item

    def entries_form(node, found):
        # The entries form stands only where an entries
        # list stands: an entry shaped object inside an
        # entries list, at the top level or in a nested
        # entries list, stands in the entries form, and
        # an entry shaped object standing anywhere else
        # stands in the form that carries it, never in
        # this one.
        # The walk never descends into a failure payload
        # looking for entries: a payload carried by the
        # list form or the single form stands under the
        # failure_records or failure_record key, as a
        # wrapper payload stands under the payload key,
        # and an entries list standing inside such a
        # payload stands in no entries form (Step 17
        # round 6 entry S17-R6-040). The entries name
        # itself stands judged in any case, as the other
        # readings in this module judge a field name by
        # its case shifted form, so an entries list under
        # a case shifted entries key stands collected.
        if isinstance(node, dict):
            for key, value in node.items():
                if is_carry_key(key):
                    continue
                if isinstance(value, list) and is_entries_key(key):
                    entries_list(value, found)
                else:
                    entries_form(value, found)
        elif isinstance(node, list):
            for item in node:
                entries_form(item, found)

    def entries_list(items, found):
        for item in items:
            if isinstance(item, dict) \
                    and item.get("entry_kind") == "failure_record" \
                    and isinstance(payload_of(item), dict):
                found.append(unwrap(item))
            elif isinstance(item, list):
                entries_list(item, found)
            elif isinstance(item, dict):
                entries_form(item, found)

    forms = []
    if isinstance(body, dict):
        for key, value in body.items():
            if components_of(key) == ("failure", "records") \
                    and isinstance(value, list):
                forms.append(
                    [unwrap(item) for item in value
                     if isinstance(unwrap(item), dict)])
            elif components_of(key) == ("failure", "record") \
                    and isinstance(value, dict):
                forms.append([unwrap(value)])
    gathered = []
    entries_form(body, gathered)
    forms.append(gathered)

    def count_of(counts, item):
        for standing, count in counts:
            if standing == item:
                return count
        return 0

    def raise_count(counts, item):
        for index, (standing, count) in enumerate(counts):
            if standing == item:
                counts[index] = (standing, count + 1)
                return
        counts.append((item, 1))

    payloads = []
    emitted = []
    for form in forms:
        seen_in_form = []
        for item in form:
            raise_count(seen_in_form, item)
            if count_of(seen_in_form, item) \
                    > count_of(emitted, item):
                payloads.append(item)
                raise_count(emitted, item)
    return payloads


def _apply_failure_records(body):
    """Stand the failure record content of a record under
    its own failure_records field, so an operator surface
    rendering the record states that a failure occurred,
    what operation failed, what error value it carried,
    and what subject it named, as the stored payload
    carries them.
    """
    if not isinstance(body, dict):
        return
    payloads = _failure_record_payloads(body)
    if payloads:
        body["failure_records"] = payloads


_CITATION_ONLY_CODE = "CITATION_ONLY_NO_QUOTABLE_SENTENCE"

_SELECTION_MARKER_KEYS = (
    "selection", "basis", "marker", "source", "chosen_by",
    "opening_kind", "opening_source",
)


def _selection_marker_values(body):
    """The values in a guide record that may name the opening's
    selection basis: any field whose name speaks of selection,
    basis, or source, at the top level or inside a nested
    record, and the code fields of the draft's actions. The
    opening text itself and the action texts are the draft's
    prose, not markers, and are not read here.
    """
    values = []

    def collect(node, key_hint):
        if isinstance(node, dict):
            for key, value in node.items():
                lowered = str(key).lower()
                hint = key_hint or any(
                    part in lowered
                    for part in _SELECTION_MARKER_KEYS)
                if isinstance(value, (dict, list)):
                    collect(value, hint)
                elif hint:
                    values.append(value)
        elif isinstance(node, list):
            for item in node:
                collect(item, key_hint)

    for key, value in body.items():
        if key in ("opening_text", "actions"):
            continue
        lowered = str(key).lower()
        if any(part in lowered for part in _SELECTION_MARKER_KEYS):
            if isinstance(value, (dict, list)):
                collect(value, True)
            else:
                values.append(value)
    for action in body.get("actions") or []:
        if isinstance(action, dict):
            for key in ("code", "check_or_outcome",
                        "selection", "basis"):
                if action.get(key) is not None:
                    values.append(action[key])
    return values


def _apply_guide_texts(body):
    """Stand the fixed guide texts the record's own state calls
    for, in the JSON forms as fields.

    The refusal sentence stands where the draft refused. The
    citation only sentence stands where the draft carries the
    citation only code, in its refusal code field or in the
    code of one of its actions, which is where the guide
    module's own draft form records that state. A selection
    statement stands where a marker field of the draft record
    names the fallback or the preference as the opening's
    basis; the marker is read in any of its stated spellings,
    as a bare word or as a compound value naming it.
    """
    if not (isinstance(body, dict) and "opening_text" in body
            and "actions" in body):
        return
    for source_key in ("source_run_id", "source_round_id"):
        if body.get(source_key) is None:
            body.pop(source_key, None)
    # The fixed guide sentences stand assigned outright,
    # as the honesty sentence stands: a stored copy under
    # the same field never replaces the fixed text, and a
    # fixed sentence field the record state does not call
    # for does not stand in the artefact at all.
    if body.get("refused") or \
            body.get("refusal_code") == "NO_REUSABLE_EVIDENCE":
        body["refusal_sentence"] = REFUSAL_SENTENCE
    else:
        body.pop("refusal_sentence", None)
    citation_only = body.get("refusal_code") == _CITATION_ONLY_CODE
    if not citation_only:
        for action in body.get("actions") or []:
            if isinstance(action, dict) and \
                    _CITATION_ONLY_CODE in (
                        action.get("code"),
                        action.get("check_or_outcome")):
                citation_only = True
    if citation_only:
        body["citation_only_sentence"] = CITATION_ONLY_SENTENCE
    else:
        body.pop("citation_only_sentence", None)
    # The selection statement is governed by the draft
    # record selection_basis field alone, in its stated
    # values. No other field of the record, and no marker
    # shaped value anywhere in it, chooses the statement.
    basis = body.get("selection_basis")
    # The basis stands judged as a stated form whole, not
    # as a substring: a value that negates, combines, or
    # embeds the stated words is no stated form and renders
    # no statement (Step 17 round 3 entry S17-R3-044).
    stated = basis.strip().casefold() if isinstance(basis, str) \
        else None
    if stated == "fallback":
        body["selection_statement"] = FALLBACK_STATEMENT
    elif stated in ("preference", "preferred"):
        body["selection_statement"] = PREFERENCE_STATEMENT
    else:
        body.pop("selection_statement", None)


def _apply_small_sample_warning_text(body):
    """Stand the fixed warning text where a rate object carries
    the warning in its boolean stored form. The brief states
    the warning as a fixed text; a stored true stands for that
    text, and the rendering states it in words in every form.
    """
    for obj in _walk(body):
        if obj.get("small_sample_warning") is True:
            obj["small_sample_warning"] = SMALL_SAMPLE_WARNING


def _apply_control_failure_notice(body):
    """Stand the failed control notice in its own form.

    Where the record states a failed control, by a notice
    field of its own or by a control_failed or control_failure
    flag standing true, the artefact carries the notice under
    its own control_failure_notice field, as a field beside
    the round's figures. It stands in no warning list and
    under no warning key, in any form. A record that states
    no failed control carries no notice.
    """
    if isinstance(body, list):
        # A record reaching the pipeline as a list stands
        # under the same pass: each object at its top
        # level stands as a record top level for the pass,
        # so a spoofed notice on one stands removed and a
        # flagged one gains the fixed notice, as a dict
        # record does (Step 17 round 5 entry S17-R5-043).
        for item in body:
            if isinstance(item, (dict, list)):
                _apply_control_failure_notice(item)
        return
    if not isinstance(body, dict):
        return
    # The notice stands only on a record that states a
    # failed control, by its control_failed or
    # control_failure flag standing true, and it stands
    # in its fixed text. Notice text read from the record
    # never stands as the artefact notice, at the top
    # level or promoted from a nested object, and a
    # record stating no failed control carries no notice:
    # its notice shaped fields do not stand in the
    # artefact in that role.
    # The flag stands judged by truthiness, as the guide
    # module judges the same field through bool() in
    # draft_from_round, so one product reads a record as
    # a failed control on the same terms the other
    # renders its notice on; a control_flag standing at
    # the record own top level states the failed control
    # in the same way (Step 17 round 5 entry S17-R5-043).
    # The three flag names stand judged as the same name
    # under the component reading this module states for
    # field names, so a flag standing under a case shifted,
    # camel, or separator form of one of the three names
    # states the failed control as the exact name does, at
    # the top level and at any depth (Step 17 round 7
    # entry S17-R7-039). control_flag stands judged at any
    # depth as the other two flags are judged, over the
    # walked objects, so a flag standing in a nested object
    # or in a list item states the failed control in the
    # same way (Step 17 round 6 entry S17-R6-037).
    flag_components = (
        ("control", "failed"), ("control", "failure"),
        ("control", "flag"))
    flagged = False
    for obj in _walk(body):
        for key in obj:
            if tuple(_key_components(key)) in flag_components \
                    and obj.get(key):
                flagged = True
    # The three notice keys stand judged as the same
    # notice name under the same component reading, at the
    # top level and in nested objects alike, so a notice
    # key carrying a hyphen, a doubled separator, or a
    # trailing space stands under the pass as the exact
    # underscore name does, as a case shifted form of one
    # of the three names stood under it before (Step 17
    # round 6 entry S17-R6-036, and round 7 entry
    # S17-R7-038).
    notice_components = (
        ("control", "failure", "notice"), ("control", "notice"),
        ("failed", "control", "notice"))

    def is_notice_key(key):
        return tuple(_key_components(key)) in notice_components

    guide_notice_text = None
    for key, value in body.items():
        if tuple(_key_components(key)) == \
                ("control", "failure", "notice"):
            guide_notice_text = value
    guide_notice = (
        "opening_text" in body and "actions" in body
        and guide_notice_text == (
            "a control in this round failed, and no action "
            "stands produced from this round"))
    # The nested removal runs on every path, not only on
    # the path where no flag and no guide notice stands:
    # a spoofed notice in a nested object stands removed
    # beside the fixed notice as on the empty path (Step
    # 17 round 3 entry S17-R3-043).
    for obj in _walk(body):
        if obj is body:
            continue
        for key in list(obj):
            if is_notice_key(key):
                obj.pop(key, None)
    # The top level stands under the same removal, on the
    # whole notice key set the pass itself states: a
    # spoofed notice under any of the three keys at the
    # top level stands removed as a nested one does, and
    # only the fixed notice, or the guide notice a guide
    # record carries in its own form, stands in its place
    # (Step 17 round 5 entry S17-R5-043).
    for key in list(body):
        if is_notice_key(key):
            body.pop(key, None)
    if flagged:
        body["control_failure_notice"] = CONTROL_FAILURE_NOTICE
        return
    if guide_notice:
        body["control_failure_notice"] = guide_notice_text
        return


def _apply_methods_note_version(body):
    """Surface the methods note version at the artefact's top
    level, naming the version only. Where the record carries
    the version inside a nested stamps object and not at its
    top level, the same value stands at the top level of the
    artefact. No version is invented: a record that carries
    none renders without one, and no methods note text or
    methods note section stands in any artefact.
    """
    if not isinstance(body, dict):
        return
    if body.get("methods_note_version") is not None:
        return
    for obj in _walk(body):
        if obj is body:
            continue
        if obj.get("methods_note_version") is not None:
            body["methods_note_version"] = \
                obj["methods_note_version"]
            return


def _apply_trend_field_names(body):
    """Stand a ProbeTrend record's stored values under the
    field names its shape states. The series break value the
    computation stored as series_break stands also as
    series_break_marker, and the capture method sets it stored
    as one capture_method_sets object stand also as the two
    named set fields, asserted and normalised. The values are
    the stored values, renamed only.
    """
    if not isinstance(body, dict):
        return
    if "series_break" in body and \
            "series_break_marker" not in body:
        body["series_break_marker"] = body["series_break"]
    sets = body.get("capture_method_sets")
    if isinstance(sets, dict):
        first = sets.get("first") or {}
        second = sets.get("second") or {}
        if "asserted_capture_method_sets" not in body:
            body["asserted_capture_method_sets"] = {
                "first": first.get("asserted"),
                "second": second.get("asserted"),
            }
        if "normalised_capture_method_sets" not in body:
            body["normalised_capture_method_sets"] = {
                "first": first.get("normalised"),
                "second": second.get("normalised"),
            }


def _recomputed_secondary_figure(score, checks):
    """The secondary figure recomputed at rendering, in the
    F6 form: an object holding the figure under value, the
    total weight of 100, and the basis statement.

    The IM7-BRK-3 landing states the figure is not stored:
    it recomputes at rendering from the stored CheckResults,
    so a record written before the figure stood in the
    ScoreObject renders it on the same terms, and no not
    recorded case stands for it. The numerator is the sum of
    earned times weight over the applicable checks, summed
    in exact decimal and rounded half up to one decimal
    place on the total weight of 100, exactly as the stored
    computation forms it. The evidence cap caps the figure
    at 39.0 on the same trigger as the headline, read here
    from the stored cap status. The figure stands only where
    at least one check stands not applicable and at least
    one check stands applicable, and never beside the
    absence form of the headline.
    """
    if not isinstance(checks, list) or not checks:
        return None
    if not isinstance(score, dict) or score.get("value") is None:
        return None
    applicable = []
    has_not_applicable = False
    for item in checks:
        if not isinstance(item, dict):
            continue
        if item.get("status") == "not_applicable":
            has_not_applicable = True
        else:
            applicable.append(item)
    if not has_not_applicable or not applicable:
        return None
    weighted = sum(
        Decimal(str(item.get("earned") or 0))
        * Decimal(str(item.get("weight") or 0))
        for item in applicable)
    value = float(_quantized_decimal(
        weighted / Decimal(100) * 100, "0.1"))
    if score.get("cap_status") and value > 39.0:
        value = 39.0
    return {
        "value": value,
        "total_weight": 100,
        "basis": SECONDARY_FIGURE_BASIS,
    }


def _apply_secondary_figure_recompute(body):
    """Stand the recomputed secondary figure beside any
    headline score whose stored ScoreObject lacks it.

    This act stands at rendering only, on the deep copy the
    pipeline renders from: the stored record and the journal
    gain no field, and the figure is never written back. A
    ScoreObject that already carries the figure renders it
    as stored.
    """
    for node in list(_walk(body)):
        if not isinstance(node, dict):
            continue
        score = node.get("score")
        if not isinstance(score, dict):
            continue
        if score.get("secondary_figure") is not None:
            continue
        figure = _recomputed_secondary_figure(
            score, node.get("checks"))
        if figure is not None:
            score["secondary_figure"] = figure


def _advanced_body(record):
    """The Advanced payload: the stored record, with the common
    carry stood beside the values it travels with."""
    body = copy.deepcopy(_plain(record))
    if not isinstance(body, dict):
        if isinstance(body, list):
            # A list record stands under the passes that
            # judge the objects it carries at its top
            # level, the control notice pass and the scope
            # pass, as a dict record does (Step 17 round 5
            # entry S17-R5-043).
            _apply_control_failure_notice(body)
            _apply_agentic_scope(body)
        return body
    _apply_secondary_figure_recompute(body)
    _apply_anchor_limit(body)
    _apply_fixed_texts(body)
    _apply_failure_records(body)
    _apply_small_sample_warning_text(body)
    _apply_methods_note_version(body)
    _apply_trend_field_names(body)
    if _is_invocation_computed(body):
        carried = _find_bounds(body)
        if carried is not None:
            carried["establishes"] = [
                COMPUTED_FIGURES_ESTABLISHES]
    if _is_report_like(body):
        body["honesty_sentence"] = HONESTY_SENTENCE
        if _find_bounds(body) is None:
            body["bounds"] = bounds_for(body)
    # The control notice pass stands on every record the
    # pipeline hands it, not only on a record carrying one
    # of the report markers: a flagged record carrying no
    # marker stands under both limbs of the discipline,
    # the fixed notice and the nested removal, as a marked
    # record does (Step 17 round 4 entry S17-R4-045).
    _apply_control_failure_notice(body)
    _apply_guide_texts(body)
    if _is_query_set_report(body):
        body.setdefault("overlap_statement", _OVERLAP_STATEMENT)
        body.setdefault("coverage_statement", _COVERAGE_STATEMENT)
    # Every Advanced report object carries the anchor
    # limit field at its top level, not only beside a head
    # hash, and the report objects the brief names carry
    # the honesty sentence field among them: the probe
    # report, the guide, the query set report, and the
    # staleness view stand named in Step 19 register entry
    # R19-096 beside the audit object itself.
    if _is_guide(body) or _is_probe_like(body) or \
            _is_query_set_report(body) or \
            _is_staleness_view(body):
        body["anchor_limit"] = ANCHOR_LIMIT_SENTENCE
        body["honesty_sentence"] = HONESTY_SENTENCE
    # The presence only scope discipline stands in every
    # form, the Simple form included, so the scope pass
    # runs on the body every rendering form derives from.
    _apply_agentic_scope(body)
    return body


# The words a fused field name can stand built from, for
# the component reading at Step 17 round 6 entry
# S17-R6-035: a fused name stands read as its components
# only where the whole name segments into words of this
# set, so a key holding the letters of a component inside
# a longer word that segments no such way, as accurate
# holds the letters of rate, keeps that component standing
# outside it, as the Yellow boundary states. The set stands
# completed on the product nouns the round 7 entry names:
# citation, citations, evidence, quotation, quotations,
# statistics, freshness, and sampling (Step 17 round 7
# entry S17-R7-037).
_FUSED_COMPONENT_WORDS = frozenset((
    "action", "actions", "answer", "answers", "applicable",
    "audit", "band", "basis", "capture", "captured", "card",
    "chain", "check", "checks", "cited", "citation",
    "citations", "claim", "code",
    "codes", "confidence", "control", "count", "counts",
    "date", "delta", "design", "early", "earned", "effect",
    "engine", "engines", "entries", "entry", "error",
    "errors", "evidence", "failure", "failures", "field", "fields",
    "figure", "figures", "file", "files", "final", "first",
    "freshness",
    "form", "forms", "gross", "group", "groups", "guide",
    "hash", "head", "headline", "high", "hit", "home",
    "identity", "interval", "intervals", "item", "items",
    "key", "keys", "kind", "label", "labels", "last",
    "limit", "limits", "list", "low", "marker", "markers",
    "mean", "method", "methods", "my", "name", "named",
    "names", "naming", "net", "note", "notes", "notice",
    "number", "numbers", "object", "objects", "opening",
    "operation", "overall", "page", "path", "paths", "pct",
    "per", "percent", "percentage", "probe", "product",
    "proportion", "quotation", "quotations", "range", "rate",
    "rates", "ratio",
    "ratios", "record", "records", "report", "result",
    "round", "rule", "rules", "ruleset", "run", "sample",
    "samples", "sampling", "score", "scores", "second", "selection",
    "set", "sets", "share", "size", "source", "state",
    "states", "statistics", "status", "subject", "text", "the", "tier",
    "tiers", "time", "total", "type", "value", "values",
    "version", "versions", "warning", "warnings", "weight",
    "weights", "wilson",
))

_FUSED_WORDS_BY_LENGTH = sorted(
    _FUSED_COMPONENT_WORDS, key=len, reverse=True)


def _segment_fused(part):
    """The components of one fused name part, where the
    whole part segments into the fused word set, and the
    part standing alone where it segments no such way."""
    if len(part) < 4 or part in _FUSED_COMPONENT_WORDS:
        return [part]

    def search(start):
        if start == len(part):
            return []
        for word in _FUSED_WORDS_BY_LENGTH:
            if part.startswith(word, start):
                rest = search(start + len(word))
                if rest is not None:
                    return [word] + rest
        return None

    found = search(0)
    if found and len(found) > 1:
        return found
    return [part]


def _key_components(key):
    """The word components of one field name, split on its
    separators and on its case shifts, in lower case. A
    part carrying no separator and no case shift stands
    read by the fused segmentation above, so a fused name
    stands on the same components as its separated form
    (Step 17 round 6 entry S17-R6-035)."""
    spaced = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])", "_", str(key))
    spaced = re.sub(
        r"(?<=[A-Z])(?=[A-Z][a-z])", "_", spaced)
    parts = []
    for raw in re.split(r"[^A-Za-z0-9]+", spaced):
        if raw:
            parts.extend(_segment_fused(raw.lower()))
    return parts


_HEAD_QUALIFIERS = (
    "gross", "net", "value", "pct", "percent", "low", "high",
    "count", "interval", "share", "ratio", "mean", "total",
    "band", "delta", "range", "confidence", "basis")


def _names_rate(key):
    """True where a field name names a rate, on the field
    names the product itself uses, in the positions and
    compounds those names stand in: the bare rate key and
    the rates key, a rate component standing after another
    component, as cited_rate and gross_rate_value stand,
    the fused citedrate form, and a rate standing at the
    head of a compound whose next component is a rate
    qualifier the product uses, as rate_gross, rate_net,
    and rate_value stand. A key holding the letters of
    rate with no rate component, as accurate holds them,
    names no rate, and a rate at the head of a compound
    whose next component is no rate qualifier, as
    rate_card stands, names none either, no product field
    standing in that shape (Step 17 round 5 entry
    S17-R5-042, with the Yellow adjacent run of round 5
    at entry S17-R4-044). The fused forms stand read by
    the same components as their separated forms, and the
    head position limb stands judged on the same
    component reading, its qualifier set completed on the
    qualifiers the round 6 entry names beside the five
    the round 5 cure names: low, high, count, interval,
    share, ratio, mean, and total (Step 17 round 6 entry
    S17-R6-035)."""
    parts = _key_components(key)
    if not parts:
        return False
    if "rates" in parts:
        return True
    if "".join(parts) == "citedrate":
        return True
    if "rate" not in parts:
        return False
    index = parts.index("rate")
    if index > 0 or len(parts) == 1:
        return True
    # The head qualifier set stands as one set for the
    # rate and score limbs alike, completed with basis,
    # the score qualifier the rate set omitted (Step 17
    # round 8 entry S17-R8-020).
    return parts[1] in _HEAD_QUALIFIERS


def _names_score(key):
    """True where a field name names a score, on the same
    component reading as the rate limb: the bare score key
    in any case, a score component standing after another
    component, as overall_score, final_score, and
    headline_score stand, and a score standing at the head
    of a compound whose next component is a score
    qualifier, as score_value stands. A score at the head
    whose next component is no qualifier, as the score
    version stamp key score_ruleset_version stands, names
    no score figure (Step 17 round 6 entry S17-R6-035)."""
    parts = _key_components(key)
    if "score" not in parts:
        return False
    index = parts.index("score")
    if index > 0 or len(parts) == 1:
        return True
    # The head qualifier set stands as one set for the
    # score and rate limbs alike, so a score at the head
    # stands judged on every qualifier the rate limb
    # states, as a rate at the head stands judged on
    # basis (Step 17 round 8 entry S17-R8-020).
    return parts[1] in _HEAD_QUALIFIERS


def _names_tier(key):
    return any(
        part in ("tier", "tiers")
        for part in _key_components(key))


def _names_wilson(key):
    return "wilson" in _key_components(key)


def _apply_agentic_scope(body):
    """The presence only bound as a field level property.

    Any record object carrying a score, a rate, or a tier also
    carries, in that same object, the short machine readable
    scope value. A ScoreObject already carries it as its claim
    type in every form, as a constant of its shape; rate and
    tier objects gain the same field here, in both JSON forms.
    The plan states the bound for the Agentic form, in that
    same record object, and states cross form equality on
    values from one canonical record, with no number in the
    Agentic form that the Advanced form does not hold. It
    states no bar on the same constant standing in the
    Advanced form. Standing it in both JSON forms is the one
    reading under which the Agentic bound and the equality of
    the rates objects across the forms both hold: an Agentic
    only addition would add a field to one form's rate objects
    and break that equality, and an artefact level addition
    would leave the rate objects themselves without the value
    the bound requires in their own object. The Simple form
    is prose and gains no field; it states the same rates in
    words, with the honesty sentence as its closing line.
    """
    for obj in _walk(body):
        if "claim_type" in obj and "value" in obj:
            continue
        if "claim_type" in obj and "band" in obj:
            # A ScoreObject carrying its band and its claim
            # type but no value key stands as a ScoreObject
            # still: its claim type is the scope value in
            # every form, as a constant of its shape, and
            # no missing value key shields it (Step 17
            # round 5 entry S17-R5-042).
            obj["claim_type"] = SCOPE_VALUE
            continue
        # The pass own stated rule: any record object
        # carrying a score, a rate, or a tier also carries
        # the scope value in that same object. The shape
        # test stands on that rule whole, not on two
        # shapes: a tier beside a count, a bare rate, and
        # a bare score key each carry the value (Step 17
        # round 3 entry S17-R3-042). A score standing as a
        # record object is the ScoreObject itself, whose
        # claim type the fixed texts pass governs through
        # its value field, so a dict score value here
        # names that nested object, not a score figure
        # this object carries.
        # A rate stands under the field names the product
        # itself uses for rates, not only under the bare
        # rate key: a key naming a rate, as cited_rate and
        # cited_rate_gross name one, carries a rate, and
        # the rate interval fields wilson_low and
        # wilson_high carry one on their own, with no tier
        # standing beside them (Step 17 round 4 entry
        # S17-R4-044).
        # The shape test stands on the pass own rule
        # whole, on the field names the product itself
        # uses in every position and compound those names
        # stand in: a tier under a compound key, a rate at
        # the head of its key or fused or case shifted,
        # the wilson interval fields in their pairings,
        # and a score under a compound key each carry a
        # rate, a tier, an interval, or a score as the
        # bare keys do (Step 17 round 5 entry S17-R5-042).
        carries = (
            any(
                isinstance(key, str) and _names_tier(key)
                for key in obj)
            or any(
                isinstance(key, str) and _names_rate(key)
                for key in obj)
            or any(
                isinstance(key, str) and _names_wilson(key)
                for key in obj)
            or any(
                isinstance(key, str)
                and _names_score(key)
                and not isinstance(obj.get(key), dict)
                for key in obj))
        if carries:
            # The scope value stands assigned outright on
            # an object that carries a rate or a tier, in
            # the fixed scope discipline: no field of the
            # object, and no value standing in any sibling
            # field, shields a stored claim_type from it.
            obj["claim_type"] = SCOPE_VALUE


def _simple_safe_text(text):
    """One text value made safe for the Simple form, at the
    pipeline's one escaping point.

    A line break or carriage return inside a value becomes
    a space, so a value never escapes its field and forges
    an artefact line. Control characters, format
    characters, and direction overrides become spaces, so
    hostile text stands as plain text characters and never
    acts on the display. A lone surrogate becomes the
    replacement character, so the artefact always encodes.
    JSON object syntax is broken by a space after the
    opening brace, so no Simple artefact carries it.
    """
    cleaned = []
    for char in text:
        category = unicodedata.category(char)
        if category == "Cs":
            cleaned.append("�")
        elif category in ("Cc", "Cf", "Zl", "Zp"):
            # Control and format characters become spaces,
            # and so do the line and paragraph separator
            # categories: a separator inside a stored name
            # or note is a line break to every line based
            # reader, so it stands as a space here, at the
            # one escaping point, like the control forms.
            cleaned.append(" ")
        else:
            cleaned.append(char)
    joined = "".join(cleaned)
    # JSON object syntax stands broken in the Simple
    # form on the brief criterion, not only in its brace
    # and quote adjacency: a zero width space stands
    # after every opening brace, a character no JSON
    # reading treats as whitespace, so no value in the
    # artefact parses as a JSON object, spaced or not.
    return joined.replace("{", "{\u200b")


def _simple_safe(node):
    """Every string in a plain structure, keys included,
    passed through the Simple escaping point."""
    if isinstance(node, str):
        return _simple_safe_text(node)
    if isinstance(node, dict):
        # Keys stand mapped through the escaping point
        # here, a second mapping after the plain
        # conversion: two keys that differ before this
        # mapping and match after it refuse in the open,
        # in the same form as the plain conversion
        # refusal, rather than one field dropping in
        # silence behind the other.
        safe = {}
        for key, item in node.items():
            text_key = _simple_safe_text(str(key))
            if text_key in safe:
                raise ValueError(
                    "record keys share the Simple form %r "
                    "after escaping and cannot both stand "
                    "in the Simple artefact" % (text_key,))
            safe[text_key] = _simple_safe(item)
        return safe
    if isinstance(node, list):
        return [_simple_safe(item) for item in node]
    return node


def render(record, form="advanced"):
    """Render one stored record in one reading form.

    Simple returns a prose string. Advanced returns the report
    object as plain data. Agentic returns the envelope holding
    that same payload under the one named report key, with the
    honesty and limit fields in structured form at the top
    level. Rendering is a pure transformation of the one record:
    it reads no second store, recomputes nothing, and a second
    render of the same record stands equal to the first.
    """
    if form not in FORMS:
        raise ValueError("unknown reading form: %r" % (form,))
    if form == "simple":
        return _render_simple(_simple_safe(_advanced_body(record)))
    body = _advanced_body(record)
    _apply_agentic_scope(body)
    if _is_audit_record(body):
        body = _audit_traced_projection(body)
    if form == "advanced":
        return body
    envelope = {
        "schema_stamp": SCHEMA_STAMP,
        "status": AGENTIC_STATUS_OK,
    }
    identity = _stored_report_identity(body)
    if identity is not None:
        envelope["report_id"] = identity
    envelope["report"] = body
    envelope["honesty_sentence"] = HONESTY_SENTENCE
    envelope["anchor_limit"] = ANCHOR_LIMIT_SENTENCE
    return envelope


# The traced field set of the Advanced audit artefact, per
# the plan Section 1.5 reverse trace table: every field the
# artefact carries stands traced to the stored AuditRun
# record, and no field outside the set stands in the
# artefact (Step 19 queue addition U-11, reporting limb).
_AUDIT_TRACED_FIELDS = (
    "run_id", "product_id", "snapshot_id", "snapshot_sha256",
    "evaluated_page_path", "path_defaulted", "snapshot_format",
    "checks", "score", "cap_status", "robots_summary",
    "honesty_sentence", "anchor_limit", "audit_date",
    "ruleset_version", "detector_version", "registry_version",
    "query_set_version", "head_hash", "entry_count",
    "methods_note_version", "bounds",
)


def _audit_traced_projection(body):
    """The Advanced audit artefact body: the stored record
    projected onto its traced field set, in set order, with
    every value standing as the record holds it."""
    return {key: body[key] for key in _AUDIT_TRACED_FIELDS
            if key in body}


def _stored_report_identity(body):
    """The stored report identity of one record, where one
    exists: the run identity of an audit record, the guide
    identity of a guide draft, or the round identity of a
    probe report, read from the record itself. A record with
    no stored identity, as a status or verify record stands,
    carries none, and its envelope omits the field, as item
    122 states the field stands where a stored report exists.
    """
    if not isinstance(body, dict):
        return None
    for name in ("run_id", "guide_id", "round_id", "report_id"):
        if body.get(name) is not None:
            return body[name]
    nested = body.get("audit_run")
    if isinstance(nested, dict) and nested.get("run_id") is not None:
        return nested["run_id"]
    return None


def format_record(record, form="advanced"):
    """The shell's name for the same rendering act.

    The shell formats the record the service layer returns and
    holds no rule of its own, so this is the pipeline's render
    under a second name, and the two stand equal for one record
    in one form.
    """
    return render(record, form=form)


def _scalar_text(value):
    if value is None:
        return "none"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


_TREND_RATE_KEYS = ("first_value", "second_value", "delta")

_NONE_SILENT_KEYS = ("honesty_line", "no_delta_statement")


def _quantized_decimal(value, quantum):
    """A Decimal figure quantized at any magnitude.

    The default decimal context holds 28 significant
    digits, so quantizing a figure of great magnitude
    raises a raw decimal error. The context here widens
    to the figure own size, so a finite figure of any
    magnitude quantizes and renders as a figure.
    """
    from decimal import localcontext
    number = Decimal(str(value))
    with localcontext() as context:
        context.prec = max(
            28, len(number.as_tuple().digits)
            + abs(number.adjusted()) + 4)
        return number.quantize(
            Decimal(quantum), rounding=ROUND_HALF_UP)


def _percent_int(value):
    """A stored proportion restated as a whole percent,
    at any magnitude: the product of a great finite
    float and 100 overflows before rounding, so the
    conversion runs in decimal at that scale."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value * 100
    number = float(value)
    if math.isfinite(number) and abs(number) < 1e12:
        return round(number * 100)
    return int(_quantized_decimal(
        Decimal(str(value)) * 100, "1"))


_THOUSANDS_FIGURE_RE = re.compile(
    r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?:[eE][+-]?\d+)?$")


def _figure_or_none(value):
    """One figure position read as a figure or as none.

    A figure carried as a string is text to the pipeline:
    a string that reads as a finite number stands as
    that number, and any other string stands as no
    figure, so no string figure prints as a figure and
    none reaches a numeric step in its string form.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return value
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            parsed = None
        if parsed is None and _THOUSANDS_FIGURE_RE.match(
                value.strip()):
            # A thousands separated figure reads as the
            # number it writes: the separator stands in
            # its stated grouping, three digits to a group
            # after the first, so the figure stands judged
            # as a figure whole, where a misgrouped comma
            # string reads as no figure and stands as text
            # (Step 17 round 5 entry S17-R5-044).
            parsed = float(value.strip().replace(",", ""))
        if parsed is None:
            return None
        return parsed if math.isfinite(parsed) else None
    return value


def _rate_value_text(value):
    """A rate value in the Simple form, at four decimal places.

    A stored rate is a proportion; printing it at full float
    precision gives a sixteen decimal place figure no reader
    can hold. Four places is the precision the product itself
    states for its disclosed rate figures.
    """
    if isinstance(value, float):
        return str(round(value, 4))
    return _scalar_text(value)


def _figure_text(value):
    """One figure in the Simple form at the precision the
    product states for its disclosed figures, four decimal
    places for a float, so no printed position stands at
    full stored precision (Step 17 round 3 entry
    S17-R3-045). A figure carried as a string that reads
    as a finite number stands at the same precision, as
    the rate and score readings already judge a string
    figure through _figure_or_none (Step 17 round 4
    entry S17-R4-046). A figure in no such form stands
    as the plain scalar text stands."""
    if isinstance(value, float):
        return _rate_value_text(value)
    if isinstance(value, str):
        parsed = _figure_or_none(value)
        if isinstance(parsed, float):
            return _rate_value_text(parsed)
    return _scalar_text(value)


def _is_rate_object(node):
    return (
        isinstance(node, dict)
        and "wilson_low" in node
        and "wilson_high" in node
        and "n" in node
        and "tier" in node
    )


def _is_capture_context(node):
    if not isinstance(node, dict):
        return False
    keys = [key.lower() for key in node]
    has_engine = any("engine" in key for key in keys)
    has_method = any("method" in key for key in keys)
    has_date = any("date" in key for key in keys)
    return has_engine and has_method and (has_date or len(node) <= 4)


def _capture_context_line(node):
    counts = {}
    for key, value in node.items():
        if isinstance(value, int) and not isinstance(value, bool):
            lowered = key.lower()
            if "engine" in lowered:
                counts["engine"] = value
            elif "date" in lowered:
                counts["date"] = value
            elif "method" in lowered:
                counts["method"] = value
    if not counts:
        return None
    parts = []
    if "engine" in counts:
        parts.append("%d distinct engines" % counts["engine"])
    if "date" in counts:
        parts.append("%d distinct capture dates" % counts["date"])
    if "method" in counts:
        parts.append("%d distinct capture methods" % counts["method"])
    return "Capture context: " + ", ".join(parts) + "."


def _rate_line(name, node):
    rate = _figure_or_none(node.get("rate"))
    low = _figure_or_none(node.get("wilson_low"))
    high = _figure_or_none(node.get("wilson_high"))
    tier = node.get("tier")
    clause = TIER_CLAUSES.get(tier) if isinstance(tier, str) \
        else None
    if tier == "count only":
        count = node.get("count")
        if count is None:
            count = node.get("n")
        count_word = "answer" if count == 1 else "answers"
        warning = node.get("small_sample_warning")
        if low is None or high is None:
            line = (
                "%s: %s %s, tier count only: %s."
                % (name, _scalar_text(count), count_word, clause)
            )
        else:
            # An interval stands on this line, so the line
            # never states that no rate is given: the count
            # only clause stands in the form that speaks of
            # the count alone, and the small sample warning
            # the stored record holds stands beside the
            # interval (Step 19 item R19-056).
            line = (
                "%s: %s %s, interval %d to %d percent, tier "
                "count only: count only means the round rests "
                "on the count of answers alone and no rate "
                "stands as a finding."
                % (name, _scalar_text(count), count_word,
                   _percent_int(low), _percent_int(high))
            )
        if warning is True or warning == SMALL_SAMPLE_WARNING:
            line += " " + SMALL_SAMPLE_WARNING
        return line
    warning = node.get("small_sample_warning")

    def with_warning(line):
        # The warning stands under the fixed warning
        # discipline: a stored true stands for the fixed
        # text, and the rendering pass conversion hands
        # this line the fixed text itself in that case, so
        # the fixed text stands where the stored form is
        # true or stands as that text, and a stored string
        # in any other words never replaces it in the
        # artefact (Step 17 round 7 entry S17-R7-044).
        if warning is True or warning == SMALL_SAMPLE_WARNING:
            line += " " + SMALL_SAMPLE_WARNING
        return line

    if rate is None or low is None or high is None:
        rate_part = "rate null" if rate is None else (
            "rate %s" % _rate_value_text(rate))
        interval_part = "interval null" if (
            low is None or high is None) else (
            "interval %d to %d percent"
            % (_percent_int(low), _percent_int(high)))
        if clause is not None:
            line = (
                "%s: %s over %s answers, %s, tier %s: %s."
                % (name, rate_part, _scalar_text(node.get("n")),
                   interval_part, _scalar_text(tier), clause)
            )
        else:
            line = (
                "%s: %s over %s answers, %s, tier %s."
                % (name, rate_part, _scalar_text(node.get("n")),
                   interval_part, _scalar_text(tier))
            )
        return with_warning(line)
    low_pct = _percent_int(low)
    high_pct = _percent_int(high)
    if clause is not None:
        line = (
            "%s: rate %s over %s answers, interval %d to %d "
            "percent, tier %s: %s."
            % (name, _rate_value_text(rate),
               _scalar_text(node.get("n")), low_pct, high_pct,
               _scalar_text(tier), clause)
        )
    else:
        line = (
            "%s: rate %s over %s answers, interval %d to %d "
            "percent, tier %s."
            % (name, _rate_value_text(rate),
               _scalar_text(node.get("n")), low_pct, high_pct,
               _scalar_text(tier))
        )
    return with_warning(line)


_FIGURE_HEAD_WORDS = (
    "score", "percent", "pct", "share", "gross", "net")

_FIGURE_TAIL_WORDS = (
    "rate", "share", "percent", "pct", "gross", "net", "score")

_FIGURE_MIDDLE_WORDS = tuple(dict.fromkeys(
    _FIGURE_TAIL_WORDS + _HEAD_QUALIFIERS))


def _value_is_figure_form(value):
    """True where a value stands in a figure form the four
    place reading judges: a float, or a string that reads
    as a finite number through _figure_or_none."""
    return isinstance(value, float) or (
        isinstance(value, str)
        and isinstance(_figure_or_none(value), float))


def _key_names_figure(key):
    """True where a key stands in the four place set of the
    generic Simple emitter, on the branch key reading as
    the precision cures state it. The reading stands
    completed on two further limbs. A compound of three
    components whose head is a figure word the branch
    names, whose tail is value, and whose middle component
    is a word the branch itself names, in its tail set or
    in its head qualifier set, stands in the set as the
    two component head compounds stand (Step 17 round 9
    entry S17-R9-016). And the reading stands judged at
    the list branch of _emit in this same form, so a
    figure standing inside a list under a key of the set
    prints at four places as the scalar under that key
    does (Step 17 round 9 entry S17-R9-018)."""
    if not isinstance(key, str):
        return False
    components = _key_components(key)
    return (
        key in _TREND_RATE_KEYS
        or key in ("rate", "share", "percent", "value",
                   "total_weight", "proportion", "ratio",
                   "earned", "weight", "applicable_weight",
                   "design_effect", "score")
        or key in ("rate_value", "rate_pct",
                   "overall_score")
        or key in ("wilson", "wilson_low", "wilson_high")
        or key.startswith("wilson_")
        or "_rate" in key
        or "rate" in components
        or "wilson" in components
        or (components and components[-1] in
            _FIGURE_TAIL_WORDS)
        or (len(components) > 1
            and components[0] in _FIGURE_HEAD_WORDS
            and components[1] == "value")
        or (len(components) == 3
            and components[0] in
            _FIGURE_HEAD_WORDS + ("value",)
            and components[1] in _FIGURE_MIDDLE_WORDS
            and components[2] == "value")
        or key.endswith("_rate")
        or key.endswith("_share")
        or key.endswith("_percent")
        or key.endswith("_gross")
        or key.endswith("_net"))


def _emit(lines, key, value, depth, suppress_anchor_bare=False,
          suppress_none=False, figure_key=False):
    pad = "  " * depth
    if _is_absence(value):
        lines.append("%s%s: not recorded" % (pad, key))
        return
    if isinstance(value, dict):
        if _is_rate_object(value):
            lines.append(pad + _rate_line(key, value))
            return
        if _is_capture_context(value):
            line = _capture_context_line(value)
            if line is not None:
                lines.append(pad + line)
        lines.append("%s%s:" % (pad, key))
        _emit_dict(lines, value, depth + 1, top=False,
                   suppress_none=suppress_none)
        return
    if isinstance(value, list):
        lines.append("%s%s:" % (pad, key))
        # The key standing over a list stands judged in
        # the same form as the key standing over a scalar:
        # a figure item inside a list under a key of the
        # four place set prints at four places, in float
        # form and in string form alike, and the judgement
        # stands carried through a nested list, whose
        # items stand under the same key (Step 17 round 9
        # entry S17-R9-018). An item standing as a record
        # stands judged by its own keys, as before.
        item_figure = figure_key or _key_names_figure(key)
        for item in value:
            if isinstance(item, list):
                _emit(lines, "item", item, depth + 1,
                      suppress_none=suppress_none,
                      figure_key=item_figure)
            elif isinstance(item, dict):
                _emit(lines, "item", item, depth + 1,
                      suppress_none=suppress_none)
            elif item_figure and _value_is_figure_form(item):
                lines.append(
                    "%s  %s" % (pad, _figure_text(item)))
            else:
                lines.append("%s  %s" % (pad, _scalar_text(item)))
        return
    # The four place set stands over the figure, in the
    # form the record carries it: a figure carried as a
    # string under a key the set names prints at four
    # places as its float form does, judged through the
    # same _figure_or_none reading the named positions
    # use, and the bare score key stands in the set, a
    # key the product itself treats as carrying a figure
    # (Step 17 round 5 entries S17-R5-045 and S17-R5-046).
    # The set stands completed on the four further keys
    # the precision cures themselves name as product
    # figure names: rate_value, rate_pct, overall_score,
    # and the bare wilson key (Step 17 round 6 entry
    # S17-R6-038).
    # The branch key reading stands completed under the
    # module component reading: a score compound, a pct
    # compound, and a wilson name standing as a suffix
    # stand in the set as the cured forms do, in float
    # form and in string form alike (Step 17 round 7
    # entry S17-R7-040). The head compound limb of that
    # reading stands completed past score: a percent,
    # pct, share, gross, or net component standing at
    # the head of a compound whose next component is
    # value stands in the set as score_value stands
    # (Step 17 round 8 entry S17-R8-021). That limb
    # stands completed on the three component compounds
    # whose middle component the branch itself names,
    # and the whole reading stands in _key_names_figure,
    # judged at the list branch in the same form (Step
    # 17 round 9 entries S17-R9-016 and S17-R9-018).
    if _value_is_figure_form(value) and _key_names_figure(key):
        lines.append("%s%s: %s" % (pad, key, _figure_text(value)))
        return
    lines.append("%s%s: %s" % (pad, key, _scalar_text(value)))
    if key == "head_hash" and value and not suppress_anchor_bare:
        lines.append("%s%s" % (pad, ANCHOR_LIMIT_SENTENCE))


def _declaration_words(value):
    """The G1 words for one stored importer declaration value,
    or None where the value names none of the three values.
    A declaration carried as a record names its value under
    a value or code member; that member is read here."""
    if isinstance(value, dict):
        for key in ("value", "code", "declaration",
                    "importer_declaration"):
            if value.get(key) is not None:
                return _declaration_words(value[key])
        return None
    if not isinstance(value, str):
        return None
    if value in DECLARATION_WORDS:
        return DECLARATION_WORDS[value]
    normalised = "_".join(value.strip().casefold().replace(
        "-", " ").split())
    return DECLARATION_WORDS.get(normalised)


def _selection_rule_text(node, value):
    """The selection rule text a stated subset declaration
    carries as asserted, where the record carries one: on
    the declaration record itself, or beside it on the frame
    under a selection rule member. No text is invented: a
    declaration carrying no rule text renders its G1 words
    alone."""
    if isinstance(value, dict):
        for key in ("selection_rule", "selection_rule_text",
                    "rule"):
            if isinstance(value.get(key), str) and value[key]:
                return value[key]
    if isinstance(node, dict):
        for key in ("selection_rule", "selection_rule_text"):
            if isinstance(node.get(key), str) and node[key]:
                return node[key]
    return None


def _declaration_line(node, value):
    """The Simple sampling frame declaration line: the
    declaration stated in its G1 words, marked as asserted,
    with a stated subset carrying its selection rule text as
    asserted."""
    words = _declaration_words(value)
    if words is None:
        return "Importer declaration, as asserted: %s." % (
            _scalar_text(value))
    line = "Importer declaration, as asserted: %s" % words
    if words == "a stated subset imported":
        rule = _selection_rule_text(node, value)
        if rule:
            line += ", with the selection rule as asserted: %s" % rule
    return line + "."


_SELECTION_RULE_KEYS = ("selection_rule", "selection_rule_text")


def _is_probe_like(body):
    """True where the artefact is a probe report or a probe
    trend, the surfaces defect E-10 names: a record carrying
    a sampling frame or a gross cited rate anywhere inside
    it, including inside an embedded trend round block."""
    for obj in _walk(body):
        if isinstance(obj, dict) and (
                "sampling_frame" in obj
                or "cited_rate_gross" in obj):
            return True
    return False


def _emit_dict(lines, node, depth, top=True, top_suppress=None,
               suppress_anchor_bare=False, suppress_none=False):
    """Walk one record level in the Simple form.

    The path defaulted companion sentence stands beside the
    artefact's own evaluated page path only, at its top level:
    it is a statement about the path this artefact evaluated,
    and a nested record the artefact carries, such as a robots
    summary, states its own flag as a field in the JSON forms
    and earns no companion sentence of its own here.

    A source_kind value that repeats the same record level's
    kind value states the one value a second time under a
    second name, so it is not printed: the kind line states
    the value once. A source_kind that differs from kind
    stands printed as it stands.
    """
    has_path = "evaluated_page_path" in node
    has_flag = "path_defaulted" in node
    for key, value in node.items():
        if value is None and (
                suppress_none or key in _NONE_SILENT_KEYS):
            # On the probe and trend surfaces no none value
            # prints as a field value: a field holding no
            # value prints nothing. The two named trend
            # fields stand silent on every surface, as the
            # D-28 cure stood.
            continue
        if key == "importer_declaration":
            pad = "  " * depth
            lines.append("%s%s" % (pad, _declaration_line(node, value)))
            continue
        if key == "declaration_unverifiable":
            if value is True:
                pad = "  " * depth
                lines.append(
                    "%s%s" % (pad, DECLARATION_UNVERIFIABLE_STATEMENT))
            continue
        if key in _SELECTION_RULE_KEYS and \
                "importer_declaration" in node:
            # The selection rule text stands inside the
            # declaration line above, as asserted.
            continue
        if key == "path_defaulted" and has_path:
            continue
        if top and top_suppress and key in top_suppress:
            continue
        if key == "source_kind" and node.get("kind") == value \
                and "kind" in node:
            continue
        _emit(lines, key, value, depth,
              suppress_anchor_bare=bool(
                  suppress_anchor_bare and key == "head_hash"),
              suppress_none=suppress_none)
        if key == "evaluated_page_path" and has_flag and top:
            pad = "  " * depth
            if node.get("path_defaulted"):
                lines.append(
                    "%sThe evaluated page path was defaulted." % pad)
            else:
                lines.append(
                    "%sThe evaluated page path was supplied and "
                    "not defaulted." % pad)


def _render_guide_simple(body):
    lines = ["Guide draft."]
    if body.get("refused"):
        lines.append(REFUSAL_SENTENCE)
    elif body.get("opening_text"):
        lines.append("Opening: %s" % body["opening_text"])
    cap_status = body.get("cap_status")
    if not isinstance(cap_status, bool):
        score = body.get("score")
        if isinstance(score, dict):
            cap_status = score.get("cap_status")
    if cap_status is True:
        lines.append(
            "The evidence cap holds the score at 39 for "
            "this run.")
    elif cap_status is False:
        lines.append(
            "The evidence cap does not hold for this run.")
    if body.get("empty_round_notice"):
        notice = body["empty_round_notice"]
        lines.append(notice if isinstance(notice, str) else
                     "This round holds no answers.")
    if body.get("citation_only_sentence"):
        lines.append(body["citation_only_sentence"])
    if body.get("selection_statement"):
        lines.append(body["selection_statement"])
    actions = body.get("actions") or []
    groups = (
        ("cap_first", LABEL_CAP_FIRST),
        ("score_check", LABEL_SCORE_CHECK),
        ("defect_not_score", LABEL_DEFECT),
    )
    grouped = set()
    for class_name, label in groups:
        lines.append(label)
        members = [
            action for action in actions
            if isinstance(action, dict)
            and action.get("worklist_class") == class_name]
        if not members:
            lines.append("  %s" % GROUP_NO_ACTION_LINE)
        for action in members:
            grouped.add(id(action))
            text = action.get("text") or action.get("code") or ""
            lines.append("  %s" % text)
    rest = [a for a in actions if id(a) not in grouped]
    if rest:
        lines.append(
            "After the groups: actions with no class value:")
        for action in rest:
            if isinstance(action, dict):
                lines.append(
                    "  %s" % (action.get("text")
                              or action.get("code") or ""))
            else:
                lines.append("  %s" % _scalar_text(action))
    if body.get("standing_action"):
        if body["standing_action"] == "ACT_THIRD_PARTY":
            lines.append(
                "Standing action: ACT_THIRD_PARTY: third party "
                "mentions stand outside version 1 measurement; "
                "this standing action is manual and unscored.")
        else:
            lines.append(
                "Standing action: %s" % body["standing_action"])
    if body.get("control_failure_notice"):
        notice = body["control_failure_notice"]
        lines.append(notice if isinstance(notice, str)
                     else CONTROL_FAILURE_NOTICE)
    handled = {"opening_text", "actions", "refused",
               "citation_only_sentence", "selection_statement",
               "standing_action", "refusal_sentence",
               "honesty_sentence", "bounds",
               "control_failure_notice", "cap_status",
               "empty_round_notice", "anchor_limit"}
    remainder = {k: v for k, v in body.items() if k not in handled}
    _emit_dict(lines, remainder, 0)
    return lines


def _render_query_set_simple(body):
    lines = ["Query set report."]
    # The total the form counts relate to stands first,
    # before the counts themselves, and every count and
    # name at the foot of the form stands in defined plain
    # words (Step 19 register entry R19-063).
    if body.get("total_count") is not None:
        lines.append(
            "The set holds %s query strings in total."
            % _scalar_text(body.get("total_count")))
    labels = (
        ("asks a question", "interrogative_count"),
        ("compares", "comparison_count"),
        ("names the product", "named_product_count"),
        ("topic only", "bare_topic_count"),
    )
    for label, key in labels:
        if key in body:
            lines.append("%s: %s" % (label, _scalar_text(body[key])))
    lines.append(_OVERLAP_STATEMENT)
    lines.append(_COVERAGE_STATEMENT)
    if body.get("duplicate_count") is not None:
        lines.append(
            "duplicates: %s query strings stand more than "
            "once in the set."
            % _scalar_text(body.get("duplicate_count")))
    if body.get("naming_none_count") is not None:
        lines.append(
            "naming none: %s query strings name neither "
            "the product nor a competitor."
            % _scalar_text(body.get("naming_none_count")))
    if "marker_list_version" in body:
        marker = body.get("marker_list_version")
        if marker is None:
            lines.append(
                "marker list version: no marker list "
                "version stands recorded for this set.")
        else:
            lines.append(
                "marker list version: the counts were read "
                "against marker list version %s."
                % _scalar_text(marker))
    handled = {key for _label, key in labels}
    handled |= {"overlap_statement", "coverage_statement",
                "anchor_limit", "honesty_sentence",
                "total_count", "duplicate_count",
                "naming_none_count", "marker_list_version"}
    remainder = {k: v for k, v in body.items() if k not in handled}
    _emit_dict(lines, remainder, 0)
    return lines


def _is_guide(body):
    return isinstance(body, dict) and "opening_text" in body \
        and "actions" in body


def _is_query_set_report(body):
    return isinstance(body, dict) and "total_count" in body \
        and "interrogative_count" in body


_OVERLAP_STATEMENT = (
    "One query may stand in more than one form, so the form "
    "counts may add to more than the count of query strings."
)

_COVERAGE_STATEMENT = (
    "Form coverage is a property of the question list, not of "
    "visibility."
)


def _is_audit_record(body):
    return isinstance(body, dict) and "checks" in body \
        and "score" in body and "run_id" in body


_AUDIT_STAMP_KEYS = (
    "registry_version", "detector_version", "query_set_version",
    "ruleset_version", "score_ruleset_version",
    "robots_ruleset_version", "methods_note_version",
)


_REASON_CODE_WORDS = {
    "AF_FULL": "the opening window names the product and a "
               "category term in a plain statement",
    "AF_MISSING_TERM": "no product name and no category term "
                       "stands in the opening window",
    "AF_OUTSIDE_WINDOW": "the naming stands outside the "
                         "opening window the check reads",
    "AF_PARTIAL": "the opening window names only part of "
                  "what this check looks for",
    "AF_TERM_NOT_DECLARATIVE": "the naming in the opening "
                               "window is not a plain statement",
    "CIT_COUNT": "the page citations stand counted by their "
                 "distinct targets",
    "CIT_NO_TARGETS": "the page carries no citation target",
    "CIT_SELF_ONLY": "the citations on the page point only "
                     "at the page itself, at the product own "
                     "domain, and at no outside source",
    "CMP_MISSING": "no comparison with another product "
                   "stands on the page",
    "CMP_NA": "the comparison check does not apply to this "
              "page",
    "CMP_OK": "a comparison with another product stands on "
              "the page",
    "CMP_THIN": "the comparison on the page is thin",
    "DESC_DRIFT": "the description on the page differs from "
                  "the registered description",
    "DESC_MISSING": "no description stands on the page",
    "DESC_PRESENT": "the description on the page stands as "
                    "registered",
    "FLF_BOOSTERS": "the page text carries booster wording "
                    "with no evidence beside it",
    "FLF_LONG_LOW_EVIDENCE": "the page is long and carries "
                             "little evidence on it",
    "FLF_OK": "no fluff finding stands on the page",
    "FRESH_FUTURE": "the date on the page stands in the "
                    "future",
    "FRESH_NO_DATE": "no date stands on the page",
    "FRESH_OK": "the date on the page stands inside the "
                "freshness band",
    "FRESH_STALE": "the date on the page stands outside the "
                   "freshness band",
    "QUOTE_NONE_ATTRIBUTED": "no quotation on the page is "
                             "attributed to a source",
    "QUO_COUNT": "the quotations on the page stand counted",
    "QUO_UNATTRIBUTED": "a quotation on the page carries no "
                        "attribution",
    "STAT_COUNT": "the statistics on the page stand counted",
    "STAT_NONE": "no statistic stands on the page",
    "STF_DENSE": "the page repeats its terms densely",
    "STF_OK": "no keyword stuffing finding stands on the "
              "page",
    "STF_REPEAT": "the page repeats one term past the "
                  "stated bound",
    "SUP_OK": "no unproven superlative stands on the page",
    "SUP_UNPROVEN": "a superlative on the page stands "
                    "without proof beside it",
}

_STATUS_WORDS = {
    "none": "no status stands recorded for this check",
    "not_applicable": "the check does not apply to this "
                      "page, and its weight is shared over "
                      "the checks that do apply",
    "fail": "the check failed",
    "warn": "the check carries a warning",
}

_EVIDENCE_CLASS_WORDS = {
    "paper_tested": "the check method was tested in a "
                    "published paper",
    "post_asserted": "the check method is asserted in a "
                     "published post",
    "tool_defined": "the check method is defined by this "
                    "tool itself",
}


def _render_audit_simple(body):
    """The Simple audit artefact in its prose form.

    The artefact opens with the verdict: the score and its
    band, and what the score rests on. It then names the run
    and the snapshot by their identifier lines, states the
    evaluated page path with its defaulted line, and gives
    the top adverse reasons in the order the record stores
    the failed and warned checks, one line per check for the
    whole check set, the next actions pointer, and a pointer
    in words to the Advanced artefact for the same run. The
    nested copies of the record the service carry folds in
    (the snapshot object and the audit_run copy) and the
    page sentences are not printed a second time: depth is
    dropped, and the bounds and honesty lines the common
    tail appends are never dropped.

    Check identifiers, reason codes, and evidence classes
    stand in their stored code form in the check lines. No
    governing statement supplies plain words for that set,
    and none is invented here.
    """
    lines = ["Audit report."]
    score = body.get("score")
    if not isinstance(score, dict):
        score = {}
    value = score.get("value")
    band = score.get("band")
    if value is None or isinstance(value, bool) or not isinstance(
            value, (int, float, Decimal)):
        # A score carried in no figure form, a string
        # included, stands as no figure in the Simple
        # form: no string prints as the run score.
        lines.append("The score for this run stands not recorded.")
    else:
        if isinstance(value, (int, float, Decimal)) \
                and not isinstance(value, bool):
            # The ScoreObject value stands rounded to one
            # decimal place in its stored shape, and the
            # Simple form prints it at that precision, at
            # any magnitude the stored figure carries.
            value_text = str(_quantized_decimal(value, "0.1"))
        else:
            value_text = _scalar_text(value)
        lines.append(
            "The score for this run is %s, in the %s band."
            % (value_text, _scalar_text(band)))
        basis = score.get("applicable_basis")
        if isinstance(basis, dict):
            checks_named = basis.get("applicable_checks") or []
            weight = basis.get("applicable_weight")
            if weight is not None:
                lines.append(
                    "The score rests on %d checks, with a total "
                    "weight of %s."
                    % (len(checks_named), _figure_text(weight)))
            # A check standing not applicable is named here,
            # beside the total its weight was redistributed
            # into, so the head lines and the check list
            # below state the same set of checks.
            for check in body.get("checks") or []:
                if isinstance(check, dict) and \
                        check.get("status") == "not_applicable":
                    lines.append(
                        "The check %s does not apply to this "
                        "page, and its weight of %s is shared "
                        "over the checks that do apply."
                        % (_scalar_text(check.get("check_id")),
                           _figure_text(check.get("weight"))))
        if score.get("cap_status"):
            lines.append(
                "The evidence cap holds the score at 39 for "
                "this run.")
        else:
            lines.append(
                "The evidence cap does not hold for this run.")
        figure = score.get("secondary_figure")
        if isinstance(figure, dict) and isinstance(
                figure.get("value"), (int, float, Decimal)) \
                and not isinstance(figure.get("value"), bool):
            # The secondary figure prints at the same one
            # decimal precision as the headline score, and
            # a value in no figure form prints no figure.
            lines.append(
                "The score on the not applicable as zero "
                "basis is %s. This figure is not a second "
                "score." % str(_quantized_decimal(
                    figure.get("value"), "0.1")))
            if isinstance(figure.get("basis"), str) and \
                    figure.get("basis"):
                lines.append(figure["basis"])
    if isinstance(body.get("sentences"), list) \
            and not body.get("sentences"):
        # The extraction outcome stands empty: the page
        # file held no readable text, stated in plain
        # words at the head of the artefact.
        lines.append(
            "The page file held no readable text, so no "
            "check could run on it.")
    lines.append("run_id: %s" % _scalar_text(body.get("run_id")))
    if body.get("snapshot_id") is not None:
        lines.append(
            "snapshot_id: %s" % _scalar_text(body.get("snapshot_id")))
    if body.get("evaluated_page_path") is not None:
        lines.append(
            "evaluated_page_path: %s"
            % _scalar_text(body.get("evaluated_page_path")))
        if "path_defaulted" in body:
            if body.get("path_defaulted"):
                lines.append("The evaluated page path was defaulted.")
            else:
                lines.append(
                    "The evaluated page path was supplied and "
                    "not defaulted.")
    if body.get("audit_date") is not None:
        lines.append(
            "audit_date: %s" % _scalar_text(body.get("audit_date")))
    checks = body.get("checks")
    if not isinstance(checks, list):
        checks = []
    lines.append("Top adverse reasons:")
    adverse = [
        check for check in checks
        if isinstance(check, dict)
        and check.get("status") in ("fail", "warn")]
    if adverse:
        for check in adverse:
            word = "failed" if check.get("status") == "fail" \
                else "warned"
            lines.append(
                "  %s: %s, reason %s."
                % (_scalar_text(check.get("check_id")), word,
                   _scalar_text(check.get("reason_code"))))
    else:
        lines.append(
            "  No check in this run carries a failed or "
            "warned status.")
    lines.append("Checks:")
    for check in checks:
        if not isinstance(check, dict):
            continue
        # The earned figure is a fraction of the check
        # weight, never points out of the weight: the line
        # states the fraction, the weight it is a fraction
        # of, and the points the fraction is worth toward
        # the score, so the arithmetic a reader does on the
        # line is the arithmetic the score rests on.
        earned = check.get("earned")
        weight = check.get("weight")
        if isinstance(earned, (int, float)) and \
                not isinstance(earned, bool) and \
                isinstance(weight, (int, float)) and \
                not isinstance(weight, bool):
            points = _figure_text(round(earned * weight, 3))
            earned_text = (
                "earned a fraction %s of its weight of %s, "
                "worth %s points toward the score"
                % (_figure_text(earned), _figure_text(weight),
                   points))
        else:
            earned_text = (
                "earned %s of weight %s"
                % (_figure_text(earned), _figure_text(weight)))
        lines.append(
            "  %s: %s, status %s, reason %s, evidence class %s."
            % (_scalar_text(check.get("check_id")),
               earned_text,
               _scalar_text(check.get("status")),
               _scalar_text(check.get("reason_code")),
               _scalar_text(check.get("evidence_class"))))
    # Every word the check lines use stands defined in plain
    # words on this artefact: the reason codes that stand in
    # the lines above, the status words that stand in them,
    # and the evidence classes that stand in them, each with
    # its meaning stated beside it.
    defined = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        code = check.get("reason_code")
        if code in _REASON_CODE_WORDS and code not in defined:
            defined.append(code)
    if defined or checks:
        lines.append("What the check words mean:")
        for code in defined:
            lines.append(
                "  %s: %s." % (code, _REASON_CODE_WORDS[code]))
        statuses = []
        for check in checks:
            if isinstance(check, dict):
                status = check.get("status")
                word = "none" if status is None else str(status)
                if word not in statuses:
                    statuses.append(word)
        for word in statuses:
            if word in _STATUS_WORDS:
                lines.append(
                    "  status %s: %s." % (word, _STATUS_WORDS[word]))
        classes = []
        for check in checks:
            if isinstance(check, dict):
                name = check.get("evidence_class")
                if name in _EVIDENCE_CLASS_WORDS and \
                        name not in classes:
                    classes.append(name)
        for name in classes:
            lines.append(
                "  evidence class %s: %s."
                % (name, _EVIDENCE_CLASS_WORDS[name]))
    lines.append("Next actions:")
    lines.append(
        "  The guide artefact for this run carries the actions "
        "for this run in plain words, from the run_id above.")
    # The page text the run read stands in the artefact as
    # plain text characters, headings first, then the page
    # sentences in their stored order: hostile page material
    # renders as text here, at the one escaping point the
    # body already passed through, and stands as evidence
    # the reader can see rather than a figure alone.
    page_headings = []
    for check in body.get("checks") or []:
        for section in check.get("section_breakdown") or []:
            heading = section.get("heading_text")
            if heading and heading not in page_headings:
                page_headings.append(heading)
    page_sentences = body.get("sentences") or []
    if page_headings or page_sentences:
        lines.append("The page text this run read:")
        for heading in page_headings:
            lines.append("  %s" % heading)
        for sentence in page_sentences:
            lines.append("  %s" % sentence)
    lines.append(
        "The full record for this run stands in the Advanced "
        "artefact for the same run.")
    for key in _AUDIT_STAMP_KEYS:
        if body.get(key) is not None:
            lines.append(
                "%s: %s" % (key, _scalar_text(body.get(key))))
    summary = body.get("robots_summary")
    if isinstance(summary, dict):
        if summary.get("finding_count") is not None:
            lines.append(
                "The robots summary for this run carries %s "
                "findings, and stands in full in the Advanced "
                "artefact for the same run."
                % _scalar_text(summary.get("finding_count")))
        else:
            lines.append(
                "A robots summary for this run stands in the "
                "Advanced artefact for the same run.")
    facts = body.get("facts_counts")
    if _is_absence(facts):
        lines.append("facts_counts: not recorded")
    if body.get("control_failure_notice"):
        notice = body["control_failure_notice"]
        lines.append(notice if isinstance(notice, str)
                     else CONTROL_FAILURE_NOTICE)
    return lines


def _is_status_body(body):
    return isinstance(body, dict) and "chain_result" in body \
        and "home_size" in body and "entry_count" in body


def _is_staleness_view(body):
    return isinstance(body, dict) and "records" in body \
        and "record_count" in body and "home_path" in body \
        and "chain_result" in body


def _render_staleness_simple(body):
    """The Simple form of the staleness view.

    One line names each stored record and its state, with
    its bound versions and the versions in force listed
    under it, the changed axes named where any axis
    differs, and the axes the record class does not store
    stated as not recorded. Over a home with no stored
    record the absence form stands: the words no entries
    beside the anchor limit sentence.
    """
    lines = ["Staleness view."]
    lines.append(
        "home_path: %s" % _scalar_text(body.get("home_path")))
    if body.get("absence") is not None or not body.get("records"):
        lines.append(
            "no entries. %s" % ANCHOR_LIMIT_SENTENCE)
        return lines
    for row in body.get("records") or []:
        if not isinstance(row, dict):
            continue
        kind = row.get("record_kind")
        label = "audit run" if kind == "audit_run" else "round"
        lines.append(
            "Record %s (%s): state %s." % (
                _scalar_text(row.get("record_id")), label,
                _scalar_text(row.get("state"))))
        bound = row.get("bound_versions") or {}
        in_force = row.get("versions_in_force") or {}
        uncompared = row.get("uncompared_axes") or []
        conflicted = row.get("conflicted_axes") or []
        for axis in bound:
            lines.append(
                "  %s: bound %s, in force %s" % (
                    axis, _scalar_text(bound.get(axis)),
                    _scalar_text(in_force.get(axis))))
        # An axis the record binds and no comparison
        # stands on is stated once, as uncompared, never
        # also as not recorded. An axis the record stores
        # in conflict is stated as conflicted, in those
        # words. Only an axis the record does not bind at
        # all stands as not recorded.
        stated = set(bound)
        for axis in row.get("not_recorded_axes") or []:
            if axis in stated:
                continue
            stated.add(axis)
            if axis in conflicted:
                lines.append(
                    "  %s: conflicted, the record stores "
                    "two different values for this axis" % axis)
            elif axis in uncompared:
                lines.append("  %s: uncompared" % axis)
            else:
                lines.append("  %s: not recorded" % axis)
        for axis in uncompared:
            if axis in stated:
                continue
            stated.add(axis)
            if axis in conflicted:
                lines.append(
                    "  %s: conflicted, the record stores "
                    "two different values for this axis" % axis)
            else:
                lines.append("  %s: uncompared" % axis)
        for axis in conflicted:
            if axis in stated:
                continue
            stated.add(axis)
            lines.append(
                "  %s: conflicted, the record stores two "
                "different values for this axis" % axis)
        changed = row.get("changed_axes") or []
        if changed:
            lines.append(
                "  changed axes: %s" % ", ".join(
                    str(axis) for axis in changed))
        if uncompared:
            lines.append(
                "  Uncompared axes: %s. No currency verdict "
                "stands on those axes." % ", ".join(
                    str(axis) for axis in uncompared))
        if row.get("state_note"):
            lines.append("  %s" % row["state_note"])
    lines.append(ANCHOR_LIMIT_SENTENCE)
    return lines


_LINE_BREAK_CHARS = (
    "\n", "\r", "\x0b", "\x0c", "\x85", "\u2028", "\u2029",
    "\x1c", "\x1d", "\x1e")


def _failure_value_text(value):
    """One stored field value in the Simple failure line.

    A value holding one of the separators the line itself
    is built from, the field separator, the sentence
    separator, or the separator phrase, stands quoted, so
    the value cannot forge a second field, a second
    subject, or a second sentence inside the one line:
    the break the separator limb states stands in the
    line structure, and the quoting closes it while the
    value itself stands character for character inside
    its quotes (Step 17 round 5 entry S17-R5-049). A
    quote character the value itself holds stands
    escaped inside the quoting, and a backslash stands
    escaped before it, so the quoted span cannot break
    open at the value own quote and no separator inside
    the value stands outside the quotes after all (Step
    17 round 6 entry S17-R6-041). A value holding no
    separator stands as the plain scalar text stands, as
    before."""
    text = _scalar_text(value)
    if ", " in text or ". " in text or " failed with " in text \
            or any(br in text for br in _LINE_BREAK_CHARS):
        # A line break inside a value stands judged as a
        # separator of the line form itself: the Simple
        # form is built of lines, so the value stands
        # quoted and its line breaks stand escaped inside
        # the quoting, and the one line the builder builds
        # stands as one physical line (Step 17 round 7
        # entry S17-R7-049). The judged set stands
        # completed on the whole standard line boundary
        # set the artefact itself is read by, the vertical
        # tab, the form feed, the next line character, the
        # line separator, and the paragraph separator
        # standing beside the newline and the carriage
        # return (Step 17 round 8 entry S17-R8-023). The
        # set stands completed on the three remaining
        # characters of that same reading, the file
        # separator, the group separator, and the record
        # separator, each standing in its backslash u form
        # inside the quoting (Step 17 round 9 entry
        # S17-R9-015).
        escaped = text.replace("\\", "\\\\").replace(
            '"', '\\"').replace("\r", "\\r").replace(
            "\n", "\\n").replace("\x0b", "\\v").replace(
            "\x0c", "\\f").replace(
            "\x85", "\\u0085").replace(
            "\u2028", "\\u2028").replace(
            "\u2029", "\\u2029").replace(
            "\x1c", "\\u001c").replace(
            "\x1d", "\\u001d").replace(
            "\x1e", "\\u001e")
        return '"%s"' % escaped
    return text


def _failure_record_line(failure):
    """One Simple line for one stored failure record,
    stating the stored payload as stored.

    A complete payload stands in the standing form, its
    operation, its error value, and its subject. A field
    the payload does not hold stands in no form in the
    line: the scalar text for an absent value would
    state a value the store does not hold (Step 17
    round 4 entry S17-R4-074). A partial payload states
    every field it holds under its field name, and only
    a payload holding no field at all stands stated as
    holding none (Step 17 round 5 entry S17-R5-049).
    """
    operation = failure.get("operation")
    error_value = failure.get("error_value")
    subject = failure.get("subject_identity")
    if operation is not None and error_value is not None \
            and subject is not None:
        return (
            "  %s failed with %s, subject %s."
            % (_failure_value_text(operation),
               _failure_value_text(error_value),
               _failure_value_text(subject)))
    # A partial payload states the fields it holds, all
    # of them, under their field names: the stored
    # payload shape carries fields past the three the
    # standing form renders, a date and a rule among
    # them, and the figure fields a recovery record
    # carries, and a payload holding any of them does
    # not stand stated as holding no fields (Step 17
    # round 5 entry S17-R5-049, merging reporting GR-8
    # and White W-04).
    parts = []
    stated = set()
    for key, label in (
            ("operation", "operation"),
            ("error_value", "error"),
            ("subject_identity", "subject"),
            ("date", "date"),
            ("rule_fired", "rule_fired"),
            ("restored_entry_count", "restored_entry_count"),
            ("batch_count", "batch_count")):
        if failure.get(key) is not None:
            parts.append(
                "%s %s" % (label, _failure_value_text(
                    failure.get(key))))
            stated.add(key)
    for key, value in failure.items():
        if key in stated or value is None:
            continue
        # Each further field name stands judged by the
        # quoting the line is built from, as each value
        # is: a name holding one of the line own
        # separators stands quoted with its quote
        # characters escaped, so a separator standing in
        # a field name cannot forge a field boundary, a
        # subject segment, or a sentence in the line
        # (Step 17 round 6 entry S17-R6-041).
        parts.append(
            "%s %s" % (_failure_value_text(key),
                       _failure_value_text(value)))
    if not parts:
        return (
            "  failure record: no fields stand in the "
            "stored payload.")
    return "  failure record: %s." % ", ".join(parts)


def _simple_opening_summary(body):
    """The prose opening of a Simple artefact on the generic
    surfaces (Step 19 item R19-055).

    The Simple form is a prose artefact: it opens with a
    summary in plain words stating what the record is and
    what it shows, before any field by field detail stands.
    The summary states only what the record itself carries.
    """
    if "passed" in body and "chain_result" in body:
        if body.get("passed"):
            return [
                "Verification of the journal in this product "
                "home: the chain verifies, so the journal "
                "stands internally consistent as stored."
            ]
        return [
            "Verification of the journal in this product "
            "home: the chain does not verify, so the journal "
            "as stored does not stand internally consistent."
        ]
    if "head_hash" in body or "entry_count" in body:
        count = body.get("entry_count")
        if count == 0:
            return [
                "Status of the journal in this product home: "
                "the journal holds no entries yet."
            ]
        return [
            "Status of the journal in this product home: "
            "the journal holds %s entries, and the figures "
            "below state its size and what room stands "
            "before its limits." % _scalar_text(count)
        ]
    if "rates" in body or "round_metrics" in body:
        return [
            "Probe report for this round: the figures below "
            "state how often the product was named, named "
            "early, and cited in the sampled answers of the "
            "round, with the counts those figures rest on."
        ]
    if "findings" in body or "robots_file" in body:
        return [
            "Robots report: the findings below state, for "
            "each crawler purpose, whether the robots file "
            "lets it reach the evaluated page path."
        ]
    if "delta" in body or "series_break" in body:
        return [
            "Probe trend: the figures below compare two "
            "rounds of sampled answers and state how the "
            "named and cited figures moved between them."
        ]
    return [
        "The record of this call stands below, stated in "
        "plain words field by field."
    ]


def _render_simple(body):
    if not isinstance(body, dict):
        return _scalar_text(body)
    if _is_staleness_view(body):
        # The staleness view carries no score, so the honesty
        # sentence, which speaks of this score, does not
        # close it (Step 19 register entry R19-059).
        lines = _render_staleness_simple(body)
        return "\n".join(lines) + "\n"
    if _is_guide(body):
        lines = _render_guide_simple(body)
    elif _is_query_set_report(body):
        lines = _render_query_set_simple(body)
    elif _is_audit_record(body):
        lines = _render_audit_simple(body)
    else:
        lines = _simple_opening_summary(body)
        top_suppress = set()
        if _is_probe_like(body):
            # The probe report carries the anchor limit
            # sentence in its closing block, not as a field
            # line (Step 19 register entry R19-097).
            top_suppress.add("anchor_limit")
            # The cited figure definitions stand in the
            # closing block in plain words, not as a raw
            # nested field (Step 19 register entry R19-003).
            top_suppress.add("rate_definitions")
        suppress_anchor_bare = False
        if _is_invocation_computed(body):
            top_suppress.add("honesty_sentence")
            if _is_report_like(body) and \
                    _find_bounds(body) is not None:
                top_suppress.add("bounds")
            if "anchor_limit" in body:
                top_suppress.add("anchor_limit_sentence")
            if "anchor_limit" in body or \
                    "anchor_limit_sentence" in body:
                suppress_anchor_bare = True
        if body.get("control_failure_notice"):
            # The notice stands in Simple in its own words,
            # as a line of its own, never as a field line
            # and never in a warning list (Step 19 queue
            # addition U-07).
            top_suppress.add("control_failure_notice")
            top_suppress.add("control_failed")
            lines.append(
                "Control failure notice: a control outcome "
                "in this round contradicts its asserted "
                "kind. The notice stands in its own form, "
                "beside the round figures.")
        if _is_status_body(body):
            # The status figures carry their units, the
            # head hash stands once in one vocabulary, and
            # the answer average states what it averages
            # and in what unit (Step 19 register entry
            # R19-061).
            top_suppress.update(
                ("head", "head_hash", "home_size",
                 "entry_count", "capacity_outlook"))
            head_hash = body.get("head_hash") or body.get("head")
            if head_hash:
                lines.append(
                    "The journal head hash (head_hash) is %s."
                    % _scalar_text(head_hash))
            else:
                lines.append(
                    "No head hash stands (head_hash): the "
                    "journal holds no entries.")
            lines.append(
                "entry_count: %s entries stand in the "
                "journal."
                % _figure_text(body.get("entry_count")))
            lines.append(
                "The product home size (home_size) is %s "
                "bytes on disk."
                % _figure_text(body.get("home_size")))
            outlook = body.get("capacity_outlook")
            if isinstance(outlook, dict):
                if outlook.get("entries_remaining") is not None:
                    lines.append(
                        "Entries remaining before the "
                        "journal length limit: %s."
                        % _figure_text(
                            outlook.get("entries_remaining")))
                if outlook.get(
                        "total_home_size_remaining") is not None:
                    lines.append(
                        "Home size remaining before the "
                        "total home size limit: %s bytes."
                        % _figure_text(outlook.get(
                            "total_home_size_remaining")))
                average = outlook.get("answer_average")
                if isinstance(average, dict) and \
                        average.get("value") is not None:
                    lines.append(
                        "The average imported answer size "
                        "is %s characters, an estimate over "
                        "the imported answers whose sizes "
                        "stand recorded."
                        % _figure_text(average.get("value")))
                elif isinstance(average, str):
                    lines.append("Answer average: %s." % average)
        findings = body.get("findings")
        if isinstance(findings, list) and findings:
            # The robots result for the evaluated path
            # stands in plain words at the head, and the
            # labels the findings carry stand defined on
            # the surface (Step 19 register entry R19-062).
            allowed = sum(
                1 for finding in findings
                if isinstance(finding, dict)
                and finding.get("outcome") == "allowed")
            barred = sum(
                1 for finding in findings
                if isinstance(finding, dict)
                and finding.get("outcome") == "disallowed")
            lines.append(
                "For the evaluated page path %s, the robots "
                "file lets %d of the %d listed crawlers "
                "reach it and bars %d."
                % (_scalar_text(body.get("evaluated_page_path")),
                   allowed, len(findings), barred))
            lines.append(
                "evidence_label: the label stating how the "
                "crawler purpose in a finding stands "
                "evidenced, directly verified where the "
                "purpose stands verified against its source, "
                "secondary transcription where it stands "
                "transcribed from a secondary source.")
            lines.append(
                "purpose_prose_evidence_label: the same "
                "evidence label carried in the prose form "
                "of the finding.")
            if body.get("next_refresh_due_date") is not None:
                lines.append(
                    "next_refresh_due_date: the date by "
                    "which the shipped crawler table stands "
                    "due for its next refresh, here %s."
                    % _scalar_text(
                        body.get("next_refresh_due_date")))
        if "evaluated_page_path" in body:
            lines.append(
                "evaluated_page_path: %s"
                % _scalar_text(body.get("evaluated_page_path")))
            if "path_defaulted" in body:
                if body.get("path_defaulted"):
                    lines.append(
                        "The evaluated page path was defaulted.")
                else:
                    lines.append(
                        "The evaluated page path was supplied "
                        "and not defaulted.")
            top_suppress.update(
                ("evaluated_page_path", "path_defaulted"))
        _emit_dict(lines, body, 0, top_suppress=top_suppress,
                   suppress_anchor_bare=suppress_anchor_bare,
                   suppress_none=_is_probe_like(body))
        if "rates" in body and "empty_answer_count" in body:
            empty_count = body.get("empty_answer_count")
            if isinstance(empty_count, int) and \
                    not isinstance(empty_count, bool) and \
                    empty_count != 0:
                lines.append(EMPTY_ANSWER_WARNING % empty_count)
    failure_records = body.get("failure_records")
    if isinstance(failure_records, list) and failure_records:
        lines.append("Failure records.")
        for failure in failure_records:
            if not isinstance(failure, dict):
                continue
            lines.append(_failure_record_line(failure))
    bounds = _find_bounds(body)
    if bounds is not None and _is_report_like(body):
        lines.append("Bounds.")
        lines.append("What this run establishes:")
        for item in bounds.get("establishes") or []:
            lines.append("  %s" % _scalar_text(item))
        lines.append("What this run does not establish:")
        for item in bounds.get("does_not_establish") or []:
            lines.append("  %s" % _scalar_text(item))
    if _carries_rate_terms(body):
        lines.append(DEFINITIONS_LINE)
        lines.append(CITED_RATE_DEFINITIONS_LINE)
        lines.append(TIER_CLAUSES_LINE)
    if _carries_score_band(body):
        lines.append(SCORE_BAND_SCALE_LINE)
    # The anchor limit sentence stands in the closing
    # block of every Simple report artefact, the audit,
    # guide, probe report, and query set report included,
    # so the limit travels with the artefact when it is
    # copied on its own (brief Section 5.5 commitment (c);
    # Step 19 register entry R19-097).
    if _is_audit_record(body) or _is_guide(body) or \
            _is_probe_like(body) or _is_query_set_report(body):
        lines.append(ANCHOR_LIMIT_SENTENCE)
    # The honesty sentence speaks of this score, so it
    # closes only the surfaces that carry a score or a
    # report of one: the audit, the guide, the probe report
    # and trend, and the robots report. An operation result
    # that produces no score, a product registration, a
    # round naming, an import, a status, a verify, does not
    # close with it (Step 19 register entry R19-059).
    if _is_audit_record(body) or _is_guide(body) or \
            _is_probe_like(body) or "findings" in body or \
            "robots_file" in body or "delta" in body or \
            "series_break" in body:
        lines.append(HONESTY_SENTENCE)
    return "\n".join(lines) + "\n"


def _carries_rate_terms(body):
    for obj in _walk(body):
        if _is_rate_object(obj) or "effective_n" in obj \
                or "tier" in obj:
            return True
    return False


def _carries_score_band(body):
    for obj in _walk(body):
        if "band" in obj and "value" in obj:
            return True
    return False


_INTERROGATIVE_WORDS = (
    "what", "which", "how", "why", "when", "where", "who",
    "whose", "can", "could", "should", "would", "is", "does",
    "do", "did",
)

_COMPARISON_MARKERS = (
    "vs", "versus", "compared to", "compared with",
    "alternative", "alternatives", "better than",
    "difference between",
)


def _fold(text):
    folded = unicodedata.normalize("NFC", str(text)).casefold()
    return " ".join(folded.split())


# The one word token form, shared in shape with the
# guide module tokeniser: a number stands as one token
# whole, carrying its thousands separators in their
# groups, its decimal parts at every point it carries,
# and a letter suffix standing on its last part, so no
# separator the number is written with splits it (Step
# 17 round 5 entry S17-R5-047). The form stands completed
# on the dressings the round 6 entry names: a suffix
# carrying a trailing digit stands on the last part with
# its digit, an exponent part stands in the number, and
# an underscore grouping stands as a thousands grouping
# does (Step 17 round 6 entry S17-R6-039). The form stands
# completed on the dressings the round 7 entry names: an
# apostrophe grouping stands as a thousands grouping, an
# underscore grouping stands inside the exponent part, and
# an underscore digit stands inside the letter suffix
# (Step 17 round 7 entry S17-R7-041). The suffix limb
# stands completed again on the composed dressings: a
# trailing digit standing before an underscore digit
# group, and underscore digit groups standing repeated
# inside the suffix, as the exponent limb already admits
# its grouping repeated (Step 17 round 8 entry
# S17-R8-022).
_WORD_TOKEN_PATTERN = (
    r"\d+(?:[,_']\d{3})*(?:\.\d+)*"
    r"(?:[eE][+-]?\d+(?:_\d+)*)?"
    r"(?:[^\W\d_]+[0-9]*(?:_\d+)*)*"
    r"|[^\W_]+(?:\.\d+)*")


def _word_tokens(text):
    """The word tokens of one text, on the matching form
    the brief states at Section 5.1: case insensitive
    over word tokens, words as alphanumeric tokens, and
    a decimal number counting as one word, so a decimal
    point standing between digits does not split the
    number it stands in (Step 17 round 4 entry
    S17-R4-048)."""
    return re.findall(
        _WORD_TOKEN_PATTERN, _fold(text), flags=re.UNICODE)


def _tokens_match(tokens, entry_tokens):
    """True where an entry stands in a token list as a
    consecutive token sequence. An entry folding to no
    token matches nothing (Step 17 round 3 entries
    S17-R3-056 and S17-R3-057)."""
    if not tokens or not entry_tokens:
        return False
    width = len(entry_tokens)
    return any(
        tokens[index:index + width] == entry_tokens
        for index in range(len(tokens) - width + 1))


def _name_in(tokens, names):
    return any(
        _tokens_match(tokens, _word_tokens(name))
        for name in names if isinstance(name, str))


def _classify_query(query, product_names, competitor_names):
    tokens = _word_tokens(query)
    interrogative = any(
        _tokens_match(tokens, [word])
        for word in _INTERROGATIVE_WORDS)
    comparison = any(
        _tokens_match(tokens, _word_tokens(marker))
        for marker in _COMPARISON_MARKERS)
    named_product = _name_in(tokens, product_names)
    named_competitor = _name_in(tokens, competitor_names)
    if named_competitor:
        # The comparison form also stands where a
        # registered competitor name or alias stands in
        # the query (Step 17 round 3 entry S17-R3-054).
        comparison = True
    bare_topic = not (interrogative or comparison or named_product
                      or named_competitor)
    return {
        "interrogative": interrogative,
        "comparison": comparison,
        "named_product": named_product,
        "naming_none": not (named_product or named_competitor),
        "bare_topic": bare_topic,
    }


def _collection(value, name):
    """One collection field in its collection form.

    A string value is one item, never its characters. A
    list or tuple stands as its items. Any other shape is
    refused in the open, as a shape the derivation cannot
    read as a collection.
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    raise ValueError(
        "%s must stand as a list of items or as one item, "
        "not as %s" % (name, type(value).__name__))


def derive_query_set_report(product):
    """Derive the QuerySetReport artefact over one Product record.

    The derivation runs over the one stored record alone: each
    query string is classified by surface form only, under the
    four forms, and the counts stand as the artefact's figures.
    No second store is read and nothing is written.
    """
    record = _plain(product)
    query_set = record.get("query_set")
    queries = []
    query_set_version = record.get("query_set_version")
    if isinstance(query_set, dict):
        queries = _collection(
            query_set.get("queries") or query_set.get("items"),
            "query set queries")
        query_set_version = query_set.get("query_set_version") \
            or query_set.get("version") or query_set_version
    elif isinstance(query_set, (list, tuple, str)):
        queries = _collection(query_set, "query set")
    product_names = [record.get("name")] + _collection(
        record.get("aliases"), "product aliases")
    competitor_names = []
    for competitor in _collection(
            record.get("competitors"), "competitors"):
        if isinstance(competitor, dict):
            competitor_names.append(competitor.get("name"))
            aliases = competitor.get("aliases")
            if aliases is not None:
                # Competitor aliases stand judged here as
                # at the product record reader: a form that
                # is no list of strings is a type swapped
                # field, refused in the open instead of
                # standing converted by string form into a
                # name (Step 17 round 3 entry S17-R3-058).
                if not isinstance(aliases, (list, tuple)) or any(
                        not isinstance(item, str) for item in aliases):
                    raise ValueError(
                        "competitor aliases must stand as a list "
                        "of strings, not as %r" % (aliases,))
                competitor_names.extend(aliases)
        elif competitor:
            competitor_names.append(competitor)
    counts = {
        "total_count": len(queries),
        "interrogative_count": 0,
        "comparison_count": 0,
        "named_product_count": 0,
        "bare_topic_count": 0,
        "duplicate_count": 0,
        "naming_none_count": 0,
    }
    seen = set()
    for query in queries:
        folded = _fold(query)
        if folded in seen:
            counts["duplicate_count"] += 1
        seen.add(folded)
        classes = _classify_query(query, product_names,
                                  competitor_names)
        if classes["interrogative"]:
            counts["interrogative_count"] += 1
        if classes["comparison"]:
            counts["comparison_count"] += 1
        if classes["named_product"]:
            counts["named_product_count"] += 1
        if classes["bare_topic"]:
            counts["bare_topic_count"] += 1
        if classes["naming_none"]:
            counts["naming_none_count"] += 1
    marker_version = record.get("marker_list_version")
    if marker_version is None:
        marker_version = {"recorded": False, "state": _ABSENCE_STATE}
    report = {
        "product_id": record.get("product_id"),
        "query_set_version": query_set_version,
        "marker_list_version": marker_version,
        "overlap_statement": _OVERLAP_STATEMENT,
        "coverage_statement": _COVERAGE_STATEMENT,
    }
    report.update(counts)
    return report


def query_set_report(product, form="advanced"):
    """The QuerySetReport for one product, in one reading form."""
    return render(derive_query_set_report(product), form=form)


def _finding_key(finding):
    return (
        finding.get("token"),
        finding.get("purpose_class"),
        finding.get("operator"),
    )


def _finding_text(finding):
    return finding.get("winning_rule")


def _rule_text(rule):
    """One group rule as written, from any of its stated forms:
    a plain string, a record carrying its as_written text, or a
    record carrying a kind and a path."""
    if isinstance(rule, str):
        return rule
    if isinstance(rule, dict):
        if rule.get("as_written"):
            return rule["as_written"]
        if rule.get("text"):
            return rule["text"]
        kind = rule.get("kind") or rule.get("name")
        path = rule.get("path") or rule.get("value")
        if kind and path is not None:
            return "%s: %s" % (kind, path)
    return None


def _group_rules(evaluation):
    """The per group rule texts an evaluation carries, keyed by
    group token folded to lower case, as evaluation keys them.

    Agent tokens combine case insensitively at evaluation,
    so the groups stand keyed the same way here, with the
    first spelling seen kept beside the key for display.
    The reading accepts the forms in which a robots evaluation
    can carry its files' group rules beside its findings: a
    groups list whose entries carry agents and rules, in the
    form the robots parser states them; a group_rules record
    keyed by token; or a flat rules list whose entries carry
    their supplying group. An evaluation that carries no group
    rule data yields an empty record, and no rule text is
    derived from its findings, because a finding states the
    rule that won at the evaluated path and no other rule.
    """
    groups = {}
    if not isinstance(evaluation, dict):
        return groups

    def note(agent, texts):
        key = str(agent).lower()
        entry = groups.setdefault(
            key, {"display": str(agent), "texts": []})
        entry["texts"].extend(texts)

    stated = evaluation.get("groups") or \
        evaluation.get("parsed_groups")
    if isinstance(stated, list):
        for group in stated:
            if not isinstance(group, dict):
                continue
            agents = group.get("agents") or group.get("tokens") \
                or []
            if isinstance(agents, str):
                agents = [agents]
            texts = []
            for rule in group.get("rules") or []:
                text = _rule_text(rule)
                if text is not None:
                    texts.append(text)
            for agent in agents:
                note(agent, texts)
        return groups
    keyed = evaluation.get("group_rules")
    if isinstance(keyed, dict):
        for token, rules in keyed.items():
            texts = []
            for rule in rules or []:
                text = _rule_text(rule)
                if text is not None:
                    texts.append(text)
            note(token, texts)
        return groups
    flat = evaluation.get("rules") or evaluation.get(
        "wildcard_rules")
    if isinstance(flat, list):
        for rule in flat:
            if not isinstance(rule, dict):
                continue
            token = rule.get("supplying_group") or \
                rule.get("group") or rule.get("agent") or "*"
            text = _rule_text(rule)
            if text is not None:
                note(token, [text])
    return groups


def _rule_text_changed_rows(first, second, existing):
    """Changed rows from the two files' group rule texts.

    A preview is a comparison of the two files, and a rule
    that stands in one file's rule set for a group and not
    in the other's is a changed row of the preview even
    where that rule does not win at the evaluated path, so
    no finding differs there. The comparison is of rule
    sets, never of rule positions: a rule is identified by
    its group and its text, so a pure reorder changes
    nothing and one inserted rule reports one row. Groups
    stand keyed as evaluation keys them, case insensitively.

    Rows stand only for the crawler table and for the
    wildcard group: a table token row carries that row's
    purpose class, and the wildcard group, which supplies
    every purpose class and no one class, carries null.
    A group naming no table token generates no finding on
    either side and reports no row. A change the finding
    rows already state, with the same two texts on any
    row, is not repeated, and a rule that still stands in
    the rule set evaluation applies for its token, because
    its group was replaced by a group supplying the same
    rule, is not reported as removed or added.
    """
    from collections import Counter
    rows = []
    first_groups = _group_rules(first)
    second_groups = _group_rules(second)
    table = {}
    try:
        from citeline.robots import CRAWLER_TABLE
        for entry in CRAWLER_TABLE:
            table[entry["token"].lower()] = entry
    except Exception:
        table = {}
    # A candidate pair is already stated only where a
    # finding row of its own token carries the same two
    # texts. A pair another token's finding carries does
    # not state this token's rule set change.
    finding_pairs = {}
    finding_pairs_any = set()
    for row in existing:
        finding_pairs.setdefault(row.get("token"), set()).add(
            (row.get("first_finding"), row.get("second_finding")))
        finding_pairs_any.add(
            (row.get("first_finding"), row.get("second_finding")))
    seen = {
        (row.get("token"), row.get("first_finding"),
         row.get("second_finding"))
        for row in existing
    }

    def effective(groups, key):
        if key in groups:
            return groups[key]["texts"]
        if "*" in groups:
            return groups["*"]["texts"]
        return []

    tokens = list(first_groups)
    for token in second_groups:
        if token not in tokens:
            tokens.append(token)
    for token in tokens:
        if token != "*" and token not in table:
            continue
        first_texts = (first_groups.get(token) or {}).get(
            "texts") or []
        second_texts = (second_groups.get(token) or {}).get(
            "texts") or []
        # The pairing below reads the two lists in a fixed
        # sorted order, never in the order the rules stand
        # written in either file, so one rule set change
        # pairs the same way and reports at one size under
        # either rule order.
        removed = sorted(
            (Counter(first_texts) - Counter(second_texts)).elements())
        added = sorted(
            (Counter(second_texts) - Counter(first_texts)).elements())
        if not removed and not added:
            continue
        if token == "*":
            display = "*"
            purpose = None
        else:
            display = table[token]["token"]
            purpose = table[token]["purpose_class"]
        eff_first = effective(first_groups, token) \
            if token != "*" else first_texts
        eff_second = effective(second_groups, token) \
            if token != "*" else second_texts
        # Removed and added texts pair into changed rows,
        # one row per pair, with any leftover standing as
        # a removal or an addition on its own. A text a
        # finding row of this token already states, as the
        # rule removed or the rule added at the evaluated
        # path, stands out of the pairing on a named token:
        # pairing it with another text would state it a
        # second time, as removed in the finding row and
        # as changed in a rule text row. It stands reserved
        # as a leftover instead, where the finding pair
        # judgement below suppresses it, and the texts it
        # would have paired with pair among themselves.
        # The wildcard group stands outside this reading:
        # its candidate judgement stands exactly as the
        # governed wildcard form records it.
        stated_before = set()
        stated_after = set()
        pair_removed = removed
        pair_added = added
        reserved = []
        if token != "*":
            pairs_here = finding_pairs.get(display, ())
            stated_before = {
                before for before, _after in pairs_here
                if before is not None
            }
            stated_after = {
                after for _before, after in pairs_here
                if after is not None
            }
            if stated_before or stated_after:
                # The reservation counts by standing, not
                # by set: a text a finding row of this
                # token states stands reserved at each of
                # its standings in the list, so a winning
                # text written more than once for the
                # token never pairs at any standing.
                pair_removed = []
                for text in removed:
                    if text in stated_before:
                        reserved.append((text, None))
                    else:
                        pair_removed.append(text)
                pair_added = []
                for text in added:
                    if text in stated_after:
                        reserved.append((None, text))
                    else:
                        pair_added.append(text)
        candidates = []
        paired = min(len(pair_removed), len(pair_added))
        for index in range(paired):
            candidates.append(
                (pair_removed[index], pair_added[index]))
        for text in pair_removed[paired:]:
            candidates.append((text, None))
        for text in pair_added[paired:]:
            candidates.append((None, text))
        candidates.extend(reserved)
        for before, after in candidates:
            if before is not None and before in eff_second:
                continue
            if after is not None and after in eff_first:
                continue
            # The wildcard group supplies every table row,
            # so a pair the finding rows state on any row
            # already states the wildcard candidate, the
            # governed form the S17-R1X-036 reconciliation
            # records. A named token is judged on its own
            # rows alone.
            stated = finding_pairs_any if display == "*" \
                else finding_pairs.get(display, ())
            if (before, after) in stated:
                continue
            if display != "*":
                # A reserved leftover states one text a
                # finding row already states on that side,
                # so the finding row states it and no rule
                # text row stands for it.
                if before is None and after in stated_after:
                    continue
                if after is None and before in stated_before:
                    continue
            key = (display, before, after)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "token": display,
                "purpose_class": purpose,
                "first_finding": before,
                "second_finding": after,
                "defect_flag_change": None,
            })
    return rows


def assemble_robots_preview(first, second, evaluated_page_path="/",
                            path_defaulted=True,
                            first_capture_date=None,
                            second_capture_date=None):
    """Assemble the RobotsPreview artefact from two evaluations.

    The two inputs are the two files' RobotsReport shaped
    evaluations, as the producing evaluation states them. The
    artefact stands unstored: this assembly writes nothing and
    appends nothing. One entry stands per changed row only,
    where the finding under the second file differs from the
    finding under the first, or where a group rule text the
    evaluations carry stands written differently in the
    second file. A defect flag change stands only where a
    search purpose row carries one, on the DQ-3 terms the
    stored findings state. Both capture date fields stand in
    the artefact in every case: a supplied date stands as its
    value, and an unsupplied date stands null beside its
    stated omission, inside the one capture_dates record.
    """
    first = _plain(first)
    second = _plain(second)
    # An empty string stands as no date supplied, never
    # as a supplied date value.
    if first_capture_date == "":
        first_capture_date = None
    if second_capture_date == "":
        second_capture_date = None
    first_findings = first.get("findings") or []
    second_findings = second.get("findings") or []
    second_by_key = {}
    for finding in second_findings:
        if isinstance(finding, dict):
            second_by_key[_finding_key(finding)] = finding
    changed_rows = []
    for finding in first_findings:
        if not isinstance(finding, dict):
            continue
        other = second_by_key.get(_finding_key(finding))
        if other is None:
            continue
        if _finding_text(other) == _finding_text(finding) and \
                other.get("outcome") == finding.get("outcome"):
            continue
        defect_change = None
        if finding.get("purpose_class") == "search":
            before = finding.get("defect_flag")
            after = other.get("defect_flag")
            if before != after:
                defect_change = {"from": before, "to": after}
        changed_rows.append({
            "token": finding.get("token"),
            "purpose_class": finding.get("purpose_class"),
            "first_finding": _finding_text(finding),
            "second_finding": _finding_text(other),
            "defect_flag_change": defect_change,
        })
    changed_rows.extend(
        _rule_text_changed_rows(first, second, changed_rows))
    preview = {
        "first_sha256": first.get("robots_snapshot_sha256"),
        "second_sha256": second.get("robots_snapshot_sha256"),
        "sha256_pair": [
            first.get("robots_snapshot_sha256"),
            second.get("robots_snapshot_sha256"),
        ],
        "first_capture_date": first_capture_date,
        "second_capture_date": second_capture_date,
        "capture_dates": {
            "first": first_capture_date,
            "second": second_capture_date,
        },
        "evaluated_page_path": evaluated_page_path,
        "path_defaulted": bool(path_defaulted),
        "table_version": first.get("table_version"),
        "table_snapshot_date": first.get("table_snapshot_date"),
        "robots_ruleset_version": first.get(
            "robots_ruleset_version"),
        "finding_counts": {
            "first": len(first_findings),
            "second": len(second_findings),
        },
        "first_finding_count": len(first_findings),
        "second_finding_count": len(second_findings),
        "changed_rows": changed_rows,
    }
    if first_capture_date is None:
        preview["first_capture_date_omission"] = (
            "The first file asserted capture date is omitted: "
            "no date was supplied for that file.")
    if second_capture_date is None:
        preview["second_capture_date_omission"] = (
            "The second file asserted capture date is omitted: "
            "no date was supplied for that file.")
    # The capture dates are operator asserted and stand
    # shown as asserted, on the IM7-DIV-7 landing: each
    # supplied date carries its asserted marker, and each
    # unsupplied date carries its omission above.
    preview["capture_dates_asserted"] = {
        "first": {
            "date": first_capture_date,
            "asserted": first_capture_date is not None,
        },
        "second": {
            "date": second_capture_date,
            "asserted": second_capture_date is not None,
        },
    }
    preview["capture_date_assertion"] = (
        "Capture dates in this preview are operator "
        "asserted dates, shown as asserted.")
    try:
        import datetime as _datetime
        first_day = _datetime.date.fromisoformat(
            str(first_capture_date))
        second_day = _datetime.date.fromisoformat(
            str(second_capture_date))
        if second_day < first_day:
            preview["capture_date_order_note"] = (
                "The second file asserted capture date "
                "stands before the first file asserted "
                "capture date.")
    except (TypeError, ValueError):
        pass
    # The diff's stated scope stands declared in the
    # artefact: it covers findings and rule texts only.
    # Evaluation fields outside that scope that differ
    # between the two files stand named with both values,
    # so an empty changed list never reads as no
    # difference of any kind.
    preview["diff_scope"] = (
        "This diff covers findings and rule texts only. "
        "Changes to other evaluation fields are not shown "
        "as changed rows.")
    outside = {}
    # Any evaluation field outside the diff scope that
    # differs stands named, not only two named fields.
    # The fields the artefact itself carries in another
    # form stand outside this record: the findings and
    # the group rule texts are the diff scope itself, the
    # snapshot hashes and asserted capture dates stand
    # named in the artefact in their own fields, and the
    # evaluated path, its defaulted flag, and the finding
    # counts are the same call's own inputs and figures.
    outside_excluded = {
        "findings", "groups", "parsed_groups", "group_rules",
        "rules", "wildcard_rules", "robots_snapshot_sha256",
        "robots_snapshot_asserted_capture_date",
        "evaluated_page_path", "path_defaulted",
        "finding_count",
    }
    for name in sorted(set(first) | set(second)):
        if name in outside_excluded:
            continue
        if first.get(name) != second.get(name):
            outside[name] = [first.get(name), second.get(name)]
    if outside:
        preview["evaluation_differences_outside_diff"] = outside
    return preview


def robots_preview(first, second, form="advanced", **inputs):
    """The RobotsPreview over two evaluations, in one form."""
    artefact = assemble_robots_preview(first, second, **inputs)
    return render(artefact, form=form)
