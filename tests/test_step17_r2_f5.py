"""Detection and metrics.

Each test pins one register entry from the findings
register, in the form the register states. Written before
the cures, watched failing, then watched passing."""

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


class TestSentenceFinalDomain042(unittest.TestCase):
    def test_bare_domain_at_sentence_end_is_named(self):
        result = detection.detect_answer(
            "Visit northbeam.example.com.", PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertEqual(field(result, "first_offset"), 6)

    def test_bare_domain_closing_a_sentence_mid_text_is_named(self):
        result = detection.detect_answer(
            "Visit northbeam.example.com. It is great.", PRODUCT, [])
        self.assertTrue(field(result, "named"))

    def test_subdomain_at_sentence_end_is_named(self):
        result = detection.detect_answer(
            "Visit sub.northbeam.example.com.", PRODUCT, [])
        self.assertTrue(field(result, "named"))

    def test_competitor_domain_at_sentence_end_is_named(self):
        result = detection.detect_answer(
            "Visit rival.example.com.", PRODUCT, [RIVAL])
        self.assertTrue(
            field(competitor_outcome(result, "Rival"), "named"))

    def test_references_domain_at_sentence_end_counts(self):
        text = "## References\n\n1. northbeam.example.com.\n"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertEqual(field(result, "references_named_count"), 1)

    def test_trailing_dot_host_with_path_is_domain_not_alias(self):
        result = detection.detect_answer(
            "Visit northbeam.example.com./guide for details.",
            PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertEqual(field(result, "first_offset"), 6)
        self.assertEqual(field(result, "matched_aliases"), [])

    def test_lookalike_host_still_counts_nothing(self):
        for text in (
            "Visit northbeam.example.com.evil.com for details.",
            "Visit northbeam.example.com-evil.com for details.",
            "Contact user@northbeam.example.com for info.",
        ):
            result = detection.detect_answer(text, PRODUCT, [])
            self.assertFalse(field(result, "named"), text)


class TestFoldedPositions043(unittest.TestCase):
    def test_domain_after_length_changing_fold_is_named(self):
        for prefix in ("ß", "ﬀ", "İ"):
            text = prefix + " northbeam.example.com is here."
            result = detection.detect_answer(text, PRODUCT, [])
            self.assertTrue(field(result, "named"), text)

    def test_subdomain_after_fold_is_named(self):
        result = detection.detect_answer(
            "ß sub.northbeam.example.com is here.", PRODUCT, [])
        self.assertTrue(field(result, "named"))

    def test_competitor_domain_after_fold_is_named(self):
        result = detection.detect_answer(
            "ß rival.example.com is here.", PRODUCT, [RIVAL])
        self.assertTrue(
            field(competitor_outcome(result, "Rival"), "named"))

    def test_references_domain_after_fold_counts(self):
        text = "## References\n\n1. ß northbeam.example.com\n"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertEqual(field(result, "references_named_count"), 1)

    def test_mention_offset_after_fold_reads_supplied_text(self):
        result = detection.detect_answer(
            "ß Northbeam is here.", PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertEqual(field(result, "first_offset"), 2)

    def test_mention_offset_after_two_folds(self):
        result = detection.detect_answer(
            "ßß Northbeam is here.", PRODUCT, [])
        self.assertEqual(field(result, "first_offset"), 3)

    def test_named_early_after_folds(self):
        text = " ".join(["ß"] * 99 + ["Northbeam is here."])
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertEqual(field(result, "first_offset"), 198)
        self.assertTrue(field(result, "named_early"))


class TestBareDomainPortToken044(unittest.TestCase):
    def test_path_alias_after_port_is_not_a_mention(self):
        result = detection.detect_answer(
            "Visit northbeam.example.com:8080/guide for details.",
            PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertEqual(field(result, "matched_aliases"), [])

    def test_references_domain_with_port_and_path_counts_once(self):
        text = "## References\n\n1. northbeam.example.com:8080/guide\n"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertEqual(field(result, "references_named_count"), 1)

    def test_subdomain_path_alias_after_port_is_not_a_mention(self):
        result = detection.detect_answer(
            "Visit sub.northbeam.example.com:8080/guide for details.",
            PRODUCT, [])
        self.assertEqual(field(result, "matched_aliases"), [])


def references_answer(entry):
    return ("Tools compared [7].\n\n## References\n\n" + entry + "\n")


class TestReferenceEntryForms045(unittest.TestCase):
    def test_bracketed_number_without_stop_resolves(self):
        result = detection.detect_answer(references_answer(
            "[7] https://northbeam.example.com/guide"), PRODUCT, [])
        self.assertTrue(field(result, "cited"))
        self.assertEqual(field(result, "unresolved_form_count"), 0)

    def test_markdown_link_entry_resolves(self):
        result = detection.detect_answer(references_answer(
            "7. [Guide page](https://northbeam.example.com/guide)"),
            PRODUCT, [])
        self.assertTrue(field(result, "cited"))
        self.assertEqual(field(result, "unresolved_form_count"), 0)

    def test_angle_bracket_entry_resolves(self):
        result = detection.detect_answer(references_answer(
            "7. <https://northbeam.example.com/guide>"), PRODUCT, [])
        self.assertTrue(field(result, "cited"))
        self.assertEqual(field(result, "unresolved_form_count"), 0)

    def test_bare_domain_entry_resolves_as_cited(self):
        result = detection.detect_answer(references_answer(
            "7. northbeam.example.com/guide"), PRODUCT, [])
        self.assertTrue(field(result, "cited"))
        self.assertEqual(field(result, "unresolved_form_count"), 0)

    def test_leading_zero_entry_number_resolves(self):
        result = detection.detect_answer(references_answer(
            "07. https://northbeam.example.com/guide"), PRODUCT, [])
        self.assertTrue(field(result, "cited"))
        self.assertEqual(field(result, "unresolved_form_count"), 0)


class TestReferencesHeadingPunctuation046(unittest.TestCase):
    def check_heading(self, heading):
        text = ("Plain prose about tools.\n\n" + heading + "\n\n"
                "Northbeam at https://northbeam.example.com/a\n")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))
        self.assertFalse(field(result, "cited"))
        self.assertEqual(field(result, "references_target_count"), 1)

    def test_heading_with_question_mark(self):
        self.check_heading("## References?")

    def test_heading_with_comma(self):
        self.check_heading("## References,")


class TestReferencesHeadingSetext047(unittest.TestCase):
    def test_setext_equals_heading_opens_references(self):
        text = ("Plain prose about tools.\n\nReferences\n==========\n\n"
                "Northbeam at https://northbeam.example.com/a\n")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))
        self.assertFalse(field(result, "cited"))
        self.assertEqual(field(result, "references_target_count"), 1)

    def test_setext_hyphen_heading_opens_references(self):
        text = ("Plain prose about tools.\n\nReferences\n----------\n\n"
                "Northbeam at https://northbeam.example.com/a\n")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))
        self.assertEqual(field(result, "references_target_count"), 1)


