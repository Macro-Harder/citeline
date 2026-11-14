"""Slice S10 tests: service layer, command line shell, and install.

Tests are written before the product. They import the product package
named citeline and call the operation signatures the plan states.
An import failure or a missing attribute is the expected red state.
Dates are call inputs in every test. No test reads a date from a clock.
Timing assertions use the scale stated in scales-w7.md.
"""

import inspect
import json
import os
import time
import unittest
from pathlib import Path

import citeline
from citeline import install as install_module
from citeline import service, shell

FIXTURES = Path(__file__).parent / "fixtures"
AUDIT_DATE = "2026-11-13"
PAGE = FIXTURES / "w7-page.md"
ROBOTS = FIXTURES / "w7-robots.txt"

RULE_IDENTIFIERS = [
    "answer_first", "citations", "statistics", "quotations", "comparison",
    "freshness", "description_consistency", "keyword_stuffing", "fluff",
    "unproven_superlatives",
]


def make_home(case):
    """Create a fresh product home through the install operation."""
    root = Path(case.enterContext(__import__("tempfile").TemporaryDirectory()))
    location = root / "install"
    home = root / "home"
    install_module.install(location=str(location), home=str(home))
    return root, location, home


def seed_product(case, home):
    """Register one product and name one round through service calls."""
    service.add_product(
        home=str(home), name="Example Product",
        canonical_line="Example Product answers questions with citations.",
        domain="example.com", audit_date=AUDIT_DATE)
    service.name_round(
        home=str(home), product="Example Product", round_label="round-1",
        importer_declaration="operator", supplier_relation="first party",
        audit_date=AUDIT_DATE)
    return home


