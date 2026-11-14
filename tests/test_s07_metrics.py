"""Slice S7 metrics and trend tests, Step 13, Citeline.

Written before the product exists. Every test imports the
product package citeline and calls the metrics operations
under the names the plan states (plan Section 5.3 module
boundary row for S7, module metrics; plan Section 5.1
RoundMetrics and ProbeTrend shapes), with the AnswerMetrics
recomputation of plan Section 5.2 called on the metrics
home, in the same invocation. Where a test in this file
claims the ProbeTrend shape or the report shape as an
operation surface, it calls the service operations,
service.probe_trend and service.probe_report, in the form
the sibling modules use; the remaining tests in this file
claim the computations only and stay on the metrics home.
Import or attribute failure is the expected red state. No
stub and no mock of the product stands in this file.

Metrics consume AnswerMetrics only, on contract 4 terms:
the per answer inputs in this file carry the AnswerMetrics
fields of plan Section 5.1 together with the AnswerRecord
context fields (query, engine label, capture method,
asserted capture date, source kind, control flag) that the
same plan section states, because the plan Section 1.5
trace states RoundMetrics computes from AnswerMetrics over
both Section 5.2 inputs.

Ground that stands blocked for this slice stands in
blocked-w5.md and no test in this file pins it: every
stratum effective n derivation, the contract C4 binding
limb, the bound limb of any figure resting on the
clustering index, and the identity of an unqualified cited
rate. Identifier discipline: C4 in this file is the
Section 11 consistency contract only, never the quotations
check of the brief condition numbering; the two senses are
merged nowhere.
"""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from citeline import metrics, service

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def has_field(record, name):
    if isinstance(record, dict):
        return name in record
    return hasattr(record, name)


def field_names(record):
    if isinstance(record, dict):
        return list(record.keys())
    return [name for name in vars(record)]


def answer(named=False, named_early=False, cited=False, cluster_id=0,
           query="q-one", engine="EngineA", method="by hand",
           captured_on="2026-11-01", kind="sampled", control=False,
           competitor_named=False, aliases=None, citations=0,
           self_citations=0, text=""):
    return {
        "named": named,
        "named_early": named_early,
        "cited": cited,
        "cluster_id": cluster_id,
        "near_duplicate": False,
        "matched_aliases": list(aliases or []),
        "query": query,
        "engine_label": engine,
        "capture_method": method,
        "captured_on": captured_on,
        "source_kind": kind,
        "control": control,
        "competitor_named": competitor_named,
        "citation_instances": citations,
        "self_citation_instances": self_citations,
        "text": text,
    }


def distinct_answers(count, **kwargs):
    return [answer(cluster_id=i, **kwargs) for i in range(count)]


class TestWilsonInterval(unittest.TestCase):
    def test_wilson_at_rate_half_effective_n_20(self):
        """Plan Section 1.3 S7 family, rates, tiers, and intervals on effective n; brief Section 10.5 primitive P11. Oracle: brief Section 5.8 item 20 statement of the Wilson construction, evaluated at the rate value with sample size effective n, z equal to 1.96, clamped to 0 to 1. Hand computed: rate 0.5, effective n 20 gives 0.2993 to 0.7007."""
        low, high = metrics.wilson_interval(0.5, 20)
        self.assertAlmostEqual(low, 0.2993, places=4)
        self.assertAlmostEqual(high, 0.7007, places=4)

    def test_wilson_clamped_at_one_for_full_rate_small_n(self):
        """Plan Section 1.3 S7 family, intervals; brief Section 5.8 item 59. Oracle: the Wilson interval with z equal to 1.96, clamped to 0 to 1, stands as the interval at every sample size including the smallest. Hand computed: rate 1.0, effective n 1 gives 0.2065 to 1.0."""
        low, high = metrics.wilson_interval(1.0, 1)
        self.assertAlmostEqual(low, 0.2065, places=4)
        self.assertEqual(high, 1.0)

    def test_wilson_at_zero_rate(self):
        """Plan Section 1.3 S7 family, intervals. Oracle: brief Section 5.8 item 20 Wilson construction. Hand computed: rate 0.0, effective n 10 gives 0.0 to 0.2775."""
        low, high = metrics.wilson_interval(0.0, 10)
        self.assertEqual(low, 0.0)
        self.assertAlmostEqual(high, 0.2775, places=4)

    def test_wilson_at_effective_n_zero_is_null(self):
        """Plan Section 1.3 S7 family, intervals; brief Section 10.5 primitive P11. Oracle: primitive P11, a rate with n equal to 0 reports a null rate and a null interval."""
        self.assertIsNone(metrics.wilson_interval(0.0, 0))


