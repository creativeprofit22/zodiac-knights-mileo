"""decompiler adapter over jadx, run on the pinned JDK 21.

jadx exits non-zero when some methods fail to decompile; that is recorded, not fatal. Only a missing sources/ fails.
"""
from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from zk.core import toolchain
from zk.ports.decompiler import CONTRACT

PORT = "decompiler"
TOOL = "jadx"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
Locate = Callable[[str, Path], Path]
Env = Callable[[Path], dict[str, str]]


def command(exe: Path, apk: Path, out: Path) -> list[str]:
    return [str(exe), "-ds", str(out / "sources"), "--no-res", str(apk)]


def error_lines(output: str, keep: int = 10) -> list[str]:
    return [ln.strip() for ln in output.splitlines() if "ERROR" in ln][-keep:]


class Jadx:
    def __init__(self, tools: Path, run: Runner = subprocess.run, locate: Locate = toolchain.path_of,
                 env: Env = toolchain.java_env) -> None:
        self.tools = tools
        self.run = run
        self.locate = locate
        self.env = env

    def decompile(self, apk: Path, out: Path) -> dict:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        # a stale sources/ from an earlier run would hide a failed decompile
        if (out / "sources").exists():
            shutil.rmtree(out / "sources")
        cmd = command(self.locate(TOOL, self.tools), apk, out)
        print("[run]", " ".join(cmd))
        proc = self.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                        errors="replace", env=self.env(self.tools), check=False)
        output = (proc.stdout or "") + (proc.stderr or "")
        (out / "jadx.log").write_text(output, encoding="utf-8")
        if not (out / "sources").is_dir():
            raise RuntimeError(f"jadx (exit {proc.returncode}) wrote no sources/: {output.strip()[-500:]}")
        CONTRACT.verify(out)
        return {"tool": TOOL, "version": toolchain.TOOLS[TOOL].version, "exit_code": proc.returncode,
                "errors": error_lines(output), "java_files": sum(1 for _ in (out / "sources").rglob("*.java"))}


def create(cfg: object) -> Jadx:
    return Jadx(getattr(cfg, "tools", Path.cwd() / "tools"))
