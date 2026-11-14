"""Step 17 fix seat F5 tests, detection and metrics family.

Each test pins one register entry from the Step 17 round 1
findings register, in the form the register states. Written
before the cures, watched failing, then watched passing.
"""

import math
import time
import unittest

from citeline import detection, metrics

PRODUCT = {
    "name": "Northbeam",
    "aliases": ["Northbeam Analytics", "Guide"],
    "domain": "northbeam.example.com",
}
RIVAL = {"name": "Rival", "aliases": [], "domain": "rival.example.com"}


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


class TestDomainBoundary039(unittest.TestCase):
    def test_lookalike_hosts_are_not_named(self):
        for text in (
            "Visit northbeam.example.com.evil.com for details.",
            "Visit northbeam.example.com-evil.com for details.",
            "Visit evil-northbeam.example.com for details.",
            "Contact user@northbeam.example.com for info.",
        ):
            result = detection.detect_answer(text, PRODUCT, [])
            self.assertFalse(field(result, "named"), text)

    def test_competitor_lookalike_hosts_are_not_named(self):
        for text in (
            "Visit evil-rival.example.com for details.",
            "Visit rival.example.com.evil.com for details.",
        ):
            result = detection.detect_answer(text, PRODUCT, [RIVAL])
            self.assertFalse(
                field(competitor_outcome(result, "Rival"), "named"), text)

    def test_subdomain_of_registered_domain_still_named(self):
        result = detection.detect_answer(
            "Visit sub.northbeam.example.com for details.", PRODUCT, [])
        self.assertTrue(field(result, "named"))


class TestHtmlComments040(unittest.TestCase):
    def test_name_inside_comment_is_not_named(self):
        result = detection.detect_answer("<!-- Northbeam -->", PRODUCT, [])
        self.assertFalse(field(result, "named"))

    def test_domain_inside_comment_is_not_named(self):
        result = detection.detect_answer(
            "<!-- see northbeam.example.com --> Plain prose.", PRODUCT, [])
        self.assertFalse(field(result, "named"))

    def test_name_inside_multiline_comment_is_not_named(self):
        result = detection.detect_answer(
            "<!-- first line\nNorthbeam\nlast --> Plain prose.", PRODUCT, [])
        self.assertFalse(field(result, "named"))


class TestReferenceDefinitions041(unittest.TestCase):
    def test_unused_definition_is_not_cited(self):
        text = ("Plain prose about tools in general.\n\n"
                "[nb]: https://northbeam.example.com/guide\n")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))
        self.assertFalse(field(result, "cited"))
        self.assertEqual(field(result, "inline_target_count"), 0)

    def test_definition_label_is_not_a_mention(self):
        text = "[Northbeam]: https://example.com/x\n\nPlain prose.\n"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))


class TestBareWordHeading042(unittest.TestCase):
    def test_bare_sources_word_does_not_open_references(self):
        text = ("Plain prose about tools.\nSources\n"
                "Northbeam is great and\n"
                "https://northbeam.example.com/a is here.\n")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertTrue(field(result, "cited"))

    def test_bare_sources_word_after_real_heading(self):
        text = ("# Overview\n\nTools compared.\n\nSources\n\n"
                "Northbeam is a tool at\n"
                "https://northbeam.example.com/a now.\n")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertTrue(field(result, "cited"))


