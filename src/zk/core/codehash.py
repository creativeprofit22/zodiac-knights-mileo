"""Hash of the code that produced a stage result: the in-package import closure of the stage and its adapters.

A module's closure is the module plus every `zk.*` module it imports (also inside functions), recursively.
A package stage/adapter (`__init__.py`) contributes its whole folder, Ghidra `.java` scripts included.
zk.core.pins is left out on purpose: tool pins reach a fingerprint through the adapters that declare them
(`PINNED`), so bumping jadx reruns only the steps that run jadx.
"""
from __future__ import annotations

import ast
import hashlib
from collections.abc import Iterable, Mapping
from importlib import metadata
from pathlib import Path
from types import ModuleType

PKG = Path(__file__).resolve().parents[1]  # src/zk
PACKAGE = "zk"
HASHED = (".py", ".java")
EXCLUDED = frozenset({"zk.core.pins"})


def code_hash(sources: Mapping[str, bytes]) -> str:
    """sha256 over the sources, by path, with CRLF normalised (git may check out CRLF on Windows)."""
    h = hashlib.sha256()
    for path in sorted(sources):
        h.update(path.encode() + b"\0" + sources[path].replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def _in_tree(module: str) -> Path | None:
    """File of an in-package module (never imported, so planning has no side effects); None for non-modules."""
    parts = module.split(".")
    if parts[0] != PACKAGE or module in EXCLUDED:
        return None
    p = PKG.joinpath(*parts[1:])
    if (p / "__init__.py").is_file():
        return p / "__init__.py"
    if p.with_suffix(".py").is_file():
        return p.with_suffix(".py")
    return None


def imports_of(path: Path, module: str) -> list[str]:
    """Absolute `zk.*` names imported by `path` (module `module`), relative imports resolved."""
    is_pkg = path.name == "__init__.py"
    pkg = module.split(".") if is_pkg else module.split(".")[:-1]
    names: list[str] = []
    for node in ast.walk(ast.parse(path.read_bytes(), filename=str(path))):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level - 1 > len(pkg):
                    continue
                base = ".".join([*pkg[:len(pkg) - (node.level - 1)], *([node.module] if node.module else [])])
            else:
                base = node.module or ""
            names.append(base)
            names += [f"{base}.{a.name}" for a in node.names if a.name != "*"]
    return sorted({n for n in names if n == PACKAGE or n.startswith(PACKAGE + ".")})


def _files(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(p for p in path.rglob("*") if p.suffix in HASHED and p.is_file()
                      and "__pycache__" not in p.parts)
    return [path]


def _module_of(f: Path, module: str, root: Path) -> str:
    """Dotted module name of a .py file found under a package root."""
    if f == root:
        return module
    rel = f.relative_to(root).with_suffix("").parts
    rel = rel[:-1] if rel[-1] == "__init__" else rel
    return ".".join([module, *rel])


def _key(f: Path, module: str, root: Path) -> str:
    try:
        return f.relative_to(PKG.parent).as_posix()
    except ValueError:  # out of tree: key by module name so the hash is checkout-independent
        base = module.replace(".", "/")
        return f"{base}.py" if f == root else f"{base}/{f.relative_to(root).as_posix()}"


Source = tuple[str, "str | Path"]  # (module name, file)


def stage_sources(stage: Source, adapters: Iterable[Source] = ()) -> dict[str, bytes]:
    """Relative POSIX path -> bytes of the stage, its adapters and their in-package import closure."""
    out: dict[str, bytes] = {}
    todo: list[str] = []
    seen: set[str] = set()
    for module, file in [stage, *adapters]:
        root = Path(file).resolve()
        if root.name == "__init__.py":
            root = root.parent
        for f in _files(root):
            out[_key(f, module, root)] = f.read_bytes()
            if f.suffix == ".py":
                name = _module_of(f, module, root)
                seen.add(name)
                todo += imports_of(f, name)
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        if (f := _in_tree(name)) is None:
            continue
        out[_key(f, name, f)] = f.read_bytes()
        todo += imports_of(f, name)
    return out


def _package_version(dist: str) -> str:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return "missing"


def fingerprint_parts(stage: ModuleType, ports: Iterable[str], cfg: object) -> dict:
    """What a stage result depends on besides its inputs: code, chosen adapters, their pins, packages, options.

    Adapter modules are loaded, never created, so this touches no device and downloads nothing."""
    from zk.core import adapters, pins

    mods = {port: adapters.load_module(port, cfg) for port in sorted(set(ports))}
    sources = stage_sources((stage.__name__, str(stage.__file__)),
                            [(m.__name__, str(m.__file__)) for m in mods.values()])
    pinned = sorted({t for m in [stage, *mods.values()] for t in getattr(m, "PINNED", ())})
    packages = sorted({p for m in [stage, *mods.values()] for p in getattr(m, "PACKAGES", ())})
    tools = {}
    for name in pinned:
        tool = pins.TOOLS.get(name)
        tools[name] = f"{tool.version} {tool.sha256}" if tool else "unknown"
    options = getattr(cfg, "options", {})
    return {"code_hash": code_hash(sources),
            "adapters": {port: getattr(cfg, "adapters", {})[port] for port in mods},
            "tools": tools,
            "packages": {p: _package_version(p) for p in packages},
            "options": {port: dict(sorted(options.get(port, {}).items())) for port in mods}}
