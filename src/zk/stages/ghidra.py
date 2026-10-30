"""ghidra: an analyzed, symbol-named Ghidra project of libil2cpp.so and decompiled C per ZodiacKnights class.

Input: the il2cpp_dump output of `zk code` (only script.json and il2cpp.h) plus the unpacked libil2cpp.so.
Output: ghidra/<version>/ with targets.tsv, project/libil2cpp.gpr, functions/<Namespace>/<Class>.c, index.json.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from collections.abc import Iterable, Mapping

from zk.formats import il2cpp_script
from zk.ports import PORTS
from zk.stages._unpack import add_abi_argument, check_code_record, resolve_abi, unpack_inputs

NAME = "ghidra"
HELP = "analyze libil2cpp.so in headless Ghidra and export decompiled C per ZodiacKnights class"

# Root namespaces of engine, BCL and plugin code (Unity 6 packages: UnityEngine.InputSystem, Unity.Burst,
# Unity.Collections, Unity.Mathematics, Unity.RenderPipelines, UnityEngine.Timeline, ...); never exported.
THIRD_PARTY = frozenset({
    "UnityEngine", "UnityEngineInternal", "Unity", "System", "Mono", "Microsoft", "Internal", "JetBrains", "AOT",
    "Interop", "TMPro", "Firebase", "Google", "Kotlin", "kotlin", "Newtonsoft",
})
# Global-namespace owners that come from the engine or BCL (prefix match).
THIRD_PARTY_GLOBAL = (
    "Interop", "SR", "Locale", "UISupport", "UnitySourceGeneratedAssemblyMonoScriptTypes", "OnTilePostProcess",
    "RenderGraphCompilationCache", "FullScreenPassRendererFeature", "__JobReflectionRegistrationOutput__",
    "<PrivateImplementationDetails>", "<Module>", "$BurstDirectCallInitializer", "Microsoft", "TMP_", "Firebase", "Google",
)
GLOBAL_DIR = "_global"
GLOBAL_ROOT = "<global>"
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def add_arguments(p: argparse.ArgumentParser) -> None:
    add_abi_argument(p, "which libil2cpp.so to analyze")
    p.add_argument("--skip-analysis", action="store_true",
                   help="reuse the saved Ghidra project and only (re-)export missing .c files")
    p.add_argument("--filter", default=None, metavar="REGEX",
                   help="only export classes whose Namespace.Class matches REGEX")
    p.add_argument("--limit", type=int, default=None, metavar="N", help="only export the first N classes")
    p.add_argument("--force", action="store_true", help="delete earlier outputs (including the project) and rerun")


def is_game_class(namespace: str, cls: str) -> bool:
    if namespace:
        return namespace.split(".", 1)[0] not in THIRD_PARTY
    return not cls.startswith(THIRD_PARTY_GLOBAL)


def class_relpath(namespace: str, cls: str) -> str:
    return f"{_UNSAFE.sub('_', namespace) or GLOBAL_DIR}/{_UNSAFE.sub('_', cls)}.c"


def root_of(namespace: str) -> str:
    return namespace.split(".", 1)[0] if namespace else GLOBAL_ROOT


def select_targets(methods: Iterable[Mapping[str, object]], owners: frozenset[str], pattern: str | None = None,
                   limit: int | None = None) -> dict[tuple[str, str], list[int]]:
    """{(namespace, class): sorted distinct RVAs} of game classes, sorted by (namespace, class)."""
    rx = re.compile(pattern) if pattern else None
    found: dict[tuple[str, str], set[int]] = {}
    for m in methods:
        name, addr = m.get("Name"), m.get("Address")
        if not isinstance(name, str) or not isinstance(addr, int) or isinstance(addr, bool) or addr <= 0:
            continue
        resolved = il2cpp_script.resolve_class(name, owners)
        if resolved is None or not is_game_class(*resolved):
            continue
        ns, cls = resolved
        if rx and not rx.search(f"{ns}.{cls}" if ns else cls):
            continue
        found.setdefault(resolved, set()).add(addr)
    keys = sorted(found)
    if limit is not None:
        keys = keys[:max(limit, 0)]
    return {k: sorted(found[k]) for k in keys}


def target_lines(targets: Mapping[tuple[str, str], list[int]]) -> list[str]:
    return [f"{rva:x}\t{class_relpath(ns, cls)}" for (ns, cls), rvas in targets.items() for rva in rvas]


def execute(ctx, args: argparse.Namespace) -> dict:
    if args.filter:
        try:
            re.compile(args.filter)
        except re.error as e:
            raise RuntimeError(f"--filter {args.filter!r} is not a valid regex: {e}") from e
    version = ctx.ws.current_version()
    abi = resolve_abi(ctx, version, args.abi)
    binary, _, _ = unpack_inputs(ctx, version, abi)
    check_code_record(ctx, version, abi, "script.json")
    dump_dir = ctx.ws.root / "il2cpp" / version
    PORTS["il2cpp_dump"].contract.verify(dump_dir)
    script_path = dump_dir / "script.json"
    script = json.loads(script_path.read_text(encoding="utf-8"))
    try:
        il2cpp_script.validate(script)
    except ValueError as e:
        raise RuntimeError(f"{script_path}: {e}; rerun `zk code --force`") from e
    targets = select_targets(script["ScriptMethod"], il2cpp_script.type_owners(script), args.filter, args.limit)
    del script
    if not targets:
        raise RuntimeError("no ZodiacKnights classes selected" + (f" by --filter {args.filter!r}" if args.filter else ""))

    out = ctx.ws.dir("ghidra", version)
    if args.force:
        shutil.rmtree(out)
        out.mkdir(parents=True)
    targets_path = out / "targets.tsv"
    targets_path.write_text("".join(line + "\n" for line in target_lines(targets)), encoding="utf-8", newline="\n")
    roots: dict[str, int] = {}
    for ns, _cls in targets:
        roots[root_of(ns)] = roots.get(root_of(ns), 0) + 1

    mode = "export only (saved project)" if args.skip_analysis else "import + analysis + export"
    print(f"[ghidra] {binary.name} ({abi}): {len(targets)} classes, {mode} -> {out}")
    info = ctx.adapter("ghidra").analyze(binary, dump_dir, targets_path, out, args.skip_analysis)
    PORTS["ghidra"].contract.verify(out)
    return {"version": version, "abi": abi, "skip_analysis": args.skip_analysis, "filter": args.filter,
            "limit": args.limit, "classes_targeted": len(targets),
            "functions_targeted": sum(len(v) for v in targets.values()), "roots": dict(sorted(roots.items())),
            "analysis": info}
