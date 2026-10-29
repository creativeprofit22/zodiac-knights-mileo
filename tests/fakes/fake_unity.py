"""Synthetic stand-ins for zk.stages.assets._unity objects (no UnityPy, no game files)."""
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from zk.stages.assets._unity import Loaded


class FakeImage:
    def save(self, path):
        path.write_bytes(b"\x89PNG fake")


@dataclass
class FakeObj:
    file: str
    path_id: int
    type: str
    name: str = ""
    payload: Any = None
    raw_bytes: bytes = b"RAW"
    tree_doc: dict = field(default_factory=dict)
    script_ref: tuple[str, str] | None = None
    read_fails: str = ""
    reads: int = 0

    def read(self):
        self.reads += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload

    def raw(self):
        return self.raw_bytes

    def tree(self):
        return self.tree_doc

    def read_nodes(self, nodes, refs=None):
        self.reads += 1
        self.refs = refs
        if self.read_fails:
            raise EOFError(self.read_fails)
        return {"m_Name": self.name, "nodes": len(nodes), **self.tree_doc}

    def script(self):
        return self.script_ref


def texture(pid, name="tex", width=4, file="sharedassets0.assets"):
    return FakeObj(file, pid, "Texture2D", name, SimpleNamespace(m_Width=width, image=FakeImage()))


def sprite(pid, name="spr"):
    return FakeObj("sharedassets0.assets", pid, "Sprite", name, SimpleNamespace(image=FakeImage()))


def audio(pid, name="clip", samples=None):
    return FakeObj("sharedassets0.assets", pid, "AudioClip", name,
                   SimpleNamespace(samples={"clip": b"RIFFwav"} if samples is None else samples))


def font(pid, name="font", data=b"\x00\x01\x00\x00ttf"):
    return FakeObj("sharedassets0.assets", pid, "Font", name, SimpleNamespace(m_FontData=data))


def text(pid, name="notes", script: str | bytes = "hello"):
    return FakeObj("sharedassets0.assets", pid, "TextAsset", name, SimpleNamespace(m_Script=script))


def shader(pid, name="URP/Lit"):
    return FakeObj("sharedassets0.assets", pid, "Shader", name)


def mono(pid, script, file="level0", name="", read_fails="", tree=None):
    return FakeObj(file, pid, "MonoBehaviour", name, script_ref=script, read_fails=read_fails,
                   tree_doc=tree or {}, raw_bytes=b"MB%d" % pid)


def scene_objects():
    """level0: Root (Canvas) -> Child (Image MonoBehaviour); a second root Lone."""
    go = lambda pid, name, comps, active=True: FakeObj(  # noqa: E731
        "level0", pid, "GameObject", name,
        tree_doc={"m_Name": name, "m_IsActive": active, "m_Layer": 5,
                  "m_Component": [{"component": {"m_FileID": 0, "m_PathID": c}} for c in comps]})
    tr = lambda pid, kind, go_pid, father, kids: FakeObj(  # noqa: E731
        "level0", pid, kind, tree_doc={"m_GameObject": {"m_FileID": 0, "m_PathID": go_pid},
                                       "m_Father": {"m_FileID": 0, "m_PathID": father},
                                       "m_Children": [{"m_FileID": 0, "m_PathID": k} for k in kids]})
    return [
        go(1, "Root", [11, 12]), tr(11, "RectTransform", 1, 0, [21]),
        mono(12, ("UnityEngine.UI", "UnityEngine.UI.CanvasScaler")),
        go(2, "Child", [21, 22], active=False), tr(21, "RectTransform", 2, 11, []),
        mono(22, ("UnityEngine.UI", "UnityEngine.UI.Image")),
        go(3, "Lone", [31]), tr(31, "Transform", 3, 0, []),
    ]


def loaded(objects, scenes=("Assets/_Project/Scenes/Main.unity",)):
    return Loaded(objects=list(objects), scenes=list(scenes), files=3, unitypy="fake")
