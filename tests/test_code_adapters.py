import json
import subprocess
from pathlib import Path

import pytest

from tests.test_csharp_dump import DUMP, EXPECTED, INSPECTOR
from tests.test_il2cpp_script import _script
from zk.adapters import il2cppdumper, il2cppinspector, jadx
from zk.ports.decompiler import Decompiler
from zk.ports.il2cpp_crosscheck import Il2CppCrosscheck
from zk.ports.il2cpp_dump import Il2CppDump

EXE = Path("tools/x/tool.exe")


class Runner:
    """Records each call and its keyword arguments; `effect(cmd)` writes the tool's output files."""

    def __init__(self, effect, returncode=0, stdout=""):
        self.effect, self.returncode, self.stdout = effect, returncode, stdout
        self.calls: list[tuple[list[str], dict]] = []

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        self.effect(cmd)
        return subprocess.CompletedProcess(cmd, self.returncode, self.stdout, "")


def _locate(name, tools):
    return EXE


def _env(tools):
    return {"X": "1"}


def _dumper_output(out: Path, script=None):
    (out / "DummyDll").mkdir(parents=True, exist_ok=True)
    (out / "dump.cs").write_text(DUMP, encoding="utf-8")
    (out / "script.json").write_text(json.dumps(script if script is not None else _script()), encoding="utf-8")
    (out / "il2cpp.h").write_text("// header\n", encoding="utf-8")


def test_command_lines():
    b, m, o = Path("lib.so"), Path("meta.dat"), Path("out")
    assert il2cppdumper.command(EXE, b, m, o) == [str(EXE), "lib.so", "meta.dat", "out", "--no-pause"]
    assert il2cppinspector.command(EXE, b, m, o) == [
        str(EXE), "-i", "lib.so", "-m", "meta.dat", "--select-outputs", "-c", str(o / "cs"),
        "-l", "assembly", "-e", "none"]
    assert jadx.command(EXE, Path("base.apk"), o) == [str(EXE), "-ds", str(o / "sources"), "--no-res", "base.apk"]


def test_adapters_satisfy_their_ports(tmp_path):
    assert isinstance(il2cppdumper.Il2CppDumper(tmp_path), Il2CppDump)
    assert isinstance(il2cppinspector.Il2CppInspector(tmp_path), Il2CppCrosscheck)
    assert isinstance(jadx.Jadx(tmp_path), Decompiler)


def test_dumper_runs_without_stdin_and_writes_summary(tmp_path):
    out = tmp_path / "out"
    run = Runner(lambda cmd: _dumper_output(Path(cmd[3])), stdout="Done!\n")
    info = il2cppdumper.Il2CppDumper(tmp_path, run, _locate, _env).dump(Path("lib.so"), Path("m.dat"), out)
    cmd, kw = run.calls[0]
    assert cmd[-1] == "--no-pause" and kw["stdin"] is subprocess.DEVNULL and kw["env"] == {"X": "1"}
    assert json.loads((out / "summary.json").read_text(encoding="utf-8")) == EXPECTED
    assert info["tool"] == "il2cppdumper" and info["script"]["methods"] == 1
    assert info["totals"]["assemblies"] == len(EXPECTED["assemblies"])


@pytest.mark.parametrize("returncode,stdout", [(0, "ERROR: Can't use auto mode to process file\n"),
                                               (0, "Unhandled exception. System.IO.IOException\n"),
                                               (1, "")])
def test_dumper_failure_raises(tmp_path, returncode, stdout):
    run = Runner(lambda cmd: _dumper_output(Path(cmd[3])), returncode, stdout)
    with pytest.raises(RuntimeError, match="Il2CppDumper failed"):
        il2cppdumper.Il2CppDumper(tmp_path, run, _locate, _env).dump(Path("a"), Path("b"), tmp_path / "out")


def test_dumper_missing_output_raises(tmp_path):
    run = Runner(lambda cmd: None)
    with pytest.raises(RuntimeError, match="left no dump.cs"):
        il2cppdumper.Il2CppDumper(tmp_path, run, _locate, _env).dump(Path("a"), Path("b"), tmp_path / "out")


def test_dumper_bad_script_json_raises(tmp_path):
    run = Runner(lambda cmd: _dumper_output(Path(cmd[3]), {"ScriptMethod": []}))
    with pytest.raises(RuntimeError, match="script.json is not valid"):
        il2cppdumper.Il2CppDumper(tmp_path, run, _locate, _env).dump(Path("a"), Path("b"), tmp_path / "out")


def _inspector_output(cs: Path):
    cs.mkdir(parents=True, exist_ok=True)
    for name, text in INSPECTOR.items():
        (cs / Path(name).name).write_text(text, encoding="utf-8")


def test_inspector_writes_summary(tmp_path):
    out = tmp_path / "out"
    run = Runner(lambda cmd: _inspector_output(Path(cmd[cmd.index("-c") + 1])))
    info = il2cppinspector.Il2CppInspector(tmp_path, run, _locate, _env).crosscheck(Path("a"), Path("b"), out)
    assert run.calls[0][1]["stdin"] is subprocess.DEVNULL
    assert json.loads((out / "summary.json").read_text(encoding="utf-8")) == EXPECTED
    assert info["files"] == len(INSPECTOR)


def test_inspector_failure_raises(tmp_path):
    run = Runner(lambda cmd: None, returncode=3, stdout="Metadata version 39 not supported")
    with pytest.raises(RuntimeError, match="exit 3.*version 39"):
        il2cppinspector.Il2CppInspector(tmp_path, run, _locate, _env).crosscheck(Path("a"), Path("b"), tmp_path)


def _jadx_output(sources: Path):
    (sources / "com" / "x").mkdir(parents=True)
    (sources / "com" / "x" / "A.java").write_text("class A {}", encoding="utf-8")


def test_jadx_nonzero_exit_is_recorded(tmp_path):
    run = Runner(lambda cmd: _jadx_output(Path(cmd[cmd.index("-ds") + 1])), returncode=1,
                 stdout="INFO  - loading\nERROR - finished with errors, count: 3\n")
    info = jadx.Jadx(tmp_path, run, _locate, _env).decompile(Path("base.apk"), tmp_path / "out")
    assert info["exit_code"] == 1 and info["java_files"] == 1
    assert info["errors"] == ["ERROR - finished with errors, count: 3"]


def test_jadx_without_sources_raises(tmp_path):
    run = Runner(lambda cmd: None, returncode=1, stdout="ERROR - bad apk")
    with pytest.raises(RuntimeError, match="wrote no sources"):
        jadx.Jadx(tmp_path, run, _locate, _env).decompile(Path("base.apk"), tmp_path / "out")


def test_jadx_failure_ignores_stale_sources(tmp_path):
    _jadx_output(tmp_path / "out" / "sources")
    run = Runner(lambda cmd: None, returncode=1, stdout="ERROR - bad apk")
    with pytest.raises(RuntimeError, match="wrote no sources"):
        jadx.Jadx(tmp_path, run, _locate, _env).decompile(Path("base.apk"), tmp_path / "out")


def test_dumper_ignores_protected_file_warning():
    from zk.adapters.il2cppdumper import error_lines
    out = "[00:00.815] WARNING: find JNI_OnLoad\n[00:00.815] ERROR: This file may be protected.\n[00:07.864] Done!\n"
    assert error_lines(out) == []
    assert error_lines(out + "[00:09.000] ERROR: Can't use auto mode to process file\n") == [
        "[00:09.000] ERROR: Can't use auto mode to process file"]