class TestOperationSignatures(unittest.TestCase):
    """Row S10 signatures. Oracle: brief Section 5.4 surface list and
    brief Section 5.12 per operation named inputs; plan Section 5.4."""

    EXPECTED_SIGNATURES = {
        "add_product": {"home", "name", "canonical_line", "domain",
                        "competitors", "aliases", "query_set",
                        "audit_date"},
        "set_canonical_line": {"home", "product", "line", "audit_date"},
        "set_competitors": {"home", "product", "competitors",
                            "audit_date"},
        "set_aliases": {"home", "product", "aliases", "audit_date"},
        "set_query_set": {"home", "product", "query_set", "audit_date"},
        "set_category": {"home", "product", "category_terms",
                         "audit_date"},
        "register_page": {"home", "product", "snapshot", "audit_date"},
        "name_round": {"home", "product", "round_label",
                       "importer_declaration", "supplier_relation",
                       "audit_date"},
        "probe_import": {"home", "answer_file", "product", "round",
                         "engine_label", "query", "kind", "captured_on",
                         "capture_method", "control_designation",
                         "audit_date"},
        "probe_report": {"home", "product", "round", "form",
                         "audit_date"},
        "probe_trend": {"home", "product", "round_a", "round_b", "form",
                        "audit_date"},
        "guide": {"home", "run_id", "product", "round_label",
                  "audit_date"},
        "robots": {"home", "robots_file", "evaluated_page_path", "form",
                   "audit_date"},
        "robots_preview": {"home", "first_robots_file",
                           "second_robots_file", "evaluated_page_path",
                           "first_capture_date", "second_capture_date",
                           "form", "audit_date"},
        "query_set_report": {"home", "product", "form", "audit_date"},
    }

    def assert_signature(self, fn, expected):
        params = inspect.signature(fn).parameters
        self.assertEqual(set(params), expected, fn.__name__)
        self.assertTrue(all(
            p.kind is p.KEYWORD_ONLY for p in params.values()),
            fn.__name__)

    def test_registry_operations_accept_named_inputs_only(self):
        """Pins plan Section 1.3 S10 operation signatures, registry limb.
        Oracle: brief Section 5.12 registry subcommand input lists.
        Every parameter stands keyword only and its name matches the
        Section 5.12 list for that operation."""
        for name in ("add_product", "set_canonical_line",
                     "set_competitors", "set_aliases", "set_query_set",
                     "set_category", "register_page", "name_round"):
            self.assert_signature(getattr(service, name),
                                  self.EXPECTED_SIGNATURES[name])

    def test_audit_signature_carries_page_and_optional_inputs(self):
        """Pins S10 signature for audit. Oracle: brief Section 5.12 audit
        inputs: page file required, robots file optional, evaluated page
        path optional with root default, audit_date optional."""
        _, _, home = make_home(self)
        record = service.audit(
            home=str(home), page_file=str(PAGE), robots_file=str(ROBOTS),
            audit_date=AUDIT_DATE)
        self.assertIn("run_id", record)
        self.assertIn("checks", record)

    def test_each_operation_returns_its_section_5_2_shape(self):
        """Pins S10 check 2 record identity limb per operation. Oracle:
        brief Section 5.4 check 2 and plan Section 5.1 shape field lists."""
        _, _, home = make_home(self)
        seed_product(self, home)
        status = service.status(home=str(home))
        for field in ("head_hash", "entry_count", "home_size", "home_path",
                      "capacity_outlook"):
            self.assertIn(field, status)
        verify = service.verify(home=str(home))
        self.assertIn("chain_result", verify)
        record = service.audit(
            home=str(home), page_file=str(PAGE), robots_file=str(ROBOTS),
            audit_date=AUDIT_DATE)
        for field in ("run_id", "product_id", "snapshot_id",
                      "evaluated_page_path", "path_defaulted",
                      "snapshot_format", "checks", "score",
                      "robots_summary", "audit_date",
                      "snapshot_sha256", "audit_date_is_run_date",
                      "limits_in_force"):
            self.assertIn(field, record)
        self.assertTrue(record["audit_date_is_run_date"])
        self.assertIn("raised_limits", record["limits_in_force"])
        stamps = [k for k in record if k.endswith("_version")]
        self.assertTrue(stamps)
        self.assertIn("score_ruleset_version", record["score"])
        report = service.probe_report(
            home=str(home), product="Example Product", round="round-1",
            form="advanced", audit_date=AUDIT_DATE)
        self.assertTrue(report)

    def test_probe_and_guide_and_report_signatures_exist(self):
        """Pins S10 signatures for probe import, probe report, probe
        trend, guide, robots, robots-preview, query-set-report. Oracle:
        brief Section 5.4 surface list and Section 5.12 inputs. Every
        parameter stands keyword only and its name matches the
        Section 5.12 list for that operation."""
        for name in ("probe_import", "probe_report", "probe_trend",
                     "guide", "robots", "robots_preview",
                     "query_set_report"):
            self.assert_signature(getattr(service, name),
                                  self.EXPECTED_SIGNATURES[name])

    def test_audit_run_assembly_fields(self):
        """Pins S10 AuditRun assembly, decided fields only. Oracle: plan
        Section 5.1 AuditRun entry: assembled by S10 from snapshot,
        checks and score, and robots report. The facts_counts member
        set stands blocked and no assertion touches its members."""
        _, _, home = make_home(self)
        seed_product(self, home)
        record = service.audit(
            home=str(home), page_file=str(PAGE), robots_file=str(ROBOTS),
            audit_date=AUDIT_DATE)
        for field in ("run_id", "product_id", "snapshot_id",
                      "evaluated_page_path", "path_defaulted",
                      "snapshot_format", "checks", "score",
                      "robots_summary", "audit_date",
                      "snapshot_sha256", "audit_date_is_run_date",
                      "limits_in_force"):
            self.assertIn(field, record)
        self.assertTrue(record["audit_date_is_run_date"])
        self.assertIn("raised_limits", record["limits_in_force"])
        stamps = [k for k in record if k.endswith("_version")]
        self.assertTrue(stamps)
        self.assertIn("score_ruleset_version", record["score"])
        self.assertEqual(len(record["checks"]), 10)
        self.assertIsNotNone(record["robots_summary"])

    def test_audit_run_robots_summary_null_only_where_no_file(self):
        """Pins AuditRun assembly robots limb. Oracle: plan Section 5.1
        AuditRun: robots_summary is null only where no robots file is
        supplied, and a rejected supplied file fails the whole audit."""
        _, _, home = make_home(self)
        seed_product(self, home)
        record = service.audit(
            home=str(home), page_file=str(PAGE), audit_date=AUDIT_DATE)
        self.assertIsNone(record["robots_summary"])


