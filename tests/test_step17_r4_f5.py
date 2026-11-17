"""Detection and metrics.

Each test pins one register entry from the findings
register, in the form the register states. Written before
the cures, watched failing, then watched passing."""

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
RIVALCO = {"name": "RivalCo", "aliases": [], "domain": "rival.example.com"}
RIVAL = {"name": "Rival", "aliases": [], "domain": "rival.example.com"}
SEP = "。"
SEPS = ["。", "．", "｡"]


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def competitor_outcome(result, name):
    for entry in field(result, "per_competitor"):
        if field(entry, "name") == name:
            return entry
    raise AssertionError("no competitor outcome for " + name)


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


def chain_texts(count):
    words = ["w%d" % index for index in range(3 * count + 40)]
    texts = []
    for index in range(count):
        start = 3 * index
        texts.append(" ".join(words[start:start + 34]))
    return texts


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


class TestChainCost037(unittest.TestCase):
    def test_detection_chain_250_inside_bound(self):
        texts = chain_texts(250)
        start = time.perf_counter()
        clusters = detection.cluster_answers(texts)
        elapsed = time.perf_counter() - start
        self.assertEqual(len(set(clusters)), 1)
        self.assertLess(elapsed, 5.0,
                        "chain of 250 took %.2f seconds" % elapsed)

    def test_metrics_chain_250_chained_and_fast(self):
        texts = chain_texts(250)
        rows = [answer(text=text, cluster_id=7) for text in texts]
        start = time.perf_counter()
        result = metrics.round_metrics(rows, "sampled")
        elapsed = time.perf_counter() - start
        self.assertEqual(field(result, "chained_cluster_count"), 1)
        self.assertLess(elapsed, 5.0,
                        "metrics chain of 250 took %.2f seconds" % elapsed)

    def test_component_differential_random(self):
        rng = random.Random(20261114)
        for trial in range(60):
            vocab = list(range(rng.randint(5, 18)))
            families = []
            for _ in range(rng.randint(1, 14)):
                size = rng.randint(1, len(vocab))
                families.append(frozenset(rng.sample(vocab, size)))
            got = {frozenset(component)
                   for component in detection._similar_components(families)}
            self.assertEqual(got, brute_components(families))
            got_metrics = {frozenset(component)
                           for component in metrics._similar_components(families)}
            self.assertEqual(got_metrics, brute_components(families))


class TestCliqueSeam038(unittest.TestCase):
    def clique_sets(self, count):
        pivot = set(range(30))
        result = [frozenset(pivot)]
        for missing in itertools.combinations(range(30), 3):
            result.append(frozenset((pivot - set(missing)) | {999}))
            if len(result) - 1 >= count:
                break
        return result

    def test_clique_1000_distinct_patterns_inside_bound(self):
        sets = self.clique_sets(1000)
        start = time.perf_counter()
        outcome = metrics._sets_clique(sets)
        elapsed = time.perf_counter() - start
        self.assertTrue(outcome)
        self.assertLess(elapsed, 3.0,
                        "clique of 1000 took %.2f seconds" % elapsed)

    def test_clique_chained_wrapper_on_same_shape(self):
        sets = self.clique_sets(300)
        self.assertFalse(metrics._cluster_chained(sets))

    def test_clique_false_case_still_found(self):
        pivot = set(range(30))
        first = frozenset(pivot)
        second = frozenset((pivot - {0, 1, 2, 3, 4, 5}) | {100, 101})
        third = frozenset((pivot - {10, 11, 12, 13, 14, 15}) | {200, 201})
        self.assertFalse(metrics._sets_clique([first, second, third]))

    def test_clique_differential_random(self):
        rng = random.Random(417)
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