class TestRatesAndTiers(unittest.TestCase):
    def test_rate_runs_on_all_answers_at_equal_weight(self):
        """Plan Section 1.3 S7 family, rates; brief Section 5.8 item 129. Oracle: item 129 and the effective n statement at item 20, the rate value runs on all answers of the kind with equal weight, and duplication moves the rate value itself. Three answers, one named and two copies of one unnamed answer in one cluster, give a named rate of 1 of 3."""
        answers = [
            answer(named=True, cluster_id=0),
            answer(named=False, cluster_id=1),
            answer(named=False, cluster_id=1),
        ]
        result = metrics.round_metrics(answers, "sampled")
        named = field(field(result, "rates"), "named")
        self.assertAlmostEqual(field(named, "rate"), 1 / 3, places=6)
        self.assertEqual(field(named, "n"), 3)
        self.assertEqual(field(result, "effective_n"), 2)
        self.assertEqual(field(result, "cluster_count"), 2)

    def test_interval_and_tier_run_on_effective_n_not_raw_n(self):
        """Plan Section 1.3 S7 family, rates, tiers, and intervals on effective n; brief Section 10.5 primitive P12. Oracle: primitive P12, tiers are assigned by effective n only. A round of 50 copies of one named answer forms one cluster, carries effective n of 1, and stands at the count only tier, not reportable, while its rate stands at 1.0."""
        answers = [answer(named=True, cluster_id=0) for _ in range(50)]
        result = metrics.round_metrics(answers, "sampled")
        named = field(field(result, "rates"), "named")
        self.assertEqual(field(named, "rate"), 1.0)
        self.assertEqual(field(result, "effective_n"), 1)
        self.assertEqual(field(named, "tier"), "count only")
        low, high = field(named, "wilson_low"), field(named, "wilson_high")
        self.assertAlmostEqual(low, 0.2065, places=4)
        self.assertEqual(high, 1.0)

    def test_tier_boundaries_on_effective_n(self):
        """Plan Section 1.3 S7 family, tiers under the labels only ruling; brief Section 5.8 item 124. Oracle: item 124, the tier set is count only under 5, exploratory 5 to 19, provisional 20 to 49, and reportable 50 and over, the thresholds running on effective n. No test in this file sets or assumes a sample target a round must meet."""
        self.assertEqual(metrics.tier_for(0), "count only")
        self.assertEqual(metrics.tier_for(4), "count only")
        self.assertEqual(metrics.tier_for(5), "exploratory")
        self.assertEqual(metrics.tier_for(19), "exploratory")
        self.assertEqual(metrics.tier_for(20), "provisional")
        self.assertEqual(metrics.tier_for(49), "provisional")
        self.assertEqual(metrics.tier_for(50), "reportable")
        self.assertEqual(metrics.tier_for(500), "reportable")

    def test_rate_block_carries_n_interval_tier_warning_and_no_coverage_claim(self):
        """Plan Section 1.3 S7 family, rates and intervals; brief Section 10.5 primitive P11. Oracle: primitive P11, every probe rate carries its n, its Wilson interval, its tier, and its warning in the same block, and plan Section 5.1 RoundMetrics, coverage_probability_claimed stands as the boolean false in the Agentic form and no coverage probability is claimed. Hand computed: the round stands at rate 1.0 with effective n 20, so its Wilson interval stands at 0.8389 to 1.0."""
        answers = distinct_answers(20, named=True)
        result = metrics.round_metrics(answers, "sampled")
        named = field(field(result, "rates"), "named")
        self.assertEqual(field(named, "n"), 20)
        self.assertAlmostEqual(field(named, "wilson_low"), 0.8389, places=4)
        self.assertAlmostEqual(field(named, "wilson_high"), 1.0, places=4)
        self.assertEqual(field(named, "tier"), "provisional")
        self.assertTrue(has_field(named, "small_sample_warning"))
        self.assertIs(field(named, "coverage_probability_claimed"), False)

    def test_kinds_never_pooled(self):
        """Plan Section 1.3 S7 family, rates. Oracle: plan Section 5.1 RoundMetrics, computed per source kind, never pooled across kinds and never across products, and brief Section 5.8 item 129."""
        answers = [answer(named=True, cluster_id=0, kind="sampled"),
                   answer(named=False, cluster_id=1, kind="fixture")]
        result = metrics.round_metrics(answers, "sampled")
        named = field(field(result, "rates"), "named")
        self.assertEqual(field(named, "n"), 1)
        self.assertEqual(field(named, "rate"), 1.0)

    def test_empty_round_reports_null_rate_null_interval_count_only_zero(self):
        """Plan Section 1.3 S7 family, rates; brief Section 5.8 n of 0 rule stated with item 129. Oracle: on an empty round the rate is null, the interval is null, and the tier is the count only tier stated as a count of zero."""
        result = metrics.round_metrics([], "sampled")
        named = field(field(result, "rates"), "named")
        self.assertIsNone(field(named, "rate"))
        self.assertIsNone(field(named, "wilson_low"))
        self.assertIsNone(field(named, "wilson_high"))
        self.assertEqual(field(named, "tier"), "count only")
        self.assertEqual(field(named, "n"), 0)
        self.assertEqual(field(result, "effective_n"), 0)


