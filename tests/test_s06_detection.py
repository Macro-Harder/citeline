"""Slice S6 detection tests, Step 13, Citeline.

Written before the product exists. Every test imports the
product package citeline and calls the detection operations
under the names the plan states (plan Section 5.3 module
boundary row for S6, module detection; plan Section 5.1
AnswerMetrics shape). Import or attribute failure is the
expected red state. No stub and no mock of the product
stands in this file.

Ground that stands blocked for this slice stands in
blocked-w5.md and no test in this file pins it: behaviour
against the contents of any CL-13 list, likeness, any cost
bound over the hostile corpus, and the item 152 removal
set. Third party mentions stand outside this file: no test
ingests them, on the ruling that third party mentions are
out and the product is files only.
"""

import json
import os
import time
import unittest

from citeline import detection

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

PRODUCT = {
    "name": "Northbeam",
    "aliases": ["Northbeam Analytics", "Guide"],
    "domain": "northbeam.example.com",
}
RIVAL = {"name": "Rival", "aliases": [], "domain": "rival.example.com"}
NODOMAIN = {"name": "Nodomain", "aliases": [], "domain": ""}


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def read_fixture(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as handle:
        return handle.read()


def competitor_outcome(result, name):
    for entry in field(result, "per_competitor"):
        if field(entry, "name") == name:
            return entry
    raise AssertionError("no per competitor outcome for " + name)


class TestMentionDetection(unittest.TestCase):
    def test_longest_alias_first_and_span_not_double_counted(self):
        """Plan Section 1.3 S6 family (a), mention detection; brief Section 10.4 primitive P5. Oracle: brief Section 5.7 item 46, at each position the longest alias is taken first and a span consumed by a match is not counted again."""
        result = detection.detect_answer("Northbeam Analytics released a report.", PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertEqual(field(result, "matched_aliases"), ["Northbeam Analytics"])
        self.assertEqual(field(result, "first_offset"), 0)

    def test_product_name_matches_as_stated_member(self):
        """Plan Section 1.3 S6 family (a), mention detection; plan Section 5.1 AnswerMetrics matched_aliases. Oracle: brief Section 10.4 primitive P64, the product name stands as a stated member value where the name matched."""
        result = detection.detect_answer("Northbeam released a report.", PRODUCT, [])
        self.assertEqual(field(result, "matched_aliases"), ["Northbeam"])

    def test_matching_is_case_insensitive(self):
        """Plan Section 1.3 S6 family (a), mention detection. Oracle: brief Section 5.7 item 46, the search runs case insensitively for all names under grill Q18."""
        result = detection.detect_answer("northbeam is a tool.", PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertEqual(field(result, "first_offset"), 0)

    def test_link_target_masked_and_link_text_searched(self):
        """Plan Section 1.3 S6 family (a), mention detection. Oracle: brief Section 5.7 item 46, link targets are masked before search, and brief Section 10.4 primitive P5."""
        result = detection.detect_answer("[Northbeam](https://example.com) is a tool.", PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertEqual(field(result, "first_offset"), 1)

    def test_bare_url_masked_so_host_text_is_no_mention(self):
        """Plan Section 1.3 S6 family (a), mention detection. Oracle: brief Section 5.7 item 46, bare URLs are masked at equal length before the search, read with item 1, which scopes the bare domain named outcome to a bare domain in prose."""
        result = detection.detect_answer("See https://northbeam.example.com/guide for the guide.", PRODUCT, [])
        self.assertFalse(field(result, "named"))
        self.assertTrue(field(result, "cited"))

    def test_first_offset_read_from_unmasked_text(self):
        """Plan Section 1.3 S6 family (a), mention detection, offsets. Oracle: brief Section 5.7 item 46, first offsets are read from the unmasked extracted text at the positions the masked search found, the equal length mask keeping them aligned. Fixture w5-answer-masked-url.txt, hand counted offset 33."""
        text = read_fixture("w5-answer-masked-url.txt").rstrip("\n")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertEqual(field(result, "first_offset"), 33)

    def test_match_flanked_by_letter_does_not_count(self):
        """Plan Section 1.3 S6 family (a), mention detection. Oracle: brief Section 5.7 item 46, a match flanked by a letter or a digit on either side does not count."""
        result = detection.detect_answer("The xNorthbeam tool and the Northbeam9 tool.", PRODUCT, [])
        self.assertFalse(field(result, "named"))
        self.assertIsNone(field(result, "first_offset"))

    def test_match_flanked_by_punctuation_counts(self):
        """Plan Section 1.3 S6 family (a), mention detection. Oracle: brief Section 5.7 item 46, the flanking bar names a letter or a digit only."""
        result = detection.detect_answer("The (Northbeam) tool.", PRODUCT, [])
        self.assertTrue(field(result, "named"))

    def test_common_word_alias_matches_without_classification(self):
        """Plan Section 1.3 S6 family (b), common word stop list, list independent limb; brief Section 10.4 primitive P64. Oracle: primitive P64, no member is classified against any common word stop list in the stored matched alias set, so an alias that is a common English word still matches and carries no classification."""
        result = detection.detect_answer("The Guide covers setup.", PRODUCT, [])
        self.assertIn("Guide", field(result, "matched_aliases"))
        self.assertNotIn("matched_alias_classification", result if isinstance(result, dict) else vars(result))


class TestNamedEarly(unittest.TestCase):
    def named_early_at(self, word_position):
        filler = ["filler"] * (word_position - 1)
        text = " ".join(filler + ["Northbeam", "is", "a", "tool."])
        return detection.detect_answer(text, PRODUCT, [])

    def test_first_mention_at_word_40_is_early(self):
        """Plan Section 1.3 S6 family (a), named early. Oracle: brief Section 10.4 primitive P6, a first mention at word 40 reports named early true."""
        self.assertTrue(field(self.named_early_at(40), "named_early"))

    def test_first_mention_at_word_140_is_not_early(self):
        """Plan Section 1.3 S6 family (a), named early. Oracle: brief Section 10.4 primitive P6, a first mention at word 140 reports named early false."""
        self.assertFalse(field(self.named_early_at(140), "named_early"))

    def test_first_mention_at_word_100_is_early(self):
        """Plan Section 1.3 S6 family (a), named early. Oracle: brief Section 5.7 named early definition, a first mention starting at word 100 or earlier is early."""
        self.assertTrue(field(self.named_early_at(100), "named_early"))

    def test_first_mention_at_word_101_is_not_early(self):
        """Plan Section 1.3 S6 family (a), named early. Oracle: brief Section 5.7 named early definition, a first mention starting after word 100 is not early."""
        self.assertFalse(field(self.named_early_at(101), "named_early"))

    def test_mention_only_in_references_is_not_named_early(self):
        """Plan Section 1.3 S6 family (a), named early with the references rule. Oracle: brief Section 5.7 named early definition, references and source list section mentions under item 160 are excluded. Fixture w5-answer-references.txt."""
        text = read_fixture("w5-answer-references.txt")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named_early"))
        self.assertFalse(field(result, "named"))


class TestCitationDetection(unittest.TestCase):
    def test_bare_domain_in_prose_is_named_only_never_cited(self):
        """Plan Section 1.3 S6 family (a), citation detection. Oracle: brief Section 5.7 item 1, a bare domain in prose counts as named only, never as cited."""
        result = detection.detect_answer("Visit northbeam.example.com for details.", PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertFalse(field(result, "cited"))

    def test_url_to_product_domain_is_cited(self):
        """Plan Section 1.3 S6 family (a), citation detection. Oracle: brief Section 10.4 primitive P4 domain level, a target whose host matches the registered domain at a dot boundary counts as cited at domain level."""
        result = detection.detect_answer("See https://northbeam.example.com/guide for the guide.", PRODUCT, [])
        self.assertTrue(field(result, "cited"))

    def test_subdomain_of_product_domain_is_cited(self):
        """Plan Section 1.3 S6 family (a), citation detection. Oracle: brief Section 5.7 item 34, a host outcome is a match where the target host is the registered host or a subdomain of it under item 44."""
        result = detection.detect_answer("See https://docs.northbeam.example.com/guide now.", PRODUCT, [])
        self.assertTrue(field(result, "cited"))

    def test_host_sharing_a_suffix_without_dot_boundary_is_not_cited(self):
        """Plan Section 1.3 S6 family (a), citation detection. Oracle: brief Section 5.7 item 34, comparison stands at host level with a dot boundary."""
        result = detection.detect_answer("See https://notnorthbeam.example.com/guide now.", PRODUCT, [])
        self.assertFalse(field(result, "cited"))

    def test_product_domain_as_subdomain_of_another_host_is_not_cited(self):
        """Plan Section 1.3 S6 family (a), citation detection. Oracle: brief Section 5.7 item 34, the registered host must stand at the head of the target host, not inside it."""
        result = detection.detect_answer("See https://northbeam.example.com.evil.example/guide now.", PRODUCT, [])
        self.assertFalse(field(result, "cited"))

    def test_title_only_capture_is_named_never_cited(self):
        """Plan Section 1.3 S6 family (a), citation detection. Oracle: brief Section 5.7 item 35, a capture carrying only a title or site name, with no target in any tagged target position, stands in scope for the named outcome only."""
        result = detection.detect_answer("Northbeam official site, a page about the tool.", PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertFalse(field(result, "cited"))

    def test_other_scheme_is_not_a_citation(self):
        """Plan Section 1.3 S6 family (a), scheme handling in citation detection. Oracle: brief Section 5.7 item 43, any scheme other than http and https is not a citation."""
        result = detection.detect_answer("Get it at ftp://northbeam.example.com/guide now.", PRODUCT, [])
        self.assertFalse(field(result, "cited"))

    def test_unresolved_bracket_counts_and_never_cites(self):
        """Plan Section 1.3 S6 family (a), citation detection, bracket forms. Oracle: brief Section 5.7 item 31, an unresolved marker is never counted as a citation, and brief Section 10.4 primitive P7."""
        result = detection.detect_answer("Tools are compared in the roundup [7].", PRODUCT, [])
        self.assertFalse(field(result, "cited"))
        self.assertEqual(field(result, "unresolved_form_count"), 1)

    def test_resolved_bracket_cites_its_references_target(self):
        """Plan Section 1.3 S6 family (a), citation detection, bracket forms. Oracle: brief Section 5.7 item 31, a resolved bracket form counts as a citation to the target the references entry gives."""
        text = "Tools are compared in the roundup [7].\n\n## References\n\n7. https://northbeam.example.com/guide\n"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertTrue(field(result, "cited"))
        self.assertEqual(field(result, "unresolved_form_count"), 0)

    def test_wrapped_target_records_target_as_written_no_unwrapped_outcome(self):
        """Plan Section 1.3 S6 family (b), intermediary host list, list independent limb. Oracle: brief Section 5.7 item 48, no decoded wrapper outcome exists in version 1, and a wrapped target is recorded as the target as written. The wrapper note limb, which turns on the list contents, stands blocked in blocked-w5.md."""
        result = detection.detect_answer("See https://www.google.com/url?q=https://northbeam.example.com/guide now.", PRODUCT, [])
        self.assertFalse(field(result, "cited"))
        self.assertNotIn("unwrapped_target", result if isinstance(result, dict) else vars(result))


class TestPerCompetitorOutcomes(unittest.TestCase):
    def test_competitor_named_and_cited(self):
        """Plan Section 1.3 S6 family (a), per competitor outcomes. Oracle: plan Section 5.1 AnswerMetrics, per competitor named and cited outcomes stand beside the product outcomes."""
        result = detection.detect_answer("Rival is covered at https://rival.example.com/guide now.", PRODUCT, [RIVAL])
        rival = competitor_outcome(result, "Rival")
        self.assertTrue(field(rival, "named"))
        self.assertTrue(field(rival, "cited"))
        self.assertFalse(field(result, "cited"))

    def test_competitor_not_present(self):
        """Plan Section 1.3 S6 family (a), per competitor outcomes. Oracle: plan Section 5.1 AnswerMetrics, per competitor named and cited outcomes."""
        result = detection.detect_answer("A plain answer about tools in general.", PRODUCT, [RIVAL])
        rival = competitor_outcome(result, "Rival")
        self.assertFalse(field(rival, "named"))
        self.assertFalse(field(rival, "cited"))

    def test_empty_domain_competitor_cited_is_not_applicable_with_reason(self):
        """Plan Section 1.3 S6 family (a), per competitor outcomes. Oracle: plan Section 5.1 AnswerMetrics per competitor cited rule and grill Q17, for a competitor whose domain stands empty, cited stands as not applicable with that reason, in place of a true or false outcome."""
        result = detection.detect_answer("Nodomain is covered in the roundup.", PRODUCT, [NODOMAIN])
        rival = competitor_outcome(result, "Nodomain")
        self.assertTrue(field(rival, "named"))
        self.assertIsNone(field(rival, "cited"))
        self.assertTrue(field(rival, "cited_reason"))


class TestHostNormalisation(unittest.TestCase):
    def test_case_folded_lowercased_one_trailing_dot_stripped(self):
        """Plan Section 1.3 S6 family (a), host normalisation. Oracle: brief Section 5.7 item 42, the host is case folded and lowercased, with one trailing dot stripped, and www stripping applies at domain level only, never inside this function."""
        self.assertEqual(detection.normalise_host("WWW.Example.COM."), "www.example.com")

    def test_only_one_trailing_dot_is_stripped(self):
        """Plan Section 1.3 S6 family (a), host normalisation. Oracle: brief Section 5.7 item 42, one trailing dot is stripped."""
        self.assertEqual(detection.normalise_host("example.com.."), "example.com.")

    def test_nfd_input_normalised_to_nfc_a_label_form(self):
        """Plan Section 1.3 S6 family (a), host normalisation. Oracle: brief Section 5.7 item 42, the host is normalised to Unicode NFC and compared in its A-label form. The decomposed spelling of the host in this call and the composed spelling stand for one host."""
        decomposed = "exa\u0308mple.com"
        self.assertEqual(detection.normalise_host(decomposed), "xn--exmple-cua.com")
        self.assertEqual(detection.normalise_host("exämple.com"), "xn--exmple-cua.com")


class TestCanonicalForm(unittest.TestCase):
    def test_http_and_https_merge(self):
        """Plan Section 1.3 S6 family (a), canonical form construction with scheme handling. Oracle: brief Section 5.7 item 43, http and https are merged, and item 33, matching compares the canonical form."""
        self.assertEqual(
            detection.canonical_form("http://example.com/a"),
            detection.canonical_form("https://example.com/a"),
        )

    def test_default_port_dropped_non_default_port_kept(self):
        """Plan Section 1.3 S6 family (a), scheme and port handling. Oracle: brief Section 5.7 item 43, a default port is dropped and a non default port is kept in the matching key."""
        self.assertEqual(
            detection.canonical_form("https://example.com:443/a"),
            detection.canonical_form("https://example.com/a"),
        )
        kept = detection.canonical_form("https://example.com:8443/a")
        self.assertNotEqual(kept, detection.canonical_form("https://example.com/a"))
        self.assertIn(":8443", kept)

    def test_trailing_slash_stripped_except_root(self):
        """Plan Section 1.3 S6 family (a), canonical form construction. Oracle: brief Section 5.7 item 33, the path stands with a trailing slash removed except for the root path."""
        self.assertEqual(
            detection.canonical_form("https://example.com/a/"),
            detection.canonical_form("https://example.com/a"),
        )
        self.assertTrue(detection.canonical_form("https://example.com/").endswith("/"))

    def test_fragment_excluded(self):
        """Plan Section 1.3 S6 family (a), canonical form construction. Oracle: brief Section 5.7 item 33, the canonical form carries no fragment."""
        self.assertEqual(
            detection.canonical_form("https://example.com/a#part"),
            detection.canonical_form("https://example.com/a"),
        )

    def test_ref_parameter_is_not_stripped(self):
        """Plan Section 1.3 S6 family (b), tracking parameter list, list independent limb for the one member the brief names. Oracle: brief Section 5.7 item 41, the ref parameter is not a tracking parameter for matching, so a target differing only in a ref parameter is a different target for page level matching. Behaviour for every other member stands blocked in blocked-w5.md."""
        self.assertNotEqual(
            detection.canonical_form("https://example.com/a?ref=x"),
            detection.canonical_form("https://example.com/a"),
        )

    def test_query_sorted_by_name_then_value_duplicates_kept(self):
        """Plan Section 1.3 S6 family (a), the T3 tolerance rung in the canonical form. Oracle: brief Section 5.7 item 40 limb (5), the remaining query is sorted by name then value, duplicates kept, a valueless parameter sorted by name with an empty value."""
        self.assertEqual(
            detection.canonical_form("https://example.com/a?b=2&a=1&b=1"),
            detection.canonical_form("https://example.com/a?a=1&b=1&b=2"),
        )

    def test_path_letter_case_stands_as_written(self):
        """Plan Section 1.3 S6 family (a), the T3 tolerance rung. Oracle: brief Section 5.7 item 40 limb (1), the path letter case stands as written and is never folded."""
        self.assertNotEqual(
            detection.canonical_form("https://example.com/AbC"),
            detection.canonical_form("https://example.com/abc"),
        )

    def test_userinfo_is_never_part_of_the_host(self):
        """Plan Section 1.3 S6 family (a), scheme and port handling. Oracle: brief Section 5.7 item 43, userinfo is never part of the host."""
        self.assertEqual(
            detection.canonical_form("https://user@example.com/a"),
            detection.canonical_form("https://example.com/a"),
        )


class TestSyntaxNormalisePath(unittest.TestCase):
    def test_unreserved_triplet_decoded_other_triplet_recased_upper(self):
        """Plan Section 1.3 S6 family (a), the T3 tolerance rung limb (1) as its own named function. Oracle: brief Section 5.7 item 40 limb (1), a percent encoded triplet standing for an unreserved character is decoded to that character, a triplet for any other character stands encoded with upper case hex digits. The three normalisations stay separate named functions, plan Section 1.3 S6 family (a); this test calls the path operation by its own name and no shared normalise helper."""
        self.assertEqual(detection.syntax_normalise_path("/a/%7Euser"), "/a/~user")
        self.assertEqual(detection.syntax_normalise_path("/a/%2f"), "/a/%2F")
        self.assertEqual(detection.syntax_normalise_path("/a/%41"), "/a/A")

    def test_dot_segments_removed_after_decoding(self):
        """Plan Section 1.3 S6 family (a), the T3 tolerance rung limb (1). Oracle: brief Section 5.7 item 40 limb (1), the percent decoding runs first and dot segment removal runs second, a single dot segment is dropped and a double dot segment removes the segment before it, a leading double dot segment with no segment before it is dropped."""
        self.assertEqual(detection.syntax_normalise_path("/a/./b"), "/a/b")
        self.assertEqual(detection.syntax_normalise_path("/a/b/../c"), "/a/c")
        self.assertEqual(detection.syntax_normalise_path("/../a"), "/a")
        self.assertEqual(detection.syntax_normalise_path("/a/%2e%2e/b"), "/b")

    def test_empty_path_stands_as_root_and_case_preserved(self):
        """Plan Section 1.3 S6 family (a), the T3 tolerance rung limb (1). Oracle: brief Section 5.7 item 40 limb (1), an empty path stands as the root path and the path letter case stands as written."""
        self.assertEqual(detection.syntax_normalise_path(""), "/")
        self.assertEqual(detection.syntax_normalise_path("/AbC"), "/AbC")

    def test_page_level_key_equality_under_the_full_t3_rung(self):
        """Plan Section 1.3 S6 family (a), the T3 tolerance rung as a whole. Oracle: brief Section 5.7 item 40, the T3 page level key is the item 33 canonical form, built by the five defined operations in order."""
        self.assertEqual(
            detection.canonical_form("https://example.com/a/%7Euser?b=2&a=1"),
            detection.canonical_form("https://example.com/a/~user?a=1&b=2"),
        )


class TestReferencesSectionRule(unittest.TestCase):
    def test_closed_set_heading_splits_mentions_and_citations(self):
        """Plan Section 1.3 S6 family (a), the references section rule. Oracle: brief Section 5.7 item 160, mentions and citations in a references section are reported separately from prose, and headline outcomes use prose only. Fixture w5-answer-references.txt, hand computed split of one named and one cited in the section, none inline."""
        text = read_fixture("w5-answer-references.txt")
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "named"))
        self.assertFalse(field(result, "cited"))
        self.assertEqual(field(result, "references_named_count"), 1)
        self.assertEqual(field(result, "references_cited_count"), 1)
        self.assertEqual(field(result, "references_target_count"), 1)
        self.assertEqual(field(result, "inline_target_count"), 0)

    def test_heading_matched_case_insensitively_ignoring_trailing_punctuation(self):
        """Plan Section 1.3 S6 family (a), the references section rule. Oracle: brief Section 5.7 item 160, the heading set is closed and matched case insensitively ignoring trailing punctuation."""
        text = "Prose about tools in general.\n\n## references:\n\n- https://northbeam.example.com/guide\n"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertFalse(field(result, "cited"))
        self.assertEqual(field(result, "references_target_count"), 1)

    def test_target_list_under_other_heading_is_prose(self):
        """Plan Section 1.3 S6 family (a), the references section rule. Oracle: brief Section 5.7 item 160, a target list under any other heading is prose."""
        text = "Prose about tools.\n\n## Notes\n\n- https://northbeam.example.com/a\n- https://northbeam.example.com/b\n"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertTrue(field(result, "cited"))
        self.assertEqual(field(result, "references_target_count"), 0)

    def test_two_references_sections_report_together(self):
        """Plan Section 1.3 S6 family (a), the references section rule. Oracle: brief Section 5.7 item 160, multiple such sections are each references sections and are reported together in the references split."""
        text = (
            "Prose about tools.\n\n## References\n\n- https://northbeam.example.com/a\n\n"
            "More prose about tools.\n\n## Bibliography\n\n- https://rival.example.com/b\n"
        )
        result = detection.detect_answer(text, PRODUCT, [RIVAL])
        self.assertEqual(field(result, "references_target_count"), 2)
        self.assertEqual(field(result, "inline_target_count"), 0)

    def test_unheaded_trailing_list_is_a_references_section(self):
        """Plan Section 1.3 S6 family (a), the references section rule. Oracle: brief Section 5.7 item 160, an unheaded trailing list after the last paragraph of prose is a references section, a list standing as a run of two or more consecutive item lines at the end of the text."""
        text = "Some prose about tools in general.\nhttps://northbeam.example.com/a\nhttps://rival.example.com/b\n"
        result = detection.detect_answer(text, PRODUCT, [RIVAL])
        self.assertFalse(field(result, "cited"))
        self.assertEqual(field(result, "references_target_count"), 2)

    def test_single_trailing_target_line_stays_prose(self):
        """Plan Section 1.3 S6 family (a), the references section rule. Oracle: brief Section 5.7 item 160, a single trailing target line is not a list and stays prose."""
        text = "Some prose about tools in general.\nhttps://northbeam.example.com/a\n"
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertTrue(field(result, "cited"))
        self.assertEqual(field(result, "references_target_count"), 0)

    def test_inline_and_section_targets_split_as_distinct_canonical_targets(self):
        """Plan Section 1.3 S6 family (a), the references section rule. Oracle: brief Section 5.7 item 160, the report shows the number of distinct canonical targets split between such a section and inline."""
        text = (
            "Prose citing https://northbeam.example.com/a inline.\n\n## Sources\n\n- https://northbeam.example.com/b\n"
        )
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertTrue(field(result, "cited"))
        self.assertEqual(field(result, "inline_target_count"), 1)
        self.assertEqual(field(result, "references_target_count"), 1)


class TestClustering(unittest.TestCase):
    def test_identical_texts_form_one_cluster(self):
        """Plan Section 1.3 S6 family (a), clustering correctness on the shingle index. Oracle: brief Section 5.8 item 20, clusters are the groups formed by joining every pair of similar answers, so identical texts stand in one cluster."""
        text = read_fixture("w5-chain-a.txt").strip()
        ids = detection.cluster_answers([text, text, text])
        self.assertEqual(len(set(ids)), 1)

    def test_disjoint_texts_form_separate_clusters(self):
        """Plan Section 1.3 S6 family (a), clustering correctness. Oracle: brief Section 5.8 item 20, a pair sharing no shingle has similarity 0, so disjoint texts stand in separate clusters."""
        first = "alpha bravo charlie delta echo foxtrot golf hotel india juliet"
        second = "kilo lima mike november oscar papa quebec romeo sierra tango"
        ids = detection.cluster_answers([first, second])
        self.assertEqual(len(set(ids)), 2)

    def test_near_duplicate_pair_forms_one_cluster(self):
        """Plan Section 1.3 S6 family (a), clustering correctness. Oracle: brief Section 5.8 item 20, two answers are similar where the Jaccard similarity of their word 5 gram shingle sets is at least 0.80. Hand computed for this pair: 15 shared shingles of 17 in the union, 0.88."""
        base = " ".join("v%d" % i for i in range(1, 21))
        variant = " ".join(["v%d" % i for i in range(1, 20)] + ["z9"])
        ids = detection.cluster_answers([base, variant])
        self.assertEqual(len(set(ids)), 1)

    def test_three_answer_chain_one_cluster(self):
        """Plan Section 1.3 S6 family (a), clustering correctness, the three answer chain case on CQ-D33 first limb; brief Section 5.8 item 65 chain fixture. Oracle: brief Section 5.8 item 20, clusters join every similar pair with no transitivity required. Hand computed Jaccard values for fixtures w5-chain-a.txt, w5-chain-b.txt, w5-chain-c.txt: first to second 25 of 27, 0.926; second to third 24 of 28, 0.857; first to third 23 of 29, 0.793, under the 0.80 line. The chain therefore forms one cluster."""
        a = read_fixture("w5-chain-a.txt").strip()
        b = read_fixture("w5-chain-b.txt").strip()
        c = read_fixture("w5-chain-c.txt").strip()
        self.assertEqual(len(set(detection.cluster_answers([a, b]))), 1)
        self.assertEqual(len(set(detection.cluster_answers([b, c]))), 1)
        self.assertEqual(len(set(detection.cluster_answers([a, c]))), 2)
        ids = detection.cluster_answers([a, b, c])
        self.assertEqual(len(set(ids)), 1)

    def test_empty_shingle_sets_cluster_only_on_identical_normalised_text(self):
        """Plan Section 1.3 S6 family (a), clustering correctness. Oracle: brief Section 5.8 item 20, where either shingle set is empty, identical normalised texts are similar and every other pair with an empty set is not similar, so an empty or whitespace only answer clusters only with an identical normalised text."""
        ids = detection.cluster_answers(["hello world", "hello world", "goodbye world"])
        self.assertEqual(len(set(ids)), 2)
        ids = detection.cluster_answers(["", "   ", "hello"])
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual(ids[0], ids[1])

    def test_case_and_whitespace_variants_cluster_together(self):
        """Plan Section 1.3 S6 family (a), clustering correctness. Oracle: brief Section 5.8 item 20, each answer text is normalised to NFC, case folded, and whitespace collapsed before its shingles are built."""
        base = read_fixture("w5-chain-a.txt").strip()
        variant = "  " + base.upper().replace(" ", "   ") + "  "
        ids = detection.cluster_answers([base, variant])
        self.assertEqual(len(set(ids)), 1)

    def test_hostile_corpus_correctness_limb_only(self):
        """Plan Section 1.3 S6 family (d), SEAM-CLUSTER-COST, correctness limb only. Oracle: plan Section 1.4 entry B7 proceeding tests, clustering correctness on the index specified exactly, and the hostile corpus in its correctness limb. The corpus stands produced by the scaling route of plan Section 1.6 from stated parameters in this test: 200 answers of ten pairwise distinct words each, and 50 exact copies of one further answer. Hand computed expectation from item 20 applied to the corpus as generated: 201 clusters. No timing, memory, completion, cap, or size bound stands asserted in this test; every such bound stands blocked on RH-2 in blocked-w5.md."""
        texts = []
        for i in range(200):
            texts.append(" ".join("h%dw%d" % (i, j) for j in range(10)))
        texts.extend(["same words here for the repeated answer text body"] * 50)
        ids = detection.cluster_answers(texts)
        self.assertEqual(len(set(ids)), 201)
        self.assertEqual(len(set(ids[200:])), 1)


class TestTimingBoundAtStatedScale(unittest.TestCase):
    def test_detection_and_clustering_within_bound_at_stated_scale(self):
        """Plan Section 1.5 timing bounds, S6 row. Oracle: plan Section 1.5, detection and clustering over one stated round at reportable size, 20 seconds, on the decided limbs only, conditional on the test scale stated on the record at scales-w5.md before the bound is applied. The scale stated there: one round of 50 answers, each of 60 words, against one product with two competitors."""
        texts = []
        for i in range(50):
            texts.append("Northbeam " + " ".join("s%dw%d" % (i, j) for j in range(59)))
        start = time.perf_counter()
        for text in texts:
            detection.detect_answer(text, PRODUCT, [RIVAL, NODOMAIN])
        detection.cluster_answers(texts)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 20.0)


if __name__ == "__main__":
    unittest.main()
