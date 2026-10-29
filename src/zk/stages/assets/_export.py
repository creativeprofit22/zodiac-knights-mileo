"""Per-object exporters and the resumable index (adapted from SSA's export helpers, minus its bundle sources).

Each exporter writes one object and returns an index entry; a failure is an entry too, never an exception.
MonoBehaviours are read with type_info nodes; when that fails their raw bytes are kept under raw/.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from zk.stages.assets._unity import AssetObject, RefNodes

DIRS = {"Texture2D": "textures", "Sprite": "sprites", "AudioClip": "audio", "Font": "fonts", "TextAsset": "text",
        "MonoBehaviour": "monobehaviours"}
LISTED = ("Shader",)
TRACKED = tuple(sorted((*DIRS, *LISTED)))
INDEX = "index.json"
_UNSAFE = re.compile(r"[^\w.\- ]+")


class Miss(Exception):
    """An object that cannot be exported for a known reason (e.g. an empty texture)."""


def safe_name(name: str, fallback: str) -> str:
    s = _UNSAFE.sub("_", name).strip(" .")[:80]
    return s or fallback


def key_of(obj: AssetObject) -> str:
    return f"{obj.file}:{obj.path_id}"


class Index:
    """{"<file>:<path_id>": {type, name, out, status, ...}}, written atomically (tmp + replace)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.entries: dict[str, dict] = (json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {})
        self.owners = {e["out"]: k for k, e in self.entries.items() if e.get("out")}

    def done(self, key: str) -> bool:
        e = self.entries.get(key)
        # failures are retried every run, so a parser or type_info fix reaches them
        return bool(e) and e.get("status") == "ok" and bool(e.get("out")) \
            and (self.path.parent / e["out"]).is_file()

    def put(self, key: str, entry: dict) -> None:
        self.entries[key] = entry
        if entry.get("out"):
            self.owners[entry["out"]] = key

    def target(self, root: Path, rel_dir: str, stem: str, ext: str, key: str, file: str) -> Path:
        """Output path for `key`; a name another object already owns gets the source file name added."""
        rel = f"{rel_dir}/{stem}{ext}"
        if self.owners.get(rel, key) != key:
            rel = f"{rel_dir}/{stem}_{file}{ext}"
        self.owners[rel] = key
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.entries, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)


def _rel(p: Path, root: Path) -> str:
    return p.relative_to(root).as_posix()


def _write_media(obj: AssetObject, o: Any, root: Path, idx: Index) -> str:
    key, stem = key_of(obj), f"{safe_name(obj.name or str(getattr(o, 'm_Name', '') or ''), 'unnamed')}_{obj.path_id}"
    d = DIRS[obj.type]
    if obj.type in ("Texture2D", "Sprite"):
        if obj.type == "Texture2D" and not getattr(o, "m_Width", 0):
            raise Miss("empty texture (m_Width 0)")
        dst = idx.target(root, d, stem, ".png", key, obj.file)
        o.image.save(dst)
        return _rel(dst, root)
    if obj.type == "AudioClip":
        samples = o.samples
        if not samples:
            raise Miss("no decodable samples")
        first = None
        for i, (sname, wav) in enumerate(sorted(samples.items())):
            s = stem if len(samples) == 1 else f"{stem}_{i}_{safe_name(sname, str(i))}"
            dst = idx.target(root, d, s, ".wav", key, obj.file)
            dst.write_bytes(bytes(wav))
            first = first or dst
        assert first is not None
        return _rel(first, root)
    if obj.type == "Font":
        data = bytes(getattr(o, "m_FontData", b"") or b"")
        if not data:
            raise Miss("no embedded font data")
        dst = idx.target(root, d, stem, ".otf" if data[:4] == b"OTTO" else ".ttf", key, obj.file)
        dst.write_bytes(data)
        return _rel(dst, root)
    if obj.type == "TextAsset":
        script = o.m_Script
        data = script.encode("utf-8", "surrogateescape") if isinstance(script, str) else bytes(script)
        try:
            data.decode("utf-8")
            ext = ".txt"
        except UnicodeDecodeError:
            ext = ".bytes"
        dst = idx.target(root, d, stem, ext, key, obj.file)
        dst.write_bytes(data)
        return _rel(dst, root)
    raise ValueError(f"no exporter for {obj.type}")


def export_media(obj: AssetObject, root: Path, idx: Index) -> dict:
    entry: dict[str, Any] = {"type": obj.type, "name": obj.name, "out": None}
    try:
        entry.update(out=_write_media(obj, obj.read(), root, idx), status="ok", error=None)
    except Miss as e:
        entry.update(status="missed", error=str(e))
    except Exception as e:  # one bad object must not stop the export; it is named in the report
        entry.update(status="missed", error=f"{type(e).__name__}: {e}"[:300])
    return entry


def _raw(obj: AssetObject, root: Path, idx: Index) -> str | None:
    try:
        data = obj.raw()
    except Exception:  # unreadable bytes: the failure entry still names the object
        return None
    dst = idx.target(root, "raw", f"{obj.file}_{obj.path_id}", ".bin", key_of(obj), obj.file)
    dst.write_bytes(data)
    return _rel(dst, root)


def export_monobehaviour(obj: AssetObject, script: tuple[str, str] | None, nodes: dict[str, list[dict]],
                         missing: dict[str, str], root: Path, idx: Index, refs: RefNodes | None = None) -> dict:
    """JSON through the type_info nodes for `script` (assembly, class); raw bytes plus a reason otherwise."""
    entry: dict[str, Any] = {"type": obj.type, "name": obj.name, "script": None, "assembly": None}
    if script is None:
        reason, error = "no_script", "m_Script does not resolve to a MonoScript"
    else:
        asm, cls = script
        cid = f"{asm}|{cls}"
        entry.update(script=cls, assembly=asm)
        if cid in missing or cid not in nodes:
            reason, error = "class_missing_in_type_info", missing.get(cid, "class not in nodes.json")
        else:
            try:
                tree = obj.read_nodes(nodes[cid], refs)
            except Exception as e:  # nodes that do not fit the bytes: keep the raw object
                reason, error = "read_error", f"{type(e).__name__}: {e}"[:300]
            else:
                stem = f"{safe_name(obj.name, 'unnamed')}_{obj.path_id}"
                dst = idx.target(root, f"monobehaviours/{safe_name(asm, 'asm')}/{safe_name(cls, 'cls')}", stem,
                                 ".json", key_of(obj), obj.file)
                dst.write_text(json.dumps(tree, indent=1, ensure_ascii=False, sort_keys=True, default=str),
                               encoding="utf-8", errors="surrogateescape")
                entry.update(out=_rel(dst, root), status="ok", error=None, reason=None)
                return entry
    entry.update(out=_raw(obj, root, idx), status="failed", error=error, reason=reason)
    return entry


def shader_list(objects: list[AssetObject]) -> list[dict]:
    return [{"file": o.file, "path_id": o.path_id, "name": o.name} for o in objects if o.type == "Shader"]
