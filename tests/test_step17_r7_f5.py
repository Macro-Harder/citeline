# Verdict tests. Entries, and: three cost defects,
# correctness standing verified by differential in the attack
# papers and rechecked here against a direct pair
# computation. Timing probes stand on process CPU time, never
# on wall clock, at the attack scales or the largest scale
# that runs in reasonable time on the uncured tree, with the
# projection to the cap stated in the repair notes. Copyright:
# J.P. Picard aka Macro-Harder.

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


def _pool_family(count, seed=7):
    # The R7-DM-01 construction: a pool of 170 shingles, each
    # set holding a seeded random 100 of the pool plus 100
    # shingles of its own, size 200 throughout. No pair can
    # stand similar: a pair shares at most its 100 pool
    # shingles, under the 178 the rule needs at size 200.
    rng = random.Random(seed)
    pool = list(range(170))
    type_sets = []
    for index in range(count):
        own = {100000 + index * 100 + offset for offset in range(100)}
        type_sets.append(set(rng.sample(pool, 100)) | own)
    return type_sets


def _clique_family(count, seed=11):
    # The R7-DM-02 construction: the pivot holds 900 parts,
    # each further set misses a seeded random 85 to 100 parts
    # of a 170 part pool of the pivot and adds a common core
    # of 70 parts plus parts of its own, size 900 throughout.
    # Any two sets share at least 800 parts, exactly the pair
    # threshold at size 900, so the family is a true clique.
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
    # The construction in the form the attack states: every
    # set holds 300 shingles, a core of 60 held by every set,
    # chain links holding a 240 shingle segment sliding by 33
    # so a link stands similar to its two neighbours and to
    # no other link, and 120 reject copies per link pair,
    # each holding the core, a 175 shingle turning subset of
    # the pair shared segment, and 65 shingles of its own,
    # sharing 235 with the links of its pair, under the 267
    # the rule needs at size 300.
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


class TestR7F5SeedCountingPass(unittest.TestCase):
    # , detection and metrics copies.

    def test_pool_family_correct_small_both_copies(self):
        type_sets = _pool_family(60)
        expected = _brute_components(type_sets)
        self.assertEqual(len(expected), 60)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_pool_family_detection_inside_backstop(self):
        type_sets = _pool_family(2400)
        start = time.process_time()
        components = detection._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 2400)
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, 5.0)

    def test_pool_family_metrics_inside_backstop(self):
        type_sets = _pool_family(2400)
        start = time.process_time()
        components = metrics._similar_components(type_sets)
        cpu = time.process_time() - start
        self.assertEqual(len(components), 2400)
        self.assertTrue(all(len(component) == 1
                            for component in components))
        self.assertLess(cpu, 5.0)


class TestR7F5SetsClique(unittest.TestCase):
    # , metrics copy only.

    def test_clique_family_true_small(self):
        type_sets = _clique_family(60)
        self.assertTrue(metrics._sets_clique(type_sets))

    def test_clique_family_false_variant(self):
        type_sets = _clique_family(60)
        broken = set(type_sets[5])
        broken -= set(range(400, 700))
        broken |= {900000 + offset for offset in range(300)}
        type_sets[5] = broken
        self.assertFalse(metrics._sets_clique(type_sets))

    def test_clique_differential_random(self):
        rng = random.Random(23)
        for _trial in range(60):
            count = rng.randint(2, 14)
            universe = list(range(rng.randint(5, 60)))
            type_sets = []
            for _index in range(count):
                size = rng.randint(1, len(universe))
                type_sets.append(set(rng.sample(universe, size)))
            expected = all(
                len(type_sets[first] & type_sets[second]) * 9
                >= 4 * (len(type_sets[first]) + len(type_sets[second]))
                for first in range(count)
                for second in range(first + 1, count))
            self.assertEqual(metrics._sets_clique(type_sets), expected)

    def test_clique_group_scan_differential_unique_added(self):
        # Families whose sets add parts of their own beside a
        # shared core, with missed patterns drawn from a wide
        # pool, so the bulk bounds leave pairs open and the
        # group pair scan carries the judgement. Judged
        # against the direct pair computation.
        rng = random.Random(41)
        for _trial in range(80):
            pivot = set(range(120))
            core = set(range(5000, 5040))
            count = rng.randint(2, 16)
            type_sets = [pivot]
            uid = 9000
            for _index in range(count - 1):
                missed = set(rng.sample(range(120),
                                        rng.randint(0, 25)))
                own = set(range(uid, uid + rng.randint(0, 25)))
                uid += 25
                shared_core = set(rng.sample(
                    sorted(core), rng.randint(20, 40)))
                type_sets.append((pivot - missed) | shared_core | own)
            expected = all(
                len(type_sets[first] & type_sets[second]) * 9
                >= 4 * (len(type_sets[first]) + len(type_sets[second]))
                for first in range(count)
                for second in range(first + 1, count))
            self.assertEqual(metrics._sets_clique(type_sets), expected)

    def test_clique_family_inside_backstop_at_seam_scale(self):
        type_sets = _clique_family(4000)
        start = time.process_time()
        result = metrics._sets_clique(type_sets)
        cpu = time.process_time() - start
        self.assertTrue(result)
        self.assertLess(cpu, 5.0)


