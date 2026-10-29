"""device_source port (contract v1): Pulls the installed game off a device.

The adapter writes into `out`/`dest` and returns info for the manifest; CONTRACT lists what it must leave there.
Changing this contract needs a new ADR.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zk.core.contracts import ArtifactContract

PORT = "device_source"
CONTRACT = ArtifactContract(PORT, files=("base.apk",))


@runtime_checkable
class DeviceSource(Protocol):
    def pull(self, package: str, dest: Path) -> dict: ...
