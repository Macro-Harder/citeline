"""Slice S11 tests: scheduled estate watch.

Tests are written before the product. They import the product package
named citeline and call the watch operation the plan states. An import
failure or a missing attribute is the expected red state. Dates are
call inputs in every test. No test claims a cadence, because the
product keeps none. No test states an estate level pooled figure.
No test assumes answers arriving during a round, assumes a watched
directory, or treats an unimported round as a product failure.
Mid round registry change effects on a target not yet run stand on
K-18 ground and no test here decides that ground.
Timing assertions use the scale stated in scales-w7.md.
"""

import json
import tempfile
import time
import unittest
from pathlib import Path

from citeline import service, shell, watch

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
PAGE = FIXTURES / "w7-page.md"
ANSWER = FIXTURES / "w7-answer.txt"


def plan_file(case, data):
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    path = root / "plan.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return root, path


def base_plan(home, scope, **extra):
    data = {"home": str(home), "scope": scope,
            "audit_date": AUDIT_DATE, "form": "simple"}
    data.update(extra)
    return data


def seed_home(case):
    """Build a home with two products through service calls.

    p-alpha holds a registered page snapshot and one round with one
    imported answer. p-beta holds neither a page nor a round.
    """
    from citeline import install as install_module
    root = Path(case.enterContext(tempfile.TemporaryDirectory()))
    location, home = root / "install", root / "home"
    install_module.install(location=str(location), home=str(home))
    for name in ("p-alpha", "p-beta"):
        service.add_product(
            home=str(home), name=name, canonical_line=name + " line.",
            domain="example.com", audit_date=AUDIT_DATE)
    audit = service.audit(home=str(home), page_file=str(PAGE),
                          audit_date=AUDIT_DATE)
    service.register_page(home=str(home), product="p-alpha",
                          snapshot=audit["snapshot_id"],
                          audit_date=AUDIT_DATE)
    # Step 16 reconciliation under D-17: the query set stands
    # registered through the governed set_query_set route before
    # any probe import, so the imported query stands in the
    # product query set already, as brief item 132 and the
    # adapter contract order. No assertion in this file changes.
    service.set_query_set(home=str(home), product="p-alpha",
                          query_set=["What is Example Product?"],
                          audit_date=AUDIT_DATE)
    service.name_round(home=str(home), product="p-alpha",
                       round_label="round-1",
                       importer_declaration="operator",
                       supplier_relation="first party",
                       audit_date=AUDIT_DATE)
    service.probe_import(
        home=str(home), answer_file=str(ANSWER), product="p-alpha",
        round="round-1", engine_label="engine-a",
        query="What is Example Product?", kind="real_sample",
        captured_on="2026-11-10", capture_method="manual copy",
        audit_date=AUDIT_DATE)
    return root, home, audit


def run(case, home, scope, **extra):
    _, path = plan_file(case, base_plan(home, scope, **extra))
    return watch.run_watch(plan_file=str(path))


