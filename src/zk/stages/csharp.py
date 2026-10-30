"""csharp: a browsable C# project per game assembly, reconstructed from IL2CPP (never the original source).

Input: assemblies built from binary + metadata (il2cpp_assemblies port) or the il2cpp_dump DummyDll/ (`--input dummydll`).
Output: csharp/<version>/ with assemblies/ (cpp2il input only), projects/<Asm>/, report.json and README.md.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from zk.ports import PORTS
from zk.stages._unpack import add_abi_argument, check_code_record, resolve_abi, unpack_inputs

NAME = "csharp"
HELP = "decompile the game assemblies into browsable C# projects (reconstructed, not the original source)"
INPUTS = ("cpp2il", "dummydll")

README = """# C# view of {version} (reconstructed)

Input: `{input}` ({source}).

IL2CPP compiles C# to native code, so the original C# can never be recovered. These projects rebuild
namespaces, types, fields, signatures and attributes from the IL2CPP metadata; method bodies are stubs
or best-effort reconstructions. See report.json for counts. For real logic, use the Ghidra stage.
"""

SOURCES = {"cpp2il": "assemblies built by the il2cpp_assemblies port from the binary and metadata",
           "dummydll": "DummyDll/ assemblies from the il2cpp_dump port (`zk code`)"}


def add_arguments(p: argparse.ArgumentParser) -> None:
    add_abi_argument(p, "which libil2cpp.so to read")
    p.add_argument("--input", choices=INPUTS, default="cpp2il",
                   help="build assemblies with il2cpp_assemblies (default) or reuse the il2cpp_dump DummyDll/")
    p.add_argument("--force", action="store_true", help="delete earlier outputs and rerun")


def _check_projects(out: Path, report: dict, game: list[str]) -> None:
    problems = []
    for name in sorted(game):
        proj = out / "projects" / name
        if not any(proj.glob("*.csproj")):
            problems.append(f"projects/{name} has no .csproj")
        if (report["assemblies"].get(name) or {}).get("types", 0) <= 0:
            problems.append(f"{name} has no types")
    if problems:
        raise RuntimeError("C# view is incomplete: " + "; ".join(problems))


def execute(ctx, args: argparse.Namespace) -> dict:
    version = ctx.ws.current_version()
    abi = resolve_abi(ctx, version, args.abi)
    binary, metadata, game = unpack_inputs(ctx, version, abi)
    if args.input == "dummydll":
        check_code_record(ctx, version, abi, "DummyDll/", ", or use --input cpp2il")
    out = ctx.ws.dir("csharp", version)
    if args.force:
        shutil.rmtree(out)
        out.mkdir(parents=True)

    built = None
    if args.input == "dummydll":
        assemblies = ctx.ws.root / "il2cpp" / version / "DummyDll"
        if not assemblies.is_dir():
            raise RuntimeError(f"{assemblies} is missing: run `zk code` first, or use --input cpp2il")
        if (out / "assemblies").exists():
            shutil.rmtree(out / "assemblies")
    else:
        unity = ctx.ws.fact("unity_version")
        print(f"[csharp] il2cpp_assemblies {binary.name} ({abi}, Unity {unity}) -> {out}")
        built = ctx.adapter("il2cpp_assemblies").build(binary, metadata, unity, out)
        PORTS["il2cpp_assemblies"].contract.verify(out)
        assemblies = out / "assemblies"

    print(f"[csharp] decompiler {', '.join(sorted(game))} -> {out / 'projects'}")
    dec = ctx.adapter("decompiler").decompile(assemblies, sorted(game), out)
    PORTS["decompiler"].contract.verify(out)
    report_path = out / "report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["input"] = args.input
    report_path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (out / "README.md").write_text(README.format(version=version, input=args.input, source=SOURCES[args.input]),
                                   encoding="utf-8")
    _check_projects(out, report, game)
    return {"version": version, "abi": abi, "input": args.input, "game_assemblies": sorted(game),
            "assemblies": built, "decompiler": dec,
            "report": {n: report["assemblies"][n] for n in sorted(game)}}