class TestBreakdowns(unittest.TestCase):
    def test_per_query_breakdown_counts(self):
        """Plan Section 1.3 S7 family, per query breakdowns. Oracle: plan Section 5.1 RoundMetrics, the shape holds a per query breakdown, and brief Section 5.8 item 58, a per query rate is shown at any n with its tier and warning, and at count only tier as a count. The breakdown rows in this test proceed on the round level effective n; no stratum effective n is derived, that derivation standing blocked on L-ID-2 in blocked-w5.md."""
        answers = [
            answer(named=True, cluster_id=0, query="q-one"),
            answer(named=False, cluster_id=1, query="q-one"),
            answer(named=True, cluster_id=2, query="q-two"),
            answer(named=True, cluster_id=3, query="q-two"),
        ]
        result = metrics.round_metrics(answers, "sampled")
        per_query = field(result, "per_query")
        self.assertEqual(field(per_query["q-one"], "answer_count"), 2)
        self.assertEqual(field(per_query["q-one"], "named_count"), 1)
        self.assertEqual(field(per_query["q-two"], "named_count"), 2)
        self.assertFalse(has_field(per_query["q-one"], "stratum_effective_n"))

    def test_per_competitor_breakdown_and_empty_domain_cited_not_applicable(self):
        """Plan Section 1.3 S7 family, per competitor breakdowns. Oracle: plan Section 5.1 RoundMetrics per competitor breakdown, for a competitor whose domain stands empty the cited figure stands as not applicable with that reason, carrying no rate value, never as zero, and never pooled into any rate, as grill Q17 decides, while mention figures still compute."""
        answers = [
            answer(cluster_id=0, competitor_named=True),
            answer(cluster_id=1, competitor_named=False),
        ]
        answers[0]["competitors"] = [{"name": "Nodomain", "named": True, "cited": None}]
        answers[1]["competitors"] = [{"name": "Nodomain", "named": False, "cited": None}]
        result = metrics.round_metrics(answers, "sampled")
        per_competitor = field(result, "per_competitor")
        entry = per_competitor["Nodomain"]
        self.assertEqual(field(entry, "named_count"), 1)
        self.assertIsNone(field(entry, "cited_rate"))
        self.assertTrue(field(entry, "cited_reason"))

    def test_per_alias_match_counts_disclosed_never_inside_a_rate(self):
        """Plan Section 1.3 S7 family, per alias breakdowns. Oracle: plan Section 5.1 RoundMetrics, per alias match counts stand as disclosed figures in the counts table, never inside a rate, and brief Section 10.4 primitive P64, counted once per answer per alias on the named outcome basis only."""
        answers = [
            answer(named=True, cluster_id=0, aliases=["Northbeam"]),
            answer(named=True, cluster_id=1, aliases=["Northbeam", "Northbeam Analytics"]),
            answer(named=False, cluster_id=2),
        ]
        result = metrics.round_metrics(answers, "sampled")
        counts = field(result, "per_alias_counts")
        self.assertEqual(counts["Northbeam"], 2)
        self.assertEqual(counts["Northbeam Analytics"], 1)
        named = field(field(result, "rates"), "named")
        self.assertAlmostEqual(field(named, "rate"), 2 / 3, places=6)


class TestClusteringFiguresDisclosed(unittest.TestCase):
    def test_cluster_figures_disclosed_and_never_inside_a_rate(self):
        """Plan Section 1.3 S7 family, clustering figures as disclosed figures only. Oracle: plan Section 1.5 reverse trace table, cluster count, effective n, and disclosed cluster figures render from the RoundMetrics computation, disclosed only, never inside a rate; the rates in this round run on all four answers while the interval and tier run on effective n of 3."""
        answers = [
            answer(named=True, cluster_id=0),
            answer(named=True, cluster_id=0),
            answer(named=False, cluster_id=1),
            answer(named=True, cluster_id=2),
        ]
        result = metrics.round_metrics(answers, "sampled")
        self.assertEqual(field(result, "cluster_count"), 3)
        self.assertEqual(field(result, "effective_n"), 3)
        named = field(field(result, "rates"), "named")
        self.assertAlmostEqual(field(named, "rate"), 0.75, places=6)
        self.assertEqual(field(named, "tier"), "count only")

    def test_largest_cluster_share_and_chained_cluster_count(self):
        """Plan Section 1.3 S7 family, clustering figures; brief Section 10.5 primitive P61. Oracle: primitive P61, each per kind RoundMetrics set carries the largest cluster share and the chained cluster count as disclosed figures. One cluster of three answers chained through pairwise similarity gives a largest cluster share of 1.0 and a chained cluster count of 1. The pairwise chain facts stand pinned in test_s06_detection.py."""
        chain_texts = []
        for name in ("w5-chain-a.txt", "w5-chain-b.txt", "w5-chain-c.txt"):
            with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as handle:
                chain_texts.append(handle.read().strip())
        answers = [answer(cluster_id=0, text=text) for text in chain_texts]
        result = metrics.round_metrics(answers, "sampled")
        self.assertAlmostEqual(field(result, "largest_cluster_share"), 1.0, places=6)
        self.assertEqual(field(result, "chained_cluster_count"), 1)

    def test_design_effect_is_a_derived_figure_only(self):
        """Plan Section 1.3 S7 family, clustering figures. Oracle: brief Section 5.8 item 20, the design effect is a derived figure only, the total number of answers divided by the number of clusters, and effective n stated as the total divided by that design effect gives the same cluster count."""
        answers = distinct_answers(4, named=True)
        answers[1]["cluster_id"] = 0
        result = metrics.round_metrics(answers, "sampled")
        self.assertEqual(field(result, "cluster_count"), 3)
        self.assertAlmostEqual(field(result, "design_effect"), 4 / 3, places=6)
        self.assertEqual(field(result, "effective_n"), 3)


