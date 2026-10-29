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
