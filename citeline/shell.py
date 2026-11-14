"""Command line shell: parse, call, format.

The shell holds no rule of its own. It performs its three
permitted acts only: it parses a call into named inputs, it
calls one service layer operation, and it formats the
record the operation returns, through the reporting
pipeline under its shell name. It returns the exit code
the item 126 table assigns to the outcome the call
reports: 0 where the call carries no error value, the code
of the class of the one error value reported where it
fails, and no code outside that table. Code 4 stands for
the gate check and stands returned by no version 1
invocation here, and code 1 stands unassigned as a product
outcome and stands returned by no invocation here.
"""

import inspect
import json
import os
import sys

from citeline import service

FORMS = ("simple", "advanced", "agentic")

# Inputs whose value stands as a list at the service seam.
# A list valued flag takes its items in one of three forms:
# a comma separated list in one flag value, a JSON list in
# one flag value, or the flag repeated once per item. A
# plain single value stands as a one item list. No value
# stands split into its characters.
_LIST_INPUTS = ("competitors", "aliases", "query_set",
                "category_terms", "category")

_USAGE = 2

# One row per subcommand: the service operation it calls,
# and the named flags it accepts. Every input stands as a
# named flag; no positional argument stands beyond the
# subcommand itself.
_SURFACE = {
    "add-product": (
        "add_product",
        ("home", "name", "canonical_line", "domain",
         "competitors", "aliases", "query_set", "audit_date",
         "form")),
    "set-canonical-line": (
        "set_canonical_line",
        ("home", "product", "line", "audit_date", "form")),
    "set-competitors": (
        "set_competitors",
        ("home", "product", "competitors", "audit_date", "form")),
    "set-aliases": (
        "set_aliases",
        ("home", "product", "aliases", "audit_date", "form")),
    "set-query-set": (
        "set_query_set",
        ("home", "product", "query_set", "audit_date", "form")),
    "set-category": (
        "set_category",
        ("home", "product", "category_terms", "category",
         "audit_date", "form")),
    "register-page": (
        "register_page",
        ("home", "product", "snapshot", "audit_date", "form")),
    "name-round": (
        "name_round",
        ("home", "product", "round_label",
         "importer_declaration", "supplier_relation",
         "audit_date", "form")),
    "audit": (
        "audit",
        ("home", "page_file", "robots_file",
         "evaluated_page_path", "audit_date", "form", "run_id")),
    "robots": (
        "robots",
        ("home", "robots_file", "evaluated_page_path", "form",
         "audit_date")),
    "robots-preview": (
        "robots_preview",
        ("home", "first_robots_file", "second_robots_file",
         "evaluated_page_path", "first_capture_date",
         "second_capture_date", "first_captured_on",
         "second_captured_on", "form", "audit_date")),
    "probe import": (
        "probe_import",
        ("home", "answer_file", "product", "round",
         "engine_label", "query", "kind", "captured_on",
         "capture_method", "control_designation", "audit_date",
         "form")),
    "probe report": (
        "probe_report",
        ("home", "product", "round", "form", "audit_date")),
    "probe trend": (
        "probe_trend",
        ("home", "product", "round_a", "round_b", "form",
         "audit_date")),
    "query-set-report": (
        "query_set_report",
        ("home", "product", "form", "audit_date")),
    "guide": (
        "guide",
        ("home", "run_id", "product", "round_label", "form",
         "audit_date")),
    "verify": ("verify", ("home", "form")),
    "status": ("status", ("home", "form")),
    "staleness-view": (
        "staleness_view", ("home", "form")),
}

# Flag spellings that name a differently named input of
# the operation they call.
_FLAG_ALIASES = {
    "name_round": {"round": "round_label"},
    "guide": {"round": "round_label"},
}

# Markers of a report artefact record, whose Agentic form
# stands as the envelope the reporting pipeline returns.
# A status or verify record carries none of these and
# renders as its own body in every form, so its stated
# field list stands present in every form.
_ARTEFACT_MARKERS = (
    "score", "checks", "opening_text", "actions", "rates",
    "entries", "outcome_counts", "changed_rows", "findings",
)


def _config_key_lines():
    """The config keys with their defaults, for the help text.

    The list stands drawn from the plan table of 44 keys:
    the 42 limit keys with the home key and the anchor key,
    each with its default, read from the journal limit
    table so the shipped text and the table cannot drift.
    """
    lines = ["config keys and their defaults:"]
    try:
        from citeline import journal
        table = list(journal._LIMIT_TABLE)
        defaults = {row[0]: (row[1], row[2]) for row in table}
        for key in journal.config_keys():
            if key in defaults:
                value, unit = defaults[key]
                lines.append(
                    "  %s: default %s %s" % (key, value, unit))
            elif key == "home_path":
                lines.append(
                    "  home_path: default the default home, a "
                    "directory named .citeline in the operator "
                    "home directory")
            elif key == "anchor_path":
                lines.append(
                    "  anchor_path: default none, unset")
    except Exception:
        pass
    return lines


