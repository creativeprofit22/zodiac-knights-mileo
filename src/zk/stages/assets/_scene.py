"""Scene hierarchy as JSON: GameObjects, their components and script references, nested by Transform parent."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from zk.stages.assets._unity import AssetObject

TRANSFORMS = ("Transform", "RectTransform")
ScriptOf = Callable[[AssetObject], "tuple[str, str] | None"]


def _pid(ptr: Any) -> tuple[int, int]:
    if not isinstance(ptr, dict):
        return 0, 0
    return int(ptr.get("m_FileID", 0)), int(ptr.get("m_PathID", 0))


def _component_ptrs(go: dict) -> list[Any]:
    out = []
    for c in go.get("m_Component") or []:
        out.append(c.get("component", c.get("second")) if isinstance(c, dict) else c)
    return out


def hierarchy(objects: Sequence[AssetObject], script_of: ScriptOf) -> dict:
    """{"game_objects", "components", "roots": [{name, path_id, active, layer, components, children}]}."""
    by_pid = {o.path_id: o for o in objects}
    gos: dict[int, dict] = {}
    order: dict[int, list[int]] = {}
    n_components = 0
    for o in objects:
        if o.type != "GameObject":
            continue
        t = o.tree()
        comps = []
        for ptr in _component_ptrs(t):
            fid, pid = _pid(ptr)
            c = by_pid.get(pid) if fid == 0 else None
            entry: dict[str, Any] = {"path_id": pid, "type": c.type if c else None}
            if fid:
                entry["file_id"] = fid
            if c is not None and c.type == "MonoBehaviour":
                s = script_of(c)
                entry["script"] = {"assembly": s[0], "class": s[1]} if s else None
            if c is not None and c.type in TRANSFORMS:
                tr = c.tree()
                order[pid] = [_pid(ch)[1] for ch in tr.get("m_Children") or []]
                entry["transform"] = True
            comps.append(entry)
        n_components += len(comps)
        gos[o.path_id] = {"name": str(t.get("m_Name", "")), "path_id": o.path_id,
                          "active": bool(t.get("m_IsActive", True)), "layer": int(t.get("m_Layer", 0)),
                          "components": comps}
    go_of_transform = {c["path_id"]: g for g, d in gos.items() for c in d["components"] if c.get("transform")}
    children: dict[int, list[int]] = {g: [] for g in gos}
    for g, d in gos.items():
        tr = next((c["path_id"] for c in d["components"] if c.get("transform")), None)
        kids = [go_of_transform[k] for k in order.get(tr, []) if k in go_of_transform] if tr else []
        children[g] = kids
    child_set = {k for ks in children.values() for k in ks}

    def node(g: int, seen: frozenset[int]) -> dict:
        d = {**gos[g], "children": []}
        if g not in seen:
            d["children"] = [node(k, seen | {g}) for k in children[g] if k not in seen]
        return d

    roots = sorted(g for g in gos if g not in child_set)
    return {"game_objects": len(gos), "components": n_components, "roots": [node(g, frozenset()) for g in roots]}