class TestCountsAndCitationFigures(unittest.TestCase):
    def test_citing_answer_and_citation_instance_counts(self):
        """Plan Section 1.3 S7 family, counts. Oracle: brief Section 5.8 item 29 statement with proposals P5-10 and P5-14, a citation instance is one resolved citation target in one answer and a citing answer is an answer holding at least one citation instance, both figures shipping on RoundMetrics."""
        answers = [
            answer(cluster_id=0, citations=2),
            answer(cluster_id=1, citations=1),
            answer(cluster_id=2, citations=0),
        ]
        result = metrics.round_metrics(answers, "sampled")
        self.assertEqual(field(result, "citing_answer_count"), 2)
        self.assertEqual(field(result, "citation_instance_count"), 3)

    def test_self_citation_share_and_cited_rates_gross_and_net(self):
        """Plan Section 1.3 S7 family, citation figures. Oracle: brief Section 5.8 item 29, the cited rate gross counts an answer as cited where it holds at least one citation instance of any kind, the cited rate net counts an answer only where it holds at least one instance that is not a self citation, and self citation share is self citation instances divided by all citation instances in the round. Hand computed for this round: gross 1.0, net 0.5, share 2 of 3. The identity of an unqualified cited rate stands blocked on L-SB-2 in blocked-w5.md and no assertion in this test rests on it."""
        answers = [
            answer(cluster_id=0, citations=2, self_citations=1),
            answer(cluster_id=1, citations=1, self_citations=1),
        ]
        result = metrics.round_metrics(answers, "sampled")
        self.assertAlmostEqual(field(result, "cited_rate_gross"), 1.0, places=6)
        self.assertAlmostEqual(field(result, "cited_rate_net"), 0.5, places=6)
        self.assertAlmostEqual(field(result, "self_citation_share"), 2 / 3, places=6)

    def test_self_citation_share_null_where_no_instances(self):
        """Plan Section 1.3 S7 family, citation figures. Oracle: brief Section 5.8 n of 0 rule extended to every ratio figure, where its denominator is zero the self citation share is null."""
        result = metrics.round_metrics(distinct_answers(2), "sampled")
        self.assertIsNone(field(result, "self_citation_share"))

    def test_no_name_count_and_share_disclosed_only(self):
        """Plan Section 1.3 S7 family, disclosed figures; brief Section 10.5 primitive P60. Oracle: primitive P60, the no name count stands for answers naming neither the product, nor any registered competitor, nor any alias of either, with its share over the answers of the kind, outside the authoritative rates object and never a headline rate."""
        answers = [
            answer(cluster_id=0),
            answer(cluster_id=1, named=True),
            answer(cluster_id=2, competitor_named=True),
            answer(cluster_id=3),
        ]
        result = metrics.round_metrics(answers, "sampled")
        self.assertEqual(field(result, "no_name_count"), 2)
        self.assertAlmostEqual(field(result, "no_name_share"), 0.5, places=6)
        self.assertNotIn("no_name", field(result, "rates"))

    def test_no_name_share_absent_where_kind_holds_no_answers(self):
        """Plan Section 1.3 S7 family, disclosed figures; brief Section 10.5 primitive P60. Oracle: primitive P60, where a kind holds no answers the count prints as 0 and no share figure stands: the share stands absent, not as a null and not as a numeric 0."""
        result = metrics.round_metrics([], "sampled")
        self.assertEqual(field(result, "no_name_count"), 0)
        self.assertFalse(has_field(result, "no_name_share"))

    def test_empty_answer_count(self):
        """Plan Section 1.3 S7 family, counts; brief Section 10.5 primitive P62. Oracle: primitive P62, empty_answer_count counts answers empty in the extracted text sense, empty or whitespace only, per source kind and never pooled."""
        answers = distinct_answers(3)
        answers[0]["text"] = ""
        answers[1]["text"] = "   "
        answers[2]["text"] = "A real answer body."
        result = metrics.round_metrics(answers, "sampled")
        self.assertEqual(field(result, "empty_answer_count"), 2)

    def test_controls_enter_no_rate_count_or_cluster(self):
        """Plan Section 1.3 S7 family, counts; brief Section 10.5 primitive P63. Oracle: primitive P63, a designated control answer enters no rate, count, cluster, effective n, or tier of either kind class, and for each kind the count imported equals n plus the control count, the control count disclosed on RoundMetrics."""
        answers = distinct_answers(4, named=True)
        answers.append(answer(named=True, cluster_id=99, control=True))
        result = metrics.round_metrics(answers, "sampled")
        self.assertEqual(field(result, "imported_count"), 5)
        self.assertEqual(field(result, "control_count"), 1)
        self.assertEqual(field(result, "cluster_count"), 4)
        named = field(field(result, "rates"), "named")
        self.assertEqual(field(named, "n"), 4)

    def test_no_share_of_voice_or_market_share_field(self):
        """Plan Section 1.3 S7 family, shape conformance. Oracle: plan Section 5.1 RoundMetrics, no share of voice or market share field ships, on brief Section 5.8 item 62, with self_citation_share expressly excepted from that bar."""
        result = metrics.round_metrics(distinct_answers(2, named=True), "sampled")
        for name in field_names(result):
            self.assertNotIn("share_of_voice", name)
            self.assertNotIn("market_share", name)


