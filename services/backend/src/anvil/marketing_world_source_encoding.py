"""Lossless bounded private fixture encoding, not an archive extraction API."""

import base64
import binascii
import zlib

LIMIT = 1048576


def encode(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= LIMIT:
        raise ValueError("Bounded nonempty fixture bytes required")
    return base64.b64encode(zlib.compress(raw, level=9)).decode("ascii")


def decode(value):
    if type(value) is not str or not 1 <= len(value) <= 1400000:
        raise ValueError("Bounded private encoded fixture required")
    try:
        packed = base64.b64decode(value, validate=True)
        if base64.b64encode(packed).decode("ascii") != value:
            raise ValueError("Canonical private fixture encoding required")
        stream = zlib.decompressobj()
        raw = stream.decompress(packed, LIMIT + 1)
        if not 0 < len(raw) <= LIMIT or not stream.eof or stream.unused_data or stream.unconsumed_tail:
            raise ValueError("Complete single bounded fixture stream required")
    except (binascii.Error, ValueError, zlib.error) as exc:
        raise ValueError("Invalid or oversized encoded private fixture") from exc
    return raw
