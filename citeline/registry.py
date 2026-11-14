"""Registry operations for Citeline, slice S1.

Perspective: what a thing is gets decided once, at the
boundary, and never re-decided downstream. This module is
that boundary for products, competitors, and rounds. It
validates every incoming form once, derives identity
once, and writes the resulting record once, through the
journal slice only (contract 2 and contract C6). Later
slices read the records this module wrote; they do not
re-derive identity or re-validate forms.

Shapes stand at plan Section 5.1: Product, Competitor,
and Round. Journal kinds written here are
product_registered, registry_change, round_named, and
the is_product_page limb of snapshot_registered, for
which this slice is sole writer after creation.

Dates are call inputs (the audit_date argument), never
clock reads.
"""

import contextlib
import copy
import fcntl
import os
import re
import unicodedata


__all__ = [
    "RegistryError",
    "add_product",
    "set_canonical_line",
    "set_competitors",
    "set_aliases",
    "set_query_set",
    "set_category",
    "register_page",
    "name_round",
    "get_product",
    "list_products",
    "find_product",
    "validate_name",
    "validate_domain",
    "validate_alias",
    "validate_slug",
    "product_id_for_name",
    "competitor_id_for_name",
    "round_id_for",
    "IMPORTER_DECLARATIONS",
    "SUPPLIER_RELATIONS",
]


# ----------------------------------------------------------------
# Errors: one value per call, from the closed entry 13 vocabulary.
# ----------------------------------------------------------------

_TOKEN_ROWS = {
    "UNKNOWN_PRODUCT": ("U-1", "usage", 2),
    "PRODUCT_READD_CHANGED": ("U-2", "usage", 2),
    "ROUND_FIELD_OUT_OF_SET": ("U-3", "usage", 2),
    "ROUND_LABEL_EXISTS": ("D-1", "domain", 3),
    "VALIDATION_FAILED": ("X-5", "usage", 2),
    "LIMIT_EXCEEDED": ("X-3", "integrity", 5),
}


try:
    from citeline.errors import CitelineError as _BaseError
except Exception:
    _BaseError = Exception


class RegistryError(_BaseError):
    """A registry refusal carrying its entry 13 token."""

    def __init__(self, token, message):
        row, precedence_class, exit_code = _TOKEN_ROWS.get(
            token, ("X-5", "usage", 2))
        self.precedence_class = precedence_class
        self.error_class = precedence_class
        if _BaseError is Exception:
            self.token = token
            self.error_value = token
            self.row = row
            self.exit_code = exit_code
            super().__init__("%s: %s" % (token, message))
        else:
            super().__init__("%s: %s" % (token, message),
                             row=row, token=token, exit_code=exit_code)


def _fail(token, message):
    raise RegistryError(token, message)


# ----------------------------------------------------------------
# Journal access (slice S0). This module writes only through
# the journal operations the plan states: append_entry as the
# append operation, fold, fold_registry, and read_entry.
# ----------------------------------------------------------------

def _journal():
    try:
        from citeline import journal
    except Exception as exc:
        raise RegistryError(
            "VALIDATION_FAILED",
            "journal module is not available: %s" % (exc,))
    return journal


def _append(home, kind, payload, audit_date):
    journal = _journal()
    append = getattr(journal, "append_entry", None)
    if append is None:
        append = getattr(journal, "append", None)
    if append is None:
        raise RegistryError(
            "VALIDATION_FAILED",
            "journal module offers no append operation")
    try:
        return append(home, kind, payload, audit_date=audit_date)
    except TypeError:
        return append(home, kind, payload)


def _fold(home):
    journal = _journal()
    fold = getattr(journal, "fold", None)
    if fold is None:
        return []
    try:
        entries = fold(home)
    except TypeError:
        entries = fold(str(home))
    if entries is None:
        return []
    return list(entries)


def _fold_registry(home):
    """Return a dict of product_id to Product record.

    The journal fold_registry operation is the stated route.
    Where it yields a mapping, that mapping stands. Where it
    yields a list of records, the records are keyed here by
    their product_id, which is a reading of the fold only,
    not a second fold rule.
    """
    journal = _journal()
    fold_registry = getattr(journal, "fold_registry", None)
    state = None
    if fold_registry is not None:
        try:
            state = fold_registry(home)
        except TypeError:
            state = fold_registry(str(home))
    if isinstance(state, dict):
        return {key: _as_record(value) for key, value in state.items()}
    records = {}
    if isinstance(state, (list, tuple)):
        for value in state:
            record = _as_record(value)
            if record.get("product_id"):
                records[record["product_id"]] = record
        return records
    # Fallback reading over the plain fold, applying the plan
    # Section 5.2 rule: a registry_change payload carries the
    # full record as changed, applied at its sequence.
    for entry in _fold(home):
        kind = _get(entry, "entry_kind")
        if kind not in ("product_registered", "registry_change"):
            continue
        payload = _as_record(_get(entry, "payload", {}))
        product_id = payload.get("product_id")
        if product_id:
            records[product_id] = payload
    return records


