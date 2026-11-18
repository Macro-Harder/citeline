"""Citeline: a record for citability audits, verifiable
for internal consistency only.

The package holds one module per slice of the design
plan. This init carries no rule and imports no slice, so
each module stands or falls on its own imports.
"""

import sys

__all__ = []

PYTHON_FLOOR = (3, 11)


def enforce_python_floor(version=None):
    """Refuse an interpreter below the stated floor.

    Citeline requires Python 3.11 or later. The refusal
    names the floor in the product's own words, so an old
    interpreter meets a Citeline statement of the floor
    and not an interpreter error in whatever form that
    Python raises.
    """
    standing = tuple(version or sys.version_info[:3])
    if standing < PYTHON_FLOOR + (0,):
        raise RuntimeError(
            "Citeline requires Python 3.11 or later; this "
            "interpreter is Python %d.%d.%d" % standing)


enforce_python_floor()
