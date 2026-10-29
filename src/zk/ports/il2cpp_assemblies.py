"""il2cpp_assemblies port (contract v1): Rebuilds .NET assemblies (metadata only) from an IL2CPP build.

The adapter writes `out/assemblies/<Asm>.dll` and returns info for the manifest. Changing this contract needs a new ADR.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zk.core.contracts import ArtifactContract

PORT = "il2cpp_assemblies"
CONTRACT = ArtifactContract(PORT, dirs=("assemblies",))


@runtime_checkable
class Il2CppAssemblies(Protocol):
    def build(self, binary: Path, metadata: Path, unity_version: str, out: Path) -> dict: ...
