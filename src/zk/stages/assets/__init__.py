"""assets: export textures, sprites, audio, fonts, text, shaders, MonoBehaviours (via type_info) and scenes.

Inputs: unpacked/<v>/.../assets/bin/Data, il2cpp/<v>/ (dump + crosscheck summaries), the unity_version fact.
Outputs: assets/<v>/ (index.json, report.json, shaders.json, per-type folders), types/<v>/ (type_info).
"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

from zk.formats.unity_serialized import managed_reference_types
from zk.ports import PORTS
from zk.stages._unpack import unpack_inputs
from zk.stages.assets import _export, _known, _scene, _unity
from zk.stages.assets._compare import compare, tag_used

NAME = "assets"
PACKAGES: tuple[str, ...] = ("UnityPy",)  # pip dists whose version is part of the update fingerprint
HELP = "export Unity assets, MonoBehaviours (type_info port) and the scene hierarchy"
SCENE = "scene"
CHOICES = (*_export.TRACKED, SCENE)
SAVE_EVERY = 50
# engine files shipped with every player build; reported apart from the game's own files
BUILTIN_FILES = ("unity default resources", "unity_builtin_extra")


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--abi", default="arm64-v8a", help="libil2cpp.so passed to type_info (default: arm64-v8a)")
    p.add_argument("--force", action="store_true", help="delete assets/<v>/ and types/<v>/ and export again")
    p.add_argument("--only", nargs="+", choices=CHOICES, metavar="TYPE",
                   help=f"export only these ({', '.join(CHOICES)})")
    p.add_argument("--limit", type=int, default=0, help="export at most N objects this run (0 = all)")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_assembly(asm: str, cls: str, summary: dict) -> str:
    """MonoScript assembly, or the one dump assembly that defines `cls` when the named one does not."""
    assemblies = summary.get("assemblies", {})
    if cls in (assemblies.get(asm) or {}).get("classes", {}):
        return asm
    hits = sorted(a for a, s in assemblies.items() if cls in s.get("classes", {}))
    return hits[0] if len(hits) == 1 else asm


def _full(ns: str, cls: str) -> str:
    return f"{ns}.{cls}" if ns else cls


def reference_types(raw: bytes, summary: dict) -> list[tuple[str, str, str]]:
    """(class, namespace, assembly) of managed references named in `raw` that the dump knows."""
    assemblies = summary.get("assemblies", {})
    return [(c, ns, a) for c, ns, a in managed_reference_types(raw)
            if _full(ns, c) in (assemblies.get(a) or {}).get("classes", {})]


def _data_dir(metadata: Path) -> Path:
    data = metadata.parents[2]  # Data/Managed/Metadata/global-metadata.dat
    if not (data / "Managed").is_dir():
        raise RuntimeError(f"{data} does not look like assets/bin/Data: run `zk unpack --force`")
    return data


def _scene_name(path: str) -> str:
    return Path(path).stem or path


def _mb_section(entries: dict[str, dict]) -> dict:
    mbs = {k: e for k, e in entries.items() if e["type"] == "MonoBehaviour"}
    failed = {k: e for k, e in mbs.items() if e["status"] == "failed"}
    failures = []
    for k, e in sorted(failed.items()):
        cid = f"{e.get('assembly')}|{e.get('script')}"
        failures.append({"object": k, "script_class": e.get("script"), "assembly": e.get("assembly"),
                         "reason": e["reason"], "error": e["error"], "raw": e.get("out"),
                         "explanation": _known.MONOBEHAVIOURS.get(cid)})
    unexplained = [f["object"] for f in failures if not f["explanation"]]
    return {"total": len(mbs), "json": sum(e["status"] == "ok" for e in mbs.values()), "failed": len(failed),
            "by_reason": dict(sorted(Counter(e["reason"] for e in failed.values()).items())),
            "failures": failures, "unexplained": unexplained}


def execute(ctx, args: argparse.Namespace) -> dict:
    version = ctx.ws.current_version()
    binary, metadata, game = unpack_inputs(ctx, version, args.abi)
    code = ctx.ws.manifest().get("code")
    if not code or code.get("version") != version:
        raise RuntimeError(f"no code record for {version}: run `zk code` first")
    unity_version = str(ctx.ws.fact("unity_version"))
    data_dir = _data_dir(metadata)
    il2cpp = ctx.ws.dir("il2cpp", version)
    PORTS["il2cpp_dump"].contract.verify(il2cpp)
    cc_path = il2cpp / "crosscheck" / "summary.json"
    if not cc_path.is_file():
        raise RuntimeError(f"{cc_path} is missing: run `zk code` without --skip-crosscheck")
    summary = _read_json(il2cpp / "summary.json")
    out, types_dir = ctx.ws.dir("assets", version), ctx.ws.dir("types", version)
    if args.force:
        for d in (out, types_dir):
            shutil.rmtree(d)
            d.mkdir(parents=True)
    wanted = set(args.only or CHOICES)

    print(f"[assets] loading {data_dir}")
    loaded = _unity.load(data_dir)
    objects = loaded.objects
    inventory = Counter(o.type for o in objects if o.type in _export.TRACKED)
    builtin = Counter(o.type for o in objects if o.type in _export.TRACKED and o.file in BUILTIN_FILES)
    print(f"[assets] {loaded.files} files, {len(objects)} objects: {dict(sorted(inventory.items()))}")

    scripts: dict[str, tuple[str, str] | None] = {}
    resolved: dict[str, str] = {}
    obj_refs: dict[str, list[tuple[str, str, str]]] = {}
    for o in objects:
        if o.type == "MonoBehaviour":
            if found := reference_types(o.raw(), summary):
                obj_refs[_export.key_of(o)] = found
            s = o.script()
            if s is not None:
                asm = resolve_assembly(s[0], s[1], summary)
                if asm != s[0]:
                    resolved[f"{s[0]}|{s[1]}"] = asm
                s = (asm, s[1])
            scripts[_export.key_of(o)] = s
    classes = sorted({s for s in scripts.values() if s is not None})
    classes_path = types_dir / "classes.json"
    ref_classes = sorted({(a, _full(ns, c)) for refs in obj_refs.values() for c, ns, a in refs})
    request = [{"assembly": a, "class": c} for a, c in classes]
    request += [{"assembly": a, "class": c, "reference": True} for a, c in ref_classes]
    classes_path.write_text(json.dumps(request, indent=1), encoding="utf-8")
    print(f"[assets] type_info for {len(classes)} script classes (Unity {unity_version}) -> {types_dir}")
    ti_info = ctx.adapter("type_info").types(binary, metadata, il2cpp, unity_version, classes_path, types_dir)
    PORTS["type_info"].contract.verify(types_dir)
    nodes_doc = _read_json(types_dir / "nodes.json")
    nodes, missing = nodes_doc.get("classes", {}), nodes_doc.get("missing", {})
    ref_nodes = nodes_doc.get("references", {})

    def refs_of(key: str) -> dict[tuple[str, str, str], list[dict]]:
        return {(c, ns, a): ref_nodes[f"{a}|{_full(ns, c)}"] for c, ns, a in obj_refs.get(key, [])
                if f"{a}|{_full(ns, c)}" in ref_nodes}

    idx = _export.Index(out / _export.INDEX)
    done_now = 0
    try:
        for o in objects:
            if o.type not in _export.DIRS or o.type not in wanted:
                continue
            key = _export.key_of(o)
            if idx.done(key):
                continue
            if args.limit and done_now >= args.limit:
                break
            if o.type == "MonoBehaviour":
                entry = _export.export_monobehaviour(o, scripts.get(key), nodes, missing, out, idx, refs_of(key))
            else:
                entry = _export.export_media(o, out, idx)
            idx.put(key, entry)
            done_now += 1
            if done_now % SAVE_EVERY == 0:
                idx.save()
                print(f"[assets] {done_now} objects exported this run")
        if "Shader" in wanted:
            shaders = _export.shader_list(objects)
            (out / "shaders.json").write_text(json.dumps(shaders, indent=1, sort_keys=True), encoding="utf-8")
            for s in shaders:
                idx.put(f"{s['file']}:{s['path_id']}", {"type": "Shader", "name": s["name"], "out": "shaders.json",
                                                        "status": "ok", "error": None})
    finally:
        idx.save()

    scenes: dict[str, dict] = {}
    if SCENE in wanted:
        by_file: dict[str, list] = {}
        for o in objects:
            by_file.setdefault(o.file, []).append(o)
        sdir = out / "scenes"
        sdir.mkdir(exist_ok=True)
        for i, path in enumerate(loaded.scenes):
            file = f"level{i}"
            h = _scene.hierarchy(by_file.get(file, []), lambda c: scripts.get(_export.key_of(c)))
            h["objects"] = [{"type": o.type, "path_id": o.path_id} for o in by_file.get(file, [])]
            name = _scene_name(path)
            (sdir / f"{name}.json").write_text(json.dumps({"scene": path, "file": file, **h}, indent=1,
                                                          ensure_ascii=False), encoding="utf-8")
            scenes[path] = {"file": file, "json": f"scenes/{name}.json", "game_objects": h["game_objects"],
                            "components": h["components"], "roots": len(h["roots"]), "objects": len(h["objects"])}

    entries = idx.entries
    exported = Counter(e["type"] for e in entries.values() if e["status"] == "ok")
    misses = []
    for o in objects:
        if o.type not in _export.TRACKED or o.type == "MonoBehaviour":
            continue
        e = entries.get(_export.key_of(o))
        if not e or e["status"] != "ok":
            misses.append({"object": _export.key_of(o), "type": o.type, "name": o.name,
                           "error": e["error"] if e else "not exported yet"})

    used: dict[str, set[str]] = {}
    for a, c in [*classes, *ref_classes]:
        if a not in game:
            used.setdefault(a, set()).add(c)
    crosscheck = tag_used(compare(summary, _read_json(cc_path), used), used, _known.CROSSCHECK_RULES)
    mb = _mb_section(entries)
    report = {"version": version, "unity_version": unity_version, "unitypy": loaded.unitypy, "files": loaded.files,
              "inventory": dict(sorted(inventory.items())),
              "inventory_by_source": {"game": {t: inventory[t] - builtin.get(t, 0) for t in sorted(inventory)},
                                      "builtin": {t: builtin.get(t, 0) for t in sorted(inventory)},
                                      "builtin_files": list(BUILTIN_FILES)},
              "exported": {t: exported.get(t, 0) for t in sorted(inventory)},
              "misses": misses, "monobehaviours": mb, "assembly_resolution": dict(sorted(resolved.items())),
              "crosscheck": crosscheck, "scenes": scenes, "type_info": ti_info}
    (out / "report.json").write_text(json.dumps(report, indent=1, sort_keys=True, default=str), encoding="utf-8")
    print(f"[assets] exported {dict(sorted(exported.items()))}; {len(misses)} misses; "
          f"MonoBehaviours {mb['json']}/{mb['total']} JSON, {len(mb['unexplained'])} unexplained failures; "
          f"crosscheck unexplained {crosscheck['unexplained']}")
    problems = []
    if mb["unexplained"]:
        problems.append(f"{len(mb['unexplained'])} unexplained MonoBehaviour failures")
    if crosscheck["unexplained"]:
        problems.append(f"{crosscheck['unexplained']} unexplained crosscheck differences in used assemblies")
    if problems:
        raise RuntimeError(f"{'; '.join(problems)}; see {out / 'report.json'}")
    return {"version": version, "unity_version": unity_version, "out": str(out), "report": str(out / "report.json"),
            "inventory": report["inventory"], "exported": report["exported"], "misses": len(misses),
            "monobehaviours": {**{k: mb[k] for k in ("total", "json", "failed", "by_reason")},
                               "unexplained": len(mb["unexplained"])},
            "crosscheck": {"unexplained": crosscheck["unexplained"]},
            "scenes": scenes, "type_info": ti_info, "exported_this_run": done_now}
