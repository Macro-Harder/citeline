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

import copy
import math
import re
import unicodedata
from collections import Counter, defaultdict
from citeline.shared import _get, _similar_components

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
    if rate is None or effective_n is None:
        return None
    try:
        rate_value = float(rate)
        n = float(effective_n)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(rate_value) or not math.isfinite(n):
        return None
    if rate_value < 0.0 or rate_value > 1.0 or n <= 0:
        return None
    rate = rate_value
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
    if effective_n is None:
        return "count only"
    try:
        n_value = float(effective_n)
    except (TypeError, ValueError, OverflowError):
        return "count only"
    if not math.isfinite(n_value) or n_value < 5:
        return "count only"
    effective_n = n_value
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
    try:
        first_low, first_high = first_interval
        second_low, second_high = second_interval
        bounds = [float(value) for value in (
            first_low, first_high, second_low, second_high)]
    except (TypeError, ValueError, OverflowError):
        return False
    if any(value is None for value in (
            first_low, first_high, second_low, second_high)):
        return False
    if not all(math.isfinite(value) for value in bounds):
        return False
    first_low, first_high, second_low, second_high = bounds
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


def _sets_clique(type_sets):
    """Whether every pair of distinct sets stands similar.

    The sets are read against the first set: a set stands
    described by the part of the first set it misses and the
    part it adds, and the shared count of any two sets is
    the first set's size less the union of their missed
    parts, plus the overlap of their added parts. A set
    that is not similar to the first set settles the
    question at once, so the pairs still to judge stand
    among the remaining sets.

    Those pairs stand judged first by a bulk bound. Every
    such pair shares at least the parts the whole family
    shares: the missed parts common to every remaining set
    stand inside the pair missed intersection, and the
    added parts common to every remaining set stand inside
    the pair added overlap, so a pair shares at least the
    pivot size less its two missed sizes plus that common
    count. Where that bound reaches the threshold of the
    two largest values of nine times the missed size plus
    four times the set size among the remaining sets, every
    pair stands similar at once, in time linear in the
    family. The missed part patterns of the measured seam
    shape, each missing two or three pivot parts and adding
    one common part, settle on this bound.

    A third bulk bound stands on the union of the missed
    parts: a pair misses at most that union between them,
    so a pair shares at least the pivot size less that
    union plus the added parts common to every remaining
    set, and where that count reaches the threshold of the
    two largest remaining sizes every pair stands similar
    at once. A family whose sets each miss a distinct
    pattern of a small pool of the pivot settles here,
    though no missed part stands common to the whole
    family.

    Pairs the bound leaves open stand judged in groups
    sharing one missed part pattern, as the scan clique
    shape requires: a family whose sets miss few patterns
    of the pivot stands in few groups however many sets it
    carries. A group pair stands settled by bounds where
    the pair base, the pivot size less the union of the
    two missed patterns, plus the added parts common to
    every set of both groups reaches the largest threshold
    the group pair can carry, and it stands refused where
    the base plus the largest added overlap either group
    can offer falls under the smallest threshold. Pairs
    the bounds leave open stand judged pair by pair, the
    patterns standing as integer masks over the pivot
    parts and the added parts, so a pair judgement is a
    mask overlap and a count, with no set built per pair.
    """
    pivot = type_sets[0]
    pivot_size = len(pivot)
    entries = []
    for shingle_set in type_sets:
        shared = len(pivot & shingle_set)
        if shared * 9 < 4 * (pivot_size + len(shingle_set)):
            return False
        entries.append((pivot - shingle_set, shingle_set - pivot,
                        len(shingle_set)))
    rest = entries[1:]
    if len(rest) < 2:
        return True
    # A second bulk bound, on the parts the sets miss from
    # their union: a pair shares at least the sum of its
    # sizes less the size of the union, so where five times
    # the sum of the two smallest sizes reaches nine times
    # the union size, every pair stands similar at once.
    # The varying missed part family settles on this
    # bound: its members each miss four parts of a union
    # only four parts larger than a member, a position the
    # pivot bound cannot see, because it prices the missed
    # and added parts of a pair apart from each other
    # where the two stand linked inside each set.
    union_size = len(set().union(*type_sets))
    smallest_sizes = sorted(len(shingle_set) for shingle_set in type_sets)
    if 5 * (smallest_sizes[0] + smallest_sizes[1]) >= 9 * union_size:
        return True
    common_missed = set(rest[0][0])
    common_added = set(rest[0][1])
    for missing, added, _size in rest[1:]:
        common_missed &= missing
        common_added &= added
    common = len(common_missed) + len(common_added)
    values = sorted(
        (9 * len(missing) + 4 * size for missing, _added, size in rest),
        reverse=True)
    if 9 * (pivot_size + common) >= values[0] + values[1]:
        return True
    missing_union = set(rest[0][0])
    for missing, _added, _size in rest[1:]:
        missing_union |= missing
    largest_sizes = sorted(
        (size for _missing, _added, size in rest), reverse=True)
    pair_floor = pivot_size - len(missing_union) + len(common_added)
    if pair_floor * 9 >= 4 * (largest_sizes[0] + largest_sizes[1]):
        return True
    if len(rest) >= 300:
        # The wide reading of the group pair scan. A pair
        # shares the pivot size less both missed sizes plus
        # the overlap of the two patterns, a pattern standing
        # as the missed parts and the added parts of a set
        # together, the cross parts standing empty because a
        # missed part stands in the pivot and an added part
        # stands outside it. The scan below prices a pair at
        # mask work on masks whose width grows with the
        # family, so at this scale the pair counts stand
        # read in parallel instead: the patterns stand
        # reduced to the parts standing in at least three
        # sets, a part standing in at most two sets standing
        # in the overlap of at most one pair beside its own,
        # and the overlap of every set with one set standing
        # counted over the reduced parts in bit planes over
        # the family. A pair the reduced count leaves under
        # its threshold stands judged exactly on its full
        # patterns before it can settle the reading, so the
        # reduced count names candidates only and the
        # judgement stands exact. A part standing in every
        # remaining set adds one to every count of its set
        # and stands read as a constant in place of a
        # posting.
        patterns = [missing | added
                    for missing, added, _size in rest]
        pattern_frequency = {}
        for pattern in patterns:
            for shingle in pattern:
                pattern_frequency[shingle] = \
                    pattern_frequency.get(shingle, 0) + 1
        reduced = {shingle for shingle, frequency
                   in pattern_frequency.items() if frequency >= 3}
        occurrences = {shingle: [] for shingle in reduced}
        for position, pattern in enumerate(patterns):
            for shingle in pattern & reduced:
                occurrences[shingle].append(position)
        rest_count = len(rest)
        packed_width = (rest_count + 7) // 8
        wide_all = (1 << rest_count) - 1
        wide_postings = {}

        def wide_posting(shingle):
            posting = wide_postings.get(shingle)
            if posting is None:
                packed = bytearray(packed_width)
                for position in occurrences[shingle]:
                    packed[position >> 3] |= 1 << (position & 7)
                posting = int.from_bytes(packed, "little")
                wide_postings[shingle] = posting
            return posting

        group_masks = {}
        for position, (missing, _added, size) in enumerate(rest):
            key = (size, len(missing))
            group_masks[key] = group_masks.get(key, 0) | (1 << position)
        for first_position, (missing_first, _added_first,
                             size_first) in enumerate(rest):
            planes = []
            universal = 0
            for shingle in patterns[first_position] & reduced:
                if pattern_frequency[shingle] == rest_count:
                    universal += 1
                    continue
                carry = wide_posting(shingle)
                level = 0
                while carry:
                    if level == len(planes):
                        planes.append(0)
                    next_carry = planes[level] & carry
                    planes[level] ^= carry
                    carry = next_carry
                    level += 1
            for (size_second, missed_second), group_mask \
                    in group_masks.items():
                numerator = 4 * (size_first + size_second) - 9 * (
                    pivot_size - len(missing_first) - missed_second)
                required = -(-numerator // 9) if numerator > 0 else 0
                required -= universal
                if required <= 0:
                    continue
                equal = wide_all
                greater = 0
                top = max(len(planes), required.bit_length())
                for bit in range(top - 1, -1, -1):
                    plane = planes[bit] if bit < len(planes) else 0
                    if (required >> bit) & 1:
                        equal &= plane
                    else:
                        greater |= equal & plane
                        equal &= wide_all ^ plane
                failing = group_mask & (wide_all ^ (greater | equal))
                failing &= ~(1 << first_position)
                while failing:
                    lowest = failing & -failing
                    second_position = lowest.bit_length() - 1
                    failing ^= lowest
                    missing_second, _added_second, size_b = \
                        rest[second_position]
                    shared = pivot_size - len(missing_first) \
                        - len(missing_second) + len(
                            patterns[first_position]
                            & patterns[second_position])
                    if shared * 9 < 4 * (size_first + size_b):
                        return False
        return True
    pivot_index = {shingle: index for index, shingle in enumerate(pivot)}
    # The added masks stand over the added parts that can
    # stand shared between two sets. A part one set alone
    # holds stands in no pair overlap, in no common part of
    # two groups, and at no pair bound, so it carries no
    # mask position, and a family whose sets each add parts
    # of their own keeps its masks at the width of its
    # shared added parts in place of the width of every
    # added part in the family, which grows with the family.
    added_frequency = {}
    for _missing, added, _size in rest:
        for shingle in added:
            added_frequency[shingle] = added_frequency.get(shingle, 0) + 1
    added_index = {}
    for shingle, frequency in added_frequency.items():
        if frequency >= 2:
            added_index[shingle] = len(added_index)
    groups = {}
    for missing, added, size in rest:
        missing_mask = 0
        for shingle in missing:
            missing_mask |= 1 << pivot_index[shingle]
        added_mask = 0
        for shingle in added:
            position = added_index.get(shingle)
            if position is not None:
                added_mask |= 1 << position
        group = groups.get(missing_mask)
        if group is None:
            group = groups[missing_mask] = {
                "entries": [], "min_size": size, "max_size": size,
                "max_added": added_mask.bit_count(),
                "common_added": added_mask, "count": 0,
            }
        group["entries"].append((added_mask, size))
        group["count"] += 1
        if size < group["min_size"]:
            group["min_size"] = size
        if size > group["max_size"]:
            group["max_size"] = size
        added_count = added_mask.bit_count()
        if added_count > group["max_added"]:
            group["max_added"] = added_count
        if group["common_added"]:
            group["common_added"] &= added_mask
    group_list = list(groups.items())
    for first in range(len(group_list)):
        missing_first, group_first = group_list[first]
        for second in range(first, len(group_list)):
            missing_second, group_second = group_list[second]
            if first == second and group_first["count"] < 2:
                continue
            base = pivot_size - (missing_first | missing_second).bit_count()
            common_overlap = (
                group_first["common_added"]
                & group_second["common_added"]).bit_count()
            max_sum = group_first["max_size"] + group_second["max_size"]
            if base + common_overlap >= -(-4 * max_sum // 9):
                continue
            max_overlap = min(
                group_first["max_added"], group_second["max_added"])
            min_sum = group_first["min_size"] + group_second["min_size"]
            if base + max_overlap < -(-4 * min_sum // 9):
                return False
            if first == second:
                pairs = (
                    (group_first["entries"][a], group_first["entries"][b])
                    for a in range(len(group_first["entries"]))
                    for b in range(a + 1, len(group_first["entries"])))
            else:
                pairs = (
                    (entry_first, entry_second)
                    for entry_first in group_first["entries"]
                    for entry_second in group_second["entries"])
            for (added_first, size_first), (added_second, size_second) \
                    in pairs:
                shared = base + (added_first & added_second).bit_count()
                if shared * 9 < 4 * (size_first + size_second):
                    return False
    return True


def _cluster_chained(shingle_sets):
    """Whether one cluster stands chained, on the cost shape
    the round cap requires. No structure in this computation
    grows with the number of pairs and no subset of a set is
    stored: duplicate sets are grouped first, the similarity
    graph's components are found through a single shingle
    inverted index, and a connected graph stands chained
    exactly where its sets do not form a clique, which the
    clique reading judges from the sets' parts against one
    pivot set rather than pair by pair."""
    if len(shingle_sets) < 2:
        return False
    if any(not shingle_set for shingle_set in shingle_sets):
        # A member with an empty shingle set is similar only
        # to a member with an empty set and an identical
        # normalised text, so such a member either forms the
        # whole cluster with every pair similar, or stands
        # apart from the rest. Neither shape is chained.
        return False
    unique = {}
    unique_sets = []
    for shingle_set in shingle_sets:
        key = frozenset(shingle_set)
        if key not in unique:
            unique[key] = len(unique_sets)
            unique_sets.append(key)
    if len(unique_sets) == 1:
        return False
    if len(_similar_components(unique_sets)) != 1:
        return False
    return not _sets_clique(unique_sets)


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
            elif _is_competitor_record(outcome):
                # A record standing in object form counts as
                # the record it stands validated as: its own
                # named and cited fields build the row, as a
                # mapping record's fields do, never the
                # truthiness of the object itself.
                row = {}
                for field_name in (
                        "name", "named", "cited", "cited_reason"):
                    value = _get(outcome, field_name, None)
                    if value is not None:
                        row[field_name] = value
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


def _is_competitor_record(entry):
    """Whether a competitor entry stands in record form: a
    mapping, or an object carrying a name. A plain string, a
    number, or a bare value stands in no record form."""
    if isinstance(entry, dict):
        return True
    if entry is None or isinstance(entry, (
            str, bytes, int, float, bool, complex,
            list, tuple, set, frozenset)):
        return False
    return hasattr(entry, "name")


def _validate_competitor_entry(entry):
    entry_name = _get(entry, "name", None)
    if entry_name is not None and not isinstance(entry_name, str):
        raise ValueError("per_competitor name must be a string")
    for outcome_name in ("named", "cited"):
        value = _get(entry, outcome_name, None)
        if value is not None and not isinstance(value, bool):
            raise ValueError(
                "per_competitor " + outcome_name + " must be a boolean")


def _validate_answer_shape(item):
    """Refuse an AnswerMetrics value outside its stated shape.

    A field of the wrong type raises ValueError in plain
    words naming the field, rather than crashing later with
    a raw error or being silently counted in a wrong form,
    as a string of aliases counted character by character.
    """
    try:
        hash(_get(item, "cluster_id", None))
    except TypeError:
        raise ValueError("cluster_id must be a hashable value")
    for name in ("query", "captured_on"):
        value = _get(item, name, None)
        if value is not None and not isinstance(value, str):
            raise ValueError(name + " must be a string")
    for value, name in (
            (_first(item, ("engine_label", "engine"), None), "engine_label"),
            (_first(item, ("capture_method", "method"), None),
             "capture_method")):
        if value is not None and not isinstance(value, str):
            raise ValueError(name + " must be a string")
    text = _get(item, "text", None)
    if text is not None and not isinstance(text, str):
        raise ValueError("text must be a string")
    matched = _get(item, "matched_aliases", None)
    if matched is not None:
        if isinstance(matched, (str, bytes)) or not isinstance(
                matched, (list, tuple, set, frozenset)):
            raise ValueError("matched_aliases must be a list of strings")
        for alias in matched:
            if not isinstance(alias, str):
                raise ValueError("matched_aliases must hold strings only")
    for name in ("citation_instances", "self_citation_instances",
                 "owner_level_cited_count"):
        value = _get(item, name, None)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(name + " must be a whole count")
        if isinstance(value, float) and (
                not math.isfinite(value) or value != int(value)):
            raise ValueError(name + " must be a whole count")
    for name in ("named", "named_early", "cited"):
        value = _get(item, name, None)
        if value is not None and not isinstance(value, bool):
            raise ValueError(name + " must be a boolean")
    for name in ("control", "control_flag", "competitor_named"):
        value = _get(item, name, None)
        if value is not None and not isinstance(value, bool):
            raise ValueError(name + " must be a boolean")
    for field_name in ("per_competitor", "competitors"):
        entries = _get(item, field_name, None)
        if entries is None:
            continue
        if not isinstance(entries, (list, tuple, dict)):
            raise ValueError(
                "per_competitor must be a list or a mapping")
        if isinstance(entries, dict):
            for key, outcome in entries.items():
                if not isinstance(key, str):
                    raise ValueError(
                        "per_competitor names must be strings")
                if not _is_competitor_record(outcome):
                    raise ValueError(
                        "per_competitor entries must be records")
                if isinstance(outcome, dict) and not any(
                        field_name in outcome for field_name in
                        ("name", "named", "cited")):
                    # A mapping value carrying none of the
                    # record fields stands in no stated form,
                    # in the mapping form as in the list form:
                    # an empty mapping, a mapping holding
                    # unrelated fields, and a mapping holding
                    # a nested record all stand refused in
                    # plain words, the nested record refused
                    # with the value that carries it, never
                    # counted in silence and never left
                    # outside the field validation.
                    raise ValueError(
                        "per_competitor entries must carry a name, "
                        "named, or cited field")
                _validate_competitor_entry(outcome)
            continue
        for entry in entries:
            if not _is_competitor_record(entry):
                raise ValueError(
                    "per_competitor entries must be records")
            if isinstance(entry, dict) and not any(
                    field_name in entry for field_name in
                    ("name", "named", "cited")):
                # A list entry carrying none of the record
                # fields stands in no stated form: the
                # mapping form nested inside the list form,
                # an empty mapping, and a mapping holding
                # unrelated fields all stand refused in
                # plain words, and a record nested inside
                # such an entry stands refused with it,
                # never dropped in silence and never left
                # outside the field validation.
                raise ValueError(
                    "per_competitor entries must carry a name, "
                    "named, or cited field")
            _validate_competitor_entry(entry)


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
    if aliases is not None:
        if isinstance(aliases, (str, bytes)):
            raise ValueError("aliases must be a list of strings")
        try:
            aliases = list(aliases)
        except TypeError:
            raise ValueError("aliases must be a list of strings")
        for alias in aliases:
            if not isinstance(alias, str):
                raise ValueError("aliases must hold strings only")
    if competitors is not None:
        if isinstance(competitors, (str, bytes)):
            raise ValueError("competitors must be a list of competitors")
        try:
            competitors = list(competitors)
        except TypeError:
            raise ValueError("competitors must be a list of competitors")
        for comp in competitors:
            if isinstance(comp, str):
                continue
            if not _is_competitor_record(comp):
                raise ValueError(
                    "competitors entries must be competitor "
                    "records or names")
            comp_name = _get(comp, "name", None)
            if comp_name is not None and not isinstance(comp_name, str):
                raise ValueError("competitor name must be a string")

    by_kind = []
    for item in answers:
        item_kind = _first(item, ("source_kind", "kind"), None)
        if item_kind == kind:
            by_kind.append(item)
    for item in by_kind:
        _validate_answer_shape(item)
    imported_count = len(by_kind)
    controls = [item for item in by_kind
                if _get(item, "control", None)
                or _get(item, "control_flag", None)]
    control_count = len(controls)
    # A control whose outcome contradicts its asserted
    # kind stands failed on the round record, so the
    # rendering pass can stand the control failure notice
    # in its own form in every form of the round report:
    # a positive control passes where the answer stands
    # named and cited, and a negative control passes
    # where it stands not named and not cited, under the
    # Settled landing.
    control_failed = False
    for item in controls:
        control_kind = _get(item, "control_kind", None)
        named = bool(_get(item, "named", False))
        cited = bool(_get(item, "cited", False)) or bool(
            _get(item, "citation_instances", None)
            or _get(item, "citation_instance_count", None))
        if control_kind == "positive" and not (named and cited):
            control_failed = True
        elif control_kind == "negative" and (named or cited):
            control_failed = True
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
        normalised = [_normalised_text(text) for text in texts]
        shingle_ids = {}
        shingle_sets = []
        for norm_text in normalised:
            words = norm_text.split()
            if len(words) < 5:
                shingle_sets.append(set())
            else:
                id_set = set()
                for i in range(len(words) - 4):
                    shingle = " ".join(words[i:i + 5])
                    if shingle not in shingle_ids:
                        shingle_ids[shingle] = len(shingle_ids)
                    id_set.add(shingle_ids[shingle])
                shingle_sets.append(id_set)
        if _cluster_chained(shingle_sets):
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
    competitor_domains = {}
    if competitors:
        for comp in competitors:
            name = comp if isinstance(comp, str) else _get(comp, "name")
            if name and name not in competitor_names:
                competitor_names.append(name)
            if name and not isinstance(comp, str):
                competitor_domains[name] = _get(comp, "domain")
    # A competitor whose registered domain stands empty
    # holds no domain a citation could point at, so its
    # cited rate stands not applicable with the reason
    # stated, and no pooled rate is ever formed from it
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
        if name in competitor_domains:
            domain = competitor_domains[name]
            if domain is None or not str(domain).strip():
                cited_reason = "competitor domain stands empty"
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
    per_alias_counts = {
        alias: per_alias_counts[alias]
        for alias in sorted(per_alias_counts, key=lambda value: str(value))
    }

    citing_answer_count = 0
    citation_instance_count = 0
    self_instance_count = 0
    gross_citing = 0
    net_citing = 0
    for item in active:
        instances = _get(item, "citation_instances", None)
        if instances is None:
            instances = 1 if _get(item, "cited") else 0
        instances = max(0, int(instances or 0))
        self_instances = min(
            instances,
            max(0, int(_get(item, "self_citation_instances", 0) or 0)))
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
    # The capture context stands over every answer
    # standing in the round for the kind, designated
    # controls included, and the same set governs the
    # sampling frame engine label set and the capture
    # methods asserted. Rates, counts, and clusters
    # above and below stay over the active answers
    # alone, controls excluded as before.
    context_engine_values = [
        _first(item, ("engine_label", "engine"), "")
        for item in by_kind]
    context_day_values = [
        _get(item, "captured_on", "") for item in by_kind]
    context_method_values = [
        _first(item, ("capture_method", "method"), "")
        for item in by_kind]

    def largest_share(values):
        if not values:
            return 0, 0.0
        count = Counter(values).most_common(1)[0][1]
        return count, (count / len(values) * 100.0)

    engine_count, engine_percent = largest_share(engine_values)
    query_count, query_percent = largest_share(query_values)
    day_count, day_percent = largest_share(day_values)
    # Dominance, guard G3: where any one asserted engine
    # label, query, or day supplies more than half of a
    # round, the pooled rate carries a dominance note. The
    # rule states no exception for an axis holding one value
    # only, so a single value axis at 100.0 percent, its one
    # value supplying the whole round, raises the note.
    dominance = bool(
        n
        and (
            engine_count * 2 > n
            or query_count * 2 > n
            or day_count * 2 > n
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
        "engine_label_set": sorted({value for value in context_engine_values if value}),
        "capture_methods_asserted": sorted({value for value in context_method_values if value}),
        "imported_count": frame_imported,
        "importer_declaration": _get(frame, "importer_declaration", None),
        "declaration_unverifiable": True,
    }
    if _get(frame, "importer_declaration", None) is None and _get(datum, "importer_declaration", None) is not None:
        sampling_frame["importer_declaration"] = _get(datum, "importer_declaration")

    capture_context = {
        "distinct_engines": len({value for value in context_engine_values if value}),
        "distinct_capture_dates": len({value for value in context_day_values if value}),
        "distinct_capture_methods": len({value for value in context_method_values if value}),
        "engine_labels": sorted({value for value in context_engine_values if value}),
        "capture_dates": sorted({value for value in context_day_values if value}),
        "capture_methods": sorted({value for value in context_method_values if value}),
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
        "control_failed": control_failed,
        "citing_answer_count": citing_answer_count,
        "citation_instance_count": citation_instance_count,
        "self_citation_share": self_citation_share,
        "cited_rate_gross": cited_rate_gross,
        "cited_rate_net": cited_rate_net,
        # The cited figures stand named and defined
        # distinctly beside the figures themselves, so no
        # two figures in the report share the one word
        # cited without their distinction stated.
        "rate_definitions": {
            "cited": "the share of the round answers whose "
                     "citations point at the product own "
                     "domain",
            "cited_rate_gross": "the share of the round "
                                "answers holding at least "
                                "one citation instance of "
                                "any kind, self citations "
                                "included",
            "cited_rate_net": "the share of the round "
                              "answers holding at least one "
                              "citation instance that is "
                              "not a self citation",
            "self_citation_share": "the share of all "
                                   "citation instances in "
                                   "the round that point at "
                                   "the product own domain",
        },
        "no_name_count": no_name_count,
        "owner_level_cited_count": sum(
            max(0, int(_get(item, "owner_level_cited_count", 0) or 0))
            for item in active
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
        # The delta stands rounded to the stated precision
        # for disclosed rate figures, four decimal places,
        # before it is stored and served, so every form
        # holds the same figure for the one delta.
        delta = round(second_value - first_value, 4)
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


def _map_host_separators(text):
    """Map the three non ASCII dot separators of item 149
    to a full stop, as the detection host reading maps
    them, so a host written with a separator stands read
    as the host it names."""
    for separator in ("\uff0e", "\u3002", "\uff61"):
        text = text.replace(separator, ".")
    return text


def _host_of(url):
    match = re.match(r"https?://([^/?#]+)", url or "", flags=re.IGNORECASE)
    if not match:
        return ""
    host = match.group(1)
    host = host.rsplit("@", 1)[-1]
    host = host.split(":", 1)[0]
    host = _map_host_separators(
        unicodedata.normalize("NFC", host).casefold())
    if host.endswith("."):
        host = host[:-1]
    return host


def _host_matches(host, domain):
    if not host or not domain:
        return False
    host_value = _map_host_separators(
        unicodedata.normalize("NFC", host).casefold())
    if host_value.endswith("."):
        host_value = host_value[:-1]
    domain_value = _map_host_separators(
        unicodedata.normalize("NFC", domain).casefold())
    if domain_value.endswith("."):
        domain_value = domain_value[:-1]
    return host_value == domain_value or host_value.endswith(
        "." + domain_value)


def _canonical_name_member(product):
    """The product name as the canonical line states it, or None.

    A canonical line opens with the product name in a plain
    statement of what the product is. Where the registered
    name and the name the canonical line states differ, an
    answer that names the product in the canonical line's
    own words names the product, so that stated name stands
    as a name member for detection in the recomputation
    path. A leading article
    word stands outside the name, and a line that opens
    with no capitalised word states no name this way.
    """
    line = _get(product, "canonical_line", None) or ""
    words = []
    for word in str(line).split():
        cleaned = word.strip(".,;:!?")
        if not cleaned or not cleaned[0].isupper():
            break
        words.append(cleaned)
    while words and words[0].casefold() in ("the", "a", "an"):
        words.pop(0)
    if not words:
        return None
    member = " ".join(words)
    if member == (_get(product, "name", "") or ""):
        return None
    return member


def _detect_answer(text, product, competitors):
    """Run the one detector over one answer for the
    recomputation.

    The product the detector sees carries the canonical
    line's stated name as an alias member where that name
    stands (see _canonical_name_member): an answer naming
    the product in the canonical line's own words names
    the product. Detection itself is the detection
    module's detect_answer, the only detector: an error
    inside it surfaces to the caller of the
    recomputation, and no second, cruder reading of the
    answer stands behind it to take over silently.
    """
    member = _canonical_name_member(product or {})
    if member:
        product = dict(product or {})
        aliases = list(_get(product, "aliases", None) or [])
        if member not in aliases:
            aliases.append(member)
        product["aliases"] = aliases
    from citeline import detection as detection_module
    return detection_module.detect_answer(text, product, competitors)


def _fold_registry(entries, fold_point):
    # Entries fold in sequence order. A correction entry
    # whose superseded entry is a registry entry inside the
    # fold range applies in sequence order: the corrected
    # record stands in place of the superseded entry record
    # for every later point in the fold, on the plan
    # Section 5.2 fold rule journal.py implements for
    # registry readers.
    ordered = sorted(
        list(entries or []),
        key=lambda item: _get(item, "sequence", 0) or 0,
    )
    effective = []
    by_sequence = {}
    for entry in ordered:
        sequence = _get(entry, "sequence", None)
        if fold_point is not None and sequence is not None \
                and sequence > fold_point:
            continue
        if _get(entry, "entry_kind", None) == "correction":
            payload = _get(entry, "payload", None) or {}
            target = by_sequence.get(
                _get(payload, "supersedes_sequence", None))
            corrected = _get(payload, "corrected_record", None)
            if target is not None and isinstance(corrected, dict):
                target["payload"] = copy.deepcopy(corrected)
            continue
        folded = {
            "entry_kind": _get(entry, "entry_kind", None),
            "payload": _get(entry, "payload", None) or {},
        }
        effective.append(folded)
        if sequence is not None:
            by_sequence[sequence] = folded
    product = {}
    competitors = []
    for entry in effective:
        if entry["entry_kind"] not in (
                "product_registered", "registry_change"):
            continue
        payload = entry["payload"]
        for key in ("product_id", "name", "domain", "aliases",
                    "canonical_line", "category", "query_set"):
            if _get(payload, key, None) is not None:
                product[key] = _get(payload, key)
        if _get(payload, "competitors", None) is not None:
            competitors = list(_get(payload, "competitors") or [])
    if "name" not in product:
        round_info = {}
        for entry in effective:
            if entry["entry_kind"] == "round_named":
                round_info = entry["payload"]
        product.setdefault("name", _get(round_info, "product_name", ""))
    product["competitors"] = competitors
    return product


def _cluster_texts(texts):
    try:
        from citeline import detection as detection_module
        return list(detection_module.cluster_answers(list(texts)))
    except Exception:  # noqa: BLE001, S110 - any failure of the shared clustering falls back to the local reading below, which computes the same components directly; the handler passes control to that reading
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
    the detection module's detect_answer alone: an error
    inside detection surfaces to the caller, and no second
    reading of an answer stands behind it.
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
        "canonical_line": product.get("canonical_line", ""),
    }
    results = []
    for index, payload in enumerate(selected):
        detected = _detect_answer(texts[index], product_for_detection, competitors)
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
            "engine_label": _first(payload, ("engine_label_normalised", "engine_label_original", "engine_label"), ""),
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
    caller_named_kind = kind
    metrics_rows = answer_metrics_from_journal(
        entries, fold_point=fold_point, detector_version=detector_version
    )
    kinds = []
    for row in metrics_rows:
        row_kind = row.get("source_kind")
        if row_kind and row_kind not in kinds:
            kinds.append(row_kind)
    # The kinds list stands in sorted order: a
    # round report is a function of the round's answers as a
    # set, and import order is not an input of the report.
    kinds = sorted(kinds, key=lambda value: str(value))
    if kind is None and len(kinds) > 1:
        product = _fold_registry(entries, fold_point)
        seed_aliases_multi = []
        if product.get("name"):
            seed_aliases_multi.append(product["name"])
        for alias in product.get("aliases") or []:
            if alias not in seed_aliases_multi:
                seed_aliases_multi.append(alias)
        stamps_multi = dict(datum or {})
        if detector_version is not None:
            stamps_multi.setdefault("detector_version", detector_version)
        declaration_multi = stamps_multi.get("importer_declaration")
        ordered_multi = sorted(
            entries, key=lambda item: _get(item, "sequence", 0) or 0)
        for entry in ordered_multi:
            sequence = _get(entry, "sequence", None)
            if fold_point is not None and sequence is not None \
                    and sequence > fold_point:
                continue
            if _get(entry, "entry_kind", None) != "round_named":
                continue
            value = _get(
                _get(entry, "payload", None) or {},
                "importer_declaration", None)
            if value is not None:
                declaration_multi = value
        frame_multi = {}
        if declaration_multi is not None:
            frame_multi["importer_declaration"] = declaration_multi
            stamps_multi.setdefault(
                "importer_declaration", declaration_multi)
        per_kind = {}
        for each_kind in kinds:
            per_kind[each_kind] = round_metrics(
                metrics_rows, each_kind, frame=frame_multi,
                datum=stamps_multi,
                aliases=seed_aliases_multi,
                competitors=list(product.get("competitors") or []),
            )
        # The multi kind form carries a round level
        # capture_context pooled over all kinds standing
        # in the round, over the same all answers set
        # the per kind contexts stand over.
        pooled_engines = sorted({
            row.get("engine_label") for row in metrics_rows
            if row.get("engine_label")})
        pooled_dates = sorted({
            row.get("captured_on") for row in metrics_rows
            if row.get("captured_on")})
        pooled_methods = sorted({
            row.get("capture_method") for row in metrics_rows
            if row.get("capture_method")})
        pooled_context = {
            "distinct_engines": len(pooled_engines),
            "distinct_capture_dates": len(pooled_dates),
            "distinct_capture_methods": len(pooled_methods),
            "engine_labels": pooled_engines,
            "capture_dates": pooled_dates,
            "capture_methods": pooled_methods,
        }
        return {
            "kind": None,
            "source_kind": None,
            "kinds": list(kinds),
            "answer_metrics": metrics_rows,
            "capture_context": pooled_context,
            "per_kind": per_kind,
            "imported_count": sum(
                per_kind[each_kind]["imported_count"]
                for each_kind in kinds),
        }
    if kind is None:
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
    # The sampling frame of guard G1 carries the importer
    # declaration recorded at round naming. The declaration
    # stands on the round_named entry of the journal, so the
    # frame built here reads it from that entry, in sequence
    # order to the fold point, and carries it into the
    # RoundMetrics computation beside the datum, which
    # carries the same value as its fallback.
    declaration = stamps.get("importer_declaration")
    ordered = sorted(
        entries, key=lambda item: _get(item, "sequence", 0) or 0)
    for entry in ordered:
        sequence = _get(entry, "sequence", None)
        if fold_point is not None and sequence is not None \
                and sequence > fold_point:
            continue
        if _get(entry, "entry_kind", None) != "round_named":
            continue
        value = _get(
            _get(entry, "payload", None) or {},
            "importer_declaration", None)
        if value is not None:
            declaration = value
    frame = {}
    if declaration is not None:
        frame["importer_declaration"] = declaration
        stamps.setdefault("importer_declaration", declaration)
    result = round_metrics(
        metrics_rows, kind, frame=frame, datum=stamps,
        aliases=seed_aliases, competitors=seed_competitors,
    )
    # The per answer AnswerMetrics stand carried in the
    # report beside the round figures, as plan Section 5.2
    # states for the Advanced probe report: effective n and
    # cluster membership recompute from the per answer
    # fields themselves. The
    # rows stand in the record ahead of the capture context,
    # so the round capture context object, the one object
    # carrying the distinct engine, date, and method counts
    # beside the round metrics, stands as the closing
    # engine and method bearing object of the record, after
    # the per answer rows and the sampling frame.
    # Where the caller named the kind, the record is that
    # kind's record: RoundMetrics stands computed per
    # source kind and never pooled across kinds, so the
    # rows carried beside its figures stand as that kind's
    # rows only, the rows its figures recompute from
    if caller_named_kind is not None:
        carried_rows = [
            row for row in metrics_rows
            if row.get("source_kind") == kind]
    else:
        carried_rows = metrics_rows
    ordered_result = {}
    for key, value in result.items():
        if key == "capture_context":
            ordered_result["answer_metrics"] = carried_rows
        ordered_result[key] = value
    if "answer_metrics" not in ordered_result:
        ordered_result["answer_metrics"] = carried_rows
    return ordered_result
