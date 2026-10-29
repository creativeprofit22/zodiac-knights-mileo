"""java_decompiler port (contract v1): Decompiles the APK's Java/Kotlin code.

The adapter writes into `out` and returns info for the manifest; CONTRACT lists what it must leave there.
Changing this contract needs a new ADR.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zk.core.contracts import ArtifactContract

PORT = "java_decompiler"
CONTRACT = ArtifactContract(PORT, dirs=("sources",))


@runtime_checkable
class JavaDecompiler(Protocol):
    def decompile(self, apk: Path, out: Path) -> dict: ...