class TestBoundaryChecks(unittest.TestCase):
    """Row S10 boundary checks 1 to 4. Oracle: brief Section 5.4."""

    def package_files(self):
        root = Path(citeline.__file__).parent
        return [p for p in root.rglob("*.py") if p.is_file()]

    def test_check1_no_shell_file_contains_a_listed_rule(self):
        """Pins boundary check 1. Oracle: brief Section 5.4 check 1, the
        source scan over the printed rule identifier list."""
        shell_files = [p for p in self.package_files()
                       if "shell" in p.name or p.parent.name == "shell"]
        self.assertTrue(shell_files)
        for path in shell_files:
            text = path.read_text(encoding="utf-8")
            for identifier in RULE_IDENTIFIERS:
                self.assertNotIn(identifier, text, f"{path}: {identifier}")

    def test_check1_no_service_file_imports_a_shell_module(self):
        """Pins boundary check 1, second limb. Oracle: brief Section 5.4
        check 1: no file implementing a service layer operation imports
        a shell module."""
        for path in self.package_files():
            if "shell" in path.name:
                continue
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("import shell", text, str(path))
            self.assertNotIn("from citeline import shell", text, str(path))
            self.assertNotIn("from citeline.shell", text, str(path))

    def test_check2_shell_call_adds_no_shell_specific_field(self):
        """Pins boundary check 2. Oracle: brief Section 5.4 check 2:
        records called from the shell validate against the Section 5.2
        shape with no shell specific field added."""
        _, _, home = make_home(self)
        seed_product(self, home)
        direct = service.status(home=str(home))
        via_shell = shell.format_record(direct, form="advanced")
        self.assertEqual(set(direct), set(via_shell))
        for field in ("head_hash", "entry_count", "home_size",
                      "home_path", "capacity_outlook"):
            self.assertIn(field, via_shell)
        verify = service.verify(home=str(home))
        via_shell_verify = shell.format_record(verify, form="advanced")
        self.assertEqual(set(verify), set(via_shell_verify))
        self.assertIn("chain_result", via_shell_verify)
        record = service.audit(
            home=str(home), page_file=str(PAGE), robots_file=str(ROBOTS),
            audit_date=AUDIT_DATE)
        via_shell_audit = shell.format_record(record, form="advanced")
        self.assertEqual(set(record), set(via_shell_audit))
        for field in ("run_id", "product_id", "snapshot_id",
                      "evaluated_page_path", "path_defaulted",
                      "snapshot_format", "checks", "score",
                      "robots_summary", "audit_date"):
            self.assertIn(field, via_shell_audit)

    def test_check3_direct_service_call_same_home_byte_identity(self):
        """Pins boundary check 3, same home scope. Oracle: brief Section
        5.4 check 3 and contract C8 severed form at plan Part B B5: a
        harness calling the service layer directly produces the same
        records byte for byte for the JSON reports named in the
        determinism contract, same home re render scope only."""
        _, _, home = make_home(self)
        seed_product(self, home)
        first = service.probe_report(
            home=str(home), product="Example Product", round="round-1",
            form="advanced", audit_date=AUDIT_DATE)
        second = service.probe_report(
            home=str(home), product="Example Product", round="round-1",
            form="advanced", audit_date=AUDIT_DATE)
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))

    def test_check3_cross_home_non_identifier_content_identifiers_excluded(self):
        """Pins boundary check 3, identifiers excluded scope. Oracle:
        plan Part B B5 proceeding tests: non identifier content across
        homes pins now. Byte identity including identifiers across
        homes stands blocked and is not asserted here."""
        _, _, home_a = make_home(self)
        _, _, home_b = make_home(self)
        seed_product(self, home_a)
        seed_product(self, home_b)
        a = service.audit(home=str(home_a), page_file=str(PAGE),
                          audit_date=AUDIT_DATE)
        b = service.audit(home=str(home_b), page_file=str(PAGE),
                          audit_date=AUDIT_DATE)
        for field in ("run_id", "snapshot_id", "answer_id"):
            a.pop(field, None)
            b.pop(field, None)
        self.assertEqual(a, b)

    def test_check4_version1_shell_holds_no_listed_rule(self):
        """Pins boundary check 4, version 1 form. Oracle: brief Section
        5.4 check 4: the version 1 shell itself holds no rule under the
        check 1 identifier list."""
        shell_files = [p for p in self.package_files()
                       if "shell" in p.name or p.parent.name == "shell"]
        self.assertTrue(shell_files)
        combined = "\n".join(p.read_text(encoding="utf-8")
                             for p in shell_files)
        for identifier in RULE_IDENTIFIERS:
            self.assertNotIn(identifier, combined)


