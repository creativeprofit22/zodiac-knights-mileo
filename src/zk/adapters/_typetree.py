"""Shared TypeTreeGeneratorAPI plumbing for the type_info adapters (lazy import; generator factory injectable)."""
from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from zk.ports.type_info import CONTRACT

TOOL = "TypeTreeGeneratorAPI"


class Generator(Protocol):
    def load_dll(self, dll: bytes) -> None: ...
    def load_il2cpp(self, il2cpp: bytes, metadata: bytes) -> None: ...
    def get_nodes(self, assembly: str, fullname: str) -> list: ...


Factory = Callable[[str], Generator]


def _module():
    try:
        # the package re-exports the class under the submodule's name, so `import a.b as m` gets the class
        ttg = importlib.import_module("TypeTreeGeneratorAPI.TypeTreeGenerator")
    except ImportError as e:
        raise RuntimeError('type_info: TypeTreeGeneratorAPI is not installed (pip install -e ".[assets]")') from e
    return ttg


def default_factory(unity_version: str) -> Generator:
    return _module().TypeTreeGenerator(unity_version)


def native_has_il2cpp() -> bool:
    ttg = _module()
    ttg.init_dll(None)
    return hasattr(ttg.DLL, "TypeTreeGenerator_loadIL2CPP")


def tool_version() -> str:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version(TOOL)
    except PackageNotFoundError:
        return "unknown"


def read_classes(classes: Path) -> list[tuple[str, str, bool]]:
    """(assembly, class, reference) per request; reference = a [SerializeReference] payload, not a component."""
    doc = json.loads(Path(classes).read_text(encoding="utf-8"))
    return sorted({(str(c["assembly"]), str(c["class"]), bool(c.get("reference", False))) for c in doc})


def fix_string_arrays(nodes: list[dict]) -> int:
    """Retype `string[]` fields that the generator emits as `string` (element type) to `vector`; return the count.

    A real string is `string > Array > [int size, char data]`; the bad node has `string data` elements instead.
    """
    fixed = 0
    for i, n in enumerate(nodes):
        if n["m_Type"] != "string" or i + 3 >= len(nodes):
            continue
        arr, size, data = nodes[i + 1], nodes[i + 2], nodes[i + 3]
        lvl = n["m_Level"]
        shape = (arr["m_Type"], arr["m_Level"], size["m_Level"], data["m_Level"], data["m_Type"])
        if shape == ("Array", lvl + 1, lvl + 2, lvl + 2, "string"):
            n["m_Type"] = "vector"
            fixed += 1
    return fixed


MONOBEHAVIOUR_HEADER = ("m_GameObject", "m_Enabled", "m_Script", "m_Name")


def strip_monobehaviour_header(nodes: list[dict]) -> list[dict]:
    """Drop the MonoBehaviour base fields the generator prepends to every class (managed references have none)."""
    top = [i for i, n in enumerate(nodes) if n["m_Level"] == 1]
    names = tuple(nodes[i]["m_Name"] for i in top[: len(MONOBEHAVIOUR_HEADER)])
    if names != MONOBEHAVIOUR_HEADER:
        return nodes
    cut = top[len(MONOBEHAVIOUR_HEADER)] if len(top) > len(MONOBEHAVIOUR_HEADER) else len(nodes)
    return nodes[:1] + nodes[cut:]


def dump_nodes(gen: Generator, unity_version: str, classes: Path, out: Path) -> dict:
    """Write nodes.json; each requested class lands in classes/missing, each reference in references/missing_references."""
    found: dict[str, dict[str, list[dict]]] = {"classes": {}, "references": {}}
    missing: dict[str, dict[str, str]] = {"classes": {}, "references": {}}
    fixes: dict[str, int] = {}
    for asm, name, reference in read_classes(classes):
        key, part = f"{asm}|{name}", "references" if reference else "classes"
        dll = asm if asm.endswith(".dll") else f"{asm}.dll"
        try:
            raw = gen.get_nodes(dll, name)
        except Exception as e:  # native errors surface as AssertionError/OSError; each one is recorded per class
            missing[part][key] = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            continue
        if not raw:
            missing[part][key] = "no nodes generated"
            continue
        nodes = [{"m_Type": n.m_Type, "m_Name": n.m_Name, "m_Level": int(n.m_Level),
                  "m_MetaFlag": int(n.m_MetaFlag)} for n in raw]
        if reference:
            nodes = strip_monobehaviour_header(nodes)
        if n_fixed := fix_string_arrays(nodes):
            fixes[key] = n_fixed
        found[part][key] = nodes
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    doc = {"unity_version": unity_version, "classes": found["classes"], "missing": missing["classes"],
           "references": found["references"], "missing_references": missing["references"]}
    (out / "nodes.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    CONTRACT.verify(out)
    return {"classes": len(found["classes"]), "missing": len(missing["classes"]),
            "references": len(found["references"]), "missing_references": len(missing["references"]),
            "string_array_fixes": dict(sorted(fixes.items()))}
