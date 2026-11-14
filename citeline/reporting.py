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
import unicodedata

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
        "may be relied on and reported as the round's "
        "result"),
}

TIER_CLAUSES_LINE = (
    "Tier clauses: count only means no rate is given, only "
    "the count of answers; exploratory means a rate is shown "
    "as an early indication that carries little weight; "
    "provisional means a rate is shown as a working figure "
    "that may still change as more answers are added; "
    "reportable means a rate is shown as a figure that may "
    "be relied on and reported as the round's result."
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
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
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
    """Stand the anchor limit sentence beside any head hash."""
    for obj in _walk(body):
        if obj.get("head_hash"):
            obj.setdefault("anchor_limit", ANCHOR_LIMIT_SENTENCE)


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
    if body.get("refused") or \
            body.get("refusal_code") == "NO_REUSABLE_EVIDENCE":
        body.setdefault("refusal_sentence", REFUSAL_SENTENCE)
    citation_only = body.get("refusal_code") == _CITATION_ONLY_CODE
    if not citation_only:
        for action in body.get("actions") or []:
            if isinstance(action, dict) and \
                    _CITATION_ONLY_CODE in (
                        action.get("code"),
                        action.get("check_or_outcome")):
                citation_only = True
    if citation_only:
        body.setdefault("citation_only_sentence",
                        CITATION_ONLY_SENTENCE)
    for value in _selection_marker_values(body):
        if not isinstance(value, str):
            continue
        lowered = value.lower()
        if "fallback" in lowered:
            body.setdefault("selection_statement",
                            FALLBACK_STATEMENT)
        elif "preference" in lowered or "preferred" in lowered:
            body.setdefault("selection_statement",
                            PREFERENCE_STATEMENT)


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
    if not isinstance(body, dict):
        return
    stated = None
    flagged = False
    for obj in _walk(body):
        for key in ("control_failure_notice", "control_notice",
                    "failed_control_notice"):
            if key in obj and obj[key]:
                stated = obj[key]
        for key in ("control_failed", "control_failure"):
            if obj.get(key) is True:
                flagged = True
    if stated is None and not flagged:
        return
    if isinstance(stated, str):
        body.setdefault("control_failure_notice", stated)
    elif isinstance(stated, dict):
        body.setdefault("control_failure_notice", stated)
    else:
        body.setdefault("control_failure_notice",
                        CONTROL_FAILURE_NOTICE)


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


def _advanced_body(record):
    """The Advanced payload: the stored record, with the common
    carry stood beside the values it travels with."""
    body = copy.deepcopy(_plain(record))
    if not isinstance(body, dict):
        return body
    _apply_anchor_limit(body)
    _apply_small_sample_warning_text(body)
    _apply_methods_note_version(body)
    _apply_trend_field_names(body)
    if _is_invocation_computed(body):
        carried = _find_bounds(body)
        if carried is not None:
            carried["establishes"] = [
                COMPUTED_FIGURES_ESTABLISHES]
    if _is_report_like(body):
        body.setdefault("honesty_sentence", HONESTY_SENTENCE)
        if _find_bounds(body) is None:
            body["bounds"] = bounds_for(body)
        _apply_control_failure_notice(body)
    _apply_guide_texts(body)
    if _is_query_set_report(body):
        body.setdefault("overlap_statement", _OVERLAP_STATEMENT)
        body.setdefault("coverage_statement", _COVERAGE_STATEMENT)
    return body


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
        carries_rate = "wilson_low" in obj and "tier" in obj
        carries_tier = "tier" in obj and ("rate" in obj or "n" in obj)
        if carries_rate or carries_tier:
            if SCOPE_VALUE not in [str(v) for v in obj.values()]:
                obj["claim_type"] = SCOPE_VALUE


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
        return _render_simple(_advanced_body(record))
    body = _advanced_body(record)
    _apply_agentic_scope(body)
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
    rate = node.get("rate")
    low = node.get("wilson_low")
    high = node.get("wilson_high")
    tier = node.get("tier")
    clause = TIER_CLAUSES.get(tier) if isinstance(tier, str) \
        else None
    if tier == "count only":
        count = node.get("count")
        if count is None:
            count = node.get("n")
        if low is None or high is None:
            return (
                "%s: %s answers, tier count only: %s."
                % (name, _scalar_text(count), clause)
            )
        return (
            "%s: %s answers, interval %d to %d percent, tier "
            "count only: %s."
            % (name, _scalar_text(count),
               round(low * 100), round(high * 100), clause)
        )
    warning = node.get("small_sample_warning")

    def with_warning(line):
        if warning is True:
            line += " " + SMALL_SAMPLE_WARNING
        elif isinstance(warning, str) and warning:
            line += " " + warning
        return line

    if rate is None or low is None or high is None:
        rate_part = "rate null" if rate is None else (
            "rate %s" % _rate_value_text(rate))
        interval_part = "interval null" if (
            low is None or high is None) else (
            "interval %d to %d percent"
            % (round(low * 100), round(high * 100)))
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
    low_pct = round(low * 100)
    high_pct = round(high * 100)
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


def _emit(lines, key, value, depth, suppress_anchor_bare=False):
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
        _emit_dict(lines, value, depth + 1, top=False)
        return
    if isinstance(value, list):
        lines.append("%s%s:" % (pad, key))
        for item in value:
            if isinstance(item, (dict, list)):
                _emit(lines, "item", item, depth + 1)
            else:
                lines.append("%s  %s" % (pad, _scalar_text(item)))
        return
    if isinstance(value, float) and (
            key in _TREND_RATE_KEYS
            or key.endswith("_rate")
            or key.endswith("_share")
            or key.endswith("_percent")):
        lines.append("%s%s: %s" % (pad, key, _rate_value_text(value)))
        return
    lines.append("%s%s: %s" % (pad, key, _scalar_text(value)))
    if key == "head_hash" and value and not suppress_anchor_bare:
        lines.append("%s%s" % (pad, ANCHOR_LIMIT_SENTENCE))


def _emit_dict(lines, node, depth, top=True, top_suppress=None,
               suppress_anchor_bare=False):
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
        if key in _NONE_SILENT_KEYS and value is None:
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
                  suppress_anchor_bare and key == "head_hash"))
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
               "control_failure_notice"}
    remainder = {k: v for k, v in body.items() if k not in handled}
    _emit_dict(lines, remainder, 0)
    return lines


