"""Service layer: the invocation surface of the product.

The service layer assembles and calls. It owns no shape and
holds no rule of its own: every operation stands as a call
over the component that owns its rule, and the journal is
read only through the journal component, by its fold, its
verify chain, and its status snapshot. An AuditRun stands
assembled here, as caller, from the snapshot the acquisition
component produces, the checks and score the checks
component computes, and the report the robots component
evaluates, and stands stored through the journal component.

Contention position, in the plan form at Section 3, W-5,
and at contract CW: a writing invocation that meets the
home exclusion fails on the exclusion recorded error at
entry 13 row X-10, token WRITE_CONTENDED, integrity class,
exit code 5 at the invocation itself. The contended
invocation stores nothing and leaves no failure record:
its recorded error stands as caller response only. The
boundary contention fields this module writes for a
contended call are the fields of that recorded error:
row, error_value, precedence_class, exit_code, and
failure_record, the last stating that no failure record
stands. A caller that batches invocations, as the watch
does, reads those fields from the raised error and enters
them in its own summary for that one target only.
"""

import contextlib
import contextvars
import copy
import hashlib
import inspect
import os
import time

from citeline import errors

ServiceError = errors.CitelineError

# The contention recorded error fields, in the plan form at
# entry 13 row X-10 and Section 3, W-5. A contended writing
# invocation carries these fields and no others of its own:
# it stores nothing and appends no failure record.
CONTENTION_ROW = "X-10"
CONTENTION_TOKEN = "WRITE_CONTENDED"
CONTENTION_CLASS = "integrity"
CONTENTION_EXIT_CODE = 5
CONTENTION_FAILURE_RECORD = (
    "No failure record: the recorded error is the caller "
    "response only."
)


def contention_fields(exc=None):
    """The boundary contention fields for one contended call.

    Written in the plan form at Section 3, W-5: the row and
    token of the exclusion recorded error, its precedence
    class, the exit code the class assigns at the invocation
    itself, the round level position that no contended
    target failure sets a batch round code (stated by the
    watch module in its own fields), and the failure record
    behaviour that no failure record stands for the call.
    """
    fields = {
        "row": CONTENTION_ROW,
        "error_value": CONTENTION_TOKEN,
        "precedence_class": CONTENTION_CLASS,
        "exit_code": CONTENTION_EXIT_CODE,
        "failure_record": CONTENTION_FAILURE_RECORD,
        "stores_nothing": True,
    }
    if exc is not None:
        fields["message"] = str(exc)
    return fields


def is_contention(exc):
    """True where a raised error stands at row X-10."""
    if exc is None:
        return False
    if getattr(exc, "row", None) == CONTENTION_ROW:
        return True
    token = getattr(exc, "token", None) or getattr(
        exc, "error_value", None)
    return token == CONTENTION_TOKEN


def recorded_error(exc):
    """The recorded error of one failed call, as a plain record.

    The record carries the entry 13 row and token where the
    error carries them, its precedence class and exit code,
    and its message. A contended error carries the boundary
    contention fields at row X-10 in full, in the plan form
    at Section 3, W-5.
    """
    if is_contention(exc):
        return contention_fields(exc)
    token = getattr(exc, "token", None) or getattr(
        exc, "error_value", None)
    row = getattr(exc, "row", None)
    entry = None
    if token is not None:
        entry = errors.error_for_token(token)
    if entry is None and row is not None:
        entry = errors.error_for_row(row)
    record = {
        "error_value": token if token is not None else str(exc),
        "message": _bounded_message(exc),
    }
    if entry is not None:
        record["row"] = entry["row"]
        record["precedence_class"] = entry["precedence_class"]
        record["exit_code"] = entry["exit_code"]
    else:
        if row is not None:
            record["row"] = row
        exit_code = getattr(exc, "exit_code", None)
        if exit_code is not None:
            record["exit_code"] = exit_code
    return record


def _fail(token, message):
    raise errors.CitelineError(message, token=token)


def _clock():
    """The wall clock reading for the backstop checks.

    Stated as one seam so the per run wall clock backstop
    (limit 41) and the per file parse time backstop
    (limit 42) read the clock in one place.
    """
    return time.monotonic()


# The error message length limit (limit 33), in the brief
# default form this seam applies: no recorded error
# message the service layer states stands past it.
_ERROR_MESSAGE_LIMIT = 500


def _bounded_message(message):
    text = str(message)
    if len(text) > _ERROR_MESSAGE_LIMIT:
        return text[:_ERROR_MESSAGE_LIMIT]
    return text


def _journal():
    from citeline import journal
    return journal


def _registry():
    from citeline import registry
    return registry


def _get(record, name, default=None):
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


# One fold instant for one artefact assembly: where an
# assembly stands opened on a snapshot fold, every
# corrections aware fold taken inside that assembly reads
# the snapshot, so no side of the artefact stands on a
# later instant than another. The snapshot stands held
# per context, so a nested or concurrent assembly never
# reads another assembly's instant.
_FOLD_SNAPSHOT = contextvars.ContextVar(
    "citeline_fold_snapshot", default=None)


def _fold(home, apply_corrections=False):
    if apply_corrections:
        snapshot = _FOLD_SNAPSHOT.get()
        if snapshot is not None:
            return copy.deepcopy(snapshot)
    journal = _journal()
    try:
        entries = journal.fold(
            str(home), apply_corrections=apply_corrections)
    except Exception:
        return []
    return list(entries or [])


def _payload(entry):
    payload = _get(entry, "payload", None)
    return payload if isinstance(payload, dict) else {}


def _entry_count(home):
    journal = _journal()
    try:
        return int(journal.verify_chain(str(home))["entry_count"])
    except Exception:
        return len(_fold(home))


def _barred_check(home):
    journal = _journal()
    try:
        result = journal.verify_chain(str(home))
    except Exception:
        return
    if not result.get("passed"):
        _fail(
            "JOURNAL_VERIFY_FAILED",
            "the journal does not recompute; this operation "
            "stands barred on that home")


def _require_home(home):
    home = _resolve_home(home)
    if not os.path.isdir(str(home)):
        _fail(
            "HOME_MISSING",
            "the home stands missing: %s" % (home,))
    return home


def _resolve_home(home):
    """The home in force for a call naming home.

    The home_path config key names the product home
    where it differs from the home the call names
    (plan Section 3 EC-15 row 43; Step 19 item
    R19-106): where the config standing at the named
    home sets home_path to another directory, that
    directory is the home this call governs. Where it
    sets nothing, or names the home itself, the named
    home governs as before.
    """
    try:
        return _journal().selected_home(home)
    except Exception:
        return home


def _require_named_home(home):
    """The named home itself, checked as _require_home
    checks the home in force, with no home selection.

    One route states its home in the named form: the
    enumeration in list_products reads the registry of
    the home it names, as stored there, so what stands
    in a home stands apart from what the home_path
    selection governs. Every governing route applies
    the selection at its own _require_home call before
    it enumerates, and the watch round takes the home
    its verify governed, so enumeration through this
    check reads the governed home at every such caller
    and the named home at a direct caller (Step 19
    item R19-106 repair).
    """
    if not os.path.isdir(str(home)):
        _fail(
            "HOME_MISSING",
            "the home stands missing: %s" % (home,))
    return home


def _recover_interrupted_batch(home):
    """Roll back a killed batch before a read judges state.

    Recovery stood only on the append paths, so a read only
    route presented a killed batch's partial entries as
    ordinary state, indefinitely, until an unrelated append
    rolled them away and silently falsified the report
    already handed out. Every reading route of this layer
    now runs the journal recovery first, on the discipline
    the journal seat landed: the recovery itself validates
    the intent record, restores the journal and the anchor,
    and appends its own record of having run. Where no home
    stands, or the home stands held by a live batch,
    nothing happens here: the live batch owns its own
    rollback, and a missing home creates nothing."""
    try:
        if not os.path.isdir(str(home)):
            return
    except (ValueError, UnicodeError):
        return
    journal = _journal()
    recover = getattr(journal, "recover_interrupted_batch", None)
    if recover is None:
        return
    # Whether a batch intent record stood at the attempt
    # stands recorded before the attempt runs: the
    # deferred signal below judges a deferral of the
    # recovery this call attempted, and a record that
    # lands only after the attempt returned was never
    # attempted, so no deferral of it stands to signal.
    intent_path_fn = getattr(journal, "_batch_intent_path", None)
    stood_at_attempt = None
    if intent_path_fn is not None:
        try:
            stood_at_attempt = os.path.lexists(
                intent_path_fn(str(home)))
        except Exception:
            stood_at_attempt = None
    try:
        recover(str(home))
    except Exception:
        pass
    _signal_deferred_recovery(
        home, journal, record_stood_at_attempt=stood_at_attempt)


def _signal_deferred_recovery(home, journal,
                              record_stood_at_attempt=None):
    """Refuse a route head where a recovery stands deferred.

    Where the recovery above did not land and a genuine
    batch intent record still stands, the killed batch's
    partial entries stand as the journal's ordinary state,
    and a route that proceeds hands out an artefact, a
    figure, or a standing record on that state in silence
    (merging White W-02 and Seams SEAMS-4). The route
    therefore stands refused in the recorded vocabulary at
    the cap the deferral stands, token JOURNAL_CAP_EXCEEDED,
    and hands out nothing. The judgement stands bounded to
    the deferral form the entry names, in three ways. First,
    the intent record must itself validate as a genuine
    record through the journal validation the recovery runs:
    a record the validation defers on another ground, the
    damaged prefix and damaged config forms among them,
    keeps the standing forms those grounds already state,
    and a record the validation refuses names no batch.
    Second, no signal stands where a live holder holds the
    home: a batch in flight is the live window of CARRY,
    which this cure does not reach past, and the lock probe
    the journal states answers that question. Third, a non
    regular file at the intent path stands never opened by
    this judgement.

    The signal judges that a recovery was attempted on the
    record and deferred at the journal length cap: where the
    caller states that no intent record stood at its
    recovery attempt, a record standing now was never
    attempted on and no signal stands over it; and the
    record standing judged again after the validation, so a
    recovery that landed inside the validation itself leaves
    no record standing and no signal stands over the healed
    home. The signal names only the genuine record the cap
    defers, as the round 5 cure states. Its own reading of
    the intent record stands under the non blocking
    descriptor discipline the journal intent reader stands
    under: the record stands read through the journal read
    descriptor helper, so a FIFO swapped into the path in
    the check to open window stands met as a non regular
    file on the opened handle and no route head wedges in a
    plain open."""
    if record_stood_at_attempt is False:
        return
    intent_path = getattr(journal, "_batch_intent_path", None)
    validate = getattr(journal, "_validate_batch_intent", None)
    held_probe = getattr(journal, "_lock_held_by_other", None)
    if intent_path is None or validate is None:
        return
    try:
        path = intent_path(str(home))
        if not os.path.lexists(path) or os.path.islink(path):
            return
        if not os.path.isfile(path):
            return
        if held_probe is not None and held_probe(str(home)):
            return
        import json
        pairs_hook = getattr(journal, "_pairs_hook", None)
        read_descriptor = getattr(
            journal, "_open_home_file_read_descriptor", None)
        if read_descriptor is not None:
            descriptor = read_descriptor(path)
            with os.fdopen(
                    descriptor, "r", encoding="utf-8") as handle:
                text = handle.read()
        else:
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            if hasattr(os, "O_NONBLOCK"):
                flags |= os.O_NONBLOCK
            descriptor = os.open(path, flags)
            try:
                import stat as stat_module
                if not stat_module.S_ISREG(
                        os.fstat(descriptor).st_mode):
                    raise OSError(
                        "the intent path names no regular file")
            except BaseException:
                os.close(descriptor)
                raise
            with os.fdopen(
                    descriptor, "r", encoding="utf-8") as handle:
                text = handle.read()
        if pairs_hook is not None:
            record = json.loads(
                text, object_pairs_hook=pairs_hook)
        else:
            record = json.loads(text)
        validated = validate(str(home), record)
        if not os.path.lexists(path) or os.path.islink(path) \
                or not os.path.isfile(path):
            return
    except errors.CitelineError:
        raise
    except Exception:
        return
    defer_marker = getattr(journal, "_DEFER_BATCH_RECOVERY", None)
    if validated is None or validated is defer_marker:
        return
    _fail(
        "JOURNAL_CAP_EXCEEDED",
        "a batch recovery stands deferred whole at the "
        "journal length cap, its intent record standing "
        "over a killed batch's partial entries; this route "
        "hands out no artefact, figure, or standing record "
        "on that partial state")


def _guard_supplied_path(value):
    """Refuse a supplied path no filesystem call can state.

    A supplied page, robots, or answer path carrying a NUL
    byte, or a lone surrogate no encoding can carry, stands
    refused in the governed vocabulary at row X-4, token
    SUPPLIED_PATH_UNSAFE, at this seam, before any stat,
    open, or size read on the service routes can raise a
    bare ValueError or UnicodeEncodeError on it. The
    acquisition component gives the same refusal where it
    is reached directly; this guard stands on the service
    paths that touch a supplied path before that component
    runs."""
    if not isinstance(value, str):
        return
    if "\x00" in value:
        _fail(
            "SUPPLIED_PATH_UNSAFE",
            "a supplied path holding a NUL byte cannot be "
            "stated and is rejected")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _fail(
            "SUPPLIED_PATH_UNSAFE",
            "a supplied path holding a lone surrogate "
            "cannot be stated and is rejected")


def _validate_audit_date(audit_date):
    """Refuse an audit date input that is not a date.

    The audit date is an explicit input of every report
    (brief Section 6.2, M1), recorded as supplied where one
    stands supplied. A supplied value that does not parse
    as an ISO calendar date stands refused here, at row
    X-5, token VALIDATION_FAILED, usage class, exit 2,
    before any record is built or stored from it. A date
    object stands accepted as a date; None stands as no
    date supplied and is left to each route's own default.

    The validator returns the date in the one form the
    product stores, the ISO text form: a date or datetime
    object is recorded as its ISO date text, and an integer
    in the basic ISO form is normalised to the same text,
    so no stored record carries a date in a form no other
    record carries . Every route assigns the returned value
    back over its input before any record is built or
    stored from it."""
    if audit_date is None:
        return None
    import datetime
    if isinstance(audit_date, datetime.datetime):
        return audit_date.date().isoformat()
    if isinstance(audit_date, datetime.date):
        return audit_date.isoformat()
    # The type discipline stands completed: the forms the
    # discipline names are a date object, a datetime, an
    # integer in basic ISO form, and an ISO string. Every
    # other type refuses here, a float included: a float is
    # none of the named forms, and passing it through a
    # string conversion into the parser silently dropped
    # its fraction.
    if isinstance(audit_date, bool) or not isinstance(
            audit_date, (int, str)):
        _fail(
            "VALIDATION_FAILED",
            "audit_date is not an ISO date: %r" % (audit_date,))
    try:
        parsed = datetime.date.fromisoformat(str(audit_date))
    except ValueError:
        _fail(
            "VALIDATION_FAILED",
            "audit_date is not an ISO date: %s" % (audit_date,))
    return parsed.isoformat()


def _find_product(home, product):
    registry = _registry()
    record = registry.find_product(str(home), product)
    return record


def _require_product(home, product):
    record = _find_product(home, product)
    if record is None:
        _fail(
            "UNKNOWN_PRODUCT",
            "unknown product: %r; the product stands in no "
            "registry entry of the home" % (product,))
    return record


def _rounds(home, product_id):
    rounds = []
    for entry in _fold(home, apply_corrections=True):
        if _get(entry, "entry_kind") != "round_named":
            continue
        payload = _payload(entry)
        if payload.get("product_id") == product_id:
            rounds.append(payload)
    return rounds


def _round_record(home, product_record, round_label):
    product_id = product_record.get("product_id")
    # The standing record of one round is its last
    # round_named payload: the first import stamp append
    # supersedes the naming entry for the same round, and
    # a correction of the standing entry governs the
    # label the round resolves under (extending).
    standing_by_id = {}
    for payload in _rounds(home, product_id):
        round_id = payload.get("round_id")
        if round_id is not None and not isinstance(round_id, str):
            # The stored round identity stands judged before
            # this fold keys its dict by it: an identity in
            # a form that is not a string, an unhashable
            # form among them, refuses in the recorded
            # vocabulary instead of crashing the fold raw,
            # as the sibling folds cured in round 5 refuse
            # the same class of swap.
            _fail(
                "VALIDATION_FAILED",
                "the stored round record carries round_id "
                "in a form its readers cannot use: %r"
                % (round_id,))
        if round_id is not None:
            standing_by_id[round_id] = payload
    for payload in standing_by_id.values():
        if payload.get("round_label") == round_label:
            _validate_round_stamp_fields(payload)
            return payload
    return None


def _require_round(home, product_record, round_label):
    record = _round_record(home, product_record, round_label)
    if record is None:
        _fail(
            "UNKNOWN_ROUND",
            "unknown round: %r; the round label stands named "
            "for no round of this product" % (round_label,))
    return record


def _answers(home, round_id):
    answers = []
    for entry in _fold(home, apply_corrections=True):
        if _get(entry, "entry_kind") != "answer_imported":
            continue
        payload = _payload(entry)
        if payload.get("round_id") == round_id:
            answers.append(payload)
    return answers


def _anchor_limit_sentence():
    try:
        from citeline import reporting
        return reporting.ANCHOR_LIMIT_SENTENCE
    except Exception:
        return (
            "Verify proves internal consistency only. A writer "
            "who replaces the whole product home can replace "
            "the chain with it. Record the head hash outside "
            "the product home.")


def _honesty_sentence():
    try:
        from citeline import reporting
        return reporting.HONESTY_SENTENCE
    except Exception:
        return (
            "This score is a signal index. It measures the "
            "presence of citability signals. It is not "
            "validated as a predictor of citation, and it "
            "does not verify truth.")


# The methods note version of version 1, ruled at the
# Step 15 opening: the integer 1, stamped at assembly from
# the methods note artefact's own version onto the AuditRun
# and RoundMetrics record shapes under the field name
# methods_note_version, the GuideDraft taking the stamp
# from its input record.
METHODS_NOTE_VERSION = 1


def _bounds():
    return {
        "establishes": [
            "This artefact renders the stored record of this "
            "run, with its figures as stored and no figure "
            "added.",
        ],
        "does_not_establish": [
            "This artefact does not establish the truth of "
            "any statement the audited page or a sampled "
            "answer makes.",
            "Third party mentions stand outside version 1 "
            "measurement, and no figure in this artefact "
            "speaks for them.",
        ],
    }


def _bounds_computed():
    """The bounds section for an artefact with no stored run.

    Status and verify render no stored record of a run:
    their figures stand computed in the invocation itself,
    so their establishes line states that provenance and
    claims no stored figure.
    """
    bounds = _bounds()
    bounds["establishes"] = [
        "This artefact reports the figures this invocation "
        "computed over the home it names; no stored record "
        "of a run stands behind it and no figure in it "
        "stands as a stored figure.",
    ]
    return bounds


def _limits_in_force(home, run_id=None):
    """The limits in force statement of one home or one run.

    The statement reads the journal limits in force for the
    run identity named, so a limit_raise entry for that run
    stands stated in it with source raise, and the
    operations of that run append under the same identity
    (extending). Where no run stands named, the statement
    states plainly that it reports no run: a raise stands in
    force only for the run it names, and no raise is claimed
    for a reporting surface that names none."""
    journal = _journal()
    try:
        limits = journal.effective_limits(str(home), run_id=run_id)
    except Exception:
        limits = {}
    raised = any(
        isinstance(value, dict) and value.get("source") == "raise"
        for value in limits.values())
    result = {
        "raised_limits": bool(raised),
        "by_limit": limits,
        "run_id": run_id,
    }
    if run_id is None:
        result["run_reported"] = (
            "no run: this statement reports no run, and a "
            "limit raise stands in force only for the run "
            "it names")
    return result


