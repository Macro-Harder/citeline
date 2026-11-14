"""Shared error vocabulary and recorded error types.

The vocabulary is the closed set fixed by the design plan
at entry 13, joined with the exit code table at item 126.
Every value carries its row, its token, its precedence
class, and the exit code its class assigns. No value
outside this set may ship. The exception types in this
module carry a row and a token from this vocabulary, so a
caller response and a failure record read the same value.
"""

CLASS_TO_EXIT = {"usage": 2, "domain": 3, "integrity": 5}


def _row(row, token, precedence_class, condition, failure_record,
         **extra):
    entry = {
        "row": row,
        "token": token,
        "precedence_class": precedence_class,
        "exit_code": CLASS_TO_EXIT[precedence_class],
        "condition": condition,
        "failure_record": failure_record,
    }
    entry.update(extra)
    return entry


_APPENDED = "Failure record appended where the chain accepts appends."
_CALLER_ONLY = "No failure record: the recorded error is the caller response only."

ERROR_VOCABULARY = [
    _row("U-1", "UNKNOWN_PRODUCT", "usage",
         "Unknown product, or a missing product that stands in no registry entry of the home.",
         _APPENDED),
    _row("U-2", "PRODUCT_READD_CHANGED", "usage",
         "Re-adding a product with any change.",
         _APPENDED),
    _row("U-3", "ROUND_FIELD_OUT_OF_SET", "usage",
         "Out of set field values at round naming.",
         _APPENDED),
    _row("U-4", "UNKNOWN_ROUND", "usage",
         "An unknown round, or a missing round not named for that product.",
         _APPENDED),
    _row("U-5", "CONTROL_CAP_EXCEEDED", "usage",
         "A control designation past the cap of 5 designated controls in one round for one source kind.",
         _APPENDED),
    _row("U-6", "HOME_MISSING", "usage",
         "A read only invocation over a missing home.",
         _CALLER_ONLY),
    _row("U-7", "ROUND_REPEATED", "usage",
         "A trend naming the same round twice.",
         _APPENDED),
    _row("U-8", "MALFORMED_CALL", "usage",
         "A generic malformed call.",
         _APPENDED),
    _row("U-9", "WATCHPLAN_SIZE_EXCEEDED", "usage",
         "A WatchPlan file over the 1 MiB governing size bound.",
         _CALLER_ONLY),
    _row("U-10", "WATCH_TARGET_COUNT_EXCEEDED", "usage",
         "A picked WatchPlan file naming more than 100 targets.",
         _CALLER_ONLY),
    _row("U-11", "WATCH_ESTATE_WITH_TARGETS", "usage",
         "A WatchPlan file whose scope is estate and which also lists targets.",
         _CALLER_ONLY),
    _row("U-12", "WATCH_DUPLICATE_TARGET", "usage",
         "A picked WatchPlan file listing the same target twice.",
         _CALLER_ONLY),
    _row("U-13", "WATCH_NO_TARGETS", "usage",
         "A picked WatchPlan file naming no target where scope is picked.",
         _CALLER_ONLY),
    _row("I-1", "JOURNAL_CAP_EXCEEDED", "integrity",
         "The cap refusal, serving both the ordinary append cap refusal and the import preflight refusal.",
         "At the cap, no failure record. A preflight refusal below both caps appends a failure record carrying the distinguishing field.",
         distinguishing_field="refusal_context",
         distinguishing_values=["append_cap", "import_preflight"],
         limit_numbers=[39, 40]),
    _row("I-2", "JOURNAL_VERIFY_FAILED", "integrity",
         "A verify refusal: an operation barred because the journal fails verify, and the verify operation reporting a chain that does not verify.",
         _CALLER_ONLY),
    _row("D-1", "ROUND_LABEL_EXISTS", "domain",
         "A standing round label for the product at round naming.",
         _APPENDED),
    _row("X-1", "CONFIG_INVALID", "integrity",
         "A config file that cannot be parsed, holds a value of the wrong form, or holds a duplicate key.",
         _APPENDED),
    _row("X-2", "ANCHOR_PATH_INSIDE_HOME", "usage",
         "An anchor path inside the product home, refused at config validation.",
         _APPENDED),
    _row("X-3", "LIMIT_EXCEEDED", "integrity",
         "A breach of any limit other than limits 39 and 40.",
         _APPENDED),
    _row("X-4", "SUPPLIED_PATH_UNSAFE", "integrity",
         "A supplied path that is not a regular file, is itself a symbolic link, has a hard link count above 1, or whose opened handle does not match the pre open stat.",
         _APPENDED),
    _row("X-5", "VALIDATION_FAILED", "usage",
         "A name, slug, domain, or alias form that fails the validation forms.",
         _APPENDED),
    _row("X-6", "DUPLICATE_IMPORT", "domain",
         "A duplicate import, identical in round, engine, query, and content hash to one already imported.",
         _APPENDED),
    _row("X-7", "CONTRADICTORY_IMPORT", "domain",
         "A contradiction import whose metadata contradicts an existing record.",
         _APPENDED),
    _row("X-8", "UNCOVERED_IMPORT_FORM", "usage",
         "An uncovered import form as a class, meeting none of the six validation tests.",
         _APPENDED),
    _row("X-9", "DESTINATION_EXISTS", "domain",
         "The destination exists failure at the no replace boundary, and its install form.",
         _APPENDED),
    _row("X-10", "WRITE_CONTENDED", "integrity",
         "A contended writing invocation under the concurrency exclusion.",
         _CALLER_ONLY),
    _row("X-11", "LIMIT_RAISE_REPEATED", "usage",
         "A second limit raise for the same limit in the same run.",
         _APPENDED),
    _row("X-12", "LOCK_UNAVAILABLE", "integrity",
         "A writing invocation on a platform or filesystem that cannot give the lock.",
         _CALLER_ONLY),
    _row("X-13", "TEMPORARY_LOST", "integrity",
         "A temporary lost under its writer before its link step.",
         _APPENDED),
    _row("X-14", "PAGE_EXTRACTION_FAILED", "usage",
         "A page extraction failure that fails an audit closed.",
         _APPENDED),
    _row("X-15", "ROBOTS_DECODING_FAILED", "usage",
         "A robots decoding failure in a supplied robots file.",
         _APPENDED),
    _row("X-16", "IMPORT_VALIDATION_FAILED", "usage",
         "An import validation failure on a covered form.",
         _APPENDED),
]