def _render_query_set_simple(body):
    lines = ["Query set report."]
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
    handled = {key for _label, key in labels}
    handled |= {"overlap_statement", "coverage_statement"}
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
    if value is None:
        lines.append("The score for this run stands not recorded.")
    else:
        lines.append(
            "The score for this run is %s, in the %s band."
            % (_scalar_text(value), _scalar_text(band)))
        basis = score.get("applicable_basis")
        if isinstance(basis, dict):
            checks_named = basis.get("applicable_checks") or []
            weight = basis.get("applicable_weight")
            if weight is not None:
                lines.append(
                    "The score rests on %d checks, with a total "
                    "weight of %s."
                    % (len(checks_named), _scalar_text(weight)))
        if score.get("cap_status"):
            lines.append(
                "The evidence cap holds the score at 39 for "
                "this run.")
        else:
            lines.append(
                "The evidence cap does not hold for this run.")
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
        lines.append(
            "  %s: earned %s of weight %s, status %s, reason "
            "%s, evidence class %s."
            % (_scalar_text(check.get("check_id")),
               _scalar_text(check.get("earned")),
               _scalar_text(check.get("weight")),
               _scalar_text(check.get("status")),
               _scalar_text(check.get("reason_code")),
               _scalar_text(check.get("evidence_class"))))
    lines.append("Next actions:")
    lines.append(
        "  The guide artefact for this run carries the actions "
        "for this run in plain words, from the run_id above.")
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
    return lines


