"""Step 16 supplementary fix tests, builder G1: the staleness view.

Defect covered: E-01 (High). The staleness view stands claimed
and unshipped. Brief Section 5.12, the IM7-ANA-5 landing, and
brief Section 11, contract C9, with plan contract C9 and pass
condition P59, claim an on demand staleness view over the stored
records of one home, listing for each stored record the bound
versions it reads, the versions in force, and its state.

Every test builds a constructed home of its own: a standing
product giving the versions in force, and stored AuditRun and
Round records appended through the journal carrying bound
versions in differing states. Dates are call inputs.
"""

import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from citeline import checks, detection, errors, journal, robots
from citeline import service, shell
from citeline import install as install_module

AUDIT_DATE = "2026-11-14"
PRODUCT = "Acme Ledger"


def token_of(exc):
    return getattr(exc, "token", None) or getattr(
        exc, "error_value", None)


def exit_code_of(exc):
    code = getattr(exc, "exit_code", None)
    if code is not None:
        return code
    entry = errors.error_for_token(token_of(exc))
    return entry["exit_code"] if entry is not None else None


def all_keys(node):
    keys = set()
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(key)
            keys |= all_keys(value)
    elif isinstance(node, list):
        for item in node:
            keys |= all_keys(item)
    return keys


class G1Case(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(
            tempfile.TemporaryDirectory()))
        self.home = self.root / "home"
        install_module.install(
            location=str(self.root / "install"),
            home=str(self.home))
        service.add_product(
            home=str(self.home), name=PRODUCT,
            canonical_line="Acme Ledger helps teams track citations.",
            domain="acme.example", audit_date=AUDIT_DATE)
        product = service.list_products(home=str(self.home))[0]
        self.product_id = product["product_id"]
        self.in_force = {
            "registry_version": product["registry_version"],
            "query_set_version": product["query_set_version"],
            "detector_version": detection.DETECTOR_VERSION,
            "lexicon_version": detection.DETECTOR_VERSION,
            "ruleset_version": checks.SCORE_RULESET_VERSION,
            "crawler_table_version": robots.TABLE_VERSION,
        }

    def append(self, kind, payload):
        return journal.append_entry(
            str(self.home), kind, payload, audit_date=AUDIT_DATE)

    def audit_payload(self, run_id, **versions):
        payload = {
            "run_id": run_id,
            "product_id": self.product_id,
            "registry_version": self.in_force["registry_version"],
            "detector_version": self.in_force["detector_version"],
            "lexicon_version": self.in_force["lexicon_version"],
            "ruleset_version": self.in_force["ruleset_version"],
            "crawler_table_version": self.in_force[
                "crawler_table_version"],
        }
        payload.update(versions)
        return payload

    def round_payload(self, label, **versions):
        payload = {
            "round_id": "%s:%s" % (self.product_id, label),
            "product_id": self.product_id,
            "round_label": label,
            "registry_version_at_first_import": self.in_force[
                "registry_version"],
            "detector_version_at_first_import": self.in_force[
                "detector_version"],
            "lexicon_version": self.in_force["lexicon_version"],
            "query_set_version": self.in_force["query_set_version"],
        }
        payload.update(versions)
        return payload

    def seed_records(self):
        self.append("audit_record", self.audit_payload("run-current"))
        self.append("audit_record", self.audit_payload(
            "run-stale",
            ruleset_version="stale-ruleset",
            crawler_table_version=self.in_force[
                "crawler_table_version"] + 100))
        self.append("audit_record", self.audit_payload(
            "run-break",
            registry_version=self.in_force["registry_version"] + 10))
        self.append("round_named", self.round_payload("round-current"))
        broken = self.round_payload(
            "round-break", detector_version_at_first_import=None)
        self.append("round_named", broken)
        self.append("answer_imported", {
            "answer_id": "ans-break",
            "product_id": self.product_id,
            "round_id": broken["round_id"],
            "registry_version_at_import": self.in_force[
                "registry_version"],
            "detector_version_at_import": self.in_force[
                "detector_version"] + 5,
        })

    def view(self):
        return service.staleness_view(home=str(self.home))

    def by_id(self, record):
        return {item["record_id"]: item
                for item in record["records"]}