_BY_ROW = {entry["row"]: entry for entry in ERROR_VOCABULARY}
_BY_TOKEN = {entry["token"]: entry for entry in ERROR_VOCABULARY}


def error_for_row(row):
    """Return the vocabulary entry for a row, or None."""
    return _BY_ROW.get(row)


def error_for_token(token):
    """Return the vocabulary entry for a token, or None."""
    return _BY_TOKEN.get(token)


class CitelineError(Exception):
    """A recorded error: one value from the closed vocabulary.

    Carries the plan row and the token beside the message.
    The exit code follows the row through the vocabulary
    where the caller does not state one itself.
    """

    def __init__(self, message, row=None, token=None, exit_code=None,
                 refusal_context=None, limit_number=None):
        super().__init__(message)
        self.message = message
        self.row = row
        entry = None
        if token is not None:
            entry = _BY_TOKEN.get(token)
        elif row is not None:
            entry = _BY_ROW.get(row)
        if token is None and entry is not None:
            token = entry["token"]
        self.token = token
        if exit_code is None and entry is not None:
            exit_code = entry["exit_code"]
        self.exit_code = exit_code
        self.refusal_context = refusal_context
        self.limit_number = limit_number

    @property
    def error_value(self):
        """The token this error reports, from the vocabulary."""
        return self.token


class JournalError(CitelineError):
    """A journal, store, or writing invocation failure."""


class ConfigError(CitelineError):
    """A config surface failure, at rows X-1 and X-2 in the main."""


__all__ = [
    "CLASS_TO_EXIT",
    "ERROR_VOCABULARY",
    "CitelineError",
    "ConfigError",
    "JournalError",
    "error_for_row",
    "error_for_token",
]
