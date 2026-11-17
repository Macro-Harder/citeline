"""Scheduled estate watch: one round per invocation.

The watch takes a WatchPlan, supplied as one local file,
unstored, and invokes service layer operations over the
one home the plan names. It captures nothing, fetches
nothing, and imports nothing: new sampled answers enter a
round only by having been imported, by hand, before the
round runs. It holds no operation rule of its own, keeps
no schedule and states no cadence, and writes no journal
entry of its own: every write a round makes stands as an
entry of an existing kind, made by the existing operation
the round invokes. The product keeps no cadence and
guarantees none; an operator cadence stands in the plan
cadence field only, read by the freshness view only.

Failure isolation stands at Section 3, W-5, on contract CW
terms. A target whose file stands missing or unreadable,
or whose operation fails, fails that target only: the
failure stands entered in the summary with the operation
recorded error, and the round continues with its next
target. No operation contract stands weakened inside a
target to keep the round moving.

WatchPlan form keys, stated here in the open. The plan
form key governs the form of a round where the invocation
names no form. A form named on the invocation, the watch
--form flag, governs the whole call: the printed rendering
and the written WatchRun artefact take that one form, so
the two can never carry opposite form values.

Contention fields, written here in the plan form at
Section 3, W-5, discharging the W-5 boundary contention
carriage: a contended target invocation fails on the
exclusion recorded error at entry 13 row X-10, token
WRITE_CONTENDED, integrity class. The fields a contended
target entry carries are: outcome, the value failed;
recorded_error, the recorded error record holding row
X-10, error_value WRITE_CONTENDED, precedence_class
integrity, exit_code 5 as the target own code, and the
failure record behaviour that no failure record stands,
the recorded error standing as caller response only;
contention, the boolean true; stored, the boolean false,
because the contended invocation stores nothing for that
target; and no record_identity, because none stands
created. The round exit position stands beside them: a
contended target failure is not the round own error
value, a round whose targets fail only by contention, or
by contention beside other target failures, returns the
code of the round own outcome, which is 0 where the round
completed and produced its summary, and read only targets
in the round stand unaffected by another target
contention. The service module writes the same fields at
the invocation itself, in its contention fields record.
"""

import hashlib
import json
import os
import stat
import time

from citeline import errors, service

WatchError = errors.CitelineError

PLAN_SIZE_BOUND = 1024 * 1024
TARGET_BOUND = 100

# The boundary contention fields of one contended target,
# in the plan form at Section 3, W-5 and entry 13 row
# X-10: the entry outcome value for a contended target,
# the recorded error row and token, its class, its own
# exit code, and the round code position that the round
# returns 0 where it completed and produced its summary.
CONTENTION_OUTCOME = "failed"
CONTENTION_ROW = "X-10"
CONTENTION_TOKEN = "WRITE_CONTENDED"
CONTENTION_CLASS = "integrity"
CONTENTION_TARGET_EXIT_CODE = 5
CONTENTION_ROUND_EXIT_CODE = 0
CONTENTION_FAILURE_RECORD = (
    "No failure record: the recorded error is the caller "
    "response only."
)

_FORMS = ("simple", "advanced", "agentic")


def _fail(token, message):
    raise errors.CitelineError(message, token=token)


def _clock():
    """The wall clock reading for the round backstop check.

    Stated as one seam so the per run wall clock backstop
    (limit 41) reads the clock in one place in this module,
    as the service module reads it in its own seam.
    """
    return time.monotonic()


def _check_round_backstop(home, started):
    """The round level backstop of limit 41 (Step 19 entry
    R19-010, watch limb): a watch round is one invocation,
    so its whole run stands under the per run backstop,
    not only each target under its own operation clock.
    At the backstop the round aborts with the recorded
    error LIMIT_EXCEEDED and produces no artefact.
    """
    limit = service._limit_value(
        home, "per_run_wall_clock_backstop")
    if isinstance(limit, (int, float)) and \
            _clock() - started > limit:
        _fail(
            "LIMIT_EXCEEDED",
            "per run wall clock backstop is %s seconds in "
            "force for this round, and this round passed it"
            % (limit,))


def _contention_entry_fields(exc):
    """The W-5 boundary contention fields for one target.

    The fields stand as the module head states them: the
    outcome value, the recorded error in its row X-10
    form, the contention mark, the stored mark standing
    false, and the round exit code position standing at
    the round own outcome code.
    """
    return {
        "outcome": CONTENTION_OUTCOME,
        "recorded_error": {
            "row": CONTENTION_ROW,
            "error_value": CONTENTION_TOKEN,
            "precedence_class": CONTENTION_CLASS,
            "exit_code": CONTENTION_TARGET_EXIT_CODE,
            "failure_record": CONTENTION_FAILURE_RECORD,
            "message": str(exc),
        },
        "contention": True,
        "stored": False,
        "round_exit_code": CONTENTION_ROUND_EXIT_CODE,
    }


def _failure_fields(exc):
    """The summary fields of one failed target."""
    if service.is_contention(exc):
        return _contention_entry_fields(exc)
    return {
        "outcome": "failed",
        "recorded_error": service.recorded_error(exc),
    }