@contextlib.contextmanager
def _registry_lock(home):
    """Serialise one registry read, edit, append cycle.

    Contract C6 states an atomic registry write. The
    journal write lock covers a single append only, so a
    setter that reads the standing record, edits its own
    copy, and appends the whole record can silently lose
    a concurrent update whose cycle overlaps its own.
    This advisory lock, on its own file inside the home,
    is held for the whole cycle, so a concurrent registry
    cycle waits and then reads the record the earlier
    cycle committed. The journal lock stands separate
    and is always taken after this one, never before it.
    """
    home_text = str(home)
    os.makedirs(home_text, exist_ok=True)
    handle = open(
        os.path.join(home_text, ".citeline-registry.lock"), "a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            handle.close()


def _as_record(value):
    if isinstance(value, dict):
        return copy.deepcopy(value)
    record = {}
    for name in ("product_id", "name", "canonical_line", "domain",
                 "path_prefix", "competitors", "aliases", "query_set",
                 "query_set_version", "category", "registry_version"):
        if hasattr(value, name):
            record[name] = copy.deepcopy(getattr(value, name))
    return record


def _get(record, name, default=None):
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


# ----------------------------------------------------------------
# Validation forms. Each form is decided here, once.
# ----------------------------------------------------------------

_ZERO_WIDTH = ("\u200b", "\u200c", "\u200d", "\u2060", "\ufeff")
_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _has_control(text):
    return any(unicodedata.category(ch) == "Cc" for ch in text)


def _has_surrogate(text):
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


def validate_name(value, what="name"):
    """A name is 1 to 200 code points, no control characters.

    Name text is normalised to Unicode NFC before case
    folding (brief item 151), and the normalised form is
    the form stored and the form identity is formed from,
    so one name in its two Unicode forms is one name at
    this boundary. A lone surrogate is not encodable text
    and fails validation here, in the closed vocabulary,
    rather than at journal encoding.
    """
    if not isinstance(value, str):
        _fail("VALIDATION_FAILED", "%s must be a string" % what)
    value = unicodedata.normalize("NFC", value)
    if len(value) < 1 or len(value) > 200:
        _fail("VALIDATION_FAILED",
              "%s must be 1 to 200 code points" % what)
    if _has_control(value):
        _fail("VALIDATION_FAILED",
              "%s must carry no control characters" % what)
    if _has_surrogate(value):
        _fail("VALIDATION_FAILED",
              "%s must carry no lone surrogate characters" % what)
    return value


def validate_slug(value, what="slug"):
    """A slug is lower case letters, digits, and single hyphens,
    beginning and ending with a letter or a digit."""
    if not isinstance(value, str) or not _SLUG_RE.match(value or ""):
        _fail("VALIDATION_FAILED",
              "%s must be a slug: lower case letters, digits, and "
              "single hyphens, beginning and ending with a letter "
              "or a digit" % what)
    return value


def validate_alias(value):
    """An alias is 3 characters or more, with no zero width
    character (items 47 and 152)."""
    if not isinstance(value, str):
        _fail("VALIDATION_FAILED", "alias must be a string")
    if len(value) < 3:
        _fail("VALIDATION_FAILED",
              "alias must be 3 characters or more")
    if any(mark in value for mark in _ZERO_WIDTH):
        _fail("VALIDATION_FAILED",
              "alias must carry no zero width character")
    if _has_control(value):
        _fail("VALIDATION_FAILED",
              "alias must carry no control characters")
    if _has_surrogate(value):
        _fail("VALIDATION_FAILED",
              "alias must carry no lone surrogate characters")
    return value


def _normalise_domain(value):
    """Item 42 host normalisation: NFC, case folded, compared
    in A-label form, lowercased. A trailing dot is not stripped
    here, because the registry domain form rejects it before
    normalisation; the caller validates the raw form first."""
    text = unicodedata.normalize("NFC", value).casefold()
    labels = text.split(".")
    out = []
    for label in labels:
        if not label:
            _fail("VALIDATION_FAILED", "domain holds an empty label")
        try:
            out.append(label.encode("idna").decode("ascii"))
        except (UnicodeError, ValueError):
            _fail("VALIDATION_FAILED",
                  "domain fails IDNA processing at label %r" % label)
    return ".".join(out).lower()


def validate_domain(value, allow_empty=False):
    """The registry domain form, item 50: a host, with no
    scheme, no port, no path, and no trailing dot, normalised
    under item 42. An empty domain stands only where the
    caller allows it, which is the competitor case."""
    if not isinstance(value, str):
        _fail("VALIDATION_FAILED", "domain must be a string")
    if value == "":
        if allow_empty:
            return ""
        _fail("VALIDATION_FAILED", "domain must not be empty")
    if "://" in value or "/" in value or "\\" in value:
        _fail("VALIDATION_FAILED",
              "domain must hold no scheme and no path")
    if ":" in value:
        _fail("VALIDATION_FAILED", "domain must hold no port")
    if value.endswith("."):
        _fail("VALIDATION_FAILED",
              "domain must hold no trailing dot")
    if value != value.strip() or " " in value or _has_control(value):
        _fail("VALIDATION_FAILED", "domain form is not a host string")
    # Item 149 dot separators map to a full stop before the
    # host form is judged, and name text stands in NFC, so a
    # decomposed accented label is judged in composed form.
    text = unicodedata.normalize("NFC", value)
    for separator in ("\u3002", "\uff0e", "\uff61"):
        text = text.replace(separator, ".")
    if text.endswith("."):
        _fail("VALIDATION_FAILED",
              "domain must hold no trailing dot")
    # A host label holds letters, digits, and hyphens only,
    # and neither begins nor ends with a hyphen (items 50
    # and 148). An invisible format character is refused,
    # never silently rewritten into a different domain.
    for label in text.split("."):
        if not label:
            _fail("VALIDATION_FAILED", "domain holds an empty label")
        if label.startswith("-") or label.endswith("-"):
            _fail("VALIDATION_FAILED",
                  "domain label must not begin or end with a hyphen")
        for ch in label:
            if unicodedata.category(ch) in ("Cf", "Cs"):
                _fail("VALIDATION_FAILED",
                      "domain must hold no invisible format "
                      "character")
            if not (ch.isalnum() or ch == "-"):
                _fail("VALIDATION_FAILED",
                      "domain label holds a character that is "
                      "not a host character: %r" % ch)
    return _normalise_domain(text)


def _validate_canonical_line(value):
    if not isinstance(value, str):
        _fail("VALIDATION_FAILED", "canonical line must be a string")
    if len(value) > 200:
        _fail("VALIDATION_FAILED",
              "canonical line must be at most 200 code points")
    if _has_surrogate(value):
        _fail("VALIDATION_FAILED",
              "canonical line must carry no lone surrogate "
              "characters")
    return value


_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "0123456789-._~")


