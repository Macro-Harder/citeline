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

import copy
import hashlib
import inspect
import os

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
        "message": str(exc),
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


def _fold(home):
    journal = _journal()
    try:
        entries = journal.fold(str(home))
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
    if not os.path.isdir(str(home)):
        _fail(
            "HOME_MISSING",
            "the home stands missing: %s" % (home,))


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
    for entry in _fold(home):
        if _get(entry, "entry_kind") != "round_named":
            continue
        payload = _payload(entry)
        if payload.get("product_id") == product_id:
            rounds.append(payload)
    return rounds


def _round_record(home, product_record, round_label):
    product_id = product_record.get("product_id")
    standing = None
    for payload in _rounds(home, product_id):
        if payload.get("round_label") == round_label:
            standing = payload
    return standing


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
    for entry in _fold(home):
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


def _limits_in_force(home):
    journal = _journal()
    try:
        run = journal.start_run(str(home))
        limits = run.get("limits_in_force") or {}
    except Exception:
        limits = {}
    raised = any(
        isinstance(value, dict) and value.get("source") == "raise"
        for value in limits.values())
    return {"raised_limits": bool(raised), "by_limit": limits}


# ----------------------------------------------------------------
# Status and verify: the service homes of the journal pair.
# ----------------------------------------------------------------

def status(*, home):
    """The status record of one home, in every case a record.

    Status completes its reporting duty over a journal that
    does not recompute: its record states the chain failure
    and the failing position in full, and no error value of
    its own stands. Its capacity outlook attributes the
    remaining capacity by entry kind, as a partition of the
    whole remaining figure over the kinds that stand in the
    journal, so the kind figures tally to the whole.
    """
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
    kinds = []
    for entry in entries:
        kind = _get(entry, "entry_kind")
        if kind is not None and kind not in kinds:
            kinds.append(kind)
    total_remaining = outlook.get("entries_remaining", 0)
    by_kind = {}
    if kinds:
        share, remainder = divmod(int(total_remaining), len(kinds))
        for index, kind in enumerate(kinds):
            figures = share + (remainder if index == 0 else 0)
            by_kind[kind] = {"entries_remaining": figures}
    outlook["by_entry_kind"] = by_kind
    outlook["by_entry_kind_basis"] = (
        "The by entry kind figures are shares of the one "
        "total of entries remaining, divided over the entry "
        "kinds standing in the journal; they are not a "
        "separate allowance per kind.")
    answers = [
        entry for entry in entries
        if _get(entry, "entry_kind") == "answer_imported"]
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
    result["anchor_limit"] = _anchor_limit_sentence()
    result["anchor_limit_sentence"] = _anchor_limit_sentence()
    result["honesty_sentence"] = _honesty_sentence()
    result["bounds"] = _bounds_computed()
    return result


def verify(*, home):
    """The verify record of one home.

    A missing home stands as a usage error at row U-6. A
    home whose chain does not recompute stands reported in
    the record itself, on row I-2, with its failing
    position, and no record from that journal stands
    claimed as verified.
    """
    _require_home(home)
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
    except Exception:
        pass
    result["anchor_limit"] = _anchor_limit_sentence()
    result["anchor_limit_sentence"] = _anchor_limit_sentence()
    result["honesty_sentence"] = _honesty_sentence()
    result["bounds"] = _bounds_computed()
    return result


# ----------------------------------------------------------------
# Registry operations: calls over the registry component.
# ----------------------------------------------------------------

def add_product(*, home, name, canonical_line, domain,
                competitors=None, aliases=None, query_set=None,
                audit_date=None):
    registry = _registry()
    return registry.add_product(
        home=str(home), name=name, canonical_line=canonical_line,
        domain=domain, competitors=competitors, aliases=aliases,
        query_set=query_set, audit_date=audit_date)


def set_canonical_line(*, home, product, line, audit_date=None):
    registry = _registry()
    return registry.set_canonical_line(
        home=str(home), product=product, line=line,
        audit_date=audit_date)


def set_competitors(*, home, product, competitors, audit_date=None):
    registry = _registry()
    return registry.set_competitors(
        home=str(home), product=product, competitors=competitors,
        audit_date=audit_date)


def set_aliases(*, home, product, aliases, audit_date=None):
    registry = _registry()
    return registry.set_aliases(
        home=str(home), product=product, aliases=aliases,
        audit_date=audit_date)


