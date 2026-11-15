# Step 17 round 8 fix seat F5 tests.
#
# Entries S17-R8-018 and S17-R8-019: two cost defects at the
# passes the fix round 7 cures rebuilt, correctness standing
# verified against direct pair computations written from the
# rule beside every cost series. Timing probes stand on
# process CPU time, never on wall clock. The registered
# constructions of round 7 stand as controls, and the round 8
# attack constructions stand as the failing probes, at the
# largest scales that run in reasonable time, with the
# projection to the cap stated in the seat paper.
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


def _direct_clique(type_sets):
    return all(
        len(type_sets[first] & type_sets[second]) * 9
        >= 4 * (len(type_sets[first]) + len(type_sets[second]))
        for first in range(len(type_sets))
        for second in range(first + 1, len(type_sets)))


def _shared_pool_family(count, seed=19):
    # The R8-DM-01 construction: every set a seeded random
    # 200 of one pool of 300 shingles, seed 19, no shingle of
    # its own. Two sets share about 133 shingles against the
    # threshold of 178 at size 200, so no pair stands similar
    # and the correct result is one singleton per set.
    rng = random.Random(seed)
    pool = list(range(300))
    return [set(rng.sample(pool, 200)) for _index in range(count)]


def _red_pool_family(count, seed=42):
    # The S17-R8-RED-01 construction: every set a seeded
    # random 200 of one pool of 2,000 shingles, seed 42, each
    # shingle standing in about a tenth of the sets, two sets
    # sharing about 20 shingles against the threshold of 178.
    rng = random.Random(seed)
    pool = list(range(2000))
    return [set(rng.sample(pool, 200)) for _index in range(count)]


def _registered_pool_family(count, seed=7):
    # The registered construction of S17-R7-035, standing as
    # a control: a pool of 170 shingles, each set holding a
    # seeded random 100 of the pool plus 100 shingles of its
    # own, size 200 throughout, no pair similar.
    rng = random.Random(seed)
    pool = list(range(170))
    type_sets = []
    for index in range(count):
        own = {100000 + index * 100 + offset for offset in range(100)}
        type_sets.append(set(rng.sample(pool, 100)) | own)
    return type_sets


def _wide_clique_family(count, seed=31):
    # The R8-DM-02 construction: the pivot holds 900 parts,
    # each further set misses exactly 95 parts of a 200 part
    # pool of the pivot, the pattern drawn with seed 31, and
    # adds a common core of 70 parts plus 25 parts it shares
    # with exactly one partner set, size 900 throughout. Any
    # two sets share at least 800 parts, the pair threshold
    # at size 900, so the family is a true clique.
    rng = random.Random(seed)
    pivot = set(range(900))
    pool = list(range(200))
    core = set(range(3000, 3070))
    type_sets = [pivot]
    for index in range(count - 1):
        partner = index // 2
        partner_parts = set(range(5000 + partner * 25,
                                  5000 + partner * 25 + 25))
        missed = set(rng.sample(pool, 95))
        type_sets.append((pivot - missed) | core | partner_parts)
    return type_sets


def _registered_clique_family(count, seed=11):
    # The registered construction of S17-R7-036, standing as
    # a control: each further set misses a seeded random 85
    # to 100 parts of a 170 part pool and adds a common core
    # of 70 plus parts of its own, size 900, a true clique.
    rng = random.Random(seed)
    pivot = set(range(900))
    pool = list(range(170))
    core = set(range(10000, 10070))
    type_sets = [pivot]
    uid = 20000
    for _index in range(count - 1):
        missed_count = rng.randint(85, 100)
        missed = set(rng.sample(pool, missed_count))
        own_count = missed_count - 70
        own = set(range(uid, uid + own_count))
        uid += own_count
        type_sets.append((pivot - missed) | core | own)
    return type_sets


def _deferred_family(links, per_pair=120, seed=9000):
    # The registered construction of S17-R7-048, standing as
    # a control, in the form the round 7 seat states it.
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


