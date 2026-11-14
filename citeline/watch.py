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
        plan = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        _fail(
            "MALFORMED_CALL",
            "the WatchPlan file does not parse: %s" % (exc,))
    if not isinstance(plan, dict):
        _fail("MALFORMED_CALL", "the WatchPlan stands as an object")
    return plan, hashlib.sha256(raw).hexdigest()


def _validate_plan(plan):
    scope = plan.get("scope")
    if scope not in ("picked", "estate"):
        _fail(
            "MALFORMED_CALL",
            "the WatchPlan scope stands as picked or estate")
    form = plan.get("form") or "simple"
    if form not in _FORMS:
        _fail(
            "MALFORMED_CALL",
            "the WatchPlan form stands outside the three "
            "stated values: simple, advanced, agentic")
    if plan.get("home") is None:
        _fail("MALFORMED_CALL", "the WatchPlan names no home")
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
        if not isinstance(target, dict) \
                or target.get("product") is None \
                or ("page_file" in target) == ("round" in target):
            _fail(
                "MALFORMED_CALL",
                "each picked target names a product and one "
                "of a page file or a named round")
        marker = json.dumps(target, sort_keys=True, default=str)
        if marker in seen:
            _fail(
                "WATCH_DUPLICATE_TARGET",
                "a picked WatchPlan listing the same target "
                "twice stands refused at open")
        seen.append(marker)
    return targets


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
        "annually": 365,
    }
    if text in words:
        return words[text]
    import re
    match = re.fullmatch(
        r"(?:every\s+)?(\d+)\s+(day|days|week|weeks|month|months"
        r"|year|years)", text)
    if match:
        unit_days = {"day": 1, "days": 1, "week": 7, "weeks": 7,
                     "month": 30, "months": 30, "year": 365,
                     "years": 365}
        return int(match.group(1)) * unit_days[match.group(2)]
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


def run_watch(*, plan_file):
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
    home = str(plan["home"])
    scope = plan["scope"]
    audit_date = plan.get("audit_date")
    form = plan.get("form") or "simple"
    verification = service.verify(home=home)
    if not verification.get("passed"):
        _fail(
            "JOURNAL_VERIFY_FAILED",
            "the home journal fails verify; the whole round "
            "stands failed before any target runs, and no "
            "WatchRun artefact stands produced")
    products = service.list_products(home=home)
    entries = []
    trend_no_pair_count = 0
    # The append cost of one target, on the S0 append cost
    # table: one entry per entry kind the target's operation
    # appends. An audit appends a snapshot_registered entry
    # and an audit_record entry, a guide call appends a
    # guide_record entry, and a probe target appends none.
    def target_cost(target):
        if "page_file" in target:
            return 2 + (1 if target.get("guide") else 0)
        return 0

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
            if "round" in target:
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
            product = target["product"]
            if "page_file" in target:
                entries.append(
                    _audit_entry(home, plan, product, target))
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
                entries.append(_audit_entry(
                    home, plan, name, {"page_file": page_path}))
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
    audited_products = {
        entry["product"] for entry in entries
        if entry["target_kind"] == "audit"
        and entry["outcome"] != "skipped"}
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
            "count": sum(
                1 for e in entries
                if e["target_kind"] == "audit"),
            "denominator": len(products)},
        "snapshots_audited": {
            "count": sum(
                1 for e in entries
                if e["target_kind"] == "audit"
                and e["outcome"] == "completed"),
            "denominator": len(products)},
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
        "freshness_view": freshness,
        "capacity_projection": projection,
        "honesty_sentence": _honesty_sentence(),
        "bounds": _bounds(),
    }
    output = plan.get("output")
    if output:
        _write_output(result, str(output), form)
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
    if os.path.lexists(output_path):
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
    except OSError as exc:
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