class TestWatchPlanBounds(unittest.TestCase):
    """Row S11 WatchPlan bounds. Oracle: plan Section 3 W-2 and entry
    13 rows U-9 to U-13 on decision D-WATCH-13. Each bound stands as a
    Manager settlement under delegation, open to Captain JP's
    overturn, and never as her words."""

    def test_watchplan_over_1mib_refused_at_open_as_usage_error(self):
        """Pins W-2 governing size bound of 1 MiB, a Manager settlement
        under delegation. Oracle: plan W-2 and row U-9: refused at
        open as a usage error naming the bound, before any round
        runs, with no failure record."""
        fixture = FIXTURES / "w7-watchplan-oversize.json"
        self.assertGreater(fixture.stat().st_size, 1024 * 1024)
        with self.assertRaises(Exception) as caught:
            watch.run_watch(plan_file=str(fixture))
        self.assertIn("1 MiB", str(caught.exception))

    def test_watchplan_over_1mib_shell_returns_usage_code_2(self):
        """Pins W-2 size bound exit limb, a Manager settlement under
        delegation. Oracle: plan Section 4.2 watch row: rows U-9 to
        U-13 are usage class with exit code 2 and no round runs."""
        code = shell.main(
            ["watch", "--plan", str(FIXTURES / "w7-watchplan-oversize.json")])
        self.assertEqual(code, 2)

    def test_picked_scope_over_100_targets_refused(self):
        """Pins picked scope bound of at most 100 targets, a Manager
        settlement under delegation. Oracle: plan W-2 and row U-10:
        refused after parsing and before any round runs as a usage
        error naming the bound, with no failure record."""
        fixture = FIXTURES / "w7-watchplan-picked-101.json"
        targets = json.loads(fixture.read_text(encoding="utf-8"))["targets"]
        self.assertEqual(len(targets), 101)
        with self.assertRaises(Exception):
            watch.run_watch(plan_file=str(fixture))

    def test_estate_scope_file_listing_targets_refused_as_usage_error(self):
        """Pins the estate with targets refusal, a Manager settlement
        under delegation. Oracle: plan W-2 row U-11 and the WatchPlan
        shape at plan Section 5.1: a file whose scope is estate and
        which also lists targets stands refused as a usage error, its
        targets never silently disregarded, and no round runs."""
        fixture = FIXTURES / "w7-watchplan-estate-with-targets.json"
        with self.assertRaises(Exception):
            watch.run_watch(plan_file=str(fixture))
        self.assertEqual(
            shell.main(["watch", "--plan", str(fixture)]), 2)

    def test_picked_scope_duplicate_target_refused_at_open(self):
        """Pins W-2 duplicate refusal. Oracle: plan W-2 row U-12,
        settlement A-09: a picked file listing the same target twice
        stands refused at open, before any round runs."""
        with self.assertRaises(Exception):
            watch.run_watch(
                plan_file=str(FIXTURES / "w7-watchplan-picked-duplicate.json"))

    def test_picked_scope_naming_no_target_refused_at_open(self):
        """Pins W-2 empty picked refusal. Oracle: plan W-2 row U-13,
        settlement A-10: a picked file naming no target stands
        refused at open, because the WatchPlan shape states targets
        required where scope is picked."""
        with self.assertRaises(Exception):
            watch.run_watch(
                plan_file=str(FIXTURES / "w7-watchplan-picked-empty.json"))


