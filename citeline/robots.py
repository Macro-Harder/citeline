"""Robots evaluation for Citeline, slice S4.

This module owns the RobotsReport on its fixed field list,
the shipped crawler table as versioned product data, and
the two evaluations a robots preview needs. A preview
evaluation is never stored here: this module writes
nothing and appends nothing. It holds no likeness rule.

A supplied robots file decodes in UTF-8 strictly. A single
leading UTF-8 byte order mark is stripped once and noted.
Any other byte order mark, a legacy encoding, or an
undecodable byte fails the call closed with the recorded
error token ROBOTS_DECODING_FAILED and no evaluation. A
file over the admitted size fails with LIMIT_EXCEEDED.
Dates arrive as call inputs, never from a clock.
"""

import hashlib
import re

__all__ = [
    "TABLE_VERSION",
    "TABLE_SNAPSHOT_DATE",
    "NEXT_REFRESH_DUE_DATE",
    "ROBOTS_RULESET_VERSION",
    "HONESTY_SENTENCE",
    "ANCHOR_LIMIT",
    "ROBOTS_FILE_LIMIT_BYTES",
    "CRAWLER_TABLE",
    "RobotsError",
    "decode_robots_bytes",
    "parse_robots",
    "evaluate_robots_bytes",
    "evaluate_robots_text",
    "evaluate_robots_file",
    "evaluate_robots",
    "build_report",
    "robots_report",
    "evaluate_preview",
    "preview_evaluations",
]

TABLE_VERSION = 1
TABLE_SNAPSHOT_DATE = "2026-11-12"
NEXT_REFRESH_DUE_DATE = "2027-02-10"
ROBOTS_RULESET_VERSION = "1"
ROBOTS_FILE_LIMIT_BYTES = 512 * 1024
ROBOTS_LINE_LIMIT = 10000
ROBOTS_GROUP_LIMIT = 1000
ROBOTS_RULES_PER_GROUP_LIMIT = 10000
ROBOTS_PATH_LIMIT = 2000

HONESTY_SENTENCE = (
    "This score is a signal index. It measures the presence of "
    "citability signals. It is not validated as a predictor of "
    "citation, and it does not verify truth."
)

ANCHOR_LIMIT = (
    "Verify proves internal consistency only. A writer who "
    "replaces the whole product home can replace the chain "
    "with it. Record the head hash outside the product home."
)

_DIRECT = "directly verified"
_SECONDARY = "secondary transcription"

