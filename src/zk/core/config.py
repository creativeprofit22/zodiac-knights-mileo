"""Project configuration (zk.toml at the repo root, all keys optional; paths relative to the file's folder)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def default_root() -> Path:
    if (ROOT / "pyproject.toml").exists() and (ROOT / "src" / "zk").is_dir():
        return ROOT
    return Path.cwd()


TOP_LEVEL_KEYS = frozenset({"workspace", "tools", "package", "adapters", "options"})


@dataclass
class Config:
    root: Path = field(default_factory=default_root)
    package: str | None = None
    workspace: Path = field(default_factory=lambda: default_root() / "workspace")
    tools: Path = field(default_factory=lambda: default_root() / "tools")
    adapters: dict[str, str] = field(default_factory=dict)  # port name -> adapter module
    options: dict[str, dict[str, str]] = field(default_factory=dict)  # port name -> adapter settings

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        if path is None:
            path = default_root() / "zk.toml"  # the default config may be absent
        else:
            path = Path(path)
            if not path.exists():
                raise RuntimeError(f"config file not found: {path}")
        base = path.resolve().parent
        cfg = cls(root=base, workspace=base / "workspace", tools=base / "tools")
        if path.exists():
            try:
                data = tomllib.loads(path.read_text(encoding="utf-8"))
            except tomllib.TOMLDecodeError as e:
                raise RuntimeError(f"{path}: invalid TOML: {e}") from e
            from zk.ports import PORTS  # lazy: zk.ports imports zk.core

            if unknown := sorted(set(data) - TOP_LEVEL_KEYS):
                raise RuntimeError(f"{path}: unknown key {unknown[0]!r} "
                                   f"(valid: {', '.join(sorted(TOP_LEVEL_KEYS))})")
            if pkg := data.get("package"):
                cfg.package = pkg
            if ws := data.get("workspace"):
                cfg.workspace = (base / ws).resolve()
            if tl := data.get("tools"):
                cfg.tools = (base / tl).resolve()
            adapters = data.get("adapters", {})
            if not isinstance(adapters, dict) or not all(isinstance(v, str) for v in adapters.values()):
                raise RuntimeError(f"{path}: [adapters] must map port names to module names")
            if unknown := sorted(set(adapters) - set(PORTS)):
                raise RuntimeError(f"{path}: unknown port {unknown[0]!r} in [adapters] "
                                   f"(valid: {', '.join(sorted(PORTS))})")
            cfg.adapters = dict(adapters)
            options = data.get("options", {})
            if not isinstance(options, dict) or not all(
                    isinstance(t, dict) and all(isinstance(v, str) for v in t.values()) for t in options.values()):
                raise RuntimeError(f"{path}: [options.<port>] tables must map setting names to strings")
            if unknown := sorted(set(options) - set(PORTS)):
                raise RuntimeError(f"{path}: unknown port {unknown[0]!r} in [options] "
                                   f"(valid: {', '.join(sorted(PORTS))})")
            cfg.options = {port: dict(t) for port, t in options.items()}
        return cfg