def _open_plan(plan_file):
    # The plan file path itself stands judged before any
    # filesystem call can raise on it (Step 17 round 3
    # entry S17-R3-049, in the family of S17-R2-077 and
    # S17-R2-078): a path string carrying a NUL character
    # or a lone surrogate names no file at all, and refuses
    # at open as MALFORMED_CALL, in the governed form the
    # unreadable plan file already answers in, never as a
    # raw ValueError or UnicodeEncodeError.
    if isinstance(plan_file, str):
        if "\x00" in plan_file:
            _fail(
                "MALFORMED_CALL",
                "the WatchPlan file path holds a NUL "
                "character and names no file")
        try:
            plan_file.encode("utf-8")
        except UnicodeEncodeError:
            _fail(
                "MALFORMED_CALL",
                "the WatchPlan file path holds a lone "
                "surrogate and names no file")
    try:
        info = os.lstat(str(plan_file))
    except OSError as exc:
        _fail(
            "MALFORMED_CALL",
            "the WatchPlan file stands unreadable: %s" % (exc,))
    if stat.S_ISLNK(info.st_mode):
        _fail(
            "SUPPLIED_PATH_UNSAFE",
            "a supplied path that is itself a symbolic link "
            "is rejected: the WatchPlan file stands in the "
            "same supplied file discipline as every other "
            "input at W-2, opened with no link following")
    if stat.S_ISFIFO(info.st_mode) or stat.S_ISCHR(info.st_mode) \
            or stat.S_ISBLK(info.st_mode) \
            or stat.S_ISSOCK(info.st_mode):
        _fail(
            "SUPPLIED_PATH_UNSAFE",
            "a supplied path that does not name a regular "
            "file is rejected: the WatchPlan file names a "
            "device, a FIFO, or a socket")
    if not stat.S_ISREG(info.st_mode):
        _fail(
            "MALFORMED_CALL",
            "the WatchPlan file stands unreadable: the path "
            "names no regular file")
    if info.st_nlink > 1:
        _fail(
            "SUPPLIED_PATH_UNSAFE",
            "a supplied file with a hard link count above 1 "
            "is rejected: the WatchPlan file stands in the "
            "same supplied file discipline as every other "
            "input at W-2")
    if info.st_size > PLAN_SIZE_BOUND:
        _fail(
            "WATCHPLAN_SIZE_EXCEEDED",
            "the WatchPlan file stands over the governing "
            "size bound of 1 MiB at W-2: refused at open, "
            "before any round runs")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        descriptor = os.open(str(plan_file), flags)
    except OSError as exc:
        import errno
        if exc.errno in (errno.ELOOP, errno.EMLINK):
            _fail(
                "SUPPLIED_PATH_UNSAFE",
                "a supplied path that is itself a symbolic link "
                "is rejected: the WatchPlan file stands in the "
                "same supplied file discipline as every other "
                "input at W-2, opened with no link following")
        _fail(
            "MALFORMED_CALL",
            "the WatchPlan file stands unreadable: %s" % (exc,))
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            _fail(
                "SUPPLIED_PATH_UNSAFE",
                "the opened handle does not match the pre open "
                "stat: the WatchPlan file stands in the same "
                "supplied file discipline as every other input "
                "at W-2")
        if not stat.S_ISREG(opened.st_mode):
            _fail(
                "SUPPLIED_PATH_UNSAFE",
                "a supplied path that does not name a regular "
                "file is rejected: the WatchPlan file names a "
                "device, a FIFO, or a socket")
        if opened.st_nlink > 1:
            _fail(
                "SUPPLIED_PATH_UNSAFE",
                "a supplied file with a hard link count above 1 "
                "is rejected: the WatchPlan file stands in the "
                "same supplied file discipline as every other "
                "input at W-2")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            raw = handle.read(PLAN_SIZE_BOUND + 1)
    except errors.CitelineError:
        raise
    except OSError as exc:
        _fail(
            "MALFORMED_CALL",
            "the WatchPlan file stands unreadable: %s" % (exc,))
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(raw) > PLAN_SIZE_BOUND:
        _fail(
            "WATCHPLAN_SIZE_EXCEEDED",
            "the WatchPlan file stands over the governing "
            "size bound of 1 MiB at W-2: refused at open, "
            "before any round runs")
    try:
        plan = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs_no_duplicates)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        # A duplicate key stands refused outright, as at
        # the sibling JSON intakes (Step 17 entry
        # S17-R1-074), and a plan nested past the parser
        # depth stands refused in the same value, not as a
        # raw crash (the WatchPlan limb of S17-R1-033).
        _fail(
            "MALFORMED_CALL",
            "the WatchPlan file does not parse: %s" % (exc,))
    if not isinstance(plan, dict):
        _fail("MALFORMED_CALL", "the WatchPlan stands as an object")
    return plan, hashlib.sha256(raw).hexdigest()


def _pairs_no_duplicates(pairs):
    """The plan object pairs hook: duplicate keys refuse.

    Both sibling JSON intakes (journal lines, config)
    refuse duplicate keys outright; the WatchPlan intake
    stands under the same discipline (Step 17 entry
    S17-R1-074), at every object depth of the plan.
    """
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key in WatchPlan: %r" % (key,))
        result[key] = value
    return result


# The plan keys the WatchPlan shape states, and the
# target keys it states: a key outside these sets stands
# named in the round's plan warnings (Step 17 entry
# S17-R1-109), never silently ignored.
_PLAN_KEYS = ("home", "scope", "targets", "form", "audit_date",
              "output", "cadence", "second_round", "second_rounds")
_TARGET_KEYS = ("product", "page_file", "round", "robots_file",
                "evaluated_page_path", "guide", "second_round")