# One row per token, in table order. Fields: token in
# operator spelling, operator, purpose class, per row
# evidence label, purpose prose evidence label, source URL,
# source date as the sourced table states it. Rows 12 to
# 14 keep their purpose prose at secondary strength,
# resting on the vendor text as transcribed, while the
# rows stand directly verified on token, operator, source,
# and page date.
_TABLE_ROWS = [
    (1, "GPTBot", "OpenAI", "training", _DIRECT, _DIRECT,
     "https://developers.openai.com/api/docs/bots?translationFallback=es-419",
     "No date on page. Accessed 2026-11-12"),
    (2, "OAI-SearchBot", "OpenAI", "search", _DIRECT, _DIRECT,
     "https://developers.openai.com/api/docs/bots?translationFallback=es-419",
     "No date on page. Accessed 2026-11-12"),
    (3, "ChatGPT-User", "OpenAI", "user_fetch", _DIRECT, _DIRECT,
     "https://developers.openai.com/api/docs/bots?translationFallback=es-419",
     "No date on page. Accessed 2026-11-12"),
    (4, "ClaudeBot", "Anthropic", "training", _DIRECT, _DIRECT,
     "https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler",
     "Page updated 2026-11-04"),
    (5, "Claude-SearchBot", "Anthropic", "search", _DIRECT, _DIRECT,
     "https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler",
     "Page updated 2026-11-04"),
    (6, "Claude-User", "Anthropic", "user_fetch", _DIRECT, _DIRECT,
     "https://support.claude.com/en/articles/8896518-does-anthropic-crawl-data-from-the-web-and-how-can-site-owners-block-the-crawler",
     "Page updated 2026-11-04"),
    (7, "Googlebot", "Google", "search", _DIRECT, _DIRECT,
     "https://developers.google.com/search/docs/crawling-indexing/google-common-crawlers",
     "No date on page. Accessed 2026-11-12"),
    (8, "Google-Extended", "Google", "control", _DIRECT, _DIRECT,
     "https://developers.google.com/search/docs/crawling-indexing/google-common-crawlers",
     "No date on page. Accessed 2026-11-12"),
    (9, "Bingbot", "Microsoft", "search", _SECONDARY, _DIRECT,
     "https://www.bing.com/webmasters/help/which-crawlers-does-bing-use-8c184ec0",
     "No date confirmed. Checked 2026-11-12"),
    (10, "PerplexityBot", "Perplexity", "search", _DIRECT, _DIRECT,
     "https://docs.perplexity.ai/docs/resources/perplexity-crawlers",
     "Page updated 2026-10-29"),
    (11, "Perplexity-User", "Perplexity", "user_fetch", _DIRECT,
     _DIRECT,
     "https://docs.perplexity.ai/docs/resources/perplexity-crawlers",
     "Page updated 2026-10-29"),
    (12, "meta-externalagent", "Meta", "training", _SECONDARY,
     _SECONDARY,
     "https://developers.facebook.com/docs/sharing/webmasters/crawler",
     "Page last updated 2026-05-21, as reported. Checked 2026-11-12"),
    (13, "meta-webindexer", "Meta", "search", _SECONDARY,
     _SECONDARY,
     "https://developers.facebook.com/docs/sharing/webmasters/crawler",
     "Page last updated 2026-05-21, as reported. Checked 2026-11-12"),
    (14, "meta-externalfetcher", "Meta", "user_fetch", _SECONDARY,
     _SECONDARY,
     "https://developers.facebook.com/docs/sharing/webmasters/crawler",
     "Page last updated 2026-05-21, as reported. Checked 2026-11-12"),
    (15, "Applebot", "Apple", "search", _DIRECT, _DIRECT,
     "https://support.apple.com/en-al/119829",
     "Page published 2026-09-04"),
    (16, "Applebot-Extended", "Apple", "control", _DIRECT, _DIRECT,
     "https://support.apple.com/en-al/119829",
     "Page published 2026-09-04"),
    (17, "Amazonbot", "Amazon", "training", _DIRECT, _DIRECT,
     "https://developer.amazon.com/docs/amazonbot/amazonbot.html",
     "Page last updated 2026-10-26"),
    (18, "Amzn-SearchBot", "Amazon", "search", _DIRECT, _DIRECT,
     "https://developer.amazon.com/docs/amazonbot/amazonbot.html",
     "Page last updated 2026-10-26"),
    (19, "Amzn-User", "Amazon", "user_fetch", _DIRECT, _DIRECT,
     "https://developer.amazon.com/docs/amazonbot/amazonbot.html",
     "Page last updated 2026-10-26"),
    (20, "MistralAI-Training", "Mistral AI", "training", _DIRECT,
     _DIRECT,
     "https://docs.mistral.ai/robots",
     "No date on page. Accessed 2026-11-12"),
    (21, "MistralAI-Index", "Mistral AI", "search", _DIRECT,
     _DIRECT,
     "https://docs.mistral.ai/robots",
     "No date on page. Accessed 2026-11-12"),
    (22, "MistralAI-User", "Mistral AI", "user_fetch", _DIRECT,
     _DIRECT,
     "https://docs.mistral.ai/robots",
     "No date on page. Accessed 2026-11-12"),
    (23, "DuckAssistBot", "DuckDuckGo", "user_fetch", _DIRECT,
     _DIRECT,
     "https://duckduckgo.com/duckduckgo-help-pages/results/duckassistbot",
     "No date on page. Accessed 2026-11-12"),
    (24, "YouBot", "You.com", "search", _DIRECT, _DIRECT,
     "https://you.com/docs/youbot",
     "No date on page. Accessed 2026-11-12"),
    (25, "CCBot", "Common Crawl", "training", _DIRECT, _DIRECT,
     "https://commoncrawl.org/ccbot",
     "No date on page. Accessed 2026-11-12"),
]