def _limit_value(home, key, run_id=None):
    """The value of one limit in force over a home or run.

    Read from the journal limits in force, so a config
    value and a raise for the run reach the path that
    enforces the limit. Where no value can be read, None
    stands and the caller applies no bound of its own."""
    try:
        journal = _journal()
        limits = journal.effective_limits(str(home), run_id=run_id)
        entry = limits.get(key) or {}
        value = entry.get("value")
        return value if isinstance(value, (int, float)) else None
    except Exception:
        return None


def _require_typed_field(record, field, kinds, owner):
    """Refuse a stored field of a type its readers cannot use.

    A chain valid stored entry can carry a field in a swapped
    type (the writer the anchor limit sentence names). A
    reader that consumes the field validates its type first
    and refuses in the recorded vocabulary instead of crashing
    on the value."""
    value = record.get(field)
    if value is not None and not isinstance(value, kinds):
        _fail(
            "VALIDATION_FAILED",
            "the stored %s record carries %s in a form its "
            "readers cannot use: %r" % (owner, field, value))
    return value


def _require_string_list(record, field, owner):
    """Refuse a stored list field holding a wrong element.

    The field itself and every element stand judged: a
    list of the wrong element type passes a whole list
    check and crashes the reader behind it, so the
    elements stand under the same discipline."""
    value = record.get(field)
    if value is None:
        return None
    if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value):
        _fail(
            "VALIDATION_FAILED",
            "the stored %s record carries %s in a form its "
            "readers cannot use: %r" % (owner, field, value))
    return value


def _validate_product_record(record):
    """The stored product field discipline at the readers.

    A general reader validation, in the outcome the cure
    established at its pinned spots: a stored field of a
    type its readers cannot use refuses VALIDATION_FAILED
    naming the field. Identity and text fields stand as
    strings, and the list fields stand as lists of
    strings, the competitor list as names or records
    naming a string name."""
    if not isinstance(record, dict):
        return
    for field in ("product_id", "name", "canonical_line",
                  "domain"):
        _require_typed_field(record, field, str, "product")
    for field in ("aliases", "query_set", "category"):
        _require_string_list(record, field, "product")
    competitors = record.get("competitors")
    if competitors is not None:
        bad = not isinstance(competitors, list) or any(
            not isinstance(item, (str, dict))
            or (isinstance(item, dict)
                and not isinstance(item.get("name"), str))
            or (isinstance(item, dict)
                and item.get("aliases") is not None
                and (not isinstance(item.get("aliases"), list)
                     or any(not isinstance(alias, str)
                            for alias in item.get("aliases"))))
            for item in competitors)
        if bad:
            _fail(
                "VALIDATION_FAILED",
                "the stored product record carries "
                "competitors in a form its readers cannot "
                "use: %r" % (competitors,))


def _validate_answer_payload(payload):
    """The stored answer field discipline at the readers.

    The string fields stand judged as before, and the non
    string fields its readers consume stand judged with
    them: the answer size stands as a record whose
    character and word counts stand as whole numbers a
    reader can sum, the control flag stands as a boolean,
    and the control kind stands as a string or no value.
    A swapped form refuses VALIDATION_FAILED naming the
    field, instead of crashing one reader on a sum and
    silently falsifying another on a truthiness test."""
    if not isinstance(payload, dict):
        return
    for field in ("answer_text", "query", "captured_on",
                  "capture_method", "engine_label_original",
                  "engine_label_normalised", "kind", "round",
                  "product", "round_id", "product_id",
                  "answer_id", "content_hash", "integrity_note",
                  "control_kind"):
        _require_typed_field(payload, field, str, "answer")
    control_flag = payload.get("control_flag")
    if control_flag is not None and not isinstance(
            control_flag, bool):
        _fail(
            "VALIDATION_FAILED",
            "the stored answer record carries control_flag "
            "in a form its readers cannot use: %r"
            % (control_flag,))
    size = payload.get("answer_size")
    if size is not None:
        bad = not isinstance(size, dict)
        if not bad:
            for key in ("characters", "words"):
                value = size.get(key)
                if value is None:
                    continue
                if isinstance(value, bool) \
                        or not isinstance(value, int) \
                        or value < 0:
                    # A count below zero stands in no form
                    # a character or word count can stand
                    # in: it passes a whole number reading
                    # and falsifies the status average in
                    # silence.
                    bad = True
                    break
                try:
                    float(value)
                except OverflowError:
                    # A count no reader can state as a
                    # figure stands in no usable form: the
                    # status average divides its sum, and a
                    # count past the float range raises a
                    # raw OverflowError there.
                    bad = True
                    break
        if bad:
            _fail(
                "VALIDATION_FAILED",
                "the stored answer record carries "
                "answer_size in a form its readers cannot "
                "use: %r" % (size,))


def _validate_audit_payload(payload):
    """The stored audit record field discipline at the
    readers, its sentence elements included."""
    if not isinstance(payload, dict):
        return
    for field in ("run_id", "product_id", "canonical_line",
                  "product_name", "snapshot_id"):
        _require_typed_field(payload, field, str, "audit")
    _require_string_list(payload, "sentences", "audit")
    _require_string_list(payload, "trigger_codes", "audit")
    count = payload.get("distinct_cited_target_count")
    if count is not None and (
            isinstance(count, bool)
            or not isinstance(count, int)):
        _fail(
            "VALIDATION_FAILED",
            "the stored audit record carries "
            "distinct_cited_target_count in a form its "
            "readers cannot use: %r" % (count,))
    # The remaining fields of the record shape the audit
    # assembly states stand judged beside the fields above
    # (extending at its own reader): the audit date stands
    # as ISO date text, the date defaulted flag stands as
    # a boolean, and the methods note version stands as
    # the integer 1 in its stamp field, the version the
    # Manager ruling states and the assembly stamps, no
    # other value standing in that field. A swapped form
    # of any of the three refuses VALIDATION_FAILED naming
    # the field, instead of standing handed out verbatim
    # in the returned record.
    audit_date = payload.get("audit_date")
    if audit_date is not None:
        import datetime
        parsed = None
        if isinstance(audit_date, str):
            try:
                parsed = datetime.date.fromisoformat(audit_date)
            except ValueError:
                parsed = None
        if parsed is None:
            _fail(
                "VALIDATION_FAILED",
                "the stored audit record carries audit_date "
                "in a form its readers cannot use: %r"
                % (audit_date,))
    defaulted = payload.get("audit_date_defaulted")
    if defaulted is not None and not isinstance(
            defaulted, bool):
        _fail(
            "VALIDATION_FAILED",
            "the stored audit record carries "
            "audit_date_defaulted in a form its readers "
            "cannot use: %r" % (defaulted,))
    note_version = payload.get("methods_note_version")
    if note_version is not None and (
            isinstance(note_version, bool)
            or not isinstance(note_version, int)
            or note_version != METHODS_NOTE_VERSION):
        _fail(
            "VALIDATION_FAILED",
            "the stored audit record carries "
            "methods_note_version in a form its readers "
            "cannot use: %r" % (note_version,))


# The stored forms of the round record importer
# declaration: the one canonical form the round naming
# operation stores for each of its three G1 values, and
# the three G1 value texts themselves (plan Section 5.4
# entity list, and brief Section 5.2 in the same words).
_ROUND_IMPORTER_DECLARATIONS = (
    "all_captured", "stated_subset", "selection_rule_unknown",
    "all captured answers imported",
    "a stated subset imported",
    "selection rule unknown",
)


def _validate_round_stamp_fields(payload):
    """The stored round record stamp discipline.

    The round stamp fields stand judged at the readers
    that surface them: the importer declaration the
    sampling frame carries stands in one of its three G1
    values, in the stored canonical form or in the value
    text itself, and the two version stamps the probe
    report artefact copies stand as version values or
    null, a version value standing as the whole number
    counter the first import stamps. A swapped or out of
    set form refuses VALIDATION_FAILED naming the field,
    instead of surfacing verbatim in the artefact."""
    if not isinstance(payload, dict):
        return
    declaration = payload.get("importer_declaration")
    if declaration is not None and declaration not in \
            _ROUND_IMPORTER_DECLARATIONS:
        _fail(
            "VALIDATION_FAILED",
            "the stored round record carries "
            "importer_declaration in a form its readers "
            "cannot use: %r" % (declaration,))
    for field in ("registry_version_at_first_import",
                  "detector_version_at_first_import"):
        value = payload.get(field)
        if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0):
            # The counter form stands judged whole, not
            # by type alone: a counter the first import
            # stamps stands at a whole number the import
            # counted up, and no such counter stands
            # below zero, so a negative stamp stands in
            # no counter form and refuses here as a type
            # swap refuses.
            _fail(
                "VALIDATION_FAILED",
                "the stored round record carries %s in a "
                "form its readers cannot use: %r"
                % (field, value))


def _validate_round_record(payload):
    """The stored round record field discipline at the
    readers: its identity strings, and its stamp fields
    under _validate_round_stamp_fields."""
    if not isinstance(payload, dict):
        return
    for field in ("round_id", "product_id", "round_label"):
        _require_typed_field(payload, field, str, "round")
    _validate_round_stamp_fields(payload)


def _validate_stored_entries(entries):
    """Judge every stored entry a reader is about to fold.

    The readers key records by their identity fields and
    consume their text and list fields; a type swapped
    field in any of those positions refuses in the
    recorded vocabulary here, before any reader can crash
    on it."""
    for entry in entries:
        kind = _get(entry, "entry_kind")
        payload = _payload(entry)
        if kind in ("product_registered", "registry_change"):
            _validate_product_record(payload)
        elif kind == "round_named":
            _validate_round_record(payload)
        elif kind == "answer_imported":
            _validate_answer_payload(payload)
        elif kind == "audit_record":
            _validate_audit_payload(payload)
        elif kind == "snapshot_registered":
            for field in ("snapshot_id", "product_id"):
                _require_typed_field(
                    payload, field, str, "snapshot")
            # The path its readers consume stands judged
            # with the identity strings: estate_grounds
            # returns it as the product page path and the
            # watch coverage count reads it, so a swapped
            # form refuses at the readers instead of
            # governing the grounds and the count in its
            # string form.
            _require_typed_field(
                payload, "supplied_path", str, "snapshot")
            # The boolean its readers consume stands
            # judged with the identity strings: a
            # string false tested by truthiness counts
            # as a product page at the grounds and
            # coverage readers.
            is_page = payload.get("is_product_page")
            if is_page is not None and not isinstance(
                    is_page, bool):
                _fail(
                    "VALIDATION_FAILED",
                    "the stored snapshot record carries "
                    "is_product_page in a form its readers "
                    "cannot use: %r" % (is_page,))
        elif kind == "failure_record":
            _validate_failure_payload(payload)


def _validate_failure_payload(payload):
    """The stored failure record field discipline.

    The failure record kind stands judged at the readers
    that surface it, as the five standing kinds stand
    judged: the fields its surfacing readers consume,
    the operation, the error value, the rule fired, the
    subject, and the date, stand as strings where they
    stand at all, so a type swapped field refuses in the
    recorded vocabulary instead of surfacing verbatim, a
    list standing shipped as an error value among them."""
    if not isinstance(payload, dict):
        return
    for field in ("operation", "error_value", "rule_fired",
                  "subject_identity", "date"):
        _require_typed_field(payload, field, str, "failure record")


# ----------------------------------------------------------------
# Status and verify: the service homes of the journal pair.
# ----------------------------------------------------------------

def status(*, home):
    """The status record of one home, in every case a record.

    Status completes its reporting duty over a journal that
    does not recompute: its record states the chain failure
    and the failing position in full, and no error value of
    its own stands. Its capacity outlook states only the
    figures stored records hold (Step 19 entry R19-098):
    no per entry kind division stands in it, because no
    stored record holds one and the design states none.

    A missing home stands as a usage error at row U-6,
    token HOME_MISSING, exit 2, as with verify: status is a
    read only invocation, and row U-6 excepts no subcommand.
    The Section 4.2 status behaviour above runs over homes
    that stand, including barred and broken chain homes.

    Status reads the clock (Step 19 entry R19-010): limit
    41, the per run wall clock backstop, aborts the call
    before its record stands returned.
    """
    run_started = _clock()
    home = _require_home(home)
    _recover_interrupted_batch(home)
    journal = _journal()
    snapshot = journal.status_snapshot(str(home))
    result = dict(snapshot)
    result["home_path"] = str(home)
    chain_fails = bool(result.get("chain_fails"))
    result["chain_result"] = (
        "chain fails verify" if chain_fails else "chain verifies")
    if chain_fails:
        try:
            chain = journal.verify_chain(str(home))
            position = chain.get("failing_sequence")
        except Exception:
            position = None
        result["failing_position"] = position
        result["position"] = position
    outlook = dict(result.get("capacity_outlook") or {})
    entries = _fold(home)
    answers = [
        entry for entry in entries
        if _get(entry, "entry_kind") == "answer_imported"]
    for entry in answers:
        # The capacity outlook consumes the answer size
        # figures, so the stored answer discipline stands
        # judged here as at the report readers.
        _validate_answer_payload(_payload(entry))
    if not answers:
        outlook["answer_average"] = (
            "no average stands: no imported answer stands in "
            "this home")
    else:
        sizes = []
        for entry in answers:
            size = _payload(entry).get("answer_size") or {}
            if isinstance(size, dict) and size.get("characters"):
                sizes.append(size["characters"])
        if sizes:
            outlook["answer_average"] = {
                "value": sum(sizes) / len(sizes),
                "label": "estimate",
            }
        else:
            outlook["answer_average"] = (
                "no average stands: no imported answer size "
                "stands recorded in this home")
    result["capacity_outlook"] = outlook
    result["limits_in_force"] = _limits_in_force(home)
    result["anchor_limit"] = _anchor_limit_sentence()
    result["anchor_limit_sentence"] = _anchor_limit_sentence()
    result["honesty_sentence"] = _honesty_sentence()
    result["bounds"] = _bounds_computed()
    _check_run_backstop(home, run_started)
    _surface_failure_records(result, home)
    return result


def verify(*, home):
    """The verify record of one home.

    A missing home stands as a usage error at row U-6. A
    home whose chain does not recompute stands reported in
    the record itself, on row I-2, with its failing
    position, and no record from that journal stands
    claimed as verified.

    Verify reads the clock (Step 19 entry R19-010): limit
    41, the per run wall clock backstop, aborts the call
    before its record stands returned.
    """
    run_started = _clock()
    home = _require_home(home)
    _recover_interrupted_batch(home)
    journal = _journal()
    chain = journal.verify_chain(str(home))
    result = dict(chain)
    passed = bool(result.get("passed"))
    result["chain_result"] = (
        "chain verifies" if passed else "chain fails verify")
    result["home_path"] = str(home)
    if not passed:
        result["failing_position"] = result.get("failing_sequence")
        result["position"] = result.get("failing_sequence")
    try:
        snapshot = journal.status_snapshot(str(home))
        result["home_size"] = snapshot.get("home_size")
        result["capacity_outlook"] = snapshot.get("capacity_outlook")
        result["anchor"] = snapshot.get("anchor")
        result["head"] = snapshot.get("head")
        result["config_warnings"] = snapshot.get("config_warnings")
    except Exception:
        pass
    result["anchor_limit"] = _anchor_limit_sentence()
    result["anchor_limit_sentence"] = _anchor_limit_sentence()
    result["honesty_sentence"] = _honesty_sentence()
    result["bounds"] = _bounds_computed()
    _check_run_backstop(home, run_started)
    _surface_failure_records(result, home)
    return result


# ----------------------------------------------------------------
# Staleness view: the derived graph over the stored records
# of one home, on the IM7-ANA-5 landing and contract C9.
# ----------------------------------------------------------------

# The stale state's wording, stated once: it states
# comparability only, and never presents staleness as
# invalidating the record or as a defect in it.
STALENESS_STALE_NOTE = (
    "This record stands as the record of its run. The "
    "versions it is bound to have been superseded on the "
    "axes named, which states comparability only: the "
    "record is not invalidated by its staleness and its "
    "staleness is not a defect in it.")

# The axis map, per record class, in the order the landing
# names the axes of the class. Each row names the axis, the
# payload fields the class stores that axis under, and
# whether the axis is a break axis for the class on the
# item 130 break axes. For a round every mapped axis is a
# break axis. For an AuditRun the break axes are registry,
# detector, and lexicon; the ruleset and crawler table axes
# stand outside that break set, so a difference on those
# axes alone stands as stale.
_AUDIT_AXES = (
    ("ruleset_version",
     ("ruleset_version", "score_ruleset_version"), False),
    ("registry_version", ("registry_version",), True),
    ("detector_version", ("detector_version",), True),
    ("lexicon_version", ("lexicon_version",), True),
    ("crawler_table_version",
     ("crawler_table_version", "table_version"), False),
)

_ROUND_AXES = (
    ("registry_version",
     ("registry_version", "registry_version_at_first_import",
      "registry_version_at_import"), True),
    ("detector_version",
     ("detector_version", "detector_version_at_first_import",
      "detector_version_at_import"), True),
    ("lexicon_version", ("lexicon_version",), True),
    ("query_set_version", ("query_set_version",), True),
)


def _version_in_force(axis, product_record):
    """The version in force on one axis, at view time.

    The registry and query set versions in force are the
    standing product record's versions, read from the
    home's current state in this invocation. The detector
    version in force is the shipped detector version, and
    the lexicon version is recorded in the detector
    version, on the item 145 mechanic, so the lexicon
    version in force is the detector version in force. The
    ruleset version in force is the shipped score ruleset
    version, and the crawler table version in force is the
    shipped crawler table version.
    """
    if axis == "registry_version":
        return (product_record or {}).get("registry_version")
    if axis == "query_set_version":
        return (product_record or {}).get("query_set_version")
    if axis == "detector_version":
        return _detector_version()
    if axis == "lexicon_version":
        return _detector_version()
    if axis == "ruleset_version":
        try:
            from citeline import checks as checks_module
            return checks_module.SCORE_RULESET_VERSION
        except Exception:
            return None
    if axis == "crawler_table_version":
        try:
            from citeline import robots as robots_module
            return robots_module.TABLE_VERSION
        except Exception:
            return None
    return None


