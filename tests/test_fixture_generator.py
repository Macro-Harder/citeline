"""Tests for the Step 13 fixture generator.

Oracle: plan Section 1.6, generation and scaling route
(CQ-D29 and CQ-D30), and the expectation source passage in
the same section. The generator is a test tree program, so
these tests are expected to pass against it. They were
written before the generator.
"""

import hashlib
import unittest

import fixture_generator as fg


class ScalingRouteTests(unittest.TestCase):
    def test_scale_to_count_repeats_stated_unit(self):
        """Pins plan Section 1.6 CQ-D29 scaling route: a large
        fixture stands produced by repeating the named base
        fixture's stated unit to a stated target count."""
        data, prov = fg.generate(
            "w1-answer-unit", "scaling", target_count=5)
        lines = data.decode("utf-8").splitlines()
        self.assertEqual(len(lines), 5)
        self.assertEqual(prov["route"], "scaling")
        self.assertEqual(prov["target_count"], 5)

    def test_scale_to_byte_size_uses_whole_units(self):
        """Pins plan Section 1.6 CQ-D29: scaling may target a
        stated byte size, reached in whole stated units and
        never by cutting a unit."""
        unit_len = len(fg.BASE_FIXTURES["w1-answer-unit"]["unit"]
                       .replace(b"INDEX", b"1"))
        data, prov = fg.generate(
            "w1-answer-unit", "scaling", target_bytes=unit_len * 3 + 1)
        self.assertEqual(len(data) % unit_len, 0)
        self.assertGreaterEqual(len(data), unit_len * 3 + 1)
        self.assertLess(len(data), unit_len * 5)

    def test_scale_varies_only_named_fields(self):
        """Pins plan Section 1.6 CQ-D29: scaling varies only
        the fields the catalogue entry names as varied, and
        no other field."""
        data, _ = fg.generate(
            "w1-journal-entry-unit", "scaling", target_count=3)
        lines = data.decode("utf-8").splitlines()
        self.assertEqual(len(lines), 3)
        stripped = [ln.replace('"sequence":%d' % (i + 1), '"sequence":N')
                    for i, ln in enumerate(lines)]
        self.assertEqual(len(set(stripped)), 1)
        for i, ln in enumerate(lines):
            self.assertIn('"sequence":%d' % (i + 1), ln)

    def test_scale_target_one_is_the_base_unit_at_index_one(self):
        """Pins plan Section 1.6 CQ-D29: the scaled form at
        count one is the base unit with its varied field at
        its first value."""
        data, _ = fg.generate(
            "w1-answer-unit", "scaling", target_count=1)
        self.assertEqual(data, fg.BASE_FIXTURES["w1-answer-unit"]["unit"]
                         .replace(b"INDEX", b"1"))


class MutationRouteTests(unittest.TestCase):
    def test_each_listed_mutation_applies_exactly(self):
        """Pins plan Section 1.6 CQ-D29 mutation route: the
        generator applies exactly the mutations the catalogue
        entry lists, and no other change."""
        base = fg.BASE_FIXTURES["w1-journal-entry-unit"]["unit"] \
            .replace(b"INDEX", b"1")
        data, prov = fg.generate(
            "w1-journal-entry-unit", "mutation",
            mutations=["append-partial-line"])
        self.assertTrue(data.startswith(base))
        self.assertEqual(prov["mutations"], ["append-partial-line"])

    def test_mutation_truncate_final_line(self):
        """Pins plan Section 1.6 CQ-D29: the truncate final
        line mutation removes the final newline and the
        final three bytes, and nothing else."""
        base = fg.BASE_FIXTURES["w1-journal-entry-unit"]["unit"] \
            .replace(b"INDEX", b"1")
        data, _ = fg.generate(
            "w1-journal-entry-unit", "mutation",
            mutations=["truncate-final-line"])
        self.assertEqual(data, base[:-4])

    def test_mutation_duplicate_unit_repeats_the_whole_unit(self):
        """Pins plan Section 1.6 CQ-D29: duplicate-unit on
        the multi line w1-page-section-unit repeats the
        whole stated unit exactly, both of its lines, so
        the product stands at twice the unit byte size
        (Step 13 test audit round 1, entry R1-014)."""
        base = fg.BASE_FIXTURES["w1-page-section-unit"]["unit"] \
            .replace(b"INDEX", b"1")
        data, prov = fg.generate(
            "w1-page-section-unit", "mutation",
            mutations=["duplicate-unit"])
        self.assertEqual(data, base + base)
        self.assertEqual(len(data), 2 * len(base))
        self.assertEqual(prov["mutations"], ["duplicate-unit"])

    def test_mutation_reverse_lines_reverses_the_whole_unit(self):
        """Pins plan Section 1.6 CQ-D29: reverse-lines on
        the multi line w1-page-section-unit gives its two
        lines in reverse order, the body line first and the
        heading line second (Step 13 test audit round 1,
        entry R1-014)."""
        base = fg.BASE_FIXTURES["w1-page-section-unit"]["unit"] \
            .replace(b"INDEX", b"1")
        lines = base.splitlines(keepends=True)
        self.assertEqual(len(lines), 2)
        data, _ = fg.generate(
            "w1-page-section-unit", "mutation",
            mutations=["reverse-lines"])
        self.assertEqual(data, lines[1] + lines[0])

    def test_two_mutations_without_a_stated_combination_stop(self):
        """Pins plan Section 1.6 CQ-D29: one mutation per
        fixture unless the catalogue entry states a
        combination; no w1 entry states one, so a pair is
        refused."""
        with self.assertRaises(fg.GenerationRefused):
            fg.generate("w1-journal-entry-unit", "mutation",
                        mutations=["append-partial-line",
                                   "truncate-final-line"])

    def test_unlisted_mutation_stops(self):
        """Pins plan Section 1.6 CQ-D29: a mutation the
        catalogue entry does not list is not applied."""
        with self.assertRaises(fg.GenerationRefused):
            fg.generate("w1-journal-entry-unit", "mutation",
                        mutations=["shuffle-words"])