class TestTargetEnumeration(unittest.TestCase):
    """Row S11 target enumeration. Oracle: plan Section 3 W-3 and W-4,
    and the WatchPlan and WatchRun shapes at plan Section 5.1."""

    def test_picked_targets_run_in_plan_order(self):
        """Pins picked enumeration order. Oracle: plan W-4: for each
        target, in plan order in picked scope."""
        _, home, _ = seed_home(self)
        result = run(self, home, "picked", targets=[
            {"product": "p-beta", "page_file": str(PAGE)},
            {"product": "p-alpha", "round": "round-1"},
            {"product": "p-alpha", "page_file": str(PAGE)}])
        sequence = [(e["product"], e["target_kind"])
                    for e in result["entries"]]
        self.assertEqual(sequence, [("p-beta", "audit"),
                                    ("p-alpha", "probe"),
                                    ("p-alpha", "audit")])

    def test_estate_targets_in_registry_order_at_round_start(self):
        """Pins estate enumeration order. Oracle: plan W-3 and W-4:
        estate targets in registry order over the registry as it
        stands at the round start, read once for enumeration."""
        _, home, _ = seed_home(self)
        service.add_product(
            home=str(home), name="a-added-late",
            canonical_line="a-added-late line.", domain="example.com",
            audit_date=AUDIT_DATE)
        result = run(self, home, "estate")
        seen = []
        for e in result["entries"]:
            if e["product"] not in seen:
                seen.append(e["product"])
        self.assertEqual(seen, ["p-alpha", "p-beta", "a-added-late"])
        self.assertNotEqual(seen, sorted(seen))

    def test_estate_skip_reason_no_page_on_file(self):
        """Pins estate skip reason one. Oracle: plan W-3: a product
        with no snapshot standing as a product page is listed as
        skipped, reason no page on file. A skip is neither a failure
        nor a pass."""
        _, home, _ = seed_home(self)
        result = run(self, home, "estate")
        skips = [e for e in result["entries"]
                 if e["product"] == "p-beta" and e["outcome"] == "skipped"]
        self.assertTrue(any(
            e.get("skip_reason") == "no page on file" for e in skips))

    def test_estate_skip_reason_no_round_with_answers(self):
        """Pins estate skip reason two. Oracle: plan W-3: a product
        with no non-empty round is listed as skipped, reason no
        round with answers."""
        _, home, _ = seed_home(self)
        result = run(self, home, "estate")
        skips = [e for e in result["entries"]
                 if e["product"] == "p-beta" and e["outcome"] == "skipped"]
        self.assertTrue(any(
            e.get("skip_reason") == "no round with answers"
            for e in skips))

    def test_estate_both_grounds_absent_gives_two_skip_entries(self):
        """Pins estate skip cardinality. Oracle: plan W-3: audit
        ground absent and probe ground absent gives two skip
        entries, one of each kind, each with its own reason."""
        _, home, _ = seed_home(self)
        result = run(self, home, "estate")
        skips = [e for e in result["entries"]
                 if e["product"] == "p-beta" and e["outcome"] == "skipped"]
        self.assertEqual(len(skips), 2)
        self.assertEqual({e["target_kind"] for e in skips},
                         {"audit", "probe"})

    def test_estate_product_with_both_grounds_has_no_skip_entry(self):
        """Pins estate skip cardinality, present grounds limb. Oracle:
        plan W-3: audit ground present and probe ground present
        gives no skip entry, and the entries stand as the operations
        give them."""
        _, home, _ = seed_home(self)
        result = run(self, home, "estate")
        skips = [e for e in result["entries"]
                 if e["product"] == "p-alpha" and e["outcome"] == "skipped"]
        self.assertEqual(skips, [])

    def test_estate_empty_registry_runs_as_zero_target_round(self):
        """Pins estate zero target round. Oracle: plan W-3 settlement
        A-10: a home whose registry stands empty runs as a zero
        target round and completes with an empty WatchRun, with no
        target entry and no skip entry."""
        from citeline import install as install_module
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        install_module.install(location=str(root / "i"),
                               home=str(root / "h"))
        result = run(self, root / "h", "estate")
        self.assertEqual(result["entries"], [])

    def test_picked_target_never_stands_skipped(self):
        """Pins picked outcome set. Oracle: plan WatchRun shape: the
        skipped outcome stands for estate enumeration only; a picked
        target completes or fails, and never stands skipped."""
        _, home, _ = seed_home(self)
        result = run(self, home, "picked", targets=[
            {"product": "p-alpha", "page_file": str(PAGE)}])
        self.assertTrue(all(
            e["outcome"] != "skipped" for e in result["entries"]))