def help_text():
    """The help output: the subcommand list in full.

    The list reproduces the invocation surface in full,
    with the named inputs of each subcommand, the watch
    subcommand among them, and the install routes stated
    as install.py invocations, not as subcommands. The
    usage text after the list states the config keys with
    their defaults, one labelled fixture example of a
    complete valid import, the closed sets an operator
    must supply, the watch plan format, the score band
    scale, and the English only scope line.
    """
    lines = [
        "citeline: the invocation surface, one subcommand "
        "per call, every input a named flag.",
        "Version 1 is English only.",
        "add-product --home --name --canonical_line --domain "
        "--competitors --aliases --query_set --audit_date "
        "--form",
        "set-canonical-line --home --product --line "
        "--audit_date --form",
        "set-competitors --home --product --competitors "
        "--audit_date --form",
        "set-aliases --home --product --aliases --audit_date "
        "--form",
        "set-query-set --home --product --query_set "
        "--audit_date --form",
        "set-category --home --product --category_terms "
        "--audit_date --form",
        "register-page --home --product --snapshot "
        "--audit_date --form",
        "name-round --home --product --round_label "
        "--importer_declaration --supplier_relation "
        "--audit_date --form",
        "audit --home --page_file --robots_file "
        "--evaluated_page_path --audit_date --form --run_id",
        "robots --home --robots_file --evaluated_page_path "
        "--form --audit_date",
        "robots-preview --home --first_robots_file "
        "--second_robots_file --evaluated_page_path "
        "--first_capture_date --second_capture_date --form "
        "--audit_date",
        "probe import --home --answer_file --product --round "
        "--engine_label --query --kind --captured_on "
        "--capture_method --control_designation --audit_date "
        "--form",
        "probe report --home --product --round --form "
        "--audit_date",
        "probe trend --home --product --round_a --round_b "
        "--form --audit_date",
        "query-set-report --home --product --form "
        "--audit_date",
        "guide --home --run_id --product --round_label "
        "--audit_date --form",
        "verify --home --form",
        "status --home --form",
        "staleness-view --home --form",
        "help",
        "watch --plan --form",
        "install: python install.py [location]",
        "uninstall: python install.py uninstall [location]",
        "The flag forms --location and --home stand accepted "
        "beside the install forms above, and --uninstall "
        "beside the word uninstall.",
        "Forms are simple, advanced, and agentic. The "
        "subcommands above and watch each take --form. "
        "The help line takes no flag.",
        "List valued inputs (--competitors, --aliases, "
        "--query_set, --category_terms) take a comma "
        "separated list, a JSON list, or the flag repeated "
        "once per item. A competitor item is a competitor "
        "name, or a JSON object with name, domain, and "
        "aliases.",
        "--round and --round_label name the same input, the "
        "round label, on name-round, probe import, probe "
        "report, probe trend, and guide.",
        "Dates: --captured_on is the date an answer was "
        "captured, and --first_capture_date and "
        "--second_capture_date are the capture dates of the "
        "two robots files of a preview; --audit_date is the "
        "date a call runs as of, a different date from any "
        "capture date.",
        "Closed sets an operator supplies:",
        "  answer kind (--kind): real_sample, fixture",
        "  control designation (--control_designation): "
        "positive, negative",
        "  importer_declaration: all captured answers "
        "imported; a stated subset imported; selection rule "
        "unknown",
        "  supplier_relation: supplied by the audited party; "
        "supplied by an independent party; supplier relation "
        "unknown",
        "  watch scope: picked, estate",
        "Watch plan format: the plan file is a JSON object "
        "with keys home, scope, targets, form, audit_date, "
        "output, and cadence. home names the product home; "
        "scope is picked or estate; targets stands required "
        "where scope is picked, each target naming a product "
        "and one of a page file (with an optional robots "
        "file, evaluated page path, and guide flag) or a "
        "named round; form is simple, advanced, or agentic; "
        "audit_date is the date the round runs as of; "
        "output is the path the WatchRun artefact is "
        "written to; cadence states the operator cadence in "
        "words. A plan may also name a second round per "
        "product for trend, under the key second_round.",
        "Score bands: strong at a score of 80 or more, "
        "developing at 60 or more, thin at 40 or more, and "
        "poor below 40, on a scale of 0 to 100, in that "
        "order from highest to lowest.",
        "Fixture example, a complete valid import:",
        "  probe import --home <home> --answer_file "
        "fixture-answer.txt --product Example Product "
        "--round round-1 --engine_label Fixture Engine "
        "--query What is Example Product? --kind fixture "
        "--captured_on 2026-08-16 --capture_method manual "
        "copy --control_designation positive --audit_date "
        "2026-08-16",
    ]
    lines.extend(_config_key_lines())
    return "\n".join(lines) + "\n"


