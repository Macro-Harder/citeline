# Step 17 round 17 fix seat F5 tests, verdict form only.
#
# Seat F5 carries no TO FIX entry in fix round 17. The
# family entry S17-R11-012, extending S17-R10-010,
# stands DISPOSED on the ruling of Captain JP of
# 2026-11-16, in her words: "Just remove the two minute
# limit." The two minute limit stands removed for this
# family and the refusal ground stands dissolved on
# her ruling, as the fix paper of this seat records.
# These tests pin the
# verdicts of this seat on the tree as it stands: the
# two copies of _similar_components standing byte
# identical; the round 10 cure standing exact against
# direct pair computations on the differential forms of
# this seat, written from the rule; and the four Red
# round 10 constructions standing at the behaviour the
# papers record at the scales these pins run, process
# CPU time, construction excluded, the singleton result
# judged at every cost scale. No product module stands
# edited by this seat.
#
# Copyright: J.P. Picard aka Macro-Harder.

import random
import time
import unittest

from citeline import detection, metrics


def _function_text(module):
    # The _similar_components text of a module, read from
    # its source file, from the def line through the last
    # line of the function, in the counting form the fix
    # round 10 paper states at 34,214 characters.
    import inspect
    source = inspect.getsource(module)
    start = source.index("def _similar_components")
    rest = source[start:]
    lines = rest.splitlines(keepends=True)
    kept = []
    for line in lines[1:]:
        if line and not line[0].isspace():
            break
        kept.append(line)
    return lines[0] + "".join(kept).rstrip("\n") + "\n"


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


def _threshold(first_size, second_size):
    # The smallest shared count standing similar under
    # the rule shared * 9 >= 4 * (first + second).
    total = 4 * (first_size + second_size)
    return (total + 8) // 9


def _allowance_sweep(seed_size, step):
    # One seed of seed_size per candidate size standing
    # in its threshold band, with two partners per seed,
    # one sharing exactly the pair threshold with the
    # seed and one sharing exactly one less, so every
    # allowance value the interval build names stands
    # exercised as the candidate size steps the band.
    type_sets = []
    next_id = 0
    low = (4 * seed_size + 4) // 5
    while (5 * low) < 4 * seed_size:
        low += 1
    high = (5 * seed_size) // 4
    size = low
    while size <= high:
        seed = set(range(next_id, next_id + seed_size))
        next_id += seed_size
        threshold = _threshold(seed_size, size)
        exact = set(list(seed)[:threshold])
        exact |= set(range(next_id, next_id + size - threshold))
        next_id += size - threshold
        under = set(list(seed)[:threshold - 1])
        under |= set(range(next_id,
                           next_id + size - threshold + 1))
        next_id += size - threshold + 1
        type_sets.extend([seed, exact, under])
        size += step
    return type_sets


def _band_edge_family():
    # Seed size 900: candidates at the band top size of
    # 1,125 sharing the whole seed, the allowance there
    # standing at zero, and sharing one less; candidates
    # at the band bottom size of 720 at its exact
    # threshold and one under; candidates one step
    # outside the band on each side; an identical twin
    # of the seed and a twin sharing one less than the
    # whole seed.
    seed_size = 900
    seed = set(range(seed_size))
    type_sets = [seed]
    next_id = seed_size

    def partner(shared, size):
        nonlocal next_id
        member = set(list(seed)[:shared])
        member |= set(range(next_id, next_id + size - shared))
        next_id += size - shared
        return member

    type_sets.append(partner(900, 1125))
    type_sets.append(partner(899, 1125))
    bottom = _threshold(900, 720)
    type_sets.append(partner(bottom, 720))
    type_sets.append(partner(bottom - 1, 720))
    type_sets.append(partner(900, 1126))
    type_sets.append(partner(719, 719))
    type_sets.append(set(seed))
    type_sets.append(partner(899, 900))
    return type_sets


