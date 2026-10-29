"""video_encoder port (contract v1): encodes a folder of numbered JPEG frames into one video file.

`encode(frames_dir, fps, out)` reads frame_*.jpg in name order and writes the file `out`; CONTRACT lists what it
must leave in out's folder. Changing this contract needs a new ADR.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from zk.core.contracts import ArtifactContract

PORT = "video_encoder"
OUTPUT = "encoded.mp4"
CONTRACT = ArtifactContract(PORT, files=(OUTPUT,))


@runtime_checkable
class VideoEncoder(Protocol):
    def encode(self, frames_dir: Path, fps: int, out: Path) -> dict: ...


def verify_output(out: Path) -> None:
    """The contract plus a non-empty file, which ArtifactContract alone does not check."""
    CONTRACT.verify(out.parent)
    if out.stat().st_size == 0:
        raise RuntimeError(f"{PORT}: {out} is empty")
