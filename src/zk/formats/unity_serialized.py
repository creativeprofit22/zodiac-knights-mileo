"""Unity SerializedFile header: format number and the Unity version string.

Format (big-endian uint32) sits at 0x08. The version string follows the header: at 0x14 for formats 9-21,
and at 0x30 for 22+ (which widened the header to 64-bit sizes).
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass

MIN_FORMAT, MAX_FORMAT = 9, 40
WIDE_HEADER_FORMAT = 22
_VERSION = re.compile(rb"((?:\d{4}|\d)\.\d+\.\d+[a-z]\d+)\0")
HEAD_BYTES = 0x30 + 32  # enough to read any supported header + version string
KNOWN_UNITY_VERSIONS = frozenset({"6000.3.2f1"})  # engine builds this pipeline has been checked against


@dataclass(frozen=True)
class SerializedHeader:
    format: int
    unity_version: str


def parse_header(head: bytes) -> SerializedHeader | None:
    """Return the header, or None if `head` is not the start of a SerializedFile."""
    if len(head) < 0x14:
        return None
    (fmt,) = struct.unpack_from(">I", head, 0x08)
    if not MIN_FORMAT <= fmt <= MAX_FORMAT:
        return None
    m = _VERSION.match(head, 0x30 if fmt >= WIDE_HEADER_FORMAT else 0x14)
    return SerializedHeader(fmt, m.group(1).decode("ascii")) if m else None


def is_serialized_file(head: bytes) -> bool:
    return parse_header(head) is not None


_IDENT = re.compile(rb"[A-Za-z_][\w.`<>+-]*")


def _aligned_string(raw: bytes, at: int) -> tuple[str, int] | None:
    """Unity aligned string at `at` (int32 length, bytes, pad to 4) -> (text, next offset)."""
    if at + 4 > len(raw):
        return None
    (n,) = struct.unpack_from("<i", raw, at)
    if n == 0:
        return "", at + 4
    end = at + 4 + n
    if not 0 < n < 256 or end > len(raw) or not _IDENT.fullmatch(raw[at + 4:end]):
        return None
    return raw[at + 4:end].decode("ascii"), (end + 3) // 4 * 4


def managed_reference_types(raw: bytes) -> list[tuple[str, str, str]]:
    """Candidate (class, namespace, assembly) triples in an object's bytes.

    A ManagedReferencesRegistry entry names its type inline as three aligned strings; with type trees disabled this
    is the only place the names appear. Callers keep only triples that name a class the dump knows.
    """
    found: set[tuple[str, str, str]] = set()
    for at in range(0, max(len(raw) - 3, 0), 4):
        first = _aligned_string(raw, at)
        if not first or not first[0]:
            continue
        second = _aligned_string(raw, first[1])
        if second is None:
            continue
        third = _aligned_string(raw, second[1])
        if third and third[0]:
            found.add((first[0], second[0], third[0]))
    return sorted(found)