class TestR8F5SeedPassSharedPool(unittest.TestCase):
    # S17-R8-018, detection and metrics copies.

    def test_shared_pool_correct_small_both_copies(self):
        type_sets = _shared_pool_family(300)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 300)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_red_pool_correct_small_both_copies(self):
        type_sets = _red_pool_family(120)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 120)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_shared_pool_detection_inside_bound(self):
        type_sets = _shared_pool_family(2400)
        start = time.process_time()
        components = detection._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 2400)
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, 5.0)

    def test_shared_pool_metrics_inside_bound(self):
        type_sets = _shared_pool_family(2400)
        start = time.process_time()
        components = metrics._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 2400)
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, 5.0)

    def test_red_pool_detection_inside_bound(self):
        type_sets = _red_pool_family(2000)
        start = time.process_time()
        components = detection._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 2000)
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, 5.0)

    def test_red_pool_metrics_inside_bound(self):
        type_sets = _red_pool_family(2000)
        start = time.process_time()
        components = metrics._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 2000)
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, 5.0)

    def test_registered_pool_family_control_both_copies(self):
        type_sets = _registered_pool_family(2400)
        for module in (detection, metrics):
            start = time.process_time()
            components = module._similar_components(type_sets)
            cpu = time.process_time() - start
            self.assertEqual(len(components), 2400)
            self.assertLess(cpu, 5.0)


class TestR8F5WideClique(unittest.TestCase):
    # S17-R8-019, metrics copy only.

    def test_wide_clique_correct_small(self):
        type_sets = _wide_clique_family(160)
        self.assertTrue(_direct_clique(type_sets))
        self.assertTrue(metrics._sets_clique(type_sets))

    def test_wide_clique_broken_pair_at_scan_scale(self):
        # A family past the scan scale where two sets of the
        # rest each stand similar to the pivot, so the pivot
        # reading does not settle the family, and their pair
        # falls under the threshold: the first misses the
        # first half of the pool and the second misses the
        # second half, so their missed union stands at the
        # whole pool. Judged against the direct computation.
        type_sets = _wide_clique_family(350)
        pivot = type_sets[0]
        core = set(range(3000, 3070))
        first = (pivot - set(range(100))) | core | set(
            range(5000, 5025))
        second = (pivot - set(range(100, 200))) | core | set(
            range(5025, 5050))
        type_sets[10] = first
        type_sets[20] = second
        self.assertFalse(_direct_clique(type_sets))
        self.assertFalse(metrics._sets_clique(type_sets))

    def test_wide_clique_true_at_scan_scale(self):
        type_sets = _wide_clique_family(350)
        self.assertTrue(metrics._sets_clique(type_sets))

    def test_wide_clique_inside_bound_at_4000(self):
        type_sets = _wide_clique_family(4000)
        start = time.process_time()
        result = metrics._sets_clique(type_sets)
        cpu = time.process_time() - start
        self.assertTrue(result)
        self.assertLess(cpu, 5.0)

    def test_wide_clique_inside_bound_at_8000(self):
        type_sets = _wide_clique_family(8000)
        start = time.process_time()
        result = metrics._sets_clique(type_sets)
        cpu = time.process_time() - start
        self.assertTrue(result)
        self.assertLess(cpu, 15.0)

    def test_registered_clique_family_control(self):
        type_sets = _registered_clique_family(4000)
        start = time.process_time()
        result = metrics._sets_clique(type_sets)
        cpu = time.process_time() - start
        self.assertTrue(result)
        self.assertLess(cpu, 5.0)


class TestR8F5StandingControls(unittest.TestCase):
    # The round 7 cures that must keep holding, and the
    # differentials of this seat.

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

    def test_component_differential_mixed_families(self):
        rng = random.Random(37)
        families = []
        for _trial in range(30):
            count = rng.randint(2, 25)
            universe = list(range(rng.randint(10, 120)))
            families.append([
                set(rng.sample(universe,
                               rng.randint(1, len(universe))))
                for _index in range(count)])
        families.append(_shared_pool_family(40, seed=5))
        families.append(_red_pool_family(40, seed=6))
        base = set(range(200))
        cluster = []
        for index in range(12):
            member = set(base)
            member -= set(range(index * 3, index * 3 + 12))
            member |= {700000 + index * 20 + offset
                       for offset in range(12)}
            cluster.append(member)
        families.append(cluster)
        for type_sets in families:
            type_sets = [item for item in type_sets if item]
            expected = _brute_components(type_sets)
            for module in (detection, metrics):
                self.assertEqual(
                    _components_as_sets(module, type_sets), expected)

    def test_clique_differential_random(self):
        rng = random.Random(29)
        for _trial in range(60):
            count = rng.randint(2, 14)
            universe = list(range(rng.randint(5, 60)))
            type_sets = []
            for _index in range(count):
                size = rng.randint(1, len(universe))
                type_sets.append(set(rng.sample(universe, size)))
            self.assertEqual(
                metrics._sets_clique(type_sets),
                _direct_clique(type_sets))


if __name__ == "__main__":
    unittest.main()