class DeterminismTests(unittest.TestCase):
    def test_same_inputs_same_bytes(self):
        """Pins plan Section 1.6 CQ-D30: the same base, route,
        and parameters produce the same bytes."""
        first, _ = fg.generate("w1-page-section-unit", "scaling",
                               target_count=7)
        second, _ = fg.generate("w1-page-section-unit", "scaling",
                                target_count=7)
        self.assertEqual(first, second)

    def test_no_run_dependent_content(self):
        """Pins plan Section 1.5 determinism statement and
        CQ-D30: procedure fixtures stand generated from
        stated parameters with no run dependent content, so
        a mutation product is byte stable across calls."""
        first, _ = fg.generate("w1-journal-entry-unit", "mutation",
                               mutations=["reverse-lines"])
        second, _ = fg.generate("w1-journal-entry-unit", "mutation",
                                mutations=["reverse-lines"])
        self.assertEqual(first, second)


class ProvenanceTests(unittest.TestCase):
    def test_provenance_record_fields(self):
        """Pins plan Section 1.6 CQ-D29: provenance stands
        recorded per fixture with the base fixture
        identifier, the route, the target or mutation list,
        the generator name and version, and the produced
        byte size and sha256."""
        data, prov = fg.generate("w1-answer-unit", "scaling",
                                 target_count=4)
        self.assertEqual(prov["base"], "w1-answer-unit")
        self.assertEqual(prov["route"], "scaling")
        self.assertEqual(prov["generator"], fg.GENERATOR_NAME)
        self.assertEqual(prov["generator_version"], fg.GENERATOR_VERSION)
        self.assertEqual(prov["byte_size"], len(data))
        self.assertEqual(prov["sha256"],
                         hashlib.sha256(data).hexdigest())

    def test_recorded_provenance_checked_on_later_use(self):
        """Pins plan Section 1.6 CQ-D29: the recorded byte
        size and sha256 stand checked on every later use, so
        altered bytes fail the check."""
        data, prov = fg.generate("w1-answer-unit", "scaling",
                                 target_count=2)
        self.assertTrue(fg.check_provenance(prov, data))
        self.assertFalse(fg.check_provenance(prov, data + b"x"))


class StopRuleTests(unittest.TestCase):
    def test_cl13_list_member_mutation_stops_at_seam_lists(self):
        """Pins plan Section 1.6 CQ-D29 stop rule: a fixture
        whose generation would need a CL-13 list member
        stops at SEAM-LISTS and is not produced."""
        with self.assertRaises(fg.SeamListsStop):
            fg.generate("w1-answer-unit", "mutation",
                        mutations=["append-lexicon-term"])

    def test_unknown_base_stops(self):
        """Pins plan Section 1.6 gate rule in generator form:
        a base fixture with no catalogue entry is not
        generated from."""
        with self.assertRaises(fg.GenerationRefused):
            fg.generate("w1-no-such-base", "scaling", target_count=2)


if __name__ == "__main__":
    unittest.main()
