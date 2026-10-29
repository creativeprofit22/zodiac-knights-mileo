"""Artifact contracts: what a port promises to leave in its output folder."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactContract:
    port: str
    files: tuple[str, ...] = ()
    dirs: tuple[str, ...] = ()

    def missing(self, out_dir: Path) -> list[str]:
        out = Path(out_dir)
        gone = [f for f in self.files if not (out / f).is_file()]
        gone += [d + "/" for d in self.dirs if not (out / d).is_dir()]
        return gone

    def verify(self, out_dir: Path) -> None:
        if gone := self.missing(out_dir):
            raise RuntimeError(f"{self.port}: adapter output in {out_dir} is missing {', '.join(gone)}")