class TestInvocationSurface(unittest.TestCase):
    """Row S10 invocation surface conformance. Oracle: brief Section
    5.12 surface, plan trade T-10 for the watch subcommand."""

    SUBCOMMANDS = [
        "add-product", "set-canonical-line", "set-competitors",
        "set-aliases", "set-query-set", "set-category", "register-page",
        "name-round", "audit", "robots", "robots-preview",
        "probe import", "probe report", "probe trend",
        "query-set-report", "guide", "verify", "status", "help", "watch",
    ]

    def test_help_lists_every_subcommand_including_watch(self):
        """Pins invocation surface conformance. Oracle: brief Section
        5.12: a help output reproduces the subcommand list in full;
        plan Section 1.3 S10 extends the surface to the watch
        subcommand on trade T-10 terms."""
        out = shell.help_text()
        for name in self.SUBCOMMANDS:
            self.assertIn(name, out)
        for required in ("page_file", "robots_file"):
            self.assertIn(required, out)
        for required in ("product", "round_label",
                         "importer_declaration", "supplier_relation"):
            self.assertIn(required, out)

    def test_help_shows_install_and_uninstall_invocation_forms(self):
        """Pins invocation surface conformance, install limb. Oracle:
        brief Section 5.12: the list shows install and uninstall as
        install.py invocations, not as citeline subcommands."""
        out = shell.help_text()
        self.assertIn("install.py", out)
        self.assertIn("uninstall", out)

    def test_positional_argument_beyond_subcommand_is_usage_error(self):
        """Pins named flags rule. Oracle: plan Section 1.3 S10: named
        flags for every input, no positional arguments beyond the
        subcommand. A positional argument returns the usage code 2."""
        code = shell.main(["status", "extra-positional"])
        self.assertEqual(code, 2)

    def test_named_flag_call_accepted(self):
        """Pins named flags rule, positive limb. Oracle: brief Section
        5.12: every call carries its inputs as named inputs."""
        _, _, home = make_home(self)
        code = shell.main(["status", "--home", str(home)])
        self.assertEqual(code, 0)

    def test_watch_subcommand_takes_named_flags_only(self):
        """Pins invocation surface conformance for watch. Oracle: plan
        Section 1.3 S10, extended to cover the watch subcommand on
        trade T-10 terms: named flags for every input and no
        positional argument beyond the subcommand."""
        code = shell.main(["watch", "some-plan-file.json"])
        self.assertEqual(code, 2)

    def test_unknown_subcommand_is_usage_error(self):
        """Pins invocation surface malformed call limb. Oracle: brief
        Section 5.12: a call naming no subcommand in the list carries
        the malformed call value in the usage class, code 2."""
        self.assertEqual(shell.main(["no-such-subcommand"]), 2)

    def test_form_outside_three_values_is_usage_error(self):
        """Pins invocation surface form limb. Oracle: brief Section
        5.12: a form input outside simple, advanced, and agentic
        carries the malformed call value, code 2."""
        _, _, home = make_home(self)
        code = shell.main(
            ["status", "--home", str(home), "--form", "verbose"])
        self.assertEqual(code, 2)