def _syntax_normalise_path(value):
    """Item 40 limb (1) syntax normalisation on a path.

    A percent encoded triplet standing for an unreserved
    character is decoded to that character, a triplet for
    any other character stands encoded with upper case hex
    digits, and the percent decoding runs first. Dot
    segments are then removed: a single dot segment is
    dropped and a double dot segment removes the segment
    before it, a leading double dot segment with no
    segment before it being dropped. The path letter case
    stands as written.
    """
    out = []
    index = 0
    while index < len(value):
        ch = value[index]
        if ch == "%" and index + 2 < len(value) + 0 \
                and index + 2 <= len(value) - 1:
            pair = value[index + 1:index + 3]
            try:
                decoded = chr(int(pair, 16))
            except ValueError:
                decoded = None
            if decoded is not None:
                if decoded in _UNRESERVED:
                    out.append(decoded)
                else:
                    out.append("%" + pair.upper())
                index += 3
                continue
        out.append(ch)
        index += 1
    segments = []
    for segment in "".join(out).split("/"):
        if segment == ".":
            continue
        if segment == "..":
            # The stack leading entry is the empty segment
            # before the leading slash; a double dot with
            # only that before it is dropped.
            if len(segments) > 1:
                segments.pop()
            continue
        segments.append(segment)
    result = "/".join(segments)
    if not result.startswith("/"):
        result = "/" + result
    return result


