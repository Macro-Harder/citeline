"""Step 17 round 5 fix seat F5 tests, detection and metrics.

Each test pins one register entry from the Step 17 round 5
findings register, in the form the register states. Written
before the cures, watched failing, then watched passing.
"""

import itertools
import random
import time
import unittest

from citeline import detection, metrics

PRODUCT = {
    "name": "Northbeam",
    "aliases": [],
    "domain": "northbeam.example.com",
}
SEPS = ["。", "．", "｡"]


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def answer(**overrides):
    row = {
        "named": False, "named_early": False, "cited": False,
        "cluster_id": 0, "matched_aliases": [], "query": "q-one",
        "engine_label": "EngineA", "capture_method": "by hand",
        "captured_on": "2026-11-01", "source_kind": "sampled",
        "control": False, "competitor_named": False,
        "citation_instances": 0, "self_citation_instances": 0,
        "text": "some answer text here now",
    }
    row.update(overrides)
    return row


def brute_components(type_sets):
    parent = list(range(len(type_sets)))

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for first in range(len(type_sets)):
        for second in range(first + 1, len(type_sets)):
            shared = len(type_sets[first] & type_sets[second])
            total = len(type_sets[first]) + len(type_sets[second])
            if shared * 9 >= 4 * total:
                root_first, root_second = find(first), find(second)
                if root_first != root_second:
                    parent[max(root_first, root_second)] = min(
                        root_first, root_second)
    groups = {}
    for index in range(len(type_sets)):
        groups.setdefault(find(index), set()).add(index)
    return {frozenset(group) for group in groups.values()}


def reject_pool_sets(backbone_count, reject_count):
    """The shape entry S17-R5-036 measures: backbone sets of
    200 shingles sliding by 20, consecutive sets sharing 180
    and second neighbours sharing 160, every set holding the
    same 10 common shingles, and each reject holding those
    10 plus 190 shingles of its own, similar to nothing."""
    common = {("c", index) for index in range(10)}
    sets = []
    for backbone in range(backbone_count):
        base = backbone * 20
        sets.append(frozenset(
            common | {("s", base + step) for step in range(190)}))
    for reject in range(reject_count):
        sets.append(frozenset(
            common | {("r", reject, step) for step in range(190)}))
    return sets


def reject_pool_texts(backbone_count, reject_count):
    """The same shape realised from answer texts: a fixed 14
    word phrase at the head of every text standing as the
    common part, then a backbone sliding by 15 words or 194
    words found nowhere else for a reject."""
    common_words = ["c%d" % index for index in range(14)]
    pool = ["b%d" % index for index in range(15 * backbone_count + 220)]
    texts = []
    for backbone in range(backbone_count):
        start = 15 * backbone
        texts.append(" ".join(common_words + pool[start:start + 194]))
    for reject in range(reject_count):
        words = ["r%dx%d" % (reject, step) for step in range(194)]
        texts.append(" ".join(common_words + words))
    return texts


class TestRejectPool036(unittest.TestCase):
    def test_detection_reject_pool_inside_bound(self):
        sets = reject_pool_sets(100, 2000)
        start = time.perf_counter()
        components = detection._similar_components(sets)
        elapsed = time.perf_counter() - start
        self.assertEqual(len(components), 2001)
        self.assertEqual(
            sorted(len(component) for component in components)[-1], 100)
        self.assertLess(elapsed, 8.0,
                        "reject pool took %.2f seconds" % elapsed)

    def test_metrics_reject_pool_inside_bound(self):
        sets = reject_pool_sets(50, 1000)
        start = time.perf_counter()
        components = metrics._similar_components(sets)
        elapsed = time.perf_counter() - start
        self.assertEqual(len(components), 1001)
        self.assertLess(elapsed, 3.0,
                        "metrics reject pool took %.2f seconds" % elapsed)

    def test_text_reject_pool_inside_bound(self):
        texts = reject_pool_texts(40, 800)
        start = time.perf_counter()
        clusters = detection.cluster_answers(texts)
        elapsed = time.perf_counter() - start
        self.assertEqual(len(set(clusters)), 801)
        self.assertLess(elapsed, 2.5,
                        "text reject pool took %.2f seconds" % elapsed)

    def test_reject_pool_small_shape_exact(self):
        sets = reject_pool_sets(8, 5)
        expected = brute_components(sets)
        got = {frozenset(component)
               for component in detection._similar_components(sets)}
        self.assertEqual(got, expected)
        got_metrics = {frozenset(component)
                       for component in metrics._similar_components(sets)}
        self.assertEqual(got_metrics, expected)

    def test_component_differential_with_common_core(self):
        rng = random.Random(20261115)
        for core_size in (0, 26, 100, 170):
            for trial in range(15):
                core = set(range(core_size))
                families = []
                for _ in range(rng.randint(1, 12)):
                    extra = set(rng.sample(
                        range(1000, 1060), rng.randint(0, 30)))
                    families.append(frozenset(core | extra))
                expected = brute_components(families)
                got = {frozenset(component) for component in
                       detection._similar_components(families)}
                self.assertEqual(got, expected)
                got_metrics = {frozenset(component) for component in
                               metrics._similar_components(families)}
                self.assertEqual(got_metrics, expected)


