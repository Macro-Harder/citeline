# Step 17 round 9 fix seat F5 tests.
#
# Entry S17-R9-014: the prefix seed pass of
# _similar_components stands outside its backstops on the
# pool families the wide reading guards leave on the
# prefix form, at both module copies. The families stand
# as the round 9 papers state them: the seed size guard
# limb at set size 3,000 over a pool of 4,500, seed 7
# (detection R9-DM-01), at set size 3,000 over a pool of
# 6,000, seed 42, and at set size 2,001 over a pool of
# 4,002, seed 7 (red S17-R9-RED-01); and the prefix
# posting total guard limb at seed size 2,000 with the
# pool standing at 500 times the set count, seed 11
# (detection R9-DM-02). Correctness stands judged against
# direct pair computations written from the rule beside
# every cost series, and timing stands on process CPU
# time, never on wall clock.
#
# Copyright: J.P. Picard aka Macro-Harder.

import random
import time
import unittest

from citeline import detection, metrics


def _brute_components(type_sets):
    parent = list(range(len(type_sets)))

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for first in range(len(type_sets)):
        for second in range(first + 1, len(type_sets)):
            shared = len(type_sets[first] & type_sets[second])
            if shared * 9 >= 4 * (len(type_sets[first])
                                  + len(type_sets[second])):
                root_first, root_second = find(first), find(second)
                if root_first != root_second:
                    parent[root_first] = root_second
    groups = {}
    for index in range(len(type_sets)):
        groups.setdefault(find(index), set()).add(index)
    return {frozenset(group) for group in groups.values()}


def _components_as_sets(module, type_sets):
    return {frozenset(component)
            for component in module._similar_components(type_sets)}


def _seed_size_family(count, size=3000, pool=4500, seed=7):
    # The R9-DM-01 construction: every set a seeded random
    # 3,000 of one pool of 4,500 shingles, seed 7. Two sets
    # share about 2,000 shingles against the pair threshold
    # of 2,667 at size 3,000, so no pair stands similar and
    # the correct result is one singleton per set.
    rng = random.Random(seed)
    pool_list = list(range(pool))
    return [set(rng.sample(pool_list, size)) for _index in range(count)]


def _red_seed_size_family(count, size=3000, pool=6000, seed=42):
    # The S17-R9-RED-01 first construction: every set a
    # seeded random 3,000 of one pool of 6,000 shingles,
    # seed 42, two sets sharing about 1,500 shingles
    # against the threshold of 2,667, no pair similar.
    rng = random.Random(seed)
    pool_list = list(range(pool))
    return [set(rng.sample(pool_list, size)) for _index in range(count)]


def _red_past_guard_family(count, size=2001, pool=4002, seed=7):
    # The S17-R9-RED-01 second construction: set size
    # 2,001, one shingle past the wide reading seed size
    # guard, drawn from a pool of 4,002, seed 7, no pair
    # similar.
    rng = random.Random(seed)
    pool_list = list(range(pool))
    return [set(rng.sample(pool_list, size)) for _index in range(count)]


def _prefix_total_family(count, size=2000, seed=11):
    # The R9-DM-02 construction: every set a seeded random
    # 2,000 of a pool standing at 500 times the set count,
    # seed 11, each shingle standing in about four sets,
    # the prefix posting totals standing under the wide
    # reading guard of 1,024 at every seed counted in the
    # attack paper, and no pair similar.
    rng = random.Random(seed)
    pool_list = list(range(500 * count))
    return [set(rng.sample(pool_list, size)) for _index in range(count)]


def _large_cluster_family(seed=23):
    # A family at set size 3,000 holding true neighbours:
    # a cluster whose members each miss a few shingles of
    # a common base and add a few of their own, standing
    # similar to the base and to each other, beside
    # singleton sets of the seed size family form. Judged
    # against the direct computation, this pins that a
    # cure at the seed pass loses no true neighbour at
    # large set sizes.
    rng = random.Random(seed)
    base = set(range(3000))
    type_sets = [set(base)]
    for index in range(5):
        member = set(base)
        member -= set(rng.sample(sorted(base), 60))
        member |= {900000 + index * 60 + offset
                   for offset in range(60)}
        type_sets.append(member)
    pool_list = list(range(3000, 7500))
    for _index in range(24):
        type_sets.append(set(rng.sample(pool_list, 3000)))
    return type_sets


def _large_pair_family(count=120, seed=11):
    # The prefix total family with one planted similar
    # pair at seed size 2,000: the second set of the pair
    # misses 100 shingles of the first and adds 100 of its
    # own, standing at a shared count of 1,900 against the
    # threshold of 1,778, so the pair stands similar and
    # every other pair does not.
    type_sets = _prefix_total_family(count, seed=seed)
    first = type_sets[10]
    rng = random.Random(99)
    second = set(first)
    second -= set(rng.sample(sorted(first), 100))
    second |= {500 * count + 500000 + offset for offset in range(100)}
    type_sets[20] = second
    return type_sets


def _shared_pool_family(count, seed=19):
    # The S17-R8-018 construction, standing as a control:
    # every set a seeded random 200 of one pool of 300
    # shingles, seed 19, no pair similar.
    rng = random.Random(seed)
    pool_list = list(range(300))
    return [set(rng.sample(pool_list, 200)) for _index in range(count)]