_MIXED_PURPOSE_NOTE = (
    "Mixed purpose note: the operator documentation spans "
    "training and direct indexing, so a reader does not take "
    "the one class as the whole purpose. The purpose span "
    "wording in this note keeps its secondary label, resting "
    "on the vendor text as transcribed."
)

_APPLICABILITY_NOTES = {
    "ChatGPT-User": (
        "Applicability note: this token is not used for "
        "automatic crawling, and robots rules may not apply "
        "to it because a user initiated the action, on the "
        "operator statement."
    ),
    "Claude-User": (
        "Applicability note: this token fetches at user "
        "direction, on the operator statement."
    ),
    "Perplexity-User": (
        "Applicability note: this token generally ignores "
        "robots rules because a user requested the fetch, "
        "on the operator statement."
    ),
    "meta-externalfetcher": (
        "Applicability note: this token fetches individual "
        "links at a user request and may bypass robots "
        "rules for that reason, on the operator statement."
    ),
    "Amzn-User": (
        "Applicability note: this token fetches live "
        "information for user actions and may not follow "
        "all robots directives, on the operator statement."
    ),
    "MistralAI-User": (
        "Applicability note: this token visits a page when "
        "a user asks a question, on the operator statement."
    ),
    "DuckAssistBot": (
        "Applicability note: this token crawls pages in "
        "real time for AI assisted answers at query time, "
        "on the operator statement."
    ),
}

CRAWLER_TABLE = [
    {
        "row": row,
        "token": token,
        "operator": operator,
        "purpose_class": purpose,
        "evidence_label": evidence,
        "purpose_prose_evidence_label": prose,
        "source_url": source,
        "source_date": source_date,
        "mixed_purpose_note": (
            _MIXED_PURPOSE_NOTE if row == 12 else None
        ),
        "applicability_note": _APPLICABILITY_NOTES.get(token),
    }
    for (
        row,
        token,
        operator,
        purpose,
        evidence,
        prose,
        source,
        source_date,
    ) in _TABLE_ROWS
]

_TABLE_BY_TOKEN = {row["token"].lower(): row for row in CRAWLER_TABLE}


class RobotsError(ValueError):
    """A recorded robots failure, carrying its error token."""

    def __init__(self, token, detail=""):
        self.token = token
        message = token if not detail else token + ": " + detail
        super().__init__(message)


# ----------------------------------------------------------------
# Decoding, on the plan Section 5.4 robots decoding rules


def decode_robots_bytes(data):
    """Decode supplied robots bytes, returning (text, notes).

    Fails closed with ROBOTS_DECODING_FAILED on any byte
    order mark other than a single leading UTF-8 mark, on
    a legacy encoding, or on an undecodable byte.
    """
    if isinstance(data, str):
        return data, []
    raw = bytes(data)
    if len(raw) > ROBOTS_FILE_LIMIT_BYTES:
        raise RobotsError(
            "LIMIT_EXCEEDED",
            "robots file total size over 512 KiB",
        )
    notes = []
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        raise RobotsError(
            "ROBOTS_DECODING_FAILED",
            "a byte order mark other than a single leading "
            "UTF-8 mark stands at the head of the file",
        )
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[len(b"\xef\xbb\xbf"):]
        notes.append("bom_stripped")
        if raw.startswith(b"\xef\xbb\xbf"):
            raise RobotsError(
                "ROBOTS_DECODING_FAILED",
                "a second byte order mark stands at the "
                "head of the file",
            )
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise RobotsError(
            "ROBOTS_DECODING_FAILED",
            "the file does not decode in UTF-8 strictly",
        ) from error
    if "\ufeff" in text:
        raise RobotsError(
            "ROBOTS_DECODING_FAILED",
            "a byte order mark stands inside the file",
        )
    return text, notes


# ----------------------------------------------------------------
# Parsing


