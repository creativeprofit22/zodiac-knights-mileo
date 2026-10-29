"""The only UnityPy importer: loads assets/bin/Data and wraps each object as a plain AssetObject.

The rest of the stage sees only AssetObject/Loaded, so it is tested with fakes and never needs real Unity files.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol


RefNodes = dict[tuple[str, str, str], list[dict]]  # (class, namespace, assembly) -> nodes of a managed reference


class AssetObject(Protocol):
    file: str
    path_id: int
    type: str

    @property
    def name(self) -> str: ...
    def read(self) -> Any: ...
    def raw(self) -> bytes: ...
    def tree(self) -> dict: ...
    def read_nodes(self, nodes: list[dict], refs: RefNodes | None = None) -> Any: ...
    def script(self) -> tuple[str, str] | None: ...


@dataclass
class Loaded:
    objects: list[AssetObject]
    scenes: list[str] = field(default_factory=list)  # BuildSettings order: scene i lives in file level<i>
    files: int = 0
    unitypy: str = ""


def _unitypy() -> Any:
    try:
        import UnityPy
    except ImportError as e:
        raise RuntimeError('assets: UnityPy is not installed (pip install -e ".[assets]")') from e
    return UnityPy


class UnityObject:
    def __init__(self, reader: Any) -> None:
        self._r = reader
        self.file = str(reader.assets_file.name)
        self.path_id = int(reader.path_id)
        self.type = str(reader.type.name)

    @property
    def name(self) -> str:
        try:
            return str(self._r.peek_name() or "")
        except Exception:  # objects without m_Name (Transform, ...) have no name to peek
            return ""

    def read(self) -> Any:
        return self._r.read()

    def raw(self) -> bytes:
        return bytes(self._r.get_raw_data())

    def tree(self) -> dict:
        return self._r.read_typetree()

    def read_nodes(self, nodes: list[dict], refs: RefNodes | None = None) -> Any:
        if not refs:
            return self._r.read_typetree(nodes=nodes)
        from UnityPy.helpers.TypeTreeNode import TypeTreeNode

        # without type trees the file's ref_types carry no names or nodes; UnityPy resolves references through them
        f = self._r.assets_file
        saved = f.ref_types
        f.ref_types = [SimpleNamespace(m_ClassName=c, m_NameSpace=ns, m_AssemblyName=a, node=TypeTreeNode.from_list(n))
                       for (c, ns, a), n in sorted(refs.items())]
        try:
            return self._r.read_typetree(nodes=nodes)
        finally:
            f.ref_types = saved

    def script(self) -> tuple[str, str] | None:
        try:
            head = self._r.parse_monobehaviour_head()
            s = head.m_Script.deref_parse_as_object()
        except Exception:  # null or unresolved m_Script: the stage reports it as no_script
            return None
        cls = f"{s.m_Namespace}.{s.m_ClassName}" if s.m_Namespace else str(s.m_ClassName)
        return str(s.m_AssemblyName), cls


def _scenes(objects: list[UnityObject]) -> list[str]:
    for o in objects:
        if o.type == "BuildSettings":
            t = o.tree()
            return [str(s) for s in (t.get("scenes") or t.get("m_Scenes") or [])]
    return []


def load(data_dir: Path) -> Loaded:
    unitypy = _unitypy()
    env = unitypy.load(str(data_dir))
    objects = sorted((UnityObject(r) for r in env.objects), key=lambda o: (o.file, o.path_id))
    return Loaded(objects=list(objects), scenes=_scenes(objects), files=len(env.files),
                  unitypy=str(unitypy.__version__))