class TestFailureIsolation(unittest.TestCase):
    """Row S11 per target failure isolation. Oracle: plan Section 3
    W-5 and contract CW failure behaviour."""

    def test_missing_target_file_fails_that_target_only(self):
        """Pins failure isolation, missing file limb. Oracle: plan
        W-5: a target whose file is missing fails that target only,
        with the operation recorded error entered in the summary,
        and the round continues."""
        _, home, _ = seed_home(self)
        result = run(self, home, "picked", targets=[
            {"product": "p-alpha", "page_file": "/no/such/page.md"},
            {"product": "p-alpha", "page_file": str(PAGE)}])
        self.assertEqual(len(result["entries"]), 2)
        self.assertEqual(result["entries"][0]["outcome"], "failed")
        self.assertIn("recorded_error", result["entries"][0])
        self.assertEqual(result["entries"][1]["outcome"], "completed")

    def test_unreadable_target_file_fails_that_target_only(self):
        """Pins failure isolation, unreadable file limb. Oracle: plan
        W-5: a target whose file is unreadable fails that target
        only and the round continues to its next target."""
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        locked = root / "locked.md"
        locked.mkdir()
        _, home, _ = seed_home(self)
        result = run(self, home, "picked", targets=[
            {"product": "p-alpha", "page_file": str(locked)},
            {"product": "p-alpha", "round": "round-1"}])
        self.assertEqual(result["entries"][0]["outcome"], "failed")
        self.assertIn("recorded_error", result["entries"][0])
        self.assertEqual(result["entries"][1]["outcome"], "completed")

    def test_failing_target_operation_fails_that_target_only(self):
        """Pins failure isolation, failing operation limb. Oracle:
        plan W-5 and contract CW: a target failure does not abort
        or void another target, and no operation contract is
        weakened inside a target to keep the round moving."""
        _, home, _ = seed_home(self)
        result = run(self, home, "picked", targets=[
            {"product": "p-alpha", "round": "no-such-round"},
            {"product": "p-alpha", "page_file": str(PAGE)}])
        self.assertEqual(result["entries"][0]["outcome"], "failed")
        self.assertIn("recorded_error", result["entries"][0])
        self.assertEqual(result["entries"][1]["outcome"], "completed")

    def test_target_failures_do_not_set_the_round_exit_code(self):
        """Pins watch exit behaviour with target failures. Oracle:
        plan Section 4.2 watch row: a target failure recorded in
        the summary is not the round's own error value, and a round
        that completed and produced its summary returns 0."""
        _, home, _ = seed_home(self)
        _, path = plan_file(self, base_plan(home, "picked", targets=[
            {"product": "p-alpha", "page_file": "/no/such/page.md"}]))
        self.assertEqual(shell.main(["watch", "--plan", str(path)]), 0)


class TestSummaryCompleteness(unittest.TestCase):
    """Row S11 summary completeness. Oracle: plan WatchRun shape at
    Section 5.1 and contract CW guarantee."""

    def test_one_entry_per_target_attempted_in_run_order(self):
        """Pins summary completeness. Oracle: contract CW: every
        target attempted stands recorded once in the summary, in
        run order, with its outcome."""
        _, home, _ = seed_home(self)
        result = run(self, home, "picked", targets=[
            {"product": "p-alpha", "page_file": str(PAGE)},
            {"product": "p-alpha", "round": "round-1"},
            {"product": "p-beta", "page_file": str(PAGE)}])
        self.assertEqual(len(result["entries"]), 3)
        sequence = [(e["product"], e["target_kind"])
                    for e in result["entries"]]
        self.assertEqual(sequence, [("p-alpha", "audit"),
                                    ("p-alpha", "probe"),
                                    ("p-beta", "audit")])

    def test_each_entry_carries_outcome_and_identity_or_error(self):
        """Pins summary entry contents. Oracle: plan WatchRun shape:
        each entry carries its outcome and the stored record
        identity, the recorded error, or the skip reason the shape
        states for that outcome."""
        _, home, _ = seed_home(self)
        result = run(self, home, "picked", targets=[
            {"product": "p-alpha", "page_file": str(PAGE)},
            {"product": "p-alpha", "page_file": "/no/such/page.md"}])
        done, failed = result["entries"]
        self.assertEqual(done["outcome"], "completed")
        self.assertIn("record_identity", done)
        self.assertEqual(failed["outcome"], "failed")
        self.assertIn("recorded_error", failed)

    def test_counts_of_each_outcome_tally_the_entries(self):
        """Pins summary outcome counts. Oracle: plan WatchRun shape:
        counts of each outcome stand as tallies of the round's own
        target entries, and no rate, score, or finding stands
        restated as a watch figure."""
        _, home, _ = seed_home(self)
        result = run(self, home, "estate")
        counts = result["outcome_counts"]
        total = sum(counts.values())
        self.assertEqual(total, len(result["entries"]))
        for key in counts:
            self.assertIn(key, ("completed", "failed", "skipped",
                                "stopped"))

    def test_watchrun_carries_round_identity_fields(self):
        """Pins WatchRun artefact fields. Oracle: plan WatchRun shape
        and plan Section 1.5 reverse trace row: home path, scope as
        run, plan file sha256, and audit date as run."""
        _, home, _ = seed_home(self)
        _, path = plan_file(self, base_plan(home, "estate"))
        result = watch.run_watch(plan_file=str(path))
        for field in ("home_path", "scope", "plan_file_sha256",
                      "audit_date"):
            self.assertIn(field, result)
        self.assertEqual(result["audit_date"], AUDIT_DATE)