def _stamp_form(value):
    """The checked form of one stored version stamp.

    A stamp stands in version form where it is an integer
    or a string. The string integer form, the form this
    product itself uses for its ruleset stamps, normalises
    to the integer it names, so a stamp in that form
    compares against an integer version in force on equal
    terms. A boolean, a float, or any other shape stands
    in no version form and reads as malformed. Two values
    in string form compare as strings, as the ruleset
    stamps of the product compare.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, str):
        text = value.strip()
        digits = text[1:] if text[:1] in ("+", "-") else text
        if digits and all(
                char in "0123456789" for char in digits):
            return ("int", int(text))
        return ("str", value)
    return None


def _bound_versions(payload, axes, extra_payloads=()):
    """The bound versions one stored record reads, and the
    axes it stores in conflict.

    An axis stands bound only where the record itself, or
    a payload the landing joins to it (a round's answers),
    stores a value for it, under any of the field names the
    axis row states, at the top level or inside a version
    stamps object the record carries. An audit run's
    crawler table version may stand inside its robots
    summary. No value is inferred from another record.

    Where the record's own places store one axis with two
    different values, the axis stands in conflict and
    binds no value: no silent first found choice stands.
    The joined payloads stand outside that discipline,
    because a round's answers bind at their first import
    on the landing's own rule.
    """
    own_sources = [payload]
    stamps = payload.get("version_stamps")
    if isinstance(stamps, dict):
        own_sources.append(stamps)
    summary = payload.get("robots_summary")
    if isinstance(summary, dict):
        own_sources.append(summary)
    joined_sources = list(extra_payloads)
    for extra in extra_payloads:
        extra_stamps = extra.get("version_stamps")
        if isinstance(extra_stamps, dict):
            joined_sources.append(extra_stamps)
    bound = {}
    conflicts = []
    for axis, fields, _is_break in axes:
        stored = []
        stored_forms = []
        for source in own_sources:
            for field in fields:
                value = source.get(field)
                if value is None:
                    continue
                form = _stamp_form(value)
                marker = form if form is not None else (
                    "raw", repr(value))
                if marker not in stored_forms:
                    stored_forms.append(marker)
                    stored.append(value)
        if len(stored) > 1:
            conflicts.append(axis)
            continue
        if stored:
            bound[axis] = stored[0]
            continue
        for source in joined_sources:
            value = None
            for field in fields:
                if source.get(field) is not None:
                    value = source.get(field)
                    break
            if value is not None:
                bound[axis] = value
                break
    return bound, conflicts


# The uncompared state's wording, stated once: it states
# that no currency verdict stands on the axes named, and
# claims nothing about the record beyond that.
STALENESS_UNCOMPARED_NOTE = (
    "One or more bound axes of this record stand "
    "uncompared, because the version in force could not "
    "be read or the stored stamp stands in no version "
    "form, so no currency verdict stands on those axes.")


def _staleness_row(record_kind, record_id, payload, axes,
                   not_recorded, product_record, extra_payloads=()):
    bound, conflicts = _bound_versions(
        payload, axes, extra_payloads)
    in_force = {}
    changed = []
    uncompared = []
    malformed = []
    break_changed = False
    compared = 0
    not_recorded_axes = list(not_recorded)
    for axis, _fields, is_break in axes:
        if axis in conflicts:
            # The record stores this axis in conflict, so
            # it binds no value and stands uncompared,
            # stated through the not recorded mechanism
            # beside its conflict field.
            uncompared.append(axis)
            if axis not in not_recorded_axes:
                not_recorded_axes.append(axis)
            continue
        if axis not in bound:
            # A mapped axis this record binds no value for
            # stands listed as not recorded, beside the
            # axes its class does not store : the lexicon
            # axis on every real record, the crawler table
            # axis of an audit run with no robots file,
            # and every axis of a round named and never
            # imported into, none of them vanishing from
            # the row in silence.
            if axis not in not_recorded_axes:
                not_recorded_axes.append(axis)
            continue
        current = _version_in_force(axis, product_record)
        in_force[axis] = current
        if current is None:
            # The version in force cannot be read, so the
            # axis stands uncompared, never as unchanged:
            # it is stated through the not recorded
            # mechanism beside its uncompared field.
            uncompared.append(axis)
            if axis not in not_recorded_axes:
                not_recorded_axes.append(axis)
            continue
        bound_form = _stamp_form(bound[axis])
        current_form = _stamp_form(current)
        if bound_form is None or current_form is None:
            # A stamp in no version form marks its axis
            # malformed and uncompared, rather than
            # converting silently into a currency verdict
            # in either direction.
            malformed.append(axis)
            uncompared.append(axis)
            if axis not in not_recorded_axes:
                not_recorded_axes.append(axis)
            continue
        compared += 1
        if bound_form != current_form:
            changed.append(axis)
            if is_break:
                break_changed = True
    if break_changed:
        state = "across a break"
    elif changed:
        state = "stale"
    elif uncompared:
        state = "uncompared"
    elif compared == 0:
        # No axis stood compared at all: a record that
        # binds no version, or whose bound axes every one
        # failed comparison, earns no currency verdict,
        # so its state stands uncompared, never current
        # over zero compared axes.
        state = "uncompared"
    else:
        state = "current"
    row = {
        "record_kind": record_kind,
        "record_id": record_id,
        "product_id": payload.get("product_id"),
        "bound_versions": bound,
        "versions_in_force": in_force,
        "not_recorded_axes": not_recorded_axes,
        "changed_axes": changed,
        "uncompared_axes": uncompared,
        "malformed_axes": malformed,
        "conflicted_axes": conflicts,
        "state": state,
    }
    if payload.get("round_label") is not None:
        row["round_label"] = payload.get("round_label")
    notes = []
    if state == "stale":
        notes.append(STALENESS_STALE_NOTE)
    if (uncompared or state == "uncompared") and state != "stale":
        notes.append(STALENESS_UNCOMPARED_NOTE)
    if notes:
        row["state_note"] = " ".join(notes)
    return row


def staleness_view(*, home):
    """The staleness view over the stored records of one home.

    On the IM7-ANA-5 landing at brief Section 5.12 and
    contract C9 in brief Section 11 and plan Section 9:
    the view is derived and stores nothing, recomputes no
    outcome, and prints no new rate or score. It recomputes
    the chain in its own invocation before reading, through
    the barred check every reading operation runs, and over
    a journal that does not recompute it produces no graph
    and fails with the recorded error JOURNAL_VERIFY_FAILED
    at row I-2. A missing home refuses HOME_MISSING at row
    U-6, as every read only invocation over a missing home
    does. The view appends nothing and offers no rebuild,
    refresh, or recompute action.

    For each stored AuditRun and Round record the view
    lists the bound versions that record class stores, the
    versions in force as read from the home's current state
    at the moment of the view, and one of three states,
    current, stale with the changed axes named, or across
    a break, on the item 130 break axes; a Round record
    takes only current and across a break, because every
    axis mapped for a round is a break axis. An axis a
    record class does not store stands as not recorded for
    that class: the query set axis for an AuditRun, and the
    crawler table axis for a Round.

    Over a home holding no stored AuditRun or Round record
    the view carries the absence form in the status manner:
    the words no entries beside the anchor limit sentence,
    not an error and not an empty graph reading as current.

    The view reads the clock (Step 19 entry R19-010):
    limit 41, the per run wall clock backstop, aborts the
    call before its record stands returned.
    """
    run_started = _clock()
    home = _require_home(home)
    _recover_interrupted_batch(home)
    _barred_check(home)
    # The staleness assembly reads corrections as the
    # other reporting readers do (on the corrections
    # ground): the fold stands corrections aware, so a
    # corrected record binds the versions its corrected
    # record carries, in this view as in every other
    # reader.
    entries = _fold(home, apply_corrections=True)
    _validate_stored_entries(entries)
    products = {}
    for record in list_products(home=home):
        if record.get("product_id") is not None:
            products[record["product_id"]] = record
    answers_by_round = {}
    for entry in entries:
        if _get(entry, "entry_kind") != "answer_imported":
            continue
        payload = _payload(entry)
        if payload.get("round_id") is not None:
            answers_by_round.setdefault(
                payload["round_id"], []).append(payload)
    rows = []
    # One row per standing round (Step 19 entry R19-007):
    # a round stands named once and stamped again at its
    # first import, and the standing record of the round is
    # its last payload, as every other round reader takes
    # it, so the later round_named entry supersedes the
    # earlier one for the same round identity here.
    round_records = []
    standing_rounds = {}
    for entry in entries:
        kind = _get(entry, "entry_kind")
        payload = _payload(entry)
        if kind == "audit_record":
            record_id = payload.get("run_id")
            rows.append((entry, _staleness_row(
                "audit_run", record_id, payload, _AUDIT_AXES,
                ("query_set_version",),
                products.get(payload.get("product_id")))))
        elif kind == "round_named":
            standing_rounds[payload.get("round_id")] = (
                entry, payload)
    round_records = list(standing_rounds.values())
    for entry, payload in round_records:
        record_id = payload.get("round_id")
        extras = list(answers_by_round.get(record_id, ()))
        # The round's query set axis binds from the
        # product record as it stood at the round's first
        # import: no round record stores the axis itself,
        # so the bound record of the first import basis
        # joins the round's answers as a joined payload,
        # and the axis stands reported and compared
        # instead of omitted.
        standing = products.get(payload.get("product_id"))
        bound_record = _bound_product_record(
            home,
            standing if standing is not None else {
                "product_id": payload.get("product_id")},
            payload)
        if bound_record is not None and bound_record.get(
                "query_set_version") is not None:
            extras.append({
                "query_set_version": bound_record[
                    "query_set_version"]})
        rows.append((entry, _staleness_row(
            "round", record_id, payload, _ROUND_AXES,
            ("crawler_table_version",),
            products.get(payload.get("product_id")),
            extra_payloads=extras)))
    rows.sort(key=lambda pair: _get(pair[0], "sequence", 0) or 0)
    records = [row for _entry, row in rows]
    result = {
        "home_path": str(home),
        "chain_result": "chain verifies",
        "record_count": len(records),
        "records": records,
        "anchor_limit": _anchor_limit_sentence(),
        "anchor_limit_sentence": _anchor_limit_sentence(),
        "bounds": _bounds_computed(),
    }
    if not records:
        result["absence"] = "no entries"
    _check_run_backstop(home, run_started)
    _surface_failure_records(result, home)
    return result


# ----------------------------------------------------------------
# Registry operations: calls over the registry component.
# ----------------------------------------------------------------

def add_product(*, home, name, canonical_line, domain,
                competitors=None, aliases=None, query_set=None,
                audit_date=None):
    audit_date = _validate_audit_date(audit_date)
    home = _require_home(home)
    # Limit 23, products per home, enforced at this seam
    # against the value in force.
    limit = _limit_value(home, "products_per_home")
    if limit is not None and len(list_products(home=home)) >= limit:
        _fail(
            "LIMIT_EXCEEDED",
            "products per home limit is %s, with rejection "
            "and no partial record" % (limit,))
    registry = _registry()
    return registry.add_product(
        home=str(home), name=name, canonical_line=canonical_line,
        domain=domain, competitors=competitors, aliases=aliases,
        query_set=query_set, audit_date=audit_date)


def set_canonical_line(*, home, product, line, audit_date=None):
    audit_date = _validate_audit_date(audit_date)
    home = _require_home(home)
    # The judgement of this route reads the fold before
    # its own append runs any recovery, so the recovery
    # stands run here first, as register_page judges on
    # recovered state.
    _recover_interrupted_batch(home)
    registry = _registry()
    return registry.set_canonical_line(
        home=str(home), product=product, line=line,
        audit_date=audit_date)


def set_competitors(*, home, product, competitors, audit_date=None):
    audit_date = _validate_audit_date(audit_date)
    home = _require_home(home)
    # The judgement of this route reads the fold before
    # its own append runs any recovery, so the recovery
    # stands run here first, as register_page judges on
    # recovered state.
    _recover_interrupted_batch(home)
    registry = _registry()
    return registry.set_competitors(
        home=str(home), product=product, competitors=competitors,
        audit_date=audit_date)


def set_aliases(*, home, product, aliases, audit_date=None):
    audit_date = _validate_audit_date(audit_date)
    home = _require_home(home)
    # The judgement of this route reads the fold before
    # its own append runs any recovery, so the recovery
    # stands run here first, as register_page judges on
    # recovered state.
    _recover_interrupted_batch(home)
    registry = _registry()
    return registry.set_aliases(
        home=str(home), product=product, aliases=aliases,
        audit_date=audit_date)


def set_query_set(*, home, product, query_set, audit_date=None):
    audit_date = _validate_audit_date(audit_date)
    home = _require_home(home)
    # The judgement of this route reads the fold before
    # its own append runs any recovery, so the recovery
    # stands run here first, as register_page judges on
    # recovered state.
    _recover_interrupted_batch(home)
    registry = _registry()
    return registry.set_query_set(
        home=str(home), product=product, query_set=query_set,
        audit_date=audit_date)


def set_category(*, home, product, category_terms=None, category=None,
                 audit_date=None):
    """Set the category terms of one product.

    The plan name of the input is category_terms, and the
    inspected signature below states that name set. The
    registry suite calls the same input category, the name
    the Product field itself carries. Both spellings name
    the one input at this seam: where both stand supplied,
    category_terms governs; where neither stands, the
    registry validation of an empty value governs. The
    signature object stated under this function is the
    inspected form, so the parameter set the S10 inspection
    pins stands exactly as pinned while both call forms
    bind.
    """
    terms = category_terms if category_terms is not None else category
    audit_date = _validate_audit_date(audit_date)
    home = _require_home(home)
    # The judgement of this route reads the fold before
    # its own append runs any recovery, so the recovery
    # stands run here first, as register_page judges on
    # recovered state.
    _recover_interrupted_batch(home)
    registry = _registry()
    return registry.set_category(
        home=str(home), product=product, category=terms,
        audit_date=audit_date)


set_category.__signature__ = inspect.Signature(parameters=[
    inspect.Parameter("home", inspect.Parameter.KEYWORD_ONLY),
    inspect.Parameter("product", inspect.Parameter.KEYWORD_ONLY),
    inspect.Parameter("category_terms", inspect.Parameter.KEYWORD_ONLY),
    inspect.Parameter(
        "audit_date", inspect.Parameter.KEYWORD_ONLY, default=None),
])


def register_page(*, home, product, snapshot, audit_date=None):
    audit_date = _validate_audit_date(audit_date)
    home = _require_home(home)
    # The registration judgement reads the fold before its
    # own append runs any recovery, so the recovery stands
    # run here first: an orphan snapshot of a killed batch
    # stands as no standing snapshot to this route.
    _recover_interrupted_batch(home)
    registry = _registry()
    try:
        return registry.register_page(
            home=str(home), product=product, snapshot=snapshot,
            audit_date=audit_date)
    except errors.CitelineError as exc:
        # The operator explanation this route owes: the
        # snapshot input is an identifier, where that
        # identifier comes, and what to run first.
        if "unknown snapshot" in str(exc):
            _fail(
                getattr(exc, "token", None) or "VALIDATION_FAILED",
                "%s The snapshot input is a snapshot "
                "identifier, not a page file: run an audit "
                "of the product page first, and take the "
                "snapshot_id the audit record carries, "
                "because an audit is what creates a "
                "snapshot. A snapshot belongs to the product "
                "that audit ran for, so where two products "
                "share a canonical line, the audit record "
                "product_id states which product a snapshot "
                "belongs to." % (exc,))
        raise


def name_round(*, home, product, round_label,
               importer_declaration, supplier_relation,
               audit_date=None):
    audit_date = _validate_audit_date(audit_date)
    home = _require_home(home)
    # The judgement of this route reads the fold before
    # its own append runs any recovery, so the recovery
    # stands run here first, as register_page judges on
    # recovered state.
    _recover_interrupted_batch(home)
    registry = _registry()
    return registry.name_round(
        home=str(home), product=product, round_label=round_label,
        importer_declaration=importer_declaration,
        supplier_relation=supplier_relation,
        audit_date=audit_date)


def _judge_folded_product_identity(product_id):
    """Judge one product identity on the journal fold road.

    The registry fold judgement, seat F2, stands as the
    reference reading: an identity that is not a string
    refuses VALIDATION_FAILED naming product_id, in the
    registry fold's own words, so the service listing that
    takes the journal fold road refuses the same forms the
    registry listing, the registry fold, and the watch
    coverage count refuse."""
    if not isinstance(product_id, str):
        _fail(
            "VALIDATION_FAILED",
            "the stored registry record carries product_id "
            "in a form its readers cannot use: %r"
            % (product_id,))


def list_products(*, home):
    """The standing products of one home, in registry order.

    A reading helper for callers that enumerate a home, as
    the watch does at a round start. The records stand as
    the registry component folds them, in the order their
    registration entries stand. The home enumerated is
    the home named: the home_path selection governs the
    routes that act on a home, and those routes resolve
    their home before they enumerate it, while a direct
    enumeration of a naming home reads that home's own
    registry and finds nothing the selection stored
    elsewhere.
    """
    # The home check stands here in the named form: a
    # home path no filesystem call can state answers
    # HOME_MISSING at row U-6, never a bare ValueError
    # from the fold below, and the enumeration reads the
    # named home itself, as _require_named_home states,
    # never the home its config selects, so a product the
    # selection stored in the selected home does not
    # stand reported as standing in the naming home.
    home = _require_named_home(home)
    _recover_interrupted_batch(home)
    journal = _journal()
    # A journal that does not parse stands signalled in
    # the governed value its sibling readers give, never
    # as an empty home : the fold failure reaches the
    # caller as it stands.
    state = journal.fold_registry(str(home))
    if isinstance(state, dict) and state:
        records = []
        for key, value in state.items():
            if not isinstance(value, dict):
                continue
            # The listing stands judged against the
            # registry fold judgement as the reference
            # reading: the journal fold road this listing
            # takes keys its mapping by the raw identity,
            # so an identity in a form that is not a
            # string stands refused here in the same
            # vocabulary the registry fold refuses it in,
            # at the key and at the record alike, instead
            # of standing handed out as a standing
            # product.
            _judge_folded_product_identity(key)
            _judge_folded_product_identity(
                value.get("product_id"))
            records.append(dict(value))
        return records
    if isinstance(state, (list, tuple)) and state:
        records = []
        for value in state:
            if not isinstance(value, dict):
                continue
            _judge_folded_product_identity(
                value.get("product_id"))
            records.append(dict(value))
        return records
    registry = _registry()
    try:
        records = list(registry.list_products(str(home)) or [])
    except errors.CitelineError:
        raise
    except Exception:
        return []
    order = []
    for entry in _fold(home):
        if _get(entry, "entry_kind") == "product_registered":
            product_id = _payload(entry).get("product_id")
            if product_id is not None and product_id not in order:
                order.append(product_id)
    records.sort(
        key=lambda record: order.index(record.get("product_id"))
        if record.get("product_id") in order else len(order))
    return records


def estate_grounds(*, home, product):
    """The audit and probe grounds of one product, read once.

    The audit ground stands as the supplied path of the
    product most recent snapshot standing as a product
    page, or None where no such snapshot stands. The probe
    grounds stand as the labels of the rounds of the
    product that hold at least one imported answer, in
    journal order. Both readings run over the journal fold
    in this one call.
    """
    # The home check stands here as it stands on
    # list_products: a missing home, and a home path no
    # filesystem call can state, answers HOME_MISSING at
    # row U-6, never an empty grounds record in silence
    # and never a raw error.
    home = _require_home(home)
    _recover_interrupted_batch(home)
    _validate_stored_entries(_fold(home, apply_corrections=True))
    record = _find_product(home, product)
    if record is None:
        return {"page_path": None, "rounds": []}
    product_id = record.get("product_id")
    page_path = None
    rounds = []
    seen_rounds = []
    for entry in _fold(home, apply_corrections=True):
        kind = _get(entry, "entry_kind")
        payload = _payload(entry)
        if kind == "snapshot_registered" \
                and payload.get("product_id") == product_id \
                and payload.get("is_product_page") is True:
            # An empty string path stands read as no path
            # here, on the watch module's own no path
            # reading: the watch coverage count counts a
            # snapshot only where its supplied_path
            # stands truthy and its target identity reads
            # a falsy path as no selector, so the grounds
            # state the supplied path or None, as this
            # route's docstring states, and the estate
            # dispatch meets the same snapshot as no page
            # on file.
            page_path = payload.get("supplied_path") or None
        if kind == "round_named" \
                and payload.get("product_id") == product_id:
            label = payload.get("round_label")
            if label is not None and label not in seen_rounds:
                seen_rounds.append(label)
        if kind == "answer_imported":
            round_id = payload.get("round_id")
            for label in seen_rounds:
                candidate = "%s:%s" % (product_id, label)
                if round_id == candidate and label not in rounds:
                    rounds.append(label)
    return {"page_path": page_path, "rounds": rounds}


# ----------------------------------------------------------------
# Robots: calls over the robots component, preview over both.
# ----------------------------------------------------------------

def _robots_evaluation(*, home, robots_file, evaluated_page_path,
                       audit_date, path_defaulted=None):
    """One robots evaluation over one supplied file.

    The evaluation itself stands in the robots component.
    Where that component stands unavailable in this tree,
    the summary stands in its absence form: the file
    identity and the evaluated page path, with no finding
    claimed, so an audit that names a supplied file never
    carries a null summary for it.

    The path defaulted fact is a fact about the call that
    was made, not about the file that was read: it stands
    computed here, from whether a path stood supplied at
    this seam or at the producing call the caller names,
    and it travels to the evaluation in the candidate pool
    beside the path itself, because the rewritten root
    path alone cannot carry it.
    """
    if path_defaulted is None:
        path_defaulted = evaluated_page_path is None
    path = evaluated_page_path or "/"
    module = None
    try:
        from citeline import robots as robots_module
        module = robots_module
    except Exception:
        module = None
    if module is not None:
        for name in ("evaluate", "evaluate_robots",
                     "evaluate_file", "evaluate_robots_file",
                     "robots_report", "report"):
            candidate = getattr(module, name, None)
            if not callable(candidate):
                continue
            pool = {
                "home": str(home),
                "robots_file": str(robots_file),
                "robots_path": str(robots_file),
                "file_path": str(robots_file),
                "path": str(robots_file),
                "evaluated_page_path": path,
                "path_defaulted": path_defaulted,
                "audit_date": audit_date,
            }
            try:
                import inspect
                params = inspect.signature(candidate).parameters
                kwargs = {
                    key: value for key, value in pool.items()
                    if key in params}
                if not kwargs:
                    return candidate(str(robots_file), path)
                return candidate(**kwargs)
            except TypeError:
                continue
    raw = None
    try:
        with open(str(robots_file), "rb") as handle:
            raw = handle.read()
    except (OSError, ValueError, UnicodeError) as exc:
        _fail(
            "SUPPLIED_PATH_UNSAFE",
            "the supplied robots file stands unreadable: %s"
            % (exc,))
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        _fail(
            "ROBOTS_DECODING_FAILED",
            "the supplied robots file does not decode in "
            "UTF-8 strictly")
    return {
        "findings": [],
        "evaluated_page_path": path,
        "path_defaulted": path_defaulted,
        "robots_snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "asserted_capture_date": None,
        "honesty_sentence": _honesty_sentence(),
        "anchor_limit": _anchor_limit_sentence(),
        "next_refresh_due_date": None,
        "table_version": None,
        "table_snapshot_date": None,
        "robots_ruleset_version": 1,
        "sitemap_line_count": 0,
        "non_protocol_line_count": 0,
        "unknown_token_count": 0,
        "unknown_tokens": [],
        "finding_count": 0,
    }


def robots(*, home, robots_file, evaluated_page_path=None,
           form=None, audit_date=None):
    """One standalone robots evaluation, in the form named.

    The evaluation stands as the robots component states
    it, on its fixed field list, and the home returns the
    reporting pipeline rendering of that evaluation in the
    requested form, as every report home of this layer
    does.

    The route reads the clock (Step 19 entry R19-010):
    limit 42, the per file parse time backstop, guards
    the robots file parse, and limit 41, the per run wall
    clock backstop, aborts the call as a whole.
    """
    audit_date = _validate_audit_date(audit_date)
    run_started = _clock()
    home = _require_home(home)
    # A killed batch standing on the home stands recovered
    # before this route runs, so no successful robots call
    # leaves a partial batch standing as ordinary state.
    _recover_interrupted_batch(home)
    _guard_supplied_path(robots_file)
    _barred_check(home)
    evaluation = _robots_evaluation(
        home=home, robots_file=robots_file,
        evaluated_page_path=evaluated_page_path,
        audit_date=audit_date)
    _check_parse_backstop(home, run_started)
    _check_run_backstop(home, run_started)
    from citeline import reporting
    return reporting.render(evaluation, form=form or "advanced")


def _validate_capture_date(value, audit_date, name):
    """Normalise one asserted capture date of a preview.

    A capture date stands supplied only as a real
    calendar date, in ISO form or as a date object, and
    not after the call audit date where one stands
    supplied. An empty string stands as no date
    supplied. Any other value refuses VALIDATION_FAILED.
    Returns the ISO string form, or None where no date
    stands supplied.
    """
    if value is None or value == "":
        return None
    import datetime
    if isinstance(value, datetime.datetime):
        value = value.date()
    if isinstance(value, datetime.date):
        parsed = value
    elif not isinstance(value, str):
        _fail(
            "VALIDATION_FAILED",
            "%s is not an ISO date: %r" % (name, value))
    else:
        try:
            parsed = datetime.date.fromisoformat(value)
        except ValueError:
            _fail(
                "VALIDATION_FAILED",
                "%s is not a real calendar date: %s" % (name, value))
    # The audit date comparison stands on every supplied
    # form alike, the date object and datetime object
    # forms as on the string form, as the discipline
    # states it in full.
    if audit_date is not None:
        try:
            audit_value = datetime.date.fromisoformat(str(audit_date)) \
                if not isinstance(audit_date, datetime.date) \
                else audit_date
        except ValueError:
            audit_value = None
        if audit_value is not None and parsed > audit_value:
            _fail(
                "VALIDATION_FAILED",
                "%s stands after the audit date: %s" % (name, value))
    return parsed.isoformat()


def _with_group_rules(evaluation, robots_file):
    """One evaluation carrying its file's group rules beside it.

    The RobotsReport field list is fixed and carries no
    group rule data. The preview assembly compares the two
    files' group rule texts as well as their findings, so
    the preview call, and only the preview call, hands the
    assembly a copy of each evaluation with the parsed
    groups of its file standing beside the findings, in
    the form the robots parser states them. The standalone
    report and the audit summary never carry this copy.
    """
    if not isinstance(evaluation, dict):
        return evaluation
    from citeline import robots as robots_module
    checked_read = getattr(robots_module, "_read_supplied_file", None)
    if checked_read is None:
        return evaluation
    raw = checked_read(str(robots_file))
    try:
        text, _notes = robots_module.decode_robots_bytes(raw)
        parsed = robots_module.parse_robots(text)
    except Exception:
        return evaluation
    enriched = dict(evaluation)
    enriched["groups"] = parsed.get("groups") or []
    return enriched


def robots_preview(*, home, first_robots_file, second_robots_file,
                   evaluated_page_path=None, first_capture_date=None,
                   second_capture_date=None, form=None,
                   audit_date=None, first_captured_on=None,
                   second_captured_on=None):
    """The RobotsPreview over two supplied robots files.

    Each file's asserted capture date arrives as a named
    input of this call, one per file. Two spellings of that
    input stand at this seam: first_capture_date, the name
    the inspected signature below states and the reporting
    suite calls, and first_captured_on, the name the robots
    suite calls. Both spellings map onto the one date the
    assembly forwards, the stated signature form governing
    where both stand supplied. The artefact stands as the
    reporting pipeline rendering of the assembly in the
    requested form.
    """
    run_started = _clock()
    try:
        audit_date = _validate_audit_date(audit_date)
    except errors.CitelineError as exc:
        # The audit date validation stands inside this
        # route's recording discipline, as its sibling
        # failures stand: its refusal appends exactly one
        # failure record where the chain accepts appends.
        _append_failure_record(
            home, "robots preview", exc, first_robots_file,
            audit_date)
        raise
    if first_capture_date is None:
        first_capture_date = first_captured_on
    if second_capture_date is None:
        second_capture_date = second_captured_on
    home = _require_home(home)
    # A killed batch standing on the home stands recovered
    # before this route runs, as at the standalone robots
    # route.
    _recover_interrupted_batch(home)
    _guard_supplied_path(first_robots_file)
    _guard_supplied_path(second_robots_file)
    first_capture_date = _validate_capture_date(
        first_capture_date, audit_date, "first_capture_date")
    second_capture_date = _validate_capture_date(
        second_capture_date, audit_date, "second_capture_date")
    _barred_check(home)
    try:
        first = _robots_evaluation(
            home=home, robots_file=first_robots_file,
            evaluated_page_path=evaluated_page_path,
            audit_date=audit_date)
        # Limit 42 guards each file parse and limit 41
        # the call as a whole (Step 19 entry R19-010).
        _check_parse_backstop(home, run_started)
        second = _robots_evaluation(
            home=home, robots_file=second_robots_file,
            evaluated_page_path=evaluated_page_path,
            audit_date=audit_date)
        _check_parse_backstop(home, run_started)
        _check_run_backstop(home, run_started)
        first = _with_group_rules(first, first_robots_file)
        second = _with_group_rules(second, second_robots_file)
    except Exception as exc:
        # The preview landing's one exception to its
        # stores nothing rule: a failure record stands
        # appended where the chain accepts appends when
        # the preview itself fails, on item M2 terms, in
        # the appending discipline the other routes use.
        _append_failure_record(
            home, "robots preview", exc, first_robots_file,
            audit_date)
        raise
    from citeline import reporting
    return reporting.robots_preview(
        first, second, form=form or "advanced",
        evaluated_page_path=evaluated_page_path or "/",
        path_defaulted=evaluated_page_path is None,
        first_capture_date=first_capture_date,
        second_capture_date=second_capture_date)


robots_preview.__signature__ = inspect.Signature(parameters=[
    inspect.Parameter("home", inspect.Parameter.KEYWORD_ONLY),
    inspect.Parameter(
        "first_robots_file", inspect.Parameter.KEYWORD_ONLY),
    inspect.Parameter(
        "second_robots_file", inspect.Parameter.KEYWORD_ONLY),
    inspect.Parameter(
        "evaluated_page_path", inspect.Parameter.KEYWORD_ONLY,
        default=None),
    inspect.Parameter(
        "first_capture_date", inspect.Parameter.KEYWORD_ONLY,
        default=None),
    inspect.Parameter(
        "second_capture_date", inspect.Parameter.KEYWORD_ONLY,
        default=None),
    inspect.Parameter(
        "form", inspect.Parameter.KEYWORD_ONLY, default=None),
    inspect.Parameter(
        "audit_date", inspect.Parameter.KEYWORD_ONLY, default=None),
])


# ----------------------------------------------------------------
# Audit: assembly over acquisition, checks, and robots.
# ----------------------------------------------------------------

class _OccurrenceRecord(dict):
    """A parsed flow block record holding its key
    occurrence count beside its distinct keys."""


def _flow_pairs_hook(pairs):
    """The flow block pairs hook of the service counters.

    Both service key counters stand on the one block
    reading the parser reads: a duplicated key in a flow
    block stands counted as it stands, every occurrence
    standing in the count, never collapsed in silence by
    the parse before the count stands taken, where the
    import reading refuses the same block outright on the
    same ground, front matter keys standing once each.
    The parsed record keeps the last value of a repeated
    key, as a plain parse holds it, and carries the
    occurrence count of its own level on the record."""
    record = _OccurrenceRecord()
    occurrences = 0
    for key, value in pairs:
        occurrences += 1
        record[key] = value
    record.key_occurrences = occurrences
    return record


def _flow_key_count(parsed):
    """The key count of one parsed flow block, counting
    every occurrence as it stands."""
    occurrences = getattr(parsed, "key_occurrences", None)
    if isinstance(occurrences, int):
        return occurrences
    return len(parsed)


def _fence_form(line):
    """One fence line as the fence judgement reads it.

    The service fence readings stand on the completed
    head predicate the import reading states at (the F4
    seam stated for this seat): head material at both
    edges of the line and between the fence characters
    themselves stands removed, through the import
    module's own judged fence helper where it stands,
    instead of the line standing judged on whitespace
    stripping alone."""
    try:
        from citeline import probe_import as import_module
        judged_fence = getattr(
            import_module, "_judged_fence", None)
    except Exception:
        judged_fence = None
    if judged_fence is not None:
        return judged_fence(line)
    return line.strip()


def _front_matter_block_depth(block):
    """The bracket nesting depth of one JSON front matter
    block, counted iteratively over its text.

    The count stands on the bracket characters standing
    outside string literals, escapes inside a string
    standing skipped, so a deep block stands judged
    without a parse and without recursion, in the form
    the depth judgement of the cured seam at states for a
    parsed value."""
    depth = 0
    deepest = 0
    in_string = False
    escaped = False
    for char in block:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > deepest:
                deepest = depth
        elif char in "]}":
            if depth > 0:
                depth -= 1
    return deepest


def _front_matter_key_count(page_file):
    """The top level key count of one page's front matter block.

    The count stands taken over the whole block, not inside a
    reading window: a block past any fixed window holds its keys
    under the limit its record states, so the file stands read
    whole here and the count runs to the closing fence wherever
    it stands. Where the first line is not a front matter fence,
    no block stands and None stands returned.

    The block this counter reads is the one block the parser
    reads: the block closes at a line whose judged fence form is
    the opening fence or the dots fence, the two closings the
    acquisition reading and the import seam counter both state,
    and a block with no closing fence stands as no block at all,
    its body lines counted as nothing. The flow form stands as
    the parser reads it: a block whose stripped text opens with
    a brace stands parsed as a JSON object and its top level
    keys stand counted, on one line or spread over indented
    lines alike. The line form counts the lines the parser's own
    line reading judges as key value pairs, blank lines and
    comment lines among the lines it passes over."""
    try:
        with open(str(page_file), "rb") as handle:
            raw = handle.read()
    except (OSError, ValueError, UnicodeError):
        return None
    # The count stands taken on the same text the parser
    # parses: the extraction path strips one leading
    # byte order mark before it parses the block, so
    # this counter strips the same mark before it reads
    # the fence.
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[len(b"\xef\xbb\xbf"):]
    text = raw.decode("utf-8", errors="ignore")
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines()
    if not lines or _fence_form(lines[0]) != "---":
        return None
    block_lines = []
    closed = False
    for line in lines[1:]:
        if _fence_form(line) in ("---", "..."):
            closed = True
            break
        block_lines.append(line)
    if not closed:
        return None
    block = "\n".join(block_lines).strip()
    if block.startswith("{"):
        # The block stands judged on its nesting depth
        # ahead of its parse, on the iterative count
        # above, under the same depth discipline as the
        # cured seam at: a block nesting past the JSON
        # nesting depth limit of 100 refuses here in the
        # recorded vocabulary, and a parse that still
        # meets the platform recursion standing converts
        # to the same refusal on the catch below, so no
        # nesting form escapes the audit route as a raw
        # RecursionError at any depth (on the discipline
        # of).
        if _front_matter_block_depth(block) > 100:
            _fail(
                "LIMIT_EXCEEDED",
                "JSON nesting depth limit is 100 in force "
                "for this run, with rejection and no "
                "partial record")
        import json
        try:
            parsed = json.loads(
                block, object_pairs_hook=_flow_pairs_hook)
        except ValueError:
            parsed = None
        except RecursionError:
            _fail(
                "LIMIT_EXCEEDED",
                "JSON nesting depth limit is 100 in force "
                "for this run, with rejection and no "
                "partial record")
        if isinstance(parsed, dict):
            return _flow_key_count(parsed)
    from citeline import acquisition as acquisition_module
    pair_reading = getattr(
        acquisition_module, "_front_matter_key_value", None)
    count = 0
    for line in block_lines:
        if pair_reading is not None:
            if pair_reading(line) is not None:
                count += 1
        elif line and not line[0].isspace() and not line.startswith(
                "#") and ":" in line:
            count += 1
    return count


def _audit_preflight_limits(home, page_file, start_limits):
    """The audit seam limit checks, against the limits in force.

    Limit 1, page file size, and limit 12, front matter key
    count, stand enforced here before any extraction runs, at
    the values in force for the run the service assigns: a
    config set value governs the audit path, not the hardcoded
    default of the component below."""
    by_limit = (start_limits or {}).get("by_limit") or {}
    size_entry = by_limit.get("page_file_size") or {}
    size_limit = size_entry.get("value")
    if isinstance(size_limit, (int, float)):
        try:
            size = os.path.getsize(str(page_file))
        except OSError:
            size = None
        if size is not None and size > size_limit * 1024 * 1024:
            _fail(
                "LIMIT_EXCEEDED",
                "page file size limit is %s MiB in force "
                "for this run, with rejection and no "
                "partial record" % (size_limit,))
    key_entry = by_limit.get("front_matter_key_count") or {}
    key_limit = key_entry.get("value")
    if isinstance(key_limit, (int, float)):
        count = _front_matter_key_count(page_file)
        if count is not None and count > key_limit:
            _fail(
                "LIMIT_EXCEEDED",
                "front matter key count limit is %s, with "
                "rejection and no partial record" % (key_limit,))


def _cap_evidence_spans(check_results, by_limit):
    """The evidence limits on one audit's check results.

    Limits 19, 20, and 21 (evidence excerpt length,
    evidence spans per check, evidence spans per report)
    stand enforced on the record the audit stores, at the
    values in force for its run: excerpts stand cut at
    the excerpt length, each check keeps at most its span
    count, and the record keeps at most the report span
    count in total, in check order."""
    def value_of(key, default):
        entry = (by_limit or {}).get(key) or {}
        value = entry.get("value")
        return value if isinstance(value, (int, float)) else default

    per_check = int(value_of("evidence_spans_per_check", 20))
    excerpt_limit = int(value_of("evidence_excerpt_length", 120))
    remaining = int(value_of("evidence_spans_per_report", 200))
    capped = []
    for result in check_results:
        if not isinstance(result, dict):
            capped.append(result)
            continue
        spans = result.get("evidence_spans")
        if isinstance(spans, list):
            keep = []
            for span in spans[:per_check]:
                if remaining <= 0:
                    break
                if isinstance(span, dict) and isinstance(
                        span.get("excerpt"), str) and len(
                        span["excerpt"]) > excerpt_limit:
                    span = dict(span)
                    span["excerpt"] = span["excerpt"][:excerpt_limit]
                keep.append(span)
                remaining -= 1
            result = dict(result)
            result["evidence_spans"] = keep
        capped.append(result)
    return capped


@contextlib.contextmanager
def _audit_assembly_lock(home):
    """Hold the home write lock across one audit assembly.

    The audit assembly computes its run identity and its
    snapshot citation from the standing entry count, and
    reads its limits under that run identity: where an
    unrelated append lands between that reading and the
    batch, the stored record cites a snapshot that denotes
    another entry or none, and states limits read under an
    identity the record does not carry. The assembly
    therefore stands inside the journal write lock, as the
    import judgement stands inside it: an append that
    meets the hold stands contended and stores nothing,
    the batch appends inside the hold join it, and the
    identities the assembly computed stand as the
    identities the storing entries resolve."""
    journal = _journal()
    lock_class = getattr(journal, "_WriteLock", None)
    if lock_class is None:
        yield
        return
    with lock_class(str(home)):
        yield


def _audit_correction_record(stored, true_snapshot_id):
    """The corrected form of one standing audit record.

    The correction restates two things and no more: the
    snapshot identity, which stands as the identity of
    the snapshot entry the record's own batch stored,
    and the limits statement, which stands rebuilt from
    the one limits reading the run started under and no
    other. The stored record's own limits statement is
    that reading: its by_limit stands as read at the
    run's start, so the correction keeps that by_limit
    whole and restates only the run identity the
    statement stands under, the identity the record
    itself carries. No fresh reading of the limits in
    force stands taken here, so a config shift landing
    after the batch cannot put the corrected record's
    statement on a reading the run never enforced."""
    corrected = copy.deepcopy(stored)
    if true_snapshot_id is not None:
        corrected["snapshot_id"] = true_snapshot_id
    stated = stored.get("limits_in_force")
    if isinstance(stated, dict):
        limits = copy.deepcopy(stated)
        limits["run_id"] = stored.get("run_id")
        limits.pop("run_reported", None)
        corrected["limits_in_force"] = limits
    return corrected


def _audit_record_correction_owed(home, audit_sequence, stored):
    """The correction one standing audit record stands owed,
    or None where the record already denotes its batch.

    A record stands owed a correction where the snapshot
    identity it carries is not the identity of the
    snapshot entry its own batch stored, the entry
    standing immediately before its own in the journal,
    or where its limits statement stands under a run
    identity the record does not carry. Returns the
    corrected record where one stands owed.
    """
    true_snapshot_id = None
    if isinstance(audit_sequence, int):
        for entry in _fold(home):
            if _get(entry, "sequence") == audit_sequence - 1 \
                    and _get(entry, "entry_kind") == \
                    "snapshot_registered":
                true_snapshot_id = _payload(entry).get(
                    "snapshot_id")
    stated_limits = stored.get("limits_in_force") or {}
    if (true_snapshot_id is not None
            and stored.get("snapshot_id") != true_snapshot_id) \
            or (isinstance(stated_limits, dict)
                and stated_limits
                and stated_limits.get("run_id")
                != stored.get("run_id")):
        return _audit_correction_record(stored, true_snapshot_id)
    return None


def _land_audit_correction(home, audit_sequence, stored,
                           audit_date=None):
    """Land the correction one audit record stands owed.

    The correction append stands judged at its own site:
    where the append cannot land, at the journal cap
    among its forms, the failure stands as the audit's
    own refusal, raised to the caller, never passed over
    in silence with the uncorrected record returned as
    success. Returns the corrected record where the
    correction lands, and None where no correction
    stands owed."""
    corrected = _audit_record_correction_owed(
        home, audit_sequence, stored)
    if corrected is None:
        return None
    journal = _journal()
    journal.append_entry(
        str(home), "correction",
        {"supersedes_sequence": audit_sequence,
         "corrected_record": corrected},
        audit_date=audit_date)
    return corrected


def _audit_impl(*, home, page_file=None, robots_file=None,
                evaluated_page_path=None, audit_date=None,
                product=None, run_id=None):
    """One audit: recovery first, then the assembly.

    A killed batch standing on the home stands recovered
    before any count this assembly reads, and a fresh
    audit's assembly and its batch stand inside the write
    lock, so no append and no recovery truncation inside
    the invocation moves the snapshot or the run the
    record names."""
    home = _require_home(home)
    _recover_interrupted_batch(home)
    if run_id is None and page_file is not None:
        with _audit_assembly_lock(home):
            result = _audit_body(
                home=home, page_file=page_file,
                robots_file=robots_file,
                evaluated_page_path=evaluated_page_path,
                audit_date=audit_date, product=product,
                run_id=run_id)
        # The assembly hold stands closed against a batch
        # intent record planted inside it: the assembly
        # lock barred the recovery from judging an intent
        # planted during the hold, so the intent stands
        # judged here, after the hold releases and before
        # the assembly's entries stand reported settled.
        # Where the judgement lands, the killed batch's
        # rollback truncates the assembly's own entries
        # with the batch's, and the audit stands refused at
        # row I-2 instead of returning a record over
        # truncated entries. Where the record still stands
        # unjudged after the attempt, at a deferred cap
        # among its forms, the refusal stands the same, in
        # the journal's own token for the state it names.
        journal = _journal()
        intent_path = getattr(
            journal, "_batch_intent_path", None)
        if intent_path is not None and os.path.lexists(
                intent_path(str(home))):
            landed = journal.recover_interrupted_batch(
                str(home))
            if landed:
                _fail(
                    "JOURNAL_VERIFY_FAILED",
                    "a batch intent record planted inside "
                    "the assembly hold stood judged after "
                    "the hold released, and its rollback "
                    "truncated the assembly's entries; the "
                    "audit stands refused")
            _signal_deferred_recovery(home, journal)
            if os.path.lexists(intent_path(str(home))):
                _fail(
                    "JOURNAL_VERIFY_FAILED",
                    "a batch intent record planted inside "
                    "the assembly hold stands unjudged after "
                    "the hold released; the audit stands "
                    "refused")
        return result
    return _audit_body(
        home=home, page_file=page_file, robots_file=robots_file,
        evaluated_page_path=evaluated_page_path,
        audit_date=audit_date, product=product, run_id=run_id)


def _audit_body(*, home, page_file=None, robots_file=None,
                evaluated_page_path=None, audit_date=None,
                product=None, run_id=None):
    """One audit, assembled as caller over its components.

    A call naming a standing run by its run_id stands as a
    form request on that run, on the invocation to artefact
    mapping: it returns the stored audit record of that run
    and appends nothing, so a second form of a standing
    audit renders the stored record and runs no new audit.
    The run identity stands alone in such a call: a call
    naming run_id together with any fresh audit input, a
    page file, a robots file, an audit date, an evaluated
    page path, or a product, refuses as a malformed call at
    row U-8, token MALFORMED_CALL, usage class, exit 2, and
    no named input is silently disregarded. A call naming
    no run stands as a fresh audit and creates a new run,
    as below. An unknown run identity fails with the
    recorded value for an unknown round identity, the value
    the guide route already returns for a missing audit
    record identity.

    The audit date of a fresh audit stands under brief
    Section 6.2, M1: where no audit date stands supplied,
    the date defaults to the current date in UTC, that date
    is the date the run runs, and the stored record carries
    it in audit_date with audit_date_defaulted true beside
    it, naming the date used; a supplied date is recorded
    as supplied, with audit_date_defaulted false. Where the
    date was defaulted, audit_date_is_run_date is true by
    construction, because the default audit date is the
    current date in UTC; the stored boolean otherwise
    stands exactly as it stood before this recording.

    The snapshot stands produced by the acquisition
    component, the checks and the score by the checks
    component, and the robots summary, where a robots file
    stands supplied, by the robots evaluation. A supplied
    robots file that stands rejected fails the whole audit,
    and no audit record stands for it. The assembled record
    stands stored as one audit_record entry through the
    journal.

    Where the call names a product, that product stands as
    the record product: a caller that runs an audit for one
    named target, as the watch does, passes the target
    product at this seam, and the record, the checks, and
    the snapshot all stand for that product. Where no
    product stands named, the first listed product of the
    home stands as the record product, as before."""
    audit_date = _validate_audit_date(audit_date)
    _barred_check(home)
    home = _require_home(home)
    _guard_supplied_path(page_file)
    _guard_supplied_path(robots_file)
    # The evaluated page path stands under the same guard:
    # it is stored on the snapshot and on the audit
    # record, so an unsafe form reaches the journal
    # hashing in stored form, and the guard refuses it
    # here in the governed vocabulary the audit wrapper
    # converts, as it refuses its sibling paths.
    _guard_supplied_path(evaluated_page_path)
    run_started = _clock()
    run_candidate = None
    start_limits = None
    if run_id is None and page_file is not None:
        # The run identity the service assigns this audit:
        # the snapshot entry the extraction appends stands
        # first and the audit record second, so the record
        # sequence stands two past the standing count. The
        # run's limits in force stand read under that
        # identity at the run's start, so a raise for the
        # run reaches its appends and its record states the
        # limits the run started under.
        run_candidate = "run-%d" % (_entry_count(home) + 2)
        start_limits = _limits_in_force(home, run_candidate)
        # The audit appends twice, a snapshot entry during
        # extraction and its audit record after: where the
        # journal holds room for fewer than both, the call
        # stands refused before either stands written, in
        # the multi append discipline of.
        try:
            cap = ((start_limits.get("by_limit") or {}).get(
                "journal_length") or {}).get("value")
            if cap is not None and _entry_count(home) + 2 > cap:
                raise _preflight_refusal(39, operation="audit")
        except errors.CitelineError:
            raise
        except Exception:
            pass
        _audit_preflight_limits(home, page_file, start_limits)
    if run_id is not None:
        fresh_named = [
            name for name, value in (
                ("page_file", page_file),
                ("robots_file", robots_file),
                ("evaluated_page_path", evaluated_page_path),
                ("audit_date", audit_date),
                ("product", product),
            ) if value is not None]
        if fresh_named:
            _fail(
                "MALFORMED_CALL",
                "an audit call naming a run identity names "
                "no fresh audit input beside it; the call "
                "also names %s, so it stands as neither a "
                "form request on the standing run nor a "
                "fresh audit" % ", ".join(fresh_named))
        standing = None
        standing_sequence = None
        for entry in _fold(home, apply_corrections=True):
            if _get(entry, "entry_kind") != "audit_record":
                continue
            payload = _payload(entry)
            # The stored record stands validated as it is
            # scanned, before its identity is compared, as
            # the guide assembly on the same store states:
            # a swapped identity field stands judged at
            # this reader in the recorded vocabulary naming
            # the field, instead of the standing run
            # reading as unknown, or a standing sibling run
            # standing handed out over a swapped record
            # beside it.
            _validate_audit_payload(payload)
            if payload.get("run_id") == run_id:
                standing = payload
                standing_sequence = _get(entry, "sequence")
        if standing is None:
            _fail(
                "UNKNOWN_ROUND",
                "no completed audit record stands under the "
                "identity given: %r" % (run_id,))
        # The form request reader stands under the stored
        # audit field discipline its sibling reader
        # enforces: the record stands judged by the same
        # validation the full fold runs before it stands
        # handed out, so a swapped field refuses here as it
        # refuses at every other reader of the stored
        # record.
        _validate_audit_payload(standing)
        # A standing record whose assembly correction never
        # landed, the correction refused at the cap among
        # its forms, stands healed at this reader where the
        # correction can land now: the correction lands
        # here, rebuilt from the run's own reading, and the
        # corrected record stands returned; where the
        # correction still cannot land, the form request
        # stands refused with it, never returning the
        # miscited record as the run's form.
        healed = _land_audit_correction(
            home, standing_sequence, standing,
            audit_date=audit_date)
        if healed is not None:
            standing = healed
        result = copy.deepcopy(standing)
        result["audit_run"] = copy.deepcopy(standing)
        return result
    if page_file is None:
        _fail(
            "VALIDATION_FAILED",
            "an audit call names no page file and no standing "
            "run identity")
    audit_date_defaulted = audit_date is None
    if audit_date_defaulted:
        import datetime
        audit_date = datetime.datetime.now(
            datetime.timezone.utc).date().isoformat()
    journal = _journal()
    products = list_products(home=home)
    product_record = None
    if product is not None:
        for candidate in products:
            if candidate.get("product_id") == product \
                    or candidate.get("name") == product:
                product_record = candidate
                break
        if product_record is None:
            product_record = _require_product(home, product)
    if product_record is None and products:
        product_record = products[0]
    if product_record is not None:
        _require_typed_field(
            product_record, "canonical_line", str, "product")
        _validate_product_record(product_record)
    product_id = (
        product_record.get("product_id") if product_record else None)
    from citeline import acquisition
    # The extraction runs without registering its snapshot:
    # the snapshot append and the audit record append land
    # together on the atomic batch at the end of this
    # assembly, or not at all. The run identity travels to
    # the extraction reading, so one reading of the limits
    # in force governs both gates.
    extraction = acquisition.extract_page(
        str(home), product_id=product_id, page_path=str(page_file),
        audit_date=audit_date,
        evaluated_page_path=evaluated_page_path,
        run_id=run_candidate, register_snapshot=False,
        limits_in_force=(start_limits or {}).get("by_limit"))
    # Limit 42, the per file parse time backstop, read
    # over the extraction this run performed.
    parse_limit = ((start_limits or {}).get("by_limit") or {}).get(
        "per_file_parse_time", {}).get("value")
    if isinstance(parse_limit, (int, float)) and \
            _clock() - run_started > parse_limit:
        _fail(
            "LIMIT_EXCEEDED",
            "per file parse time backstop is %s seconds in "
            "force for this run, and the parse of this page "
            "passed it" % (parse_limit,))
    snapshot = extraction["snapshot"]
    extracted = extraction["extracted"]
    facts = {
        "product_name": (
            product_record.get("name") if product_record else None),
        "aliases": (
            list(product_record.get("aliases") or [])
            if product_record else []),
        "category_terms": (
            list(product_record.get("category") or [])
            if product_record else []),
        "canonical_line": (
            product_record.get("canonical_line")
            if product_record else None),
        "is_product_page": bool(snapshot.get("is_product_page")),
        "domain": (
            product_record.get("domain") if product_record else None),
        "competitors": (
            list(product_record.get("competitors") or [])
            if product_record else []),
    }
    from citeline import checks as checks_module
    check_results = checks_module.run_checks(
        extracted, facts, audit_date=audit_date)
    score = checks_module.compute_score(check_results)
    check_results = _cap_evidence_spans(
        check_results, (start_limits or {}).get("by_limit"))
    robots_summary = None
    if robots_file is not None:
        robots_summary = _robots_evaluation(
            home=home, robots_file=robots_file,
            evaluated_page_path=snapshot.get("evaluated_page_path"),
            audit_date=audit_date,
            path_defaulted=snapshot.get("path_defaulted"))
    # The run identity derives from the journal sequence
    # of the entry that stores this record, resolved by
    # the append itself under its write lock: the marker
    # stands in the payload in place of any count read
    # taken here.
    run_id = "run-{sequence}"
    # The guide's trigger codes name the check by the stem
    # the guide's closed list states. Three checks carry a
    # stem shorter than their check id: description
    # consistency fires as DESCRIPTION, keyword stuffing as
    # KEYWORD, and unproven superlatives as SUPERLATIVES.
    # The carry states the guide's stems, so a firing check
    # reaches the guide under the code the guide reads.
    trigger_stems = {
        "answer_first": "ANSWER_FIRST",
        "citations": "CITATIONS",
        "statistics": "STATISTICS",
        "quotations": "QUOTATIONS",
        "comparison": "COMPARISON",
        "freshness": "FRESHNESS",
        "description_consistency": "DESCRIPTION",
        "keyword_stuffing": "KEYWORD",
        "fluff": "FLUFF",
        "unproven_superlatives": "SUPERLATIVES",
    }
    triggers = []
    for result in check_results:
        status_value = _get(result, "status")
        check_id = _get(result, "check_id")
        stem = trigger_stems.get(
            str(check_id), str(check_id).upper())
        if status_value == "fail":
            triggers.append("FAIL_" + stem)
        elif status_value == "warn":
            triggers.append("WARN_" + stem)
    cited_count = None
    for result in check_results:
        if _get(result, "check_id") == "citations":
            counts = _get(result, "detail_counts") or {}
            if isinstance(counts, dict):
                cited_count = counts.get("distinct_target_count")
    # The record states the limits in force at the run's
    # start, under the run identity the service assigned.
    # Where the config changed during the run, the change
    # stands recorded beside them, in the limits the
    # record was read under at its assembly, so the run
    # can show the change .
    limits_record = start_limits if start_limits is not None \
        else _limits_in_force(home, run_candidate)
    current_limits = _limits_in_force(home, run_candidate)
    if current_limits.get("by_limit") != limits_record.get(
            "by_limit"):
        limits_record = dict(limits_record)
        limits_record["config_changed_during_run"] = {
            "limits_at_record": current_limits.get("by_limit"),
        }
    # Limit 41, the per run wall clock backstop, read over
    # the whole run before its record stands appended.
    run_limit = ((start_limits or {}).get("by_limit") or {}).get(
        "per_run_wall_clock_backstop", {}).get("value")
    if isinstance(run_limit, (int, float)) and \
            _clock() - run_started > run_limit:
        _fail(
            "LIMIT_EXCEEDED",
            "per run wall clock backstop is %s seconds in "
            "force for this run, and this run passed it"
            % (run_limit,))
    # The snapshot identity the batch append will resolve:
    # the snapshot entry stands first in the batch, so its
    # sequence stands one past the standing count, and the
    # record names the identity that append will store.
    stated_snapshot_id = snapshot.get("snapshot_id")
    if stated_snapshot_id and "{sequence}" not in str(
            stated_snapshot_id):
        snapshot_id = stated_snapshot_id
    else:
        snapshot_id = "snap-%d" % (_entry_count(home) + 1)
    record = {
        "run_id": run_id,
        "product_id": product_id,
        "snapshot_id": snapshot_id,
        "snapshot_sha256": snapshot.get("sha256"),
        "evaluated_page_path": snapshot.get("evaluated_page_path"),
        "path_defaulted": bool(snapshot.get("path_defaulted")),
        "snapshot_format": snapshot.get("format"),
        "checks": check_results,
        "score": score,
        # No facts_counts field stands on the record
        # (Step 19 queue addition U-11): the field stands
        # as a blocked gap on L-CC-4, outside the traced
        # field set of the audit artefact, and a
        # placeholder for a blocked gap is not a traced
        # field, so the stored record carries none.
        "robots_summary": robots_summary,
        "audit_date": audit_date,
        "audit_date_defaulted": audit_date_defaulted,
        "audit_date_is_run_date": True,
        "limits_in_force": limits_record,
        "registry_version": (
            product_record.get("registry_version", 1)
            if product_record else 1),
        "methods_note_version": METHODS_NOTE_VERSION,
        "detector_version": _detector_version(),
        "query_set_version": (
            product_record.get("query_set_version", 1)
            if product_record else 1),
        "ruleset_version": score.get("score_ruleset_version"),
        "score_ruleset_version": score.get("score_ruleset_version"),
        "robots_ruleset_version": (
            robots_summary.get("robots_ruleset_version")
            if isinstance(robots_summary, dict) else None),
        "honesty_sentence": _honesty_sentence(),
        "bounds": _bounds(),
        "canonical_line": facts["canonical_line"],
        "product_name": facts["product_name"],
        # The selection inputs of the run stand stored on
        # the record, as they stood at the run: the aliases
        # and category terms in force at audit time, so a
        # guide drafted from the run reads the run time
        # basis from the record itself and no later
        # registry state enters the draft (the service
        # route limb).
        "aliases": list(facts["aliases"]),
        "category_terms": list(facts["category_terms"]),
        "sentences": list(_get(extracted, "sentences", []) or []),
        "trigger_codes": triggers,
        "distinct_cited_target_count": cited_count,
    }
    # The audit appends land whole or not at all, on the
    # atomic batch primitive the import route uses (on the
    # multi append discipline): the snapshot entry and the
    # audit record stand in one batch, so a failure, a
    # kill, or contention between them leaves no orphan
    # snapshot, and a contended audit stores nothing, as
    # its contract states.
    batch = [
        ("snapshot_registered", copy.deepcopy(snapshot)),
        ("audit_record", copy.deepcopy(record)),
    ]
    appended = journal.append_entries_atomic(
        str(home), batch, audit_date=audit_date,
        run_id=run_candidate)
    stored = record
    stored_snapshot = snapshot
    audit_sequence = None
    for entry in appended or []:
        if _get(entry, "entry_kind") == "audit_record":
            stored = _payload(entry) or record
            audit_sequence = _get(entry, "sequence")
        elif _get(entry, "entry_kind") == "snapshot_registered":
            stored_snapshot = _payload(entry) or snapshot
    # The batch primitive runs its own head recovery
    # inside this hold, after the assembly read the
    # standing count for its citation and its limits run
    # identity: a recovery landing there appends its
    # ruled record and moves every sequence the count
    # based identities denote. Where the storing entries
    # show that move, the assembly stands a correction
    # over its own record at its store, so the standing
    # record denotes the snapshot entry its own batch
    # stored and states its limits under the run
    # identity the record itself carries, as the
    # identity discipline of states for the entries the
    # append resolved.
    if audit_sequence is not None:
        # The correction stands landed or the audit stands
        # refused, never a success reported over a
        # correction that never landed: the append failure
        # propagates as the audit's own refusal, in the
        # recorded vocabulary of the state that barred it,
        # and the corrected record is rebuilt from the
        # run's own start reading by the shared correction
        # builder.
        landed = _land_audit_correction(
            home, audit_sequence, stored, audit_date=audit_date)
        if landed is not None:
            stored = landed
    result = dict(stored)
    result["snapshot"] = stored_snapshot
    result["audit_run"] = dict(stored)
    return result


def audit(*, home, page_file=None, robots_file=None,
          evaluated_page_path=None, audit_date=None,
          product=None, run_id=None):
    """One audit: the public route over the assembly above.

    A failed audit over a healthy chain far below cap
    appends exactly one failure record, as the failure
    record claim of brief Section 5.2 states for reading
    and non appending operations as for writing ones; the
    barred chain, cap, and contention exceptions stand in
    the appending helper, as they stand for the import
    route."""
    try:
        audit_date = _validate_audit_date(audit_date)
    except errors.CitelineError as exc:
        # The date validation stands inside the recording
        # discipline: its refusal appends exactly one
        # failure record, as every other governed failure
        # of the route.
        _append_failure_record(
            home, "audit", exc,
            page_file if page_file is not None else run_id,
            audit_date)
        raise
    try:
        return _audit_impl(
            home=home, page_file=page_file,
            robots_file=robots_file,
            evaluated_page_path=evaluated_page_path,
            audit_date=audit_date, product=product,
            run_id=run_id)
    except errors.CitelineError as exc:
        if getattr(exc, "token", None) != "MALFORMED_CALL" \
                and getattr(exc, "token", None) \
                not in _LOOKUP_REFUSAL_CODES:
            _append_failure_record(
                home, "audit", exc,
                page_file if page_file is not None else run_id,
                audit_date)
        raise
    except Exception as exc:
        # A governed failure class of this route whose
        # error type is not the recorded error type, the
        # robots component error among them, stands caught
        # here all the same: it converts to the recorded
        # error of its token, and its failure record stands
        # appended exactly once, as for every governed
        # failure of the route.
        token = getattr(exc, "token", None)
        if token is None or errors.error_for_token(token) is None:
            raise
        converted = errors.CitelineError(str(exc), token=token)
        _append_failure_record(
            home, "audit", converted,
            page_file if page_file is not None else run_id,
            audit_date)
        raise converted


def _detector_version():
    try:
        from citeline import detection
        return getattr(detection, "DETECTOR_VERSION", 1)
    except Exception:
        return 1


@contextlib.contextmanager
def _import_judgement_lock(home):
    """Hold the home write lock across one import judgement.

    The duplicate and contradiction judgement and the first
    import stamp decision of an import stand inside the
    journal write lock, with the batch append they govern: a
    caller that meets the lock held stands contended at row
    X-10 and stores nothing, and a caller that takes the
    lock reads the standing answers as they stand at its
    judgement, never as another caller's unstored work left
    them. The batch and single appends inside the judgement
    join the hold on this thread, as the journal lock's own
    re-entry discipline states."""
    journal = _journal()
    lock_class = getattr(journal, "_WriteLock", None)
    if lock_class is None:
        yield
        return
    with lock_class(str(home)):
        yield


# ----------------------------------------------------------------
# Probe import, report, and trend: calls over their components.
# ----------------------------------------------------------------

def _preflight_refusal(limit_number, operation="import"):
    # The refusal context and message name the operation
    # refused (Step 19 entry R19-011): an audit refused at
    # the cap carries the audit context, not an import
    # preflight refusal about an import that never
    # happened.
    if operation == "audit":
        return errors.CitelineError(
            "the journal holds no room for the entries "
            "this audit would append, so the audit stands "
            "refused before any part of it is attempted",
            row="I-1", token="JOURNAL_CAP_EXCEEDED",
            refusal_context="audit_preflight",
            limit_number=limit_number)
    return errors.CitelineError(
        "the journal holds no room for the entries this "
        "import would append, so the import stands refused "
        "before any part of it is attempted",
        row="I-1", token="JOURNAL_CAP_EXCEEDED",
        refusal_context="import_preflight",
        limit_number=limit_number)


def _import_preflight(home, answer_file, extra_entries):
    """The import preflight gate, row I-1.

    Before any byte of the incoming file is read, the
    stated cost of the import (the file size as stat
    states it, beside the journal entries the import
    would append: its answer entry and the first import
    round stamp where one would stand) stands checked
    against limits 39 and 40. Where the cost does not
    fit, the import stands refused here with
    refusal_context import_preflight, in the integrity
    class, ahead of every usage class validation the
    file would otherwise meet."""
    journal = _journal()
    try:
        limits = journal.effective_limits(str(home))
    except Exception:
        return
    count = _entry_count(home)
    needed = 1 + int(extra_entries)
    if count + needed > limits["journal_length"]["value"]:
        raise _preflight_refusal(39)
    try:
        snapshot = journal.status_snapshot(str(home))
        # The snapshot nests the size remaining figure in
        # its capacity outlook (Step 19 entry R19-009): the
        # preflight reads it there, so the limit 40 limb
        # can fire.
        outlook = snapshot.get("capacity_outlook") or {}
        size_remaining = outlook.get("total_home_size_remaining")
        if size_remaining is None:
            size_remaining = snapshot.get(
                "total_home_size_remaining")
        file_size = 0
        if answer_file is not None:
            try:
                file_size = os.path.getsize(str(answer_file))
            except OSError:
                file_size = 0
        if size_remaining is not None and file_size + 4096 > (
                size_remaining):
            raise _preflight_refusal(40)
    except errors.CitelineError:
        raise
    except Exception:
        pass


_SERVICE_JSON_DEPTH_LIMIT = 100


def _service_json_depth(value):
    """The nesting depth of one parsed JSON value, counted
    iteratively so a deep value stands judged without
    recursion, in the form the component readings state:
    the page reading and the import reading each count the
    depth in this form ahead of their measures and refuse
    past the JSON nesting depth limit of 100."""
    depth = 0
    stack = [(value, 1)]
    while stack:
        current, level = stack.pop()
        if isinstance(current, (dict, list)):
            depth = max(depth, level)
            children = current.values() if isinstance(
                current, dict) else current
            for child in children:
                stack.append((child, level + 1))
    return depth


def _service_container_value_measure(value):
    """The container measure in this module's own form.

    The measure stands identical to the import reading
    measure, completed at the key position at: a string
    standing inside a container, as a value or as a key,
    stands measured by its length in characters, a number
    standing inside it by its written form (a written
    number stands as a string holding its token, so its
    length stands as its token length), and the container
    marks, quote marks, and separators of a rendering
    count for nothing. It stands as the fallback measure
    of _import_front_matter_limits where the import
    module's measure does not stand, in place of any
    rendered measure, so no rendered fallback reopens the
    split at the sizes works (the F2 and F4 seams stated
    for this seat)."""
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return sum(
            _service_container_value_measure(key)
            + _service_container_value_measure(item)
            for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return sum(
            _service_container_value_measure(item)
            for item in value)
    return 0


def _import_front_matter_limits(home, answer_file):
    """The front matter limits in force at the import seam.

    The import adapter receives no home, so the brief
    values govern inside it, on the bound recorded at. At
    this seam the home stands known, so the limits in force
    stand enforced here over the answer file's head block,
    as the audit preflight enforces its front matter key
    count at its seam (import limb): limit 11, block size,
    limit 12, key count, and limit 17, value length,
    measured in the forms the component measures on a head
    block. Worksheet slot bodies carry blocks of their own
    inside the sheet and stand under the adapter reading;
    this seam reaches the head block of the file as
    supplied, and no further."""
    block_limit = _limit_value(home, "front_matter_block_size")
    key_limit = _limit_value(home, "front_matter_key_count")
    value_limit = _limit_value(
        home, "front_matter_value_length_per_key")
    if block_limit is None and key_limit is None \
            and value_limit is None:
        return
    try:
        from citeline import probe_import as import_module
        _raw, text, _hash = import_module.read_answer_file(
            str(answer_file), home=home)
    except Exception:
        return
    strip = getattr(import_module, "_strip_head", None)
    working = strip(text) if strip is not None else text
    lines = working.splitlines()
    if not lines or _fence_form(lines[0]) != "---":
        return
    closing = None
    for index in range(1, len(lines)):
        if _fence_form(lines[index]) in ("---", "..."):
            closing = index
            break
    if closing is None:
        return
    block_lines = lines[1:closing]
    # The block size stands measured on the block as it
    # stands in the file, the lines between the fences
    # taken with their terminators at their file width,
    # as the import reading measures it at (the F4 seam
    # stated for this seat), not on the lines rejoined
    # with newline characters.
    kept_lines = working.splitlines(keepends=True)
    block_in_file = "".join(kept_lines[1:closing])
    if block_limit is not None and len(
            block_in_file.encode("utf-8")) \
            > block_limit * 1024:
        _fail(
            "LIMIT_EXCEEDED",
            "front matter block size limit is %s KiB in "
            "force for this home, with rejection and no "
            "partial record" % ("%g" % (block_limit,),))
    block = "\n".join(block_lines).strip()
    if block.startswith("{"):
        import json
        written_number = getattr(
            import_module, "_WrittenNumber", None)
        try:
            if written_number is not None:
                parsed = json.loads(
                    block, parse_int=written_number,
                    parse_float=written_number,
                    object_pairs_hook=_flow_pairs_hook)
            else:
                parsed = json.loads(
                    block, object_pairs_hook=_flow_pairs_hook)
        except Exception:
            return
        if not isinstance(parsed, dict):
            return
        # The nesting depth of the parsed value stands
        # judged at this seam ahead of either container
        # measure, the import measure and the fallback
        # measure alike, on the iterative count above, so
        # a block nesting past the JSON nesting depth
        # limit of 100 refuses here in the recorded
        # vocabulary and no nesting form reaches a
        # recursive measure past the platform recursion
        # standing (on the discipline of).
        if _service_json_depth(parsed) \
                > _SERVICE_JSON_DEPTH_LIMIT:
            _fail(
                "LIMIT_EXCEEDED",
                "JSON nesting depth limit is 100 in force "
                "for this home, with rejection and no "
                "partial record")
        if key_limit is not None \
                and _flow_key_count(parsed) > key_limit:
            _fail(
                "LIMIT_EXCEEDED",
                "front matter key count limit is %s in "
                "force for this home, with rejection and "
                "no partial record" % ("%g" % (key_limit,),))
        if value_limit is not None:
            for key, value in parsed.items():
                # A key of the top level object stands
                # measured by its length in characters at
                # this seam, in the form the cures at state
                # for that position: the loop below measures
                # the values alone, and the container
                # measure it borrows stands applied to
                # container values only, so the key measure
                # stands stated here, ahead of the value
                # measure, in the primary form and in the
                # fallback form alike, neither of which
                # reaches the key.
                if isinstance(key, str) \
                        and len(key) > value_limit:
                    _fail(
                        "LIMIT_EXCEEDED",
                        "front matter value length limit is "
                        "%s characters in force for this "
                        "home, with rejection and no partial "
                        "record" % ("%g" % (value_limit,),))
                # The measurement stands whole on a JSON
                # numeric value, as the module measurement
                # the F4 cure at landed states: a number
                # stands measured by the length of its
                # written form, at a whole value position
                # and inside a container alike, so the
                # limit in force stands enforced on this
                # route as the seam's docstring states.
                # The container measure itself stands
                # completed, as the branch below states.
                if written_number is not None and isinstance(
                        value, written_number):
                    measured = len(str(value))
                elif isinstance(value, str):
                    measured = len(value)
                elif isinstance(value, (dict, list)):
                    # A container stands measured on the
                    # container measure the import reading
                    # states at (the F4 seam stated for this
                    # seat): a string inside the container
                    # by its length in characters, a number
                    # inside it by its written form, and the
                    # container marks, quote marks, and
                    # separators of a rendering counting for
                    # nothing. Where the import module's
                    # measure does not stand, the fallback
                    # stands on the same measure in this
                    # module's own form at
                    # _service_container_value_measure, keys
                    # counted beside values, and no rendered
                    # measure stands as a fallback (the F2
                    # and F4 seams stated for this seat).
                    container_measure = getattr(
                        import_module,
                        "_container_value_measure", None)
                    if container_measure is not None:
                        measured = container_measure(value)
                    else:
                        measured = \
                            _service_container_value_measure(value)
                else:
                    measured = 0
                if measured > value_limit:
                    _fail(
                        "LIMIT_EXCEEDED",
                        "front matter value length limit is "
                        "%s characters in force for this "
                        "home, with rejection and no partial "
                        "record" % ("%g" % (value_limit,),))
        return
    key_value = getattr(
        import_module, "_front_matter_key_value", None)
    if key_value is None:
        return
    key_count = 0
    current_length = None
    for block_line in block_lines:
        if not block_line.strip() or block_line.lstrip() \
                .startswith("#"):
            continue
        pair = key_value(block_line)
        if pair is None:
            if block_line[0] in " \t" \
                    and current_length is not None:
                current_length += len(block_line.strip())
                if value_limit is not None \
                        and current_length > value_limit:
                    _fail(
                        "LIMIT_EXCEEDED",
                        "front matter value length limit "
                        "is %s characters in force for "
                        "this home, with rejection and no "
                        "partial record"
                        % ("%g" % (value_limit,),))
            continue
        key_count += 1
        current_length = len(pair[1])
        if value_limit is not None \
                and current_length > value_limit:
            _fail(
                "LIMIT_EXCEEDED",
                "front matter value length limit is %s "
                "characters in force for this home, with "
                "rejection and no partial record"
                % ("%g" % (value_limit,),))
    if key_limit is not None and key_count > key_limit:
        _fail(
            "LIMIT_EXCEEDED",
            "front matter key count limit is %s in force "
            "for this home, with rejection and no partial "
            "record" % ("%g" % (key_limit,),))


def _worksheet_record_count(answer_file, home=None):
    """The records one worksheet import would append.

    The count stands read from the sheet itself: one
    record per filled slot. A sheet that cannot be read
    or parsed here counts as None, and the preflight
    falls back to the single record cost while the
    worksheet route raises its own recorded error for
    the sheet."""
    try:
        from citeline import probe_import as import_module
        _raw, text, _hash = import_module.read_answer_file(
            str(answer_file), home=home)
        sheet = import_module.parse_worksheet(text)
    except Exception:
        return None
    return sum(1 for slot in sheet.get("slots", [])
               if str(slot.get("body") or "").strip())


def _first_import_extra(home, product, round_label):
    """One where this import would write the round stamps."""
    try:
        product_record = _require_product(home, product)
        round_record = _require_round(home, product_record,
                                      round_label)
    except Exception:
        return 0
    if round_record.get("registry_version_at_first_import") is None:
        return 1
    return 0


def probe_import(*, home, answer_file=None, product=None,
                 round=None, engine_label=None, query=None,
                 kind=None, captured_on=None, capture_method=None,
                 control_designation=None, audit_date=None):
    """One import of one supplied answer file into one round.

    The import component validates and builds the record.
    This caller stores it as one answer_imported entry,
    writes the round two at first import stamps through the
    journal where no stamp stands yet, and, where the
    import fails, appends exactly one failure record where
    the chain accepts appends, on contract C1 terms: none
    on a barred chain, at cap, or under contention.

    The eleven parameter names stand as the inspected
    signature pins them. The eight adapter inputs carry
    defaults of None at this seam: a call omitting one
    binds, and the adapter validation below runs before
    any product or round lookup, so the omission fails
    with the recorded error value IMPORT_VALIDATION_FAILED
    rather than a binding TypeError here, and rather than
    an unknown product or round value raised over a None
    the caller never chose. The seam inputs the adapter
    validation receives are neutral, no membership, no
    standing record, and no control count, so no round
    level check fires ahead of the lookup that owns it.
    """
    home = _require_home(home)
    try:
        # The audit date stands under the service
        # validator's stated discipline and token, as on
        # every sibling route: the input stands normalised
        # here, before the component parser reads it, so a
        # datetime or an integer in basic ISO form stands
        # accepted and recorded as its ISO date text, and
        # a bad string refuses VALIDATION_FAILED, the one
        # token the other operations name this failure in.
        audit_date = _validate_audit_date(audit_date)
    except errors.CitelineError as exc:
        _append_failure_record(
            home, "probe import", exc, answer_file, audit_date)
        raise
    try:
        _guard_supplied_path(answer_file)
    except Exception as exc:
        # The supplied path guard stands at this route's
        # head, before the recording tries below: its
        # refusal stands recorded like every other governed
        # failure of the route, carrying the governed token
        # as its error value and rule fired, never the raw
        # message.
        _append_failure_record(
            home, "probe import", exc, answer_file, audit_date)
        raise
    # A batch killed inside its appends on an earlier
    # invocation stands rolled back before anything here
    # reads the chain, so no partial batch stands as the
    # state this import meets.
    journal = _journal()
    recover = getattr(journal, "recover_interrupted_batch", None)
    if recover is not None:
        try:
            recover(str(home))
        except Exception:
            pass
    _barred_check(home)
    run_started = _clock()
    from citeline import probe_import as import_module
    worksheet = bool(answer_file) and import_module.is_worksheet_file(
        str(answer_file))
    try:
        # The preflight cost of a worksheet import stands
        # counted in the records the sheet would append,
        # beside the first import round stamp, and not as
        # one answer entry however many slots the sheet
        # holds.
        preflight_extra = _first_import_extra(home, product, round)
        if worksheet:
            record_count = _worksheet_record_count(answer_file, home)
            if record_count:
                preflight_extra += record_count - 1
        _import_preflight(home, answer_file, preflight_extra)
        _import_front_matter_limits(home, answer_file)
        # Limits 31 and 3's seam companions, enforced at
        # the values in force before the file's validation
        # runs: the capture method text length stands
        # checked here, in code points, as the engine
        # label length stands checked in the adapter.
        method_limit = _limit_value(
            home, "capture_method_text_length")
        if isinstance(capture_method, str) \
                and method_limit is not None \
                and len(capture_method) > method_limit:
            _fail(
                "LIMIT_EXCEEDED",
                "capture method text length limit is %s "
                "code points, with rejection and no partial "
                "record" % (method_limit,))
    except Exception as exc:
        _append_failure_record(
            home, "probe import", exc, answer_file, audit_date)
        raise
    if worksheet:
        try:
            import_module.validate_adapter_inputs(
                answer_file=answer_file, product=product,
                round=round, engine_label=engine_label,
                query=query, kind=kind, captured_on=captured_on,
                capture_method=capture_method,
                control_designation=control_designation,
                audit_date=audit_date, known_round=True,
                query_set=None, control_count=0)
        except TypeError as exc:
            # The worksheet seam screens the call through the
            # same conversion the plain file adapter runs, so a
            # malformed input set refuses in the recorded
            # vocabulary here too, and its failure record
            # carries that vocabulary value.
            converted = errors.CitelineError(
                "IMPORT_VALIDATION_FAILED: adapter call does "
                "not match the contract inputs: " + str(exc),
                token="IMPORT_VALIDATION_FAILED")
            _append_failure_record(
                home, "probe import", converted, answer_file,
                audit_date)
            raise converted
        except Exception as exc:
            _append_failure_record(
                home, "probe import", exc, answer_file, audit_date)
            raise
    else:
        try:
            import_module.probe_import(
                answer_file=answer_file, product=product,
                round=round, engine_label=engine_label,
                query=query, kind=kind, captured_on=captured_on,
                capture_method=capture_method,
                control_designation=control_designation,
                audit_date=audit_date, known_round=True,
                query_set=None, standing_records=(), control_count=0,
                product_id=None, round_id=None, answer_id=None,
                registry_version_at_import=None,
                detector_version_at_import=None, home=home)
        except Exception as exc:
            _append_failure_record(
                home, "probe import", exc, answer_file, audit_date)
            raise
    with _import_judgement_lock(home):
        try:
            product_record = _require_product(home, product)
            round_record = _require_round(home, product_record, round)
        except Exception as exc:
            _append_failure_record(
                home, "probe import", exc, answer_file, audit_date)
            raise
        product_id = product_record.get("product_id")
        round_id = round_record.get("round_id")
        standing = _answers(home, round_id)
        sequence = _entry_count(home) + 1
        from citeline import probe_import as import_module
        try:
            if worksheet:
                control_count = sum(
                    1 for item in standing
                    if item.get("control_flag"))
                records = import_module.prepare_worksheet_import(
                    answer_file=str(answer_file), product=product,
                    round=round, engine_label=engine_label,
                    query=query, kind=kind, captured_on=captured_on,
                    capture_method=capture_method,
                    control_designation=control_designation,
                    audit_date=audit_date, known_round=True,
                    query_set=list(product_record.get("query_set") or []),
                    standing_records=standing,
                    control_count=control_count,
                    product_id=product_id, round_id=round_id,
                    answer_id_prefix="ans-{sequence}",
                    registry_version_at_import=product_record.get(
                        "registry_version", 1),
                    detector_version_at_import=_detector_version(),
                    answer_sequence_base=sequence, home=home)
            else:
                control_count = sum(
                    1 for item in standing
                    if item.get("control_flag")
                    and item.get("kind") == kind)
                records = [import_module.prepare_import(
                    answer_file=str(answer_file), product=product,
                    round=round, engine_label=engine_label, query=query,
                    kind=kind, captured_on=captured_on,
                    capture_method=capture_method,
                    control_designation=control_designation,
                    audit_date=audit_date, known_round=True,
                    query_set=list(product_record.get("query_set") or []),
                    standing_records=standing,
                    control_count=control_count,
                    product_id=product_id, round_id=round_id,
                    answer_id="ans-{sequence}",
                    registry_version_at_import=product_record.get(
                        "registry_version", 1),
                    detector_version_at_import=_detector_version(),
                    home=home)]
        except Exception as exc:
            _append_failure_record(
                home, "probe import", exc, answer_file, audit_date)
            raise
        try:
            # The seam limits on the prepared records, at the
            # values in force, before anything stands stored:
            # limit 3, extracted text length per answer;
            # limit 22, answers per round; and the two
            # backstops, limit 42 over the preparation and
            # limit 41 over the whole run.
            text_limit = _limit_value(
                home, "extracted_text_length_per_page_or_answer")
            if text_limit is not None:
                for item in records:
                    text = item.get("answer_text")
                    if isinstance(text, str) and len(text) > text_limit:
                        _fail(
                            "LIMIT_EXCEEDED",
                            "extracted text length per answer "
                            "limit is %s characters, with "
                            "rejection and no partial record"
                            % (text_limit,))
            round_limit = _limit_value(home, "answers_per_round")
            if round_limit is not None and len(standing) + len(
                    records) > round_limit:
                _fail(
                    "LIMIT_EXCEEDED",
                    "answers per round limit is %s, with "
                    "rejection and no partial record"
                    % (round_limit,))
            parse_limit = _limit_value(home, "per_file_parse_time")
            if parse_limit is not None and \
                    _clock() - run_started > parse_limit:
                _fail(
                    "LIMIT_EXCEEDED",
                    "per file parse time backstop is %s seconds "
                    "in force, and the preparation of this file "
                    "passed it" % (parse_limit,))
            run_limit = _limit_value(
                home, "per_run_wall_clock_backstop")
            if run_limit is not None and \
                    _clock() - run_started > run_limit:
                _fail(
                    "LIMIT_EXCEEDED",
                    "per run wall clock backstop is %s seconds "
                    "in force, and this run passed it"
                    % (run_limit,))
        except Exception as exc:
            _append_failure_record(
                home, "probe import", exc, answer_file, audit_date)
            raise
        batch = [("answer_imported", copy.deepcopy(item))
                 for item in records]
        if round_record.get("registry_version_at_first_import") is None:
            stamped = dict(round_record)
            stamped["registry_version_at_first_import"] = records[0].get(
                "registry_version_at_import")
            stamped["detector_version_at_first_import"] = records[0].get(
                "detector_version_at_import")
            batch.append(("round_named", stamped))
        try:
            appended = journal.append_entries_atomic(
                str(home), batch, audit_date=audit_date)
        except Exception as exc:
            # The final batch call stands inside this
            # route's failure record discipline, as every
            # failure stage above it stands: a batch
            # failure of the route appends exactly one
            # failure record where the chain accepts
            # appends, on the contract C1 terms the route
            # docstring states, and the failure then
            # raises to the caller as before.
            _append_failure_record(
                home, "probe import", exc, answer_file,
                audit_date)
            raise
        # The identities the appends assigned stand read back
        # from the appended entries themselves, so the record
        # the caller receives names the identity that stands
        # stored.
        appended_answers = [
            _payload(entry) for entry in appended
            if _get(entry, "entry_kind") == "answer_imported"]
        result_records = []
        for index, item in enumerate(records):
            shown = dict(item)
            if index < len(appended_answers) and appended_answers[
                    index].get("answer_id") is not None:
                shown["answer_id"] = appended_answers[index][
                    "answer_id"]
            if not str(shown.get("answer_text") or "").strip():
                shown["import_warning"] = (
                    "Empty answer warning: the file held no "
                    "answer text, and the empty answer stands "
                    "imported and counted in its round. If the "
                    "empty file was the wrong file, import the "
                    "right file under a different capture date")
            result_records.append(shown)
    if len(result_records) == 1:
        return result_records[0]
    return result_records


# The audit route's form request stands apart: a run
# identity that names no standing run is refused as
# UNKNOWN_ROUND and stores nothing, on the E-05 pin.
# The reporting and guide routes hold no such pin, and
# their lookup refusals append a failure record like
# any other governed failure, on the worked cases of.
_LOOKUP_REFUSAL_CODES = frozenset({
    "UNKNOWN_ROUND", "NO_SUCH_PRODUCT"})


def _failure_record_payloads(home):
    """The failure record payloads standing in one home.

    The surfacing assembly limb, carried into the
    records the service routes hand to rendering: the
    stored failure record payloads of the home, in
    journal order, complete as appended.

    The fold stands corrections aware, as the reporting
    readers fold: a correction superseding a failure
    record governs the surface, as it governs every
    other reporting reader. And a stored entry stands on
    the surface whatever its payload holds: an entry
    holding an empty payload is a stored failure record,
    and it surfaces as one, instead of the home reading
    as if no failure stands."""
    payloads = []
    for entry in _fold(home, apply_corrections=True):
        if _get(entry, "entry_kind") == "failure_record":
            payload = _payload(entry)
            # The surfacing readers judge the kind here,
            # at the one assembly every surfacing route
            # reads through.
            _validate_failure_payload(payload)
            payloads.append(payload)
    return payloads


def _surface_failure_records(record, home):
    """Carry one home's failure records into one record.

    The rendering cure of fires on a record that carries
    the payloads; this assembly stands them on the
    record before it is handed to rendering, so a later
    operator can distinguish a home with failed
    operations from a home with none on the operator
    surfaces themselves."""
    if not isinstance(record, dict):
        return record
    try:
        payloads = _failure_record_payloads(home)
    except errors.CitelineError:
        # A stored field refusal of the surfacing
        # assembly stands as the route's own refusal, in
        # the recorded vocabulary; the assembly's
        # silence covers a fold that cannot stand, not a
        # judged field.
        raise
    except Exception:
        return record
    if payloads:
        record["failure_records"] = payloads
    return record


def _append_failure_record(home, operation, exc, subject, audit_date):
    if is_contention(exc):
        return
    if getattr(exc, "token", None) == "LIMIT_EXCEEDED":
        # A cap refusal stores nothing on every route
        # (Step 19 item R19-041): the add product route
        # stores nothing at its cap, through its _fail
        # path, and the routes that append a failure
        # record beside a refusal store nothing at a cap
        # either, so refusal traffic alone cannot spend
        # journal entries on one route and store nothing
        # on another.
        return
    # No state stands created by a read: where no home
    # stands, no failure record stands appended, because
    # the journal append itself would create the home and
    # its journal for a failure whose governed refusal is
    # that the home stands missing (on row U-6).
    try:
        if not os.path.isdir(str(home)):
            return
    except (ValueError, UnicodeError):
        return
    journal = _journal()
    try:
        chain = journal.verify_chain(str(home))
        if not chain.get("passed"):
            return
    except Exception:
        return
    token = getattr(exc, "token", None) or getattr(
        exc, "error_value", None) or str(exc)
    if errors.error_for_token(token) is None:
        # A value outside the closed vocabulary never
        # stands in the journal as an error value: a bare
        # operating system message on a supplied path
        # stands recorded under the row X-4 token its
        # refusal carries.
        if "null byte" in str(exc) or "\x00" in str(exc):
            token = "SUPPLIED_PATH_UNSAFE"
        else:
            token = "VALIDATION_FAILED"
    subject_text = str(subject)
    try:
        subject_text.encode("utf-8")
    except UnicodeEncodeError:
        # A subject no encoding can carry, a supplied path
        # holding a lone surrogate among them, stands
        # recorded in its escaped form, so the failure
        # record itself stands appended and carries the
        # governed token, instead of the append failing in
        # silence on the subject text.
        subject_text = subject_text.encode(
            "utf-8", "backslashreplace").decode("utf-8")
    payload = {
        "operation": operation,
        "error_value": token,
        "subject_identity": subject_text,
        "date": audit_date,
        "rule_fired": token,
    }
    try:
        journal.append_entry(
            str(home), "failure_record", payload,
            audit_date=audit_date)
    except Exception:
        pass


def _bound_product_record(home, product_record, round_record):
    """The product record as it stood at a round's first import.

    The binding of brief item 29: a registry change recorded
    after a round's first import does not bind the round. The
    record that governs the round is the last registry record
    standing at or before the round's first imported answer, or,
    where the round holds no answer, the last standing at or
    before the round's own naming. Where no such record stands,
    the standing product record stands returned. The choice for
    a change landing between imports of one round stands as the
    governed carry states, and this reading does not cure past
    it."""
    entries = _fold(home, apply_corrections=True)
    product_id = product_record.get("product_id")
    round_id = round_record.get("round_id")
    first_import = None
    round_sequence = None
    for entry in entries:
        payload = _payload(entry)
        sequence = _get(entry, "sequence")
        if _get(entry, "entry_kind") == "answer_imported" \
                and payload.get("round_id") == round_id \
                and isinstance(sequence, int):
            if first_import is None or sequence < first_import:
                first_import = sequence
        if _get(entry, "entry_kind") == "round_named" \
                and payload.get("round_id") == round_id \
                and isinstance(sequence, int):
            round_sequence = sequence
    bound = first_import if first_import is not None \
        else round_sequence
    if bound is None:
        return product_record
    standing = None
    for entry in entries:
        payload = _payload(entry)
        sequence = _get(entry, "sequence")
        if _get(entry, "entry_kind") in (
                "product_registered", "registry_change") \
                and payload.get("product_id") == product_id \
                and isinstance(sequence, int) \
                and sequence <= bound:
            standing = payload
    return standing if standing is not None else product_record


def _round_entries(home, product_record, round_record):
    """The entries one round's computation reads.

    The fold stands corrections aware, as the registry
    readers are, and bound to the round's first import
    basis: registry entries recorded after the round's
    first imported answer do not reach the computation,
    on the item 29 binding, stopping at the governed
    carry for a change landing between imports of the
    round."""
    product_id = product_record.get("product_id")
    round_id = round_record.get("round_id")
    entries = _fold(home, apply_corrections=True)
    first_import = None
    round_sequence = None
    for entry in entries:
        payload = _payload(entry)
        sequence = _get(entry, "sequence")
        if _get(entry, "entry_kind") == "answer_imported" \
                and payload.get("round_id") == round_id \
                and isinstance(sequence, int):
            if first_import is None or sequence < first_import:
                first_import = sequence
        if _get(entry, "entry_kind") == "round_named" \
                and payload.get("round_id") == round_id \
                and isinstance(sequence, int):
            round_sequence = sequence
    bound = first_import if first_import is not None \
        else round_sequence
    selected = []
    for entry in entries:
        kind = _get(entry, "entry_kind")
        payload = _payload(entry)
        sequence = _get(entry, "sequence")
        if kind in ("product_registered", "registry_change"):
            if payload.get("product_id") == product_id and (
                    bound is None or not isinstance(
                        sequence, int) or sequence <= bound):
                _validate_product_record(payload)
                selected.append(entry)
        elif kind == "round_named":
            if payload.get("round_id") == round_id:
                selected.append(entry)
        elif kind == "answer_imported":
            if payload.get("round_id") == round_id:
                _validate_answer_payload(payload)
                selected.append(entry)
    return selected


def _round_datum(entries, product_record, round_record):
    """The RoundMetrics datum of one round, from its entries.

    The datum declaration at plan Section 5.1: the registry
    version, detector version, query set version, and
    lexicon version where one is recorded, in force at the
    round's first import. The first two stand on the round
    record the import stamped; the query set version stands
    on the product record; a lexicon version stands in the
    datum only where a selected entry records one.
    """
    datum = {}
    registry_version = round_record.get(
        "registry_version_at_first_import")
    if registry_version is not None:
        datum["registry_version"] = registry_version
    detector_version = round_record.get(
        "detector_version_at_first_import")
    if detector_version is not None:
        datum["detector_version"] = detector_version
    # The query set version stands as it stood at the
    # round's first import (its stamp limb): the bound
    # record of _round_entries' binding, not the standing
    # product record at report time. The bound record
    # travels as the last selected registry entry of the
    # round.
    bound_record = None
    for entry in entries:
        payload = _payload(entry)
        if _get(entry, "entry_kind") in (
                "product_registered", "registry_change") and \
                payload.get("product_id") == product_record.get(
                    "product_id"):
            bound_record = payload
    query_set_version = (
        bound_record.get("query_set_version")
        if bound_record is not None else None)
    if query_set_version is None:
        query_set_version = product_record.get("query_set_version")
    if query_set_version is not None:
        datum["query_set_version"] = query_set_version
    # The importer declaration recorded at round naming
    # stands on the round record, and the metrics sampling
    # frame reads it from the datum this assembly builds, so
    # the declaration travels with the version stamps above.
    declaration = round_record.get("importer_declaration")
    if declaration is not None:
        datum["importer_declaration"] = declaration
    for entry in entries:
        payload = _payload(entry)
        for key in ("lexicon_version", "importer_declaration"):
            if payload.get(key) is not None:
                datum.setdefault(key, payload[key])
        stamps = payload.get("version_stamps")
        if isinstance(stamps, dict) and stamps.get(
                "lexicon_version") is not None:
            datum.setdefault(
                "lexicon_version", stamps["lexicon_version"])
    return datum


def _round_metrics(home, product_record, round_record):
    from citeline import metrics
    entries = _round_entries(home, product_record, round_record)
    datum = _round_datum(entries, product_record, round_record)
    kwargs = {"datum": datum}
    try:
        params = inspect.signature(
            metrics.round_metrics_from_journal).parameters
    except (TypeError, ValueError):
        params = {}
    if "frame" in params:
        kwargs["frame"] = dict(datum)
    return metrics.round_metrics_from_journal(entries, **kwargs)


def _check_run_backstop(home, started):
    """The per run wall clock backstop, limit 41, at this
    seam, on a reporting run.

    The backstop position of the report routes (its
    report route limb): a probe report or trend
    recomputes its figures in this invocation, and that
    run stands under the same limit 41 reading the audit
    and import runs stand under at this seam, through the
    one clock this module reads. At the backstop the run
    aborts with the recorded error LIMIT_EXCEEDED and
    produces no report."""
    limit = _limit_value(home, "per_run_wall_clock_backstop")
    if isinstance(limit, (int, float)) and \
            _clock() - started > limit:
        _fail(
            "LIMIT_EXCEEDED",
            "per run wall clock backstop is %s seconds in "
            "force for this run, and this run passed it"
            % (limit,))


def _check_parse_backstop(home, started):
    """The per file parse time backstop, limit 42, at this
    seam, on a robots reading run (Step 19 entry R19-010).

    At the backstop the run aborts with the recorded
    error LIMIT_EXCEEDED and produces no report.
    """
    limit = _limit_value(home, "per_file_parse_time")
    if isinstance(limit, (int, float)) and \
            _clock() - started > limit:
        _fail(
            "LIMIT_EXCEEDED",
            "per file parse time backstop is %s seconds in "
            "force for this run, and the parse of this "
            "robots file passed it" % (limit,))


def _probe_report_record(home, product_record, round_record,
                         audit_date=None, metrics_record=None):
    """The assembled probe report record of one round.

    The record stands as probe_report renders it: the
    RoundMetrics record the metrics component computes,
    the product and round identities, the first import
    stamps the round record carries, and the methods note
    stamp the ruling names for the RoundMetrics shape.
    """
    _validate_round_stamp_fields(round_record)
    if metrics_record is None:
        metrics_record = _round_metrics(
            home, product_record, round_record)
    result = dict(metrics_record)
    result["product_id"] = product_record.get("product_id")
    result["product"] = product_record.get("name")
    result["round"] = round_record.get("round_label")
    result["round_id"] = round_record.get("round_id")
    result["audit_date"] = audit_date
    result["registry_version_at_first_import"] = round_record.get(
        "registry_version_at_first_import")
    result["detector_version_at_first_import"] = round_record.get(
        "detector_version_at_first_import")
    result["methods_note_version"] = METHODS_NOTE_VERSION
    # The honesty sentence stands on the assembled record
    # itself, so a round report embedded in a trend carries
    # the sentence exactly as the standalone report does.
    result["honesty_sentence"] = _honesty_sentence()
    return result


def probe_report(*, home, product, round, form=None,
                 audit_date=None):
    """One probe report over one named round of one product.

    The report recomputes in this invocation, through the
    metrics component, from the journal entries of the
    round alone, on contract C4 terms. The home returns
    the reporting pipeline rendering of the assembled
    record in the requested form, the prose walk in the
    Simple form and the record object or its envelope in
    the structured forms, never the raw assembly.

    Probe report is a non appending operation (brief
    CL19-177): a failed report appends no failure record
    (Step 19 entry R19-017). The recorded error stands as
    the caller response only.
    """
    audit_date = _validate_audit_date(audit_date)
    run_started = _clock()
    try:
        home = _require_home(home)
        _recover_interrupted_batch(home)
        _barred_check(home)
        # The whole artefact stands on one fold instant:
        # the head fold stands taken here, before the
        # product and round resolution, and every
        # corrections aware fold of the assembly below
        # reads that instant, the figure side and the
        # failure side together, so a correction landing
        # during the assembly enters neither side of this
        # artefact in place of the other, and the whole
        # corrected basis stands read by the next report
        # over the home. The round 4 head surfacing of
        # stands inside this wider instant unchanged.
        fold_token = _FOLD_SNAPSHOT.set(
            _fold(home, apply_corrections=True))
        try:
            product_record = _require_product(home, product)
            round_record = _require_round(
                home, product_record, round)
            result = _probe_report_record(
                home, product_record, round_record,
                audit_date=audit_date)
            _check_run_backstop(home, run_started)
            # Standing failure record payloads stay out of
            # the probe report record (Step 19 entry
            # R19-018): the determinism contract at CL19-146
            # and CL19-181 binds this report, and state left
            # behind by other calls is no input of it.
            from citeline import reporting
            return reporting.render(result, form=form or "advanced")
        finally:
            _FOLD_SNAPSHOT.reset(fold_token)
    except errors.CitelineError:
        raise


def _trend_frame(metrics_record):
    """The trend frame of one round, from its own record.

    The capture method sets, capture dates, engine label
    set, query set, and version stamps the trend contract
    compares stand in the RoundMetrics record itself, in
    its capture context, sampling frame, per query
    breakdown, and version stamps. This assembly reads
    them from that record and hands them to the trend
    computation beside the record, so a capture method
    change between two rounds reaches the computation.
    """
    record = metrics_record if isinstance(metrics_record, dict) \
        else {}
    context = record.get("capture_context") or {}
    sampling = record.get("sampling_frame") or {}
    per_query = record.get("per_query") or {}
    frame = {
        "capture_methods": list(
            context.get("capture_methods")
            or sampling.get("capture_methods_asserted") or []),
        "capture_dates": list(context.get("capture_dates") or []),
        "engine_label_set": list(
            sampling.get("engine_label_set") or []),
        "query_set": list(per_query.keys()),
        "per_query_counts": {
            name: (counts.get("answer_count")
                   if isinstance(counts, dict) else None)
            for name, counts in per_query.items()},
        "cluster_count": record.get("cluster_count"),
        "effective_n": record.get("effective_n"),
    }
    stamps = record.get("version_stamps") or {}
    if isinstance(stamps, dict):
        for key, value in stamps.items():
            if value is not None:
                frame.setdefault(key, value)
    return frame


def probe_trend(*, home, product, round_a, round_b, form=None,
                audit_date=None):
    """One probe trend over two named rounds of one product.

    The home returns the reporting pipeline rendering of
    the assembled trend in the requested form, as the
    probe report home does.

    Probe trend is a non appending operation (brief
    CL19-177): a failed trend appends no failure record
    (Step 19 entry R19-017).
    """
    audit_date = _validate_audit_date(audit_date)
    run_started = _clock()
    try:
        home = _require_home(home)
        _recover_interrupted_batch(home)
        _barred_check(home)
        product_record = _require_product(home, product)
        first = _require_round(home, product_record, round_a)
        second = _require_round(home, product_record, round_b)
        if round_a == round_b:
            raise errors.CitelineError(
                "a trend naming the same round twice stands "
                "refused: %r" % (round_a,),
                token="ROUND_REPEATED")
        from citeline import metrics
        first_metrics = _round_metrics(home, product_record, first)
        second_metrics = _round_metrics(home, product_record, second)
        trend = metrics.compute_trend(
            {"metrics": first_metrics,
             "frame": _trend_frame(first_metrics)},
            {"metrics": second_metrics,
             "frame": _trend_frame(second_metrics)})
        result = dict(trend) if isinstance(trend, dict) else {
            "trend": trend}
        result["product_id"] = product_record.get("product_id")
        result["product"] = product_record.get("name")
        result["round_a"] = round_a
        result["round_b"] = round_b
        result["first_round"] = _probe_report_record(
            home, product_record, first, audit_date=audit_date,
            metrics_record=first_metrics)
        result["second_round"] = _probe_report_record(
            home, product_record, second, audit_date=audit_date,
            metrics_record=second_metrics)
        result["audit_date"] = audit_date
        # The trend assembly carries the honesty sentence at
        # trend level, as the standalone probe report carries
        # it, whether or not the trend computation printed a
        # delta with its own comparability line.
        result["honesty_sentence"] = _honesty_sentence()
        _check_run_backstop(home, run_started)
        _surface_failure_records(result, home)
        from citeline import reporting
        return reporting.render(result, form=form or "advanced")
    except errors.CitelineError:
        raise


def query_set_report(*, home, product, form=None, audit_date=None):
    """The QuerySetReport of one product, from its record alone.

    The home returns the reporting pipeline rendering of
    the derived report in the requested form.

    Query-set-report is a non appending operation (brief
    CL19-177): a failed report appends no failure record
    (Step 19 entry R19-017).

    The report reads the clock (Step 19 entry R19-010):
    limit 41, the per run wall clock backstop, aborts the
    call before its record stands returned.
    """
    audit_date = _validate_audit_date(audit_date)
    run_started = _clock()
    home = _require_home(home)
    _recover_interrupted_batch(home)
    _barred_check(home)
    product_record = _require_product(home, product)
    _validate_product_record(product_record)
    _check_run_backstop(home, run_started)
    from citeline import reporting
    return reporting.query_set_report(
        product_record, form=form or "advanced")


def export_capture_worksheet(*, home, product, round, queries=None,
                             engine_labels=None, planned_answers=0,
                             output_path=None, audit_date=None):
    """One capture worksheet written from a named round definition.

    The worksheet stands written from the named round definition:
    where the call names no query list, the product query set for
    the round stands as the list, and a named query that stands in
    no query set of the product stands refused here, before any
    file stands written . The inputs travel to the worksheet writer
    as they stand, with no string or integer coercion at this seam,
    so a malformed input meets the writer validation in its own
    form and refuses in a recorded error value ."""
    audit_date = _validate_audit_date(audit_date)
    # The home check stands here as it stands on
    # list_products, and the batch recovery stands at
    # the head of this route as at every reading route
    # of the layer, so the worksheet stands judged on
    # recovered state and no artefact stands handed out
    # on a killed batch's partial state.
    home = _require_home(home)
    _recover_interrupted_batch(home)
    product_record = _require_product(home, product)
    _validate_product_record(product_record)
    _require_round(home, product_record, round)
    if queries is None:
        queries = list(product_record.get("query_set") or [])
    elif isinstance(queries, (list, tuple)):
        known = list(product_record.get("query_set") or [])
        for value in queries:
            if value not in known:
                _fail(
                    "VALIDATION_FAILED",
                    "a worksheet query stands in no query "
                    "set for the product: %r; the worksheet "
                    "stands written from the named round "
                    "definition, whose queries are the "
                    "product query set" % (value,))
    from citeline import probe_import as import_module
    return import_module.export_capture_worksheet(
        output_path=output_path, product=product, round=round,
        queries=queries,
        engine_labels=() if engine_labels is None else engine_labels,
        planned_answers=planned_answers, home=str(home))


# ----------------------------------------------------------------
# Guide: calls over the guide component, stored as guide_record.
# ----------------------------------------------------------------

# The guide store re-read bound, stated in the open
# where it binds: the guide assembly re-reads the
# standing audit record at most this many times while
# rebuilding its draft on a record that moved, and the
# store itself stands judged under a sealed hold at the
# append, as the registry cure at states its own bound.
GUIDE_STORE_RE_READ_LIMIT = 5


def _store_guide_draft(home, draft, run_id, basis_record,
                       audit_date):
    """Store one guide draft, judged at the store.

    The final judgement and the append stand inside one
    sealed journal hold: inside the hold the standing
    audit record stands re-read, and where it differs
    from the record the draft stands built, the store
    stands refused and nothing stands stored, so no
    guide stands stored on a superseded basis. A
    correction append attempted by other code inside the
    hold stands contended at the sealed container and
    lands nothing, so the append gate form of the race
    stands closed as the re-read form stands closed. The
    guide append itself joins the hold under the journal
    join authorization for its exact payload."""
    journal = _journal()
    write_lock = getattr(journal, "_WriteLock", None)
    join = getattr(journal, "_join_authorization", None)
    payload = copy.deepcopy(draft)
    if write_lock is None or join is None:
        return journal.append_entry(
            str(home), "guide_record", payload,
            audit_date=audit_date or draft.get("audit_date"))
    with write_lock(str(home), kind="batch"):
        standing = None
        for entry in _fold(home, apply_corrections=True):
            if _get(entry, "entry_kind") != "audit_record":
                continue
            candidate = _payload(entry)
            if candidate.get("run_id") == run_id:
                standing = candidate
        if standing is None or standing != basis_record:
            _fail(
                "VALIDATION_FAILED",
                "the standing audit record at the guide "
                "store differs from the record the draft "
                "stands built on; the guide stands refused "
                "at the store and nothing stands stored")
        lock_path = getattr(journal, "_lock_path", None)
        join_path = lock_path(str(home)) if lock_path \
            is not None else str(home)
        with join(join_path, "guide_record", payload):
            return journal.append_entry(
                str(home), "guide_record", payload,
                audit_date=audit_date or draft.get("audit_date"))


def _store_guide_draft_for_round(home, draft, product_record,
                                 round_record, bound_record,
                                 round_entries, audit_date):
    """Store one product and round guide draft, judged at
    the store.

    The second selector the guide route states stands
    under the same store discipline as the run identity
    selector: the final judgement and the append stand
    inside one sealed journal hold, the basis the draft
    stands built on stands re-read inside the hold, the
    round record, the bound product record, and the round
    entries together, and where any of them differs from
    the basis the draft stands built, the store stands
    refused and nothing stands stored, so no guide taken
    by product and round stores on a superseded basis. A
    correction append attempted by other code inside the
    hold stands contended at the sealed container and
    lands nothing. The guide append itself joins the hold
    under the journal join authorization for its exact
    payload, as the run identity store stands."""
    journal = _journal()
    write_lock = getattr(journal, "_WriteLock", None)
    join = getattr(journal, "_join_authorization", None)
    payload = copy.deepcopy(draft)
    if write_lock is None or join is None:
        return journal.append_entry(
            str(home), "guide_record", payload,
            audit_date=audit_date or draft.get("audit_date"))
    with write_lock(str(home), kind="batch"):
        fresh_product = _find_product(
            home, product_record.get("name")) or product_record
        fresh_round = _round_record(
            home, fresh_product, round_record.get("round_label"))
        if fresh_round is None or fresh_round != round_record:
            _fail(
                "VALIDATION_FAILED",
                "the standing round record at the guide "
                "store differs from the record the draft "
                "stands built on; the guide stands refused "
                "at the store and nothing stands stored")
        fresh_bound = _bound_product_record(
            home, fresh_product, fresh_round)
        if fresh_bound != bound_record:
            _fail(
                "VALIDATION_FAILED",
                "the standing bound product record at the "
                "guide store differs from the record the "
                "draft stands built on; the guide stands "
                "refused at the store and nothing stands "
                "stored")
        fresh_entries = _round_entries(
            home, fresh_product, fresh_round)
        if fresh_entries != round_entries:
            _fail(
                "VALIDATION_FAILED",
                "the standing round entries at the guide "
                "store differ from the entries the draft "
                "stands built on; the guide stands refused "
                "at the store and nothing stands stored")
        lock_path = getattr(journal, "_lock_path", None)
        join_path = lock_path(str(home)) if lock_path \
            is not None else str(home)
        with join(join_path, "guide_record", payload):
            return journal.append_entry(
                str(home), "guide_record", payload,
                audit_date=audit_date or draft.get("audit_date"))


def _guide_impl(*, home, run_id=None, product=None,
                round_label=None, audit_date=None):
    """One guide draft, from one audit record or one round.

    The draft stands computed by the guide component from
    the one completed record the call names, and stands
    stored as one guide_record entry through the journal.
    A refusal stands as a completed outcome of the draft
    itself and carries no error value. The re-read loop
    that rebuilds the draft on a moved record stands
    bounded at GUIDE_STORE_RE_READ_LIMIT attempts, stated
    in the open at the constant above, and the store
    stands judged at the store under _store_guide_draft.

    The selector rule (brief Section 5.12) takes exactly
    one of run_id, or product with round label. Both
    selectors named, neither named, or only half of the
    product with round selector named stands as a malformed
    call at row U-8, token MALFORMED_CALL, usage class,
    exit 2. An unknown run identity carries the governed
    value for a missing round at row U-4, token
    UNKNOWN_ROUND, as the branch below states: the closed
    vocabulary holds no run specific token, and the joined
    table assigns guide its missing references at U-4.

    Repeat bound (Step 19 entry R19-023): plan trade T-9
    grants that each repeat call over an unchanged record
    appends a new guide_record, and that grant stands.
    The route reads the clock: every call stands under
    limit 41, the per run wall clock backstop, checked
    before its record stands appended, and repeat appends
    stand bounded in total by limit 39, the journal cap,
    as every append stands. A call whose run passes the
    backstop appends nothing.
    """
    run_started = _clock()
    audit_date = _validate_audit_date(audit_date)
    # The guide assembly runs the home existence check
    # every sibling read only route runs, at row U-6,
    # before its barred check and its lookups, so a guide
    # over a missing home answers HOME_MISSING and creates
    # nothing.
    home = _require_home(home)
    _recover_interrupted_batch(home)
    _barred_check(home)
    if run_id is not None and (
            product is not None or round_label is not None):
        _fail(
            "MALFORMED_CALL",
            "guide takes exactly one of run_id, or product "
            "with round label; both selectors stand named")
    if run_id is None and not (
            product is not None and round_label is not None):
        _fail(
            "MALFORMED_CALL",
            "guide takes exactly one of run_id, or product "
            "with round label; no complete selector stands "
            "named")
    journal = _journal()
    from citeline import guide as guide_module
    if run_id is not None:
        audit_record = None
        for entry in _fold(home, apply_corrections=True):
            if _get(entry, "entry_kind") != "audit_record":
                continue
            payload = _payload(entry)
            # The stored record stands validated as it is
            # scanned, before its identity is compared: a
            # run identity in a swapped type refuses in the
            # recorded vocabulary naming the field, instead
            # of the standing run reading as unknown.
            _validate_audit_payload(payload)
            if payload.get("run_id") == run_id:
                audit_record = payload
        if audit_record is None:
            _fail(
                "UNKNOWN_ROUND",
                "no completed audit record stands under the "
                "identity given: %r" % (run_id,))
        _validate_audit_payload(audit_record)

        def _guide_product_record(record):
            found = None
            for candidate in list_products(home=home):
                if candidate.get("product_id") == record.get(
                        "product_id"):
                    found = candidate
            if found is not None:
                _validate_product_record(found)
            return found

        def _build_guide_draft(record, product_rec):
            built = guide_module.draft_from_audit_record(
                record,
                canonical_line=(
                    product_rec.get("canonical_line")
                    if product_rec else record.get(
                        "canonical_line")),
                audit_date=audit_date or record.get("audit_date"),
                product_name=(
                    product_rec.get("name")
                    if product_rec else record.get(
                        "product_name")),
                aliases=(
                    list(product_rec.get("aliases") or [])
                    if product_rec else []),
                category_terms=(
                    list(product_rec.get("category") or [])
                    if product_rec else []),
                sentences=record.get("sentences"),
                distinct_cited_target_count=record.get(
                    "distinct_cited_target_count"),
                trigger_codes=record.get("trigger_codes") or [])
            if record.get("methods_note_version") is not None:
                built["methods_note_version"] = record[
                    "methods_note_version"]
            return built

        product_record = _guide_product_record(audit_record)
        draft = _build_guide_draft(audit_record, product_record)
        # The guide assembly stands under the identity
        # discipline the audit assembly stands under:
        # the folded audit record stands re-read at the
        # store, and where a correction superseding it
        # landed between the fold and the append, the
        # draft stands rebuilt from the standing record,
        # so no stored guide rests on a superseded audit
        # record while citing its run as its source.
        for _attempt in range(GUIDE_STORE_RE_READ_LIMIT):
            fresh_record = None
            for entry in _fold(home, apply_corrections=True):
                if _get(entry, "entry_kind") != "audit_record":
                    continue
                candidate_payload = _payload(entry)
                _validate_audit_payload(candidate_payload)
                if candidate_payload.get("run_id") == run_id:
                    fresh_record = candidate_payload
            if fresh_record is None \
                    or fresh_record == audit_record:
                break
            audit_record = fresh_record
            product_record = _guide_product_record(audit_record)
            draft = _build_guide_draft(audit_record, product_record)
    else:
        product_record = _require_product(home, product)
        round_record = _require_round(
            home, product_record, round_label)
        from citeline import metrics
        entries = _round_entries(home, product_record, round_record)
        answers = metrics.answer_metrics_from_journal(entries)
        bound_record = _bound_product_record(
            home, product_record, round_record)
        _validate_product_record(bound_record)
        draft = guide_module.draft_from_round(
            round_record,
            canonical_line=bound_record.get("canonical_line"),
            audit_date=audit_date,
            answers=answers)
    _check_run_backstop(home, run_started)
    if run_id is not None:
        entry = _store_guide_draft(
            home, draft, run_id, audit_record, audit_date)
    else:
        entry = _store_guide_draft_for_round(
            home, draft, product_record, round_record,
            bound_record, entries, audit_date)
    result = dict(draft)
    sequence = _get(entry, "sequence", None)
    if sequence is None:
        sequence = _entry_count(home)
    result["guide_id"] = "guide-%d" % int(sequence)
    _surface_failure_records(result, home)
    return result


def guide(*, home, run_id=None, product=None, round_label=None,
          audit_date=None):
    """One guide draft: the public route over the assembly above.

    A failed guide call over a healthy chain far below cap
    appends exactly one failure record, as the audit route
    states."""
    try:
        audit_date = _validate_audit_date(audit_date)
    except errors.CitelineError as exc:
        _append_failure_record(
            home, "guide", exc,
            run_id if run_id is not None else round_label,
            audit_date)
        raise
    try:
        return _guide_impl(
            home=home, run_id=run_id, product=product,
            round_label=round_label, audit_date=audit_date)
    except errors.CitelineError as exc:
        # Every governed failure of this route appends,
        # the unknown run identity and the both selectors
        # malformed call included, on the worked cases
        # of.
        _append_failure_record(
            home, "guide", exc,
            run_id if run_id is not None else round_label,
            audit_date)
        raise


__all__ = [
    "CONTENTION_CLASS",
    "CONTENTION_EXIT_CODE",
    "CONTENTION_FAILURE_RECORD",
    "CONTENTION_ROW",
    "CONTENTION_TOKEN",
    "ServiceError",
    "add_product",
    "audit",
    "contention_fields",
    "estate_grounds",
    "export_capture_worksheet",
    "guide",
    "is_contention",
    "list_products",
    "name_round",
    "probe_import",
    "probe_report",
    "probe_trend",
    "query_set_report",
    "recorded_error",
    "register_page",
    "robots",
    "robots_preview",
    "set_aliases",
    "set_canonical_line",
    "set_category",
    "set_competitors",
    "set_query_set",
    "status",
    "verify",
]