def _validate_path_prefix(value):
    if value is None:
        return None
    if not isinstance(value, str) or value == "":
        _fail("VALIDATION_FAILED",
              "path prefix must be a path string beginning with a "
              "slash, and an empty prefix is defective input")
    if not value.startswith("/"):
        _fail("VALIDATION_FAILED",
              "path prefix must begin with a slash")
    if "://" in value or "?" in value or "#" in value:
        _fail("VALIDATION_FAILED",
              "path prefix must hold no scheme, no host, no query, "
              "and no fragment")
    if _has_control(value) or _has_surrogate(value):
        _fail("VALIDATION_FAILED",
              "path prefix must hold no control characters")
    value = _syntax_normalise_path(value)
    if value != "/" and value.endswith("/"):
        value = value.rstrip("/")
        if value == "":
            value = "/"
    return value


# ----------------------------------------------------------------
# Identity. Formed once, here, and never re-formed downstream.
# ----------------------------------------------------------------

def _slugify(text):
    text = unicodedata.normalize("NFC", str(text))
    slug = re.sub(r"[^a-z0-9]+", "-", text.casefold())
    return slug.strip("-")


def product_id_for_name(name):
    return "p-" + _slugify(name)


def competitor_id_for_name(name):
    return "c-" + _slugify(name)


def round_id_for(product_id, round_label):
    return "%s:%s" % (product_id, round_label)


# ----------------------------------------------------------------
# Record reading helpers.
# ----------------------------------------------------------------

def list_products(home):
    state = _fold_registry(home)
    return [state[key] for key in sorted(state)]


def find_product(home, product):
    """Resolve a product input to its standing record.

    A product input names a product by its name or by its
    product_id; both forms resolve to the one record the
    registry holds, decided here and nowhere else.
    """
    if product is None:
        return None
    wanted = str(product)
    state = _fold_registry(home)
    if wanted in state:
        return state[wanted]
    for record in state.values():
        if record.get("name") == wanted:
            return record
    return None


def get_product(home, product):
    return find_product(home, product)


def _unknown_product(home, product):
    names = sorted(
        str(record.get("name")) for record in _fold_registry(home).values()
        if record.get("name"))
    allowed = ", ".join(names) if names else "no standing product"
    _fail("UNKNOWN_PRODUCT",
          "unknown product %r; allowed values: %s" % (product, allowed))


def _require_product(home, product):
    record = find_product(home, product)
    if record is None:
        _unknown_product(home, product)
    return record


def _rounds(home):
    rounds = []
    for entry in _fold(home):
        if _get(entry, "entry_kind") == "round_named":
            payload = _as_record(_get(entry, "payload", {}))
            if payload:
                rounds.append(payload)
    return rounds


def _snapshots(home):
    snapshots = {}
    order = []
    for entry in _fold(home):
        if _get(entry, "entry_kind") != "snapshot_registered":
            continue
        payload = _get(entry, "payload", {})
        if isinstance(payload, str):
            record = {"snapshot_id": payload}
        else:
            record = _as_record(payload)
        snapshot_id = record.get("snapshot_id")
        if snapshot_id:
            if snapshot_id not in snapshots:
                order.append(snapshot_id)
            snapshots[snapshot_id] = record
    return [snapshots[key] for key in order]


# ----------------------------------------------------------------
# Competitor and list forms.
# ----------------------------------------------------------------

# Section 5.11 limits that bind registry lists.
_LIMIT_COMPETITORS = 100
_LIMIT_ALIASES = 100
_LIMIT_QUERIES = 1000


def _normalise_competitor(value, index=0):
    if isinstance(value, dict):
        name = value.get("name")
        domain = value.get("domain", "")
        aliases = value.get("aliases", [])
        competitor_id = value.get("competitor_id")
    else:
        name = getattr(value, "name", None)
        domain = getattr(value, "domain", "")
        aliases = getattr(value, "aliases", [])
        competitor_id = getattr(value, "competitor_id", None)
    name = validate_name(name, "competitor name")
    domain = validate_domain(domain, allow_empty=True)
    aliases = _validate_aliases(aliases)
    base = competitor_id_for_name(name)
    if not competitor_id:
        competitor_id = base
    elif competitor_id != base:
        _fail("VALIDATION_FAILED",
              "a stated competitor_id must match the identity "
              "formed from the competitor name")
    return {
        "competitor_id": competitor_id,
        "name": name,
        "domain": domain,
        "aliases": list(aliases),
    }


def _require_list(value, what):
    """A list valued input stands as a list or a tuple.

    Any other form, a plain string included, fails
    validation in the closed vocabulary: a string is
    never a list of its own characters, and a non list
    is never iterated into one.
    """
    if not isinstance(value, (list, tuple)):
        _fail("VALIDATION_FAILED", "%s must be a list" % what)
    return value


