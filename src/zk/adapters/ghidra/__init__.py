"""ghidra adapter: Ghidra 12.2 analyzeHeadless on the portable JDK 25 (ported from SSA 6e1be49).

One headless run imports libil2cpp.so into `out/project/libil2cpp.gpr`, applies the dumper's names, signatures
and il2cpp.h types (preScript Il2CppImport.java), auto-analyses, then decompiles the target functions to
`out/functions/<Ns>/<Class>.c` (postScript Il2CppExport.java, resumable). With skip_analysis it reopens the saved
project read-only and only exports. analyzeHeadless exits 0 even when the import fails, so success is judged from
this run's `ERROR (HeadlessAnalyzer)` log lines.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

from zk.core import toolchain
from zk.ports.ghidra import CONTRACT

PORT = "ghidra"
PINNED: tuple[str, ...] = ("ghidra", "jdk25")  # toolchain pins whose bump reruns this adapter's steps
UNFINGERPRINTED_OPTIONS: tuple[str, ...] = ("maxmem",)  # JVM heap only: changing it must not redo the analysis
TOOL = "ghidra"
JDK = "jdk25"
PROJECT = "libil2cpp"
SCRIPTS = Path(__file__).resolve().parent / "scripts"
DEFAULT_MAXMEM = "12G"
DEFAULT_TIMEOUT = 30  # seconds per function, Il2CppExport.java

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
Locate = Callable[[str, Path], Path]
Clock = Callable[[], datetime]

# Same fix-up as Il2CppDumper's il2cpp_header_to_ghidra.py: MSVC integer types, and C++ `struct X : Base {`
# inheritance turned into a leading `Base super;` member that CParser understands.
HEADER_PRELUDE = "".join(f"typedef {a} {b};\n" for a, b in (
    ("unsigned __int8", "uint8_t"), ("unsigned __int16", "uint16_t"),
    ("unsigned __int32", "uint32_t"), ("unsigned __int64", "uint64_t"),
    ("__int8", "int8_t"), ("__int16", "int16_t"), ("__int32", "int32_t"),
    ("__int64", "int64_t"), ("__int64", "intptr_t"), ("__int64", "uintptr_t"),
    ("unsigned __int64", "size_t"), ("_Bool", "bool")))
_INHERIT = re.compile(r": (\w+) {")
_STAMP = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def _clean(s: str) -> str:
    return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\r", "\\r").replace("\n", "\\n")


def symbol_lines(script: dict) -> Iterator[str]:
    """script.json -> TSV lines for Il2CppImport.java (kind, rva hex, name, signature)."""
    for a in script.get("Addresses", [])[:-1]:
        yield f"A\t{a:x}\t\t"
    for m in script.get("ScriptMethod", []):
        yield f"F\t{m['Address']:x}\t{_clean(m['Name'])}\t{_clean(m['Signature'].rstrip(';'))}"
    for i, s in enumerate(script.get("ScriptString", [])):
        yield f"S\t{s['Address']:x}\tStringLiteral_{i}\t{_clean(s['Value'])}"
    for m in script.get("ScriptMetadata", []):
        yield f"M\t{m['Address']:x}\t{_clean(m['Name'])}\t{_clean(m.get('Signature') or '')}"
    for m in script.get("ScriptMetadataMethod", []):
        yield f"N\t{m['Address']:x}\t{_clean(m['Name'])}\t"


def ghidra_header(il2cpp_h: str) -> str:
    return HEADER_PRELUDE + _INHERIT.sub(r"{\n \1 super;", il2cpp_h)


def headless_cmd(headless: Path, project_dir: Path, binary: Path, symbols: Path, header: Path,
                 targets: Path, functions: Path, log: Path, skip_analysis: bool,
                 timeout: int = DEFAULT_TIMEOUT) -> list[str]:
    cmd = [str(headless), str(project_dir), PROJECT]
    if skip_analysis:
        cmd += ["-process", binary.name, "-noanalysis", "-readOnly"]
    else:
        cmd += ["-import", str(binary), "-overwrite"]
    cmd += ["-scriptPath", str(SCRIPTS), "-log", str(log), "-scriptlog", str(log.with_suffix(".script.log"))]
    if not skip_analysis:
        cmd += ["-preScript", "Il2CppImport.java", str(symbols), str(header), "true"]
    cmd += ["-postScript", "Il2CppExport.java", str(targets), str(functions), str(timeout)]
    return cmd


def headless_errors(log_text: str) -> list[str]:
    """`ERROR (HeadlessAnalyzer)` lines (failed import, script error); analyzer noise like
    `ERROR (LSDACallSiteTable)` is not fatal and is ignored."""
    return [line.split("(HeadlessAnalyzer)", 1)[1].strip() for line in log_text.splitlines()
            if "ERROR (HeadlessAnalyzer)" in line]


def run_lines(log_text: str, since: datetime) -> str:
    """Lines of a Ghidra log stamped at or after `since` (local time); unstamped continuation lines follow the
    last stamped one. By time, not offset: Ghidra appends to headless.log and rotates it by size mid-run."""
    cut = since.strftime("%Y-%m-%d %H:%M:%S")
    keep, out = False, []
    for line in log_text.splitlines(keepends=True):
        if m := _STAMP.match(line):
            keep = m.group(1) >= cut
        if keep:
            out.append(line)
    return "".join(out)


def run_logs(log: Path, since: datetime) -> list[Path]:
    """headless.log plus its rotated `headless.log-*` siblings modified since `since`, oldest name first."""
    rotated = [p for p in log.parent.glob(f"{log.name}-*") if p.stat().st_mtime >= since.timestamp()]
    return sorted(rotated) + ([log] if log.exists() else [])


def ghidra_env(jdk_home: Path, maxmem: str, base: dict[str, str]) -> dict[str, str]:
    env = dict(base)
    env["JAVA_HOME"] = str(jdk_home)
    env["GHIDRA_HEADLESS_MAXMEM"] = maxmem
    env["PATH"] = str(jdk_home / "bin") + os.pathsep + base.get("PATH", "")
    return env


def pin_jdk(ghidra_home: Path, jdk_home: Path) -> None:
    """Ghidra asks for a JDK on first run: pin ours in its (tools/-local) launch.properties."""
    props = ghidra_home / "support" / "launch.properties"
    text = props.read_text(encoding="utf-8")
    new = re.sub(r"(?m)^JAVA_HOME_OVERRIDE=.*$", lambda _: f"JAVA_HOME_OVERRIDE={jdk_home.as_posix()}", text)
    if new != text:
        props.write_text(new, encoding="utf-8")


def read_targets(targets: Path) -> dict[str, int]:
    """targets.tsv -> {relpath: distinct functions}."""
    by_file: dict[str, set[str]] = {}
    for line in targets.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rva, rel = line.split("\t", 1)
            by_file.setdefault(rel, set()).add(rva)
    return {rel: len(rvas) for rel, rvas in sorted(by_file.items())}


def failed_functions(text: str) -> int:
    """Functions Il2CppExport.java could not decompile in one class file (timeouts, decompiler errors)."""
    return sum(1 for line in text.splitlines() if line.startswith("// decompilation failed"))


class GhidraHeadless:
    def __init__(self, tools: Path, run: Runner = subprocess.run, locate: Locate = toolchain.path_of,
                 maxmem: str = DEFAULT_MAXMEM, clock: Clock = datetime.now, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.tools = tools
        self.run = run
        self.locate = locate
        self.maxmem = maxmem
        self.timeout = timeout
        self.clock = clock

    def analyze(self, binary: Path, dump_dir: Path, targets: Path, out: Path, skip_analysis: bool) -> dict:
        out = Path(out)
        project, functions = out / "project", out / "functions"
        if skip_analysis and not (project / f"{PROJECT}.gpr").exists():
            raise RuntimeError(f"no Ghidra project in {project}: run without --skip-analysis first")
        project.mkdir(parents=True, exist_ok=True)
        functions.mkdir(parents=True, exist_ok=True)
        for part in functions.rglob("*.part"):  # left by an interrupted export
            part.unlink()

        symbols, header = out / "symbols.tsv", out / "il2cpp_ghidra.h"
        if not skip_analysis:
            script = json.loads((dump_dir / "script.json").read_text(encoding="utf-8"))
            with symbols.open("w", encoding="utf-8", newline="\n") as f:
                for line in symbol_lines(script):
                    f.write(line + "\n")
            del script
            header.write_text(ghidra_header((dump_dir / "il2cpp.h").read_text(encoding="utf-8")),
                              encoding="utf-8", newline="\n")

        headless = self.locate(TOOL, self.tools)
        jdk_home = self.locate(JDK, self.tools).parents[1]
        pin_jdk(headless.parents[1], jdk_home)
        log = out / "headless.log"
        cmd = headless_cmd(headless, project, binary, symbols, header, targets, functions, log, skip_analysis,
                           self.timeout)
        print("[run]", " ".join(cmd))
        start = self.clock().replace(microsecond=0)
        # stdin closed: analyzeHeadless must never wait for input
        proc = self.run(cmd, stdin=subprocess.DEVNULL, env=ghidra_env(jdk_home, self.maxmem, dict(os.environ)),
                        check=False)
        # Verified on 12.2: uncaught script exceptions log `ERROR (HeadlessAnalyzer) REPORT SCRIPT ERROR` to headless.log;
        # the script log is scanned too in case a script prints one there.
        script_log = log.with_suffix(".script.log")
        errors = [e for p in run_logs(log, start) + ([script_log] if script_log.exists() else [])
                  for e in headless_errors(run_lines(p.read_text(encoding="utf-8", errors="replace"), start))]
        if proc.returncode != 0 or errors:
            detail = errors[0][:300] if errors else "no ERROR line in the log"
            raise RuntimeError(f"Ghidra failed (exit {proc.returncode}, {len(errors)} error(s)): {detail}; see {log}")

        classes = read_targets(targets)
        missing = [rel for rel in classes if not (functions / rel).is_file()]
        # From the files, not the log: a resumed run skips existing files and would not count their failures.
        counts = {rel: failed_functions((functions / rel).read_text(encoding="utf-8", errors="replace"))
                  for rel in classes if rel not in missing}
        failed = {rel: n for rel, n in sorted(counts.items()) if n}
        index = {"tool": TOOL, "version": toolchain.TOOLS[TOOL].version, "jdk": toolchain.TOOLS[JDK].version,
                 "project": f"project/{PROJECT}.gpr", "classes": classes, "missing": missing, "failed": failed}
        (out / "index.json").write_text(json.dumps(index, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        CONTRACT.verify(out)
        return {"tool": TOOL, "version": index["version"], "jdk": index["jdk"], "maxmem": self.maxmem,
                "decompile_timeout": self.timeout,
                "classes_written": len(classes) - len(missing), "classes_missing": len(missing),
                "functions_failed": sum(failed.values())}


def create(cfg: object) -> GhidraHeadless:
    opts: dict[str, str] = getattr(cfg, "options", {}).get(PORT, {})
    raw = opts.get("decompile_timeout") or str(DEFAULT_TIMEOUT)
    if not raw.isdigit() or int(raw) <= 0:
        raise RuntimeError(f"[options.ghidra] decompile_timeout must be a positive number of seconds, got {raw!r}")
    maxmem = opts.get("maxmem") or DEFAULT_MAXMEM
    # JVM -Xmx form; a typo would otherwise only fail (or get a tiny heap) after the JVM starts.
    if not re.fullmatch(r"[1-9]\d*[MG]", maxmem, re.IGNORECASE):
        raise RuntimeError(f"[options.ghidra] maxmem must look like 12G or 8192M, got {maxmem!r}")
    return GhidraHeadless(getattr(cfg, "tools", Path.cwd() / "tools"), maxmem=maxmem,
                          timeout=int(raw))