def parse_robots(text):
    """Parse decoded robots text into groups and counts.

    Duplicate groups for one token stay as separate group
    records here and are combined at evaluation. Rules
    before the first user agent line belong to a malformed
    group whose rules are not evaluated, so they are
    counted as orphan rules and dropped.
    """
    groups = []
    current = None
    blank_since_content = False
    sitemap_count = 0
    crawl_delay = None
    non_protocol_count = 0
    unknown_tokens = []
    unknown_seen = set()
    orphan_rules = 0

    def note_unknown(agent):
        key = agent.lower()
        if agent == "*":
            return
        if key in _TABLE_BY_TOKEN or key in unknown_seen:
            return
        unknown_seen.add(key)
        unknown_tokens.append(agent)

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if len(line) > ROBOTS_LINE_LIMIT:
            raise RobotsError(
                "LIMIT_EXCEEDED", "robots line length over limit"
            )
        stripped = line.strip()
        if not stripped:
            blank_since_content = True
            continue
        if stripped.startswith("#"):
            continue
        field_match = re.match(
            r"^([A-Za-z][A-Za-z-]*)\s*:\s*(.*)$", stripped
        )
        if field_match is None:
            non_protocol_count += 1
            continue
        field_name = field_match.group(1).lower()
        value = field_match.group(2).strip()
        if field_name == "user-agent":
            note_unknown(value)
            if current is None or current["rules"] or (
                blank_since_content and current["agents"]
            ):
                current = {"agents": [], "rules": []}
                groups.append(current)
                if len(groups) > ROBOTS_GROUP_LIMIT:
                    raise RobotsError(
                        "LIMIT_EXCEEDED",
                        "robots group count over limit",
                    )
            if value and value not in current["agents"]:
                current["agents"].append(value)
            blank_since_content = False
        elif field_name in ("allow", "disallow"):
            if current is None:
                # A malformed group: its rules are not
                # evaluated.
                orphan_rules += 1
                continue
            if value == "":
                # An empty value counts as no rule.
                continue
            kind = "Allow" if field_name == "allow" else "Disallow"
            current["rules"].append(
                {
                    "kind": kind,
                    "path": value,
                    "as_written": kind + ": " + value,
                }
            )
            if len(current["rules"]) > ROBOTS_RULES_PER_GROUP_LIMIT:
                raise RobotsError(
                    "LIMIT_EXCEEDED",
                    "robots rules per group over limit",
                )
            blank_since_content = False
        elif field_name == "sitemap":
            sitemap_count += 1
            # A sitemap line does not terminate a group.
        elif field_name == "crawl-delay":
            # An observation only. The case of more than
            # one crawl delay line stands at a referred
            # stop; the first value stands here.
            if crawl_delay is None:
                try:
                    crawl_delay = int(value)
                except ValueError:
                    try:
                        crawl_delay = float(value)
                    except ValueError:
                        crawl_delay = value
        else:
            non_protocol_count += 1
    return {
        "groups": groups,
        "sitemap_line_presence_count": sitemap_count,
        "crawl_delay_observation": crawl_delay,
        "non_protocol_line_count": non_protocol_count,
        "unknown_tokens": unknown_tokens,
        "orphan_rule_count": orphan_rules,
    }


# ----------------------------------------------------------------
# Evaluation


def _rule_matches(rule_path, evaluated_path):
    """Prefix matching on the path as written.

    A star in the rule path matches any sequence of
    characters. A dollar sign at the end of the rule path
    anchors the match at the end of the evaluated path.
    Percent encoding is compared as written, with no
    decoding before comparison.
    """
    anchored = rule_path.endswith("$")
    pattern = rule_path[:-1] if anchored else rule_path
    regex_parts = []
    for char in pattern:
        if char == "*":
            regex_parts.append(".*")
        else:
            regex_parts.append(re.escape(char))
    regex = "^" + "".join(regex_parts)
    if anchored:
        regex += "$"
    return re.match(regex, evaluated_path, re.DOTALL) is not None