class TestAliasInBareDomainPath043(unittest.TestCase):
    def test_path_alias_is_not_a_mention(self):
        result = detection.detect_answer(
            "Visit northbeam.example.com/guide for details.", PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertEqual(field(result, "matched_aliases"), [])

    def test_references_domain_with_path_counts_once(self):
        text = ("## References\n\n1. northbeam.example.com/guide\n")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertEqual(field(result, "references_named_count"), 1)


class TestNameNormalisation044(unittest.TestCase):
    def test_nfd_registered_name_matches_nfc_text(self):
        product = {"name": "Cafe\u0301beam", "aliases": [],
                   "domain": "x.example.com"}
        result = detection.detect_answer(
            "Caf\u00e9beam is a tool.", product, [])
        self.assertTrue(field(result, "named"))

    def test_casefold_length_change_matches(self):
        product = {"name": "STRASSE", "aliases": [],
                   "domain": "x.example.com"}
        result = detection.detect_answer(
            "Die Stra\u00dfe ist hier.", product, [])
        self.assertTrue(field(result, "named"))


class TestMalformedTargets045(unittest.TestCase):
    def test_malformed_port_is_not_cited(self):
        for text in (
            "See https://northbeam.example.com:abc/guide now.",
            "See https://northbeam.example.com:99999/guide now.",
        ):
            result = detection.detect_answer(text, PRODUCT, [])
            self.assertFalse(field(result, "cited"), text)

    def test_hostless_target_counts_nowhere(self):
        result = detection.detect_answer(
            "See [x](https:///guide) now.", PRODUCT, [])
        self.assertEqual(field(result, "inline_target_count"), 0)
        self.assertFalse(field(result, "cited"))


class TestBracketTrailingText046(unittest.TestCase):
    def test_entry_with_title_after_target_resolves(self):
        text = ("Tools are compared in the roundup [7].\n\n"
                "## References\n\n"
                "7. https://northbeam.example.com/guide "
                "Northbeam guide page\n")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertTrue(field(result, "cited"))
        self.assertEqual(field(result, "unresolved_form_count"), 0)


class TestClusterPerformance047(unittest.TestCase):
    def test_large_single_cluster_completes_within_bound(self):
        common = " ".join("common%d" % i for i in range(19))
        answers = []
        for i in range(600):
            if i % 2 == 0:
                text = common + " tail%d" % i
            else:
                text = " ".join("other%d" % j for j in range(19)) + \
                    " tail%d" % i
            answers.append(answer(cluster_id=0, text=text))
        start = time.perf_counter()
        result = metrics.round_metrics(answers, "sampled")
        elapsed = time.perf_counter() - start
        self.assertEqual(field(result, "imported_count"), 600)
        self.assertLess(elapsed, 5.0,
                        "chained cluster computation took %.2fs" % elapsed)


class TestCitationCountBounds048(unittest.TestCase):
    def test_self_share_above_one_is_bounded(self):
        result = metrics.round_metrics(
            [answer(citation_instances=1, self_citation_instances=5)],
            "sampled")
        share = field(result, "self_citation_share")
        self.assertGreaterEqual(share, 0.0)
        self.assertLessEqual(share, 1.0)

    def test_negative_counts_are_bounded(self):
        result = metrics.round_metrics(
            [answer(citation_instances=-5, self_citation_instances=-10)],
            "sampled")
        self.assertGreaterEqual(field(result, "citation_instance_count"), 0)
        share = field(result, "self_citation_share")
        if share is not None:
            self.assertGreaterEqual(share, 0.0)
            self.assertLessEqual(share, 1.0)
        self.assertLessEqual(field(result, "cited_rate_net"),
                             field(result, "cited_rate_gross"))

    def test_negative_self_count_share_is_bounded(self):
        result = metrics.round_metrics(
            [answer(citation_instances=5, self_citation_instances=-1)],
            "sampled")
        share = field(result, "self_citation_share")
        self.assertGreaterEqual(share, 0.0)
        self.assertLessEqual(share, 1.0)

    def test_negative_owner_level_count_is_bounded(self):
        row = answer()
        row["owner_level_cited_count"] = -5
        result = metrics.round_metrics([row], "sampled")
        self.assertGreaterEqual(field(result, "owner_level_cited_count"), 0)


class TestMetricsDomain049(unittest.TestCase):
    def test_wilson_out_of_domain_returns_none(self):
        for rate, n in ((1.5, 10), (-0.5, 10), (2, 100), (0.5, -5),
                        (math.nan, 10), (0.5, math.nan), (0.5, math.inf)):
            self.assertIsNone(metrics.wilson_interval(rate, n), (rate, n))

    def test_tier_for_undefined_n_is_count_only(self):
        self.assertEqual(metrics.tier_for(math.nan), "count only")
        self.assertEqual(metrics.tier_for(math.inf), "count only")

    def test_rates_separated_on_undefined_interval_is_false(self):
        self.assertFalse(metrics.rates_separated(
            (math.nan, 0.5), (0.6, 1.0)))
        self.assertFalse(metrics.rates_separated(
            (0.0, 0.5), (0.6, math.inf)))


class TestMetricsShape050(unittest.TestCase):
    def test_unhashable_cluster_id_refused(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics([answer(cluster_id=[1])], "sampled")

    def test_list_query_refused(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics([answer(query=["q"])], "sampled")

    def test_list_engine_refused(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics([answer(engine_label=["E"])], "sampled")

    def test_int_text_refused(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics([answer(text=7)], "sampled")

    def test_string_citation_count_refused(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics(
                [answer(citation_instances="abc")], "sampled")

    def test_string_matched_aliases_not_counted_by_character(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics(
                [answer(matched_aliases="Acme")], "sampled")

    def test_string_aliases_argument_refused(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics([answer()], "sampled", aliases="Acme")


class TestControlDisagreement051(unittest.TestCase):
    def test_control_flag_true_wins_over_control_false(self):
        row = answer(named=True)
        row["control"] = False
        row["control_flag"] = True
        result = metrics.round_metrics([row], "sampled")
        self.assertEqual(field(result, "control_count"), 1)
        self.assertEqual(field(result, "imported_count"), 1)
        named = field(field(result, "rates"), "named")
        self.assertIsNone(field(named, "rate"))


class TestPerAliasOrder052(unittest.TestCase):
    def test_per_alias_counts_keys_sorted(self):
        row = answer(matched_aliases=[
            "Zeta", "Alpha", "Mid", "Beta", "Gamma", "Delta"])
        result = metrics.round_metrics([row], "sampled")
        keys = list(field(result, "per_alias_counts").keys())
        self.assertEqual(keys, sorted(keys))


def journal_entries(order):
    product_entry = {
        "sequence": 1, "entry_kind": "product_registered",
        "payload": {"product_id": "acme-ledger", "name": "Acme Ledger",
                    "domain": "acme.example", "aliases": [],
                    "competitors": [],
                    "query_set": ["What is Acme Ledger?"]},
    }
    round_entry = {
        "sequence": 2, "entry_kind": "round_named",
        "payload": {"product_id": "acme-ledger",
                    "round_label": "r1",
                    "importer_declaration": "all captured"},
    }
    named_answer = {
        "sequence": 3, "entry_kind": "answer_imported",
        "payload": {"product_id": "acme-ledger", "round_label": "r1",
                    "query": "What is Acme Ledger?",
                    "engine_label_original": "Engine A",
                    "kind": "real_sample", "captured_on": "2026-11-07",
                    "capture_method": "manual copy",
                    "control_flag": False,
                    "answer_text": "Acme Ledger helps teams."},
    }
    plain_answer = {
        "sequence": 4, "entry_kind": "answer_imported",
        "payload": {"product_id": "acme-ledger", "round_label": "r1",
                    "query": "What is Acme Ledger?",
                    "engine_label_original": "Engine A",
                    "kind": "fixture", "captured_on": "2026-11-07",
                    "capture_method": "manual copy",
                    "control_flag": False,
                    "answer_text": "Nothing relevant stands here."},
    }
    answers = [named_answer, plain_answer]
    if order == "swapped":
        named_answer = dict(named_answer, sequence=4)
        plain_answer = dict(plain_answer, sequence=3)
        answers = [plain_answer, named_answer]
    return [product_entry, round_entry] + answers


class TestPerKindCompleteness083(unittest.TestCase):
    def test_two_kinds_each_stand_reported(self):
        result = metrics.round_metrics_from_journal(journal_entries("plain"))
        per_kind = field(result, "per_kind")
        self.assertEqual(set(per_kind), {"real_sample", "fixture"})
        self.assertEqual(field(per_kind["real_sample"], "imported_count"), 1)
        self.assertEqual(field(per_kind["fixture"], "imported_count"), 1)
        real_named = field(field(per_kind["real_sample"], "rates"), "named")
        fix_named = field(field(per_kind["fixture"], "rates"), "named")
        self.assertEqual(field(real_named, "rate"), 1.0)
        self.assertEqual(field(fix_named, "rate"), 0.0)

    def test_import_order_does_not_choose_the_reported_kind(self):
        first = metrics.round_metrics_from_journal(journal_entries("plain"))
        second = metrics.round_metrics_from_journal(
            journal_entries("swapped"))
        self.assertEqual(field(first, "per_kind"), field(second, "per_kind"))


if __name__ == "__main__":
    unittest.main()
