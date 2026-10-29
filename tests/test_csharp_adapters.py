import json
import subprocess
from pathlib import Path

import pytest

from zk.adapters import cpp2il, ilspycmd
from zk.formats.csharp_project import DISCLAIMER
from zk.ports.decompiler import Decompiler
from zk.ports.il2cpp_assemblies import Il2CppAssemblies

EXE = Path("tools/x/tool.exe")

GAME_CS = """namespace ZK.Game
{
    public class Hero
    {
        public int Hp;
        public void Hit() { }
        public int Power() { return Hp * 2; }
    }
}
"""


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


def _cpp2il_output(cmd, names=("Game", "mscorlib")):
    out = Path(cmd[cmd.index("--output-to") + 1])
    out.mkdir(parents=True, exist_ok=True)
    for n in names:
        (out / f"{n}.dll").write_bytes(b"MZ")


def _ilspy_output(cmd):
    proj = Path(cmd[cmd.index("-o") + 1])
    (proj / "ZK" / "Game").mkdir(parents=True, exist_ok=True)
    (proj / f"{proj.name}.csproj").write_text("<Project />\n", encoding="utf-8")
    (proj / "ZK" / "Game" / "Hero.cs").write_text(GAME_CS, encoding="utf-8")


def _assemblies(tmp_path, names=("Game", "Logic")):
    asm = tmp_path / "asm"
    asm.mkdir()
    for n in names:
        (asm / f"{n}.dll").write_bytes(b"MZ")
    return asm


def test_command_lines():
    o = Path("out")
    assert cpp2il.command(EXE, Path("lib.so"), Path("m.dat"), "6000.0.1f1", o) == [
        str(EXE), "--force-binary-path", "lib.so", "--force-metadata-path", "m.dat",
        "--force-unity-version", "6000.0.1f1", "--output-as", "dummydll", "--output-to", str(o / "assemblies")]
    assert ilspycmd.command(EXE, Path("a/G.dll"), Path("a"), Path("p/G")) == [
        str(EXE), "-p", "-o", str(Path("p/G")), "-r", "a", "--disable-updatecheck", str(Path("a/G.dll"))]


def test_adapters_satisfy_their_ports(tmp_path):
    assert isinstance(cpp2il.Cpp2Il(tmp_path), Il2CppAssemblies)
    assert isinstance(ilspycmd.IlSpyCmd(tmp_path), Decompiler)


def test_cpp2il_runs_headless_in_out_and_counts_dlls(tmp_path):
    out = tmp_path / "out"
    (out / "assemblies").mkdir(parents=True)
    (out / "assemblies" / "Stale.dll").write_bytes(b"old")
    run = Runner(_cpp2il_output, stdout="Done\n")
    info = cpp2il.Cpp2Il(tmp_path, run, _locate).build(Path("lib.so"), Path("m.dat"), "6000.0.1f1", out)
    cmd, kw = run.calls[0]
    assert kw["stdin"] is subprocess.DEVNULL and kw["cwd"] == str(out)
    assert sorted(p.name for p in (out / "assemblies").iterdir()) == ["Game.dll", "mscorlib.dll"]
    assert (out / "cpp2il.log").read_text(encoding="utf-8") == "Done\n"
    assert info["tool"] == "cpp2il" and info["dlls"] == 2 and info["output_as"] == "dummydll"


@pytest.mark.parametrize("returncode,names", [(1, ("Game",)), (0, ())])
def test_cpp2il_failure_raises(tmp_path, returncode, names):
    run = Runner(lambda cmd: _cpp2il_output(cmd, names), returncode, "boom")
    with pytest.raises(RuntimeError, match="Cpp2IL failed"):
        cpp2il.Cpp2Il(tmp_path, run, _locate).build(Path("a"), Path("b"), "6000.0.1f1", tmp_path / "out")


def test_ilspycmd_writes_projects_and_report(tmp_path):
    asm, out = _assemblies(tmp_path), tmp_path / "out"
    run = Runner(_ilspy_output)
    info = ilspycmd.IlSpyCmd(tmp_path, run, _locate).decompile(asm, ["Logic", "Game"], out)
    assert [Path(c[0][c[0].index("-o") + 1]).name for c in run.calls] == ["Game", "Logic"]
    assert all(kw["stdin"] is subprocess.DEVNULL for _, kw in run.calls)
    assert all(c[0][c[0].index("-r") + 1] == str(asm) for c in run.calls)
    doc = json.loads((out / "report.json").read_text(encoding="utf-8"))
    counts = {"types": 1, "methods": 2, "bodies": {"none": 0, "reconstructed": 1, "stub": 1}}
    assert doc == {"input": None, "tool": {"name": "ilspycmd", "version": doc["tool"]["version"]},
                   "assemblies": {"Game": counts, "Logic": counts}, "disclaimer": DISCLAIMER}
    assert info["cs_files"] == 2 and info["exit_codes"] == {"Game": 0, "Logic": 0}
    assert (out / "ilspycmd.log").is_file()


def test_ilspycmd_missing_input_dll_raises(tmp_path):
    run = Runner(_ilspy_output)
    with pytest.raises(RuntimeError, match="no Logic.dll"):
        ilspycmd.IlSpyCmd(tmp_path, run, _locate).decompile(_assemblies(tmp_path, ("Game",)), ["Game", "Logic"],
                                                            tmp_path / "out")
    assert run.calls == []


@pytest.mark.parametrize("returncode,effect", [(1, _ilspy_output), (0, lambda cmd: None)])
def test_ilspycmd_failure_raises(tmp_path, returncode, effect):
    run = Runner(effect, returncode, "err")
    with pytest.raises(RuntimeError, match="ilspycmd failed on Game"):
        ilspycmd.IlSpyCmd(tmp_path, run, _locate).decompile(_assemblies(tmp_path), ["Game"], tmp_path / "out")
    assert not (tmp_path / "out" / "report.json").exists()


def test_ilspycmd_partial_errors_are_recorded(tmp_path):
    run = Runner(_ilspy_output, 70, "3 error(s) occurred; the affected code was replaced by the error text")
    info = ilspycmd.IlSpyCmd(tmp_path, run, _locate).decompile(_assemblies(tmp_path), ["Game"], tmp_path / "out")
    assert info["exit_codes"] == {"Game": 70} and info["decompile_errors"] == {"Game": 3}
    assert (tmp_path / "out" / "report.json").is_file()


def test_ilspycmd_exit_70_without_error_summary_raises(tmp_path):
    run = Runner(_ilspy_output, 70, "crash")
    with pytest.raises(RuntimeError, match="ilspycmd failed on Game"):
        ilspycmd.IlSpyCmd(tmp_path, run, _locate).decompile(_assemblies(tmp_path), ["Game"], tmp_path / "out")