class TestExitBehaviour(unittest.TestCase):
    """Row S10 exit behaviour. Oracle: plan Part 1 Section 4 item 126
    exit code table and its per operation reading at subsection 4.2."""

    def test_code_4_returned_by_no_version1_invocation(self):
        """Pins item 126 table row for code 4. Oracle: plan Section 4.1:
        code 4 stands for the gate check and is not returned by any
        version 1 product invocation."""
        _, _, home = make_home(self)
        codes = {
            shell.main(["status", "--home", str(home)]),
            shell.main(["verify", "--home", str(home)]),
            shell.main(["no-such-subcommand"]),
            shell.main(["status", "extra-positional"]),
        }
        self.assertNotIn(4, codes)

    def test_code_1_never_returned_by_the_product(self):
        """Pins item 126 table row for code 1. Oracle: plan Section
        4.1: value 1 stands unassigned as a product outcome and is
        never returned by the product itself in version 1."""
        _, _, home = make_home(self)
        codes = {
            shell.main(["status", "--home", str(home)]),
            shell.main(["verify", "--home", str(home)]),
            shell.main(["help"]),
        }
        self.assertNotIn(1, codes)
        self.assertTrue(codes <= {0, 2, 3, 5})

    def test_no_code_outside_the_table_is_returned(self):
        """Pins item 126 completeness limb for this slice. Oracle: plan
        Section 4.2 head rule: a subcommand returns no code outside
        0 and the code of the class of the one error value reported,
        and none returns 4 or 1. No code is invented in this slice."""
        _, _, home = make_home(self)
        for argv in (["status", "--home", str(home)],
                     ["verify", "--home", str(home)],
                     ["help"], ["bogus"]):
            self.assertIn(shell.main(argv), (0, 2, 3, 5))

    def test_status_returns_0_in_every_case(self):
        """Pins item 126 per operation reading for status. Oracle: plan
        Section 4.2 status row: status returns 0 in every case, and
        over a journal that does not recompute its report states the
        chain failure in full."""
        _, _, home = make_home(self)
        self.assertEqual(shell.main(["status", "--home", str(home)]), 0)

    def test_status_returns_0_and_reports_chain_failure(self):
        """Pins item 126 status row, non recomputing journal limb.
        Oracle: plan Section 4.2 status row: status returns 0 in
        every case and its report states the chain failure and the
        failing position."""
        _, _, home = make_home(self)
        seed_product(self, home)
        journal_files = [p for p in home.rglob("*") if p.is_file()]
        target = max(journal_files, key=lambda p: p.stat().st_size)
        data = bytearray(target.read_bytes())
        data[-2] = data[-2] ^ 1
        target.write_bytes(bytes(data))
        self.assertEqual(shell.main(["status", "--home", str(home)]), 0)
        report = service.status(home=str(home))
        text = json.dumps(report).lower()
        self.assertIn("chain", text)
        self.assertIn("fail", text)
        self.assertTrue(any(
            k in report for k in ("failing_position", "failure_position",
                                  "position")) or "position" in text)

    def test_verify_missing_home_returns_2(self):
        """Pins item 126 per operation reading for verify. Oracle:
        plan Section 4.2 verify row: code 2 on row U-6 where the
        home is missing."""
        with __import__("tempfile").TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "no-home")
            self.assertEqual(
                shell.main(["verify", "--home", missing]), 2)

    def test_verify_chain_failure_returns_5(self):
        """Pins item 126 per operation reading for verify. Oracle:
        plan Section 4.2 verify row: code 5 where a home stands and
        its chain fails verify, on row I-2."""
        _, _, home = make_home(self)
        seed_product(self, home)
        journal_files = [p for p in home.rglob("*") if p.is_file()]
        self.assertTrue(journal_files)
        target = max(journal_files, key=lambda p: p.stat().st_size)
        data = bytearray(target.read_bytes())
        data[-2] = data[-2] ^ 1
        target.write_bytes(bytes(data))
        self.assertEqual(shell.main(["verify", "--home", str(home)]), 5)

    def test_name_round_twice_returns_3(self):
        """Pins item 126 name round row D-1. Oracle: plan Section
        4.2: naming a round twice for one product stands in the
        domain class and returns code 3."""
        _, _, home = make_home(self)
        seed_product(self, home)
        code = shell.main(
            ["name-round", "--home", str(home),
             "--product", "Example Product", "--round", "round-1",
             "--importer-declaration", "operator",
             "--supplier-relation", "first party"])
        self.assertEqual(code, 3)

    def test_guide_missing_product_returns_2(self):
        """Pins item 126 per operation reading for guide. Oracle: plan
        Section 4.2 guide row: code 2 on row U-1 for a missing
        product. The same row states that a guide refusal is a
        completed outcome carrying no error value and returns 0;
        no test here forces a refusal, because the refusal triggers
        stand on CL-16 ground at Part B entry B1, and that gap
        stands named in the writer paper."""
        _, _, home = make_home(self)
        code = shell.main(
            ["guide", "--home", str(home),
             "--product", "Example Product", "--round", "round-1"])
        self.assertEqual(code, 2)


