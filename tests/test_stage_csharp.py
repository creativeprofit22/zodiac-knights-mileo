import json

import pytest

from zk import cli

GAME = ["Assembly-CSharp", "ZodiacKnights.Game", "ZodiacKnights.Logic"]
COUNTS = {"types": 1, "methods": 2, "bodies": {"none": 0, "reconstructed": 1, "stub": 1}}


def _config(tmp_path, skip=""):
    lines = ['workspace = "ws"', 'tools = "tools"', 'package = "com.zodiacknights.game"', "[adapters]",
             'device_source = "tests.fakes.fake_device"', 'il2cpp_dump = "tests.fakes.fake_dump_a"',
             'il2cpp_crosscheck = "tests.fakes.fake_crosscheck"',
             'java_decompiler = "tests.fakes.fake_java_decompiler"',
             'il2cpp_assemblies = "tests.fakes.fake_il2cpp_assemblies"',
             'decompiler = "tests.fakes.fake_csharp_decompiler"', "[options.decompiler]", f'skip = "{skip}"']
    p = tmp_path / "zk.toml"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _unpacked(tmp_path, **kw):
    cfg = _config(tmp_path, **kw)
    assert cli.main(["--config", str(cfg), "acquire"]) == 0
    assert cli.main(["--config", str(cfg), "unpack"]) == 0
    return cfg


def _manifest(tmp_path):
    return json.loads((tmp_path / "ws" / "manifest.json").read_text(encoding="utf-8"))


def _out(tmp_path):
    return tmp_path / "ws" / "csharp" / "0.4.6-17"


def test_cpp2il_input_builds_assemblies_and_records_report(tmp_path):
    cfg = _unpacked(tmp_path)
    assert cli.main(["--config", str(cfg), "csharp"]) == 0
    c = _manifest(tmp_path)["csharp"]
    unity = _manifest(tmp_path)["game"]["unity_version"]
    assert c["input"] == "cpp2il" and c["abi"] == "arm64-v8a" and c["game_assemblies"] == GAME
    assert c["assemblies"] == {"tool": "fake", "unity_version": unity, "dlls": 4}
    assert c["decompiler"]["from"].endswith("csharp/0.4.6-17/assemblies")
    assert c["report"] == {n: COUNTS for n in GAME}
    assert set(c["adapters"]) == {"il2cpp_assemblies", "decompiler"}
    out = _out(tmp_path)
    assert json.loads((out / "report.json").read_text(encoding="utf-8"))["input"] == "cpp2il"
    readme = (out / "README.md").read_text(encoding="utf-8")
    assert "`cpp2il`" in readme and "original C# can never be recovered" in readme and "Ghidra" in readme


def test_dummydll_input_reuses_code_stage_output(tmp_path):
    cfg = _unpacked(tmp_path)
    assert cli.main(["--config", str(cfg), "code", "--skip-crosscheck", "--skip-java"]) == 0
    assert cli.main(["--config", str(cfg), "csharp"]) == 0
    assert cli.main(["--config", str(cfg), "csharp", "--input", "dummydll"]) == 0
    c = _manifest(tmp_path)["csharp"]
    assert c["input"] == "dummydll" and c["assemblies"] is None
    assert c["decompiler"]["from"].endswith("il2cpp/0.4.6-17/DummyDll")
    out = _out(tmp_path)
    assert not (out / "assemblies").exists()
    assert json.loads((out / "report.json").read_text(encoding="utf-8"))["input"] == "dummydll"
    assert "`dummydll`" in (out / "README.md").read_text(encoding="utf-8")


def test_dummydll_input_without_code_stage_fails(tmp_path, capsys):
    cfg = _unpacked(tmp_path)
    assert cli.main(["--config", str(cfg), "csharp", "--input", "dummydll"]) == 2
    assert "run `zk code` first" in capsys.readouterr().err
    assert "csharp" not in _manifest(tmp_path)


def test_missing_project_fails(tmp_path, capsys):
    cfg = _unpacked(tmp_path, skip="ZodiacKnights.Logic")
    assert cli.main(["--config", str(cfg), "csharp"]) == 2
    err = capsys.readouterr().err
    assert "projects/ZodiacKnights.Logic has no .csproj" in err and "ZodiacKnights.Logic has no types" in err
    assert "csharp" not in _manifest(tmp_path)


def test_csharp_needs_unpack(tmp_path, capsys):
    cfg = _config(tmp_path)
    assert cli.main(["--config", str(cfg), "acquire"]) == 0
    assert cli.main(["--config", str(cfg), "csharp"]) == 2
    assert "run `zk unpack` first" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["ilspy", ""])
def test_unknown_input_is_rejected(tmp_path, bad):
    with pytest.raises(SystemExit):
        cli.main(["--config", str(_config(tmp_path)), "csharp", "--input", bad])


def test_dummydll_input_rejects_abi_other_than_code_stage(tmp_path, capsys):
    cfg = _unpacked(tmp_path)
    abis = sorted(_manifest(tmp_path)["unpack"]["il2cpp"])
    other = next(a for a in abis if a != "arm64-v8a")
    assert cli.main(["--config", str(cfg), "code", "--skip-crosscheck", "--skip-java"]) == 0
    capsys.readouterr()
    assert cli.main(["--config", str(cfg), "csharp", "--input", "dummydll", "--abi", other]) == 2
    err = capsys.readouterr().err
    assert "'arm64-v8a'" in err and repr(other) in err and f"zk code --abi {other}" in err
    assert "csharp" not in _manifest(tmp_path)


def test_cpp2il_input_without_unity_version_fails_cleanly(tmp_path, capsys):
    cfg = _unpacked(tmp_path)
    for f in (tmp_path / "ws" / "unpacked").rglob("globalgamemanagers"):
        f.unlink()
    assert cli.main(["--config", str(cfg), "unpack"]) == 0
    assert _manifest(tmp_path)["game"]["unity_version"] is None
    assert cli.main(["--config", str(cfg), "csharp"]) == 2
    assert "'unity_version' is unknown" in capsys.readouterr().err
    assert "csharp" not in _manifest(tmp_path)