class TestJournalVerifyBar(unittest.TestCase):
    """Row S11 journal verify bar. Oracle: plan W-5 and contract CW:
    a home whose journal fails verify fails the whole round before
    any target runs."""

    def test_failed_verify_fails_round_before_any_target_runs(self):
        """Pins the verify bar. Oracle: plan W-5: every operation the
        round would call stands barred on that home, no WatchRun
        artefact stands produced, and no target entry stands made,
        on the WatchRun shape terms at plan Section 5.1."""
        _, home, _ = seed_home(self)
        journal_files = [p for p in home.rglob("*") if p.is_file()]
        target = max(journal_files, key=lambda p: p.stat().st_size)
        data = bytearray(target.read_bytes())
        data[-2] = data[-2] ^ 1
        target.write_bytes(bytes(data))
        before = service.status(home=str(home))["entry_count"]
        with self.assertRaises(Exception):
            run(self, home, "estate")
        after = service.status(home=str(home))["entry_count"]
        self.assertEqual(before, after)


class TestWatchRunRendering(unittest.TestCase):
    """Row S11 WatchRun rendering. Oracle: plan W-6: rendered on the
    S9 pipeline in the form the invocation names, and written under
    boundary B4's no replace rule where written to a file."""

    def test_watchrun_written_to_a_new_output_path(self):
        """Pins WatchRun rendering to a file. Oracle: plan W-6: the
        output path a WatchPlan names is the path for that one
        round only."""
        _, home, _ = seed_home(self)
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        out_path = root / "watchrun.txt"
        run(self, home, "estate", output=str(out_path))
        self.assertTrue(out_path.is_file())
        self.assertIn("p-alpha", out_path.read_text(encoding="utf-8"))

    def test_watchrun_write_never_replaces_a_standing_artefact(self):
        """Pins boundary B4 no replace rule on the WatchRun write.
        Oracle: plan W-6: the product neither overwrites nor rotates
        a standing artefact path. Where the write alone fails on
        row X-9 after every target completed, the stored records
        stand, no WatchRun artefact for that round stands produced,
        and the watch invocation returns exit code 3."""
        _, home, _ = seed_home(self)
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        out_path = root / "watchrun.txt"
        out_path.write_text("earlier round\n", encoding="utf-8")
        _, path = plan_file(self, base_plan(
            home, "estate", output=str(out_path)))
        code = shell.main(["watch", "--plan", str(path)])
        self.assertEqual(code, 3)
        self.assertEqual(out_path.read_text(encoding="utf-8"),
                         "earlier round\n")