class TestR7F5SecondQueuePass(unittest.TestCase):
    # , detection and metrics copies.

    def test_deferred_family_correct_small_both_copies(self):
        type_sets = _deferred_family(8, per_pair=6)
        expected = _brute_components(type_sets)
        largest = max(len(group) for group in expected)
        self.assertEqual(largest, 8)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_deferred_family_heavy_differential_both_copies(self):
        # At 120 copies per pair the shared segment shingles
        # stand heavy, over the 96 bound the first queue
        # states, so the links and the rejects stand deferred
        # and the second queue carries the chain. The result
        # stands judged against the direct pair computation.
        type_sets = _deferred_family(6, per_pair=120)
        expected = _brute_components(type_sets)
        self.assertEqual(max(len(group) for group in expected), 6)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_deferred_family_interleaved_differential(self):
        # The same family with the rejects standing between
        # the links in the input order, so the seeds and the
        # deferrals land in a different order.
        links = _deferred_family(5, per_pair=0)
        rejects = _deferred_family(5, per_pair=120)[5:]
        type_sets = []
        block = 120
        for index, link in enumerate(links):
            type_sets.append(link)
            type_sets.extend(
                rejects[index * block:(index + 1) * block])
        type_sets.extend(rejects[len(links) * block:])
        expected = _brute_components(type_sets)
        self.assertEqual(max(len(group) for group in expected), 5)
        for module in (detection, metrics):
            self.assertEqual(
                _components_as_sets(module, type_sets), expected)

    def test_deferred_family_detection_inside_backstop(self):
        type_sets = _deferred_family(25)
        start = time.process_time()
        components = detection._similar_components(type_sets)
        cpu = time.process_time() - start
        sizes = sorted((len(component) for component in components),
                       reverse=True)
        self.assertEqual(sizes[0], 25)
        self.assertTrue(all(size == 1 for size in sizes[1:]))
        self.assertLess(cpu, 8.0)

    def test_deferred_family_metrics_inside_backstop(self):
        type_sets = _deferred_family(25)
        start = time.process_time()
        components = metrics._similar_components(type_sets)
        cpu = time.process_time() - start
        sizes = sorted((len(component) for component in components),
                       reverse=True)
        self.assertEqual(sizes[0], 25)
        self.assertTrue(all(size == 1 for size in sizes[1:]))
        self.assertLess(cpu, 8.0)


class TestR7F5ComponentDifferential(unittest.TestCase):
    # Differential controls over mixed families, both copies.

    def test_component_differential_mixed_families(self):
        rng = random.Random(31)
        families = []
        # Random heterogeneous sets.
        for _trial in range(30):
            count = rng.randint(2, 25)
            universe = list(range(rng.randint(10, 120)))
            families.append([
                set(rng.sample(universe,
                               rng.randint(1, len(universe))))
                for _index in range(count)])
        # Chains with reject pools at small sizes.
        for links in (4, 6, 9):
            families.append(_deferred_family(links, per_pair=4))
        # Varying subset pool family at a small size.
        families.append(_pool_family(40, seed=3))
        # Near duplicate clusters.
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


if __name__ == "__main__":
    unittest.main()
