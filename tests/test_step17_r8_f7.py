"""Step 17 round 8 fix seat F7 tests: service, watch, seams.

Pins the register entry charged to F7 in fix round 8,
S17-R8-024, and the seam positions the F2, F4, and F6
papers of this round state for this seat. Every defect
test was written before its cure and run failing for
the register stated reason, except the controls named
as controls.
Oracle: the round 8 findings register and disposition.

Copyright: J.P. Picard aka Macro-Harder.
"""

import json
import tempfile
import unittest
from pathlib import Path

from citeline import errors, install as install_module
from citeline import service, watch

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-14"
PRODUCT = "Acme Ledger"
Q1 = "What is Acme Ledger?"
Q2 = "Best ferry tracker?"
ROUND = "round-1"
ROUND0 = "round-0"


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


def temp_file(case, content, name="file.txt"):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    path = root / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


class SeededBase(unittest.TestCase):
    def setUp(self):
        self.root, self.home = make_home(self)
        seed(self, self.home)

    def import_block(self, block):
        answer = temp_file(
            self, "---\n" + block + "\n---\n"
            "Acme Ledger is a ledger tool.\n", "answer.txt")
        return do_import(self.home, answer)


# ----------------------------------------------------------------
# S17-R8-024: a plan level second_round field, singular, on
# an estate plan stands warned in the open, never
# disregarded in silence.
# ----------------------------------------------------------------

class Test024EstateSecondRoundSingular(SeededBase):

    def two_round_home(self):
        root, home = make_home(self)
        service.add_product(
            home=str(home), name=PRODUCT,
            canonical_line="Acme Ledger helps teams track citations.",
            domain="acme.example", audit_date=AUDIT_DATE)
        service.set_query_set(
            home=str(home), product=PRODUCT, query_set=[Q1, Q2],
            audit_date=AUDIT_DATE)
        for label in (ROUND0, ROUND):
            service.name_round(
                home=str(home), product=PRODUCT, round_label=label,
                importer_declaration="all captured",
                supplier_relation="independent party",
                audit_date=AUDIT_DATE)
            answer = temp_file(
                self, "Acme Ledger is a ledger tool.\n", "answer.txt")
            do_import(home, answer, round=label)
        return home

    def run_estate_plan(self, home, **plan_fields):
        plan = {"home": str(home), "scope": "estate",
                "audit_date": AUDIT_DATE}
        plan.update(plan_fields)
        plan_file = temp_file(
            self, json.dumps(plan), "plan.json")
        return watch.run_watch(plan_file=str(plan_file))

    def test_unit_warnings_name_the_singular_field_and_label(self):
        plan = {"home": str(self.home), "scope": "estate",
                "second_round": ROUND0}
        warnings = watch._plan_warnings(plan, [])
        self.assertTrue(
            any("second_round" in warning and ROUND0 in warning
                for warning in warnings),
            "no warning names the singular field: %r" % (warnings,))

    def test_estate_round_runs_whole_with_the_warning(self):
        home = self.two_round_home()
        result = self.run_estate_plan(home, second_round=ROUND0)
        warnings = result.get("plan_warnings") or []
        self.assertTrue(
            any("second_round" in warning and ROUND0 in warning
                for warning in warnings),
            "no warning names the singular field: %r" % (warnings,))
        self.assertTrue(result.get("entries"))

    def test_estate_singular_beside_plural_both_stand_warned(self):
        home = self.two_round_home()
        result = self.run_estate_plan(
            home, second_round=ROUND0,
            second_rounds={PRODUCT: ROUND0})
        warnings = result.get("plan_warnings") or []
        self.assertTrue(
            any("second_round:" in warning or
                "second_round field" in warning
                for warning in warnings),
            "no warning names the singular field: %r" % (warnings,))
        self.assertTrue(
            any("second_rounds" in warning for warning in warnings))

    def test_estate_plan_without_the_field_warns_nothing_control(self):
        home = self.two_round_home()
        result = self.run_estate_plan(home)
        warnings = result.get("plan_warnings") or []
        self.assertFalse(
            any("second_round" in warning for warning in warnings))

    def test_picked_plan_unit_warns_nothing_on_the_field_control(self):
        plan = {"home": str(self.home), "scope": "picked",
                "second_round": ROUND0}
        warnings = watch._plan_warnings(plan, [])
        self.assertFalse(
            any("second_round" in warning for warning in warnings))


