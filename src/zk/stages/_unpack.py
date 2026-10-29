"""Shared lookup of the `unpack` record (binary, metadata, game assemblies) for stages that read it."""
from __future__ import annotations

from pathlib import Path


def unpack_inputs(ctx, version: str, abi: str) -> tuple[Path, Path, list[str]]:
    unpack = ctx.ws.manifest().get("unpack")
    if not unpack or unpack.get("version") != version:
        raise RuntimeError(f"no unpack record for {version}: run `zk unpack` first")
    root = ctx.ws.dir("unpacked", version)
    rel = (unpack.get("il2cpp") or {}).get(abi)
    if not rel:
        raise RuntimeError(f"unpack found no libil2cpp.so for ABI {abi!r} (have {unpack.get('abis')}): "
                           "run `zk unpack` or pass --abi")
    meta = (unpack.get("metadata") or {}).get("path")
    if not meta:
        raise RuntimeError("unpack found no global-metadata.dat: run `zk unpack`")
    binary, metadata = root / rel, root / meta
    for p in (binary, metadata):
        if not p.is_file():
            raise RuntimeError(f"{p} is missing: run `zk unpack --force`")
    game = (unpack.get("assemblies") or {}).get("game")
    if not game:
        raise RuntimeError("unpack recorded no game assemblies (ScriptingAssemblies.json): run `zk unpack`")
    return binary, metadata, list(game)
