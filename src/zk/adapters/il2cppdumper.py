"""il2cpp_dump adapter over Il2CppDumper (AndnixSH fork, CLI since 3.2.1), run on the portable .NET 10 runtime.

The tool writes dump.cs, script.json, il2cpp.h and DummyDll/; this adapter then checks script.json and writes summary.json.
"""
from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from zk.core import toolchain
from zk.formats import csharp_dump, il2cpp_script
from zk.ports.il2cpp_dump import CONTRACT

PORT = "il2cpp_dump"
TOOL = "il2cppdumper"
TOOL_FILES = ("dump.cs", "script.json", "il2cpp.h")
_ERROR = re.compile(r"\b(?:error|exception)\b", re.IGNORECASE)
# Printed when JNI_OnLoad is not found; the registration search still runs and the dump completes.
_BENIGN = ("This file may be protected.",)

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
Locate = Callable[[str, Path], Path]
Env = Callable[[Path], dict[str, str]]


def command(exe: Path, binary: Path, metadata: Path, out: Path) -> list[str]:
    return [str(exe), str(binary), str(metadata), str(out), "--no-pause"]


def error_lines(output: str) -> list[str]:
    return [ln.strip() for ln in output.splitlines()
            if _ERROR.search(ln) and not ln.strip().endswith(_BENIGN)]


def totals(summary: csharp_dump.Summary) -> dict[str, int]:
    asms = summary["assemblies"].values()
    return {"assemblies": len(summary["assemblies"]), "types": sum(a["types"] for a in asms),
            "methods": sum(a["methods"] for a in asms)}


class Il2CppDumper:
    def __init__(self, tools: Path, run: Runner = subprocess.run, locate: Locate = toolchain.path_of,
                 env: Env = toolchain.dotnet_env) -> None:
        self.tools = tools
        self.run = run
        self.locate = locate
        self.env = env

    def dump(self, binary: Path, metadata: Path, out: Path) -> dict:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        cmd = command(self.locate(TOOL, self.tools), binary, metadata, out)
        print("[run]", " ".join(cmd))
        # stdin closed: the tool must never wait for a key press
        proc = self.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                        errors="replace", env=self.env(self.tools), check=False)
        output = (proc.stdout or "") + (proc.stderr or "")
        (out / "il2cppdumper.log").write_text(output, encoding="utf-8")
        errors = error_lines(output)
        if proc.returncode != 0 or errors:
            detail = "; ".join(errors[-5:]) or output.strip()[-500:]
            raise RuntimeError(f"Il2CppDumper failed (exit {proc.returncode}): {detail}")
        if gone := [f for f in TOOL_FILES if not (out / f).is_file()] + \
                [d + "/" for d in CONTRACT.dirs if not (out / d).is_dir()]:
            raise RuntimeError(f"Il2CppDumper finished but left no {', '.join(gone)} in {out}")
        try:
            script = il2cpp_script.validate(json.loads((out / "script.json").read_text(encoding="utf-8")))
        except (ValueError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Il2CppDumper script.json is not valid: {e}") from e
        try:
            summary = csharp_dump.summarize_dumper((out / "dump.cs").read_text(encoding="utf-8", errors="replace"))
        except ValueError as e:
            raise RuntimeError(f"Il2CppDumper dump.cs could not be summarized: {e}") from e
        (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        CONTRACT.verify(out)
        return {"tool": TOOL, "version": toolchain.TOOLS[TOOL].version, "totals": totals(summary),
                "script": script.as_dict()}


def create(cfg: object) -> Il2CppDumper:
    return Il2CppDumper(getattr(cfg, "tools", Path.cwd() / "tools"))