def _render_simple(body):
    if not isinstance(body, dict):
        return _scalar_text(body)
    if _is_guide(body):
        lines = _render_guide_simple(body)
    elif _is_query_set_report(body):
        lines = _render_query_set_simple(body)
    elif _is_audit_record(body):
        lines = _render_audit_simple(body)
    else:
        lines = []
        top_suppress = set()
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
                   suppress_anchor_bare=suppress_anchor_bare)
        if "rates" in body and "empty_answer_count" in body:
            empty_count = body.get("empty_answer_count")
            if isinstance(empty_count, int) and \
                    not isinstance(empty_count, bool) and \
                    empty_count != 0:
                lines.append(EMPTY_ANSWER_WARNING % empty_count)
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
        lines.append(TIER_CLAUSES_LINE)
    if _carries_score_band(body):
        lines.append(SCORE_BAND_SCALE_LINE)
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


_INTERROGATIVE_STARTERS = {
    "what", "how", "why", "when", "where", "which", "who",
    "is", "are", "can", "could", "does", "do", "did", "will",
}


def _fold(text):
    folded = unicodedata.normalize("NFC", str(text)).casefold()
    return " ".join(folded.split())


def _classify_query(query, product_names, competitor_names):
    folded = _fold(query)
    first_word = folded.split(" ", 1)[0].strip("?") if folded else ""
    interrogative = first_word in _INTERROGATIVE_STARTERS \
        or folded.endswith("?")
    comparison = " vs " in folded or " versus " in folded
    named_product = any(
        name and _fold(name) in folded for name in product_names)
    named_competitor = any(
        name and _fold(name) in folded for name in competitor_names)
    bare_topic = not (interrogative or comparison or named_product
                      or named_competitor)
    return {
        "interrogative": interrogative,
        "comparison": comparison,
        "named_product": named_product,
        "naming_none": not (named_product or named_competitor),
        "bare_topic": bare_topic,
    }


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
        queries = query_set.get("queries") or query_set.get("items") \
            or []
        query_set_version = query_set.get("query_set_version") \
            or query_set.get("version") or query_set_version
    elif isinstance(query_set, list):
        queries = query_set
    product_names = [record.get("name")] + list(
        record.get("aliases") or [])
    competitor_names = []
    for competitor in record.get("competitors") or []:
        if isinstance(competitor, dict):
            competitor_names.append(competitor.get("name"))
            competitor_names.extend(competitor.get("aliases") or [])
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
    group token in operator spelling, in file order.

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
                groups.setdefault(str(agent), []).extend(texts)
        return groups
    keyed = evaluation.get("group_rules")
    if isinstance(keyed, dict):
        for token, rules in keyed.items():
            texts = []
            for rule in rules or []:
                text = _rule_text(rule)
                if text is not None:
                    texts.append(text)
            groups[str(token)] = texts
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
                groups.setdefault(str(token), []).append(text)
    return groups


def _rule_text_changed_rows(first, second, existing):
    """Changed rows from the two files' group rule texts.

    A preview is a comparison of the two files, and a rule
    that stands written differently in the second file is a
    changed row of the preview even where that rule does not
    win at the evaluated path, so no finding differs there.
    One entry stands per position whose rule text differs,
    keyed by the group token that supplies the rule. The
    wildcard group supplies every purpose class and no one
    class, so its purpose class stands null, and a rule text
    row carries no defect flag change. Rows a finding
    comparison already produced, with the same token and the
    same two texts, are not repeated.
    """
    rows = []
    first_groups = _group_rules(first)
    second_groups = _group_rules(second)
    seen = {
        (row.get("token"), row.get("first_finding"),
         row.get("second_finding"))
        for row in existing
    }
    tokens = list(first_groups)
    for token in second_groups:
        if token not in tokens:
            tokens.append(token)
    for token in tokens:
        first_texts = first_groups.get(token) or []
        second_texts = second_groups.get(token) or []
        for index in range(max(len(first_texts),
                               len(second_texts))):
            before = first_texts[index] \
                if index < len(first_texts) else None
            after = second_texts[index] \
                if index < len(second_texts) else None
            if before == after:
                continue
            key = (token, before, after)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "token": token,
                "purpose_class": None,
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
    return preview


def robots_preview(first, second, form="advanced", **inputs):
    """The RobotsPreview over two evaluations, in one form."""
    artefact = assemble_robots_preview(first, second, **inputs)
    return render(artefact, form=form)
