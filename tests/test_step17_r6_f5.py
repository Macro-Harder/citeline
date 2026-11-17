"""Detection and metrics.

Each test pins one register entry from the findings
register, in the form the register states. Written before
the cures, watched failing, then watched passing."""

import random
import time
import unittest

from citeline import detection, metrics


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


def frontier_family(n_large, n_reject):
    """The mixed size frontier shape measures, in the attack
    paper's own construction: a small chain of sets of
    size 12 sliding by one, a ramp of 13 nested sets
    bridging to a large chain of sets of size 200 holding
    a core of 100 plus a window of 100 sliding by 20, and
    rejects holding 95 of the core plus 105 shingles of
    their own, similar to nothing."""
    ramp_sizes = [15, 18, 22, 27, 33, 41, 51, 63, 78, 97,
                  121, 151, 188]
    core = list(range(20000, 20100))

    def large(index):
        return set(core) | set(range(
            21000 + 20 * index, 21000 + 20 * index + 100))

    large_zero = list(large(0))
    small_zero = set(range(10000, 10012))
    n_small = n_large + len(ramp_sizes) + 8
    sets = [frozenset(range(10000 + i, 10000 + i + 12))
            for i in range(n_small)]
    sets += [frozenset(small_zero | set(large_zero[:size - 12]))
             for size in ramp_sizes]
    sets += [frozenset(large(i)) for i in range(n_large)]
    sets += [frozenset(set(core[:95]) | set(range(
        40000 + j * 105, 40000 + j * 105 + 105)))
        for j in range(n_reject)]
    return sets


class TestMixedFrontier033(unittest.TestCase):
    def test_small_shape_exact_both_copies(self):
        for n_large, n_reject in ((8, 5), (20, 30)):
            sets = frontier_family(n_large, n_reject)
            expected = brute_components(sets)
            got = {frozenset(component) for component in
                   detection._similar_components(sets)}
            self.assertEqual(got, expected)
            got_metrics = {frozenset(component) for component in
                           metrics._similar_components(sets)}
            self.assertEqual(got_metrics, expected)

    def test_detection_mixed_frontier_inside_bound(self):
        sets = frontier_family(120, 2400)
        start = time.process_time()
        components = detection._similar_components(sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 2401)
        self.assertEqual(
            max(len(component) for component in components),
            120 + 21 + 13 + 120)
        self.assertLess(cpu, 6.0,
                        "detection mixed frontier took %.2f "
                        "seconds of CPU" % cpu)

    def test_metrics_mixed_frontier_inside_bound(self):
        sets = frontier_family(120, 2400)
        start = time.process_time()
        components = metrics._similar_components(sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 2401)
        self.assertEqual(
            max(len(component) for component in components),
            120 + 21 + 13 + 120)
        self.assertLess(cpu, 6.0,
                        "metrics mixed frontier took %.2f "
                        "seconds of CPU" % cpu)

    def test_detection_large_mixed_frontier_inside_bound(self):
        sets = frontier_family(200, 4000)
        start = time.process_time()
        components = detection._similar_components(sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 4001)
        self.assertEqual(
            max(len(component) for component in components),
            200 + 21 + 13 + 200)
        self.assertLess(cpu, 12.0,
                        "large mixed frontier took %.2f "
                        "seconds of CPU" % cpu)

    def test_heavy_only_candidate_still_joins(self):
        core = set(range(90))
        sets = [frozenset(core | set(range(1000, 1010)))]
        sets.append(frozenset(core | set(range(2000, 2010))))
        sets.append(frozenset({999999}))
        expected = brute_components(sets)
        got = {frozenset(component) for component in
               detection._similar_components(sets)}
        self.assertEqual(got, expected)
        got_metrics = {frozenset(component) for component in
                       metrics._similar_components(sets)}
        self.assertEqual(got_metrics, expected)

    def test_component_differential_mixed_families(self):
        rng = random.Random(20261115)
        for trial in range(150):
            families = []
            kind = trial % 3
            if kind == 0:
                core = set(rng.sample(range(5000), rng.choice(
                    (0, 10, 50, 95, 180))))
                for _ in range(rng.randint(1, 14)):
                    extra = set(rng.sample(
                        range(5000, 5300), rng.randint(0, 40)))
                    families.append(frozenset(core | extra))
                for _ in range(rng.randint(0, 6)):
                    families.append(frozenset(rng.sample(
                        range(9000, 9400), rng.randint(5, 60))))
            elif kind == 1:
                base = rng.randint(0, 500)
                for step in range(rng.randint(2, 12)):
                    size = rng.choice((12, 30, 100, 200))
                    start = base + step * (size // 6 + 1)
                    families.append(frozenset(
                        range(start, start + size)))
            else:
                for _ in range(rng.randint(1, 14)):
                    families.append(frozenset(rng.sample(
                        range(300), rng.randint(5, 120))))
            if not families:
                continue
            expected = brute_components(families)
            got = {frozenset(component) for component in
                   detection._similar_components(families)}
            self.assertEqual(got, expected)
            got_metrics = {frozenset(component) for component in
                           metrics._similar_components(families)}
            self.assertEqual(got_metrics, expected)

    def test_clique_differential_random(self):
        rng = random.Random(7331)
        for trial in range(100):
            vocab = list(range(rng.randint(6, 20)))
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

            self.assertEqual(
                metrics._sets_clique(families), brute(families))


class RecordObject:
    def __init__(self, name, named, cited=None):
        self.name = name
        self.named = named
        if cited is not None:
            self.cited = cited


class TestCompetitorMappingNoFields034(unittest.TestCase):
    def check_refused(self, value):
        row = answer(per_competitor=value)
        with self.assertRaises(ValueError) as caught:
            metrics.round_metrics([row], "sampled")
        self.assertIn("must carry a name, named, or cited",
                      str(caught.exception))

    def test_mapping_empty_value_refused(self):
        self.check_refused({"Rival": {}})

    def test_mapping_unrelated_field_refused(self):
        self.check_refused({"Rival": {"foo": 1}})

    def test_mapping_cited_reason_only_refused(self):
        self.check_refused({"Rival": {"cited_reason": "x"}})

    def test_mapping_nested_record_refused(self):
        self.check_refused(
            {"Rival": {"Inner": {"name": "Inner", "named": True}}})

    def test_mapping_nested_bad_boolean_refused(self):
        self.check_refused({"Rival": {"Inner": {
            "name": "Inner", "named": "false"}}})

    def test_mapping_under_competitors_field_refused(self):
        row = answer(competitors={"Rival": {}})
        with self.assertRaises(ValueError):
            metrics.round_metrics([row], "sampled")

    def test_mapping_controls_count_as_before(self):
        row = answer(per_competitor={
            "Rival": {"name": "Rival", "named": False}})
        result = metrics.round_metrics([row], "sampled")
        entry = field(result, "per_competitor")["Rival"]
        self.assertEqual(field(entry, "named_count"), 0)
        row = answer(per_competitor={
            "Rival": RecordObject("Rival", True, True)})
        result = metrics.round_metrics([row], "sampled")
        entry = field(result, "per_competitor")["Rival"]
        self.assertEqual(field(entry, "named_count"), 1)
        self.assertEqual(field(entry, "cited_rate"), 1.0)

    def test_list_form_control_still_refused(self):
        row = answer(per_competitor=[{"cited_reason": "x"}])
        with self.assertRaises(ValueError):
            metrics.round_metrics([row], "sampled")


if __name__ == "__main__":
    unittest.main()
