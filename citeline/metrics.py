"""Metrics for Citeline, slice S7.

This module owns RoundMetrics, the one authoritative rates
object, the Wilson construction at effective n, tiers, per
query and per competitor breakdowns, clustering figures as
disclosed figures, trend computation under contract C5, and
guards G1, G3, G4, and G8 as computations.

Metrics consume AnswerMetrics only, on contract 4 terms.
Figures are computed per source kind, never pooled across
kinds, and never across products. Dates in the inputs are
call inputs, read as asserted values only. No date is read
from a clock here.
"""

import math
import re
import unicodedata
from collections import Counter, defaultdict

Z_VALUE = 1.96

HONESTY_LINE = (
    "comparability is shown only for the recorded frame, and "
    "a silent engine change under a fixed label cannot be shown"
)

VERSION_KEYS = (
    "registry_version",
    "detector_version",
    "query_set_version",
    "lexicon_version",
    "ruleset_version",
    "crawler_table_version",
)

BREAK_VERSION_KEYS = (
    "registry_version",
    "detector_version",
    "query_set_version",
    "lexicon_version",
)


def _get(record, name, default=None):
    if record is None:
        return default
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def _first(record, names, default=None):
    for name in names:
        value = _get(record, name, None)
        if value is not None:
            return value
    return default


def wilson_interval(rate, effective_n):
    """Return the Wilson interval for a rate at effective n.

    The construction uses z equal to 1.96 and is clamped to
    the range 0 to 1. A call with effective n of 0 returns
    None, matching the null rate and null interval rule.
    """
    if rate is None or not effective_n:
        return None
    n = float(effective_n)
    z = Z_VALUE
    z2 = z * z
    centre = rate + z2 / (2.0 * n)
    margin = z * math.sqrt(
        (rate * (1.0 - rate) + z2 / (4.0 * n)) / n
    )
    denominator = 1.0 + z2 / n
    low = (centre - margin) / denominator
    high = (centre + margin) / denominator
    low = max(0.0, min(1.0, low))
    high = max(0.0, min(1.0, high))
    if rate == 0.0:
        low = 0.0
    if rate == 1.0:
        high = 1.0
    return (low, high)


def tier_for(effective_n):
    """Return the tier label for an effective n value."""
    if effective_n is None or effective_n < 5:
        return "count only"
    if effective_n < 20:
        return "exploratory"
    if effective_n < 50:
        return "provisional"
    return "reportable"


def rates_separated(first_interval, second_interval):
    """Return True where two Wilson intervals do not overlap.

    Guard G4: where two compared rates have overlapping
    Wilson intervals, the sample does not separate them.
    Intervals that only touch at one endpoint still overlap.
    """
    if first_interval is None or second_interval is None:
        return False
    first_low, first_high = first_interval
    second_low, second_high = second_interval
    if first_low is None or first_high is None:
        return False
    if second_low is None or second_high is None:
        return False
    return first_high < second_low or second_high < first_low


def _normalised_text(text):
    value = unicodedata.normalize("NFC", text or "")
    value = value.casefold()
    return " ".join(value.split())


def _shingles(text):
    words = _normalised_text(text).split()
    if len(words) < 5:
        return set()
    return {" ".join(words[i:i + 5]) for i in range(len(words) - 4)}


def _texts_similar(first, second):
    first_norm = _normalised_text(first)
    second_norm = _normalised_text(second)
    first_set = _shingles(first)
    second_set = _shingles(second)
    if not first_set or not second_set:
        return first_norm == second_norm
    union = first_set | second_set
    if not union:
        return first_norm == second_norm
    return len(first_set & second_set) / len(union) >= 0.80


def _rate_block(answers, key, effective_n):
    n = len(answers)
    if n == 0:
        rate = None
        interval = None
    else:
        rate = sum(1 for item in answers if _get(item, key)) / n
        interval = wilson_interval(rate, effective_n)
    if interval is None:
        low, high = None, None
    else:
        low, high = interval
    return {
        "rate": rate,
        "wilson_low": low,
        "wilson_high": high,
        "n": n,
        "tier": tier_for(effective_n),
        "small_sample_warning": bool(effective_n is not None and effective_n < 50),
        "coverage_probability_claimed": False,
        "count": sum(1 for item in answers if _get(item, key)) if n else 0,
    }


