"""Step 16 supplementary fix G2 tests: surface words and figures.

Written test first against the round 2 disposition at
design/steps/step-16-record.md, defects E-02, E-07, and E-10,
and the governing texts those entries name: brief Section
5.8 item 19 guard G1 with pass condition P26 for the importer
declaration in its three values in words and the unverifiable
position as a statement, and the IM7-BRK-3 landing in brief
Section 5.8 for the secondary figure on the not applicable
as zero basis, which is not stored, recomputes at rendering,
and travels wherever the headline score travels, labelled in
words in the Simple form.
"""

import copy
import unittest

from citeline import reporting


BASIS_TEXT = (
    "Computed on a different basis from the headline score: "
    "the headline score is computed on the applicable checks "
    "with not applicable weight redistributed, and this "
    "figure is computed on the total weight of 100 with not "
    "applicable checks earning 0. Neither figure ranks "
    "against a score on another basis."
)

WEIGHTS = {
    "answer_first": 12, "citations": 16, "statistics": 13,
    "quotations": 11, "comparison": 10, "freshness": 8,
    "description_consistency": 8, "keyword_stuffing": 8,
    "fluff": 7, "unproven_superlatives": 7,
}


def check(check_id, earned, status=None):
    return {
        "check_id": check_id,
        "weight": WEIGHTS[check_id],
        "earned": earned,
        "status": status,
        "reason_code": "TEST",
        "evidence_class": "paper_tested",
        "evidence_spans": [],
        "detail_counts": {},
    }


def stored_results(applicable, not_applicable):
    out = []
    for check_id in WEIGHTS:
        if check_id in not_applicable:
            out.append(check(check_id, not_applicable[check_id],
                             status="not_applicable"))
        else:
            out.append(check(check_id, applicable[check_id]))
    return out


# Stored session runs 9, 25, and 29 basis: the applicable
# earned times weight sum is 26.45, with at least one check
# not applicable, so the figure on the total weight of 100
# is 26.5 at one decimal place.
RUN_25_APPLICABLE = {
    "answer_first": 0.6, "citations": 0.0, "statistics": 0.25,
    "quotations": 0.0, "comparison": 0.0, "freshness": 0.0,
    "keyword_stuffing": 0.25, "fluff": 1.0,
    "unproven_superlatives": 1.0,
}
RUN_25_NA = {"description_consistency": 1.0}

# Stored session run 11 basis: the applicable sum is 50.722,
# so the figure is 50.7.
RUN_11_APPLICABLE = {
    "answer_first": 0.6, "citations": 0.267, "statistics": 0.75,
    "quotations": 0.5, "freshness": 1.0,
    "keyword_stuffing": 0.25, "fluff": 1.0,
    "unproven_superlatives": 1.0,
}
RUN_11_NA = {"comparison": 0.6, "description_consistency": 0.3}


def pre_cure_audit_record(applicable, not_applicable, value,
                          band="poor", cap_status=False):
    """An audit record as stored before the D-24 cure: its
    ScoreObject carries no secondary_figure field at all."""
    score = {
        "value": value,
        "band": band,
        "cap_status": cap_status,
        "applicable_basis": {
            "applicable_checks": [
                name for name in WEIGHTS
                if name not in not_applicable],
            "applicable_weight": sum(
                WEIGHTS[name] for name in WEIGHTS
                if name not in not_applicable),
        },
        "claim_type": "signal_presence_only",
        "validated_predictor": False,
    }
    return {
        "run_id": "run-25",
        "snapshot_id": "snap-1",
        "score": score,
        "checks": stored_results(applicable, not_applicable),
    }


def frame_record(declaration, extra_frame=None):
    frame = {
        "query_set_version": 1,
        "engine_label_set": ["engine-a"],
        "capture_methods_asserted": ["manual copy"],
        "imported_count": 3,
        "importer_declaration": declaration,
        "declaration_unverifiable": True,
    }
    if extra_frame:
        frame.update(extra_frame)
    return {"sampling_frame": frame, "empty_answer_count": 0}


class TestE02DeclarationInWords(unittest.TestCase):
    def test_all_captured_prints_in_g1_words(self):
        text = reporting.render(
            frame_record("all_captured"), form="simple")
        self.assertIn("all captured answers imported", text)
        self.assertNotIn("all_captured", text)
        self.assertNotIn("importer_declaration:", text)

    def test_unverifiable_position_prints_as_a_statement(self):
        text = reporting.render(
            frame_record("all_captured"), form="simple")
        self.assertIn(
            "The declaration is unverifiable by the tool.", text)
        self.assertNotIn("declaration_unverifiable", text)
        self.assertNotIn("declaration_unverifiable: true", text)

    def test_declaration_is_marked_as_asserted(self):
        text = reporting.render(
            frame_record("all_captured"), form="simple")
        self.assertIn("as asserted", text)

    def test_stated_subset_carries_its_selection_rule_text(self):
        record = frame_record(
            "stated_subset",
            {"selection_rule": "every third answer, as filed"})
        text = reporting.render(record, form="simple")
        self.assertIn("a stated subset imported", text)
        self.assertIn("every third answer, as filed", text)
        self.assertNotIn("stated_subset", text)

    def test_selection_rule_unknown_prints_in_g1_words(self):
        text = reporting.render(
            frame_record("selection_rule_unknown"), form="simple")
        self.assertIn("selection rule unknown", text)
        self.assertNotIn("selection_rule_unknown", text)

    def test_trend_embedded_frames_print_in_g1_words(self):
        record = {
            "first_round": frame_record("all_captured"),
            "second_round": frame_record("stated_subset"),
        }
        text = reporting.render(record, form="simple")
        self.assertIn("all captured answers imported", text)
        self.assertIn("a stated subset imported", text)
        self.assertNotIn("all_captured", text)
        self.assertNotIn("stated_subset", text)

    def test_advanced_form_keeps_the_code_form(self):
        body = reporting.render(
            frame_record("all_captured"), form="advanced")
        frame = body["sampling_frame"]
        self.assertEqual(frame["importer_declaration"],
                         "all_captured")
        self.assertIs(frame["declaration_unverifiable"], True)