class TestStalenessStates(G1Case):
    def test_each_record_lists_bound_in_force_and_state(self):
        self.seed_records()
        record = self.view()
        self.assertEqual(record["home_path"], str(self.home))
        self.assertEqual(record["record_count"], 5)
        rows = self.by_id(record)
        self.assertEqual(rows["run-current"]["state"], "current")
        self.assertEqual(rows["run-stale"]["state"], "stale")
        self.assertEqual(
            rows["run-break"]["state"], "across a break")
        self.assertEqual(
            rows["%s:round-current" % self.product_id]["state"],
            "current")
        self.assertEqual(
            rows["%s:round-break" % self.product_id]["state"],
            "across a break")
        stale = rows["run-stale"]
        self.assertEqual(
            set(stale["changed_axes"]),
            {"ruleset_version", "crawler_table_version"})
        self.assertEqual(
            stale["bound_versions"]["ruleset_version"],
            "stale-ruleset")
        self.assertEqual(
            stale["versions_in_force"]["ruleset_version"],
            self.in_force["ruleset_version"])
        self.assertIn(
            "registry_version", rows["run-break"]["changed_axes"])
        current = rows["run-current"]
        self.assertEqual(current["changed_axes"], [])
        self.assertEqual(
            current["bound_versions"]["registry_version"],
            self.in_force["registry_version"])
        self.assertEqual(
            current["versions_in_force"]["detector_version"],
            self.in_force["detector_version"])

    def test_round_takes_only_current_and_across_a_break(self):
        self.seed_records()
        record = self.view()
        for item in record["records"]:
            if item["record_kind"] == "round":
                self.assertIn(
                    item["state"], ("current", "across a break"))

    def test_unstored_axis_is_not_recorded_and_never_inferred(self):
        self.seed_records()
        rows = self.by_id(self.view())
        audit = rows["run-current"]
        self.assertIn(
            "query_set_version", audit["not_recorded_axes"])
        self.assertNotIn(
            "query_set_version", audit["bound_versions"])
        round_row = rows["%s:round-current" % self.product_id]
        self.assertIn(
            "crawler_table_version", round_row["not_recorded_axes"])
        self.assertNotIn(
            "crawler_table_version", round_row["bound_versions"])

    def test_stale_wording_states_comparability_only(self):
        self.seed_records()
        rows = self.by_id(self.view())
        note = rows["run-stale"].get("state_note") or ""
        self.assertIn("comparability", note)
        self.assertIn("not invalidated", note)
        self.assertNotIn("invalid", note.replace(
            "not invalidated", ""))

    def test_view_prints_no_new_rate_or_score(self):
        self.seed_records()
        record = self.view()
        keys = all_keys(record)
        self.assertNotIn("score", keys)
        self.assertNotIn("rates", keys)

    def test_versions_in_force_are_read_at_view_time(self):
        self.append(
            "audit_record", self.audit_payload("run-current"))
        self.assertEqual(
            self.by_id(self.view())["run-current"]["state"],
            "current")
        service.set_canonical_line(
            home=str(self.home), product=PRODUCT,
            line="Acme Ledger tracks citations for teams.",
            audit_date=AUDIT_DATE)
        self.assertEqual(
            self.by_id(self.view())["run-current"]["state"],
            "across a break")


class TestStalenessRoute(G1Case):
    def test_view_appends_nothing(self):
        self.seed_records()
        path = Path(self.home) / "journal.jsonl"
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        count_before = service.verify(
            home=str(self.home))["entry_count"]
        self.view()
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = shell.main([
                "staleness-view", "--home", str(self.home),
                "--form", "advanced"])
        self.assertEqual(code, 0)
        after = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        self.assertEqual(
            count_before,
            service.verify(home=str(self.home))["entry_count"])

    def test_shell_route_in_all_three_forms(self):
        self.seed_records()
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = shell.main([
                "staleness-view", "--home", str(self.home),
                "--form", "advanced"])
        self.assertEqual(code, 0)
        parsed = json.loads(stream.getvalue())
        self.assertEqual(parsed["record_count"], 5)

        stream = io.StringIO()
        with redirect_stdout(stream):
            code = shell.main([
                "staleness-view", "--home", str(self.home),
                "--form", "simple"])
        self.assertEqual(code, 0)
        text = stream.getvalue()
        self.assertIn("across a break", text)
        self.assertIn("stale", text)

        stream = io.StringIO()
        with redirect_stdout(stream):
            code = shell.main([
                "staleness-view", "--home", str(self.home),
                "--form", "agentic"])
        self.assertEqual(code, 0)
        envelope = json.loads(stream.getvalue())
        self.assertIn("schema_stamp", envelope)
        self.assertEqual(
            envelope["report"]["record_count"], 5)
        self.assertNotEqual(envelope, parsed)

    def test_help_surface_list_names_the_view(self):
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = shell.main(["help"])
        self.assertEqual(code, 0)
        self.assertIn("staleness-view", stream.getvalue())
        self.assertIn("staleness-view", shell.help_text())


class TestStalenessEdges(G1Case):
    def test_empty_home_prints_the_absence_form(self):
        record = self.view()
        self.assertEqual(record["record_count"], 0)
        self.assertEqual(record["records"], [])
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = shell.main([
                "staleness-view", "--home", str(self.home),
                "--form", "simple"])
        self.assertEqual(code, 0)
        text = stream.getvalue()
        self.assertIn("no entries", text)
        self.assertIn(
            "Verify proves internal consistency only", text)

    def test_missing_home_refuses_home_missing(self):
        missing = str(self.root / "no-such-home")
        with self.assertRaises(Exception) as caught:
            service.staleness_view(home=missing)
        self.assertEqual(token_of(caught.exception), "HOME_MISSING")
        self.assertEqual(exit_code_of(caught.exception), 2)
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = shell.main([
                "staleness-view", "--home", missing])
        self.assertEqual(code, 2)

    def test_barred_chain_produces_no_graph(self):
        self.seed_records()
        path = Path(self.home) / "journal.jsonl"
        raw = path.read_bytes()
        self.assertIn(b"Acme Ledger", raw)
        path.write_bytes(raw.replace(
            b"Acme Ledger", b"acme Ledger", 1))
        with self.assertRaises(Exception) as caught:
            self.view()
        self.assertEqual(
            token_of(caught.exception), "JOURNAL_VERIFY_FAILED")
        self.assertEqual(exit_code_of(caught.exception), 5)
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = shell.main([
                "staleness-view", "--home", str(self.home),
                "--form", "advanced"])
        self.assertEqual(code, 5)
        self.assertNotIn("record_count", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
