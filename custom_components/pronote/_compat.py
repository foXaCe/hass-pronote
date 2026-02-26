"""Compatibility patches for the Pronote integration.

Hotfix for python 3.13+: https://github.com/bain3/pronotepy/pull/317#issuecomment-2523257656
This must be imported before pronotepy to patch autoslot if needed.

Patches autoslot.assignments_to_self to handle Python 3.13+ bytecode
(LOAD_FAST_LOAD_FAST) and Python 3.14+ (LOAD_FAST_BORROW,
LOAD_FAST_BORROW_LOAD_FAST_BORROW). Only patches if the installed
autoslot version does not already handle these opcodes.
"""

from __future__ import annotations

import dis
from itertools import tee

import autoslot


def _needs_patch() -> bool:
    """Check if autoslot needs patching for current Python bytecode."""
    # Build a test function and check if autoslot detects self-assignments
    code = "def _test(self, val):\n    self._test_attr = val\n"
    ns: dict = {}
    exec(code, ns)  # noqa: S102
    detected = autoslot.assignments_to_self(ns["_test"])
    return "_test_attr" not in detected


def _assignments_to_self(method) -> set:
    """Detect self-assignments in __init__ bytecode (Python 3.13+/3.14+)."""
    instance_var = next(iter(method.__code__.co_varnames), "self")
    instructions = dis.Bytecode(method)
    i0, i1 = tee(instructions)
    next(i1, None)
    names = set()
    for a, b in zip(i0, i1, strict=False):
        # Single-load opcodes: self is loaded alone
        accessing_self = a.opname in ("LOAD_FAST", "LOAD_DEREF", "LOAD_FAST_BORROW") and a.argval == instance_var
        # Fused-load opcodes (Python 3.13+/3.14+): self is second in the pair
        if not accessing_self and a.opname in ("LOAD_FAST_LOAD_FAST", "LOAD_FAST_BORROW_LOAD_FAST_BORROW"):
            accessing_self = a.argval[1] == instance_var
        storing_attribute = b.opname == "STORE_ATTR"
        if accessing_self and storing_attribute:
            names.add(b.argval)
    return names


if _needs_patch():
    autoslot.assignments_to_self = _assignments_to_self