def _competitor_entries(answer):
    entries = _get(answer, "competitors", None)
    if entries is None:
        entries = _get(answer, "per_competitor", None)
    if entries is None:
        return []
    if isinstance(entries, dict):
        result = []
        for name, outcome in entries.items():
            if isinstance(outcome, dict):
                row = dict(outcome)
            else:
                row = {"named": bool(outcome)}
            row.setdefault("name", name)
            result.append(row)
        return result
    return list(entries)


def _competitor_outcome(answer, name):
    for entry in _competitor_entries(answer):
        if _get(entry, "name") == name:
            return entry
    return None


def round_metrics(answers, kind, frame=None, datum=None,
                  aliases=None, competitors=None):
    """Compute RoundMetrics for one source kind.

    The answers argument carries AnswerMetrics values, each
    with the AnswerRecord context fields the plan states.
    Only answers of the requested kind enter any figure.
    Control answers enter no rate, count, cluster, or tier,
    apart from imported_count and control_count, which
    disclose them.
    """
    answers = list(answers or [])
    frame = frame or {}
    datum = datum or {}

    by_kind = []
    for item in answers:
        item_kind = _first(item, ("source_kind", "kind"), None)
        if item_kind is None or item_kind == kind:
            by_kind.append(item)
    imported_count = len(by_kind)
    controls = [item for item in by_kind if _first(item, ("control", "control_flag"), False)]
    control_count = len(controls)
    active = [item for item in by_kind if item not in controls] if controls else list(by_kind)
    # The membership test above relies on equality. Dicts that
    # compare equal but stand as distinct control rows are
    # handled by identity below, which is the safe reading.
    if controls:
        control_ids = {id(item) for item in controls}
        active = [item for item in by_kind if id(item) not in control_ids]

    n = len(active)

    cluster_sizes = Counter()
    cluster_members = defaultdict(list)
    for item in active:
        cluster_id = _get(item, "cluster_id", None)
        if cluster_id is None:
            cluster_id = ("own", id(item))
        cluster_sizes[cluster_id] += 1
        cluster_members[cluster_id].append(item)
    cluster_count = len(cluster_sizes)
    effective_n = cluster_count
    design_effect = (n / cluster_count) if cluster_count else None
    if n == 0:
        largest_cluster_share = None
    else:
        largest_cluster_share = max(cluster_sizes.values()) / n

    chained_cluster_count = 0
    for members in cluster_members.values():
        if len(members) < 2:
            continue
        texts = [(_get(item, "text", "") or "") for item in members]
        similar_pairs = 0
        pair_count = 0
        connected = True
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                pair_count += 1
                if _texts_similar(texts[i], texts[j]):
                    similar_pairs += 1
        if pair_count and 0 < similar_pairs < pair_count:
            # A cluster held together by some similar pairs,
            # while at least one pair is not similar, stands
            # chained, provided its similar pairs link every
            # member. Reachability is checked on the graph.
            parent = list(range(len(texts)))

            def find(x):
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            for i in range(len(texts)):
                for j in range(i + 1, len(texts)):
                    if _texts_similar(texts[i], texts[j]):
                        ri, rj = find(i), find(j)
                        if ri != rj:
                            parent[ri] = rj
            connected = len({find(i) for i in range(len(texts))}) == 1
            if connected:
                chained_cluster_count += 1

    rates = {
        "named": _rate_block(active, "named", effective_n),
        "named_early": _rate_block(active, "named_early", effective_n),
        "cited": _rate_block(active, "cited", effective_n),
    }

    per_query = {}
    query_groups = defaultdict(list)
    for item in active:
        query_groups[_get(item, "query", "")].append(item)
    for query, group in query_groups.items():
        per_query[query] = {
            "answer_count": len(group),
            "n": len(group),
            "named_count": sum(1 for item in group if _get(item, "named")),
            "named_early_count": sum(1 for item in group if _get(item, "named_early")),
            "cited_count": sum(1 for item in group if _get(item, "cited")),
        }

    competitor_names = []
    if competitors:
        for comp in competitors:
            name = comp if isinstance(comp, str) else _get(comp, "name")
            if name and name not in competitor_names:
                competitor_names.append(name)
    for item in active:
        for entry in _competitor_entries(item):
            name = _get(entry, "name")
            if name and name not in competitor_names:
                competitor_names.append(name)
    per_competitor = {}
    for name in competitor_names:
        named_count = 0
        cited_outcomes = []
        cited_reason = None
        for item in active:
            outcome = _competitor_outcome(item, name)
            if outcome is None:
                cited_outcomes.append(False)
                continue
            if _get(outcome, "named"):
                named_count += 1
            cited_value = _get(outcome, "cited", False)
            if cited_value is None:
                cited_reason = _get(outcome, "cited_reason", None) or "competitor domain stands empty"
            else:
                cited_outcomes.append(bool(cited_value))
        if cited_reason is not None:
            per_competitor[name] = {
                "name": name,
                "named_count": named_count,
                "cited_rate": None,
                "cited_reason": cited_reason,
                "cited_not_applicable": True,
            }
        else:
            cited_rate = None
            if n:
                cited_rate = sum(1 for value in cited_outcomes if value) / n
            per_competitor[name] = {
                "name": name,
                "named_count": named_count,
                "cited_rate": cited_rate,
                "cited_reason": None,
                "cited_not_applicable": False,
            }

    per_alias_counts = {}
    if aliases:
        for alias in aliases:
            per_alias_counts.setdefault(alias, 0)
    for item in active:
        matched = _get(item, "matched_aliases", None) or []
        for alias in set(matched):
            per_alias_counts[alias] = per_alias_counts.get(alias, 0) + 1

    citing_answer_count = 0
    citation_instance_count = 0
    self_instance_count = 0
    gross_citing = 0
    net_citing = 0
    for item in active:
        instances = _get(item, "citation_instances", None)
        if instances is None:
            instances = 1 if _get(item, "cited") else 0
        instances = int(instances or 0)
        self_instances = int(_get(item, "self_citation_instances", 0) or 0)
        citation_instance_count += instances
        self_instance_count += self_instances
        if instances > 0:
            citing_answer_count += 1
            gross_citing += 1
        if instances - self_instances > 0:
            net_citing += 1
    if n:
        cited_rate_gross = gross_citing / n
        cited_rate_net = net_citing / n
    else:
        cited_rate_gross = None
        cited_rate_net = None
    if citation_instance_count:
        self_citation_share = self_instance_count / citation_instance_count
    else:
        self_citation_share = None

    no_name_count = 0
    for item in active:
        if _get(item, "named"):
            continue
        if _first(item, ("competitor_named",), False):
            continue
        if _get(item, "matched_aliases"):
            continue
        competitor_named = False
        for entry in _competitor_entries(item):
            if _get(entry, "named"):
                competitor_named = True
        if competitor_named:
            continue
        no_name_count += 1

    empty_answer_count = sum(
        1 for item in active
        if not ((_get(item, "text", "") or "").strip())
        and _get(item, "text", None) is not None
    )
    # Answers that carry no text field at all are counted by
    # their AnswerMetrics empty outcome where one stands.
    if any(_get(item, "text", None) is None for item in active):
        empty_answer_count = sum(
            1 for item in active
            if not ((_get(item, "text", "") or "").strip())
        )

    engine_values = [_first(item, ("engine_label", "engine"), "") for item in active]
    query_values = [_get(item, "query", "") for item in active]
    day_values = [_get(item, "captured_on", "") for item in active]
    method_values = [_first(item, ("capture_method", "method"), "") for item in active]

    def largest_share(values):
        if not values:
            return 0, 0.0
        count = Counter(values).most_common(1)[0][1]
        return count, (count / len(values) * 100.0)

    engine_count, engine_percent = largest_share(engine_values)
    query_count, query_percent = largest_share(query_values)
    day_count, day_percent = largest_share(day_values)
    # Dominance stands on an axis that mixes values, where
    # one value supplies more than half. An axis holding one
    # value only is the frame itself, not a mixture that one
    # part dominates, so it does not raise the note alone.
    dominance = bool(
        n
        and (
            (len(set(engine_values)) > 1 and engine_count * 2 > n)
            or (len(set(query_values)) > 1 and query_count * 2 > n)
            or (len(set(day_values)) > 1 and day_count * 2 > n)
        )
    )
    composition = {
        "largest_engine_share_count": engine_count,
        "largest_engine_share_percent": engine_percent,
        "largest_query_share_count": query_count,
        "largest_query_share_percent": query_percent,
        "largest_day_share_count": day_count,
        "largest_day_share_percent": day_percent,
        "dominance_note": dominance,
    }

    stamp_source = {}
    stamp_source.update(datum)
    for key, value in frame.items():
        if key in VERSION_KEYS and key not in stamp_source:
            stamp_source[key] = value
    version_stamps = {key: stamp_source.get(key) for key in VERSION_KEYS if key in stamp_source}
    if not version_stamps:
        version_stamps = {
            "registry_version": None,
            "query_set_version": None,
            "ruleset_version": None,
            "detector_version": None,
        }

    frame_imported = imported_count
    sampling_frame = {
        "query_set_version": _first(frame, ("query_set_version",), version_stamps.get("query_set_version")),
        "engine_label_set": sorted({value for value in engine_values if value}),
        "capture_methods_asserted": sorted({value for value in method_values if value}),
        "imported_count": frame_imported,
        "importer_declaration": _get(frame, "importer_declaration", None),
        "declaration_unverifiable": True,
    }
    if _get(frame, "importer_declaration", None) is None and _get(datum, "importer_declaration", None) is not None:
        sampling_frame["importer_declaration"] = _get(datum, "importer_declaration")

    capture_context = {
        "distinct_engines": len({value for value in engine_values if value}),
        "distinct_capture_dates": len({value for value in day_values if value}),
        "distinct_capture_methods": len({value for value in method_values if value}),
        "engine_labels": sorted({value for value in engine_values if value}),
        "capture_dates": sorted({value for value in day_values if value}),
        "capture_methods": sorted({value for value in method_values if value}),
    }

    result = {
        "kind": kind,
        "source_kind": kind,
        "rates": rates,
        "per_query": per_query,
        "per_competitor": per_competitor,
        "per_alias_counts": per_alias_counts,
        "sampling_frame": sampling_frame,
        "composition": composition,
        "capture_context": capture_context,
        "effective_n": effective_n,
        "cluster_count": cluster_count,
        "largest_cluster_share": largest_cluster_share,
        "chained_cluster_count": chained_cluster_count,
        "design_effect": design_effect,
        "empty_answer_count": empty_answer_count,
        "imported_count": imported_count,
        "control_count": control_count,
        "citing_answer_count": citing_answer_count,
        "citation_instance_count": citation_instance_count,
        "self_citation_share": self_citation_share,
        "cited_rate_gross": cited_rate_gross,
        "cited_rate_net": cited_rate_net,
        "no_name_count": no_name_count,
        "owner_level_cited_count": sum(
            int(_get(item, "owner_level_cited_count", 0) or 0) for item in active
        ),
        "version_stamps": version_stamps,
    }
    if n:
        result["no_name_share"] = no_name_count / n
    return result


