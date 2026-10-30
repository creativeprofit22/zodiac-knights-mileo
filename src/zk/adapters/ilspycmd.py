"""decompiler adapter over ilspycmd (ILSpy native AOT): one C# project per assembly, then report.json.

Each name runs `-p -o projects/<name> -r <assemblies> <name>.dll` headless; the log goes to ilspycmd.log.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from zk.core import toolchain
from zk.formats import csharp_project
from zk.ports.decompiler import CONTRACT

PORT = "decompiler"
PINNED: tuple[str, ...] = ("ilspycmd",)  # toolchain pins whose bump reruns this adapter's steps
TOOL = "ilspycmd"
# ilspycmd exits 70 when some members failed; it still writes the project with the error text in their bodies.
PARTIAL_EXIT = 70
PARTIAL_LINE = re.compile(r"(\d+) error\(s\) occurred")

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
Locate = Callable[[str, Path], Path]


def command(exe: Path, dll: Path, refdir: Path, outdir: Path) -> list[str]:
    return [str(exe), "-p", "-o", str(outdir), "-r", str(refdir), "--disable-updatecheck", str(dll)]


def read_sources(projects: Path) -> dict[str, str]:
    """{"<Asm>/<path>.cs": text} for every C# file under projects/."""
    return {p.relative_to(projects).as_posix(): p.read_text(encoding="utf-8", errors="replace")
            for p in sorted(projects.rglob("*.cs"))}


class IlSpyCmd:
    def __init__(self, tools: Path, run: Runner = subprocess.run, locate: Locate = toolchain.path_of) -> None:
        self.tools = tools
        self.run = run
        self.locate = locate

    def decompile(self, assemblies: Path, names: list[str], out: Path) -> dict:
        assemblies, out = Path(assemblies), Path(out)
        if missing := [n for n in names if not (assemblies / f"{n}.dll").is_file()]:
            raise RuntimeError(f"ilspycmd: no {', '.join(m + '.dll' for m in missing)} in {assemblies}")
        out.mkdir(parents=True, exist_ok=True)
        projects = out / "projects"
        if projects.exists():
            shutil.rmtree(projects)
        exe = self.locate(TOOL, self.tools)
        log: list[str] = []
        exits: dict[str, int] = {}
        errors: dict[str, int] = {}
        for name in sorted(names):
            cmd = command(exe, assemblies / f"{name}.dll", assemblies, projects / name)
            print("[run]", " ".join(cmd))
            proc = self.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", check=False)
            output = (proc.stdout or "") + (proc.stderr or "")
            log.append(f"== {name} (exit {proc.returncode})\n{output}")
            exits[name] = proc.returncode
            partial = PARTIAL_LINE.search(output) if proc.returncode == PARTIAL_EXIT else None
            errors[name] = int(partial.group(1)) if partial else 0
            if (proc.returncode != 0 and not partial) or not (projects / name).is_dir():
                (out / "ilspycmd.log").write_text("\n".join(log), encoding="utf-8")
                raise RuntimeError(f"ilspycmd failed on {name} (exit {proc.returncode}): {output.strip()[-500:]}")
        (out / "ilspycmd.log").write_text("\n".join(log), encoding="utf-8")
        tool = {"name": TOOL, "version": toolchain.TOOLS[TOOL].version}
        summary = csharp_project.summarize(read_sources(projects))
        doc = csharp_project.report(summary, tool)
        (out / "report.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        CONTRACT.verify(out)
        return {"tool": TOOL, "version": tool["version"], "exit_codes": exits, "decompile_errors": errors,
                "cs_files": sum(1 for _ in projects.rglob("*.cs"))}


def create(cfg: object) -> IlSpyCmd:
    return IlSpyCmd(getattr(cfg, "tools", Path.cwd() / "tools"))
