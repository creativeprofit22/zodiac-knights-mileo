# Port: `il2cpp_dump` (contract v1)

Module `zk/ports/il2cpp_dump.py`. Changing this contract needs a new ADR.

Turns libil2cpp.so + global-metadata.dat into C# signatures. Perfare Il2CppDumper is not used: it breaks on metadata v39.

## Protocol
```python
class Il2CppDump(Protocol):
    def dump(self, binary: Path, metadata: Path, out: Path) -> dict: ...
```

## Artifact contract
| path | kind | content |
|---|---|---|
| `dump.cs` | file | |
| `script.json` | file | |
| `DummyDll/` | folder | |

## Adapters
| name (`zk.toml` value) | tool | status |
|---|---|---|
| none yet | | added by its adapter phase |
