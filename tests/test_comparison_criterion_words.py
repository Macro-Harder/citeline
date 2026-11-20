"""Repair test: comparison criterion words.

Oracle: brief Section 5.7, the comparison check has four
components at 0.4, 0.2, 0.2, and 0.2, the last being at
least 3 distinct criterion words from the stated list
of 10 near the comparison; a page satisfying every
component earns 1.0 and prints CMP_OK.
"""

import unittest

from citeline import checks

AUDIT_DATE = "2026-08-20"


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


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


class TestR19004ComparisonCriterionWords(unittest.TestCase):
    def test_all_components_earn_full_credit(self):
        sentences = [
            "Versus Rivalforge for planning work.",
            "Price speed cost support features setup quality "
            "limit free open.",
        ]
        running = "\n\n".join(sentences)
        page = {
            "running_text": running,
            "sentences": sentences,
            "paragraphs": [[s] for s in sentences],
            "headings": [],
            "sections": [{
                "heading_text": "Comparison", "start": 0,
                "end": len(running), "references_section": False,
            }],
            "links": [],
            "blockquotes": [],
            "lists": [{"items": ["one", "two", "three"], "start": 5}],
            "tables": [],
            "date_strings": [],
            "canonical_link_element": None,
            "meta_robots": None,
            "word_count": sum(len(s.split()) for s in sentences),
            "extracted_text_length": len(running),
            "extraction_notes": [],
        }
        results = checks.run_checks(page, make_facts(), audit_date=AUDIT_DATE)
        by_id = {field(r, "check_id"): r for r in results}
        r = by_id["comparison"]
        self.assertEqual(field(r, "earned"), 1.0)
        self.assertEqual(field(r, "reason_code"), "CMP_OK")


if __name__ == "__main__":
    unittest.main()
