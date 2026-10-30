"""il2cpp_assemblies adapter over Cpp2IL (self-contained exe): stub .NET assemblies from binary + metadata.

Runs `--output-as dummydll` into out/assemblies/ and logs to out/cpp2il.log. Cpp2IL loads plugins from its working
directory, so it runs inside `out`.
"""
from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from zk.core import toolchain
from zk.ports.il2cpp_assemblies import CONTRACT

PORT = "il2cpp_assemblies"
PINNED: tuple[str, ...] = ("cpp2il",)  # toolchain pins whose bump reruns this adapter's steps
TOOL = "cpp2il"
OUTPUT_FORMAT = "dummydll"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
Locate = Callable[[str, Path], Path]


def command(exe: Path, binary: Path, metadata: Path, unity_version: str, out: Path) -> list[str]:
    return [str(exe), "--force-binary-path", str(binary), "--force-metadata-path", str(metadata),
            "--force-unity-version", unity_version, "--output-as", OUTPUT_FORMAT,
            "--output-to", str(out / "assemblies")]


class Cpp2Il:
    def __init__(self, tools: Path, run: Runner = subprocess.run, locate: Locate = toolchain.path_of) -> None:
        self.tools = tools
        self.run = run
        self.locate = locate

    def build(self, binary: Path, metadata: Path, unity_version: str, out: Path) -> dict:
        if not unity_version:
            raise RuntimeError("Cpp2IL needs the game's Unity version, but none was given")
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        # stale DLLs from an earlier run would hide a failed build
        if (out / "assemblies").exists():
            shutil.rmtree(out / "assemblies")
        cmd = command(self.locate(TOOL, self.tools), binary, metadata, unity_version, out)
        print("[run]", " ".join(cmd))
        proc = self.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                        errors="replace", cwd=str(out), check=False)
        output = (proc.stdout or "") + (proc.stderr or "")
        (out / "cpp2il.log").write_text(output, encoding="utf-8")
        dlls = sorted((out / "assemblies").glob("*.dll")) if (out / "assemblies").is_dir() else []
        if proc.returncode != 0 or not dlls:
            raise RuntimeError(f"Cpp2IL failed (exit {proc.returncode}, {len(dlls)} DLLs): {output.strip()[-500:]}")
        CONTRACT.verify(out)
        tool = toolchain.TOOLS[TOOL]
        return {"tool": TOOL, "version": tool.version, "pin": tool.url, "output_as": OUTPUT_FORMAT,
                "dlls": len(dlls)}


def create(cfg: object) -> Cpp2Il:
    return Cpp2Il(getattr(cfg, "tools", Path.cwd() / "tools"))