class TestInstallUninstall(unittest.TestCase):
    """Row S10 install and uninstall. Oracle: brief Section 3.5
    created items list and install statement; plan Section 1.3 S10:
    operations over the created items list only, lstat driven, no
    removal through a link. The home contents fate beyond the
    created items list stands blocked and no test here decides it."""

    def setUp(self):
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.location = self.tmp / "citeline"
        self.home = self.tmp / "home"

    def install(self):
        return install_module.install(
            location=str(self.location), home=str(self.home))

    def uninstall(self):
        return install_module.uninstall(
            location=str(self.location), home=str(self.home))

    def test_install_creates_only_the_created_items_list(self):
        """Pins created items list completeness. Oracle: brief Section
        3.5: the install location directory and the product files in
        it, the install config file where the installer creates one,
        and the product home where none stands. No other item, and
        no command link."""
        self.install()
        self.assertTrue(self.location.is_dir())
        self.assertTrue((self.location / "citeline.py").is_file())
        self.assertTrue(self.home.is_dir())
        created = {p.name for p in self.tmp.iterdir()}
        self.assertEqual(created, {self.location.name, self.home.name})

    def test_install_creates_no_command_link(self):
        """Pins created items list, link limb. Oracle: brief Section
        3.5 and grill Q24: no command link is created."""
        self.install()
        for path in self.tmp.rglob("*"):
            self.assertFalse(path.is_symlink(), str(path))

    def test_pre_existing_config_left_untouched_and_reported(self):
        """Pins install config limb. Oracle: brief Section 3.5 point 5:
        an existing config file that parses is left untouched and is
        reported as pre-existing."""
        self.location.mkdir(parents=True)
        config = self.location / "config.txt"
        config.write_text("home = %s\n" % self.home, encoding="utf-8")
        before = config.read_bytes()
        result = self.install()
        self.assertEqual(config.read_bytes(), before)
        self.assertIn("config", str(result).lower())

    def test_pre_existing_product_file_refused_and_not_overwritten(self):
        """Pins planted file case. Oracle: brief Section 3.5: a pre
        existing file that is not Citeline's at the path of a product
        file is never overwritten; the install refuses with a
        recorded error."""
        self.location.mkdir(parents=True)
        planted = self.location / "citeline.py"
        planted.write_text("planted\n", encoding="utf-8")
        with self.assertRaises(Exception):
            self.install()
        self.assertEqual(planted.read_text(encoding="utf-8"), "planted\n")

    def test_install_location_standing_as_a_file_refused(self):
        """Pins planted file case at the location path. Oracle: brief
        Section 3.5: the same refusal states the outcome where the
        install location path itself stands as a file."""
        self.location.write_text("a file\n", encoding="utf-8")
        with self.assertRaises(Exception):
            install_module.install(
                location=str(self.location), home=str(self.home))
        self.assertEqual(
            self.location.read_text(encoding="utf-8"), "a file\n")

    def test_uninstall_removes_created_items_only(self):
        """Pins uninstall over the created items list. Oracle: brief
        Section 3.5: uninstall removes everything the installer
        created, and a config file the installer did not create is
        not removed."""
        self.install()
        self.uninstall()
        self.assertFalse((self.location / "citeline.py").exists())
        self.assertFalse(self.location.exists())
        self.assertFalse(self.home.exists())

    def test_uninstall_removes_installer_created_config(self):
        """Pins created items list, installer created config limb.
        Oracle: brief Section 3.5: where the installer creates the
        config file, uninstall removes it with the other created
        items."""
        self.install()
        config = self.location / "config.txt"
        self.assertTrue(config.is_file())
        self.uninstall()
        self.assertFalse(config.exists())
        self.assertFalse(self.location.exists())

    def test_uninstall_never_removes_through_a_link(self):
        """Pins planted link case. Oracle: plan Section 1.3 S10:
        lstat driven, no removal through a link. A created item path
        replaced by a link to an outside file leaves the outside
        file standing."""
        self.install()
        outside = self.tmp / "outside.txt"
        outside.write_text("outside\n", encoding="utf-8")
        link = self.location / "citeline.py"
        link.unlink()
        os.symlink(outside, link)
        self.uninstall()
        self.assertTrue(outside.exists())
        self.assertEqual(outside.read_text(encoding="utf-8"), "outside\n")
        self.assertFalse(os.path.lexists(link))
        self.assertFalse(link.is_symlink())

    def test_uninstall_leaves_a_config_it_did_not_create(self):
        """Pins uninstall, planted config limb. Oracle: brief Section
        3.5 point 5: a config file the installer did not create is
        not removed."""
        self.location.mkdir(parents=True)
        config = self.location / "config.txt"
        config.write_text("home = %s\n" % self.home, encoding="utf-8")
        self.install()
        self.uninstall()
        self.assertTrue(config.exists())

    def test_repeat_install_over_no_part_completes_the_list(self):
        """Pins part completed state: none present. Oracle: brief
        Section 3.5 resumability: a repeat install over a part
        completed install completes the created items list."""
        self.install()
        result = self.install()
        self.assertTrue((self.location / "citeline.py").is_file())
        self.assertTrue(self.home.is_dir())
        self.assertIsNotNone(result)

    def test_repeat_install_over_location_only_completes_the_list(self):
        """Pins part completed state: location directory only. Oracle:
        brief Section 3.5 resumability: the repeat call completes the
        list and does not treat partial creation as a whole."""
        self.location.mkdir(parents=True)
        self.install()
        self.assertTrue((self.location / "citeline.py").is_file())
        self.assertTrue(self.home.is_dir())

    def test_repeat_install_over_missing_product_file_reports_it(self):
        """Pins part completed state: one product file missing.
        Oracle: brief Section 3.5 resumability: a repeat install
        completes the list or reports each missing created item
        by name."""
        self.install()
        (self.location / "citeline.py").unlink()
        result = self.install()
        self.assertTrue((self.location / "citeline.py").is_file()
                        or "citeline.py" in str(result))

    def test_repeat_install_over_missing_home_recreates_home_only(self):
        """Pins part completed state: home absent, files present.
        Oracle: brief Section 3.5 created items list: the product
        home stands in the list only where none stands."""
        self.install()
        import shutil
        shutil.rmtree(self.home)
        self.install()
        self.assertTrue(self.home.is_dir())

    def test_repeat_uninstall_over_full_install_reports_completion(self):
        """Pins part completed state for uninstall: full list present.
        Oracle: brief Section 3.5 resumability: a repeat uninstall
        over a part completed uninstall removes what remains and
        reports completion against the created items list."""
        self.install()
        first = self.uninstall()
        second = self.uninstall()
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)

    def test_repeat_uninstall_over_partial_removal_completes(self):
        """Pins part completed state for uninstall: some items already
        removed. Oracle: brief Section 3.5 resumability rule."""
        self.install()
        (self.location / "citeline.py").unlink()
        result = self.uninstall()
        self.assertIsNotNone(result)
        self.assertFalse(self.home.exists())

    def test_repeat_uninstall_over_nothing_reports_completion(self):
        """Pins part completed state for uninstall: nothing present.
        Oracle: brief Section 3.5: install.py stands after a part
        completed uninstall, and a repeat uninstall is made by the
        same invocation."""
        result = self.uninstall()
        self.assertIsNotNone(result)

    def test_interrupted_install_then_uninstall_created_items_limb(self):
        """Pins interrupted install then uninstall, created items list
        limb only. Oracle: plan Section 1.3 S10 status: the case pins
        in its created items list limb. Its home contents limb stands
        blocked on L-MA-6 and is not asserted here."""
        self.location.mkdir(parents=True)
        partial = self.location / "citeline.py"
        partial.write_text("partial\n", encoding="utf-8")
        result = self.uninstall()
        self.assertIsNotNone(result)
        self.assertFalse(partial.exists())


