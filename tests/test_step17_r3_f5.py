"""Detection and metrics.

Each test pins one register entry from the findings
register, in the form the register states. Written before
the cures, watched failing, then watched passing."""

import random
import time
import tracemalloc
import unicodedata
import unittest

from citeline import detection, metrics

PRODUCT = {
    "name": "Northbeam",
    "aliases": ["Northbeam Analytics", "Guide"],
    "domain": "northbeam.example.com",
}
RIVAL = {"name": "Rival", "aliases": [], "domain": "rival.example.com"}
COMPETITOR = {
    "name": "CompetitorCo", "aliases": [], "domain": "rival.example.com"}


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


class TestBareDomainSeparatorForms030(unittest.TestCase):
    def check_separator(self, separator):
        text = ("Visit rival" + separator + "example" + separator
                + "com today.")
        result = detection.detect_answer(text, PRODUCT, [COMPETITOR])
        self.assertTrue(
            field(competitor_outcome(result, "CompetitorCo"), "named"),
            text)

    def test_ideographic_full_stop_separator(self):
        self.check_separator("。")

    def test_fullwidth_full_stop_separator(self):
        self.check_separator("．")

    def test_halfwidth_ideographic_separator(self):
        self.check_separator("｡")

    def test_ascii_domain_control(self):
        result = detection.detect_answer(
            "Visit rival.example.com today.", PRODUCT, [COMPETITOR])
        self.assertTrue(
            field(competitor_outcome(result, "CompetitorCo"), "named"))


class TestReferencesHeadingHeadMarks031(unittest.TestCase):
    def check_atx(self, heading):
        text = ("Plain prose about tools.\n\n" + heading + "\n\n"
                "Northbeam at https://northbeam.example.com/a\n")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"), heading)
        self.assertFalse(field(result, "cited"), heading)
        self.assertEqual(field(result, "references_target_count"), 1)

    def check_setext(self, heading_text):
        text = ("Plain prose about tools.\n\n" + heading_text
                + "\n==========\n\n"
                "Northbeam at https://northbeam.example.com/a\n")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"), heading_text)
        self.assertFalse(field(result, "cited"), heading_text)
        self.assertEqual(field(result, "references_target_count"), 1)

    def test_atx_bold_heading(self):
        self.check_atx("## **References**")

    def test_atx_italic_heading(self):
        self.check_atx("## *References*")

    def test_atx_single_quoted_heading(self):
        self.check_atx("## 'References'")

    def test_atx_double_quoted_heading(self):
        self.check_atx('## "References"')

    def test_setext_bold_heading(self):
        self.check_setext("**References**")

    def test_setext_italic_heading(self):
        self.check_setext("*References*")

    def test_setext_single_quoted_heading(self):
        self.check_setext("'References'")


class TestReferenceDefinitionTitleLine032(unittest.TestCase):
    def check_title_line(self, title_line):
        text = ("[nb]: https://example.com/x\n" + title_line
                + "\n\nPlain prose.\n")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"), title_line)
        self.assertEqual(field(result, "matched_aliases"), [])

    def test_double_quoted_title_on_unindented_line(self):
        self.check_title_line('"Northbeam guide"')

    def test_single_quoted_title_on_unindented_line(self):
        self.check_title_line("'Northbeam guide'")

    def test_parenthesis_title_on_unindented_line(self):
        self.check_title_line("(Northbeam guide)")


class TestReferenceDefinitionMaskWhole033(unittest.TestCase):
    def test_unquoted_words_after_destination_are_prose(self):
        text = ("[nb]: https://example.com/x Northbeam guide words\n"
                "\nPlain prose.")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertIn("Northbeam", field(result, "matched_aliases"))

    def test_prose_sentence_in_label_form_is_prose(self):
        text = "[Note]: Northbeam is great and stands here.\n\nPlain prose."
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertTrue(field(result, "named"))

    def test_quoted_title_after_destination_still_masked(self):
        text = ('[nb]: https://example.com/x "Northbeam guide"\n'
                "\nPlain prose.")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))


