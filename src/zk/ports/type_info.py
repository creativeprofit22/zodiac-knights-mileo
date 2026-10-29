"""type_info port (contract v2, ADR 0006): type-tree nodes for MonoBehaviour script classes.

The adapter writes nodes.json into `out` and returns info for the manifest.
Changing this contract needs a new ADR.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zk.core.contracts import ArtifactContract

PORT = "type_info"
CONTRACT = ArtifactContract(PORT, files=("nodes.json",))


@runtime_checkable
class TypeInfo(Protocol):
    def types(self, binary: Path, metadata: Path, dump_dir: Path, unity_version: str,
              classes: Path, out: Path) -> dict: ...
