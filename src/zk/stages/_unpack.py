"""Shared stage glue: the `unpack` record lookup, ABI resolution, the `code` record ABI check and `--abi`."""
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_ABI = "arm64-v8a"


def _unpack_record(ctx, version: str) -> dict:
    unpack = ctx.ws.manifest().get("unpack")
    if not unpack or unpack.get("version") != version:
        raise RuntimeError(f"no unpack record for {version}: run `zk unpack` first")
    return unpack


def resolve_abi(ctx, version: str, abi: str | None) -> str:
    """--abi if given; else the device's ABI from `acquire`, arm64-v8a, or the only one unpack found."""
    if abi:
        return abi
    have = sorted((_unpack_record(ctx, version).get("il2cpp") or {}))
    acquire = ctx.ws.manifest().get("acquire") or {}
    device = acquire.get("abi") if acquire.get("version") == version else None
    for candidate in (device, DEFAULT_ABI):
        if candidate and candidate in have:
            return candidate
    if len(have) == 1:
        return have[0]
    raise RuntimeError(f"cannot pick an ABI: device ABI {device!r}, unpacked ABIs {have}: pass --abi")


def unpack_inputs(ctx, version: str, abi: str) -> tuple[Path, Path, list[str]]:
    unpack = _unpack_record(ctx, version)
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


def add_abi_argument(p: argparse.ArgumentParser, help: str) -> None:
    p.add_argument("--abi", default=None,
                   help=f"{help} (default: the device's ABI from `zk acquire` if unpacked, else {DEFAULT_ABI}, "
                        "else the only unpacked ABI)")


def check_code_record(ctx, version: str, abi: str, what: str, missing_hint: str = "") -> None:
    """Refuse a `code` record for another version, or one dumped for another ABI than `abi`."""
    code = ctx.ws.manifest().get("code")
    if not code or code.get("version") != version:
        raise RuntimeError(f"no code record for {version}: run `zk code` first{missing_hint}")
    if code.get("abi") != abi:
        raise RuntimeError(f"{what} was dumped for ABI {code.get('abi')!r} by `zk code`, not {abi!r}: "
                           f"rerun `zk code --abi {abi}` or pass `--abi {code.get('abi')}`")
