"""Pure existing wire/timing checks without API config, DB or secret imports.

Algorithms retained from campaign_semantic_contract.bounded_json and
marketing_capture_database.remaining. This module grants no operational gate.
"""

import math
from time import monotonic

from anvil.praxis_generic_contract import canonical


def bounded_json(value, max_bytes, *, max_nodes=4096, max_depth=32):
    """Bound work before RFC hashing/serialization; reject rather than truncate.

    Traverse iterators without copying a large container. Repeated subtrees
    consume the bound each time; cyclic/non-JSON objects fail before encoding.
    Only a bounded scalar is ever handed to the canonical encoder here.
    """
    nodes, size, ancestors = 0, 0, set()

    def visit(item, depth):
        nonlocal nodes, size
        nodes += 1
        if nodes > max_nodes or depth > max_depth:
            raise ValueError("Private JSON exceeds bounded depth or node count")
        kind = type(item)
        if kind in (dict, list):
            if len(item) > max_nodes or id(item) in ancestors:
                raise ValueError("Private JSON has an oversized or cyclic container")
            ancestors.add(id(item))
            size += 2 + max(0, len(item) - 1)
            if kind is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        raise ValueError("Private JSON requires string keys")
                    visit(key, depth + 1)
                    size += 1
                    visit(child, depth + 1)
            else:
                for child in item:
                    visit(child, depth + 1)
            ancestors.remove(id(item))
        else:
            if kind is str:
                if len(item) > max_bytes:
                    raise ValueError("Private JSON scalar exceeds byte bound")
            elif kind is int:
                if item.bit_length() > 54:
                    raise ValueError("Private JSON integer exceeds the RFC range")
            elif item is not None and kind not in (bool, float):
                raise ValueError("Private JSON scalar type is unsupported")
            size += len(canonical(item))
        if size > max_bytes:
            raise ValueError(
                "Private JSON exceeds frozen bound in bytes; no evidence was truncated"
            )

    visit(value, 0)
    return size


def remaining(deadline):
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError("Original absolute capture database deadline required")
    seconds = deadline - monotonic()
    if seconds <= 0:
        raise TimeoutError("Original capture database deadline reached")
    return seconds