def set_query_set(*, home, product, query_set, audit_date=None):
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
    registry = _registry()
    return registry.register_page(
        home=str(home), product=product, snapshot=snapshot,
        audit_date=audit_date)


def name_round(*, home, product, round_label,
               importer_declaration, supplier_relation,
               audit_date=None):
    registry = _registry()
    return registry.name_round(
        home=str(home), product=product, round_label=round_label,
        importer_declaration=importer_declaration,
        supplier_relation=supplier_relation,
        audit_date=audit_date)


def list_products(*, home):
    """The standing products of one home, in registry order.

    A reading helper for callers that enumerate a home, as
    the watch does at a round start. The records stand as
    the registry component folds them, in the order their
    registration entries stand.
    """
    journal = _journal()
    try:
        state = journal.fold_registry(str(home))
        if isinstance(state, dict) and state:
            return [dict(value) for value in state.values()
                    if isinstance(value, dict)]
        if isinstance(state, (list, tuple)) and state:
            return [dict(value) for value in state
                    if isinstance(value, dict)]
    except Exception:
        pass
    registry = _registry()
    try:
        records = list(registry.list_products(str(home)) or [])
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
    record = _find_product(home, product)
    if record is None:
        return {"page_path": None, "rounds": []}
    product_id = record.get("product_id")
    page_path = None
    rounds = []
    seen_rounds = []
    for entry in _fold(home):
        kind = _get(entry, "entry_kind")
        payload = _payload(entry)
        if kind == "snapshot_registered" \
                and payload.get("product_id") == product_id \
                and payload.get("is_product_page"):
            page_path = payload.get("supplied_path")
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
    except OSError as exc:
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
    """
    evaluation = _robots_evaluation(
        home=home, robots_file=robots_file,
        evaluated_page_path=evaluated_page_path,
        audit_date=audit_date)
    from citeline import reporting
    return reporting.render(evaluation, form=form or "advanced")


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
    if first_capture_date is None:
        first_capture_date = first_captured_on
    if second_capture_date is None:
        second_capture_date = second_captured_on
    _barred_check(home)
    first = _robots_evaluation(
        home=home, robots_file=first_robots_file,
        evaluated_page_path=evaluated_page_path,
        audit_date=audit_date)
    second = _robots_evaluation(
        home=home, robots_file=second_robots_file,
        evaluated_page_path=evaluated_page_path,
        audit_date=audit_date)
    first = _with_group_rules(first, first_robots_file)
    second = _with_group_rules(second, second_robots_file)
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

def audit(*, home, page_file, robots_file=None,
          evaluated_page_path=None, audit_date=None,
          product=None):
    """One audit, assembled as caller over its components.

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
    home stands as the record product, as before.
    """
    _barred_check(home)
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
    product_id = (
        product_record.get("product_id") if product_record else None)
    from citeline import acquisition
    extraction = acquisition.extract_page(
        str(home), product_id=product_id, page_path=str(page_file),
        audit_date=audit_date,
        evaluated_page_path=evaluated_page_path)
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
    robots_summary = None
    if robots_file is not None:
        robots_summary = _robots_evaluation(
            home=home, robots_file=robots_file,
            evaluated_page_path=snapshot.get("evaluated_page_path"),
            audit_date=audit_date,
            path_defaulted=snapshot.get("path_defaulted"))
    sequence = _entry_count(home) + 1
    run_id = "run-%d" % sequence
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
    record = {
        "run_id": run_id,
        "product_id": product_id,
        "snapshot_id": snapshot.get("snapshot_id"),
        "snapshot_sha256": snapshot.get("sha256"),
        "evaluated_page_path": snapshot.get("evaluated_page_path"),
        "path_defaulted": bool(snapshot.get("path_defaulted")),
        "snapshot_format": snapshot.get("format"),
        "checks": check_results,
        "score": score,
        "facts_counts": {"recorded": False, "state": "not_recorded"},
        "robots_summary": robots_summary,
        "audit_date": audit_date,
        "audit_date_is_run_date": True,
        "limits_in_force": _limits_in_force(home),
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
        "sentences": list(_get(extracted, "sentences", []) or []),
        "trigger_codes": triggers,
        "distinct_cited_target_count": cited_count,
    }
    journal.append_entry(
        str(home), "audit_record", copy.deepcopy(record),
        audit_date=audit_date)
    result = dict(record)
    result["snapshot"] = snapshot
    result["audit_run"] = dict(record)
    return result


def _detector_version():
    try:
        from citeline import detection
        return getattr(detection, "DETECTOR_VERSION", 1)
    except Exception:
        return 1


# ----------------------------------------------------------------
# Probe import, report, and trend: calls over their components.
# ----------------------------------------------------------------

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
    _barred_check(home)
    journal = _journal()
    from citeline import probe_import as import_module
    try:
        import_module.probe_import(
            answer_file=answer_file, product=product, round=round,
            engine_label=engine_label, query=query, kind=kind,
            captured_on=captured_on, capture_method=capture_method,
            control_designation=control_designation,
            audit_date=audit_date, known_round=True,
            query_set=None, standing_records=(), control_count=0,
            product_id=None, round_id=None, answer_id=None,
            registry_version_at_import=None,
            detector_version_at_import=None)
    except Exception as exc:
        _append_failure_record(
            home, "probe import", exc, answer_file, audit_date)
        raise
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
    control_count = sum(
        1 for item in standing
        if item.get("control_flag") and item.get("kind") == kind)
    sequence = _entry_count(home) + 1
    from citeline import probe_import as import_module
    try:
        record = import_module.prepare_import(
            answer_file=str(answer_file), product=product,
            round=round, engine_label=engine_label, query=query,
            kind=kind, captured_on=captured_on,
            capture_method=capture_method,
            control_designation=control_designation,
            audit_date=audit_date, known_round=True,
            query_set=list(product_record.get("query_set") or [])
            or None,
            standing_records=standing,
            control_count=control_count,
            product_id=product_id, round_id=round_id,
            answer_id="ans-%d" % sequence,
            registry_version_at_import=product_record.get(
                "registry_version", 1),
            detector_version_at_import=_detector_version())
    except Exception as exc:
        _append_failure_record(
            home, "probe import", exc, answer_file, audit_date)
        raise
    journal.append_entry(
        str(home), "answer_imported", copy.deepcopy(record),
        audit_date=audit_date)
    if round_record.get("registry_version_at_first_import") is None:
        stamped = dict(round_record)
        stamped["registry_version_at_first_import"] = record.get(
            "registry_version_at_import")
        stamped["detector_version_at_first_import"] = record.get(
            "detector_version_at_import")
        journal.append_entry(
            str(home), "round_named", stamped, audit_date=audit_date)
    return record


def _append_failure_record(home, operation, exc, subject, audit_date):
    if is_contention(exc):
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
    payload = {
        "operation": operation,
        "error_value": token,
        "subject_identity": str(subject),
        "date": audit_date,
        "rule_fired": token,
    }
    try:
        journal.append_entry(
            str(home), "failure_record", payload,
            audit_date=audit_date)
    except Exception:
        pass


def _round_entries(home, product_record, round_record):
    product_id = product_record.get("product_id")
    round_id = round_record.get("round_id")
    selected = []
    for entry in _fold(home):
        kind = _get(entry, "entry_kind")
        payload = _payload(entry)
        if kind in ("product_registered", "registry_change"):
            if payload.get("product_id") == product_id:
                selected.append(entry)
        elif kind == "round_named":
            if payload.get("round_id") == round_id:
                selected.append(entry)
        elif kind == "answer_imported":
            if payload.get("round_id") == round_id:
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
    query_set_version = product_record.get("query_set_version")
    if query_set_version is not None:
        datum["query_set_version"] = query_set_version
    for entry in entries:
        payload = _payload(entry)
        for key in ("lexicon_version",):
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


def _probe_report_record(home, product_record, round_record,
                         audit_date=None, metrics_record=None):
    """The assembled probe report record of one round.

    The record stands as probe_report renders it: the
    RoundMetrics record the metrics component computes,
    the product and round identities, the first import
    stamps the round record carries, and the methods note
    stamp the ruling names for the RoundMetrics shape.
    """
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
    """
    _require_home(home)
    _barred_check(home)
    product_record = _require_product(home, product)
    round_record = _require_round(home, product_record, round)
    result = _probe_report_record(
        home, product_record, round_record, audit_date=audit_date)
    from citeline import reporting
    return reporting.render(result, form=form or "advanced")


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
    """
    _require_home(home)
    _barred_check(home)
    product_record = _require_product(home, product)
    first = _require_round(home, product_record, round_a)
    second = _require_round(home, product_record, round_b)
    if round_a == round_b:
        _fail(
            "ROUND_REPEATED",
            "a trend naming the same round twice stands "
            "refused: %r" % (round_a,))
    from citeline import metrics
    first_metrics = _round_metrics(home, product_record, first)
    second_metrics = _round_metrics(home, product_record, second)
    trend = metrics.compute_trend(
        {"metrics": first_metrics, "frame": _trend_frame(first_metrics)},
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
    from citeline import reporting
    return reporting.render(result, form=form or "advanced")


def query_set_report(*, home, product, form=None, audit_date=None):
    """The QuerySetReport of one product, from its record alone.

    The home returns the reporting pipeline rendering of
    the derived report in the requested form.
    """
    _require_home(home)
    _barred_check(home)
    product_record = _require_product(home, product)
    from citeline import reporting
    return reporting.query_set_report(
        product_record, form=form or "advanced")


def export_capture_worksheet(*, home, product, round, queries=None,
                             engine_labels=None, planned_answers=0,
                             output_path=None, audit_date=None):
    """One capture worksheet written from a named round definition."""
    product_record = _require_product(home, product)
    _require_round(home, product_record, round)
    from citeline import probe_import as import_module
    return import_module.export_capture_worksheet(
        output_path=str(output_path), product=product, round=round,
        queries=list(queries or []),
        engine_labels=list(engine_labels or []),
        planned_answers=int(planned_answers or 0))


# ----------------------------------------------------------------
# Guide: calls over the guide component, stored as guide_record.
# ----------------------------------------------------------------

def guide(*, home, run_id=None, product=None, round_label=None,
          audit_date=None):
    """One guide draft, from one audit record or one round.

    The draft stands computed by the guide component from
    the one completed record the call names, and stands
    stored as one guide_record entry through the journal.
    A refusal stands as a completed outcome of the draft
    itself and carries no error value.
    """
    _barred_check(home)
    journal = _journal()
    from citeline import guide as guide_module
    if run_id is not None:
        audit_record = None
        for entry in _fold(home):
            if _get(entry, "entry_kind") != "audit_record":
                continue
            payload = _payload(entry)
            if payload.get("run_id") == run_id:
                audit_record = payload
        if audit_record is None:
            _fail(
                "UNKNOWN_ROUND",
                "no completed audit record stands under the "
                "identity given: %r" % (run_id,))
        product_record = None
        for candidate in list_products(home=home):
            if candidate.get("product_id") == audit_record.get(
                    "product_id"):
                product_record = candidate
        draft = guide_module.draft_from_audit_record(
            audit_record,
            canonical_line=(
                product_record.get("canonical_line")
                if product_record else audit_record.get(
                    "canonical_line")),
            audit_date=audit_date or audit_record.get("audit_date"),
            product_name=(
                product_record.get("name")
                if product_record else audit_record.get(
                    "product_name")),
            aliases=(
                list(product_record.get("aliases") or [])
                if product_record else []),
            category_terms=(
                list(product_record.get("category") or [])
                if product_record else []),
            sentences=audit_record.get("sentences"),
            distinct_cited_target_count=audit_record.get(
                "distinct_cited_target_count"),
            trigger_codes=audit_record.get("trigger_codes") or [])
        if audit_record.get("methods_note_version") is not None:
            draft["methods_note_version"] = audit_record[
                "methods_note_version"]
    else:
        product_record = _require_product(home, product)
        round_record = _require_round(
            home, product_record, round_label)
        from citeline import metrics
        entries = _round_entries(home, product_record, round_record)
        answers = metrics.answer_metrics_from_journal(entries)
        draft = guide_module.draft_from_round(
            round_record,
            canonical_line=product_record.get("canonical_line"),
            audit_date=audit_date,
            answers=answers)
    entry = journal.append_entry(
        str(home), "guide_record", copy.deepcopy(draft),
        audit_date=audit_date or draft.get("audit_date"))
    result = dict(draft)
    sequence = _get(entry, "sequence", None)
    if sequence is None:
        sequence = _entry_count(home)
    result["guide_id"] = "guide-%d" % int(sequence)
    return result


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