class TestE07SecondaryFigureAtRendering(unittest.TestCase):
    def test_pre_cure_record_renders_the_figure_advanced(self):
        record = pre_cure_audit_record(
            RUN_25_APPLICABLE, RUN_25_NA, 28.7)
        body = reporting.render(record, form="advanced")
        figure = body["score"]["secondary_figure"]
        self.assertEqual(figure["value"], 26.5)
        self.assertEqual(figure["total_weight"], 100)
        self.assertEqual(figure["basis"], BASIS_TEXT)

    def test_pre_cure_record_renders_the_figure_agentic(self):
        record = pre_cure_audit_record(
            RUN_11_APPLICABLE, RUN_11_NA, 61.9, band="developing")
        body = reporting.render(record, form="agentic")
        figure = body["report"]["score"]["secondary_figure"]
        self.assertEqual(figure["value"], 50.7)
        self.assertEqual(figure["total_weight"], 100)

    def test_recompute_renders_and_does_not_write_back(self):
        record = pre_cure_audit_record(
            RUN_25_APPLICABLE, RUN_25_NA, 28.7)
        before = copy.deepcopy(record)
        reporting.render(record, form="advanced")
        reporting.render(record, form="simple")
        self.assertEqual(record, before)
        self.assertNotIn("secondary_figure", record["score"])

    def test_recomputed_figure_carries_the_evidence_cap(self):
        applicable = {
            name: 1.0 for name in WEIGHTS
            if name != "description_consistency"}
        record = pre_cure_audit_record(
            applicable, {"description_consistency": 1.0}, 39.0,
            band="thin", cap_status=True)
        body = reporting.render(record, form="advanced")
        self.assertEqual(
            body["score"]["secondary_figure"]["value"], 39.0)

    def test_fully_applicable_record_renders_no_figure(self):
        applicable = {name: 1.0 for name in WEIGHTS}
        record = pre_cure_audit_record(applicable, {}, 100.0,
                                       band="strong")
        record["score"]["secondary_figure"] = None
        body = reporting.render(record, form="advanced")
        self.assertIsNone(body["score"]["secondary_figure"])

    def test_all_not_applicable_record_renders_no_figure(self):
        record = pre_cure_audit_record(
            {}, {name: 0.0 for name in WEIGHTS}, None, band=None)
        record["score"]["secondary_figure"] = None
        body = reporting.render(record, form="advanced")
        self.assertIsNone(body["score"]["secondary_figure"])

    def test_simple_audit_carries_the_recomputed_figure(self):
        record = pre_cure_audit_record(
            RUN_25_APPLICABLE, RUN_25_NA, 28.7)
        text = reporting.render(record, form="simple")
        self.assertIn(
            "The score on the not applicable as zero basis "
            "is 26.5.", text)
        self.assertIn("not a second score", text)
        self.assertIn("total weight of 100", text)

    def test_simple_audit_carries_a_stored_figure(self):
        record = pre_cure_audit_record(
            RUN_11_APPLICABLE, RUN_11_NA, 65.1, band="developing")
        record["score"]["secondary_figure"] = {
            "value": 59.9, "total_weight": 100,
            "basis": BASIS_TEXT}
        text = reporting.render(record, form="simple")
        self.assertIn(
            "The score on the not applicable as zero basis "
            "is 59.9.", text)


class TestE10RatePrecisionAndNoneValues(unittest.TestCase):
    def test_cited_rate_gross_at_four_places_standalone(self):
        record = {"cited_rate_gross": 1 / 3,
                  "cited_rate_net": 1 / 3}
        text = reporting.render(record, form="simple")
        self.assertIn("cited_rate_gross: 0.3333", text)
        self.assertIn("cited_rate_net: 0.3333", text)
        self.assertNotIn("0.3333333333333333", text)

    def test_cited_rate_gross_at_four_places_in_trend_blocks(self):
        record = {
            "first_round": {"cited_rate_gross": 1 / 3},
            "second_round": {"cited_rate_gross": 2 / 3},
        }
        text = reporting.render(record, form="simple")
        self.assertIn("cited_rate_gross: 0.3333", text)
        self.assertIn("cited_rate_gross: 0.6667", text)
        self.assertNotIn("0.3333333333333333", text)
        self.assertNotIn("0.6666666666666666", text)

    def test_none_values_do_not_print_as_field_values(self):
        record = {
            "delta": None,
            "series_break": None,
            "self_citation_share": None,
            "no_name_share": None,
            "named_count": 2,
            "sampling_frame": {
                "importer_declaration": "all_captured",
                "declaration_unverifiable": True,
            },
        }
        text = reporting.render(record, form="simple")
        self.assertNotIn("delta: none", text)
        self.assertNotIn("series_break: none", text)
        self.assertNotIn("self_citation_share: none", text)
        self.assertNotIn("no_name_share: none", text)
        self.assertIn("named_count: 2", text)

    def test_none_values_do_not_print_inside_round_blocks(self):
        record = {
            "first_round": {
                "delta": None, "self_citation_share": None,
                "cited_rate_gross": 0.5},
            "second_round": {
                "delta": None, "series_break": None,
                "cited_rate_gross": 0.25},
        }
        text = reporting.render(record, form="simple")
        self.assertNotIn(": none", text)
        self.assertIn("cited_rate_gross: 0.5", text)


if __name__ == "__main__":
    unittest.main()