class TestGuardsAsComputations(unittest.TestCase):
    def test_g1_sampling_frame_carried_beside_rates(self):
        """Plan Section 1.3 S7 family, guard G1 as a computation. Oracle: brief Section 5.8 item 19, every probe output carries the sampling frame beside every rate: query set version, engine label set, capture method as asserted, and the count imported, plus the importer declaration with its three values only, stated as unverifiable by the tool."""
        answers = distinct_answers(3, named=True)
        result = metrics.round_metrics(answers, "sampled", frame={
            "query_set_version": 4,
            "importer_declaration": "all_captured",
        })
        frame = field(result, "sampling_frame")
        self.assertEqual(field(frame, "query_set_version"), 4)
        self.assertEqual(set(field(frame, "engine_label_set")), {"EngineA"})
        self.assertEqual(set(field(frame, "capture_methods_asserted")), {"by hand"})
        self.assertEqual(field(frame, "imported_count"), 3)
        self.assertEqual(field(frame, "importer_declaration"), "all_captured")
        self.assertIs(field(frame, "declaration_unverifiable"), True)

    def test_g3_composition_figures_and_dominance(self):
        """Plan Section 1.3 S7 family, guard G3 as a computation. Oracle: brief Section 5.8 item 21 with item 76, every pooled rate prints its composition, the largest engine label share, the largest query share, and the largest single day share, each as a count and a percentage of n, and where any one asserted engine label, query, or day supplies more than half of a round the pooled rate carries a dominance note. Hand computed: three of four answers from one engine give a largest engine share of 3 and 75 percent, over half, so the note stands."""
        answers = distinct_answers(4, named=True)
        answers[3]["engine_label"] = "EngineB"
        result = metrics.round_metrics(answers, "sampled")
        composition = field(result, "composition")
        self.assertEqual(field(composition, "largest_engine_share_count"), 3)
        self.assertAlmostEqual(field(composition, "largest_engine_share_percent"), 75.0, places=4)
        self.assertEqual(field(composition, "largest_query_share_count"), 4)
        self.assertEqual(field(composition, "largest_day_share_count"), 4)
        self.assertTrue(field(composition, "dominance_note"))

    def test_g3_no_dominance_at_exactly_half(self):
        """Plan Section 1.3 S7 family, guard G3 as a computation. Oracle: brief Section 5.8 item 76, the dominance line stands at more than half of a round, so a largest share of exactly half carries no dominance note."""
        answers = distinct_answers(4, named=True)
        answers[2]["engine_label"] = "EngineB"
        answers[3]["engine_label"] = "EngineB"
        result = metrics.round_metrics(answers, "sampled")
        composition = field(result, "composition")
        self.assertEqual(field(composition, "largest_engine_share_count"), 2)
        self.assertFalse(field(composition, "dominance_note"))

    def test_g4_overlapping_intervals_do_not_separate(self):
        """Plan Section 1.3 S7 family, guard G4 as a computation. Oracle: brief Section 5.8 item 22 with item 74, the separation rule is Wilson interval overlap: where two compared rates have overlapping Wilson intervals, the sample does not separate them."""
        self.assertFalse(metrics.rates_separated((0.2993, 0.7007), (0.2500, 0.7500)))
        self.assertTrue(metrics.rates_separated((0.2993, 0.7007), (0.0, 0.2775)))

    def test_g8_note_names_every_changed_axis_including_capture_dates(self):
        """Plan Section 1.3 S7 family, guard G8 as a computation. Oracle: brief Section 5.8 item 26, the axes the composition changed note names are exactly per query answer counts, engine shares, capture dates, and cluster composition, and every changed axis among them is named; contract C5 adds that a capture date difference alone triggers neither form, so the dates axis stands named here beside a second changed axis, in the case the delta test in this file does not cover."""
        first = trend_round(0.5, {"capture_dates": ["2026-11-01"]})
        second = trend_round(0.75, {
            "per_query_counts": {"q-one": 12, "q-two": 8},
            "capture_dates": ["2026-11-08"],
        })
        trend = metrics.compute_trend(first, second)
        self.assertIsNone(field(trend, "delta"))
        axes = field(trend, "composition_changed_axes")
        self.assertIn("per query answer counts", axes)
        self.assertIn("capture dates", axes)


def trend_round(rate_named, frame_overrides=None, answers=None):
    if answers is None:
        total = 20
        named_count = int(rate_named * total)
        answers = []
        for i in range(total):
            answers.append(answer(named=i < named_count, cluster_id=i,
                                  query="q-one" if i < 10 else "q-two",
                                  engine="EngineA" if i < 10 else "EngineB"))
    result = metrics.round_metrics(answers, "sampled")
    frame = {
        "per_query_counts": {"q-one": 10, "q-two": 10},
        "engine_shares": {"EngineA": 50.0, "EngineB": 50.0},
        "capture_methods": ["by hand"],
        "capture_dates": ["2026-11-01"],
        "registry_version": 1,
        "detector_version": 1,
        "query_set_version": 1,
        "lexicon_version": 1,
        "cluster_count": field(result, "cluster_count"),
        "effective_n": field(result, "effective_n"),
    }
    if frame_overrides:
        frame.update(frame_overrides)
    return {"metrics": result, "frame": frame}