def _plan_warnings(plan, targets):
    """The warnings a round states for its plan's unknown keys."""
    warnings = []
    for key in plan:
        if key not in _PLAN_KEYS:
            warnings.append(
                "unknown WatchPlan key: %s; the key names "
                "nothing the plan shape states and the round "
                "runs without it" % (key,))
    for target in targets or []:
        if not isinstance(target, dict):
            continue
        for key in target:
            if key not in _TARGET_KEYS:
                warnings.append(
                    "unknown WatchPlan target key: %s; the "
                    "key names nothing the target shape "
                    "states and the target runs without it"
                    % (key,))
    # A second_rounds record key naming no product the
    # plan targets stands warned in the open (Step 17
    # round 6 entry S17-R6-045): the dispatch reads the
    # record by product name, so such a key can never be
    # read, and it stands named here instead of standing
    # disregarded in silence at the dispatch.
    second_rounds = plan.get("second_rounds")
    if isinstance(second_rounds, dict):
        target_products = {
            target.get("product") for target in targets or []
            if isinstance(target, dict)}
        if target_products:
            for key in second_rounds:
                if isinstance(key, str) \
                        and key not in target_products:
                    warnings.append(
                        "unknown WatchPlan second_rounds "
                        "key: %s; the key names no product "
                        "the plan targets and the round runs "
                        "without it" % (key,))
    if plan.get("scope") == "estate":
        # On an estate plan the record stands disregarded
        # whole (Step 17 round 7 entry S17-R7-047): the
        # estate dispatch runs on the grounds rounds and
        # reads no second_rounds field at all, picked
        # targets standing empty here by the plan's own
        # form, so every key of the record, and the list
        # form beside it, stands named in the open here
        # instead of standing disregarded in silence, on
        # the same ground the estate targets discipline
        # states at open. Both watch modes stand as
        # options under Captain JP's rulings; this warning
        # rules neither mode away, it names the field the
        # estate round does not read.
        second_round = plan.get("second_round")
        if isinstance(second_round, str) and second_round:
            warnings.append(
                "WatchPlan second_round: %s; the plan "
                "scope stands as estate, the estate round "
                "runs on the grounds rounds and reads no "
                "second_round field, so the label stands "
                "disregarded and the round runs without "
                "it" % (second_round,))
        if isinstance(second_rounds, dict):
            for key in second_rounds:
                if isinstance(key, str):
                    warnings.append(
                        "WatchPlan second_rounds key: %s; "
                        "the plan scope stands as estate, "
                        "the estate round runs on the "
                        "grounds rounds and reads no "
                        "second_rounds record, so the key "
                        "stands disregarded and the round "
                        "runs without it" % (key,))
        elif isinstance(second_rounds, (list, tuple)) \
                and second_rounds:
            warnings.append(
                "WatchPlan second_rounds list: %s; the "
                "plan scope stands as estate, the estate "
                "round runs on the grounds rounds and "
                "reads no second_rounds field, so the "
                "list stands disregarded and the round "
                "runs without it" % (
                    ", ".join(
                        str(item) for item in second_rounds),))
    return warnings


