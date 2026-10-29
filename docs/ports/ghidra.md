# Port: `ghidra` (contract v1)

Module `zk/ports/ghidra.py`. Changing this contract needs a new ADR.

Headless analysis of the native binary into ghidra/<version>/.

## Protocol
```python
class Ghidra(Protocol):
    def analyze(self, binary: Path, dump_dir: Path, out: Path) -> dict: ...
```

## Artifact contract
| path | kind | content |
|---|---|---|
| `index.json` | file | |
| `functions/` | folder | |

## Adapters
| name (`zk.toml` value) | tool | status |
|---|---|---|
| none yet | | added by its adapter phase |