def format_record(record, form="simple"):
    """Format one returned record in one reading form.

    The act stands as the reporting pipeline render under
    its shell name, and adds no field of its own to the
    record. A report artefact in the Agentic form stands
    as the envelope that pipeline returns. A status or
    verify record renders as its own body in every form,
    so the field list those operations state stands
    present in every form.
    """
    from citeline import reporting
    rendered = reporting.format_record(record, form=form)
    if form == "agentic" and isinstance(rendered, dict) \
            and "report" in rendered \
            and isinstance(record, dict) \
            and not any(marker in record
                        for marker in _ARTEFACT_MARKERS):
        return rendered["report"]
    return rendered


def _render_for_print(record, form):
    """Render one record for printing in one reading form.

    The printed Agentic form stands as the item 122 envelope
    the reporting pipeline returns, with its contract fields
    at the top level, for every command, so no printed
    Agentic artefact stands byte identical to its Advanced
    artefact. The format act above keeps its own stated
    form for a standing record rendered through it; the
    invocation print path is the surface a caller reads as
    the invocation response, and the envelope belongs there.
    """
    if form != "agentic":
        return format_record(record, form=form)
    from citeline import reporting
    return reporting.format_record(record, form="agentic")


def _exit_code_for(exc):
    code = getattr(exc, "exit_code", None)
    if code in (2, 3, 5):
        return code
    token = getattr(exc, "token", None) or getattr(
        exc, "error_value", None)
    if token is not None:
        try:
            from citeline import errors
            entry = errors.error_for_token(token)
            if entry is not None:
                return entry["exit_code"]
        except Exception:
            pass
    return 3


def _parse_flags(tokens, allowed, operation):
    inputs = {}
    aliases = _FLAG_ALIASES.get(operation, {})
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("--"):
            return None
        name = token[2:].replace("-", "_")
        name = aliases.get(name, name)
        if name not in allowed:
            return None
        if index + 1 >= len(tokens):
            return None
        value = tokens[index + 1]
        if name in _LIST_INPUTS and name in inputs:
            standing = inputs[name]
            if isinstance(standing, list):
                standing.append(value)
            else:
                inputs[name] = [standing, value]
        else:
            inputs[name] = value
        index += 2
    return inputs


def _coerce_list_inputs(inputs):
    """Carry each list valued input to the list it states.

    One flag value stands parsed as a JSON list where it
    opens with a bracket, as a JSON object where it opens
    with a brace (the competitors object form), and as a
    comma separated list otherwise. A competitor item that
    stands as a plain name stands carried as a competitor
    record naming that name. No value stands split into
    its characters.
    """
    out = dict(inputs)
    for name in _LIST_INPUTS:
        if name not in out:
            continue
        raw = out[name]
        values = raw if isinstance(raw, list) else [raw]
        items = []
        for value in values:
            if not isinstance(value, str):
                items.append(value)
                continue
            text = value.strip()
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                except ValueError:
                    return None
                if not isinstance(parsed, list):
                    return None
                items.extend(parsed)
            elif text.startswith("{"):
                try:
                    items.append(json.loads(text))
                except ValueError:
                    return None
            elif text:
                items.extend(
                    part.strip() for part in text.split(",")
                    if part.strip())
        if name == "competitors":
            items = [
                item if isinstance(item, dict)
                else {"name": item}
                for item in items]
        out[name] = items
    return out


def _print_rendered(rendered):
    """Print one rendered record in the form it stands in.

    A Simple form stands as prose text and prints as it
    stands. A structured form (Advanced or Agentic) stands
    as a record object and prints as JSON text. No form
    stands discarded.
    """
    if rendered is None:
        return
    if isinstance(rendered, str):
        print(rendered, end="" if rendered.endswith("\n")
              else "\n")
    elif isinstance(rendered, (dict, list)):
        print(json.dumps(rendered, indent=2, sort_keys=True,
                         default=str))
    else:
        print(str(rendered))


