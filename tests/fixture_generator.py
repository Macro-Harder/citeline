"""Step 13 fixture generator.

A test tree program. It produces large fixtures by scaling
and hostile fixtures by mutation, on the route plan
Section 1.6 states (CQ-D29), deterministically (CQ-D30),
with a provenance record per fixture. It is not product
code and holds no product rule.
"""

import hashlib

GENERATOR_NAME = "fixture_generator"
GENERATOR_VERSION = "1.0"


class GenerationRefused(Exception):
    """The stated route does not produce this fixture."""


class SeamListsStop(Exception):
    """Generation would need a CL-13 list member.

    The fixture stops at SEAM-LISTS and is not produced,
    on the doctrine at plan Section 2 as Section 1.6
    restates it.
    """


BASE_FIXTURES = {
    "w1-answer-unit": {
        "unit": b"Answer INDEX body text.\n",
        "varied": ["index"],
        "mutations": ["append-partial-line", "duplicate-unit",
                      "reverse-lines"],
    },
    "w1-journal-entry-unit": {
        "unit": b'{"entry_kind":"product_registered",'
                b'"form_version":1,"payload":{"name":'
                b'"Example Product","product_id":"p-example"},'
                b'"previous_hash":null,"sequence":INDEX}\n',
        "varied": ["sequence"],
        "mutations": ["append-partial-line", "truncate-final-line",
                      "duplicate-unit", "reverse-lines"],
    },
    "w1-page-section-unit": {
        "unit": b"## Section INDEX\nBody of section INDEX.\n",
        "varied": ["index"],
        "mutations": ["append-partial-line", "duplicate-unit",
                      "reverse-lines"],
    },
}

CL13_MUTATIONS = {"append-lexicon-term", "append-stop-word",
                  "insert-tracking-parameter"}


def _render_unit(base_id, index):
    unit = BASE_FIXTURES[base_id]["unit"]
    return unit.replace(b"INDEX", str(index).encode("ascii"))


def _apply_mutation(base_id, data, mutation):
    if mutation == "append-partial-line":
        return data + b'{"entry_kind":"corre'
    if mutation == "truncate-final-line":
        return data[:-4]
    if mutation == "duplicate-unit":
        return data + data
    if mutation == "reverse-lines":
        lines = data.splitlines(keepends=True)
        return b"".join(reversed(lines))
    raise GenerationRefused("unlisted mutation: %s" % mutation)


def generate(base_id, route, target_count=None, target_bytes=None,
             mutations=None):
    """Produce one fixture and its provenance record.

    Returns (data, provenance). Raises SeamListsStop where
    generation would need a CL-13 list member, and
    GenerationRefused where the stated route does not
    produce the fixture.
    """
    if base_id not in BASE_FIXTURES:
        raise GenerationRefused("no catalogue entry: %s" % base_id)
    entry = BASE_FIXTURES[base_id]
    if route == "scaling":
        if mutations:
            raise GenerationRefused("scaling takes no mutations")
        if target_count is None and target_bytes is None:
            raise GenerationRefused("scaling needs a stated target")
        chunks = []
        size = 0
        index = 1
        while True:
            if target_count is not None and index > target_count:
                break
            chunk = _render_unit(base_id, index)
            chunks.append(chunk)
            size += len(chunk)
            index += 1
            if target_bytes is not None and size >= target_bytes:
                break
        data = b"".join(chunks)
        target = {"target_count": target_count,
                  "target_bytes": target_bytes}
    elif route == "mutation":
        if not mutations or len(mutations) != 1:
            raise GenerationRefused(
                "one mutation per fixture; no w1 catalogue entry "
                "states a combination")
        mutation = mutations[0]
        if mutation in CL13_MUTATIONS:
            raise SeamListsStop(
                "mutation needs a CL-13 list member: %s" % mutation)
        if mutation not in entry["mutations"]:
            raise GenerationRefused(
                "mutation not listed for %s: %s" % (base_id, mutation))
        data = _apply_mutation(base_id, _render_unit(base_id, 1),
                               mutation)
        target = {"mutations": list(mutations)}
    else:
        raise GenerationRefused("unknown route: %s" % route)
    provenance = {
        "base": base_id,
        "route": route,
        "generator": GENERATOR_NAME,
        "generator_version": GENERATOR_VERSION,
        "byte_size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    provenance.update(target)
    if route == "mutation":
        provenance["mutations"] = target["mutations"]
    return data, provenance


def check_provenance(provenance, data):
    """Check produced bytes against a recorded provenance.

    The recorded byte size and sha256 stand checked on
    every later use, on plan Section 1.6 terms.
    """
    return (provenance.get("byte_size") == len(data)
            and provenance.get("sha256")
            == hashlib.sha256(data).hexdigest())