def _validate_aliases(aliases):
    if aliases is None:
        return []
    _require_list(aliases, "aliases")
    out = []
    for alias in aliases:
        validate_alias(alias)
        out.append(alias)
    if len(out) > _LIMIT_ALIASES:
        _fail("LIMIT_EXCEEDED",
              "aliases per product or per competitor limit is 100")
    return out


def _validate_query_set(query_set):
    if query_set is None:
        return []
    _require_list(query_set, "query_set")
    out = []
    for query in query_set:
        if not isinstance(query, str) or query == "":
            _fail("VALIDATION_FAILED", "a query must be a string")
        if len(query) > 2000:
            _fail("LIMIT_EXCEEDED", "query text length limit is 2000")
        out.append(query)
    if len(out) > _LIMIT_QUERIES:
        _fail("LIMIT_EXCEEDED", "queries per product limit is 1000")
    return out


def _validate_category(category):
    if category is None:
        return []
    _require_list(category, "category")
    out = []
    for term in category:
        out.append(validate_name(term, "category term"))
    return out


def _base_product(name, canonical_line, domain, competitors,
                  aliases, query_set, category, path_prefix):
    return {
        "product_id": product_id_for_name(name),
        "name": name,
        "canonical_line": canonical_line,
        "domain": domain,
        "path_prefix": path_prefix,
        "competitors": competitors,
        "aliases": aliases,
        "query_set": query_set,
        "query_set_version": 1,
        "category": category,
        "registry_version": 1,
    }


def _public_product(record):
    """The Product shape as returned: path_prefix stands absent
    where no prefix stands, on the Section 5.1 form."""
    out = copy.deepcopy(record)
    if out.get("path_prefix") is None:
        out.pop("path_prefix", None)
    return out


def _store_change(home, record, audit_date):
    record = copy.deepcopy(record)
    record["registry_version"] = int(record.get("registry_version", 1)) + 1
    _append(home, "registry_change", _payload_product(record), audit_date)
    return _public_product(record)


def _payload_product(record):
    payload = copy.deepcopy(record)
    if payload.get("path_prefix") is None:
        payload.pop("path_prefix", None)
    return payload


# ----------------------------------------------------------------
# The seven registry operations and round naming.
# ----------------------------------------------------------------

def add_product(home, name=None, canonical_line=None, domain=None,
                competitors=None, aliases=None, query_set=None,
                category=None, path_prefix=None, audit_date=None,
                **kwargs):
    """Add a product, idempotently, under contract C6.

    Re-adding with no change returns the standing product and
    writes nothing. Re-adding with any change is a usage
    error naming the allowed values, and writes nothing.
    Extra inputs the service form carries (category under
    either of its names, a stated product_id, a stated slug)
    are decided here: a stated slug must pass the slug form,
    and a stated product_id must match the identity this
    module forms from the name.

    A field the call does not state stands unstated, not
    stated as empty. The set operations own the competitors,
    aliases, query set, and category fields after creation,
    and set_category is the only operation that sets the
    category field, so an unstated field makes no change
    statement against a standing record those operations
    have set. A field the call does state is compared in
    full against the standing record, and any stated
    difference is a change this operation refuses.
    """
    if category is None:
        category = kwargs.get("category_terms", kwargs.get("category"))
    stated = {
        "competitors": competitors is not None,
        "aliases": aliases is not None,
        "query_set": query_set is not None,
        "category": category is not None,
        "path_prefix": path_prefix is not None,
    }
    name = validate_name(name, "name")
    if not _slugify(name):
        _fail("VALIDATION_FAILED",
              "a name that forms no slug forms no product "
              "identity: a slug begins and ends with a letter "
              "or a digit")
    _validate_canonical_line(canonical_line)
    domain = validate_domain(domain)
    path_prefix = _validate_path_prefix(path_prefix)
    if "slug" in kwargs and kwargs.get("slug") is not None:
        validate_slug(kwargs["slug"])
    if competitors is not None:
        _require_list(competitors, "competitors")
    competitor_records = []
    seen_ids = {}
    for index, competitor in enumerate(competitors or []):
        record = _normalise_competitor(competitor, index)
        base = record["competitor_id"]
        count = seen_ids.get(base, 0)
        if count:
            record["competitor_id"] = "%s-%d" % (base, count + 1)
        seen_ids[base] = count + 1
        competitor_records.append(record)
    if len(competitor_records) > _LIMIT_COMPETITORS:
        _fail("LIMIT_EXCEEDED", "competitors per product limit is 100")
    alias_list = _validate_aliases(aliases)
    query_list = _validate_query_set(query_set)
    category_list = _validate_category(category)

    candidate = _base_product(
        name, canonical_line, domain, competitor_records,
        alias_list, query_list, category_list, path_prefix)
    if kwargs.get("product_id"):
        if kwargs["product_id"] != candidate["product_id"]:
            _fail("VALIDATION_FAILED",
                  "a stated product_id must match the identity "
                  "formed from the product name")
    with _registry_lock(home):
        existing = find_product(home, name)
        if existing is None:
            # A standing record under the formed identity with a
            # different name is still a re-add case, not a new
            # product: identity is decided once.
            existing = find_product(home, candidate["product_id"])
        if existing is not None:
            same = (
                existing.get("name") == candidate["name"]
                and existing.get("canonical_line") == candidate["canonical_line"]
                and existing.get("domain") == candidate["domain"]
                and (not stated["competitors"]
                     or existing.get("competitors", [])
                     == candidate["competitors"])
                and (not stated["aliases"]
                     or existing.get("aliases", []) == candidate["aliases"])
                and (not stated["query_set"]
                     or existing.get("query_set", [])
                     == candidate["query_set"])
                and (not stated["category"]
                     or existing.get("category", []) == candidate["category"])
                and (not stated["path_prefix"]
                     or existing.get("path_prefix") == candidate["path_prefix"])
            )
            if same:
                return _public_product(existing)
            _fail(
                "PRODUCT_READD_CHANGED",
                "re-adding a product with any change is refused; "
                "allowed values: name %s, canonical_line %s, domain %s"
                % (existing.get("name"), existing.get("canonical_line"),
                   existing.get("domain")))
        _append(home, "product_registered", _payload_product(candidate),
                audit_date)
        return _public_product(candidate)