class TestCommentCloseForms048(unittest.TestCase):
    def test_abrupt_close_angle(self):
        result = detection.detect_answer(
            "<!--> Northbeam is great.", PRODUCT, [])
        self.assertTrue(field(result, "named"))

    def test_abrupt_close_dash_angle(self):
        result = detection.detect_answer(
            "<!---> Northbeam is great.", PRODUCT, [])
        self.assertTrue(field(result, "named"))

    def test_bang_close(self):
        result = detection.detect_answer(
            "<!-- note --!> Northbeam is great.", PRODUCT, [])
        self.assertTrue(field(result, "named"))

    def test_name_inside_bang_closed_comment_counts_nothing(self):
        result = detection.detect_answer(
            "<!-- Northbeam --!> Plain prose.", PRODUCT, [])
        self.assertFalse(field(result, "named"))


class TestSplitReferenceDefinition049(unittest.TestCase):
    def test_destination_on_next_line_counts_no_citation(self):
        text = ("Plain prose about tools.\n\n[nb]:\n"
                "    https://northbeam.example.com/guide\n")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "cited"))
        self.assertEqual(field(result, "inline_target_count"), 0)

    def test_title_on_next_line_counts_no_mention(self):
        text = ("[nb]: https://example.com/x\n"
                "    \"Northbeam guide\"\n\nPlain prose.\n")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))