def varying_missed_family(count, seed=99):
    """The family entry S17-R5-037 states: member sets of
    size 57 over a shared core of 27 parts plus a pool of
    34 parts, each member holding the core and all but 4
    of the pool, the missed parts varying in size against
    the pivot and the added parts rotating with no part
    common to every member."""
    core = set(range(27))
    pool = list(range(27, 61))
    rng = random.Random(seed)
    seen = set()
    families = []
    while len(families) < count:
        miss = frozenset(rng.sample(pool, 4))
        if miss in seen:
            continue
        seen.add(miss)
        families.append(frozenset(core | (set(pool) - set(miss))))
    return families


class TestCliqueVaryingMissed037(unittest.TestCase):
    def test_clique_family_4000_inside_bound(self):
        sets = varying_missed_family(4000)
        start = time.perf_counter()
        outcome = metrics._sets_clique(sets)
        elapsed = time.perf_counter() - start
        self.assertTrue(outcome)
        self.assertLess(elapsed, 3.0,
                        "clique family took %.2f seconds" % elapsed)

    def test_cluster_chained_wrapper_on_family(self):
        sets = varying_missed_family(2000)
        start = time.perf_counter()
        outcome = metrics._cluster_chained(sets)
        elapsed = time.perf_counter() - start
        self.assertFalse(outcome)
        self.assertLess(elapsed, 3.0,
                        "chained wrapper took %.2f seconds" % elapsed)

    def test_clique_false_case_still_found(self):
        sets = varying_missed_family(20)
        broken = frozenset(set(sets[0]) - set(range(10, 30)))
        self.assertFalse(metrics._sets_clique(sets + [broken]))

    def test_clique_differential_random(self):
        rng = random.Random(515)
        for trial in range(60):
            vocab = list(range(rng.randint(6, 16)))
            families = []
            for _ in range(rng.randint(2, 10)):
                size = rng.randint(1, len(vocab))
                families.append(frozenset(rng.sample(vocab, size)))

            def brute(sets):
                for first in range(len(sets)):
                    for second in range(first + 1, len(sets)):
                        shared = len(sets[first] & sets[second])
                        total = len(sets[first]) + len(sets[second])
                        if shared * 9 < 4 * total:
                            return False
                return True

            self.assertEqual(metrics._sets_clique(families), brute(families))


def journal_entries(link):
    return [
        {"sequence": 1, "entry_kind": "product_registered",
         "payload": {"name": "Northbeam",
                     "domain": "northbeam.example.com",
                     "aliases": []}},
        {"sequence": 2, "entry_kind": "answer_imported",
         "payload": {"answer_text": "See " + link + " for details",
                     "kind": "sampled", "query": "q",
                     "captured_on": "2026-11-01"}},
    ]


class TestMetricsSeparator038(unittest.TestCase):
    def test_journal_route_separator_self_citation(self):
        for sep in SEPS:
            link = "https://northbeam" + sep + "example" + sep + "com/guide"
            rows = metrics.answer_metrics_from_journal(
                journal_entries(link))
            self.assertTrue(rows[0]["cited"], sep)
            self.assertEqual(rows[0]["citation_instances"], 1, sep)
            self.assertEqual(rows[0]["self_citation_instances"], 1, sep)

    def test_journal_route_ascii_control(self):
        rows = metrics.answer_metrics_from_journal(
            journal_entries("https://northbeam.example.com/guide"))
        self.assertTrue(rows[0]["cited"])
        self.assertEqual(rows[0]["self_citation_instances"], 1)

    def test_host_helpers_separator_mapping(self):
        for sep in SEPS:
            url = "https://northbeam" + sep + "example" + sep + "com/guide"
            host = metrics._host_of(url)
            self.assertEqual(host, "northbeam.example.com", sep)
            self.assertTrue(
                metrics._host_matches(host, "northbeam.example.com"), sep)

    def test_round_metrics_from_journal_separator_share(self):
        sep = "。"
        link = "https://northbeam" + sep + "example" + sep + "com/guide"
        result = metrics.round_metrics_from_journal(
            journal_entries(link))
        self.assertEqual(field(result, "self_citation_share"), 1.0)
        self.assertEqual(field(result, "cited_rate_net"), 0.0)