# ----------------------------------------------------------------
# F2 seam at entry S17-R8-028: the service reading stands
# on the same import container measure the page side now
# states, with no rendered fallback reopening the split
# at 4,094 to 4,096 characters inside a list, and the
# block size limb standing on the same file form at page
# and service.
# ----------------------------------------------------------------

class TestF2ContainerSeamServiceReading(SeededBase):

    def test_container_strings_at_the_limit_accepted(self):
        for size in (4094, 4095, 4096):
            with self.subTest(size=size):
                root, home = make_home(self)
                seed(self, home)
                answer = temp_file(
                    self, "---\n" + '{"note": ["%s"]}' % ("v" * size)
                    + "\n---\nAcme Ledger is a ledger tool.\n",
                    "answer.txt")
                self.assertIsNotNone(do_import(home, answer))

    def test_container_string_past_the_limit_refuses_control(self):
        with self.assertRaises(errors.CitelineError) as caught:
            self.import_block('{"note": ["%s"]}' % ("v" * 5000))
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_no_rendered_fallback_at_the_limit_sizes(self):
        import inspect
        for size in (4094, 4096):
            with self.subTest(size=size):
                value = ["v" * size]
                self.assertEqual(
                    service._service_container_value_measure(value),
                    size)
                self.assertGreater(
                    len(json.dumps(value, ensure_ascii=False)), 4096)
        source = inspect.getsource(
            service._import_front_matter_limits)
        self.assertNotIn("len(render_written(value))", source)
        self.assertNotIn("len(json.dumps(", source)
        self.assertIn("_service_container_value_measure", source)

    def test_block_size_measured_as_the_block_stands_in_the_file(self):
        from citeline import journal
        journal.write_config(
            str(self.home), "front_matter_block_size = 1\n")
        block = "#c\r\n" * 300
        answer = temp_file(
            self, "---\r\n" + block + "---\r\n"
            "Acme Ledger is a ledger tool.\r\n", "answer.txt")
        with self.assertRaises(errors.CitelineError) as caught:
            do_import(self.home, answer)
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")


# ----------------------------------------------------------------
# F4 seam: the service container measure stands on the
# import measure at the key position, a string standing
# as a key inside a container measured by its length in
# characters, after the S17-R8-016 cure.
# ----------------------------------------------------------------

class TestF4ContainerKeySeamServiceReading(SeededBase):

    def test_long_key_inside_a_container_refuses(self):
        with self.assertRaises(errors.CitelineError) as caught:
            self.import_block(
                '{"note": {"%s": "x"}}' % ("k" * 5000))
        self.assertEqual(
            token_of(caught.exception), "LIMIT_EXCEEDED")

    def test_key_at_the_limit_inside_a_container_accepted_control(self):
        self.assertIsNotNone(
            self.import_block('{"note": {"%s": "x"}}' % ("k" * 4000)))

    def test_no_rendered_fallback_at_the_key_position(self):
        value = {"k" * 4090: "x"}
        self.assertEqual(
            service._service_container_value_measure(value), 4091)
        self.assertGreater(
            len(json.dumps(value, ensure_ascii=False)), 4096)
        nested = [{"k" * 5000: "x"}]
        self.assertEqual(
            service._service_container_value_measure(nested), 5001)


# ----------------------------------------------------------------
# F6 seams: no service or watch reading of its own stands
# apart from the cured guide and reporting forms.
# ----------------------------------------------------------------

class TestF6SeamsServiceWatchPositions(unittest.TestCase):

    def sources(self):
        import inspect
        return (inspect.getsource(service), inspect.getsource(watch))

    def test_no_scope_reading_of_its_own(self):
        for source in self.sources():
            self.assertNotIn("claim_type", source)

    def test_no_tokeniser_copy_of_its_own(self):
        for source in self.sources():
            self.assertNotIn("_WORD_TOKEN_PATTERN", source)
            self.assertNotIn("_word_tokens", source)
        package = Path(service.__file__).parent
        copies = [
            path.name for path in package.glob("*.py")
            if "_WORD_TOKEN_PATTERN = " in
            path.read_text(encoding="utf-8")]
        self.assertEqual(sorted(copies), ["guide.py", "reporting.py"])

    def test_no_failure_line_builder_of_its_own(self):
        for source in self.sources():
            self.assertNotIn("_failure_record_line", source)
            self.assertNotIn("_failure_value_text", source)

    def test_no_emitter_of_its_own(self):
        for source in self.sources():
            self.assertNotIn("def _emit", source)


if __name__ == "__main__":
    unittest.main()
