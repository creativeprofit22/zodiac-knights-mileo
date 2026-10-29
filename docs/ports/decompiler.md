# Port: `decompiler` (contract v1)

Module `zk/ports/decompiler.py`. Changing this contract needs a new ADR.

Decompiles the APK Java/Kotlin layer into code/<version>/.

## Protocol
```python
class Decompiler(Protocol):
    def decompile(self, apk: Path, out: Path) -> dict: ...
```

## Artifact contract
| path | kind | content |
|---|---|---|
| `sources/` | folder | |

## Adapters
| name (`zk.toml` value) | tool | status |
|---|---|---|
| none yet | | added by its adapter phase |