class TestLinkTextMask050(unittest.TestCase):
    def test_alias_after_paren_in_link_text_is_a_mention(self):
        result = detection.detect_answer(
            "See [the tool (Guide) page](https://example.com/x) "
            "for details.", PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertEqual(field(result, "matched_aliases"), ["Guide"])

    def test_product_name_after_paren_in_link_text_is_a_mention(self):
        result = detection.detect_answer(
            "See [tools (Northbeam) compared](https://example.com/x) "
            "now.", PRODUCT, [])
        self.assertTrue(field(result, "named"))


class TestCompetitorBracketGuard051(unittest.TestCase):
    def test_link_text_number_is_no_competitor_bracket(self):
        text = ("Tools [7](https://example.com/x) are listed.\n\n"
                "## References\n\n7. https://rival.example.com/guide\n")
        result = detection.detect_answer(text, PRODUCT, [RIVAL])
        self.assertFalse(
            field(competitor_outcome(result, "Rival"), "cited"))

    def test_plain_bracket_still_cites_competitor(self):
        text = ("Tools compared [7].\n\n"
                "## References\n\n7. https://rival.example.com/guide\n")
        result = detection.detect_answer(text, PRODUCT, [RIVAL])
        self.assertTrue(
            field(competitor_outcome(result, "Rival"), "cited"))


def cluster_answers(count):
    common = " ".join("common%d" % i for i in range(19))
    other = " ".join("other%d" % j for j in range(19))
    rows = []
    for i in range(count):
        base = common if i % 2 == 0 else other
        rows.append(answer(cluster_id=0, text=base + " tail%d" % i))
    return rows


class TestClusterScale052(unittest.TestCase):
    def test_round_one_pin_restated_at_600(self):
        rows = cluster_answers(600)
        start = time.perf_counter()
        result = metrics.round_metrics(rows, "sampled")
        elapsed = time.perf_counter() - start
        self.assertEqual(field(result, "imported_count"), 600)
        self.assertLess(elapsed, 5.0,
                        "600 answer round took %.2fs" % elapsed)

    def test_cap_scale_single_cluster_inside_backstop(self):
        rows = cluster_answers(10000)
        start = time.perf_counter()
        result = metrics.round_metrics(rows, "sampled")
        elapsed = time.perf_counter() - start
        self.assertEqual(field(result, "imported_count"), 10000)
        self.assertEqual(field(result, "cluster_count"), 1)
        self.assertEqual(field(result, "chained_cluster_count"), 0)
        self.assertLess(elapsed, 60.0,
                        "cap scale round took %.2fs" % elapsed)

    def test_chained_cluster_still_counted(self):
        words = ["w%02d" % i for i in range(30)]
        first = " ".join(words[0:20])
        second = " ".join(words[1:21])
        third = " ".join(words[2:22])
        rows = [answer(cluster_id=0, text=text)
                for text in (first, second, third)]
        result = metrics.round_metrics(rows, "sampled")
        self.assertEqual(field(result, "chained_cluster_count"), 1)


class TestCompetitorsArgumentShape053(unittest.TestCase):
    def test_string_competitors_argument_refused(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics([answer()], "sampled",
                                  competitors="Rival")

    def test_bytes_competitors_argument_refused(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics([answer()], "sampled",
                                  competitors=b"Rival")


class TestCompetitorEntryNameShape054(unittest.TestCase):
    def test_list_competitor_name_in_answer_refused(self):
        row = answer()
        row["per_competitor"] = [
            {"name": ["X"], "named": True, "cited": True}]
        with self.assertRaises(ValueError):
            metrics.round_metrics([row], "sampled")

    def test_integer_competitor_name_in_answer_refused(self):
        row = answer()
        row["per_competitor"] = [
            {"name": 7, "named": True, "cited": True}]
        with self.assertRaises(ValueError):
            metrics.round_metrics([row], "sampled")

    def test_list_competitor_name_in_argument_refused(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics([answer()], "sampled",
                                  competitors=[{"name": ["X"]}])

    def test_integer_competitor_name_in_argument_refused(self):
        with self.assertRaises(ValueError):
            metrics.round_metrics([answer()], "sampled",
                                  competitors=[{"name": 7}])


class TestDomainGuardOverflow055(unittest.TestCase):
    def test_wilson_huge_integer_returns_none(self):
        self.assertIsNone(metrics.wilson_interval(0.5, 10 ** 1000))
        self.assertIsNone(metrics.wilson_interval(10 ** 1000, 10))

    def test_tier_huge_integer_is_count_only(self):
        self.assertEqual(metrics.tier_for(10 ** 1000), "count only")

    def test_rates_separated_huge_integer_is_false(self):
        self.assertFalse(metrics.rates_separated(
            (0.0, 10 ** 1000), (0.1, 0.2)))


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


class TestKindsSorted089(unittest.TestCase):
    def test_kinds_list_sorted_regardless_of_import_order(self):
        first = metrics.round_metrics_from_journal(
            journal_entries("plain"))
        second = metrics.round_metrics_from_journal(
            journal_entries("swapped"))
        self.assertEqual(field(first, "kinds"),
                         ["fixture", "real_sample"])
        self.assertEqual(field(second, "kinds"),
                         ["fixture", "real_sample"])
        self.assertEqual(list(field(first, "per_kind").keys()),
                         ["fixture", "real_sample"])


if __name__ == "__main__":
    unittest.main()
