"""Slice S1 registry tests, Step 13, Citeline.

Written before the product exists. Every test imports the
product package citeline and calls the registry operations
on the service form the suite lands on in the Step 13 fix
wave (register entry R1-088): citeline.service, the home
passed as the keyword home, the brief's named inputs
including audit_date, and the product input carrying the
product name, as test_s10_service.py pins in its operation
signatures family. Import or attribute failure is the
expected red state. No stub and no mock of the product
stands in this file.

The slug form row of item 136 stands blocked in
blocked-w2.md at entry B-W2-9 (register entry R1-016): no
source names a registry surface carrying a slug value in,
so no slug test stands in this module.
"""

import hashlib
import os
import tempfile
import unittest

from citeline import acquisition, service

AUDIT_DATE = "2026-11-14"
PRODUCT = "Example Product"
CANONICAL = "The reference sentence that must match verbatim."


def field(record, name):
    if isinstance(record, dict):
        return record[name]
    return getattr(record, name)


def opt_field(record, name):
    if isinstance(record, dict):
        return record.get(name)
    return getattr(record, name, None)


def home_bytes(home):
    total = {}
    for root, _dirs, files in os.walk(home):
        for name in files:
            path = os.path.join(root, name)
            with open(path, "rb") as handle:
                total[os.path.relpath(path, home)] = hashlib.sha256(handle.read()).hexdigest()
    return total


def assert_token(case, caught, token):
    text = str(caught.exception)
    value = getattr(caught.exception, "error_value", None)
    alt = getattr(caught.exception, "token", None)
    case.assertTrue(token in text or value == token or alt == token,
                    "expected %s, got %r" % (token, caught.exception))


class RegistryBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "home")
        os.makedirs(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def add_default(self):
        return service.add_product(
            home=self.home,
            name=PRODUCT,
            canonical_line=CANONICAL,
            domain="example.invalid",
            audit_date=AUDIT_DATE,
        )


class TestSubcommandsAndNameRound(RegistryBase):
    def test_add_product_returns_product_shape(self):
        """Plan Section 1.3 S1, seven registry subcommands; plan Section 5.1 Product shape. Oracle: brief Section 5.12 item 136 and contract C6. The creation state of the remaining Product fields stands asserted under register entry R1-024: path_prefix absent, competitors, aliases, query_set, and category each empty at creation."""
        product = self.add_default()
        self.assertEqual(field(product, "name"), "Example Product")
        self.assertEqual(field(product, "domain"), "example.invalid")
        self.assertEqual(field(product, "canonical_line"), "The reference sentence that must match verbatim.")
        self.assertTrue(field(product, "product_id"))
        self.assertIsNone(opt_field(product, "path_prefix"))
        self.assertEqual(field(product, "competitors"), [])
        self.assertEqual(field(product, "aliases"), [])
        self.assertEqual(field(product, "query_set"), [])
        self.assertEqual(field(product, "category"), [])

    def test_set_canonical_line_changes_line(self):
        """Plan Section 1.3 S1, seven registry subcommands. Oracle: brief Section 5.12 item 136, set or change the canonical line subject to the 200 code point limit at grill Q11."""
        product = self.add_default()
        updated = service.set_canonical_line(home=self.home, product=PRODUCT, line="A new canonical line.", audit_date=AUDIT_DATE)
        self.assertEqual(field(updated, "canonical_line"), "A new canonical line.")

    def test_set_competitors_adds_competitor(self):
        """Plan Section 1.3 S1, seven registry subcommands. Oracle: brief Section 5.12 item 136, add or remove a competitor subject to Section 5.11 limits and the empty domain rule."""
        product = self.add_default()
        updated = service.set_competitors(home=self.home, product=PRODUCT, competitors=[{"name": "Rival", "domain": "rival.invalid", "aliases": []}], audit_date=AUDIT_DATE)
        self.assertEqual(len(field(updated, "competitors")), 1)
        self.assertEqual(field(field(updated, "competitors")[0], "name"), "Rival")

    def test_set_competitors_removes_competitor(self):
        """Plan Section 1.3 S1, seven registry subcommands, removal limb. Oracle: brief Section 5.12 item 136, add or remove a competitor. Register entry R1-021."""
        product = self.add_default()
        service.set_competitors(home=self.home, product=PRODUCT, competitors=[{"name": "Rival", "domain": "rival.invalid", "aliases": []}], audit_date=AUDIT_DATE)
        updated = service.set_competitors(home=self.home, product=PRODUCT, competitors=[], audit_date=AUDIT_DATE)
        self.assertEqual(field(updated, "competitors"), [])

    def test_set_aliases_adds_alias(self):
        """Plan Section 1.3 S1, seven registry subcommands. Oracle: brief Section 5.12 item 136, add or remove an alias subject to items 47 and 152."""
        product = self.add_default()
        updated = service.set_aliases(home=self.home, product=PRODUCT, aliases=["Example Prod"], audit_date=AUDIT_DATE)
        self.assertIn("Example Prod", field(updated, "aliases"))

    def test_set_aliases_removes_alias(self):
        """Plan Section 1.3 S1, seven registry subcommands, removal limb. Oracle: brief Section 5.12 item 136, add or remove an alias. Register entry R1-021."""
        product = self.add_default()
        service.set_aliases(home=self.home, product=PRODUCT, aliases=["Example Prod"], audit_date=AUDIT_DATE)
        updated = service.set_aliases(home=self.home, product=PRODUCT, aliases=[], audit_date=AUDIT_DATE)
        self.assertEqual(field(updated, "aliases"), [])

    def test_set_query_set_stores_queries(self):
        """Plan Section 1.3 S1, seven registry subcommands. Oracle: brief Section 5.12 item 136 and item 132, only a registry operation may add a query to a query set."""
        product = self.add_default()
        updated = service.set_query_set(home=self.home, product=PRODUCT, query_set=["what is example product"], audit_date=AUDIT_DATE)
        self.assertEqual(field(updated, "query_set"), ["what is example product"])

    def test_set_category_sets_terms(self):
        """Plan Section 1.3 S1, seven registry subcommands. Oracle: brief Section 5.12 item 136, set-category is the only operation that sets the category field."""
        product = self.add_default()
        updated = service.set_category(home=self.home, product=PRODUCT, category=["tools", "guides"], audit_date=AUDIT_DATE)
        self.assertEqual(field(updated, "category"), ["tools", "guides"])

    def test_set_category_empty_list_means_no_category(self):
        """Plan Section 5.1 Product shape, category. Oracle: brief Section 5.12 item 136, an empty list is no category, not a category of none."""
        product = self.add_default()
        updated = service.set_category(home=self.home, product=PRODUCT, category=[], audit_date=AUDIT_DATE)
        self.assertEqual(field(updated, "category"), [])

    def test_register_page_sets_is_product_page(self):
        """Plan Section 1.3 S1, sole writer discipline for is_product_page. Oracle: brief Section 5.12 item 136, register-page is the only operation that sets that field after creation. Superseded at Step 16 under defect D-03: the earlier form of this test registered the identifier snap-1 in a home where no snapshot stood and asserted only the returned flag, which asserted the defective behaviour D-03 cures. This form registers a standing snapshot created by extraction, on the governed behaviour, and asserts the full PageSnapshot shape stands on the returned record."""
        product = self.add_default()
        page = os.path.join(self.tmp.name, "page.txt")
        with open(page, "w", encoding="utf-8") as handle:
            handle.write("Body text stands here.\n")
        created = acquisition.extract_page(home=self.home, product_id=field(product, "product_id"), page_path=page, audit_date=AUDIT_DATE)
        created_snapshot = field(created, "snapshot")
        snapshot = service.register_page(home=self.home, product=PRODUCT, snapshot=field(created_snapshot, "snapshot_id"), audit_date=AUDIT_DATE)
        self.assertTrue(field(snapshot, "is_product_page"))
        self.assertEqual(field(snapshot, "supplied_path"), page)
        self.assertTrue(field(snapshot, "sha256"))
        self.assertTrue(field(snapshot, "format"))

    def test_register_page_second_snapshot_unregistered_until_registered(self):
        """Plan Section 1.3 S1, sole writer discipline for is_product_page, per snapshot limb. Oracle: brief Section 5.12 item 136, registration is per snapshot and must be repeated for each new snapshot of a product page. Register entry R1-024. The second snapshot stands created by extraction with is_product_page false, and stands unregistered until register page runs for it."""
        product = self.add_default()
        page = os.path.join(self.tmp.name, "page.txt")
        with open(page, "w", encoding="utf-8") as handle:
            handle.write("Body text stands here.\n")
        first = acquisition.extract_page(home=self.home, product_id=field(product, "product_id"), page_path=page, audit_date=AUDIT_DATE)
        first_snapshot = field(first, "snapshot")
        registered = service.register_page(home=self.home, product=PRODUCT, snapshot=field(first_snapshot, "snapshot_id"), audit_date=AUDIT_DATE)
        self.assertTrue(field(registered, "is_product_page"))
        second = acquisition.extract_page(home=self.home, product_id=field(product, "product_id"), page_path=page, audit_date=AUDIT_DATE)
        second_snapshot = field(second, "snapshot")
        self.assertNotEqual(field(second_snapshot, "snapshot_id"), field(first_snapshot, "snapshot_id"))
        self.assertFalse(field(second_snapshot, "is_product_page"))
        registered_second = service.register_page(home=self.home, product=PRODUCT, snapshot=field(second_snapshot, "snapshot_id"), audit_date=AUDIT_DATE)
        self.assertTrue(field(registered_second, "is_product_page"))

    def test_name_round_returns_round_shape(self):
        """Plan Section 1.3 S1, name round and Round identity and declaration fields. Oracle: contract C10 and brief Section 5.12 round naming operation in full. Both declaration values and created_by stand asserted under register entry R1-019."""
        product = self.add_default()
        named = service.name_round(home=self.home, product=PRODUCT, round_label="round-one", importer_declaration="all_captured", supplier_relation="independent", audit_date=AUDIT_DATE)
        self.assertEqual(field(named, "round_label"), "round-one")
        self.assertEqual(field(named, "product_id"), field(product, "product_id"))
        self.assertTrue(field(named, "round_id"))
        self.assertEqual(field(named, "importer_declaration"), "all_captured")
        self.assertEqual(field(named, "supplier_relation"), "independent")
        self.assertEqual(str(field(named, "created_by")).replace("-", "_"), "name_round")

    def test_name_round_stamps_null_before_import(self):
        """Plan Section 5.1 Round shape. Oracle: brief Section 5.2 Round fields, registry_version_at_first_import and detector_version_at_first_import or null before any import."""
        product = self.add_default()
        named = service.name_round(home=self.home, product=PRODUCT, round_label="round-one", importer_declaration="all_captured", supplier_relation="independent", audit_date=AUDIT_DATE)
        self.assertIsNone(field(named, "registry_version_at_first_import"))
        self.assertIsNone(field(named, "detector_version_at_first_import"))

    def test_name_round_duplicate_label_domain_error_home_bytes(self):
        """Plan Section 1.3 S1, Round identity. Oracle: brief Section 5.12 round naming error cases, a standing label for the product is a domain error, nothing is stored, rounds are never overwritten or renamed; plan entry 13 row D-1, token ROUND_LABEL_EXISTS, domain class, asserted expressly under register entry R1-017. The no write claim is a byte identity claim over the home files."""
        product = self.add_default()
        service.name_round(home=self.home, product=PRODUCT, round_label="round-one", importer_declaration="all_captured", supplier_relation="independent", audit_date=AUDIT_DATE)
        before = home_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            service.name_round(home=self.home, product=PRODUCT, round_label="round-one", importer_declaration="all_captured", supplier_relation="independent", audit_date=AUDIT_DATE)
        assert_token(self, caught, "ROUND_LABEL_EXISTS")
        self.assertEqual(home_bytes(self.home), before)

    def test_name_round_out_of_set_declaration_usage_error(self):
        """Plan Section 1.3 S1, Round declaration fields. Oracle: brief Section 5.12 round naming error cases, out of set field values are usage errors naming the allowed values; plan entry 13 row U-3, token ROUND_FIELD_OUT_OF_SET. Register entry R1-017: the message names each allowed importer declaration value in full, value by value."""
        product = self.add_default()
        with self.assertRaises(Exception) as caught:
            service.name_round(home=self.home, product=PRODUCT, round_label="round-one", importer_declaration="bogus_value", supplier_relation="independent", audit_date=AUDIT_DATE)
        assert_token(self, caught, "ROUND_FIELD_OUT_OF_SET")
        message = str(caught.exception)
        self.assertIn("all captured answers imported", message)
        self.assertIn("a stated subset imported", message)
        self.assertIn("selection rule unknown", message)

    def test_name_round_out_of_set_supplier_relation_usage_error(self):
        """Plan Section 1.3 S1, Round declaration fields, supplier relation limb. Oracle: brief Section 5.12 round naming error cases, out of set field values are usage errors naming the allowed values; plan entry 13 row U-3, token ROUND_FIELD_OUT_OF_SET. Register entries R1-019 and R1-017: the message names each allowed supplier relation value in full, value by value."""
        product = self.add_default()
        with self.assertRaises(Exception) as caught:
            service.name_round(home=self.home, product=PRODUCT, round_label="round-one", importer_declaration="all_captured", supplier_relation="bogus_value", audit_date=AUDIT_DATE)
        assert_token(self, caught, "ROUND_FIELD_OUT_OF_SET")
        message = str(caught.exception)
        self.assertIn("supplied by the audited party", message)
        self.assertIn("supplied by an independent party", message)
        self.assertIn("supplier relation unknown", message)

    def test_name_round_unknown_product_usage_error(self):
        """Plan Section 1.3 S1, Round identity. Oracle: brief Section 5.12 round naming error cases, an unknown product is a usage error naming the allowed values; plan entry 13 row U-1, token UNKNOWN_PRODUCT. Register entry R1-017: the message names the allowed value, the one standing product name, in full."""
        self.add_default()
        with self.assertRaises(Exception) as caught:
            service.name_round(home=self.home, product="no-such-product", round_label="round-one", importer_declaration="all_captured", supplier_relation="independent", audit_date=AUDIT_DATE)
        assert_token(self, caught, "UNKNOWN_PRODUCT")
        self.assertIn("Example Product", str(caught.exception))

    def test_registry_timing_bound(self):
        """Plan Section 1.5 timing bounds, S1. Oracle: registry operations over a test registry, 2 seconds, conditional on a test scale Step 13 states on the record. Scale stated here and in design/tests/scales-w2.md: one product, seven operations, one round. The body runs the stated scale under register entry R1-020: the seven registry operations and one round naming over the one product, inside the timed span."""
        import time
        start = time.monotonic()
        product = self.add_default()
        service.set_canonical_line(home=self.home, product=PRODUCT, line="A new canonical line.", audit_date=AUDIT_DATE)
        service.set_competitors(home=self.home, product=PRODUCT, competitors=[{"name": "Rival", "domain": "rival.invalid", "aliases": []}], audit_date=AUDIT_DATE)
        service.set_aliases(home=self.home, product=PRODUCT, aliases=["Example Prod"], audit_date=AUDIT_DATE)
        service.set_query_set(home=self.home, product=PRODUCT, query_set=["what is example product"], audit_date=AUDIT_DATE)
        service.set_category(home=self.home, product=PRODUCT, category=["tools", "guides"], audit_date=AUDIT_DATE)
        page = os.path.join(self.tmp.name, "timing-page.txt")
        with open(page, "w", encoding="utf-8") as handle:
            handle.write("Body text stands here.\n")
        created = acquisition.extract_page(home=self.home, product_id=field(product, "product_id"), page_path=page, audit_date=AUDIT_DATE)
        service.register_page(home=self.home, product=PRODUCT, snapshot=field(field(created, "snapshot"), "snapshot_id"), audit_date=AUDIT_DATE)
        service.name_round(home=self.home, product=PRODUCT, round_label="round-one", importer_declaration="all_captured", supplier_relation="independent", audit_date=AUDIT_DATE)
        self.assertLess(time.monotonic() - start, 2.0)


class TestValidationForms(RegistryBase):
    """Validation rejection form, plan entry 13 row X-5, token
    VALIDATION_FAILED, usage class. Every rejection test in
    this class carries the same assertions under register
    entries R1-017 and R1-018: the token on the raised error,
    which is the recorded error limb at the strength the
    chain state in the test allows, and the home bytes
    standing identical after the refused call, a byte
    identity claim over the home files, for the write limb.
    The slug form tests stand withdrawn under register entry
    R1-016 and the slug row stands blocked at B-W2-9."""

    def test_name_empty_rejected_home_bytes(self):
        """Plan Section 1.3 S1, validation forms. Oracle: brief Section 5.12 item 136, a name is 1 to 200 code points with no control characters; row X-5."""
        before = home_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            service.add_product(home=self.home, name="", canonical_line="Line.", domain="example.invalid", audit_date=AUDIT_DATE)
        assert_token(self, caught, "VALIDATION_FAILED")
        self.assertEqual(home_bytes(self.home), before)

    def test_name_over_200_rejected_home_bytes(self):
        """Plan Section 1.3 S1, validation forms. Oracle: brief Section 5.12 item 136, a name is 1 to 200 code points; brief Section 5.11 limit 28, product name length 200 code points; row X-5."""
        before = home_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            service.add_product(home=self.home, name="x" * 201, canonical_line="Line.", domain="example.invalid", audit_date=AUDIT_DATE)
        assert_token(self, caught, "VALIDATION_FAILED")
        self.assertEqual(home_bytes(self.home), before)

    def test_name_control_character_rejected_home_bytes(self):
        """Plan Section 1.3 S1, validation forms. Oracle: brief Section 5.12 item 136, a name carries no control characters; row X-5."""
        before = home_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            service.add_product(home=self.home, name="Bad\x01Name", canonical_line="Line.", domain="example.invalid", audit_date=AUDIT_DATE)
        assert_token(self, caught, "VALIDATION_FAILED")
        self.assertEqual(home_bytes(self.home), before)

    def test_name_exactly_200_code_points_accepted(self):
        """Plan Section 1.3 S1, validation forms, boundary limb. Oracle: brief Section 5.12 item 136, a name is 1 to 200 code points, so a name of exactly 200 code points stands accepted. Register entry R1-022."""
        product = service.add_product(home=self.home, name="x" * 200, canonical_line="Line.", domain="example.invalid", audit_date=AUDIT_DATE)
        self.assertEqual(field(product, "name"), "x" * 200)
        self.assertTrue(field(product, "product_id"))

    def test_canonical_line_over_200_rejected_home_bytes(self):
        """Plan Section 1.3 S1, validation forms. Oracle: brief Section 5.12 item 136 with grill Q11, the canonical line stands subject to the 200 code point limit; row X-5."""
        before = home_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            service.add_product(home=self.home, name="Long Line", canonical_line="y" * 201, domain="example.invalid", audit_date=AUDIT_DATE)
        assert_token(self, caught, "VALIDATION_FAILED")
        self.assertEqual(home_bytes(self.home), before)

    def test_set_canonical_line_over_200_rejected_home_bytes(self):
        """Plan Section 1.3 S1, validation forms, set-canonical-line limb. Oracle: brief Section 5.12 item 136, set or change the canonical line subject to the 200 code point limit at grill Q11; row X-5. Register entry R1-022."""
        self.add_default()
        before = home_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            service.set_canonical_line(home=self.home, product=PRODUCT, line="y" * 201, audit_date=AUDIT_DATE)
        assert_token(self, caught, "VALIDATION_FAILED")
        self.assertEqual(home_bytes(self.home), before)

    def test_alias_too_short_rejected_home_bytes(self):
        """Plan Section 1.3 S1, validation forms. Oracle: brief Section 5.12 item 136 with item 47, an alias is 3 characters or more; row X-5."""
        product = self.add_default()
        before = home_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            service.set_aliases(home=self.home, product=PRODUCT, aliases=["ab"], audit_date=AUDIT_DATE)
        assert_token(self, caught, "VALIDATION_FAILED")
        self.assertEqual(home_bytes(self.home), before)

    def test_alias_zero_width_rejected_home_bytes(self):
        """Plan Section 1.3 S1, validation forms. Oracle: brief Section 5.12 item 136 with item 152, an alias carries no zero width character; plan entry 13 row X-5 names this case expressly."""
        product = self.add_default()
        before = home_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            service.set_aliases(home=self.home, product=PRODUCT, aliases=["abc\u200bdef"], audit_date=AUDIT_DATE)
        assert_token(self, caught, "VALIDATION_FAILED")
        self.assertEqual(home_bytes(self.home), before)

    def test_domain_with_scheme_rejected_home_bytes(self):
        """Plan Section 1.3 S1, validation forms. Oracle: plan Section 5.1 Product domain, registry domain form item 50, host, no scheme, no port, no path, no trailing dot; row X-5."""
        before = home_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            service.add_product(home=self.home, name="Scheme Host", canonical_line="Line.", domain="https://example.invalid", audit_date=AUDIT_DATE)
        assert_token(self, caught, "VALIDATION_FAILED")
        self.assertEqual(home_bytes(self.home), before)

    def test_domain_with_port_rejected_home_bytes(self):
        """Plan Section 1.3 S1, validation forms. Oracle: plan Section 5.1 Product domain, item 50, no port; row X-5."""
        before = home_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            service.add_product(home=self.home, name="Port Host", canonical_line="Line.", domain="example.invalid:8080", audit_date=AUDIT_DATE)
        assert_token(self, caught, "VALIDATION_FAILED")
        self.assertEqual(home_bytes(self.home), before)

    def test_domain_with_path_rejected_home_bytes(self):
        """Plan Section 1.3 S1, validation forms, path limb. Oracle: plan Section 5.1 Product domain, registry domain form item 50, host, no path; row X-5. Register entry R1-022."""
        before = home_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            service.add_product(home=self.home, name="Path Host", canonical_line="Line.", domain="example.invalid/some/path", audit_date=AUDIT_DATE)
        assert_token(self, caught, "VALIDATION_FAILED")
        self.assertEqual(home_bytes(self.home), before)

    def test_domain_trailing_dot_rejected_home_bytes(self):
        """Plan Section 1.3 S1, validation forms. Oracle: plan Section 5.1 Product domain, item 50, no trailing dot; row X-5."""
        before = home_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            service.add_product(home=self.home, name="Dot Host", canonical_line="Line.", domain="example.invalid.", audit_date=AUDIT_DATE)
        assert_token(self, caught, "VALIDATION_FAILED")
        self.assertEqual(home_bytes(self.home), before)

    def test_set_category_invalid_term_rejected_home_bytes(self):
        """Plan Section 1.3 S1, validation forms, category term limb. Oracle: brief Section 5.2 Product shape, each category term is validated as a name string of 1 to 200 code points with no control characters; row X-5. Register entry R1-022."""
        self.add_default()
        before = home_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            service.set_category(home=self.home, product=PRODUCT, category=["bad\x01term"], audit_date=AUDIT_DATE)
        assert_token(self, caught, "VALIDATION_FAILED")
        self.assertEqual(home_bytes(self.home), before)

    def test_competitor_empty_domain_allowed(self):
        """Plan Section 5.1 Competitor shape. Oracle: brief Section 5.12 item 136 with Section 5.8 empty domain rule, a competitor domain may be empty and detection runs on name and aliases."""
        product = self.add_default()
        updated = service.set_competitors(home=self.home, product=PRODUCT, competitors=[{"name": "No Domain Rival", "domain": "", "aliases": []}], audit_date=AUDIT_DATE)
        self.assertEqual(field(field(updated, "competitors")[0], "domain"), "")


class TestReAddIdempotence(RegistryBase):
    def test_readd_no_change_returns_unchanged(self):
        """Plan Section 1.3 S1, re add idempotence. Oracle: contract C6 and brief Section 5.12 item 136, re-adding a product with no change returns the product unchanged. The returned product stands compared field by field against the standing product, on the registry re add route the register charges at R1-004 for this slice."""
        first = self.add_default()
        second = self.add_default()
        for name in ("name", "domain", "canonical_line", "product_id",
                     "competitors", "aliases", "query_set", "category"):
            self.assertEqual(field(first, name), field(second, name), name)
        self.assertIsNone(opt_field(second, "path_prefix"))

    def test_readd_no_change_writes_nothing_home_bytes(self):
        """Plan Section 1.3 S1, re add idempotence, no write and no version advance. Oracle: contract C6, re adding with no change writes nothing and does not advance the registry version. Pinned here by the home bytes standing identical across the re add, a byte identity claim over the home files."""
        self.add_default()
        before = home_bytes(self.home)
        self.add_default()
        self.assertEqual(home_bytes(self.home), before)

    def test_readd_with_change_is_usage_error_home_bytes(self):
        """Plan Section 1.3 S1, re add idempotence. Oracle: brief Section 5.12 item 136 and plan entry 13 row U-2, token PRODUCT_READD_CHANGED, re-adding a product with any change is a usage error naming the allowed values, and nothing is written. Register entry R1-017: the message names the allowed values in full, the standing product name, canonical line, and domain a re add must match, value by value. The no write claim is a byte identity claim over the home files."""
        self.add_default()
        before = home_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            service.add_product(home=self.home, name="Example Product", canonical_line="A different line.", domain="example.invalid", audit_date=AUDIT_DATE)
        assert_token(self, caught, "PRODUCT_READD_CHANGED")
        message = str(caught.exception)
        self.assertIn("Example Product", message)
        self.assertIn("The reference sentence that must match verbatim.", message)
        self.assertIn("example.invalid", message)
        self.assertEqual(home_bytes(self.home), before)

    def test_unknown_product_operation_writes_nothing_home_bytes(self):
        """Plan Section 1.3 S1, registry subcommands. Oracle: brief Section 5.12 item 136, unknown product outcome stated once for every registry operation that names a product, a usage error naming the allowed values, and the operation writes nothing; row U-1, token UNKNOWN_PRODUCT. Register entry R1-017: the message names the allowed value, the one standing product name, in full. The no write claim is a byte identity claim over the home files."""
        self.add_default()
        before = home_bytes(self.home)
        with self.assertRaises(Exception) as caught:
            service.set_aliases(home=self.home, product="no-such-product", aliases=["Some Alias"], audit_date=AUDIT_DATE)
        assert_token(self, caught, "UNKNOWN_PRODUCT")
        self.assertIn("Example Product", str(caught.exception))
        self.assertEqual(home_bytes(self.home), before)


if __name__ == "__main__":
    unittest.main()