def set_canonical_line(home, product=None, line=None, audit_date=None,
                       **kwargs):
    if line is None:
        line = kwargs.get("canonical_line")
    _validate_canonical_line(line)
    if line is not None and len(line) > 200:
        _fail("VALIDATION_FAILED",
              "canonical line must be at most 200 code points")
    _require_product(home, product)
    with _registry_lock(home):
        record = _require_product(home, product)
        record["canonical_line"] = line
        return _store_change(home, record, audit_date)


def set_competitors(home, product=None, competitors=None,
                    audit_date=None, **kwargs):
    if competitors is None:
        competitors = kwargs.get("competitor_change", [])
    _require_list(competitors, "competitors")
    records = []
    seen_ids = {}
    for index, competitor in enumerate(competitors or []):
        record_in = _normalise_competitor(competitor, index)
        base = record_in["competitor_id"]
        count = seen_ids.get(base, 0)
        if count:
            record_in["competitor_id"] = "%s-%d" % (base, count + 1)
        seen_ids[base] = count + 1
        records.append(record_in)
    if len(records) > _LIMIT_COMPETITORS:
        _fail("LIMIT_EXCEEDED", "competitors per product limit is 100")
    _require_product(home, product)
    with _registry_lock(home):
        record = _require_product(home, product)
        record["competitors"] = records
        return _store_change(home, record, audit_date)


def set_aliases(home, product=None, aliases=None, audit_date=None,
                **kwargs):
    if aliases is None:
        aliases = kwargs.get("alias_change", [])
    alias_list = _validate_aliases(aliases)
    _require_product(home, product)
    with _registry_lock(home):
        record = _require_product(home, product)
        record["aliases"] = alias_list
        return _store_change(home, record, audit_date)


def set_query_set(home, product=None, query_set=None, audit_date=None,
                  **kwargs):
    query_list = _validate_query_set(query_set)
    _require_product(home, product)
    with _registry_lock(home):
        record = _require_product(home, product)
        record["query_set"] = query_list
        record["query_set_version"] = int(
            record.get("query_set_version", 1)) + 1
        return _store_change(home, record, audit_date)


def set_category(home, product=None, category=None, audit_date=None,
                 **kwargs):
    if category is None:
        category = kwargs.get("category_terms", kwargs.get("category_list"))
    category_list = _validate_category(category)
    _require_product(home, product)
    with _registry_lock(home):
        record = _require_product(home, product)
        record["category"] = category_list
        return _store_change(home, record, audit_date)


def _append_register_failure(home, token, subject, audit_date):
    """Append one failure record for a refused register page call.

    The joined entry 13 table orders a failure record for
    row X-5 where the chain accepts appends. A barred chain,
    a chain at cap, and any append failure leave no record,
    and the caller response stands as the only record, on
    the same terms the service layer applies to its failure
    records. This helper never raises.
    """
    journal = _journal()
    try:
        chain = journal.verify_chain(str(home))
        if not chain.get("passed"):
            return
    except Exception:
        return
    payload = {
        "operation": "register_page",
        "error_value": token,
        "subject_identity": str(subject),
        "date": audit_date,
        "rule_fired": token,
    }
    try:
        journal.append_entry(
            str(home), "failure_record", payload,
            audit_date=audit_date)
    except Exception:
        pass


