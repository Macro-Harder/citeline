"""Repair tests.

Test first cures for eight settled rules. Each test names
the settled text it pins.
Copyright: J.P. Picard aka Macro-Harder.
"""

import unittest

from citeline import checks, detection, metrics, registry


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


PRODUCT = {
    "name": "Northbeam",
    "aliases": ["Northbeam Analytics", "Guide"],
    "domain": "northbeam.example.com",
}
EXAMPLE = {"name": "Widget", "aliases": [], "domain": "example.com"}
GUIDE_EXAMPLE = {"name": "Guide", "aliases": [], "domain": "example.com"}


class TestS2001DecodingBeforeHostParsing(unittest.TestCase):
    """The settled rule. Brief items 148 and 159, the settled decision:
    percent sequences and entities in a link destination are
    decoded exactly once before host parsing."""

    def test_percent_encoded_host_in_markdown_link_cites(self):
        result = detection.detect_answer(
            "See [notes](https://examp%6ce.com/guide) for details.",
            EXAMPLE, [])
        self.assertTrue(field(result, "cited"))

    def test_percent_encoded_host_in_bare_url_cites(self):
        result = detection.detect_answer(
            "See https://examp%6ce.com/guide for details.",
            EXAMPLE, [])
        self.assertTrue(field(result, "cited"))

    def test_entity_encoded_host_in_markdown_link_cites(self):
        result = detection.detect_answer(
            "See [notes](https://example&#46;com/guide) for details.",
            EXAMPLE, [])
        self.assertTrue(field(result, "cited"))

    def test_percent_encoded_references_entry_resolves_and_cites(self):
        text = ("Tools are compared in the roundup [7].\n\n"
                "## References\n\n"
                "7. https://examp%6ce.com/guide\n")
        result = detection.detect_answer(text, EXAMPLE, [])
        self.assertTrue(field(result, "cited"))
        self.assertEqual(field(result, "unresolved_form_count"), 0)
        self.assertEqual(field(result, "references_cited_count"), 1)

    def test_encoded_and_plain_form_share_one_canonical_key(self):
        self.assertEqual(
            detection.canonical_form("https://example.com/guide"),
            detection.canonical_form("https://examp%6ce.com/guide"))

    def test_references_split_counts_encoded_twin_once(self):
        text = ("A plain answer about tools.\n\n"
                "## References\n\n"
                "1. https://example.com/guide\n"
                "2. https://examp%6ce.com/guide\n")
        result = detection.detect_answer(text, EXAMPLE, [])
        self.assertEqual(field(result, "references_target_count"), 1)

    def test_double_encoded_host_counts_no_citation(self):
        result = detection.detect_answer(
            "See [notes](https://examp%256ce.com/guide) for details.",
            EXAMPLE, [])
        self.assertFalse(field(result, "cited"))


class TestS2007IdnaFailureCountsNoCitation(unittest.TestCase):
    """The settled rule. Brief item 42: an IDNA failure is
    malformed and counts no citation."""

    def test_normalise_host_returns_none_on_idna_failure(self):
        self.assertIsNone(checks._normalise_host("exam\ufffdple.com"))

    def test_citation_analysis_counts_no_citation_for_idna_failure(self):
        running = "See https://exam\ufffdple.com/report for details."
        page = {
            "running_text": running,
            "sentences": [running],
            "paragraphs": [running],
            "links": [{
                "text": "https://exam\ufffdple.com/report",
                "target": "https://exam\ufffdple.com/report",
                "start": 4,
                "end": 4 + len("https://exam\ufffdple.com/report"),
            }],
        }
        facts = {"domain": "example.com"}
        outcome = checks._citation_analysis(page, facts)
        self.assertEqual(outcome["count"], 0)


class TestS2008BoundarySets(unittest.TestCase):
    """The settled rule. Brief item 46 and primitive P5 name a
    letter or a digit only; item 40 states host only matching
    with a dot boundary. The mention limb is cured here. The
    bare domain limb stands not cured, as the last test of
    this class and the repair record state."""

    def test_mention_flanked_by_underscores_counts(self):
        result = detection.detect_answer(
            "the_guide_here is one token in this answer text.",
            PRODUCT, [])
        self.assertTrue(field(result, "named"))

    def test_mention_with_underscore_before_counts(self):
        result = detection.detect_answer(
            "See my_guide release notes here.", PRODUCT, [])
        self.assertTrue(field(result, "named"))

    def test_mention_with_underscore_after_counts(self):
        result = detection.detect_answer(
            "The guide_ release is out now.", PRODUCT, [])
        self.assertTrue(field(result, "named"))

    def test_bare_domain_lookalike_forms_stay_unnamed(self):
        # The bare domain limb of the settled rule stands NOT cured by
        # this repair, for the reasons stated in the repair record:
        # the shipped pins (TestDomainBoundary039,
        # TestDomainBoundaryUnderscore038, and the lookalike
        # case of TestSentenceFinalDomain042) pin the wider
        # flank set of _domain_offsets as settled cure
        # behaviour for lookalike hosts, and the defect audit filed no
        # finding on the domain offsets. This test pins the
        # standing shipped behaviour so the uncured limb is
        # visible in this suite, not silently dropped.
        for text in (
            "Visit northbeam.example.com-evil.com for details.",
            "Contact user@northbeam.example.com for info.",
            "See a_northbeam.example.com now.",
        ):
            result = detection.detect_answer(text, PRODUCT, [])
            self.assertFalse(field(result, "named"), text)

    def test_letter_flanked_mention_still_barred(self):
        result = detection.detect_answer(
            "The xguide release is out now.", PRODUCT, [])
        self.assertFalse(field(result, "named"))