class TestTrendContractC5(unittest.TestCase):
    def test_delta_prints_over_comparable_composition(self):
        """Plan Section 1.3 S7 family, contract C5 trend in full on its decided limbs; brief Section 5.4 example E4. Oracle: contract C5 and brief Section 5.8 item 26, a delta stands printed only over comparable composition, and a capture date difference alone is not a break. Two rounds of 10 answers per query, same engine shares, same capture method, same four version stamps, capture dates a week apart: the named rate moves from 0.5 to 0.75 and the delta of 0.25 prints, with the capture method sets of both rounds shown beside it in asserted and normalised forms and the honesty line beside the delta."""
        first = trend_round(0.5, {"capture_dates": ["2026-11-01"]})
        second = trend_round(0.75, {"capture_dates": ["2026-11-08"]})
        trend = metrics.compute_trend(first, second)
        self.assertIsNone(field(trend, "series_break"))
        self.assertAlmostEqual(field(trend, "delta"), 0.25, places=6)
        self.assertEqual(
            field(trend, "honesty_line"),
            "comparability is shown only for the recorded frame, and a silent engine change under a fixed label cannot be shown",
        )
        shown = field(trend, "capture_method_sets")
        self.assertEqual(field(field(shown, "first"), "asserted"), ["by hand"])
        self.assertEqual(field(field(shown, "first"), "normalised"), ["by hand"])

    def test_capture_method_set_change_breaks_series(self):
        """Plan Section 1.3 S7 family, contract C5 trend. Oracle: contract C5, a change in the capture method set between the two rounds stands as a series break trigger: where a break trigger stands, no delta stands printed, both values stand printed, and the break stands stated."""
        first = trend_round(0.5)
        second = trend_round(0.75, {"capture_methods": ["export"]})
        trend = metrics.compute_trend(first, second)
        self.assertIsNone(field(trend, "delta"))
        self.assertTrue(field(trend, "series_break"))
        self.assertAlmostEqual(field(trend, "first_value"), 0.5, places=6)
        self.assertAlmostEqual(field(trend, "second_value"), 0.75, places=6)

    def test_version_change_breaks_series(self):
        """Plan Section 1.3 S7 family, contract C5 trend. Oracle: contract C5 and brief Section 5.8 item 130, a change in registry version, detector version, lexicon version, or query set version between the rounds stands as a series break trigger with no delta printed across it."""
        for axis in ("registry_version", "detector_version", "query_set_version", "lexicon_version"):
            first = trend_round(0.5)
            second = trend_round(0.75, {axis: 2})
            trend = metrics.compute_trend(first, second)
            self.assertIsNone(field(trend, "delta"), axis)
            self.assertTrue(field(trend, "series_break"), axis)

    def test_ruleset_and_crawler_table_versions_break_no_series(self):
        """Plan Section 1.3 S7 family, trend datum discipline. Oracle: plan Section 5.1 RoundMetrics datum declaration, the ruleset version and the crawler table version stand outside the datum, neither is a datum axis, and a change of either breaks no series."""
        first = trend_round(0.5, {"ruleset_version": 1})
        second = trend_round(0.75, {"ruleset_version": 2})
        trend = metrics.compute_trend(first, second)
        self.assertIsNone(field(trend, "series_break"))
        self.assertAlmostEqual(field(trend, "delta"), 0.25, places=6)

    def test_per_query_count_change_is_composition_changed_not_break(self):
        """Plan Section 1.3 S7 family, contract C5 trend. Oracle: contract C5, where composition differs on an axis guard G8 governs and no break trigger stands, no delta stands printed, both values stand printed, and a composition changed note naming every axis that changed stands printed."""
        first = trend_round(0.5)
        second = trend_round(0.75, {"per_query_counts": {"q-one": 12, "q-two": 8}})
        trend = metrics.compute_trend(first, second)
        self.assertIsNone(field(trend, "delta"))
        self.assertIsNone(field(trend, "series_break"))
        self.assertIn("per query answer counts", field(trend, "composition_changed_axes"))

    def test_cluster_composition_change_named_in_note(self):
        """Plan Section 1.3 S7 family, contract C5 trend. Oracle: contract C5, cluster composition stands on the composition changed axis guard G8 governs: where the two rounds differ in cluster composition, no delta stands printed and the composition changed note naming cluster composition stands printed in its place."""
        first = trend_round(0.5)
        second = trend_round(0.75, {"cluster_count": 19, "effective_n": 19})
        trend = metrics.compute_trend(first, second)
        self.assertIsNone(field(trend, "delta"))
        self.assertIn("cluster composition", field(trend, "composition_changed_axes"))

    def test_mixed_methods_inside_one_round_are_not_a_break(self):
        """Plan Section 1.3 S7 family, contract C5 trend. Oracle: contract C5, a mix of capture method values inside one round is not a break, and brief Section 5.8 IM7-BRK-4 landing, two asserted spellings normalising to one form count once in the set, the comparison standing at set level over normalised forms (trimmed, case folded, whitespace collapsed, after NFC)."""
        first = trend_round(0.5, {"capture_methods": ["by hand"]})
        second = trend_round(0.75, {"capture_methods": ["by hand", "By  Hand "]})
        trend = metrics.compute_trend(first, second)
        self.assertIsNone(field(trend, "series_break"))
        self.assertAlmostEqual(field(trend, "delta"), 0.25, places=6)

    def test_both_rounds_empty_prints_both_null_values_and_no_delta(self):
        """Plan Section 1.3 S7 family, contract C5 trend. Oracle: contract C5, where both rounds exist and both stand empty, the trend prints both null values, each the null rate at n of 0, with an express statement that no delta stands printed for that pair."""
        first = trend_round(0.0, answers=[])
        second = trend_round(0.0, answers=[])
        trend = metrics.compute_trend(first, second)
        self.assertIsNone(field(trend, "delta"))
        self.assertIsNone(field(trend, "first_value"))
        self.assertIsNone(field(trend, "second_value"))
        self.assertTrue(field(trend, "no_delta_statement"))