class TestStatusCapacity(unittest.TestCase):
    """Row S10 status. Oracle: brief Section 5.5 status field list,
    brief Section 5.12 IM7-BRK-8 capacity outlook landing, and plan
    Section 1.3 S10 capacity outlook by entry kind."""

    def test_status_fields_present_in_every_form(self):
        """Pins status field list. Oracle: brief item 128: head hash
        or its absence form, entry count, home size, home path, and
        capacity outlook figures, in all three forms."""
        _, _, home = make_home(self)
        record = service.status(home=str(home))
        for form in ("simple", "advanced", "agentic"):
            out = shell.format_record(record, form=form)
            for field in ("head_hash", "entry_count", "home_size",
                          "home_path"):
                self.assertIn(field, out, form)

    def test_status_empty_home_shows_absence_form(self):
        """Pins status over an empty journal. Oracle: brief Section
        3.5 post install check and contract C7: status prints the
        stated absence form and verify passes over zero entries."""
        _, _, home = make_home(self)
        out = service.status(home=str(home))
        self.assertEqual(out["entry_count"], 0)
        self.assertIn("head_hash", out)

    def test_status_capacity_outlook_exact_figures(self):
        """Pins capacity outlook exact figures. Oracle: brief IM7-BRK-8
        landing: journal entries remaining under limit 39 and bytes
        remaining under limit 40, each exact."""
        _, _, home = make_home(self)
        out = service.status(home=str(home))
        outlook = out["capacity_outlook"]
        self.assertEqual(
            outlook["entries_remaining"] + out["entry_count"], 100000)
        self.assertEqual(outlook["bytes_remaining"],
                         1024 * 1024 * 1024 - out["home_size"])

    def test_status_capacity_outlook_attributes_by_entry_kind(self):
        """Pins capacity outlook by entry kind. Oracle: plan Section
        1.3 S10 and trade T-9: status attributes remaining capacity
        by entry kind, on IM2-BRK-18's outlook limb."""
        _, _, home = make_home(self)
        seed_product(self, home)
        service.audit(home=str(home), page_file=str(PAGE),
                      audit_date=AUDIT_DATE)
        out = service.status(home=str(home))
        outlook = out["capacity_outlook"]
        self.assertIn("by_entry_kind", outlook)
        kinds = outlook["by_entry_kind"]
        self.assertTrue(any("audit" in k for k in kinds))
        total = 0
        for kind, figures in kinds.items():
            if isinstance(figures, dict):
                self.assertIn("entries_remaining", figures)
                total += figures["entries_remaining"]
            else:
                total += figures
        self.assertEqual(total, outlook["entries_remaining"])

    def test_status_answers_estimate_labelled_and_absent_without_answers(self):
        """Pins capacity outlook estimate limb. Oracle: brief IM7-BRK-8
        landing: where the home holds no imported answer yet, no
        average stands and the outlook states that no average stands;
        the estimate is labelled an estimate wherever it prints."""
        _, _, home = make_home(self)
        outlook = service.status(home=str(home))["capacity_outlook"]
        text = json.dumps(outlook).lower()
        self.assertIn("no average", text)

    def test_status_last_verify_result_is_not_a_status_field(self):
        """Pins status field list exclusion. Oracle: brief item 128:
        the last verify result is not a status field."""
        _, _, home = make_home(self)
        out = service.status(home=str(home))
        self.assertNotIn("last_verify_result", out)


class TestServiceTimingScale(unittest.TestCase):
    """Row S10 timing. Oracle: plan Section 1.5 timing bounds: S10,
    one invocation's service layer work, install and status excluded,
    10 seconds, conditional on the scale stated in scales-w7.md."""

    def test_one_audit_invocation_within_bound_at_stated_scale(self):
        """Pins S10 timing bound at the scales-w7.md scale: one audit
        invocation over a home holding 25 registered products, one
        named round, the 154 byte page fixture, and the authored
        robots fixture w7-robots.txt at 23 bytes."""
        _, _, home = make_home(self)
        seed_product(self, home)
        for index in range(24):
            service.add_product(
                home=str(home), name="Extra Product %d" % index,
                canonical_line="Extra line.", domain="example.com",
                audit_date=AUDIT_DATE)
        start = time.monotonic()
        service.audit(home=str(home), page_file=str(PAGE),
                      robots_file=str(ROBOTS), audit_date=AUDIT_DATE)
        self.assertLess(time.monotonic() - start, 10.0)


if __name__ == "__main__":
    unittest.main()
