"""ghidra port (contract v2, ADR 0005): Analyses the native binary and exports decompiled C per class.

`analyze` reads only `script.json` and `il2cpp.h` from `dump_dir` (the il2cpp_dump output) and the target list
`targets` (TSV: `rva_hex<TAB><Ns>/<Class>.c`). It keeps the analysed project in `out/project/`, writes
`out/functions/<Ns>/<Class>.c` (resumable: existing files are kept) and `out/index.json`
(`{tool, version, jdk, project, classes: {relpath: functions}, missing: [relpaths],
failed: {relpath: functions not decompiled}}`), and returns info for the manifest. With `skip_analysis` it re-exports from the saved project. Changing this contract needs a new ADR.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zk.core.contracts import ArtifactContract

PORT = "ghidra"
CONTRACT = ArtifactContract(PORT, files=("index.json",), dirs=("functions", "project"))


@runtime_checkable
class Ghidra(Protocol):
    def analyze(self, binary: Path, dump_dir: Path, targets: Path, out: Path, skip_analysis: bool) -> dict: ...
