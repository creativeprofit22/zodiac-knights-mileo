# Port: `il2cpp_crosscheck` (contract v1)

Module `zk/ports/il2cpp_crosscheck.py`, added by [ADR 0003](../adr/0003-il2cpp-dump-v2.md). Changing this contract needs a new ADR.

A second, independent IL2CPP dumper. The `code` stage compares its per-assembly summary with the `il2cpp_dump` one, so a bug in either tool shows up as a count difference.

## Protocol
```python
class Il2CppCrosscheck(Protocol):
    def crosscheck(self, binary: Path, metadata: Path, out: Path) -> dict: ...
```

## Artifact contract
| path | kind | content |
|---|---|---|
| `summary.json` | file | same shape and normalization as the `il2cpp_dump` `summary.json` (rules in [il2cpp_dump Notes](il2cpp_dump.md#notes) and [csharp_dump](../formats/csharp_dump.md#layout)) |

## Adapters
| name (`zk.toml` value) | tool | status |
|---|---|---|
| `il2cppinspector` | Il2CppInspectorRedux 2026.2, Legacy CLI (C# per assembly in `out/cs/`) | default |

## Notes
- Il2CppInspectorRedux is AGPL-3.0. It is only downloaded and run as a separate program, never vendored.
- Type counts must match the dump for every game assembly; method counts may differ per class and are only reported.
