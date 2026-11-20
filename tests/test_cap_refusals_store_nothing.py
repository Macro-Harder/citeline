"""Repair tests.

This file pins the cap refusal items the repair item and
the repair item at the service locus. Tests were written before the fixes they pin.
Dates are call inputs in every test.
"""

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from citeline import journal, service, shell
from citeline import install as install_module

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
ANSWER = FIXTURES / "w7-answer.txt"
QUERY = "What is Example Product?"


def make_home(case, name="home"):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / ("install-" + name), root / name
    install_module.install(location=str(location), home=str(home))
    return root, home


def seed(case, home, product="p-alpha"):
    service.add_product(
        home=str(home), name=product, canonical_line=product + " line.",
        domain="example.com", audit_date=AUDIT_DATE)
    service.set_query_set(home=str(home), product=product,
                          query_set=[QUERY], audit_date=AUDIT_DATE)
    service.name_round(home=str(home), product=product,
                       round_label="round-1",
                       importer_declaration="operator",
                       supplier_relation="first party",
                       audit_date=AUDIT_DATE)
    return home


def raw_entries(home):
    path = Path(home) / "journal.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out


def count(home):
    return len(raw_entries(home))


def failures(home):
    return [e for e in raw_entries(home)
            if e.get("entry_kind") == "failure_record"]


def set_cap(home, n):
    journal.write_config(home, "journal_length = %d\n" % n)


def page_file(root, name="page.txt"):
    p = Path(root) / name
    p.write_text("# Example Product\n\np-alpha line.\n\n"
                 "Example Product does things well.\n", encoding="utf-8")
    return p


def answer_file(root, name, text):
    p = Path(root) / name
    p.write_text(text, encoding="utf-8")
    return p


def tok(exc):
    return (getattr(exc, "token", None)
            or getattr(exc, "error_value", None))


def import_kwargs(answer):
    return dict(answer_file=str(answer), product="p-alpha",
                round="round-1", engine_label="engine-a", query=QUERY,
                kind="real_sample", captured_on="2026-11-10",
                capture_method="manual copy", audit_date=AUDIT_DATE)


class TestP7A1CapRefusalsStoreNothing(unittest.TestCase):
    """The repair item and the repair item: a refusal carrying any cap token
    (LIMIT_EXCEEDED, JOURNAL_CAP_EXCEEDED, CONTROL_CAP_EXCEEDED)
    stores nothing on every route, while a non cap failure on an
    appending route keeps storing exactly one record (the settled rule)."""

    def _one_slot(self):
        root, home = make_home(self)
        seed(self, home)
        n = count(home)
        set_cap(home, n + 1)
        return root, home, n

    def test_audit_preflight_journal_cap_stores_nothing(self):
        root, home, n = self._one_slot()
        with self.assertRaises(Exception) as caught:
            service.audit(home=str(home),
                          page_file=str(page_file(root)),
                          audit_date=AUDIT_DATE)
        self.assertEqual(tok(caught.exception), "JOURNAL_CAP_EXCEEDED")
        self.assertEqual(count(home), n)
        self.assertEqual(failures(home), [])

    def test_import_preflight_journal_cap_stores_nothing(self):
        root, home, n = self._one_slot()
        with self.assertRaises(Exception) as caught:
            service.probe_import(home=str(home), **import_kwargs(ANSWER))
        self.assertEqual(tok(caught.exception), "JOURNAL_CAP_EXCEEDED")
        self.assertEqual(count(home), n)
        self.assertEqual(failures(home), [])

    def test_import_size_preflight_stores_nothing(self):
        root, home = make_home(self)
        seed(self, home)
        n = count(home)
        big = Path(root) / "big.txt"
        with open(big, "wb") as handle:
            handle.truncate(1024 * 1024 * 1024 + 8192)
        with self.assertRaises(Exception) as caught:
            service.probe_import(home=str(home), **import_kwargs(big))
        self.assertEqual(tok(caught.exception), "JOURNAL_CAP_EXCEEDED")
        self.assertEqual(count(home), n)
        self.assertEqual(failures(home), [])

    def test_control_cap_refusal_stores_nothing(self):
        root, home = make_home(self)
        seed(self, home)
        for i in range(5):
            kwargs = import_kwargs(answer_file(
                root, "ctl%d.txt" % i,
                "Control answer number %d about the product.\n" % i))
            kwargs["captured_on"] = "2026-11-0%d" % (i + 1)
            kwargs["control_designation"] = "positive"
            service.probe_import(home=str(home), **kwargs)
        n = count(home)
        kwargs = import_kwargs(answer_file(
            root, "ctl6.txt",
            "Control answer number six about the product.\n"))
        kwargs["control_designation"] = "positive"
        with self.assertRaises(Exception) as caught:
            service.probe_import(home=str(home), **kwargs)
        self.assertEqual(tok(caught.exception), "CONTROL_CAP_EXCEEDED")
        self.assertEqual(count(home), n)

    def test_watch_audit_target_cap_refusal_stores_nothing(self):
        root, home = make_home(self)
        seed(self, home)
        service.audit(home=str(home), page_file=str(page_file(root)),
                      audit_date=AUDIT_DATE)
        n = count(home)
        set_cap(home, n + 1)
        plan = {"home": str(home), "scope": "picked",
                "audit_date": AUDIT_DATE, "form": "simple",
                "targets": [{"product": "p-alpha",
                             "page_file": str(page_file(root))}],
                "output": str(Path(root) / "watch-out.json")}
        plan_path = Path(root) / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        from citeline import watch
        result = watch.run_watch(plan_file=str(plan_path))
        self.assertIsInstance(result, dict)
        self.assertEqual(count(home), n)
        self.assertEqual(failures(home), [])

    def test_answers_cap_limit_token_still_stores_nothing(self):
        root, home = make_home(self)
        journal.write_config(home, "answers_per_round = 1\n")
        seed(self, home)
        service.probe_import(home=str(home), **import_kwargs(ANSWER))
        n = count(home)
        set_cap(home, n + 1)
        journal.write_config(
            home, "answers_per_round = 1\njournal_length = %d\n" % (n + 1))
        kwargs = import_kwargs(answer_file(
            root, "other.txt",
            "A different answer about the product, with its own "
            "words and its own sentence.\n"))
        kwargs["engine_label"] = "engine-b"
        kwargs["captured_on"] = "2026-11-11"
        with self.assertRaises(Exception) as caught:
            service.probe_import(home=str(home), **kwargs)
        self.assertEqual(tok(caught.exception), "LIMIT_EXCEEDED")
        self.assertEqual(count(home), n)

    def test_guide_failure_one_slot_stores_exactly_one(self):
        root, home, n = self._one_slot()
        with self.assertRaises(Exception):
            service.guide(home=str(home), run_id="run-999",
                          audit_date=AUDIT_DATE)
        self.assertEqual(count(home), n + 1)
        self.assertEqual(len(failures(home)), 1)

    def test_audit_failure_with_room_stores_exactly_one(self):
        root, home = make_home(self)
        seed(self, home)
        n = count(home)
        set_cap(home, n + 2)
        with self.assertRaises(Exception) as caught:
            service.audit(home=str(home),
                          page_file=str(root / "nope.txt"),
                          audit_date=AUDIT_DATE)
        self.assertNotIn(tok(caught.exception),
                         ("LIMIT_EXCEEDED", "JOURNAL_CAP_EXCEEDED",
                          "CONTROL_CAP_EXCEEDED"))
        self.assertEqual(count(home), n + 1)
        self.assertEqual(len(failures(home)), 1)


