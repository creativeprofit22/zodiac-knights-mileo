# Port: `type_info` (contract v1)

Module `zk/ports/type_info.py`. Changing this contract needs a new ADR.

Produces C headers for IL2CPP types (for Ghidra) into types/<version>/.

## Protocol
```python
class TypeInfo(Protocol):
    def types(self, dump_dir: Path, out: Path) -> dict: ...
```

## Artifact contract
| path | kind | content |
|---|---|---|
| `il2cpp.h` | file | |

## Adapters
| name (`zk.toml` value) | tool | status |
|---|---|---|
| none yet | | added by its adapter phase |