def _validate_plan(plan):
    scope = plan.get("scope")
    if scope not in ("picked", "estate"):
        _fail(
            "MALFORMED_CALL",
            "the WatchPlan scope stands as picked or estate")
    # The WatchPlan shape states each field's type, and a
    # value outside its field's type stands refused at
    # open as MALFORMED_CALL, as the other shape refusals
    # stand (Step 17 entries S17-R1-069 and S17-R1-072):
    # no field stands coerced into a form no one stated.
    form = plan.get("form")
    if form is not None and form not in _FORMS:
        _fail(
            "MALFORMED_CALL",
            "the WatchPlan form stands outside the three "
            "stated values: simple, advanced, agentic")
    if plan.get("home") is None:
        _fail("MALFORMED_CALL", "the WatchPlan names no home")
    if not isinstance(plan.get("home"), str):
        _fail(
            "MALFORMED_CALL",
            "the WatchPlan home stands as a path string")
    audit_date = plan.get("audit_date")
    if audit_date is not None:
        if not isinstance(audit_date, str):
            _fail(
                "MALFORMED_CALL",
                "the WatchPlan audit_date stands as an ISO "
                "date string")
        import datetime
        try:
            datetime.date.fromisoformat(audit_date)
        except ValueError:
            _fail(
                "MALFORMED_CALL",
                "the WatchPlan audit_date is not an ISO "
                "date: %s" % (audit_date,))
    output = plan.get("output")
    if output is not None and not isinstance(output, str):
        _fail(
            "MALFORMED_CALL",
            "the WatchPlan output stands as an output path "
            "string")
    cadence = plan.get("cadence")
    if cadence is not None and not isinstance(cadence, str):
        _fail(
            "MALFORMED_CALL",
            "the WatchPlan cadence stands as a cadence in "
            "words")
    # The second round fields stand under the same shape
    # discipline as every other field the shape states
    # (Step 17 round 5 entry S17-R5-066): the plan second
    # round stands as one round label, and the plan second
    # rounds stand as a list of round labels or as a record
    # of round labels, or of lists of round labels, by
    # product. A form the shape does not state refuses at
    # open as MALFORMED_CALL, never standing disregarded
    # in silence where the round assembly reads the fields
    # on their stated forms alone.
    second_round = plan.get("second_round")
    if second_round is not None and not isinstance(
            second_round, str):
        _fail(
            "MALFORMED_CALL",
            "the WatchPlan second_round stands as a round "
            "label string")
    second_rounds = plan.get("second_rounds")
    if second_rounds is not None:
        def _label_or_labels(value):
            if isinstance(value, str):
                return True
            return isinstance(value, (list, tuple)) and all(
                isinstance(item, str) for item in value)

        if isinstance(second_rounds, dict):
            # The record keys stand judged with its values
            # (Step 17 round 6 entry S17-R6-045): the
            # dispatch reads the record by product name, so
            # a key that stands in no product name form at
            # all, a non string key among its forms, can
            # never be read there and refuses at open in
            # the same shape discipline, never standing
            # disregarded in silence at the dispatch.
            bad = any(
                not isinstance(key, str)
                or not _label_or_labels(value)
                for key, value in second_rounds.items())
        elif isinstance(second_rounds, (list, tuple)):
            bad = any(
                not isinstance(item, str)
                for item in second_rounds)
        else:
            bad = True
        if bad:
            _fail(
                "MALFORMED_CALL",
                "the WatchPlan second_rounds stands as a "
                "list of round labels or a record of round "
                "labels by product")
    targets = plan.get("targets")
    if scope == "estate":
        if targets:
            _fail(
                "WATCH_ESTATE_WITH_TARGETS",
                "a WatchPlan whose scope is estate and which "
                "also lists targets stands refused at open: "
                "its targets stand never silently disregarded")
        return []
    if not targets:
        _fail(
            "WATCH_NO_TARGETS",
            "a picked WatchPlan naming no target stands "
            "refused at open: targets stand required where "
            "scope is picked")
    if not isinstance(targets, list):
        _fail(
            "MALFORMED_CALL",
            "the WatchPlan targets stand as a list of "
            "target objects")
    if len(targets) > TARGET_BOUND:
        _fail(
            "WATCH_TARGET_COUNT_EXCEEDED",
            "a picked WatchPlan naming more than 100 "
            "targets stands refused: the picked scope bound "
            "is 100 targets")
    seen = []
    for target in targets:
        # The target form stands judged before any of its
        # fields stand read (Step 17 round 5 entry
        # S17-R5-065): a target that does not stand as an
        # object refuses at open as MALFORMED_CALL, in the
        # shape discipline this validation states, never as
        # a raw AttributeError from a field reading on a
        # value that holds no fields.
        if not isinstance(target, dict):
            _fail(
                "MALFORMED_CALL",
                "each picked target stands as a target "
                "object")
        # The selector stands judged on its named values,
        # not on its keys (Step 17 round 2 entry
        # S17-R2-073): a selector key holding null names
        # no selector, so a target whose only selector
        # holds null names neither, and a target naming a
        # page file beside a null round names one.
        # An empty string stands as no selector at all,
        # as an absent or null value stands (Step 17
        # round 4 entry S17-R4-057, on the module's own
        # ground at S17-R2-079): a target whose page file
        # or round stands as an empty string names no
        # selector on that limb, and refuses at open
        # where it names none or both.
        page_selector = target.get("page_file")
        round_selector = target.get("round")
        if not isinstance(target, dict) \
                or target.get("product") is None \
                or (page_selector is not None
                    and page_selector != "") == \
                (round_selector is not None
                    and round_selector != ""):
            _fail(
                "MALFORMED_CALL",
                "each picked target names a product and one "
                "of a page file or a named round")
        # The target field types the shape states (Step
        # 17 entries S17-R1-069 and S17-R1-072): a product
        # names a product, and product names are strings
        # everywhere in the product; a non string product
        # stands refused at open, before any round runs,
        # not as a raw crash part way through it.
        if not isinstance(target.get("product"), str) \
                or not target.get("product"):
            _fail(
                "MALFORMED_CALL",
                "each picked target names its product as a "
                "string")
        for field in ("page_file", "round", "robots_file",
                      "evaluated_page_path"):
            value = target.get(field)
            if value is not None and not isinstance(value, str):
                _fail(
                    "MALFORMED_CALL",
                    "the target %s stands as a string" % (field,))
        # The target path strings stand judged before any
        # filesystem call can raise on them (Step 17 round
        # 2 entry S17-R2-078): a page file or robots file
        # string carrying a NUL character or a lone
        # surrogate cannot name a path at all, and refuses
        # at open as MALFORMED_CALL, before the identity
        # reading below runs any path call on it.
        for field in ("page_file", "robots_file",
                      "evaluated_page_path"):
            value = target.get(field)
            if not isinstance(value, str):
                continue
            if "\x00" in value:
                _fail(
                    "MALFORMED_CALL",
                    "the target %s holds a NUL character and "
                    "names no path" % (field,))
            try:
                value.encode("utf-8")
            except UnicodeEncodeError:
                _fail(
                    "MALFORMED_CALL",
                    "the target %s holds a lone surrogate "
                    "and names no path" % (field,))
        guide_flag = target.get("guide")
        if guide_flag is not None and not isinstance(
                guide_flag, bool):
            _fail(
                "MALFORMED_CALL",
                "the target guide flag stands as a boolean")
        # The target second round stands under the plan
        # shape discipline as the plan level fields do
        # (Step 17 round 5 entry S17-R5-066): it stands as
        # one round label, and a form the shape does not
        # state refuses at open instead of falling through
        # the round assembly in silence.
        target_second = target.get("second_round")
        if target_second is not None and not isinstance(
                target_second, str):
            _fail(
                "MALFORMED_CALL",
                "the target second_round stands as a round "
                "label string")
        marker = _target_identity(target)
        if marker in seen:
            _fail(
                "WATCH_DUPLICATE_TARGET",
                "a picked WatchPlan listing the same target "
                "twice stands refused at open")
        seen.append(marker)
    return targets


def _target_identity(target):
    """The identity of one target, on the invocation it orders.

    The duplicate refusal of row U-12 compares the
    invocation each target orders, not the serialisation
    of the whole target object (Step 17 entry
    S17-R1-070): a key the shape gives no effect to, a
    false guide flag, a null field, and a path alias
    spelling of the same file name the same invocation
    as the target without them.
    """
    product = target.get("product")

    def path_form(value):
        # An empty path string orders no file at all, as
        # an absent or null value orders none (Step 17
        # round 2 entry S17-R2-079): the empty robots file
        # spelling stands as the same identity as the
        # absence it is identical to in effect, never as
        # the working directory a realpath reading would
        # map it to.
        if not value:
            return None
        return os.path.realpath(str(value))

    def evaluated_form(value):
        # The evaluated page path stands compared in its
        # normalised form (Step 17 round 2 entry
        # S17-R2-074): a doubled slash spelling, a dot
        # segment spelling, and a trailing slash form of
        # one path name the same invocation to the audit,
        # so they name one identity to this comparison.
        if not value:
            return None
        import posixpath
        form = posixpath.normpath(str(value))
        if form.startswith("/"):
            form = "/" + form.lstrip("/")
        return form

    # The identity branches on the selector value as the
    # open judgement judges it (Step 17 round 5 entry
    # S17-R5-054): an empty page file stands as no page
    # selector, as an absent or null value stands, so a
    # target naming an empty page file beside a named
    # round carries the probe identity of the round it
    # names, not the audit identity of the empty path.
    if target.get("page_file"):
        return (
            "audit", product, path_form(target.get("page_file")),
            path_form(target.get("robots_file")),
            evaluated_form(target.get("evaluated_page_path")),
            bool(target.get("guide")))
    return ("probe", product, target.get("round"))


