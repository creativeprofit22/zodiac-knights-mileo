"""device_source adapter for game files already on disk (a single .apk, or a folder of APK/OBB/data files).

There is no device to ask, so the version label comes from [options.device_source] in zk.toml:
    path = "raw/0.4.6-17"      # .apk file or folder; relative to zk.toml
    version = "0.4.6-17"
Adapted from SSA stages/import_.py (6e1be49).
"""
from __future__ import annotations

import shutil
from pathlib import Path

PORT = "device_source"
LAYOUT_DIRS = frozenset({"apk", "obb", "data"})  # a folder already in raw/<v>/ layout keeps its split


class FolderSource:
    def __init__(self, path: Path | None, version: str | None) -> None:
        self.path = path
        self.version = version

    def _source(self) -> Path:
        if self.path is None or not self.version:
            raise RuntimeError("folder adapter needs [options.device_source] path and version in zk.toml")
        if not self.path.exists():
            raise RuntimeError(f"folder adapter source {self.path} does not exist")
        return self.path

    def identify(self, package: str) -> dict:
        self._source()
        return {"package": package, "version": self.version, "abi": None}

    def pull(self, package: str, dest: Path) -> dict:
        src = self._source()
        dest = Path(dest)
        if src.is_file():
            if src.suffix.lower() != ".apk":
                raise RuntimeError(f"{src} is not an .apk file")
            plan = [(src, dest / "apk" / "base.apk")]
        else:
            plan = [(f, self._target(f.relative_to(src), dest)) for f in sorted(src.rglob("*")) if f.is_file()]
        apks = sorted(t.name for _, t in plan if t.parent == dest / "apk")
        if "base.apk" not in apks:
            raise RuntimeError(f"no base.apk found in {src}" if apks else f"no .apk found in {src}")
        if len(set(t for _, t in plan)) != len(plan):
            raise RuntimeError(f"{src} holds several files that map to the same destination (duplicate APK names?)")
        for f, target in plan:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
        obb = any(t.parent.name == "obb" and t.parent.parent == dest for _, t in plan)
        data = any(t.is_relative_to(dest / "data") for _, t in plan)
        return {"pulled": {"apk": apks, "obb": obb, "data": data}, "source": str(src)}

    @staticmethod
    def _target(rel: Path, dest: Path) -> Path:
        suffix = rel.suffix.lower()
        if suffix == ".apk":
            return dest / "apk" / rel.name
        if suffix == ".obb":
            return dest / "obb" / rel.name
        parts = rel.parts[1:] if len(rel.parts) > 1 and rel.parts[0] in LAYOUT_DIRS else rel.parts
        return dest.joinpath("data", *parts)


def create(cfg: object) -> FolderSource:
    opts: dict[str, str] = getattr(cfg, "options", {}).get(PORT, {})
    root: Path = getattr(cfg, "root", Path.cwd())
    raw = opts.get("path")
    path = None if not raw else (Path(raw) if Path(raw).is_absolute() else root / raw)
    return FolderSource(path, opts.get("version") or None)