def _deferred_family(links, per_pair=120, seed=9000):
    # The registered construction of S17-R7-048, standing
    # as a control, in the form the round 7 seat states
    # it, so the two queue organisation stands exercised
    # whole beside this cure.
    core = set(range(60))
    type_sets = []
    for index in range(links):
        segment = set(range(100000 + index * 33,
                            100000 + index * 33 + 240))
        type_sets.append(core | segment)
    uid = 500000
    for pair in range(links - 1):
        first = set(range(100000 + pair * 33,
                          100000 + pair * 33 + 240))
        second = set(range(100000 + (pair + 1) * 33,
                           100000 + (pair + 1) * 33 + 240))
        shared_segment = sorted(first & second)
        rng = random.Random(seed + pair)
        for _copy in range(per_pair):
            subset = set(rng.sample(shared_segment, 175))
            filler = set(range(uid, uid + 65))
            uid += 65
            type_sets.append(core | subset | filler)
    return type_sets


class TestR9F5SeedSizeLimbCorrectness(unittest.TestCase):
    # S17-R9-014, the seed size guard limb.

    def test_seed_size_family_correct_both_copies(self):
        type_sets = _seed_size_family(150)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 150)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_red_seed_size_family_correct_both_copies(self):
        type_sets = _red_seed_size_family(60)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 60)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_red_past_guard_family_correct_both_copies(self):
        type_sets = _red_past_guard_family(60)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 60)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_large_cluster_family_correct_both_copies(self):
        type_sets = _large_cluster_family()
        expected = _brute_components(type_sets)
        self.assertTrue(any(len(group) == 6 for group in expected))
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)


class TestR9F5PrefixTotalLimbCorrectness(unittest.TestCase):
    # S17-R9-014, the prefix posting total guard limb.

    def test_prefix_total_family_correct_both_copies(self):
        type_sets = _prefix_total_family(200)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 200)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_prefix_total_planted_pair_correct_both_copies(self):
        type_sets = _large_pair_family(120)
        expected = _brute_components(type_sets)
        self.assertTrue(any(len(group) == 2 for group in expected))
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)


class TestR9F5SeedSizeLimbCost(unittest.TestCase):
    # S17-R9-014, cost on the seed size guard limb, process
    # CPU time, construction excluded.

    def test_seed_size_detection_inside_bound(self):
        type_sets = _seed_size_family(600)
        start = time.process_time()
        components = detection._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 600)
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, 10.0)

    def test_seed_size_metrics_inside_bound(self):
        type_sets = _seed_size_family(600)
        start = time.process_time()
        components = metrics._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 600)
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, 10.0)

    def test_red_seed_size_detection_inside_bound(self):
        type_sets = _red_seed_size_family(400)
        start = time.process_time()
        components = detection._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 400)
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, 6.0)

    def test_red_seed_size_metrics_inside_bound(self):
        type_sets = _red_seed_size_family(400)
        start = time.process_time()
        components = metrics._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 400)
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, 6.0)

    def test_red_past_guard_detection_inside_bound(self):
        type_sets = _red_past_guard_family(400)
        start = time.process_time()
        components = detection._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 400)
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, 6.0)

    def test_red_past_guard_metrics_inside_bound(self):
        type_sets = _red_past_guard_family(400)
        start = time.process_time()
        components = metrics._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 400)
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, 6.0)


class TestR9F5PrefixTotalLimbCost(unittest.TestCase):
    # S17-R9-014, cost on the prefix posting total guard
    # limb, process CPU time, construction excluded.

    def test_prefix_total_detection_inside_bound(self):
        type_sets = _prefix_total_family(2000)
        start = time.process_time()
        components = detection._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 2000)
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, 18.0)

    def test_prefix_total_metrics_inside_bound(self):
        type_sets = _prefix_total_family(2000)
        start = time.process_time()
        components = metrics._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 2000)
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, 18.0)


class TestR9F5StandingControls(unittest.TestCase):
    # The cures this entry stands beside: the S17-R8-018
    # families, the two queue organisation of S17-R7-048,
    # and the S17-R8-019 clique reading, which this cure
    # does not touch.

    def test_shared_pool_control_both_copies(self):
        type_sets = _shared_pool_family(2400)
        expected_count = 2400
        for module in (detection, metrics):
            start = time.process_time()
            components = module._similar_components(type_sets)
            cpu = time.process_time() - start
            self.assertEqual(len(components), expected_count)
            self.assertLess(cpu, 5.0)

    def test_deferred_family_control_both_copies(self):
        type_sets = _deferred_family(25)
        for module in (detection, metrics):
            start = time.process_time()
            components = module._similar_components(type_sets)
            cpu = time.process_time() - start
            sizes = sorted((len(component)
                            for component in components),
                           reverse=True)
            self.assertEqual(sizes[0], 25)
            self.assertTrue(all(size == 1 for size in sizes[1:]))
            self.assertLess(cpu, 8.0)

    def test_component_differential_mixed_sizes(self):
        rng = random.Random(41)
        families = []
        for _trial in range(24):
            count = rng.randint(2, 20)
            universe = list(range(rng.randint(10, 100)))
            families.append([
                set(rng.sample(universe,
                               rng.randint(1, len(universe))))
                for _index in range(count)])
        families.append(_seed_size_family(30, seed=3))
        families.append(_prefix_total_family(30, seed=4))
        for type_sets in families:
            type_sets = [item for item in type_sets if item]
            expected = _brute_components(type_sets)
            for module in (detection, metrics):
                self.assertEqual(
                    _components_as_sets(module, type_sets), expected)


if __name__ == "__main__":
    unittest.main()