def _page_age_days(record, audit_date):
    """The age in days of the page one audit used.

    The age stands computed from the dates the audit
    record already carries: the page date the freshness
    limb reads, found in the record sentences in the
    freshness limb's own order (a labelled line first,
    then a date in the opening lines), against the audit
    date the round ran at. Where either date stands
    absent, no age stands.
    """
    if audit_date is None:
        return None
    sentences = record.get("sentences") or []
    text = "\n".join(str(sentence) for sentence in sentences)
    found = None
    try:
        from citeline import checks as checks_module
        for line in text.splitlines():
            match = checks_module._LABELLED_LINE.match(line)
            if not match:
                continue
            value = checks_module._parse_date_in(match.group(2))
            if value is not None:
                found = value
                break
        if found is None:
            for line in text.splitlines()[:20]:
                value = checks_module._parse_date_in(line)
                if value is not None:
                    found = value
                    break
    except Exception:
        return None
    if found is None:
        return None
    try:
        import datetime
        audit_value = datetime.date.fromisoformat(str(audit_date))
    except ValueError:
        return None
    return (audit_value - found).days


def _audit_entry(home, plan, product, target):
    audit_date = plan.get("audit_date")
    form = plan.get("form") or "simple"
    kwargs = {
        "home": str(home),
        "page_file": str(target["page_file"]),
        "audit_date": audit_date,
        "product": product,
    }
    if target.get("robots_file"):
        kwargs["robots_file"] = str(target["robots_file"])
    if target.get("evaluated_page_path"):
        kwargs["evaluated_page_path"] = target[
            "evaluated_page_path"]
    try:
        record = service.audit(**kwargs)
    except Exception as exc:
        entry = {"product": product, "target_kind": "audit"}
        entry.update(_failure_fields(exc))
        return entry
    run_id = record.get("run_id")
    rows = [{
        "kind": "audit",
        "outcome": "completed",
        "record_identity": run_id,
    }]
    entry = {
        "product": product,
        "target_kind": "audit",
        "outcome": "completed",
        "record_identity": run_id,
    }
    entry["page_age_days"] = _page_age_days(record, audit_date)
    if target.get("guide"):
        try:
            draft = service.guide(
                home=str(home), run_id=run_id,
                audit_date=audit_date)
            rows.append({
                "kind": "guide",
                "outcome": "completed",
                "record_identity": draft.get("guide_id"),
                "source_run_id": run_id,
            })
        except Exception as exc:
            fields = _failure_fields(exc)
            row = {
                "kind": "guide",
                "outcome": fields["outcome"],
                "recorded_error": fields["recorded_error"],
                "source_run_id": run_id,
            }
            if fields.get("contention"):
                row["contention"] = True
                row["stored"] = False
            rows.append(row)
            entry["outcome"] = "failed"
            entry["recorded_error"] = fields["recorded_error"]
            if fields.get("contention"):
                entry["contention"] = True
                entry["stored"] = False
    entry["channel_rows"] = rows
    return entry


def _probe_entry(home, plan, product, round_label, scope_rounds):
    audit_date = plan.get("audit_date")
    form = plan.get("form") or "simple"
    try:
        service.probe_report(
            home=str(home), product=product, round=round_label,
            form=form, audit_date=audit_date)
    except Exception as exc:
        entry = {"product": product, "target_kind": "probe"}
        entry.update(_failure_fields(exc))
        return entry, 0
    rows = [{
        "kind": "probe",
        "outcome": "completed",
        "record_identity": round_label,
    }]
    entry = {
        "product": product,
        "target_kind": "probe",
        "outcome": "completed",
        "record_identity": round_label,
        "channel_rows": rows,
    }
    no_pair = 0
    qualifying = list(scope_rounds)
    if qualifying:
        earliest = qualifying[0]
        if earliest == round_label:
            no_pair = 1
            entry["trend_pair"] = None
        else:
            try:
                service.probe_trend(
                    home=str(home), product=product,
                    round_a=earliest, round_b=round_label,
                    form=form, audit_date=audit_date)
                entry["trend_pair"] = [earliest, round_label]
                rows.append({
                    "kind": "trend",
                    "outcome": "completed",
                    "record_identity": round_label,
                })
            except Exception as exc:
                entry["trend_error"] = service.recorded_error(exc)
                rows.append({
                    "kind": "trend",
                    "outcome": "failed",
                    "recorded_error": service.recorded_error(exc),
                })
    else:
        entry["trend_pair"] = None
    return entry, no_pair


