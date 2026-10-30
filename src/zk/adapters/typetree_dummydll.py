"""type_info adapter: TypeTreeGeneratorAPI over the il2cpp_dump DummyDll stubs (load_dll, sorted)."""
from __future__ import annotations

from pathlib import Path

from zk.adapters import _typetree
from zk.ports.il2cpp_dump import CONTRACT as DUMP_CONTRACT

PORT = "type_info"
PINNED: tuple[str, ...] = ()  # toolchain pins whose bump reruns this adapter's steps
PACKAGES: tuple[str, ...] = ("TypeTreeGeneratorAPI",)  # pip dists whose version is part of the update fingerprint
NAME = "typetree_dummydll"


class TypeTreeDummyDll:
    def __init__(self, factory: _typetree.Factory = _typetree.default_factory) -> None:
        self.factory = factory

    def types(self, binary: Path, metadata: Path, dump_dir: Path, unity_version: str,
              classes: Path, out: Path) -> dict:
        dump_dir = Path(dump_dir)
        DUMP_CONTRACT.verify(dump_dir)
        dlls = sorted((dump_dir / "DummyDll").glob("*.dll"))
        if not dlls:
            raise RuntimeError(f"type_info: no DLLs in {dump_dir / 'DummyDll'}")
        gen = self.factory(unity_version)
        for dll in dlls:
            gen.load_dll(dll.read_bytes())
        info = _typetree.dump_nodes(gen, unity_version, classes, out)
        return {"tool": _typetree.TOOL, "version": _typetree.tool_version(), "adapter": NAME,
                "unity_version": unity_version, "dlls": len(dlls), **info}


def create(cfg: object) -> TypeTreeDummyDll:
    return TypeTreeDummyDll()