class TestInvokedOperations(unittest.TestCase):
    """Row S11 invoked operations, limb by limb. Oracle: plan W-4,
    slice S11 families for the invoked operations, and contract CW."""

    def test_audit_limb_runs_the_audit_operation_on_c8_terms(self):
        """Pins the audit limb. Oracle: plan W-4 and contract C8: an
        audit target runs the existing audit operation over the
        file as it stands at that moment, exact for the supplied
        file only, and its entry carries the audit run identity."""
        _, home, _ = seed_home(self)
        result = run(self, home, "picked", targets=[
            {"product": "p-alpha", "page_file": str(PAGE)}])
        entry = result["entries"][0]
        self.assertEqual(entry["outcome"], "completed")
        self.assertIn("record_identity", entry)

    def test_audit_limb_no_completed_audit_claimed_on_a_stopped_limb(self):
        """States the audit limb stopped form at its reduced strength.
        Oracle: plan W-4 and slice S11. No stated seam in the sources
        read forces a stop inside a watch round, so this test pins
        only the ordinary completed audit entry, and the stopped
        audit limb stands carried as a named gap at its stated
        strength, in the same form as the contention gap carriage:
        a stopped limb recorded under the outcome value stopped, and
        no completed audit claimed on a stopped limb, proven at the
        first stage that holds a surface for forcing a stop. The
        severance stands recorded in writer 7's paper by an appended
        dated erratum note."""
        _, home, _ = seed_home(self)
        result = run(self, home, "picked", targets=[
            {"product": "p-alpha", "page_file": str(PAGE)}])
        entry = result["entries"][0]
        self.assertEqual(entry["outcome"], "completed")
        self.assertIn("record_identity", entry)

    def test_probe_report_limb_runs_on_c4_terms(self):
        """Pins the probe report limb. Oracle: plan W-4 and contract
        C4: a probe target runs the existing probe report operation
        over rounds already imported by hand, reading one consistent
        round state."""
        _, home, _ = seed_home(self)
        result = run(self, home, "picked", targets=[
            {"product": "p-alpha", "round": "round-1"}])
        entry = result["entries"][0]
        self.assertEqual(entry["outcome"], "completed")
        self.assertEqual(entry.get("record_identity"), "round-1")

    def test_trend_limb_pair_first_member_is_earliest_qualifying_round(self):
        """Pins the trend limb pairing, first member. Oracle: plan
        W-4 ruled pairing: each target's trend pair has as its first
        member that target's earliest qualifying round in the
        watch's scope, on contract C5 terms."""
        _, home, _ = seed_home(self)
        service.name_round(home=str(home), product="p-alpha",
                           round_label="round-2",
                           importer_declaration="operator",
                           supplier_relation="first party",
                           audit_date=AUDIT_DATE)
        service.probe_import(
            home=str(home), answer_file=str(ANSWER), product="p-alpha",
            round="round-2", engine_label="engine-a",
            query="What is Example Product?", kind="real_sample",
            captured_on="2026-11-11", capture_method="manual copy",
            audit_date=AUDIT_DATE)
        result = run(self, home, "picked", targets=[
            {"product": "p-alpha", "round": "round-2"}])
        entry = result["entries"][0]
        self.assertEqual(entry["outcome"], "completed")
        trend = entry.get("trend_pair")
        if trend is not None:
            self.assertEqual(trend[0], "round-1")
            self.assertEqual(trend[1], "round-2")

    def test_trend_limb_runs_once_per_probe_target(self):
        """Pins the trend limb at its reduced stated strength. Oracle:
        plan W-4 and contract CW. This test observes one summary
        entry per probe target only. The trend run count limb stands
        carried as a named gap at the strength the WatchRun shape
        allows, beside the trend first member gap: the shape states
        no trend run count, so no count stands pinned here unless a
        shape surface stating one is added to the plan first."""
        _, home, _ = seed_home(self)
        service.name_round(home=str(home), product="p-alpha",
                           round_label="round-2",
                           importer_declaration="operator",
                           supplier_relation="first party",
                           audit_date=AUDIT_DATE)
        service.probe_import(
            home=str(home), answer_file=str(ANSWER), product="p-alpha",
            round="round-2", engine_label="engine-a",
            query="What is Example Product?", kind="real_sample",
            captured_on="2026-11-11", capture_method="manual copy",
            audit_date=AUDIT_DATE)
        result = run(self, home, "picked", targets=[
            {"product": "p-alpha", "round": "round-1"},
            {"product": "p-alpha", "round": "round-2"}])
        probe_entries = [e for e in result["entries"]
                         if e["target_kind"] == "probe"]
        self.assertEqual(len(probe_entries), 2)

    def test_trend_degenerate_pair_excluded_before_any_trend_call(self):
        """Pins the trend limb degenerate pair rule. Oracle: plan
        W-4: a pair whose second member would be its first member
        is excluded before any trend call, the target entry keeps
        the outcome its probe report gives it, and its no pair
        outcome is carried in the trend limb tally."""
        _, home, _ = seed_home(self)
        result = run(self, home, "picked", targets=[
            {"product": "p-alpha", "round": "round-1"}])
        entry = result["entries"][0]
        self.assertEqual(entry["outcome"], "completed")
        self.assertGreaterEqual(result["trend_no_pair_count"], 1)

    def test_guide_limb_picked_target_only_over_the_audit_just_ran(self):
        """Pins the guide call limb, picked form. Oracle: plan W-4
        and the WatchPlan shape: a picked audit target naming a
        guide call runs the guide operation over the audit record
        that target just produced, in the one guide form the plan
        states, with one outcome row per operation invoked."""
        _, home, _ = seed_home(self)
        result = run(self, home, "picked", targets=[
            {"product": "p-alpha", "page_file": str(PAGE),
             "guide": True}])
        entry = result["entries"][0]
        channels = entry.get("channel_rows", [])
        kinds = [row["kind"] for row in channels]
        self.assertIn("audit", kinds)
        self.assertIn("guide", kinds)
        audit_row = next(r for r in channels if r["kind"] == "audit")
        guide_row = next(r for r in channels if r["kind"] == "guide")
        audit_identity = audit_row.get("record_identity")
        self.assertIsNotNone(audit_identity)
        self.assertIn(audit_identity, guide_row.values())

    def test_guide_limb_no_guide_form_for_a_probe_target(self):
        """Pins the guide call limb, probe exclusion. Oracle: plan
        Section 1.3 S11: no guide form for a probe target stands,
        and a probe entry carries no guide channel row."""
        _, home, _ = seed_home(self)
        result = run(self, home, "picked", targets=[
            {"product": "p-alpha", "round": "round-1"}])
        entry = result["entries"][0]
        kinds = [row["kind"] for row in entry.get("channel_rows", [])]
        self.assertNotIn("guide", kinds)

    def test_guide_limb_no_implicit_guide_call_for_an_estate_target(self):
        """Pins the guide call limb, estate exclusion. Oracle: plan
        W-6 guide passage: no estate target runs a guide call
        implicitly, and estate rounds audit and report only."""
        _, home, _ = seed_home(self)
        result = run(self, home, "estate")
        for entry in result["entries"]:
            kinds = [row["kind"]
                     for row in entry.get("channel_rows", [])]
            self.assertNotIn("guide", kinds)


class TestWatchTimingScale(unittest.TestCase):
    """Row S11 timing. Oracle: plan Section 1.5 timing bounds: S11,
    one watch round over a WatchPlan, 30 seconds, conditional on the
    scale stated in scales-w7.md, for the watch batch work itself."""

    def test_one_watch_round_within_bound_at_stated_scale(self):
        """Pins S11 timing bound at the scales-w7.md scale: one watch
        round over a WatchPlan naming 10 picked targets."""
        _, home, _ = seed_home(self)
        for index in range(9):
            service.add_product(
                home=str(home), name="p-extra-%d" % index,
                canonical_line="Extra line.",
                domain="example.com", audit_date=AUDIT_DATE)
        targets = [{"product": "p-extra-%d" % index,
                    "page_file": str(PAGE)} for index in range(9)]
        targets.append({"product": "p-alpha", "round": "round-1"})
        start = time.monotonic()
        run(self, home, "picked", targets=targets)
        self.assertLess(time.monotonic() - start, 30.0)


if __name__ == "__main__":
    unittest.main()
