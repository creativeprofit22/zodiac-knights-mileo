"""il2cpp_dump port (contract v1): Dumps IL2CPP metadata into C# signatures.

The adapter writes into `out`/`dest` and returns info for the manifest; CONTRACT lists what it must leave there.
Changing this contract needs a new ADR.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zk.core.contracts import ArtifactContract

PORT = "il2cpp_dump"
CONTRACT = ArtifactContract(PORT, files=("dump.cs", "script.json"), dirs=("DummyDll",))


@runtime_checkable
class Il2CppDump(Protocol):
    def dump(self, binary: Path, metadata: Path, out: Path) -> dict: ...
