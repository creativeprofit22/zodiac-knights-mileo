# Port: `ghidra` (contract v2, [ADR 0005](../adr/0005-ghidra-v2.md))

Module `zk/ports/ghidra.py`. Changing this contract needs a new ADR.

Headless analysis of the native binary into `ghidra/<version>/`, exporting decompiled C for the target functions.

## Protocol
```python
class Ghidra(Protocol):
    def analyze(self, binary: Path, dump_dir: Path, targets: Path, out: Path, skip_analysis: bool) -> dict: ...
```
- `dump_dir`: the `il2cpp_dump` output; only `script.json` and `il2cpp.h` are read.
- `targets`: TSV `rva_hex<TAB><Ns>/<Class>.c`, one line per function.
- `skip_analysis`: re-export from the saved `project/`; fails when there is none.

## Artifact contract
| path | kind | content |
|---|---|---|
| `index.json` | file | `{tool, version, jdk, project, classes: {relpath: functions}, missing: [relpaths not written], failed: {relpath: functions not decompiled, non-zero only}}` |
| `functions/` | folder | `<Ns>/<Class>.c`, decompiled C per class; existing files are kept (resumable) |
| `project/` | folder | the analysed Ghidra project (`libil2cpp.gpr`) |

## Adapters
| name (`zk.toml` value) | tool | status |
|---|---|---|
| `ghidra` | Ghidra 12.2 `analyzeHeadless` on JDK 25 | default |
