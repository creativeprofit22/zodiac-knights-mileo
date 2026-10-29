"""il2cpp_crosscheck port (contract v1, ADR 0003): an independent IL2CPP dumper used to check il2cpp_dump.

The adapter writes into `out` and returns info for the manifest; summary.json has the il2cpp_dump summary shape.
Changing this contract needs a new ADR.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zk.core.contracts import ArtifactContract

PORT = "il2cpp_crosscheck"
CONTRACT = ArtifactContract(PORT, files=("summary.json",))


@runtime_checkable
class Il2CppCrosscheck(Protocol):
    def crosscheck(self, binary: Path, metadata: Path, out: Path) -> dict: ...