class RecordObject:
    def __init__(self, name, named, cited=None):
        self.name = name
        self.named = named
        if cited is not None:
            self.cited = cited


class FalseTruthRecord:
    def __init__(self):
        self.name = "Rival"
        self.named = True
        self.cited = True

    def __bool__(self):
        return False


class TestCompetitorObjectRecord039(unittest.TestCase):
    def test_object_named_false_counts_zero(self):
        row = answer(per_competitor={"Rival": RecordObject("Rival", False)})
        result = metrics.round_metrics([row], "sampled")
        entry = field(result, "per_competitor")["Rival"]
        self.assertEqual(field(entry, "named_count"), 0)

    def test_object_named_and_cited_counted(self):
        row = answer(per_competitor={
            "Rival": RecordObject("Rival", True, True)})
        result = metrics.round_metrics([row], "sampled")
        entry = field(result, "per_competitor")["Rival"]
        self.assertEqual(field(entry, "named_count"), 1)
        self.assertEqual(field(entry, "cited_rate"), 1.0)

    def test_object_under_competitors_field_name(self):
        row = answer(competitors={"Rival": RecordObject("Rival", False)})
        result = metrics.round_metrics([row], "sampled")
        entry = field(result, "per_competitor")["Rival"]
        self.assertEqual(field(entry, "named_count"), 0)

    def test_object_false_truthiness_still_counted_as_record(self):
        row = answer(per_competitor={"Rival": FalseTruthRecord()})
        result = metrics.round_metrics([row], "sampled")
        entry = field(result, "per_competitor")["Rival"]
        self.assertEqual(field(entry, "named_count"), 1)
        self.assertEqual(field(entry, "cited_rate"), 1.0)

    def test_mapping_and_list_object_controls(self):
        row = answer(per_competitor={
            "Rival": {"name": "Rival", "named": True, "cited": True}})
        result = metrics.round_metrics([row], "sampled")
        entry = field(result, "per_competitor")["Rival"]
        self.assertEqual(field(entry, "named_count"), 1)
        self.assertEqual(field(entry, "cited_rate"), 1.0)
        row = answer(per_competitor=[RecordObject("Rival", False)])
        result = metrics.round_metrics([row], "sampled")
        entry = field(result, "per_competitor")["Rival"]
        self.assertEqual(field(entry, "named_count"), 0)


class TestCompetitorListNoFields040(unittest.TestCase):
    def check_refused(self, value):
        row = answer(per_competitor=value)
        with self.assertRaises(ValueError):
            metrics.round_metrics([row], "sampled")

    def test_list_nested_mapping_form_refused(self):
        self.check_refused([{"Rival": {"name": "Rival", "named": True}}])

    def test_list_nested_bad_boolean_refused(self):
        self.check_refused(
            [{"Rival": {"name": "Rival", "named": "false"}}])

    def test_list_empty_mapping_refused(self):
        self.check_refused([{}])

    def test_list_unrelated_field_mapping_refused(self):
        self.check_refused([{"foo": 1}])

    def test_list_record_controls_pass(self):
        row = answer(per_competitor=[{"name": "Rival", "named": True}])
        result = metrics.round_metrics([row], "sampled")
        entry = field(result, "per_competitor")["Rival"]
        self.assertEqual(field(entry, "named_count"), 1)
        row = answer(per_competitor=[{"name": "Rival"}])
        result = metrics.round_metrics([row], "sampled")
        entry = field(result, "per_competitor")["Rival"]
        self.assertEqual(field(entry, "named_count"), 0)


class TestEscapedParenthesis041(unittest.TestCase):
    def test_escaped_closing_parenthesis_masked(self):
        text = "See [the page](https://example.com/f\\)Northbeam) now"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))
        self.assertEqual(field(result, "matched_aliases"), [])

    def test_escaped_pair_control_masked(self):
        text = "See [the page](https://example.com/f\\(Northbeam\\)) now"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))

    def test_balanced_and_angle_controls_masked(self):
        text = "See [the page](https://example.com/f()Northbeam) now"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))
        text = "See [the page](<https://example.com/f)Northbeam>) now"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))


if __name__ == "__main__":
    unittest.main()
