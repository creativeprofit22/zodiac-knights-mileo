# Format: `unity_serialized`

Module `zk/formats/unity_serialized.py`. A pure parser: bytes in, data out. It uses no tools and no workspace.

## Where it appears
Raw Unity SerializedFiles (no UnityFS wrapper) under `assets/bin/Data`: `globalgamemanagers`, `level0`, `sharedassets*.assets`, the hash-named files, and the `.split0` part of split files. This game has no AssetBundles, so the `unity_version` game fact comes from the `globalgamemanagers` header.

## Layout
| offset | size | type | field | notes |
|---|---|---|---|---|
| 0x08 | 4 | u32 BE | format | the parser accepts 9–40; Unity 6 uses 22 |
| 0x14 | var | cstring | engine version | formats 9–21 |
| 0x30 | var | cstring | engine version | formats 22 and later (64-bit header fields) |

The version string must match `(\d{4}|\d)\.\d+\.\d+[a-z]\d+\0`, e.g. `6000.3.2f1`.

## API
```python
HEAD_BYTES = 0x50
def parse_header(head: bytes) -> SerializedHeader | None: ...  # (format, unity_version)
def is_serialized_file(head: bytes) -> bool: ...
def managed_reference_types(raw: bytes) -> list[tuple[str, str, str]]: ...  # (class, namespace, assembly)
```

## Evidence
In the 0.4.6-17 `globalgamemanagers`, the header starts with format 22 at 0x08, and `6000.3.2f1` is at 0x30. This matches SSA `is_serialized_file`.

## Tests
`tests/test_formats.py` covers:
- format 22 with the version at 0x30;
- format 17 with the version at 0x14;
- garbage input;
- a short buffer;
- an out-of-range format.

## Managed references
A `[SerializeReference]` field stores a `ManagedReferencesRegistry` at the end of the object. Each entry is `rid`
(int64), then the type as three aligned strings (int32 length, ASCII, padded to 4): class, namespace, assembly; then
the payload. With type trees disabled, the file's ref-type table carries no names, so `managed_reference_types` scans an
object's bytes for such triples. It over-reports (any three identifier strings in a row); the assets stage keeps only
triples naming a class the IL2CPP dump knows. On 0.4.6-17 this finds the 12 URP/Core settings classes in
`UniversalRenderPipelineGlobalSettings`. Covered by `test_managed_reference_types_finds_inline_type_triples`.