class TestSeparatorMapping039(unittest.TestCase):
    def test_entry_target_separator_cited(self):
        for sep in SEPS:
            text = ("See the guide [7] for details.\n\n## References\n\n"
                    "7. rival" + sep + "example" + sep + "com/guide\n")
            result = detection.detect_answer(text, PRODUCT, [RIVALCO])
            outcome = competitor_outcome(result, "RivalCo")
            self.assertTrue(field(outcome, "cited"), sep)

    def test_entry_target_ascii_control(self):
        text = ("See the guide [7] for details.\n\n## References\n\n"
                "7. rival.example.com/guide\n")
        result = detection.detect_answer(text, PRODUCT, [RIVALCO])
        self.assertTrue(field(
            competitor_outcome(result, "RivalCo"), "cited"))

    def test_item_lines_separator_open_references(self):
        for sep in SEPS:
            text = ("Some prose about tools.\n\n"
                    "northbeam" + sep + "example" + sep + "com\n"
                    "rival" + sep + "example" + sep + "com\n")
            result = detection.detect_answer(text, PRODUCT, [RIVALCO])
            self.assertFalse(field(result, "named"), sep)
            self.assertEqual(field(result, "references_named_count"), 1, sep)

    def test_bare_domain_token_separator_masked(self):
        for sep in SEPS:
            text = "See rival" + sep + "example" + sep + "com/Acme for details"
            comp = {"name": "Acme", "aliases": [], "domain": "acme.example.com"}
            result = detection.detect_answer(text, PRODUCT, [comp])
            outcome = competitor_outcome(result, "Acme")
            self.assertFalse(field(outcome, "named"), sep)


class TestItemLineQueryFragment040(unittest.TestCase):
    def test_trailing_lines_with_query_open_references(self):
        text = ("Some prose about tools.\n"
                "northbeam.example.com?ref=1\n"
                "rival.example.com?ref=2\n")
        result = detection.detect_answer(text, PRODUCT, [RIVAL])
        self.assertFalse(field(result, "named"))
        self.assertEqual(field(result, "references_named_count"), 1)

    def test_trailing_lines_with_fragment_open_references(self):
        text = ("Some prose about tools.\n"
                "northbeam.example.com#part\n"
                "rival.example.com#part\n")
        result = detection.detect_answer(text, PRODUCT, [RIVAL])
        self.assertFalse(field(result, "named"))
        self.assertEqual(field(result, "references_named_count"), 1)


class TestLinkBalancedParentheses041(unittest.TestCase):
    def test_bare_destination_balanced_parentheses_masked(self):
        text = "See [the page](https://example.com/f()Northbeam) now"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))
        self.assertEqual(field(result, "matched_aliases"), [])

    def test_bare_destination_nested_balanced_parentheses_masked(self):
        text = "See [the page](https://example.com/f(x(y))Northbeam) now"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))

    def test_angle_destination_control(self):
        text = "See [the page](<https://example.com/f()Northbeam>) now"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))

    def test_plain_link_still_masked(self):
        text = "See [the page](https://example.com/Northbeam) now"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))


class TestCompetitorMappingShape042(unittest.TestCase):
    def check_refused(self, value):
        row = answer(per_competitor={"Rival": value})
        with self.assertRaises(ValueError):
            metrics.round_metrics([row], "sampled")

    def test_mapping_string_value_refused(self):
        self.check_refused("yes")

    def test_mapping_list_value_refused(self):
        self.check_refused(["x"])

    def test_mapping_list_holding_bad_record_refused(self):
        self.check_refused([{"name": 7, "named": True}])

    def test_mapping_zero_value_refused(self):
        self.check_refused(0)

    def test_mapping_null_value_refused(self):
        self.check_refused(None)

    def test_mapping_record_value_control(self):
        row = answer(per_competitor={"Rival": {"name": "Rival", "named": True}})
        result = metrics.round_metrics([row], "sampled")
        self.assertEqual(
            field(field(result, "per_competitor")["Rival"], "named_count"), 1)


class TestBooleanFields043(unittest.TestCase):
    def check_refused(self, field_name, value):
        row = answer(**{field_name: value})
        with self.assertRaises(ValueError):
            metrics.round_metrics([row], "sampled")

    def test_control_flag_string_refused(self):
        self.check_refused("control_flag", "false")

    def test_control_string_refused(self):
        self.check_refused("control", "false")

    def test_competitor_named_string_refused(self):
        self.check_refused("competitor_named", "false")

    def test_boolean_controls_pass(self):
        row = answer(control_flag=False, control=False, competitor_named=False)
        result = metrics.round_metrics([row], "sampled")
        self.assertEqual(field(result, "control_count"), 0)
        self.assertEqual(field(result, "no_name_count"), 1)


if __name__ == "__main__":
    unittest.main()
