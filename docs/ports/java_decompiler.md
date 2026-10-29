# Port: `java_decompiler` (contract v1)

Module `zk/ports/java_decompiler.py`. Changing this contract needs a new ADR. Named `decompiler` before [ADR 0004](../adr/0004-decompiler-v2.md).

Decompiles the APK Java/Kotlin layer into code/<version>/.

## Protocol
```python
class JavaDecompiler(Protocol):
    def decompile(self, apk: Path, out: Path) -> dict: ...
```

## Artifact contract
| path | kind | content |
|---|---|---|
| `sources/` | folder | Java sources |

## Adapters
| name (`zk.toml` value) | tool | status |
|---|---|---|
| `jadx` | jadx 1.5.6 (`-ds <out>/sources --no-res`) | default |

## Notes
- A non-zero jadx exit is common on obfuscated code. It is recorded (`exit_code`, last `errors`), and the run fails only when `sources/` is missing.
