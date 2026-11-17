# fix seat F5 tests.
# Entry, reopening: the counted reading of
# _similar_components prices every seed at the batch
# count times the distinct size count times the set
# count width, so a family holding many distinct sizes
# inside the threshold band prices past the 120 second
# backstop at the round cap of 10,000 sets, at both
# module copies. The families stand as the round 10
# papers state them: the Red constructions at
# scratch/r10-red/p_f5_cost.py to p_f5_cost4.py (sizes
# cycling through 1,000 sizes from 1,000 to 1,999 over
# one pool of 60,000, seed 11; sizes cycling through
# 900 sizes from 1,600 to 2,499 over the same pool;
# pairs sharing one rare block and holding apart on a
# common block, at 451 distinct sizes from 2,000 to
# 2,450; and sizes cycling through 2,250 sizes from
# 4,000 to 6,249 over a pool of 200,000, seed 11), and
# the detection seat families at
# scratch/r10-detection/probe4_wider.py and
# probe2_cyclic.py with probe2b_cyclic_big.py (the
# mixed size family at 201 distinct sizes from 800 to
# 2,800 over one pool of 20,000, seed 3, and the two
# late miss cyclic constructions at set sizes 3,100 and
# 6,500). Correctness stands judged against direct pair
# computations written from the rule beside every cost
# series, and timing stands on process CPU time, never
# on wall clock.
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


def _band_family(count, low, span, pool_size, seed=11):
    # The Red first, second, and fourth constructions in
    # one form: sizes cycling through span distinct
    # values from low, every set a seeded random sample
    # of one pool, seed 11. No pair stands similar at any
    # measured scale, so the correct result is one
    # singleton component per set.
    rng = random.Random(seed)
    pool_list = list(range(pool_size))
    return [set(rng.sample(pool_list, low + (index % span)))
            for index in range(count)]


def _pair_family(pairs, seed=3):
    # The Red third construction: pairs of sets sharing
    # one rare block of 1,100 to 1,550 shingles and
    # holding apart on a common block of 900, the first
    # member holding the block every first member holds
    # and the second the block every second member
    # holds, sizes standing at 451 distinct values from
    # 2,000 to 2,450. One member of each pair survives
    # deep into the counting of the other, and no pair
    # stands similar, the shared rare block standing at
    # most 1,550 against a pair threshold of at least
    # 1,778.
    rng = random.Random(seed)
    del rng
    common_first = set(range(900))
    common_second = set(range(900, 1800))
    type_sets = []
    next_id = 1800
    for index in range(pairs):
        rare_size = 1100 + (index % 451)
        rare = set(range(next_id, next_id + rare_size))
        next_id += rare_size
        type_sets.append(rare | common_first)
        type_sets.append(rare | common_second)
    return type_sets


def _planted_pair_family(pairs, seed=17):
    # Pairs standing similar at distinct sizes inside
    # one band: pair index holds a common part standing
    # at 95 percent of the smaller member, the members
    # standing at sizes cycling through the values from
    # 2,000 upward, every pair standing on its own
    # shingles so no cross pair similarity stands. The
    # correct result holds one component per pair.
    rng = random.Random(seed)
    del rng
    type_sets = []
    next_id = 0
    for index in range(pairs):
        size_first = 2000 + (index * 37) % 500
        size_second = size_first + index % 40
        shared_size = (95 * size_first) // 100
        common = set(range(next_id, next_id + shared_size))
        next_id += shared_size
        first = common | set(
            range(next_id, next_id + size_first - shared_size))
        next_id += size_first - shared_size
        second = common | set(
            range(next_id, next_id + size_second - shared_size))
        next_id += size_second - shared_size
        type_sets.append(first)
        type_sets.append(second)
    return type_sets


def _mixed_family(count, seed=3):
    # The detection seat mixed size family: sizes
    # cycling over 201 distinct values from 800 to
    # 2,800, every set drawn from one pool of 20,000,
    # seed 3, no pair similar.
    rng = random.Random(seed)
    pool_list = list(range(20000))
    return [set(rng.sample(pool_list, 800 + (index % 201) * 10))
            for index in range(count)]


def _cyclic_family(count, width=6, block=500, core=100):
    # The detection seat late miss cyclic construction:
    # a universal core plus blocks of 500 shingles, set
    # index holding the core and width cyclically
    # consecutive blocks, size 3,100 at the standing
    # width. Two sets at cyclic shift 1 share 2,600
    # against the pair threshold of 2,756, so no pair
    # stands similar.
    block_count = count + width
    blocks = []
    for position in range(block_count):
        base = core + position * block
        blocks.append(set(range(base, base + block)))
    core_set = set(range(core))
    type_sets = []
    for index in range(count):
        member = set(core_set)
        for offset in range(width):
            member |= blocks[(index + offset) % block_count]
        type_sets.append(member)
    return type_sets


def _cyclic_wide_family(count):
    # The detection seat late miss cyclic wide
    # construction: width eight blocks of 800 plus the
    # core of 100, size 6,500, pair threshold 5,778,
    # two sets at shift 1 sharing 5,700, no pair similar.
    return _cyclic_family(count, width=8, block=800, core=100)