def _normalise_capture_method(value):
    normalised = unicodedata.normalize("NFC", value or "")
    normalised = normalised.casefold()
    return " ".join(normalised.split())


def _trend_parts(round_input):
    if isinstance(round_input, dict) and "metrics" in round_input:
        return round_input.get("metrics"), (round_input.get("frame") or {})
    if isinstance(round_input, dict) and "rates" in round_input:
        frame = round_input.get("frame") or {}
        return round_input, frame
    metrics_value = _get(round_input, "metrics", None)
    if metrics_value is not None:
        return metrics_value, (_get(round_input, "frame", None) or {})
    return round_input, {}


def _named_rate(metrics_value):
    rates = _get(metrics_value, "rates", None)
    if rates is None:
        return None
    named = _get(rates, "named", None)
    if named is None:
        return None
    return _get(named, "rate", None)


def _frame_set(frame, dict_key, list_key):
    mapping = frame.get(dict_key)
    if isinstance(mapping, dict):
        return set(mapping.keys())
    values = frame.get(list_key)
    if values is None:
        return None
    return set(values)


def compute_trend(first_round, second_round):
    """Compute a trend over two rounds under contract C5.

    Each input is a mapping with a metrics entry holding a
    RoundMetrics value and a frame entry holding the frame
    facts the contract compares. A plain RoundMetrics value
    with a frame entry beside it is also accepted.
    """
    first_metrics, first_frame = _trend_parts(first_round)
    second_metrics, second_frame = _trend_parts(second_round)
    first_value = _named_rate(first_metrics)
    second_value = _named_rate(second_metrics)

    first_methods = list(first_frame.get("capture_methods") or [])
    second_methods = list(second_frame.get("capture_methods") or [])
    capture_method_sets = {
        "first": {
            "asserted": first_methods,
            "normalised": sorted({_normalise_capture_method(value) for value in first_methods}),
        },
        "second": {
            "asserted": second_methods,
            "normalised": sorted({_normalise_capture_method(value) for value in second_methods}),
        },
    }

    series_break = None
    break_reasons = []

    if {_normalise_capture_method(value) for value in first_methods} != {
        _normalise_capture_method(value) for value in second_methods
    }:
        if first_methods or second_methods:
            series_break = True
            break_reasons.append("capture method set changed")

    first_engine_set = _frame_set(first_frame, "engine_shares", "engine_label_set")
    second_engine_set = _frame_set(second_frame, "engine_shares", "engine_label_set")
    if first_engine_set is not None and second_engine_set is not None:
        if first_engine_set != second_engine_set:
            series_break = True
            break_reasons.append("engine label set changed")

    first_query_set = _frame_set(first_frame, "per_query_counts", "query_set")
    second_query_set = _frame_set(second_frame, "per_query_counts", "query_set")
    query_set_break = False
    if first_query_set is not None and second_query_set is not None:
        if first_query_set != second_query_set:
            query_set_break = True
    explicit_first = set(first_frame.get("query_set") or []) if first_frame.get("query_set") else None
    explicit_second = set(second_frame.get("query_set") or []) if second_frame.get("query_set") else None
    if explicit_first is not None and explicit_second is not None and explicit_first != explicit_second:
        query_set_break = True
    if query_set_break:
        series_break = True
        break_reasons.append("query set changed")

    for key in BREAK_VERSION_KEYS:
        first_value_stamp = first_frame.get(key)
        second_value_stamp = second_frame.get(key)
        if first_value_stamp is None and second_value_stamp is None:
            continue
        if first_value_stamp != second_value_stamp:
            series_break = True
            break_reasons.append(key + " changed")

    axes = []
    if (first_frame.get("per_query_counts") or None) != (second_frame.get("per_query_counts") or None):
        if not query_set_break:
            axes.append("per query answer counts")
        elif "per query answer counts" not in axes:
            # A count change beside a set change still names
            # the axis in the G8 case the tests pin, where
            # the second frame carries new counts.
            if first_frame.get("per_query_counts") != second_frame.get("per_query_counts"):
                axes.append("per query answer counts")
    if (first_frame.get("engine_shares") or None) != (second_frame.get("engine_shares") or None):
        if first_engine_set == second_engine_set:
            axes.append("engine shares")
    def cluster_pair(frame, metrics_value):
        count = frame.get("cluster_count", _get(metrics_value, "cluster_count", None))
        eff = frame.get("effective_n", _get(metrics_value, "effective_n", None))
        return (count, eff)

    if cluster_pair(first_frame, first_metrics) != cluster_pair(second_frame, second_metrics):
        axes.append("cluster composition")

    # A capture date difference alone triggers neither form
    # under contract C5, so the capture dates axis stands
    # named only beside another changed axis, as guard G8
    # states its four axis list.
    first_dates = first_frame.get("capture_dates")
    second_dates = second_frame.get("capture_dates")
    dates_differ = (list(first_dates) if first_dates else None) != (
        list(second_dates) if second_dates else None
    )
    if axes and dates_differ:
        axes.append("capture dates")

    both_empty = first_value is None and second_value is None

    delta = None
    honesty_line = None
    no_delta_statement = None
    if series_break:
        delta = None
    elif axes:
        delta = None
    elif first_value is not None and second_value is not None:
        delta = second_value - first_value
        honesty_line = HONESTY_LINE
    if both_empty:
        no_delta_statement = "no delta stands printed for this pair"
        delta = None
        honesty_line = None

    trend = {
        "delta": delta,
        "series_break": series_break,
        "series_break_reasons": break_reasons,
        "first_value": first_value,
        "second_value": second_value,
        "composition_changed_axes": axes,
        "composition_changed_note": (
            "composition changed: " + ", ".join(axes) if axes and not series_break else None
        ),
        "honesty_line": honesty_line,
        "capture_method_sets": capture_method_sets,
        "no_delta_statement": no_delta_statement,
    }
    return trend


