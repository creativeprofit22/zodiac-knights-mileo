"""unpack: extract raw/<version>/apk/*.apk into unpacked/<version>/<stem>/ and inventory the Unity 6 build.

Adapted from SSA stages/unpack.py (6e1be49); this game has no AssetBundles, so the Unity version is
read from the globalgamemanagers SerializedFile header instead.
"""
from __future__ import annotations

import argparse
import re
import shutil
import zipfile
from pathlib import Path

from zk.formats import il2cpp_metadata, scripting_assemblies, unity_serialized

NAME = "unpack"
HELP = "extract the APKs and record Unity version, IL2CPP binaries, metadata, assemblies and assets"

DATA = "assets/bin/Data"
METADATA = f"{DATA}/Managed/Metadata/global-metadata.dat"
GGM = f"{DATA}/globalgamemanagers"
SCRIPTING_ASSEMBLIES = f"{DATA}/ScriptingAssemblies.json"
VIDEO = "assets/Video"
RESOURCE_SUFFIXES = (".resource", ".ress")
_SPLIT = re.compile(r"^(.*)\.split(\d+)$")


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--force", action="store_true", help="re-extract APKs that were already unpacked")


def _head(path: Path) -> bytes:
    with path.open("rb") as f:
        return f.read(unity_serialized.HEAD_BYTES)


def _find(roots: list[Path], rel: str) -> Path | None:
    return next((r / rel for r in roots if (r / rel).is_file()), None)


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def inventory(root: Path) -> dict:
    """Inventory every extracted APK folder under `root` (unpacked/<version>/); paths are relative to `root`."""
    roots = sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    warnings: list[str] = []

    il2cpp: dict[str, str] = {}
    for r in roots:
        for so in sorted(r.glob("lib/*/libil2cpp.so")):
            il2cpp.setdefault(so.parent.name, _rel(so, root))
    mono = any((r / DATA / "Managed" / "Assembly-CSharp.dll").is_file() for r in roots)
    backend = "il2cpp" if il2cpp else ("mono" if mono else "unknown")

    metadata = None
    if (mp := _find(roots, METADATA)) is not None:
        with mp.open("rb") as f:
            hdr = il2cpp_metadata.parse_header(f.read(8))
        metadata = {"path": _rel(mp, root), "magic": hdr.magic_hex, "version": hdr.version,
                    "encrypted": hdr.encrypted}
        warnings += hdr.warnings
    elif backend == "il2cpp":
        warnings.append(f"{METADATA} not found")

    unity_version = serialized_format = None
    ggm = _find(roots, GGM) or _find(roots, GGM + ".split0")
    if ggm is None:
        warnings.append(f"{GGM} not found")
    elif (sh := unity_serialized.parse_header(_head(ggm))) is None:
        warnings.append(f"{_rel(ggm, root)} is not a SerializedFile this pipeline can read")
    else:
        unity_version, serialized_format = sh.unity_version, sh.format
        if unity_version not in unity_serialized.KNOWN_UNITY_VERSIONS:
            known = ", ".join(sorted(unity_serialized.KNOWN_UNITY_VERSIONS))
            warnings.append(f"Unity version {unity_version} is not one this pipeline has been checked against "
                            f"({known}); check the asset and type-info output")

    assemblies = None
    if (sp := _find(roots, SCRIPTING_ASSEMBLIES)) is None:
        warnings.append(f"{SCRIPTING_ASSEMBLIES} not found")
    else:
        try:
            sa = scripting_assemblies.parse(sp.read_text(encoding="utf-8"))
            assemblies = {"count": len(sa.names), "game": scripting_assemblies.game_assemblies(sa)}
        except ValueError as e:
            warnings.append(str(e))

    serialized = resources = 0
    for r in roots:
        data = r / DATA
        if not data.is_dir():
            continue
        for f in sorted(p for p in data.rglob("*") if p.is_file()):
            name = f.name.lower()
            if name.endswith(RESOURCE_SUFFIXES):
                resources += 1
                continue
            split = _SPLIT.match(f.name)
            if split and split.group(2) != "0":
                continue  # a split file counts once, through its .split0 part
            if unity_serialized.is_serialized_file(_head(f)):
                serialized += 1

    videos: list[dict] = []
    manifest_json = False
    for r in roots:
        vdir = r / VIDEO
        if not vdir.is_dir():
            continue
        for f in sorted(p for p in vdir.iterdir() if p.is_file()):
            if f.name == "manifest.json":
                manifest_json = True
            else:
                videos.append({"name": f.name, "bytes": f.stat().st_size})

    return {"abis": sorted(il2cpp), "il2cpp": dict(sorted(il2cpp.items())), "backend": backend,
            "metadata": metadata, "unity_version": unity_version, "serialized_format": serialized_format,
            "assemblies": assemblies, "serialized_files": serialized, "resource_streams": resources,
            "videos": {"files": sorted(videos, key=lambda v: v["name"]), "manifest_json": manifest_json},
            "warnings": warnings}


def extract(apk: Path, dst: Path, force: bool) -> bool:
    if dst.exists() and not force:
        return False
    if dst.exists():
        shutil.rmtree(dst)
    partial = dst.with_name(dst.name + ".partial")  # only renamed into place once fully extracted
    if partial.exists():
        shutil.rmtree(partial)
    print(f"[unpack] extracting {apk.name} -> {dst}")
    with zipfile.ZipFile(apk) as z:
        z.extractall(partial)
    partial.rename(dst)
    return True


def remove_orphans(out: Path, stems: set[str]) -> list[str]:
    """Delete unpacked/<v>/<stem>/ folders whose <stem>.apk is gone, so inventory never reads a stale split."""
    removed = []
    for d in sorted(p for p in out.iterdir() if p.is_dir()) if out.is_dir() else []:
        if d.name not in stems:
            print(f"[unpack] removing {d}: no {d.name}.apk in raw/")
            shutil.rmtree(d)
            removed.append(d.name)
    return removed


def execute(ctx, args: argparse.Namespace) -> dict:
    version = ctx.ws.current_version()
    raw = ctx.ws.dir("raw", version)
    apks = sorted((raw / "apk").glob("*.apk"))
    if not apks:
        raise RuntimeError(f"no APKs in {raw / 'apk'}: run `zk acquire` first")
    out = ctx.ws.dir("unpacked", version)
    removed = remove_orphans(out, {apk.stem for apk in apks})
    extracted = []
    for apk in apks:
        try:
            if extract(apk, out / apk.stem, args.force):
                extracted.append(apk.name)
        except zipfile.BadZipFile as e:
            raise RuntimeError(f"{apk} is not a valid APK/zip: {e}") from e
    inv = inventory(out)
    metadata_version = inv["metadata"]["version"] if inv["metadata"] else None
    ctx.ws.record_facts({"unity_version": inv["unity_version"], "metadata_version": metadata_version,
                         "backend": inv["backend"], "abis": inv["abis"]})
    return {"version": version, "extracted": extracted, "removed": removed, "path": str(out), **inv}
