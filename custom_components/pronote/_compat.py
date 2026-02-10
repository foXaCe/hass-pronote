"""Compatibility patches for the Pronote integration.

Hotfix for python 3.13: https://github.com/bain3/pronotepy/pull/317#issuecomment-2523257656
This must be imported before pronotepy to patch autoslot.
"""

from __future__ import annotations

import dis
from itertools import tee

import autoslot


def _assignments_to_self(method) -> set:
    instance_var = next(iter(method.__code__.co_varnames), "self")
    instructions = dis.Bytecode(method)
    i0, i1 = tee(instructions)
    next(i1, None)
    names = set()
    for a, b in zip(i0, i1, strict=False):
        accessing_self = (a.opname in ("LOAD_FAST", "LOAD_DEREF") and a.argval == instance_var) or (
            a.opname == "LOAD_FAST_LOAD_FAST" and a.argval[1] == instance_var
        )
        storing_attribute = b.opname == "STORE_ATTR"
        if accessing_self and storing_attribute:
            names.add(b.argval)
    return names


autoslot.assignments_to_self = _assignments_to_self