class TestBareDomainTokenTrailingDotPort034(unittest.TestCase):
    def test_path_alias_after_trailing_dot_and_port_is_no_mention(self):
        result = detection.detect_answer(
            "See northbeam.example.com.:8080/guide for details.",
            PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertEqual(field(result, "matched_aliases"), [])

    def test_references_domain_trailing_dot_port_path_counts_once(self):
        text = "## References\n\n1. northbeam.example.com.:8080/guide\n"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertEqual(field(result, "references_named_count"), 1)


class TestBareEntryTargetTrailingDot035(unittest.TestCase):
    def check_entry(self, entry):
        text = ("Tools compared [7].\n\n## References\n\n" + entry + "\n")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertTrue(field(result, "cited"), entry)
        self.assertEqual(field(result, "unresolved_form_count"), 0)

    def test_bare_entry_trailing_dot_before_path(self):
        self.check_entry("7. northbeam.example.com./guide")

    def test_bare_entry_trailing_dot_before_port(self):
        self.check_entry("7. northbeam.example.com.:8080/guide")

    def test_bare_entry_trailing_dot_alone_control(self):
        self.check_entry("7. northbeam.example.com.")


class TestLinkTargetMaskTitleParenthesis036(unittest.TestCase):
    def check_link(self, link):
        result = detection.detect_answer(
            "See [the page](" + link + ") now.", PRODUCT, [])
        self.assertFalse(field(result, "named"), link)
        self.assertEqual(field(result, "matched_aliases"), [])

    def test_double_quoted_title_holding_closing_parenthesis(self):
        self.check_link(
            'https://example.com/x "Guide ) Northbeam title"')

    def test_single_quoted_title_holding_closing_parenthesis(self):
        self.check_link(
            "https://example.com/x 'Guide ) Northbeam title'")

    def test_parenthesis_title_holding_closing_parenthesis(self):
        self.check_link(
            "https://example.com/x (Guide ) Northbeam title)")


class TestItemLinePortAndTrailingDot037(unittest.TestCase):
    def check_lines(self, lines):
        text = "Some prose about tools here.\n\n" + "\n".join(lines) + "\n"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"), text)
        self.assertEqual(field(result, "references_named_count"), 1)

    def test_bare_host_lines_with_port_and_path(self):
        self.check_lines([
            "northbeam.example.com:8080/guide",
            "rival.example.com:8080/x",
        ])

    def test_bare_host_lines_with_port_alone(self):
        self.check_lines([
            "northbeam.example.com:8080",
            "rival.example.com:8080",
        ])

    def test_bare_host_lines_with_trailing_dot(self):
        self.check_lines([
            "northbeam.example.com.",
            "rival.example.com.",
        ])

    def test_marker_led_bare_host_lines_with_port(self):
        self.check_lines([
            "- northbeam.example.com:8080/guide",
            "- rival.example.com:8080/x",
        ])


class TestDomainBoundaryUnderscore038(unittest.TestCase):
    def test_domain_glued_to_underscore_label_before(self):
        result = detection.detect_answer(
            "See a_northbeam.example.com now.", PRODUCT, [])
        self.assertFalse(field(result, "named"))

    def test_domain_glued_to_underscore_label_after_dot(self):
        result = detection.detect_answer(
            "See northbeam.example.com._evil now.", PRODUCT, [])
        self.assertFalse(field(result, "named"))


def scan_clique_rows(count):
    core = ["c%02d" % i for i in range(27)]
    rows = []
    for i in range(count):
        words = core + ["p%04d" % (i % 50), "q%05d" % i]
        rows.append(answer(cluster_id=0, text=" ".join(words)))
    return rows


def mixed_clique_texts(count):
    texts = []
    for i in range(count):
        if i % 2 == 0:
            words = (["a%02d" % k for k in range(27)]
                     + ["p%02d" % (i % 40), "q%05d" % i])
        else:
            words = (["b%02d" % k for k in range(28)]
                     + ["p%02d" % (i % 40), "q%05d" % i])
        texts.append(" ".join(words))
    return texts


def big_size_clique_rows(count):
    rows = []
    for i in range(count):
        if i % 2 == 0:
            words = (["a%02d" % k for k in range(32)]
                     + ["p%02d" % (i % 40), "q%05d" % i])
        else:
            words = (["b%02d" % k for k in range(32)]
                     + ["p%02d" % (i % 40), "q%05d" % i])
        rows.append(answer(cluster_id=0, text=" ".join(words)))
    return rows


def disjoint_texts(count):
    texts = []
    for i in range(count):
        words = ["t%05d_%02d" % (i, k) for k in range(29)]
        texts.append(" ".join(words))
    return texts


def brute_cluster_partition(texts):
    def norm(value):
        return " ".join(
            unicodedata.normalize("NFC", str(value)).casefold().split())

    def shingles(norm_text):
        words = norm_text.split()
        if len(words) < 5:
            return set()
        return {tuple(words[i:i + 5]) for i in range(len(words) - 4)}

    normalised = [norm(text) for text in texts]
    sets = [shingles(text) for text in normalised]
    parent = list(range(len(texts)))

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for first in range(len(texts)):
        for second in range(first + 1, len(texts)):
            first_set, second_set = sets[first], sets[second]
            if not first_set or not second_set:
                similar = normalised[first] == normalised[second]
            else:
                shared = len(first_set & second_set)
                union_size = len(first_set) + len(second_set) - shared
                similar = union_size > 0 and shared / union_size >= 0.80
            if similar:
                root_first, root_second = find(first), find(second)
                if root_first != root_second:
                    parent[max(root_first, root_second)] = min(
                        root_first, root_second)
    groups = {}
    for index in range(len(texts)):
        groups.setdefault(find(index), set()).add(index)
    return {frozenset(group) for group in groups.values()}


def brute_chained(texts):
    def norm(value):
        return " ".join(
            unicodedata.normalize("NFC", str(value)).casefold().split())

    def shingles(norm_text):
        words = norm_text.split()
        if len(words) < 5:
            return set()
        return {" ".join(words[i:i + 5]) for i in range(len(words) - 4)}

    count = len(texts)
    if count < 2:
        return False
    normalised = [norm(text) for text in texts]
    sets = [shingles(text) for text in normalised]
    parent = list(range(count))

    def find(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    similar_any = False
    nonsimilar_any = False
    for first in range(count):
        for second in range(first + 1, count):
            first_set, second_set = sets[first], sets[second]
            if not first_set or not second_set:
                similar = normalised[first] == normalised[second]
            else:
                shared = len(first_set & second_set)
                union_size = len(first_set) + len(second_set) - shared
                similar = union_size > 0 and shared / union_size >= 0.80
            if similar:
                similar_any = True
                root_first, root_second = find(first), find(second)
                if root_first != root_second:
                    parent[root_first] = root_second
            else:
                nonsimilar_any = True
    return (len({find(i) for i in range(count)}) == 1
            and similar_any and nonsimilar_any)


class TestClusterCostShape039(unittest.TestCase):
    def test_metrics_scan_clique_at_cap_inside_backstop(self):
        rows = scan_clique_rows(10000)
        start = time.perf_counter()
        result = metrics.round_metrics(rows, "sampled")
        elapsed = time.perf_counter() - start
        self.assertEqual(field(result, "imported_count"), 10000)
        self.assertEqual(field(result, "chained_cluster_count"), 0)
        self.assertLess(elapsed, 60.0,
                        "scan clique cap round took %.2fs" % elapsed)

    def test_metrics_mixed_size_pair_loop_shape_at_cap(self):
        rows = [answer(cluster_id=0, text=text)
                for text in mixed_clique_texts(10000)]
        start = time.perf_counter()
        result = metrics.round_metrics(rows, "sampled")
        elapsed = time.perf_counter() - start
        self.assertEqual(field(result, "imported_count"), 10000)
        self.assertEqual(field(result, "chained_cluster_count"), 0)
        self.assertLess(elapsed, 60.0,
                        "mixed size cap round took %.2fs" % elapsed)

    def test_metrics_big_size_pair_loop_shape_at_cap(self):
        rows = big_size_clique_rows(10000)
        start = time.perf_counter()
        result = metrics.round_metrics(rows, "sampled")
        elapsed = time.perf_counter() - start
        self.assertEqual(field(result, "imported_count"), 10000)
        self.assertEqual(field(result, "chained_cluster_count"), 0)
        self.assertLess(elapsed, 60.0,
                        "big size cap round took %.2fs" % elapsed)

    def test_detection_mixed_cliques_at_cap(self):
        texts = mixed_clique_texts(10000)
        start = time.perf_counter()
        result = detection.cluster_answers(texts)
        elapsed = time.perf_counter() - start
        self.assertEqual(len(set(result)), 2)
        self.assertLess(elapsed, 60.0,
                        "detection cap clustering took %.2fs" % elapsed)

    def test_detection_disjoint_at_cap(self):
        texts = disjoint_texts(10000)
        start = time.perf_counter()
        result = detection.cluster_answers(texts)
        elapsed = time.perf_counter() - start
        self.assertEqual(len(set(result)), 10000)
        self.assertLess(elapsed, 60.0,
                        "detection disjoint cap took %.2fs" % elapsed)

    def test_detection_subset_index_memory_shape(self):
        texts = disjoint_texts(4000)
        tracemalloc.start()
        try:
            result = detection.cluster_answers(texts)
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(len(set(result)), 4000)
        self.assertLess(peak, 200 * 1024 * 1024,
                        "subset memory shape peaked at %d bytes" % peak)

    def test_cluster_answers_differential_against_direct_pairs(self):
        rng = random.Random(20261114)
        vocab = ["w%02d" % i for i in range(40)]
        for _trial in range(150):
            count = rng.randrange(0, 11)
            texts = []
            for _index in range(count):
                mode = rng.randrange(4)
                if mode == 0 and texts:
                    words = rng.choice(texts).split()
                    for _change in range(rng.randrange(1, 3)):
                        if words:
                            words[rng.randrange(len(words))] = (
                                rng.choice(vocab))
                    texts.append(" ".join(words))
                elif mode == 1:
                    texts.append(" ".join(
                        rng.choice(vocab) for _ in range(rng.randrange(0, 5))))
                else:
                    texts.append(" ".join(
                        rng.choice(vocab)
                        for _ in range(rng.randrange(5, 26))))
            expected = brute_cluster_partition(texts)
            result = detection.cluster_answers(texts)
            groups = {}
            for index, cluster_id in enumerate(result):
                groups.setdefault(cluster_id, set()).add(index)
            actual = {frozenset(group) for group in groups.values()}
            if not texts:
                actual = set()
            self.assertEqual(actual, expected, texts)

    def test_chained_differential_against_direct_pairs(self):
        rng = random.Random(20261115)
        vocab = ["w%02d" % i for i in range(36)]
        base_words = [rng.choice(vocab) for _ in range(24)]
        for _trial in range(150):
            count = rng.randrange(2, 9)
            texts = []
            for _index in range(count):
                mode = rng.randrange(4)
                if mode == 0:
                    words = list(base_words)
                    start = rng.randrange(0, 10)
                    for pos in range(start, min(len(words), start + 6)):
                        words[pos] = rng.choice(vocab)
                    texts.append(" ".join(words))
                elif mode == 1 and texts:
                    texts.append(texts[-1])
                else:
                    texts.append(" ".join(
                        rng.choice(vocab)
                        for _ in range(rng.randrange(5, 26))))
            expected = 1 if brute_chained(texts) else 0
            rows = [answer(cluster_id=0, text=text) for text in texts]
            result = metrics.round_metrics(rows, "sampled")
            self.assertEqual(
                field(result, "chained_cluster_count"), expected, texts)


class TestCompetitorEntryShape040(unittest.TestCase):
    def test_mapping_form_integer_name_refused(self):
        row = answer(per_competitor={
            "Rival": {"name": 7, "named": True, "cited": True}})
        with self.assertRaises(ValueError):
            metrics.round_metrics([row], "sampled")

    def test_mapping_form_list_name_refused(self):
        row = answer(per_competitor={
            "Rival": {"name": ["X"], "named": True}})
        with self.assertRaises(ValueError):
            metrics.round_metrics([row], "sampled")

    def test_list_form_string_entry_refused(self):
        row = answer(per_competitor=["Rival"])
        with self.assertRaises(ValueError):
            metrics.round_metrics([row], "sampled")

    def test_list_form_integer_entry_refused(self):
        row = answer(per_competitor=[7])
        with self.assertRaises(ValueError):
            metrics.round_metrics([row], "sampled")

    def test_competitors_argument_integer_entry_refused(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics([answer()], "sampled", competitors=[7])

    def test_competitors_argument_none_entry_refused(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics([answer()], "sampled", competitors=[None])

    def test_mapping_form_valid_entry_still_reports(self):
        row = answer(per_competitor={
            "Rival": {"name": "Rival", "named": True, "cited": True}})
        result = metrics.round_metrics([row], "sampled")
        report = field(result, "per_competitor")
        self.assertEqual(field(report["Rival"], "named_count"), 1)
        self.assertEqual(field(report["Rival"], "cited_rate"), 1.0)


class TestBooleanOutcomeShape041(unittest.TestCase):
    def test_named_as_string_refused(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics([answer(named="false")], "sampled")

    def test_named_early_as_string_refused(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics([answer(named_early="no")], "sampled")

    def test_cited_as_string_refused(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics([answer(cited="no")], "sampled")

    def test_competitor_cited_as_string_refused_list_form(self):
        row = answer(per_competitor=[
            {"name": "Rival", "named": True, "cited": "yes"}])
        with self.assertRaises(ValueError):
            metrics.round_metrics([row], "sampled")

    def test_competitor_cited_as_string_refused_mapping_form(self):
        row = answer(per_competitor={
            "Rival": {"name": "Rival", "named": True, "cited": "yes"}})
        with self.assertRaises(ValueError):
            metrics.round_metrics([row], "sampled")

    def test_boolean_outcomes_still_count(self):
        result = metrics.round_metrics(
            [answer(named=True, named_early=True, cited=True)], "sampled")
        rates = field(result, "rates")
        self.assertEqual(field(rates["named"], "rate"), 1.0)
        self.assertEqual(field(rates["cited"], "rate"), 1.0)


if __name__ == "__main__":
    unittest.main()