def _standing_product_page_snapshot_count(home, products):
    """The standing product page snapshots of one home.

    The count stands on the journal facts the round already
    stands on, on the plan Section 5.1 WatchRun definition:
    one per snapshot identity whose most recent
    snapshot_registered record stands as a product page
    (is_product_page true) and carries the PageSnapshot
    supplied_path, for a product standing in the registry
    at the round start. An audit entry of the round, and in
    particular a skipped audit entry, is not a snapshot and
    counts as none.
    """
    product_ids = {
        record.get("product_id") for record in products
        if isinstance(record, dict) and record.get("product_id")}
    try:
        from citeline import journal
        # The coverage count folds with corrections, as
        # the reporting readers do (Step 17 round 3 entry
        # S17-R3-064): a registration a correction
        # superseded to not a product page counts as no
        # standing product page snapshot here, as it
        # counts nowhere else.
        entries = journal.fold(str(home), apply_corrections=True)
    except Exception:
        return 0, set()
    latest = {}
    order = []
    for entry in entries or []:
        if isinstance(entry, dict):
            kind = entry.get("entry_kind")
            payload = entry.get("payload") or {}
        else:
            kind = getattr(entry, "entry_kind", None)
            payload = getattr(entry, "payload", {}) or {}
        if kind != "snapshot_registered" \
                or not isinstance(payload, dict):
            continue
        snapshot_id = payload.get("snapshot_id")
        if not snapshot_id:
            continue
        if not isinstance(snapshot_id, str):
            # The fold keys its dict by the identity, so the
            # identity stands judged against the stored field
            # discipline before the keying: an identity in a
            # form that is not a string, an unhashable form
            # among them, stands refused in the recorded
            # vocabulary instead of crashing the fold raw
            # (Step 17 round 5 entry S17-R5-064, the watch
            # limb of the registry fold cure).
            _fail("VALIDATION_FAILED",
                  "the stored snapshot record carries "
                  "snapshot_id in a form its readers cannot "
                  "use: %r" % (snapshot_id,))
        supplied_path = payload.get("supplied_path")
        if supplied_path is not None and not isinstance(
                supplied_path, str):
            # The path this count consumes stands judged
            # against the stored field discipline before
            # it stands read, as the identity above it
            # stands (Step 17 round 5 entry S17-R5-052):
            # a swapped path refuses in the recorded
            # vocabulary instead of governing the count
            # through its string form.
            _fail("VALIDATION_FAILED",
                  "the stored snapshot record carries "
                  "supplied_path in a form its readers cannot "
                  "use: %r" % (supplied_path,))
        product_id = payload.get("product_id")
        if product_id is not None and not isinstance(
                product_id, str):
            # The product identity this count tests for
            # membership stands judged before the test, as
            # the identities above it stand (Step 17 round
            # 6 entry S17-R6-049): an identity in a form
            # that is not a string, an unhashable form
            # among them, refuses in the recorded
            # vocabulary instead of raising raw at the
            # membership test below.
            _fail("VALIDATION_FAILED",
                  "the stored snapshot record carries "
                  "product_id in a form its readers cannot "
                  "use: %r" % (product_id,))
        if snapshot_id not in latest:
            order.append(snapshot_id)
        latest[snapshot_id] = payload
    count = 0
    paths = set()
    for snapshot_id in order:
        payload = latest[snapshot_id]
        if payload.get("is_product_page") is True \
                and payload.get("supplied_path") \
                and payload.get("product_id") in product_ids:
            count += 1
            paths.add(os.path.realpath(
                str(payload.get("supplied_path"))))
    return count, paths


def _cadence_interval_days(cadence):
    """The interval in days a stated cadence names, or None.

    The cadence field states the operator cadence in words.
    The words this reading accepts are the plain period
    words (daily, weekly, fortnightly, monthly, quarterly,
    yearly) and an every N days, weeks, months, or years
    form. A cadence in other words states no interval this
    product can read, and the forward count then stands in
    its absence form.
    """
    text = str(cadence).strip().casefold()
    words = {
        "daily": 1, "weekly": 7, "fortnightly": 14,
        "monthly": 30, "quarterly": 91, "yearly": 365,
    }
    if text in words:
        return words[text]
    import re
    # The form stands exactly as the docstring states
    # (Step 17 round 3 entry S17-R3-059): the word every
    # stands required, the digits stand as Latin digits,
    # and a zero count names no interval, because a zero
    # interval is no cadence and its forward count would
    # stand as a computed figure where the absence form
    # belongs. The separator stands as the ordinary
    # space the stated form writes, and no other
    # whitespace form stands in the set (Step 17 round
    # 4 entry S17-R4-058): a Unicode whitespace
    # separator names no stated form, as the annually
    # word names none. The stated form writes one
    # ordinary space at each separator position, so a
    # run of ordinary spaces at a position stands as
    # no stated form either (Step 17 round 5 entry
    # S17-R5-055).
    match = re.fullmatch(
        r"every ([0-9]+) (day|days|week|weeks|month|months"
        r"|year|years)", text)
    if match:
        # The conversion stands bounded (Step 17 round 2
        # entry S17-R2-093): a digit run past six digits
        # names no cadence this product reads, and stands
        # as no interval, instead of raising at the integer
        # conversion limit after the round's targets have
        # stored their records.
        digits = match.group(1)
        if len(digits) > 6:
            return None
        if int(digits) == 0:
            return None
        unit_days = {"day": 1, "days": 1, "week": 7, "weeks": 7,
                     "month": 30, "months": 30, "year": 365,
                     "years": 365}
        return int(digits) * unit_days[match.group(2)]
    return None


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