def _print_error(exc):
    """Print the error value and message of one failed call."""
    try:
        record = service.recorded_error(exc)
        value = record.get("error_value")
        message = record.get("message") or str(exc)
    except Exception:
        value = getattr(exc, "token", None) or getattr(
            exc, "error_value", None)
        message = str(exc)
    if value:
        text = str(message)
        prefix = "%s: " % (value,)
        if text == str(value):
            text = ""
        elif text.startswith(prefix):
            text = text[len(prefix):]
        if text:
            print("%s: %s" % (value, text), file=sys.stderr)
        else:
            print(str(value), file=sys.stderr)
    else:
        print(str(message), file=sys.stderr)


def _default_home():
    """The stated default product home: a directory named
    .citeline in the operator home directory."""
    return os.path.join(os.path.expanduser("~"), ".citeline")


def _extract_value(tokens, flag):
    """The value standing after one flag spelling, or None."""
    tokens = list(tokens or [])
    for index, token in enumerate(tokens):
        if token == flag and index + 1 < len(tokens):
            return tokens[index + 1]
    return None


def _home_from_plan(plan_path):
    """The home a watch plan file names, or None."""
    if not plan_path:
        return None
    try:
        with open(plan_path, "r", encoding="utf-8") as handle:
            plan = json.load(handle)
    except Exception:
        return None
    if isinstance(plan, dict):
        home = plan.get("home")
        if isinstance(home, str) and home:
            return home
    return None


def _append_malformed_record(home, operation, audit_date=None):
    """Append the row U-8 failure record for one malformed call.

    The record stands appended only where a home stands and
    its chain verifies, on the row U-8 terms: where the chain
    accepts appends. Where no home stands named, or the chain
    does not accept an append, the caller response stands as
    the only record and nothing is created.
    """
    if not home or not os.path.isdir(str(home)):
        return
    try:
        from citeline import journal
        chain = journal.verify_chain(str(home))
        if not chain.get("passed"):
            return
        payload = {
            "operation": operation,
            "error_value": "MALFORMED_CALL",
            "subject_identity": str(operation),
            "date": audit_date,
            "rule_fired": "MALFORMED_CALL",
        }
        journal.append_entry(
            str(home), "failure_record", payload,
            audit_date=audit_date)
    except Exception:
        pass


def _usage_error(detail, home=None, operation="citeline",
                 audit_date=None):
    """The governed malformed call outcome, at the shell layer.

    Prints the MALFORMED_CALL value with its message to
    standard error, reproduces the subcommand list in full
    on standard output, appends the failure record where the
    named home chain accepts appends, and returns the usage
    exit code 2.
    """
    from citeline import errors
    exc = errors.CitelineError(detail, token="MALFORMED_CALL")
    _append_malformed_record(home, operation, audit_date)
    _print_error(exc)
    print(help_text(), end="")
    return _USAGE


def _missing_required(operation, inputs):
    """The required inputs of one operation that stand absent.

    The required set stands read from the service operation
    signature: a parameter with no default stands required,
    except the home input, whose default the shell supplies,
    and the form input, which the shell itself carries. One
    stated alternative stands beside the signature rule: an
    audit call names either a page file or a standing run
    identity, so the page file stands required exactly where
    the call names neither.
    """
    try:
        signature = inspect.signature(getattr(service, operation))
    except Exception:
        return []
    present = set(inputs)
    if operation == "set_category" and "category" in present:
        present.add("category_terms")
    missing = []
    for name, parameter in signature.parameters.items():
        if parameter.default is not inspect.Parameter.empty:
            continue
        if name in ("home", "form"):
            continue
        if name not in present:
            missing.append(name)
    if operation == "audit" and "page_file" not in present \
            and "run_id" not in present:
        missing.append("page_file")
    return missing