def _winning_rule(rules, evaluated_path):
    """The most specific matching rule, or None.

    Specificity is the number of octets of the rule path
    as written. Where an allow rule and a disallow rule
    are equivalent, the allow rule is used.
    """
    best = None
    best_key = None
    for rule in rules:
        if not _rule_matches(rule["path"], evaluated_path):
            continue
        octets = len(rule["path"].encode("utf-8"))
        key = (octets, 1 if rule["kind"] == "Allow" else 0)
        if best_key is None or key > best_key:
            best = rule
            best_key = key
    return best


def _evaluate_row(row, groups_by_agent, wildcard_rules,
                  wildcard_group_name, evaluated_path):
    token = row["token"]
    specific = groups_by_agent.get(token.lower())
    if specific is not None:
        rules, supplying = specific
    elif wildcard_rules is not None:
        rules, supplying = wildcard_rules, wildcard_group_name
    else:
        rules, supplying = [], None
    winner = _winning_rule(rules, evaluated_path) if rules else None
    if winner is not None:
        fetch_outcome = (
            "allowed" if winner["kind"] == "Allow" else "blocked"
        )
        winning_rule = winner["as_written"]
    else:
        fetch_outcome = "allowed"
        winning_rule = None

    purpose = row["purpose_class"]
    defect = purpose == "search" and fetch_outcome == "blocked"
    finding = {
        "token": token,
        "operator": row["operator"],
        "purpose_class": purpose,
        "evidence_label": row["evidence_label"],
        "purpose_prose_evidence_label": row[
            "purpose_prose_evidence_label"
        ],
        "mixed_purpose_note": row["mixed_purpose_note"],
        "winning_rule": winning_rule,
        "supplying_group": supplying if winner is not None or rules else None,
        "defect": defect,
        "defect_flag": defect,
    }
    if purpose == "control":
        # A control row is never worded as blocked or
        # allowed for a path in the fetch sense.
        if winner is not None and winner["kind"] == "Disallow":
            stance = "disallows"
        else:
            stance = "does not disallow"
        finding["outcome"] = None
        finding["control_note"] = (
            "Control note: this token governs the use the "
            "operator describes for it, not a fetch of a "
            "path. On the rules that apply, the supplied "
            "file " + stance + " that use."
        )
        finding["applicability_note"] = None
    elif purpose == "user_fetch":
        # A computed outcome plus an applicability note,
        # never a bare boolean.
        finding["outcome"] = fetch_outcome
        finding["control_note"] = None
        finding["applicability_note"] = row["applicability_note"]
    else:
        finding["outcome"] = fetch_outcome
        finding["control_note"] = None
        finding["applicability_note"] = None
    if finding["supplying_group"] is None and rules:
        finding["supplying_group"] = supplying
    return finding


def _build_report(text, sha256_value, evaluated_path,
                  path_defaulted, asserted_capture_date):
    parsed = parse_robots(text)
    groups_by_agent = {}
    wildcard_rules = None
    wildcard_group_name = None
    for group in parsed["groups"]:
        for agent in group["agents"]:
            key = agent.lower()
            if key == "*":
                if wildcard_rules is None:
                    wildcard_rules = []
                    wildcard_group_name = agent
                wildcard_rules.extend(group["rules"])
            else:
                if key not in groups_by_agent:
                    groups_by_agent[key] = ([], agent)
                groups_by_agent[key][0].extend(group["rules"])
    findings = [
        _evaluate_row(
            row,
            groups_by_agent,
            wildcard_rules,
            wildcard_group_name,
            evaluated_path,
        )
        for row in CRAWLER_TABLE
    ]
    report = {
        "findings": findings,
        "evaluated_page_path": evaluated_path,
        "path_defaulted": bool(path_defaulted),
        "honesty_sentence": HONESTY_SENTENCE,
        "anchor_limit": ANCHOR_LIMIT,
        "next_refresh_due_date": NEXT_REFRESH_DUE_DATE,
        "robots_snapshot_sha256": sha256_value,
        "robots_snapshot_asserted_capture_date": asserted_capture_date,
        "table_version": TABLE_VERSION,
        "table_snapshot_date": TABLE_SNAPSHOT_DATE,
        "robots_ruleset_version": ROBOTS_RULESET_VERSION,
        "crawl_delay_observation": parsed[
            "crawl_delay_observation"
        ],
        "sitemap_line_presence_count": parsed[
            "sitemap_line_presence_count"
        ],
        "non_protocol_line_count": parsed["non_protocol_line_count"],
        "unknown_token_count": len(parsed["unknown_tokens"]),
        "finding_count": len(findings),
    }
    if parsed["unknown_tokens"]:
        # The names of the unlisted tokens are carried
        # with the count, each in the spelling the
        # supplied file used, marked not in table, and
        # carrying no verdict of any kind. This detail
        # stands only where an unlisted token stands.
        report["unknown_tokens"] = [
            {"token": token, "status": "not in table"}
            for token in parsed["unknown_tokens"]
        ]
    return report