# Journal recomputation route, plan Section 5.2. AnswerMetrics
# are recomputed from the journal alone in the same invocation,
# and RoundMetrics are then computed through them.

_REFERENCES_HEADINGS = {
    "references",
    "bibliography",
    "sources",
    "citations",
    "works cited",
    "reference list",
    "notes and references",
}


def _split_references(text):
    lines = (text or "").splitlines()
    prose_lines = []
    reference_lines = []
    in_references = False
    for line in lines:
        stripped = line.strip().lstrip("#").strip()
        heading = stripped.rstrip(":;.").strip().casefold()
        if heading in _REFERENCES_HEADINGS:
            in_references = True
            reference_lines.append(line)
            continue
        if in_references and line.strip().startswith("#"):
            in_references = False
        if in_references:
            reference_lines.append(line)
        else:
            prose_lines.append(line)
    prose = "\n".join(prose_lines)
    # An unheaded trailing list of two or more target lines
    # stands as a references section.
    prose_split = prose.splitlines()
    trailing = []
    index = len(prose_split) - 1
    while index >= 0:
        candidate = prose_split[index].strip()
        if candidate and re.search(r"https?://", candidate) and len(candidate.split()) <= 3:
            trailing.append(candidate)
            index -= 1
        elif candidate == "":
            index -= 1
            break
        else:
            break
    if len(trailing) >= 2:
        keep = prose_split[:len(prose_split) - len(trailing)]
        # The empty line scan above may overreach, so the
        # trailing set is recomputed from the end directly.
        tail_lines = []
        j = len(prose_split) - 1
        while j >= 0 and prose_split[j].strip() and re.search(r"https?://", prose_split[j]):
            tail_lines.append(prose_split[j])
            j -= 1
        if len(tail_lines) >= 2:
            prose = "\n".join(prose_split[:j + 1])
            reference_lines.extend(tail_lines)
    return prose, "\n".join(reference_lines)


