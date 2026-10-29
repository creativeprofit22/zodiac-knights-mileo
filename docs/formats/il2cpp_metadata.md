# Format: `il2cpp_metadata`

Module `zk/formats/il2cpp_metadata.py`. A pure parser: bytes in, data out. It uses no tools and no workspace.

## Where it appears
`assets/bin/Data/Managed/Metadata/global-metadata.dat` in the base APK. The `unpack` stage records the result as the `metadata_version` game fact.

## Layout
| offset | size | type | field | notes |
|---|---|---|---|---|
| 0x00 | 4 | u32 LE | magic | `0xFAB11BAF`; anything else means encrypted or obfuscated |
| 0x04 | 4 | i32 LE | version | 39 for this build |

## API
```python
MAGIC = 0xFAB11BAF
KNOWN_VERSIONS = frozenset({39})
def parse_header(data: bytes) -> MetadataHeader: ...  # (magic, version, encrypted, warnings), magic_hex
```
It never raises:
- With fewer than 8 bytes, or a bad magic, it returns `encrypted=True` plus a warning.
- An unknown version is kept, with a warning.

## Evidence
Read from the 0.4.6-17 APK (2026-10-28 probe): magic `0xFAB11BAF`, version 39. It matches SSA `stages/unpack.py` `metadata_info`.

## Tests
`tests/test_formats.py` uses synthetic headers: a good v39 header, an unknown version, a bad magic, and a short buffer.