def _resolve_path(evaluated_page_path, path_defaulted):
    if evaluated_page_path is None:
        return "/", True
    if path_defaulted is None:
        path_defaulted = False
    path = str(evaluated_page_path)
    if len(path) > ROBOTS_PATH_LIMIT:
        raise RobotsError(
            "LIMIT_EXCEEDED", "robots path argument over limit"
        )
    return path, path_defaulted


def evaluate_robots_bytes(data, evaluated_page_path=None,
                          path_defaulted=None,
                          asserted_capture_date=None,
                          audit_date=None, **_ignored):
    """Evaluate one supplied robots file given as bytes."""
    raw = bytes(data)
    sha256_value = hashlib.sha256(raw).hexdigest()
    text, _notes = decode_robots_bytes(raw)
    path, defaulted = _resolve_path(evaluated_page_path, path_defaulted)
    return _build_report(
        text, sha256_value, path, defaulted, asserted_capture_date
    )


def evaluate_robots_text(text, evaluated_page_path=None,
                         path_defaulted=None,
                         asserted_capture_date=None,
                         audit_date=None, **_ignored):
    """Evaluate one supplied robots file given as text."""
    sha256_value = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path, defaulted = _resolve_path(evaluated_page_path, path_defaulted)
    return _build_report(
        text, sha256_value, path, defaulted, asserted_capture_date
    )


def evaluate_robots_file(path, evaluated_page_path=None,
                         path_defaulted=None,
                         asserted_capture_date=None,
                         audit_date=None, **_ignored):
    """Evaluate one supplied robots file read from a path.

    The file is opened and read inside this module, the
    component that owns this intake.
    """
    with open(path, "rb") as handle:
        raw = handle.read()
    return evaluate_robots_bytes(
        raw,
        evaluated_page_path=evaluated_page_path,
        path_defaulted=path_defaulted,
        asserted_capture_date=asserted_capture_date,
        audit_date=audit_date,
    )


def evaluate_robots(source, evaluated_page_path=None, **kwargs):
    """Evaluate a supplied robots file in any of its forms.

    A bytes value is evaluated as bytes. A path value is
    read as a file. Any other string is evaluated as the
    file text itself.
    """
    if isinstance(source, (bytes, bytearray)):
        return evaluate_robots_bytes(
            bytes(source), evaluated_page_path, **kwargs
        )
    import os

    if isinstance(source, (str, os.PathLike)) and os.path.isfile(
        source
    ):
        return evaluate_robots_file(
            source, evaluated_page_path=evaluated_page_path, **kwargs
        )
    return evaluate_robots_text(
        str(source), evaluated_page_path=evaluated_page_path, **kwargs
    )


build_report = evaluate_robots
robots_report = evaluate_robots


def evaluate_preview(first, second, evaluated_page_path=None,
                     **kwargs):
    """The two evaluations a preview needs, unstored.

    Returns the pair of RobotsReports, first file first.
    Nothing is stored and nothing is appended by this
    evaluation.
    """
    first_report = evaluate_robots(
        first, evaluated_page_path=evaluated_page_path, **kwargs
    )
    second_report = evaluate_robots(
        second, evaluated_page_path=evaluated_page_path, **kwargs
    )
    return first_report, second_report


preview_evaluations = evaluate_preview