class TestContractC4ComputationLimbs(unittest.TestCase):
    def test_report_rates_computed_over_one_answer_set_with_stamps_travelling(self):
        """Plan Section 1.3 S7 family, contract C4 rows severed at the join, computation limb. Identifier: contract C4 is the Section 11 consistency contract. Oracle: contract C4, every rate in one report stands computed over the same set of stored answers, under the same registry version, the same query set version, the same ruleset version, and the same detector version, and those stamps travel in the report. The binding limb stands blocked on K-18 in blocked-w5.md and no assertion in this test rests on it."""
        answers = distinct_answers(4, named=True)
        result = metrics.round_metrics(answers, "sampled", datum={
            "registry_version": 3, "query_set_version": 2,
            "ruleset_version": 5, "detector_version": 7,
        })
        stamps = field(result, "version_stamps")
        self.assertEqual(field(stamps, "registry_version"), 3)
        self.assertEqual(field(stamps, "query_set_version"), 2)
        self.assertEqual(field(stamps, "ruleset_version"), 5)
        self.assertEqual(field(stamps, "detector_version"), 7)
        for name in ("named", "named_early", "cited"):
            self.assertEqual(field(field(field(result, "rates"), name), "n"), 4)

    def test_consistent_round_state_recompute_agrees(self):
        """Plan Section 1.3 S7 family, contract C4, consistent round state limb. Oracle: contract C4, the report reads one consistent round state, and plan Section 5.2, RoundMetrics stands recomputed per report from AnswerMetrics computed in the same invocation, never from a stored RoundMetrics, so two computations over the same inputs in one invocation agree on every figure."""
        answers = distinct_answers(6, named=True)
        first = metrics.round_metrics(answers, "sampled")
        second = metrics.round_metrics(answers, "sampled")
        self.assertEqual(field(first, "rates"), field(second, "rates"))
        self.assertEqual(field(first, "effective_n"), field(second, "effective_n"))

    def test_report_reflects_only_imports_completed_before_invocation(self):
        """Plan Section 1.3 S7 family, contract C4, consistent round state limb. Oracle: contract C4, a report reflects every import that completed before the report invocation and no import that did not complete, the fold reading as of one stated snapshot point. The reproduction fixture round at fold point 6 holds four answers; the same entries read at fold point 5 hold three."""
        with open(os.path.join(FIXTURES, "w4-reproduction-fixture.json"), "r", encoding="utf-8") as handle:
            entries = json.load(handle)["journal_entries"]
        at_six = metrics.round_metrics_from_journal(entries, fold_point=6, detector_version=1)
        at_five = metrics.round_metrics_from_journal(entries, fold_point=5, detector_version=1)
        self.assertEqual(field(at_six, "imported_count"), 4)
        self.assertEqual(field(at_five, "imported_count"), 3)


class TestNoAgeSlotK17(unittest.TestCase):
    """The K-17 shape tests call the service operations, in the
    seeding form test_s05_import.py and test_s09_reporting.py
    use: an installed home, the product Acme Ledger with its
    one query, two named rounds, and one imported answer in
    each round, the answer file w4-repro-a1.txt in kind
    real_sample."""

    AUDIT_DATE = "2026-11-13"

    def seeded_home(self):
        from citeline import install as install_module
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        location, home = root / "install", root / "home"
        install_module.install(location=str(location), home=str(home))
        service.add_product(
            home=str(home), name="Acme Ledger",
            canonical_line="Acme Ledger helps teams track citations.",
            domain="acme.example", audit_date=self.AUDIT_DATE)
        service.set_query_set(
            home=str(home), product="Acme Ledger",
            query_set=["What is Acme Ledger?"],
            audit_date=self.AUDIT_DATE)
        for label in ("round-a", "round-b"):
            service.name_round(
                home=str(home), product="Acme Ledger", round_label=label,
                importer_declaration="all captured",
                supplier_relation="independent party",
                audit_date=self.AUDIT_DATE)
            service.probe_import(
                home=str(home),
                answer_file=os.path.join(FIXTURES, "w4-repro-a1.txt"),
                product="Acme Ledger", round=label,
                engine_label="Engine A", query="What is Acme Ledger?",
                kind="real_sample", captured_on="2026-11-07",
                capture_method="manual copy", audit_date=self.AUDIT_DATE)
        return home

    def test_round_metrics_shape_carries_no_age_field(self):
        """Plan Section 1.3 S7 entry, K-17 limb. Oracle: plan Section 1.3 S7 entry and Section 1.4 Part B carried account for K-17, no age field, no age statement, and no placeholder for one stands in any RoundMetrics shape, report object, or matrix row in this slice, and the absence of any age slot stands as a conformance point. This test asserts the absence over the field names of the report the service probe report operation returns."""
        home = self.seeded_home()
        result = service.probe_report(
            home=str(home), product="Acme Ledger", round="round-a",
            form="advanced", audit_date=self.AUDIT_DATE)
        for name in field_names(result):
            self.assertNotIn("age", name)

    def test_probe_trend_shape_carries_no_age_field(self):
        """Plan Section 1.3 S7 entry, K-17 limb. Oracle: the K-17 absence as stated at the S7 entry, asserted here over the ProbeTrend field names of plan Section 5.1, on the trend the service probe trend operation returns."""
        home = self.seeded_home()
        trend = service.probe_trend(
            home=str(home), product="Acme Ledger", round_a="round-a",
            round_b="round-b", form="advanced",
            audit_date=self.AUDIT_DATE)
        for name in field_names(trend):
            self.assertNotIn("age", name)