class TestR10F5CompoundedCorrectness(unittest.TestCase):
    # , correctness on the compounded factor families
    # at reduced scale, judged against direct pair
    # computations in both copies.

    def test_red_first_construction_correct_both_copies(self):
        type_sets = _band_family(120, 1000, 1000, 60000)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 120)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_red_second_construction_correct_both_copies(self):
        type_sets = _band_family(90, 1600, 900, 60000)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 90)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_red_fourth_construction_correct_both_copies(self):
        type_sets = _band_family(40, 4000, 2250, 200000)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 40)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_red_pair_construction_correct_both_copies(self):
        type_sets = _pair_family(30)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 60)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_planted_pairs_at_distinct_sizes_correct(self):
        type_sets = _planted_pair_family(24)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 24)
        self.assertTrue(all(len(group) == 2 for group in expected))
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_mixed_size_family_correct_both_copies(self):
        type_sets = _mixed_family(120)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 120)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_cyclic_family_correct_both_copies(self):
        type_sets = _cyclic_family(120)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 120)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_cyclic_wide_family_correct_both_copies(self):
        type_sets = _cyclic_wide_family(100)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 100)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_component_differential_mixed_sizes(self):
        rng = random.Random(43)
        families = []
        for _trial in range(24):
            count = rng.randint(2, 20)
            universe = list(range(rng.randint(10, 100)))
            families.append([
                set(rng.sample(universe,
                               rng.randint(1, len(universe))))
                for _index in range(count)])
        families.append(_band_family(30, 1000, 1000, 60000, seed=5))
        families.append(_mixed_family(30, seed=6))
        families.append(_pair_family(12))
        families.append(_planted_pair_family(10))
        for type_sets in families:
            type_sets = [item for item in type_sets if item]
            expected = _brute_components(type_sets)
            for module in (detection, metrics):
                self.assertEqual(
                    _components_as_sets(module, type_sets), expected)


class TestR10F5CompoundedCost(unittest.TestCase):
    # , cost on the Red constructions at the scales the
    # Red paper measures, process CPU time, construction
    # excluded, the singleton result judged at every
    # scale in both copies.

    def _run_inside_bound(self, module, type_sets, bound):
        start = time.process_time()
        components = module._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), len(type_sets))
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, bound)

    def test_red_first_detection_inside_bound(self):
        self._run_inside_bound(
            detection, _band_family(4000, 1000, 1000, 60000), 19.0)

    def test_red_first_metrics_inside_bound(self):
        self._run_inside_bound(
            metrics, _band_family(4000, 1000, 1000, 60000), 19.0)

    def test_red_second_detection_inside_bound(self):
        self._run_inside_bound(
            detection, _band_family(2000, 1600, 900, 60000), 11.0)

    def test_red_second_metrics_inside_bound(self):
        self._run_inside_bound(
            metrics, _band_family(2000, 1600, 900, 60000), 11.0)

    def test_red_pair_detection_inside_bound(self):
        self._run_inside_bound(detection, _pair_family(500), 4.5)

    def test_red_pair_metrics_inside_bound(self):
        self._run_inside_bound(metrics, _pair_family(500), 4.5)

    # The two fourth construction pins below stand
    # re-pinned under the ruling of Captain JP of
    # 2026-11-16, in her words: "Just remove the two
    # minute limit." The two minute limit stands removed
    # for this family, so these pins assert the
    # correctness standing of the family at this scale,
    # the singleton result judged, and no time bound
    # assertion on this family stands in their place.
    # Their old form, the same construction at this scale
    # against a bound of 40.0 seconds of process CPU
    # time, stands recorded in the fix papers of rounds
    # 10 to 13 in its standing as the pin form of the
    # backstop judgement on this family.

    def _run_correct_at_scale(self, module, type_sets):
        components = module._similar_components(type_sets)
        self.assertEqual(len(components), len(type_sets))
        self.assertTrue(all(len(component) == 1
                            for component in components))

    def test_red_fourth_detection_correct_at_scale(self):
        self._run_correct_at_scale(
            detection, _band_family(2400, 4000, 2250, 200000))

    def test_red_fourth_metrics_correct_at_scale(self):
        self._run_correct_at_scale(
            metrics, _band_family(2400, 4000, 2250, 200000))


class TestR10F5DetectionFamilyControls(unittest.TestCase):
    # The detection seat families of this round, standing
    # as controls beside the cure: the mixed size family
    # and the two late miss cyclic constructions, inside
    # their bounds in both copies, the singleton result
    # judged at every scale.

    def _run_inside_bound(self, module, type_sets, bound):
        start = time.process_time()
        components = module._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), len(type_sets))
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, bound)

    def test_mixed_size_detection_inside_bound(self):
        self._run_inside_bound(detection, _mixed_family(1200), 6.0)

    def test_mixed_size_metrics_inside_bound(self):
        self._run_inside_bound(metrics, _mixed_family(1200), 6.0)

    def test_cyclic_detection_inside_bound(self):
        self._run_inside_bound(detection, _cyclic_family(2400), 8.0)

    def test_cyclic_metrics_inside_bound(self):
        self._run_inside_bound(metrics, _cyclic_family(2400), 8.0)

    def test_cyclic_wide_detection_inside_bound(self):
        self._run_inside_bound(
            detection, _cyclic_wide_family(1200), 8.0)

    def test_cyclic_wide_metrics_inside_bound(self):
        self._run_inside_bound(metrics, _cyclic_wide_family(1200), 8.0)


if __name__ == "__main__":
    unittest.main()
