"""video_encoder adapter over a user-installed ffmpeg (found on PATH or via [options.video_encoder] path).

Nothing is downloaded: a missing ffmpeg is a clear error, and only `zk video --encode` ever asks for one.
"""
from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from zk.ports.video_encoder import verify_output

PORT = "video_encoder"
TOOL = "ffmpeg"
MISSING = "ffmpeg not found: install ffmpeg (or set [options.video_encoder] path) or drop --encode"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
Which = Callable[[str], "str | None"]


def command(exe: Path, frames_dir: Path, fps: int, out: Path) -> list[str]:
    return [str(exe), "-hide_banner", "-loglevel", "error", "-y", "-framerate", str(fps), "-start_number", "0",
            "-i", str(frames_dir / "frame_%04d.jpg"), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)]


def find(path: Path | None, which: Which | None = None) -> Path:
    if path is not None:
        if not path.is_file():
            raise RuntimeError(f"{MISSING} ([options.video_encoder] path {path} is not a file)")
        return path
    found = (which or shutil.which)(TOOL)
    if not found:
        raise RuntimeError(MISSING)
    return Path(found)


class Ffmpeg:
    def __init__(self, path: Path | None = None, run: Runner = subprocess.run, which: Which | None = None) -> None:
        self.path = path
        self.run = run
        self.which = which

    def encode(self, frames_dir: Path, fps: int, out: Path) -> dict:
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")
        exe = find(self.path, self.which)
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = command(exe, Path(frames_dir), fps, out)
        print("[run]", " ".join(cmd))
        proc = self.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                        errors="replace", check=False)
        if proc.returncode != 0:
            output = (proc.stdout or "") + (proc.stderr or "")
            raise RuntimeError(f"ffmpeg exit {proc.returncode}: {output.strip()[-500:]}")
        verify_output(out)
        return {"tool": TOOL, "exe": str(exe), "fps": fps, "bytes": out.stat().st_size}


def create(cfg: object) -> Ffmpeg:
    opts: dict[str, str] = getattr(cfg, "options", {}).get(PORT, {})
    root: Path = getattr(cfg, "root", Path.cwd())
    raw = opts.get("path")
    return Ffmpeg(None if not raw else (Path(raw) if Path(raw).is_absolute() else root / raw))
