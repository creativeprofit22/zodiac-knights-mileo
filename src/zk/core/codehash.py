"""Hash of the code that produced a stage result: stage + stages/_*.py + core/ports/formats + adapters used."""
from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]  # src/zk
SHARED = ("core", "ports", "formats")


def code_hash(sources: Mapping[str, bytes]) -> str:
    """sha256 over the sources, by path, with CRLF normalised (git may check out CRLF on Windows)."""
    h = hashlib.sha256()
    for path in sorted(sources):
        h.update(path.encode() + b"\0" + sources[path].replace(b"\r\n", b"\n") + b"\0")
    return h.hexdigest()


def _files(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)
    return [path]


Source = tuple[str, "str | Path"]  # (module name, file)


def _key(f: Path, module: str, root: Path) -> str:
    try:
        return f.relative_to(PKG.parent).as_posix()
    except ValueError:  # out of tree: key by module name so the hash is checkout-independent
        base = module.replace(".", "/")
        return f"{base}.py" if f == root else f"{base}/{f.relative_to(root).as_posix()}"


def stage_sources(stage: Source, adapters: Iterable[Source] = ()) -> dict[str, bytes]:
    """Relative POSIX path -> bytes. A package stage/adapter (`__init__.py`) contributes its whole folder."""
    roots = [(m, Path(f).resolve()) for m, f in [stage, *adapters]]
    roots = [(m, r.parent if r.name == "__init__.py" else r) for m, r in roots]
    roots += [(f"zk.{s}", (PKG / s).resolve()) for s in SHARED]
    # shared stage helpers (stages/_*.py) feed every stage that may import them
    roots += [(f"zk.stages.{f.stem}", f.resolve()) for f in sorted((PKG / "stages").glob("_*.py"))
              if f.name != "__init__.py"]
    out: dict[str, bytes] = {}
    for module, root in roots:
        for f in _files(root):
            out[_key(f, module, root)] = f.read_bytes()
    return out
