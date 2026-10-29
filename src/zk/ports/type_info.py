"""type_info port (contract v1): Produces C type definitions for the IL2CPP types.

The adapter writes into `out`/`dest` and returns info for the manifest; CONTRACT lists what it must leave there.
Changing this contract needs a new ADR.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zk.core.contracts import ArtifactContract

PORT = "type_info"
CONTRACT = ArtifactContract(PORT, files=("il2cpp.h",))


@runtime_checkable
class TypeInfo(Protocol):
    def types(self, dump_dir: Path, out: Path) -> dict: ...