class TestReproductionFixtureFamily(unittest.TestCase):
    """The reproduction fixture family, plan Section 1.3 S7 entry.

    The fixture stands as plan Section 1.6 states it: a stated
    round of answer_imported entries held as journal entries,
    authored for this proof and recorded from no run, with the
    hand computed AnswerMetrics and the hand computed
    RoundMetrics through them as its expectation source, and
    its version binding the detector version the report
    states. The fixture of record is writer 4's fixture,
    design/tests/fixtures/w4-reproduction-fixture.json, with
    its catalogue entry at design/tests/catalogue-w4.md; these
    tests read its journal_entries list and its entry_kind
    field names in the form the S5 tests already use, with
    the round kind read as real_sample. Hand computed
    expectation for that round: four answers; named true,
    false, true, false; named early true, false, false,
    false; cited true, false, false, false; clusters 4;
    effective n 4; named rate 0.5 with Wilson 0.150036 to
    0.849964 at effective n 4, stated at places 4 as 0.1500
    to 0.8500, tier count only; cited rate gross 0.25; per
    query named count 2 under the one query "What is Acme
    Ledger?"; citing answer count 1; citation instance
    count 1.
    """

    def load_entries(self):
        with open(os.path.join(FIXTURES, "w4-reproduction-fixture.json"), "r", encoding="utf-8") as handle:
            return json.load(handle)["journal_entries"]

    def test_answer_metrics_recomputed_from_journal_alone(self):
        """Plan Section 1.3 S7 family, the reproduction fixture family, AnswerMetrics limb; plan Section 5.2 AnswerMetrics recomputation. Oracle: plan Section 5.2, a stated round of answer_imported entries, with the registry entries folded to the fold point the fixture names, folded and recomputed, must yield the hand computed AnswerMetrics the catalogue entry states."""
        entries = self.load_entries()
        results = metrics.answer_metrics_from_journal(entries, fold_point=6, detector_version=1)
        self.assertEqual(len(results), 4)
        self.assertEqual([field(r, "named") for r in results], [True, False, True, False])
        self.assertEqual([field(r, "cited") for r in results], [True, False, False, False])
        self.assertEqual([field(r, "named_early") for r in results], [True, False, False, False])

    def test_round_metrics_through_answer_metrics_same_invocation(self):
        """Plan Section 1.3 S7 family, the reproduction fixture family, RoundMetrics limb; plan Section 5.2 RoundMetrics recomputation. Oracle: plan Section 5.2, the RoundMetrics a report prints must equal the values recomputed in that invocation from the journal alone, through AnswerMetrics computed in the same invocation, against the hand computed expectation the catalogue entry states."""
        entries = self.load_entries()
        result = metrics.round_metrics_from_journal(entries, fold_point=6, detector_version=1)
        self.assertEqual(field(result, "imported_count"), 4)
        self.assertEqual(field(result, "cluster_count"), 4)
        self.assertEqual(field(result, "effective_n"), 4)
        named = field(field(result, "rates"), "named")
        self.assertAlmostEqual(field(named, "rate"), 0.5, places=6)
        self.assertAlmostEqual(field(named, "wilson_low"), 0.1500, places=4)
        self.assertAlmostEqual(field(named, "wilson_high"), 0.8500, places=4)
        self.assertEqual(field(named, "tier"), "count only")
        self.assertAlmostEqual(field(result, "cited_rate_gross"), 0.25, places=6)
        per_query = field(result, "per_query")
        self.assertEqual(field(per_query["What is Acme Ledger?"], "named_count"), 2)
        self.assertEqual(field(result, "citing_answer_count"), 1)
        self.assertEqual(field(result, "citation_instance_count"), 1)


class TestTimingBoundAtStatedScale(unittest.TestCase):
    def test_metrics_and_trend_within_bound_at_stated_scale(self):
        """Plan Section 1.5 timing bounds, S7 row. Oracle: plan Section 1.5, metrics and trend over two rounds, 5 seconds, conditional on the test scale stated on the record at scales-w5.md before the bound is applied. The scale stated there: two rounds of 20 answers each, every answer in its own cluster, with comparable composition so the trend runs its full delta path."""
        start = time.perf_counter()
        first = trend_round(0.5)
        second = trend_round(0.75)
        metrics.compute_trend(first, second)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 5.0)


if __name__ == "__main__":
    unittest.main()