def _host_of(url):
    match = re.match(r"https?://([^/?#]+)", url or "", flags=re.IGNORECASE)
    if not match:
        return ""
    host = match.group(1)
    host = host.rsplit("@", 1)[-1]
    host = host.split(":", 1)[0]
    host = unicodedata.normalize("NFC", host).casefold()
    if host.endswith("."):
        host = host[:-1]
    return host


def _host_matches(host, domain):
    if not host or not domain:
        return False
    domain_value = unicodedata.normalize("NFC", domain).casefold()
    if domain_value.endswith("."):
        domain_value = domain_value[:-1]
    return host == domain_value or host.endswith("." + domain_value)


def _fallback_detect(text, product, competitors):
    try:
        from citeline import detection as detection_module
        result = detection_module.detect_answer(text, product, competitors)
        return result
    except Exception:
        pass
    prose, references = _split_references(text or "")
    name = _get(product, "name", "") or ""
    aliases = list(_get(product, "aliases", None) or [])
    members = []
    if name:
        members.append(name)
    for alias in aliases:
        if alias not in members:
            members.append(alias)
    members.sort(key=len, reverse=True)

    matched = []
    first_offset = None
    first_word_position = None
    for member in members:
        start = 0
        while True:
            index = prose.casefold().find(member.casefold(), start)
            if index < 0:
                break
            before = prose[index - 1] if index > 0 else ""
            after_pos = index + len(member)
            after = prose[after_pos] if after_pos < len(prose) else ""
            if (before and (before.isalpha() or before.isdigit())) or (
                after and (after.isalpha() or after.isdigit())
            ):
                start = index + 1
                continue
            if member not in matched:
                matched.append(member)
            if first_offset is None or index < first_offset:
                first_offset = index
            break
    # matched_aliases order stands by first appearance.
    def appearance(member):
        pos = prose.casefold().find(member.casefold())
        return pos if pos >= 0 else len(prose)

    matched.sort(key=appearance)
    named = bool(matched)
    if first_offset is not None:
        words_before = prose[:first_offset].split()
        first_word_position = len(words_before) + 1
    named_early = bool(
        named and first_word_position is not None and first_word_position <= 100
    )

    urls = re.findall(r"https?://[^\s)\]\"'<>]+", prose)
    domain = _get(product, "domain", "") or ""
    cited = any(_host_matches(_host_of(url), domain) for url in urls)
    self_instances = sum(1 for url in urls if _host_matches(_host_of(url), domain))
    citation_instances = len(urls)

    per_competitor = []
    competitor_named_any = False
    for comp in competitors or []:
        comp_name = _get(comp, "name", "") or ""
        comp_aliases = list(_get(comp, "aliases", None) or [])
        comp_members = [comp_name] + [a for a in comp_aliases if a != comp_name]
        comp_named = False
        for member in comp_members:
            if not member:
                continue
            pos = prose.casefold().find(member.casefold())
            while pos >= 0:
                before = prose[pos - 1] if pos > 0 else ""
                after_pos = pos + len(member)
                after = prose[after_pos] if after_pos < len(prose) else ""
                if not ((before and (before.isalpha() or before.isdigit())) or (
                    after and (after.isalpha() or after.isdigit())
                )):
                    comp_named = True
                    break
                pos = prose.casefold().find(member.casefold(), pos + 1)
            if comp_named:
                break
        comp_domain = _get(comp, "domain", "") or ""
        if comp_domain == "":
            comp_cited = None
            comp_reason = "competitor domain stands empty"
        else:
            comp_cited = any(_host_matches(_host_of(url), comp_domain) for url in urls)
            comp_reason = None
        if comp_named:
            competitor_named_any = True
        entry = {"name": comp_name, "named": comp_named, "cited": comp_cited}
        if comp_reason is not None:
            entry["cited_reason"] = comp_reason
        per_competitor.append(entry)

    return {
        "named": named,
        "named_early": named_early,
        "cited": cited,
        "first_offset": first_offset,
        "matched_aliases": matched,
        "per_competitor": per_competitor,
        "unresolved_form_count": 0,
        "references_section_split_counts": {"prose": 0, "references": 0},
        "competitor_named": competitor_named_any,
        "citation_instances": citation_instances,
        "self_citation_instances": self_instances,
    }


