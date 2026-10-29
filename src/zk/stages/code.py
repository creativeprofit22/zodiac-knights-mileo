"""code: dump the IL2CPP binary, cross-check it with an independent dumper, and decompile the Java side.

Outputs: il2cpp/<version>/ (il2cpp_dump), il2cpp/<version>/crosscheck/ + crosscheck.json, code/<version>/ (decompiler).
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from zk.ports import PORTS

NAME = "code"
HELP = "dump IL2CPP types/methods, cross-check them with a second dumper, and decompile the Java code"


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--abi", default="arm64-v8a", help="which libil2cpp.so to dump (default: arm64-v8a)")
    p.add_argument("--force", action="store_true", help="delete earlier outputs and rerun every step")
    p.add_argument("--skip-crosscheck", action="store_true", help="do not run the il2cpp_crosscheck port")
    p.add_argument("--skip-java", action="store_true", help="do not run the decompiler port")


def _pair(a: int | None, b: int | None) -> list[int | None]:
    return [a, b]


def compare(a: dict, b: dict, assemblies: list[str]) -> dict:
    """Compare two summary.json documents for the given assemblies; a missing side counts as None."""
    report: dict[str, dict] = {}
    mismatches: list[str] = []
    for name in sorted(assemblies):
        sa = a.get("assemblies", {}).get(name)
        sb = b.get("assemblies", {}).get(name)
        ca = sa["classes"] if sa else {}
        cb = sb["classes"] if sb else {}
        gaps = {cls: _pair(ca.get(cls), cb.get(cls)) for cls in sorted(set(ca) | set(cb))
                if ca.get(cls) != cb.get(cls)}
        types = _pair(sa["types"] if sa else None, sb["types"] if sb else None)
        if types[0] != types[1]:
            mismatches.append(name)
        report[name] = {"types": types, "methods": _pair(sa["methods"] if sa else None,
                                                         sb["methods"] if sb else None),
                        "method_gaps": gaps}
    return {"assemblies": report, "type_mismatches": mismatches, "types_match": not mismatches}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _inputs(ctx, version: str, abi: str) -> tuple[Path, Path, list[str]]:
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


def _check_game_assemblies(out: Path, summary: dict, game: list[str]) -> None:
    problems = []
    for name in sorted(game):
        s = summary.get("assemblies", {}).get(name)
        if not s or s["types"] <= 0:
            problems.append(f"{name} has no types in summary.json")
        if not (out / "DummyDll" / f"{name}.dll").is_file():
            problems.append(f"DummyDll/{name}.dll is missing")
    if problems:
        raise RuntimeError("il2cpp dump is incomplete: " + "; ".join(problems))


def _java_apk(ctx, version: str) -> Path:
    """The APK whose extracted folder holds classes.dex; base.apk when none does."""
    apks = sorted(ctx.ws.dir("raw", version, "apk").glob("*.apk"))
    if not apks:
        raise RuntimeError(f"no APKs for {version}: run `zk acquire` first")
    unpacked = ctx.ws.dir("unpacked", version)
    with_dex = [a for a in apks if (unpacked / a.stem / "classes.dex").is_file()]
    base = [a for a in apks if a.name == "base.apk"]
    return (with_dex or base or apks)[0]


def execute(ctx, args: argparse.Namespace) -> dict:
    version = ctx.ws.current_version()
    binary, metadata, game = _inputs(ctx, version, args.abi)
    il2cpp = ctx.ws.dir("il2cpp", version)
    code = ctx.ws.dir("code", version)
    if args.force:
        for d in (il2cpp, code):
            shutil.rmtree(d)
            d.mkdir(parents=True)

    print(f"[code] il2cpp_dump {binary.name} ({args.abi}) -> {il2cpp}")
    dump_info = ctx.adapter("il2cpp_dump").dump(binary, metadata, il2cpp)
    PORTS["il2cpp_dump"].contract.verify(il2cpp)
    summary = _read_json(il2cpp / "summary.json")
    _check_game_assemblies(il2cpp, summary, game)
    info: dict = {"version": version, "abi": args.abi, "game_assemblies": sorted(game),
                  "dump": {**dump_info, "assemblies": {n: {k: summary["assemblies"][n][k] for k in ("types", "methods")}
                                                       for n in sorted(game)}},
                  "crosscheck": None, "java": None}

    if not args.skip_crosscheck:
        cc = il2cpp / "crosscheck"
        cc.mkdir(exist_ok=True)
        print(f"[code] il2cpp_crosscheck -> {cc}")
        cc_info = ctx.adapter("il2cpp_crosscheck").crosscheck(binary, metadata, cc)
        PORTS["il2cpp_crosscheck"].contract.verify(cc)
        report = {"run": cc_info, **compare(summary, _read_json(cc / "summary.json"), game)}
        (il2cpp / "crosscheck.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        if not report["types_match"]:
            detail = ", ".join(f"{n} {report['assemblies'][n]['types']}" for n in report["type_mismatches"])
            raise RuntimeError(f"type counts differ between dumpers ([dump, crosscheck]): {detail}; "
                               f"see {il2cpp / 'crosscheck.json'}")
        info["crosscheck"] = {"types_match": True, "assemblies": report["assemblies"],
                              "method_gap_classes": sum(len(a["method_gaps"]) for a in report["assemblies"].values())}

    if not args.skip_java:
        apk = _java_apk(ctx, version)
        print(f"[code] decompiler {apk.name} -> {code}")
        java_info = ctx.adapter("decompiler").decompile(apk, code)
        PORTS["decompiler"].contract.verify(code)
        info["java"] = {"apk": apk.name, **java_info}
    return info
