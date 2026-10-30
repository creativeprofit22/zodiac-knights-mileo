"""il2cpp_crosscheck adapter over Il2CppInspectorRedux (Legacy CLI), run on the portable .NET 10 runtime.

Il2CppInspectorRedux is AGPL-3.0: it is only downloaded (pinned in TOOLS) and run as a separate program, never vendored.
Writes C# per assembly into out/cs/ (all namespaces kept) and summarizes it into summary.json.
"""
from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from zk.core import toolchain
from zk.formats import csharp_dump
from zk.ports.il2cpp_crosscheck import CONTRACT

PORT = "il2cpp_crosscheck"
PINNED: tuple[str, ...] = ("il2cppinspector", "dotnet10")  # toolchain pins whose bump reruns this adapter's steps
TOOL = "il2cppinspector"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
Locate = Callable[[str, Path], Path]
Env = Callable[[Path], dict[str, str]]


def command(exe: Path, binary: Path, metadata: Path, out: Path) -> list[str]:
    return [str(exe), "-i", str(binary), "-m", str(metadata), "--select-outputs", "-c", str(out / "cs"),
            "-l", "assembly", "-e", "none"]


class Il2CppInspector:
    def __init__(self, tools: Path, run: Runner = subprocess.run, locate: Locate = toolchain.path_of,
                 env: Env = toolchain.dotnet_env) -> None:
        self.tools = tools
        self.run = run
        self.locate = locate
        self.env = env

    def crosscheck(self, binary: Path, metadata: Path, out: Path) -> dict:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        cmd = command(self.locate(TOOL, self.tools), binary, metadata, out)
        print("[run]", " ".join(cmd))
        proc = self.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                        errors="replace", env=self.env(self.tools), check=False)
        output = (proc.stdout or "") + (proc.stderr or "")
        (out / "il2cppinspector.log").write_text(output, encoding="utf-8")
        if proc.returncode != 0:
            raise RuntimeError(f"Il2CppInspector failed (exit {proc.returncode}): {output.strip()[-500:]}")
        files = {f.relative_to(out / "cs").as_posix(): f.read_text(encoding="utf-8", errors="replace")
                 for f in sorted((out / "cs").rglob("*.cs"))} if (out / "cs").is_dir() else {}
        if not files:
            raise RuntimeError(f"Il2CppInspector finished but wrote no C# files to {out / 'cs'}")
        summary = csharp_dump.summarize_inspector(files)
        (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        CONTRACT.verify(out)
        return {"tool": TOOL, "version": toolchain.TOOLS[TOOL].version, "files": len(files)}


def create(cfg: object) -> Il2CppInspector:
    return Il2CppInspector(getattr(cfg, "tools", Path.cwd() / "tools"))
