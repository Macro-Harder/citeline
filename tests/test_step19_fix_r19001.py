"""Repair test: unproven superlatives.

Oracle: brief Section 5.7, earned is 1.0 minus 0.34 per
unproven hit, floored at 0, each unproven span reported
as evidence with reason SUP_UNPROVEN; a hit counts as
proven only where its sentence or a neighbouring
sentence contains a citation, a statistic, or an
attributed quote.
"""

import unittest

from citeline import checks

AUDIT_DATE = "2026-08-20"


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def make_page(paragraphs=None, links=(), sections=None, lists=()):
    paras = [list(p) for p in (paragraphs or [])]
    flat = [s for p in paras for s in p]
    running_text = "\n\n".join(" ".join(p) for p in paras)
    if sections is None:
        sections = [{
            "heading_text": None, "start": 0,
            "end": len(running_text), "references_section": False,
        }]
    return {
        "running_text": running_text,
        "sentences": flat,
        "paragraphs": [" ".join(p) for p in paras],
        "headings": [],
        "sections": sections,
        "links": list(links),
        "blockquotes": [],
        "lists": list(lists),
        "tables": [],
        "date_strings": [],
        "canonical_link_element": None,
        "meta_robots": None,
        "word_count": sum(len(s.split()) for s in flat),
        "extracted_text_length": len(running_text),
        "extraction_notes": [],
    }


def make_facts():
    return {
        "product_name": "Macroforge",
        "aliases": ["Macroforge"],
        "category_terms": ["workbench"],
        "canonical_line": "Macroforge is a campaign workbench for agent teams.",
        "is_product_page": True,
        "domain": "macroforge.example",
        "competitors": [{"name": "Rivalforge", "aliases": ["Rivalforge"]}],
    }


def run(page):
    results = checks.run_checks(page, make_facts(), audit_date=AUDIT_DATE)
    return {field(r, "check_id"): r for r in results}


class TestR19001Superlatives(unittest.TestCase):
    def test_many_unproven_hits_floor_at_zero(self):
        page = make_page(paragraphs=[[
            "Widget is the best and fastest and ultimate gadget.",
            "It is leading and top and unmatched in every way possible today.",
        ]])
        r = run(page)["unproven_superlatives"]
        self.assertEqual(field(r, "earned"), 0)
        self.assertEqual(field(r, "reason_code"), "SUP_UNPROVEN")
        self.assertTrue(field(r, "evidence_spans"))

    def test_one_unproven_hit_deducts_a_third(self):
        page = make_page(paragraphs=[[
            "Widget is the best gadget for planning teams today.",
        ]])
        r = run(page)["unproven_superlatives"]
        self.assertEqual(field(r, "earned"), 0.66)
        self.assertEqual(field(r, "reason_code"), "SUP_UNPROVEN")
        self.assertEqual(len(field(r, "evidence_spans")), 1)

    def test_hit_beside_a_citation_is_proven(self):
        sentence = ("The best guide stands at "
                    "https://example.org/a for readers.")
        target = "https://example.org/a"
        page = make_page(
            paragraphs=[[sentence]],
            links=[{"text": target, "target": target,
                    "start": sentence.index(target),
                    "end": sentence.index(target) + len(target)}],
        )
        r = run(page)["unproven_superlatives"]
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "SUP_OK")


if __name__ == "__main__":
    unittest.main()