def register_page(home, product=None, snapshot=None, audit_date=None,
                  **kwargs):
    """Set is_product_page for one snapshot of one product.

    This operation is sole writer of that field after
    creation, and registration is per snapshot. It appends
    a snapshot_registered entry carrying the snapshot record
    as changed, with is_product_page true.

    The snapshot input names a standing snapshot of this
    product by its snapshot_id, on brief Section 5.12. An
    identifier that names no standing snapshot for this
    product stands refused, and no snapshot record stands
    written for it: registration sets the field on the
    standing PageSnapshot record, and fabricates no record
    of its own. The refusal carries row X-5, token
    VALIDATION_FAILED, usage class, exit code 2, with a
    failure record appended where the chain accepts
    appends, as that joined row orders. No row of the
    joined table names an unknown snapshot as its own
    condition, and the closed vocabulary admits no new
    value, so the registry validation row governs this
    caller correctable identifier failure, as it already
    governs a missing snapshot identity in this operation.
    Both identifier failures of this operation, the missing
    or empty identity and the non-standing identity, append
    their failure record through the one helper above,
    before the refusal is raised.
    """
    if snapshot is None:
        snapshot = kwargs.get("snapshot_id")
    _require_product(home, product)
    with _registry_lock(home):
        record = _require_product(home, product)
        if isinstance(snapshot, dict):
            snapshot_id = snapshot.get("snapshot_id")
        else:
            snapshot_id = snapshot
        if not snapshot_id:
            _append_register_failure(
                home, "VALIDATION_FAILED", snapshot_id, audit_date)
            _fail("VALIDATION_FAILED", "a snapshot identity is required")
        standing = None
        for candidate in _snapshots(home):
            if candidate.get("snapshot_id") == snapshot_id \
                    and candidate.get("product_id") \
                    == record["product_id"]:
                standing = candidate
        if standing is None:
            allowed = ", ".join(sorted(
                str(candidate.get("snapshot_id"))
                for candidate in _snapshots(home)
                if candidate.get("product_id") == record["product_id"]
                and candidate.get("snapshot_id"))) or (
                    "no standing snapshot for this product")
            _append_register_failure(
                home, "VALIDATION_FAILED", snapshot_id, audit_date)
            _fail(
                "VALIDATION_FAILED",
                "unknown snapshot %r for product %s; allowed values: %s"
                % (snapshot_id, record.get("name"), allowed))
        base = copy.deepcopy(standing)
        base["snapshot_id"] = snapshot_id
        base["product_id"] = record["product_id"]
        base["is_product_page"] = True
        _append(home, "snapshot_registered", base, audit_date)
        return copy.deepcopy(base)


# Round declaration values. The plan Section 5.1 values stand
# in full phrase form. The Step 13 suite also carries code
# forms and short forms for the same three values of each
# field; the normalised key of every accepted form is decided
# here, once, and every accepted form of one value stands
# stored in the one canonical form for that value, in the
# canonical maps below.

IMPORTER_DECLARATION_TEXTS = (
    "all captured answers imported",
    "a stated subset imported",
    "selection rule unknown",
)

SUPPLIER_RELATION_TEXTS = (
    "supplied by the audited party",
    "supplied by an independent party",
    "supplier relation unknown",
)


