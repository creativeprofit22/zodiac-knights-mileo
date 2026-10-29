"""device_source port (contract v2, ADR 0002): pulls the installed game off a device.

`identify` names the build before anything is pulled, so the stage can choose raw/<version>/.
`pull` writes dest/apk/*.apk (always base.apk), optionally dest/obb/ and dest/data/, and returns info for the manifest.
Changing this contract needs a new ADR.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zk.core.contracts import ArtifactContract

PORT = "device_source"
CONTRACT = ArtifactContract(PORT, files=("apk/base.apk",))


@runtime_checkable
class DeviceSource(Protocol):
    def identify(self, package: str) -> dict: ...  # {"package", "version", "abi"?}; RuntimeError if absent

    def pull(self, package: str, dest: Path) -> dict: ...