def _threshold_chains(chains=19, seed=211):
    # Chains of three sets at mixed sizes, each link
    # sharing exactly its pair threshold with the next,
    # beside a crowd of dissimilar sets standing on
    # their own shingles.
    rng = random.Random(seed)
    type_sets = []
    next_id = 0
    for _index in range(chains):
        sizes = [rng.randint(280, 1500) for _ in range(3)]
        first = set(range(next_id, next_id + sizes[0]))
        next_id += sizes[0]
        link = _threshold(sizes[0], sizes[1])
        second = set(list(first)[:link])
        second |= set(range(next_id, next_id + sizes[1] - link))
        next_id += sizes[1] - link
        link = _threshold(sizes[1], sizes[2])
        third = set(list(second)[:link])
        third |= set(range(next_id, next_id + sizes[2] - link))
        next_id += sizes[2] - link
        type_sets.extend([first, second, third])
    for _index in range(36):
        size = rng.randint(200, 900)
        type_sets.append(set(range(next_id, next_id + size)))
        next_id += size
    return type_sets


def _heterogeneous_trials(trials=44, seed=173):
    # Random families at sizes from 40 to 6,500 holding
    # planted partners at exact pair thresholds and at
    # one under, at seed sizes past 2,000 among them,
    # where the counted reading stands taken on the
    # price limb alone.
    rng = random.Random(seed)
    families = []
    for trial in range(trials):
        count = rng.randint(2, 14)
        universe = list(range(rng.randint(50, 400)))
        family = [set(rng.sample(universe,
                                 rng.randint(1, len(universe))))
                  for _ in range(count)]
        seed_size = rng.choice([2100, 3000, 4444, 6500])
        base = trial * 100000
        seed_set = set(range(base, base + seed_size))
        partner_size = seed_size + rng.randint(0, 200)
        threshold = _threshold(seed_size, partner_size)
        exact = set(list(seed_set)[:threshold])
        exact |= set(range(base + seed_size,
                           base + seed_size
                           + partner_size - threshold))
        under = set(list(seed_set)[:threshold - 1])
        under |= set(range(base + 2 * seed_size,
                           base + 2 * seed_size
                           + partner_size - threshold + 1))
        family.extend([seed_set, exact, under])
        families.append(family)
    return families


def _distinct_seed_size_family(count):
    # Every set at its own distinct size, sizes 4,000
    # plus the set index, over a pool of 600,000, seed
    # 11, so every set stands as a seed at a distinct
    # seed size. No pair stands similar.
    rng = random.Random(11)
    pool_list = list(range(600000))
    return [set(rng.sample(pool_list, 4000 + index))
            for index in range(count)]


def _band_family(count, low, span, pool_size, seed=11):
    # The Red first, second, and fourth constructions in
    # one form, as the round 10 test file states them.
    rng = random.Random(seed)
    pool_list = list(range(pool_size))
    return [set(rng.sample(pool_list, low + (index % span)))
            for index in range(count)]


def _pair_family(pairs):
    # The Red third construction, as the round 10 test
    # file states it.
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


def _mixed_family(count, seed=3):
    rng = random.Random(seed)
    pool_list = list(range(20000))
    return [set(rng.sample(pool_list, 800 + (index % 201) * 10))
            for index in range(count)]


def _cyclic_family(count, width=6, block=500, core=100):
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


class TestR17F5ByteIdentity(unittest.TestCase):
    # The two copies of _similar_components stand byte
    # identical in the cured reading.

    def test_similar_components_copies_byte_identical(self):
        detection_text = _function_text(detection)
        metrics_text = _function_text(metrics)
        self.assertEqual(detection_text, metrics_text)
        self.assertEqual(len(detection_text), 34214)


