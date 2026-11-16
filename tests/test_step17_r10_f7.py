"""Step 17 round 10 fix seat F7 tests: service, watch, seams.

Entry S17-R10-001: the service seam
_import_front_matter_limits in service.py measures no
key of the top level object of a JSON front matter
block, in its primary form or in its fallback form
alike, so a top level key standing past the value
length limit in force for the home passes the seam and
imports whole through service.probe_import. The pins
below stand on a home whose config states
front_matter_value_length_per_key = 100 as the limit in
force, in the worked forms of the registry paper of
round 10, with the brief value route forms at 4,097
and 5,000 standing as controls.
Oracle: the round 10 findings register entry
S17-R10-001 and the round 10 disposition, ruling (b)
and Section 3 seat F7.

Copyright: J.P. Picard aka Macro-Harder.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from citeline import errors, install as install_module
from citeline import journal, probe_import, service

AUDIT_DATE = "2026-11-14"
PRODUCT = "Acme Ledger"
Q1 = "What is Acme Ledger?"
Q2 = "Best ferry tracker?"
ROUND = "round-1"


def make_home(case):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, home


def seed(case, home):
    service.add_product(
        home=str(home), name=PRODUCT,
        canonical_line="Acme Ledger helps teams track citations.",
        domain="acme.example", audit_date=AUDIT_DATE)
    service.set_query_set(
        home=str(home), product=PRODUCT, query_set=[Q1, Q2],
        audit_date=AUDIT_DATE)
    service.name_round(
        home=str(home), product=PRODUCT, round_label=ROUND,
        importer_declaration="all captured",
        supplier_relation="independent party", audit_date=AUDIT_DATE)
    return home


def temp_file(case, content, name="file.txt"):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    path = root / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


def do_import(home, answer_file, **overrides):
    kwargs = {
        "home": str(home), "answer_file": str(answer_file),
        "product": PRODUCT, "round": ROUND, "engine_label": "Engine A",
        "query": Q1, "kind": "real_sample",
        "captured_on": "2026-11-10", "capture_method": "manual copy",
        "audit_date": AUDIT_DATE,
    }
    kwargs.update(overrides)
    return service.probe_import(**kwargs)


def token_of(exc):
    return getattr(exc, "token", None) or getattr(
        exc, "error_value", None)


class LimitedBase(unittest.TestCase):
    """A seeded home carrying the limit in force of 100."""

    def setUp(self):
        self.root, self.home = make_home(self)
        seed(self, self.home)
        journal.write_config(
            str(self.home),
            "front_matter_value_length_per_key = 100\n")

    def answer_with_block(self, block):
        return temp_file(
            self, "---\n" + block + "\n---\n"
            "Acme Ledger is a ledger tool.\n", "answer.txt")

    def seam(self, block):
        return service._import_front_matter_limits(
            str(self.home), str(self.answer_with_block(block)))

    def seam_refuses(self, block):
        with self.assertRaises(errors.CitelineError) as caught:
            self.seam(block)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")


# ----------------------------------------------------------------
# S17-R10-001, the primary form: a top level key past the
# limit in force refuses at the seam.
# ----------------------------------------------------------------

class TestTopLevelKeyAtTheSeamPrimary(LimitedBase):

    def test_top_level_key_of_200_refuses_at_the_seam(self):
        self.seam_refuses('{"%s": "v"}' % ("k" * 200))

    def test_top_level_key_of_5000_refuses_at_the_seam(self):
        self.seam_refuses('{"%s": "v"}' % ("k" * 5000))

    def test_top_level_key_past_the_limit_beside_a_container(self):
        self.seam_refuses(
            '{"%s": "v", "note": ["x"]}' % ("k" * 200))


# ----------------------------------------------------------------
# S17-R10-001, the fallback form: with the import container
# measure removed for the run, so the seam stands on its
# fallback measure, the top level key stands measured all
# the same.
# ----------------------------------------------------------------

class TestTopLevelKeyAtTheSeamFallback(LimitedBase):

    def test_top_level_key_of_200_refuses_on_the_fallback(self):
        with mock.patch.object(
                probe_import, "_container_value_measure", None):
            self.seam_refuses('{"%s": "v"}' % ("k" * 200))

    def test_top_level_key_of_5000_refuses_on_the_fallback(self):
        with mock.patch.object(
                probe_import, "_container_value_measure", None):
            self.seam_refuses('{"%s": "v"}' % ("k" * 5000))

    def test_container_key_still_refuses_on_the_fallback(self):
        with mock.patch.object(
                probe_import, "_container_value_measure", None):
            self.seam_refuses('{"note": {"%s": "v"}}' % ("k" * 200))


# ----------------------------------------------------------------
# S17-R10-001, end to end: the block holding the top level
# key past the limit in force imports no whole through
# the service route.
# ----------------------------------------------------------------

class TestTopLevelKeyEndToEnd(LimitedBase):

    def test_top_level_key_of_200_refuses_at_the_route(self):
        answer = self.answer_with_block('{"%s": "v"}' % ("k" * 200))
        with self.assertRaises(errors.CitelineError) as caught:
            do_import(self.home, answer)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_top_level_key_of_200_refuses_at_the_route_fallback(self):
        answer = self.answer_with_block('{"%s": "v"}' % ("k" * 200))
        with mock.patch.object(
                probe_import, "_container_value_measure", None):
            with self.assertRaises(errors.CitelineError) as caught:
                service._import_front_matter_limits(
                    str(self.home), str(answer))
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")


# ----------------------------------------------------------------
# Controls: keys inside the limit in force pass the seam
# and import whole, the neighbouring value and container
# key forms refuse as they stood, and the brief value
# route forms at 4,097 and 5,000 still refuse at the
# route while the form at 4,096 imports.
# ----------------------------------------------------------------

class TestTopLevelKeyControls(LimitedBase):

    def test_top_level_key_of_90_passes_the_seam(self):
        self.assertIsNone(self.seam('{"%s": "v"}' % ("k" * 90)))

    def test_top_level_key_at_the_limit_passes_the_seam(self):
        self.assertIsNone(self.seam('{"%s": "v"}' % ("k" * 100)))

    def test_top_level_key_of_90_imports_whole_at_the_route(self):
        answer = self.answer_with_block('{"%s": "v"}' % ("k" * 90))
        self.assertIsNotNone(do_import(self.home, answer))

    def test_string_value_of_200_still_refuses_at_the_seam(self):
        self.seam_refuses('{"note": "%s"}' % ("v" * 200))

    def test_container_key_of_200_still_refuses_at_the_seam(self):
        self.seam_refuses('{"note": {"%s": "v"}}' % ("k" * 200))

    def test_container_key_and_value_summing_past_still_refuses(self):
        self.seam_refuses(
            '{"note": {"%s": "%s"}}' % ("k" * 90, "v" * 20))

    def test_brief_value_forms_still_refuse_at_the_route(self):
        for size in (4097, 5000):
            with self.subTest(size=size):
                root, home = make_home(self)
                seed(self, home)
                answer = temp_file(
                    self, "---\n" + '{"%s": "v"}' % ("k" * size)
                    + "\n---\nAcme Ledger is a ledger tool.\n",
                    "answer.txt")
                with self.assertRaises(Exception) as caught:
                    do_import(home, answer)
                self.assertEqual(
                    token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_brief_value_form_at_4096_still_imports_at_the_route(self):
        root, home = make_home(self)
        seed(self, home)
        answer = temp_file(
            self, "---\n" + '{"%s": "v"}' % ("k" * 4096)
            + "\n---\nAcme Ledger is a ledger tool.\n", "answer.txt")
        self.assertIsNotNone(do_import(home, answer))


if __name__ == "__main__":
    unittest.main()
