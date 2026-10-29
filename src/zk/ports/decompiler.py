"""decompiler port (contract v2, ADR 0004): Decompiles .NET assemblies into one C# project each.

`decompile` reads `assemblies/<name>.dll` for each name (other DLLs there are references), writes
`out/projects/<name>/` and `out/report.json` (zk.formats.csharp_project), and returns info for the manifest.
Changing this contract needs a new ADR.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zk.core.contracts import ArtifactContract

PORT = "decompiler"
CONTRACT = ArtifactContract(PORT, files=("report.json",), dirs=("projects",))


@runtime_checkable
class Decompiler(Protocol):
    def decompile(self, assemblies: Path, names: list[str], out: Path) -> dict: ...
