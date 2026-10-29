"""il2cpp_dump port (contract v2, ADR 0003): Dumps IL2CPP metadata into C# signatures.

The adapter writes into `out` and returns info for the manifest; CONTRACT lists what it must leave there.
summary.json: {"assemblies": {name: {"types": n, "methods": n, "classes": {"Ns.Type": methods}}}}.
Names are normalized by the rules in docs/formats/csharp_dump.md, which are normative (generic Name`N, <>c -> __c,
no <Module>, accessors count as methods, "types" counts declarations).
Changing this contract needs a new ADR.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zk.core.contracts import ArtifactContract

PORT = "il2cpp_dump"
CONTRACT = ArtifactContract(PORT, files=("dump.cs", "script.json", "il2cpp.h", "summary.json"), dirs=("DummyDll",))


@runtime_checkable
class Il2CppDump(Protocol):
    def dump(self, binary: Path, metadata: Path, out: Path) -> dict: ...