class TestS2019ZeroWidthRemoval(unittest.TestCase):
    """The settled rule. Brief item 152, zero width limb only:
    zero width characters are removed in the matching copy
    only, after NFC and before case folding."""

    def test_zero_width_space_inside_product_name_matches(self):
        result = detection.detect_answer(
            "North\u200bbeam released a report.", PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertEqual(field(result, "matched_aliases"), ["Northbeam"])

    def test_zero_width_space_inside_alias_matches(self):
        result = detection.detect_answer(
            "The Gu\u200bide covers setup.", PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertEqual(field(result, "matched_aliases"), ["Guide"])

    def test_zero_width_joiner_inside_product_name_matches(self):
        result = detection.detect_answer(
            "North\u200dbeam released a report.", PRODUCT, [])
        self.assertTrue(field(result, "named"))

    def test_first_offset_maps_through_removed_character(self):
        text = "North\u200bbeam released a report."
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertEqual(field(result, "first_offset"), 0)


class TestS2021Ipv6CanonicalForm(unittest.TestCase):
    """The settled rule. Brief item 33: two distinct targets must
    not share one canonical key."""

    def test_ipv6_brackets_kept_in_canonical_form(self):
        key = detection.canonical_form("https://[2001:db8::1]:8080/x")
        self.assertIn("[2001:db8::1]", key)
        self.assertIn(":8080", key)

    def test_ipv6_address_and_port_forms_key_apart(self):
        first = detection.canonical_form("https://[2001:db8::1]:8080/x")
        second = detection.canonical_form("https://[2001:db8::1:8080]/x")
        self.assertNotEqual(first, second)


class TestS2022DeferredNamedOnce(unittest.TestCase):
    """The settled rule. The second queue statement in
    _similar_components: a deferred set stands named once
    and judged once in one pass, in both module copies."""

    def _trigger_family(self):
        # The family the audit record names: a set deferred at
        # one layer, promoted at a later layer without joining,
        # and deferred again at a still later layer. Eight
        # heavy shingles stand shared by 150 filler sets, so
        # each heavy shingle posting stands past the heavy
        # bound. Sets 0 to 4 form the joining chain, set 5 is
        # the set that is deferred, promoted, and deferred
        # again, and the fillers stand deferred once each.
        heavy = [("h", i) for i in range(8)]
        families = [
            set(heavy) | {"s0", "s9"},
            set(heavy) | {"s0", "a0"},
            set(heavy) | {"a0", "L"},
            set(heavy) | {"a0", "c0"},
            set(heavy) | {"c0", "d0"},
            set(heavy) | {"L"} | {("x", k) for k in range(11)},
        ]
        for index in range(150):
            families.append(
                set(heavy) | {("f", index, k) for k in range(12)})
        return families

    def test_deferred_set_named_once_in_second_queue_snapshot(self):
        # The defect is cost only and changes no result, as
        # its paper grades it, so it is observed at the one
        # place it stands: the second queue snapshot itself,
        # read through a line trace on the snapshot line of
        # each module copy. Every snapshot must name each
        # waiting set exactly once.
        import inspect
        import sys
        for module in (detection, metrics):
            families = self._trigger_family()
            lines, start = inspect.getsourcelines(
                module._similar_components)
            snap_line = None
            for offset, line in enumerate(lines):
                if "snapshot = [other for other in deferred_order" in line:
                    snap_line = start + offset
                    break
            self.assertIsNotNone(snap_line, module.__name__)
            snapshots = []

            def tracer(frame, event, arg, snap_line=snap_line,
                       snapshots=snapshots):
                if event == "line" and \
                        frame.f_code.co_name == "_similar_components" and \
                        frame.f_lineno == snap_line:
                    order = list(frame.f_locals.get("deferred_order", []))
                    waiting = set(frame.f_locals.get("deferred", set()))
                    snapshots.append(
                        [item for item in order if item in waiting])
                return tracer

            sys.settrace(tracer)
            try:
                components = module._similar_components(
                    [set(family) for family in families])
            finally:
                sys.settrace(None)
            self.assertTrue(snapshots, module.__name__)
            for snapshot in snapshots:
                self.assertEqual(
                    len(snapshot), len(set(snapshot)), module.__name__)
            flat = [item for comp in components for item in comp]
            self.assertEqual(sorted(flat), list(range(len(families))),
                             module.__name__)


class TestS2036FirstOffsetSuppliedCoordinates(unittest.TestCase):
    """The settled rule. Brief items 46 and 151: first_offset is a
    position in the text as supplied, not in its NFC form."""

    def test_first_offset_after_decomposed_character(self):
        text = "Cafe\u0301 Guide covers setup."
        result = detection.detect_answer(text, PRODUCT, [])
        self.assertTrue(field(result, "named"))
        self.assertEqual(text[field(result, "first_offset"):
                              field(result, "first_offset") + 5], "Guide")
        self.assertEqual(field(result, "first_offset"), 6)


class TestS2037AliasLengthAfterNfc(unittest.TestCase):
    """The settled rule. Brief items 47 and 151: the alias minimum
    length of 3 is judged on the NFC normalised form."""

    def test_alias_normalising_to_two_characters_is_refused(self):
        with self.assertRaises(Exception):
            registry.validate_alias("e\u0301x")

    def test_alias_of_three_after_normalisation_is_accepted(self):
        accepted = registry.validate_alias("e\u0301xy")
        self.assertEqual(len(accepted), 3)

    def test_plain_two_character_alias_still_refused(self):
        with self.assertRaises(Exception):
            registry.validate_alias("ab")


if __name__ == "__main__":
    unittest.main()