def main(argv=None):
    """Run one invocation and return its exit code."""
    argv = list(argv or [])
    if not argv:
        return _usage_error(
            "the call names no subcommand in the invocation "
            "surface list")
    if argv[0] == "help":
        if len(argv) != 1:
            return _usage_error(
                "help takes no further input: %s"
                % " ".join(argv[1:]),
                home=_extract_value(argv, "--home"))
        print(help_text(), end="")
        return 0
    if argv[0] == "watch":
        return _run_watch(argv[1:])
    if argv[0] == "probe":
        if len(argv) < 2 or argv[1] not in ("import", "report",
                                            "trend"):
            bad = argv[1] if len(argv) > 1 else ""
            return _usage_error(
                "the call names no probe subcommand in the "
                "invocation surface list: probe %s" % bad,
                home=_extract_value(argv, "--home"),
                operation="probe")
        subcommand = "probe " + argv[1]
        tokens = argv[2:]
    else:
        subcommand = argv[0]
        tokens = argv[1:]
    if subcommand not in _SURFACE:
        return _usage_error(
            "the call names no subcommand in the invocation "
            "surface list: %s" % subcommand,
            home=_extract_value(argv, "--home"),
            operation=subcommand)
    operation, allowed = _SURFACE[subcommand]
    inputs = _parse_flags(tokens, allowed, operation)
    if inputs is None:
        return _usage_error(
            "the call stands malformed: its inputs stand as "
            "named flags with a value each, from the inputs "
            "the subcommand accepts",
            home=_extract_value(tokens, "--home"),
            operation=subcommand,
            audit_date=_extract_value(tokens, "--audit_date"))
    inputs = _coerce_list_inputs(inputs)
    if inputs is None:
        return _usage_error(
            "the call stands malformed: a list valued input "
            "stands in no admitted list form",
            home=inputs.get("home") if inputs else
            _extract_value(tokens, "--home"),
            operation=subcommand,
            audit_date=_extract_value(tokens, "--audit_date"))
    form = inputs.get("form")
    if form is not None and form not in FORMS:
        return _usage_error(
            "the form input stands outside the three stated "
            "values (simple, advanced, agentic): %s" % form,
            home=inputs.get("home"),
            operation=subcommand,
            audit_date=inputs.get("audit_date"))
    missing = _missing_required(operation, inputs)
    if missing:
        return _usage_error(
            "the call names no %s, which stands required"
            % ", ".join(missing),
            home=inputs.get("home"),
            operation=subcommand,
            audit_date=inputs.get("audit_date"))
    if operation == "audit" and "run_id" in inputs:
        # A run identity stands alone in an audit call: any
        # fresh audit input named beside it stands refused
        # here, in the standing shell outcome, before the
        # service call can disregard it. A named audit date
        # that is not a date stands left to the service
        # call, whose non date refusal governs that value.
        fresh_named = [
            name for name in ("page_file", "robots_file",
                              "evaluated_page_path",
                              "audit_date")
            if name in inputs]
        date_names_fresh = "audit_date" not in fresh_named
        if "audit_date" in fresh_named:
            import datetime
            try:
                datetime.date.fromisoformat(
                    str(inputs["audit_date"]))
                date_names_fresh = True
            except ValueError:
                date_names_fresh = False
        if fresh_named and date_names_fresh:
            return _usage_error(
                "an audit call naming a run identity names "
                "no fresh audit input beside it; the call "
                "also names %s" % ", ".join(fresh_named),
                home=inputs.get("home"),
                operation=subcommand,
                audit_date=inputs.get("audit_date"))
    if "home" not in inputs:
        inputs["home"] = _default_home()
    call = dict(inputs)
    call.pop("form", None)
    try:
        record = getattr(service, operation)(**call)
    except TypeError:
        return _usage_error(
            "the call stands malformed against the inputs "
            "the subcommand accepts",
            home=inputs.get("home"),
            operation=subcommand,
            audit_date=inputs.get("audit_date"))
    except Exception as exc:
        _print_error(exc)
        return _exit_code_for(exc)
    try:
        rendered = _render_for_print(record, form=form or "simple")
        _print_rendered(rendered)
    except Exception:
        pass
    if operation == "verify":
        return 0 if record.get("passed") else 5
    return 0


def _run_watch(tokens):
    inputs = _parse_flags(tokens, ("plan", "form"), "watch")
    if inputs is None or "plan" not in inputs:
        return _usage_error(
            "the watch call names no plan, which stands "
            "required",
            home=_home_from_plan(_extract_value(tokens, "--plan")),
            operation="watch")
    form = inputs.get("form")
    if form is not None and form not in FORMS:
        return _usage_error(
            "the form input stands outside the three stated "
            "values (simple, advanced, agentic): %s" % form,
            home=_home_from_plan(inputs.get("plan")),
            operation="watch")
    from citeline import watch
    try:
        result = watch.run_watch(plan_file=inputs["plan"])
    except TypeError:
        return _usage_error(
            "the watch call stands malformed against the "
            "inputs the subcommand accepts",
            home=_home_from_plan(inputs.get("plan")),
            operation="watch")
    except Exception as exc:
        _print_error(exc)
        return _exit_code_for(exc)
    try:
        rendered = _render_for_print(
            result, form=form or result.get("form") or "simple")
        _print_rendered(rendered)
    except Exception:
        pass
    return 0


__all__ = ["FORMS", "format_record", "help_text", "main"]