class TestR17F5CureCorrectnessDifferentials(unittest.TestCase):
    # The round 10 cure stands exact against direct pair
    # computations on the differential forms of this
    # seat, in both copies.

    def test_allowance_sweep_seed_560_both_copies(self):
        type_sets = _allowance_sweep(560, 5)
        expected = _brute_components(type_sets)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_allowance_sweep_seed_880_both_copies(self):
        type_sets = _allowance_sweep(880, 8)
        expected = _brute_components(type_sets)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_allowance_sweep_seed_1150_both_copies(self):
        type_sets = _allowance_sweep(1150, 9)
        expected = _brute_components(type_sets)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_band_edge_family_both_copies(self):
        type_sets = _band_edge_family()
        expected = _brute_components(type_sets)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_threshold_chains_both_copies(self):
        type_sets = _threshold_chains()
        expected = _brute_components(type_sets)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_heterogeneous_differentials_both_copies(self):
        for type_sets in _heterogeneous_trials():
            expected = _brute_components(type_sets)
            for module in (detection, metrics):
                self.assertEqual(
                    _components_as_sets(module, type_sets), expected)

    def test_distinct_seed_size_family_correct_both_copies(self):
        type_sets = _distinct_seed_size_family(110)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 110)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_fourth_construction_correct_both_copies(self):
        type_sets = _band_family(40, 4000, 2250, 200000)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 40)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_first_and_second_constructions_correct(self):
        for type_sets in (_band_family(110, 1000, 1000, 60000),
                          _band_family(90, 1600, 900, 60000)):
            expected = _brute_components(type_sets)
            self.assertEqual(len(expected), len(type_sets))
            for module in (detection, metrics):
                self.assertEqual(
                    _components_as_sets(module, type_sets), expected)

    def test_pair_construction_correct_both_copies(self):
        type_sets = _pair_family(30)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 60)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)


class TestR17F5ConstructionCostPins(unittest.TestCase):
    # The four Red constructions at the scales these
    # pins run, process CPU time, construction excluded,
    # the singleton result judged at every scale. The
    # bounds stand wide against the measured standings
    # of the round 16 papers, as verdict pins on the
    # cured behaviour and not as backstop measurements.

    def _run_inside_bound(self, module, type_sets, bound):
        start = time.process_time()
        components = module._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), len(type_sets))
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, bound)

    def test_first_construction_detection_inside_bound(self):
        self._run_inside_bound(
            detection, _band_family(2000, 1000, 1000, 60000), 30.0)

    def test_first_construction_metrics_inside_bound(self):
        self._run_inside_bound(
            metrics, _band_family(2000, 1000, 1000, 60000), 30.0)

    def test_second_construction_detection_inside_bound(self):
        self._run_inside_bound(
            detection, _band_family(2000, 1600, 900, 60000), 30.0)

    def test_second_construction_metrics_inside_bound(self):
        self._run_inside_bound(
            metrics, _band_family(2000, 1600, 900, 60000), 30.0)

    def test_pair_construction_detection_inside_bound(self):
        self._run_inside_bound(detection, _pair_family(500), 15.0)

    def test_pair_construction_metrics_inside_bound(self):
        self._run_inside_bound(metrics, _pair_family(500), 15.0)

    # The two fourth construction pins below stand
    # re-pinned under the ruling of Captain JP of
    # 2026-11-16 on entry S17-R11-012, in her words:
    # "Just remove the two minute limit." The two minute
    # limit stands removed for this family, so these pins
    # assert the correctness standing of the family at
    # this scale, the singleton result judged, and no
    # time bound assertion on this family stands in
    # their place. Their old form, the same construction
    # at this scale against a bound of 40.0 seconds of
    # process CPU time, stands recorded in the fix
    # papers of rounds 10 to 17 in its standing as a pin
    # form derived from the backstop judgement on this
    # family.

    def _run_correct_at_scale(self, module, type_sets):
        components = module._similar_components(type_sets)
        self.assertEqual(len(components), len(type_sets))
        self.assertTrue(all(len(component) == 1
                            for component in components))

    def test_fourth_construction_detection_correct_at_scale(self):
        self._run_correct_at_scale(
            detection, _band_family(1200, 4000, 2250, 200000))

    def test_fourth_construction_metrics_correct_at_scale(self):
        self._run_correct_at_scale(
            metrics, _band_family(1200, 4000, 2250, 200000))

    def test_mixed_size_control_inside_bound(self):
        for module in (detection, metrics):
            self._run_inside_bound(module, _mixed_family(1200), 12.0)

    def test_cyclic_control_inside_bound(self):
        for module in (detection, metrics):
            self._run_inside_bound(
                module, _cyclic_family(2400), 20.0)


if __name__ == "__main__":
    unittest.main()
