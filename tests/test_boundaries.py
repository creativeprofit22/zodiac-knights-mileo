"""Import-boundary rule (ADR 0001), checked statically over the source tree."""
import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

# package prefix -> imports it must never make
FORBIDDEN = {
    "zk.core": ("zk.stages", "zk.adapters", "zk.cli"),
    "zk.formats": ("zk.stages", "zk.adapters", "zk.cli"),
    "zk.ports": ("zk.stages", "zk.adapters", "zk.cli"),
    "zk.stages": ("zk.adapters", "zk.core.toolchain", "zk.cli"),
    "zk.adapters": ("zk.stages", "zk.cli"),
    "zk.update": ("zk.adapters", "zk.cli"),
    "zk.steps": ("zk.adapters", "zk.stages", "zk.cli"),
}


def _module(path: Path, src: Path) -> tuple[str, bool]:
    parts = list(path.relative_to(src).with_suffix("").parts)
    is_pkg = parts[-1] == "__init__"
    return ".".join(parts[:-1] if is_pkg else parts), is_pkg


def _imports(path: Path, src: Path) -> list[str]:
    mod, is_pkg = _module(path, src)
    pkg = mod.split(".") if is_pkg else mod.split(".")[:-1]
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = pkg[: len(pkg) - (node.level - 1)]
                base = ".".join([*anchor, *([base] if base else [])])
            names.append(base)
            names += [f"{base}.{a.name}" for a in node.names]
    return names


def _under(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def _stage(name: str) -> str | None:
    parts = name.split(".")
    return parts[2] if len(parts) > 2 and parts[:2] == ["zk", "stages"] else None


def _cross_stage(mod: str, name: str) -> bool:
    # stages may share `_`-prefixed helpers (e.g. _unpack), never another stage's modules
    own, other = _stage(mod), _stage(name)
    return own is not None and other is not None and other != own and not other.startswith("_")


def violations(src: Path) -> list[str]:
    found = set()
    for path in sorted(src.joinpath("zk").rglob("*.py")):
        mod, _ = _module(path, src)
        banned = [b for owner, bs in FORBIDDEN.items() if _under(mod, owner) for b in bs]
        for name in _imports(path, src):
            if any(_under(name, b) for b in banned) or _cross_stage(mod, name):
                found.add(f"{mod} imports {name}")
    return sorted(found)


def test_real_tree_respects_boundaries():
    assert violations(SRC) == []


def _tree(tmp_path, files):
    for rel, text in {"zk/__init__.py": "", **files}.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return tmp_path


@pytest.mark.parametrize("rel, text, expect", [
    ("zk/core/x.py", "import zk.stages.code\n", "zk.core.x imports zk.stages.code"),
    ("zk/core/x.py", "from ..adapters import jadx\n", "zk.core.x imports zk.adapters"),
    ("zk/formats/f.py", "from zk.stages import code\n", "zk.formats.f imports zk.stages"),
    ("zk/formats/f.py", "from zk import adapters\n", "zk.formats.f imports zk.adapters"),
    ("zk/ports/p.py", "from zk.adapters.jadx import create\n", "zk.ports.p imports zk.adapters.jadx"),
    ("zk/stages/s.py", "from zk.adapters import jadx\n", "zk.stages.s imports zk.adapters"),
    ("zk/stages/s.py", "from ..core import toolchain\n", "zk.stages.s imports zk.core.toolchain"),
    ("zk/stages/pkg/__init__.py", "from ...adapters.ghidra import x\n", "zk.stages.pkg imports zk.adapters.ghidra"),
    ("zk/adapters/a.py", "from zk.stages import code\n", "zk.adapters.a imports zk.stages"),
    ("zk/update.py", "from .adapters import jadx\n", "zk.update imports zk.adapters"),
    ("zk/stages/code.py", "from zk.stages.assets._compare import compare\n",
     "zk.stages.code imports zk.stages.assets._compare"),
    ("zk/stages/csharp.py", "from .code import x\n", "zk.stages.csharp imports zk.stages.code"),
])
def test_violation_is_detected(tmp_path, rel, text, expect):
    assert expect in violations(_tree(tmp_path, {rel: text}))


def test_allowed_imports_pass(tmp_path):
    src = _tree(tmp_path, {
        "zk/stages/s.py": "from zk.ports import PORTS\nfrom ..core.workspace import Workspace\n",
        "zk/adapters/a.py": "from zk.core import toolchain\nfrom zk.ports.ghidra import CONTRACT\n",
        "zk/core/c.py": "from . import workspace\n",
        "zk/stages/pkg/__init__.py": "from zk.stages.pkg import _a\nfrom zk.stages._unpack import y\n",
    })
    assert violations(src) == []