def _bounds():
    return {
        "establishes": [
            "This artefact records one entry per target the "
            "round attempted, in run order, with its outcome.",
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


def run_watch(*, plan_file, form=None):
    """Run one watch round over the plan the file states.

    The round stands as a batch of independent invocations
    under contract CW: the plan stands opened and refused
    on its bounds before any round runs, the home journal
    stands verified before any target runs, targets run in
    plan order in picked scope and in registry order in
    estate scope, and every target attempted stands
    recorded once in the summary the round returns.
    """
    plan, plan_sha256 = _open_plan(plan_file)
    targets = _validate_plan(plan)
    if form is not None:
        if form not in _FORMS:
            _fail(
                "MALFORMED_CALL",
                "the watch form stands outside the three "
                "stated values: simple, advanced, agentic")
        # A form named on the invocation governs the whole
        # call, the written artefact beside the printed
        # rendering, as the module head states.
        plan = dict(plan)
        plan["form"] = form
    home = str(plan["home"])
    round_started = _clock()
    scope = plan["scope"]
    audit_date = plan.get("audit_date")
    form = plan.get("form") or "simple"
    output = plan.get("output")
    if output:
        # An occupied output path refuses before any round
        # work runs, so no round is spent producing no
        # artefact: the refusal the write step would raise
        # at the end stands raised here, at the start.
        try:
            occupied = os.path.lexists(str(output))
        except (ValueError, UnicodeError, OSError):
            occupied = False
        if occupied:
            _fail(
                "DESTINATION_EXISTS",
                "the WatchRun output path stands occupied and "
                "stands never replaced: %s" % output)
    verification = service.verify(home=home)
    if not verification.get("passed"):
        _fail(
            "JOURNAL_VERIFY_FAILED",
            "the home journal fails verify; the whole round "
            "stands failed before any target runs, and no "
            "WatchRun artefact stands produced")
    products = service.list_products(home=home)
    standing_snapshot_count, standing_snapshot_paths = \
        _standing_product_page_snapshot_count(home, products)
    audited_snapshot_paths = set()
    entries = []
    trend_no_pair_count = 0
    # The append cost of one target, priced from what the
    # round will actually append, failure records included:
    # an audit appends a snapshot_registered entry and an
    # audit_record entry on success and one failure record
    # on failure, so its price stands at 2 either way; a
    # guide call appends a guide_record entry on success and
    # one failure record on failure, so its price stands at
    # 1 either way; a probe target appends nothing on success
    # and one failure record on failure, so its price stands
    # at 1. The projection is the most a round can append, so
    # a round reported as fitting cannot end part refused at
    # the cap.
    def target_cost(target):
        # The cost branches on the selector value as the
        # open judgement judges it, as the identity and
        # the dispatch below do (Step 17 round 5 entry
        # S17-R5-054): an empty page file names no page
        # selector and costs as the probe target it is.
        if target.get("page_file"):
            return 2 + (1 if target.get("guide") else 0)
        return 1

    estate_grounds_by_product = {}
    if scope == "estate":
        for product_record in products:
            name = product_record.get("name")
            estate_grounds_by_product[name] = \
                service.estate_grounds(home=home, product=name)
    if scope == "picked":
        attempted = list(targets)
        projected_entries = sum(
            target_cost(target) for target in targets)
    else:
        attempted = []
        projected_entries = 0
        for product_record in products:
            name = product_record.get("name")
            grounds = estate_grounds_by_product[name]
            if grounds.get("page_path") is not None:
                attempted.append({"page_file": grounds["page_path"]})
                projected_entries += 2
            for _label in grounds.get("rounds") or []:
                attempted.append({"round": _label})
                projected_entries += 1
    total_targets = len(attempted)
    status_record = service.status(home=home)
    outlook = status_record.get("capacity_outlook") or {}
    entries_remaining = outlook.get("entries_remaining") or 0
    if projected_entries > entries_remaining:
        projection_words = "meet refusal part way"
    elif projected_entries > 0 \
            and entries_remaining - projected_entries \
            < projected_entries:
        projection_words = "approach the cap"
    else:
        projection_words = "fit"
    projection = {
        "entries_remaining": outlook.get("entries_remaining"),
        "bytes_remaining": outlook.get("bytes_remaining"),
        "target_count": total_targets,
        "projected_entries": projected_entries,
        "projection": projection_words,
    }
    if scope == "picked":
        scope_rounds_by_product = {}
        for target in targets:
            if target.get("round"):
                rounds = scope_rounds_by_product.setdefault(
                    target["product"], [])
                if target["round"] not in rounds:
                    rounds.append(target["round"])
            second = target.get("second_round")
            if second:
                rounds = scope_rounds_by_product.setdefault(
                    target["product"], [])
                if second not in rounds:
                    rounds.append(second)
        plan_second = plan.get("second_round")
        plan_seconds = plan.get("second_rounds")
        for target in targets:
            _check_round_backstop(home, round_started)
            product = target["product"]
            # The dispatch branches on the selector value
            # as the open judgement judges it (Step 17
            # round 5 entry S17-R5-054): a target whose
            # page file stands empty beside a named round
            # runs as the probe target it opened as.
            if target.get("page_file"):
                entry = _audit_entry(home, plan, product, target)
                entries.append(entry)
                if entry.get("outcome") == "completed":
                    audited_snapshot_paths.add(os.path.realpath(
                        str(target["page_file"])))
            else:
                grounds = service.estate_grounds(
                    home=home, product=product)
                scope_labels = list(
                    scope_rounds_by_product.get(product) or [])
                extra = []
                if isinstance(plan_seconds, dict):
                    named = plan_seconds.get(product)
                    if isinstance(named, (list, tuple)):
                        extra.extend(named)
                    elif named:
                        extra.append(named)
                elif isinstance(plan_seconds, (list, tuple)):
                    extra.extend(plan_seconds)
                if plan_second:
                    extra.append(plan_second)
                for label in extra:
                    if label not in scope_labels:
                        scope_labels.append(label)
                scope_rounds = [
                    label for label in grounds.get("rounds") or []
                    if label in scope_labels]
                entry, no_pair = _probe_entry(
                    home, plan, product, target["round"],
                    scope_rounds)
                entries.append(entry)
                trend_no_pair_count += no_pair
    else:
        for product_record in products:
            _check_round_backstop(home, round_started)
            name = product_record.get("name")
            grounds = estate_grounds_by_product[name]
            page_path = grounds.get("page_path")
            rounds = grounds.get("rounds") or []
            if page_path is None:
                entries.append({
                    "product": name,
                    "target_kind": "audit",
                    "outcome": "skipped",
                    "skip_reason": "no page on file",
                })
            else:
                entry = _audit_entry(
                    home, plan, name, {"page_file": page_path})
                entries.append(entry)
                if entry.get("outcome") == "completed":
                    audited_snapshot_paths.add(
                        os.path.realpath(str(page_path)))
            if not rounds:
                entries.append({
                    "product": name,
                    "target_kind": "probe",
                    "outcome": "skipped",
                    "skip_reason": "no round with answers",
                })
            else:
                for label in rounds:
                    entry, no_pair = _probe_entry(
                        home, plan, name, label, rounds)
                    entries.append(entry)
                    trend_no_pair_count += no_pair
    outcome_counts = {}
    channel_counts = {}
    for entry in entries:
        outcome_counts[entry["outcome"]] = outcome_counts.get(
            entry["outcome"], 0) + 1
        for row in entry.get("channel_rows") or []:
            channel_counts[row["outcome"]] = channel_counts.get(
                row["outcome"], 0) + 1
    for value in ("completed", "failed", "skipped", "stopped"):
        outcome_counts.setdefault(value, 0)
    # The coverage assembly builds every count from the
    # population its figure names (Step 17 entry
    # S17-R1-071): products with an audit target counts
    # registered products only, over the registered
    # denominator, and snapshots audited counts the
    # standing product page snapshots the round audited,
    # over that same standing population, never the fresh
    # snapshots the round itself created.
    registered_names = {
        record.get("name") for record in products
        if isinstance(record, dict)}
    audited_products = {
        entry["product"] for entry in entries
        if entry["target_kind"] == "audit"
        and entry["outcome"] != "skipped"
        and entry["product"] in registered_names}
    only_skips = []
    for product_record in products:
        name = product_record.get("name")
        own = [e for e in entries if e["product"] == name]
        if own and all(e["outcome"] == "skipped" for e in own):
            only_skips.append(name)
    coverage = {
        "registered_products": {
            "count": len(products), "denominator": len(products)},
        "products_with_audit_target": {
            "count": len(audited_products),
            "denominator": len(products)},
        "product_page_snapshots": {
            "count": standing_snapshot_count,
            "denominator": len(products)},
        "snapshots_audited": {
            "count": len(
                standing_snapshot_paths & audited_snapshot_paths),
            "denominator": standing_snapshot_count},
        "products_with_only_skips": {
            "count": len(only_skips), "denominator": len(products)},
    }
    cadence = plan.get("cadence")
    page_ages = [
        {"product": entry["product"],
         "page_age_days": entry.get("page_age_days")}
        for entry in entries
        if entry["target_kind"] == "audit"
        and entry["outcome"] == "completed"]
    freshness = {
        "cadence": cadence,
        "page_ages": page_ages,
        "forward_count": {
            "recorded": False, "state": "not_recorded"},
    }
    if cadence:
        interval = _cadence_interval_days(cadence)
        if interval is not None:
            freshness["forward_count"] = sum(
                1 for item in page_ages
                if item["page_age_days"] is not None
                and item["page_age_days"] <= 90
                and item["page_age_days"] + interval > 90)
    result = {
        "home_path": home,
        "scope": scope,
        "plan_file_sha256": plan_sha256,
        "audit_date": audit_date,
        "form": form,
        "entries": entries,
        "outcome_counts": outcome_counts,
        "channel_outcome_counts": channel_counts,
        "trend_no_pair_count": trend_no_pair_count,
        "coverage_statement": coverage,
        "plan_warnings": _plan_warnings(plan, targets),
        "freshness_view": freshness,
        "capacity_projection": projection,
        "honesty_sentence": _honesty_sentence(),
        "bounds": _bounds(),
    }
    _check_round_backstop(home, round_started)
    output = plan.get("output")
    if output:
        _write_output(result, output, form)
    return result


def _write_output(result, output_path, form):
    """Write the WatchRun artefact under the no replace rule.

    Where the destination stands, the write alone fails on
    row X-9 after every target completed: the stored
    records stand, no artefact for this round stands
    produced, and the failure stands as caller response
    only, the watch invocation writing no journal entry of
    its own.
    """
    # The output path string stands judged before any
    # filesystem call can raise on it (Step 17 round 2
    # entry S17-R2-077): a string carrying a NUL character
    # or a lone surrogate can name no destination, and the
    # write step fails on it in its stated governed form
    # alone, row X-9, DESTINATION_EXISTS, after every
    # target completed, as every other write failure of
    # this step does.
    if isinstance(output_path, str) and "\x00" in output_path:
        _fail(
            "DESTINATION_EXISTS",
            "the WatchRun output path names no destination "
            "a filesystem call can state: %s"
            % (output_path.encode(
                "utf-8", "backslashreplace").decode("utf-8"),))
    if isinstance(output_path, str):
        try:
            output_path.encode("utf-8")
        except UnicodeEncodeError:
            _fail(
                "DESTINATION_EXISTS",
                "the WatchRun output path names no "
                "destination a filesystem call can state")
    try:
        occupied = os.path.lexists(output_path)
    except (ValueError, UnicodeError, OSError):
        _fail(
            "DESTINATION_EXISTS",
            "the WatchRun output path names no destination "
            "a filesystem call can state")
    if occupied:
        _fail(
            "DESTINATION_EXISTS",
            "the WatchRun output path stands occupied and "
            "stands never replaced: %s" % output_path)
    try:
        from citeline import reporting
        rendered = reporting.render(result, form=form)
    except Exception:
        rendered = result
    if not isinstance(rendered, str):
        rendered = json.dumps(rendered, sort_keys=True, indent=2)
    try:
        with open(output_path, "x", encoding="utf-8") as handle:
            handle.write(rendered)
            if not rendered.endswith("\n"):
                handle.write("\n")
    except FileExistsError:
        _fail(
            "DESTINATION_EXISTS",
            "the WatchRun output path stands occupied and "
            "stands never replaced: %s" % output_path)
    except (OSError, ValueError, UnicodeError) as exc:
        _fail(
            "DESTINATION_EXISTS",
            "the WatchRun artefact write failed: %s" % (exc,))


__all__ = [
    "CONTENTION_CLASS",
    "CONTENTION_OUTCOME",
    "CONTENTION_ROUND_EXIT_CODE",
    "CONTENTION_ROW",
    "CONTENTION_TARGET_EXIT_CODE",
    "CONTENTION_TOKEN",
    "PLAN_SIZE_BOUND",
    "TARGET_BOUND",
    "WatchError",
    "run_watch",
]
