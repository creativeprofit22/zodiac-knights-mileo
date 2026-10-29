from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import adapters
from .config import Config
from .workspace import Workspace


@dataclass
class Context:
    cfg: Config
    ws: Workspace
    used: dict[str, dict] = field(default_factory=dict)  # port -> adapter used this run (for the manifest)

    @classmethod
    def create(cls, config_path: Path | None = None) -> "Context":
        cfg = Config.load(config_path)
        return cls(cfg, Workspace(cfg.workspace))

    def adapter(self, port: str):
        impl, mod = adapters.resolve(port, self.cfg)
        self.used[port] = {"adapter": self.cfg.adapters[port], "module": mod.__name__, "file": mod.__file__}
        return impl
