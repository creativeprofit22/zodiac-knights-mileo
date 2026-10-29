"""type_info adapter: TypeTreeGeneratorAPI load_il2cpp (Cpp2IL) from binary + metadata.

Not enabled in zk.toml unless it is shown to load this build's metadata (see docs/ports/type_info.md).
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from zk.adapters import _typetree

PORT = "type_info"
NAME = "typetree_cpp2il"


class TypeTreeCpp2Il:
    def __init__(self, factory: _typetree.Factory = _typetree.default_factory,
                 has_il2cpp: Callable[[], bool] = _typetree.native_has_il2cpp) -> None:
        self.factory = factory
        self.has_il2cpp = has_il2cpp

    def types(self, binary: Path, metadata: Path, dump_dir: Path, unity_version: str,
              classes: Path, out: Path) -> dict:
        if not self.has_il2cpp():
            raise RuntimeError("type_info: this TypeTreeGeneratorAPI native build has no IL2CPP support "
                               "(TypeTreeGenerator_loadIL2CPP missing); use typetree_dummydll")
        gen = self.factory(unity_version)
        try:
            gen.load_il2cpp(Path(binary).read_bytes(), Path(metadata).read_bytes())
        except Exception as e:  # Cpp2IL failures come back as AssertionError from the binding
            raise RuntimeError(f"type_info: Cpp2IL could not load {metadata}: {e}") from e
        info = _typetree.dump_nodes(gen, unity_version, classes, out)
        return {"tool": _typetree.TOOL, "version": _typetree.tool_version(), "adapter": NAME,
                "unity_version": unity_version, **info}


def create(cfg: object) -> TypeTreeCpp2Il:
    return TypeTreeCpp2Il()
