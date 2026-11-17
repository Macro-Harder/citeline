"""Step 19 repair test for R19-005, fluff filler boosters.

Oracle: brief Section 5.7, the otherwise 1.0 fluff
outcome loses 0.3 where the stated filler boosters
appear at least 3 times with no evidence in their
sentences, with reason FLF_BOOSTERS.
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


class TestR19005FluffBoosters(unittest.TestCase):
    def test_booster_dense_short_page_loses_the_deduction(self):
        sentences = [
            "Revolutionary game changing tools feel seamless.",
            "Cutting edge world class design stays seamless.",
            "A robust solution feels revolutionary and seamless.",
        ]
        running = "\n\n".join(sentences)
        page = {
            "running_text": running,
            "sentences": sentences,
            "paragraphs": [sentences],
            "headings": [],
            "sections": [{
                "heading_text": None, "start": 0,
                "end": len(running), "references_section": False,
            }],
            "links": [],
            "blockquotes": [],
            "lists": [],
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
        r = by_id["fluff"]
        self.assertEqual(field(r, "earned"), 0.7)
        self.assertEqual(field(r, "reason_code"), "FLF_BOOSTERS")


if __name__ == "__main__":
    unittest.main()
