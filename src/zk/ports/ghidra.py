"""ghidra port (contract v1): Analyses the native binary and exports per-function results.

The adapter writes into `out`/`dest` and returns info for the manifest; CONTRACT lists what it must leave there.
Changing this contract needs a new ADR.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zk.core.contracts import ArtifactContract

PORT = "ghidra"
CONTRACT = ArtifactContract(PORT, files=("index.json",), dirs=("functions",))


@runtime_checkable
class Ghidra(Protocol):
    def analyze(self, binary: Path, dump_dir: Path, out: Path) -> dict: ...
