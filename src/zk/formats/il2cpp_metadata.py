"""IL2CPP global-metadata.dat header: magic + version (little-endian uint32 / int32)."""
from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = 0xFAB11BAF
KNOWN_VERSIONS = frozenset({39})  # versions this pipeline has been checked against


@dataclass(frozen=True)
class MetadataHeader:
    magic: int
    version: int | None
    encrypted: bool
    warnings: tuple[str, ...] = ()

    @property
    def magic_hex(self) -> str:
        return f"0x{self.magic:08X}"


def parse_header(data: bytes) -> MetadataHeader:
    """Never raises on bad input: problems become `encrypted` and/or warnings."""
    if len(data) < 8:
        return MetadataHeader(0, None, True, (f"metadata too short ({len(data)} bytes) for a header",))
    magic, version = struct.unpack_from("<Ii", data, 0)
    if magic != MAGIC:
        return MetadataHeader(magic, None, True,
                              (f"metadata magic 0x{magic:08X} is not 0x{MAGIC:08X}: encrypted or obfuscated",))
    if version not in KNOWN_VERSIONS:
        known = ", ".join(map(str, sorted(KNOWN_VERSIONS)))
        return MetadataHeader(magic, version, False,
                              (f"metadata version {version} not in known versions ({known})",))
    return MetadataHeader(magic, version, False)
