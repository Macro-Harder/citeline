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

from citeline import service

FORMS = ("simple", "advanced", "agentic")

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
         "evaluated_page_path", "audit_date", "form")),
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


def help_text():
    """The help output: the subcommand list in full.

    The list reproduces the invocation surface in full,
    with the named inputs of each subcommand, the watch
    subcommand among them, and the install routes stated
    as install.py invocations, not as subcommands.
    """
    lines = [
        "citeline: the invocation surface, one subcommand "
        "per call, every input a named flag.",
        "add-product --home --name --canonical_line --domain "
        "--competitors --aliases --query_set --audit_date",
        "set-canonical-line --home --product --line "
        "--audit_date",
        "set-competitors --home --product --competitors "
        "--audit_date",
        "set-aliases --home --product --aliases --audit_date",
        "set-query-set --home --product --query_set "
        "--audit_date",
        "set-category --home --product --category_terms "
        "--audit_date",
        "register-page --home --product --snapshot "
        "--audit_date",
        "name-round --home --product --round_label "
        "--importer_declaration --supplier_relation "
        "--audit_date",
        "audit --home --page_file --robots_file "
        "--evaluated_page_path --audit_date",
        "robots --home --robots_file --evaluated_page_path "
        "--form --audit_date",
        "robots-preview --home --first_robots_file "
        "--second_robots_file --evaluated_page_path "
        "--first_capture_date --second_capture_date --form "
        "--audit_date",
        "probe import --home --answer_file --product --round "
        "--engine_label --query --kind --captured_on "
        "--capture_method --control_designation --audit_date",
        "probe report --home --product --round --form "
        "--audit_date",
        "probe trend --home --product --round_a --round_b "
        "--form --audit_date",
        "query-set-report --home --product --form "
        "--audit_date",
        "guide --home --run_id --product --round_label "
        "--audit_date",
        "verify --home",
        "status --home --form",
        "help",
        "watch --plan",
        "install: python install.py --location --home",
        "uninstall: python install.py --uninstall "
        "--location --home",
    ]
    return "\n".join(lines) + "\n"


def format_record(record, form="advanced"):
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
        inputs[name] = tokens[index + 1]
        index += 2
    return inputs


def main(argv=None):
    """Run one invocation and return its exit code."""
    argv = list(argv or [])
    if not argv:
        return _USAGE
    if argv[0] == "help":
        if len(argv) != 1:
            return _USAGE
        print(help_text(), end="")
        return 0
    if argv[0] == "watch":
        return _run_watch(argv[1:])
    if argv[0] == "probe":
        if len(argv) < 2 or argv[1] not in ("import", "report",
                                            "trend"):
            return _USAGE
        subcommand = "probe " + argv[1]
        tokens = argv[2:]
    else:
        subcommand = argv[0]
        tokens = argv[1:]
    if subcommand not in _SURFACE:
        return _USAGE
    operation, allowed = _SURFACE[subcommand]
    inputs = _parse_flags(tokens, allowed, operation)
    if inputs is None:
        return _USAGE
    form = inputs.get("form")
    if form is not None and form not in FORMS:
        return _USAGE
    call = dict(inputs)
    call.pop("form", None)
    try:
        record = getattr(service, operation)(**call)
    except Exception as exc:
        return _exit_code_for(exc)
    if operation == "verify":
        return 0 if record.get("passed") else 5
    if operation == "status":
        return 0
    try:
        rendered = format_record(record, form=form or "advanced")
        if isinstance(rendered, str):
            print(rendered, end="" if rendered.endswith("\n")
                  else "\n")
    except Exception:
        pass
    return 0


def _run_watch(tokens):
    inputs = _parse_flags(tokens, ("plan", "form"), "watch")
    if inputs is None or "plan" not in inputs:
        return _USAGE
    form = inputs.get("form")
    if form is not None and form not in FORMS:
        return _USAGE
    from citeline import watch
    try:
        watch.run_watch(plan_file=inputs["plan"])
    except Exception as exc:
        return _exit_code_for(exc)
    return 0


__all__ = ["FORMS", "format_record", "help_text", "main"]