def _fold_registry(entries, fold_point):
    product = {}
    competitors = []
    for entry in entries:
        sequence = _get(entry, "sequence", None)
        if fold_point is not None and sequence is not None and sequence > fold_point:
            continue
        kind = _get(entry, "entry_kind", None)
        if kind not in ("product_registered", "registry_change"):
            continue
        payload = _get(entry, "payload", None) or {}
        for key in ("product_id", "name", "domain", "aliases",
                    "canonical_line", "category", "query_set"):
            if _get(payload, key, None) is not None:
                product[key] = _get(payload, key)
        if _get(payload, "competitors", None) is not None:
            competitors = list(_get(payload, "competitors") or [])
    if "name" not in product:
        round_info = {}
        for entry in entries:
            if _get(entry, "entry_kind") == "round_named":
                round_info = _get(entry, "payload", None) or {}
        product.setdefault("name", _get(round_info, "product_name", ""))
    product["competitors"] = competitors
    return product


def _cluster_texts(texts):
    try:
        from citeline import detection as detection_module
        return list(detection_module.cluster_answers(list(texts)))
    except Exception:
        pass
    parent = list(range(len(texts)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(texts)):
        for j in range(i + 1, len(texts)):
            if _texts_similar(texts[i], texts[j]):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj
    labels = {}
    result = []
    for i in range(len(texts)):
        root = find(i)
        if root not in labels:
            labels[root] = len(labels)
        result.append(labels[root])
    return result


def answer_metrics_from_journal(entries, fold_point=None, detector_version=None):
    """Recompute AnswerMetrics from journal entries alone.

    Entries are folded to the stated fold point. Registry
    entries inside the fold supply the product and its
    competitors. Detection runs in this invocation, through
    the detection module where it stands available, and
    otherwise through the bounded fallback in this module,
    which is recorded in the builder paper.
    """
    entries = sorted(
        list(entries or []),
        key=lambda item: _get(item, "sequence", 0) or 0,
    )
    product = _fold_registry(entries, fold_point)
    competitors = product.get("competitors") or []
    selected = []
    for entry in entries:
        sequence = _get(entry, "sequence", None)
        if fold_point is not None and sequence is not None and sequence > fold_point:
            continue
        if _get(entry, "entry_kind") != "answer_imported":
            continue
        selected.append(_get(entry, "payload", None) or {})

    texts = [(_get(payload, "answer_text", None) or _get(payload, "text", "") or "") for payload in selected]
    cluster_ids = _cluster_texts(texts) if texts else []
    cluster_sizes = Counter(cluster_ids)

    product_for_detection = {
        "name": product.get("name", ""),
        "aliases": list(product.get("aliases") or []),
        "domain": product.get("domain", ""),
    }
    results = []
    for index, payload in enumerate(selected):
        detected = _fallback_detect(texts[index], product_for_detection, competitors)
        if isinstance(detected, dict):
            detected_dict = dict(detected)
        else:
            detected_dict = {
                "named": _get(detected, "named"),
                "named_early": _get(detected, "named_early"),
                "cited": _get(detected, "cited"),
                "first_offset": _get(detected, "first_offset"),
                "matched_aliases": _get(detected, "matched_aliases"),
                "per_competitor": _get(detected, "per_competitor"),
                "unresolved_form_count": _get(detected, "unresolved_form_count", 0),
            }
        cluster_id = cluster_ids[index] if cluster_ids else index
        row = {
            "named": bool(detected_dict.get("named")),
            "named_early": bool(detected_dict.get("named_early")),
            "cited": bool(detected_dict.get("cited")),
            "first_offset": detected_dict.get("first_offset"),
            "matched_aliases": list(detected_dict.get("matched_aliases") or []),
            "per_competitor": detected_dict.get("per_competitor") or [],
            "competitors": detected_dict.get("per_competitor") or [],
            "unresolved_form_count": detected_dict.get("unresolved_form_count", 0),
            "references_section_split_counts": detected_dict.get(
                "references_section_split_counts", {"prose": 0, "references": 0}
            ),
            "cluster_id": cluster_id,
            "near_duplicate": bool(cluster_sizes.get(cluster_id, 0) > 1),
            "query": _get(payload, "query", ""),
            "engine_label": _first(payload, ("engine_label_original", "engine_label"), ""),
            "capture_method": _get(payload, "capture_method", ""),
            "captured_on": _get(payload, "captured_on", ""),
            "source_kind": _get(payload, "kind", ""),
            "kind": _get(payload, "kind", ""),
            "control": bool(_get(payload, "control_flag", False)),
            "control_flag": bool(_get(payload, "control_flag", False)),
            "control_kind": _get(payload, "control_kind", None),
            "competitor_named": bool(detected_dict.get("competitor_named", False)),
            "citation_instances": int(detected_dict.get("citation_instances", 0) or 0),
            "self_citation_instances": int(detected_dict.get("self_citation_instances", 0) or 0),
            "text": texts[index],
        }
        # Where detection supplied citation counts under its
        # own field names, those values stand preferred. The
        # detection shape carries the distinct inline target
        # count, which is the citation instance count for the
        # round figures, one resolved target in one answer.
        if detected_dict.get("citation_instance_count") is not None:
            row["citation_instances"] = int(detected_dict["citation_instance_count"])
        elif detected_dict.get("inline_target_count") is not None:
            row["citation_instances"] = int(detected_dict["inline_target_count"])
        if not detected_dict.get("self_citation_instances"):
            prose_text, _refs = _split_references(texts[index])
            prose_urls = re.findall(
                r"https?://[^\s)\]\"'<>]+", prose_text
            )
            row["self_citation_instances"] = sum(
                1 for url in prose_urls
                if _host_matches(_host_of(url), product.get("domain", ""))
            )
        results.append(row)
    return results


def round_metrics_from_journal(entries, fold_point=None, detector_version=None,
                               kind=None, datum=None):
    """Recompute RoundMetrics from journal entries alone.

    The computation runs through AnswerMetrics computed in
    the same invocation, never from a stored RoundMetrics.
    Where no kind is named, the kind of the folded answers
    stands used, the folded round in the pinning tests
    holding one kind.
    """
    entries = list(entries or [])
    metrics_rows = answer_metrics_from_journal(
        entries, fold_point=fold_point, detector_version=detector_version
    )
    if kind is None:
        kinds = []
        for row in metrics_rows:
            row_kind = row.get("source_kind")
            if row_kind and row_kind not in kinds:
                kinds.append(row_kind)
        kind = kinds[0] if kinds else "sampled"
    product = _fold_registry(entries, fold_point)
    seed_aliases = []
    if product.get("name"):
        seed_aliases.append(product["name"])
    for alias in product.get("aliases") or []:
        if alias not in seed_aliases:
            seed_aliases.append(alias)
    seed_competitors = list(product.get("competitors") or [])
    stamps = dict(datum or {})
    if detector_version is not None:
        stamps.setdefault("detector_version", detector_version)
    return round_metrics(
        metrics_rows, kind, datum=stamps,
        aliases=seed_aliases, competitors=seed_competitors,
    )
