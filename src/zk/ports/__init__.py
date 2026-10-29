"""Port registry: one Protocol + artifact contract per external-tool boundary."""
from __future__ import annotations

from dataclasses import dataclass

from zk.core.contracts import ArtifactContract

from . import decompiler, device_source, ghidra, il2cpp_crosscheck, il2cpp_dump, type_info


@dataclass(frozen=True)
class Port:
    name: str
    protocol: type
    contract: ArtifactContract


PORTS: dict[str, Port] = {p.name: p for p in (
    Port(device_source.PORT, device_source.DeviceSource, device_source.CONTRACT),
    Port(il2cpp_dump.PORT, il2cpp_dump.Il2CppDump, il2cpp_dump.CONTRACT),
    Port(il2cpp_crosscheck.PORT, il2cpp_crosscheck.Il2CppCrosscheck, il2cpp_crosscheck.CONTRACT),
    Port(decompiler.PORT, decompiler.Decompiler, decompiler.CONTRACT),
    Port(type_info.PORT, type_info.TypeInfo, type_info.CONTRACT),
    Port(ghidra.PORT, ghidra.Ghidra, ghidra.CONTRACT),
)}