def _normal_key(value):
    text = str(value).strip().casefold()
    text = re.sub(r"[\s\-]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


_IMPORTER_KEYS = {
    _normal_key(text): text for text in IMPORTER_DECLARATION_TEXTS
}
_IMPORTER_KEYS.update({
    "all_captured": IMPORTER_DECLARATION_TEXTS[0],
    "all_captured_answers_imported": IMPORTER_DECLARATION_TEXTS[0],
    "all_captured_answers": IMPORTER_DECLARATION_TEXTS[0],
    "all_answers_imported": IMPORTER_DECLARATION_TEXTS[0],
    "operator": IMPORTER_DECLARATION_TEXTS[0],
    "a_stated_subset_imported": IMPORTER_DECLARATION_TEXTS[1],
    "a_stated_subset": IMPORTER_DECLARATION_TEXTS[1],
    "stated_subset": IMPORTER_DECLARATION_TEXTS[1],
    "stated_subset_imported": IMPORTER_DECLARATION_TEXTS[1],
    "subset": IMPORTER_DECLARATION_TEXTS[1],
    "selection_rule_unknown": IMPORTER_DECLARATION_TEXTS[2],
    "unknown": IMPORTER_DECLARATION_TEXTS[2],
})

_SUPPLIER_KEYS = {
    _normal_key(text): text for text in SUPPLIER_RELATION_TEXTS
}
_SUPPLIER_KEYS.update({
    "supplied_by_the_audited_party": SUPPLIER_RELATION_TEXTS[0],
    "audited_party": SUPPLIER_RELATION_TEXTS[0],
    "audited": SUPPLIER_RELATION_TEXTS[0],
    "first_party": SUPPLIER_RELATION_TEXTS[0],
    "supplied_by_an_independent_party": SUPPLIER_RELATION_TEXTS[1],
    "independent_party": SUPPLIER_RELATION_TEXTS[1],
    "independent": SUPPLIER_RELATION_TEXTS[1],
    "third_party": SUPPLIER_RELATION_TEXTS[1],
    "supplier_relation_unknown": SUPPLIER_RELATION_TEXTS[2],
    "unknown": SUPPLIER_RELATION_TEXTS[2],
})

IMPORTER_DECLARATIONS = tuple(sorted(_IMPORTER_KEYS))
SUPPLIER_RELATIONS = tuple(sorted(_SUPPLIER_KEYS))

# The one stored form for each declaration value. Every
# accepted key in the maps above resolves through the full
# text its map holds to the canonical form here, so one
# value stands stored in one form whichever accepted form
# the caller supplied.
_CANONICAL_IMPORTER = {
    IMPORTER_DECLARATION_TEXTS[0]: "all_captured",
    IMPORTER_DECLARATION_TEXTS[1]: "stated_subset",
    IMPORTER_DECLARATION_TEXTS[2]: "selection_rule_unknown",
}
_CANONICAL_SUPPLIER = {
    SUPPLIER_RELATION_TEXTS[0]: "audited_party",
    SUPPLIER_RELATION_TEXTS[1]: "independent",
    SUPPLIER_RELATION_TEXTS[2]: "supplier_relation_unknown",
}


def name_round(home, product=None, round_label=None,
               importer_declaration=None, supplier_relation=None,
               audit_date=None, **kwargs):
    """Name a round for a standing product, under contract C10.

    One round_named entry stands written, advancing no
    registry version. A standing label for the product is a
    domain error and nothing is stored. Out of set field
    values are usage errors naming the allowed values in
    full, value by value.
    """
    if round_label is None:
        round_label = kwargs.get("label", kwargs.get("round"))
    _require_product(home, product)
    with _registry_lock(home):
        record = _require_product(home, product)
        if not isinstance(round_label, str) or not round_label:
            _fail("VALIDATION_FAILED", "a round label is required")
        if len(round_label) > 200:
            _fail("LIMIT_EXCEEDED", "round label length limit is 200")
        importer_key = _normal_key(importer_declaration or "")
        if importer_key not in _IMPORTER_KEYS:
            _fail(
                "ROUND_FIELD_OUT_OF_SET",
                "importer_declaration is out of set; allowed values: "
                "all captured answers imported; a stated subset "
                "imported; selection rule unknown")
        supplier_key = _normal_key(supplier_relation or "")
        if supplier_key not in _SUPPLIER_KEYS:
            _fail(
                "ROUND_FIELD_OUT_OF_SET",
                "supplier_relation is out of set; allowed values: "
                "supplied by the audited party; supplied by an "
                "independent party; supplier relation unknown")
        for standing in _rounds(home):
            if (standing.get("product_id") == record["product_id"]
                    and standing.get("round_label") == round_label):
                _fail(
                    "ROUND_LABEL_EXISTS",
                    "round label %r already stands for product %s; "
                    "rounds are never overwritten or renamed"
                    % (round_label, record.get("name")))
        round_record = {
            "round_id": round_id_for(record["product_id"], round_label),
            "product_id": record["product_id"],
            "round_label": round_label,
            "importer_declaration": _CANONICAL_IMPORTER[
                _IMPORTER_KEYS[importer_key]],
            "supplier_relation": _CANONICAL_SUPPLIER[
                _SUPPLIER_KEYS[supplier_key]],
            "registry_version_at_first_import": None,
            "detector_version_at_first_import": None,
            "created_by": "name_round",
        }
        _append(home, "round_named", copy.deepcopy(round_record), audit_date)
        return copy.deepcopy(round_record)
