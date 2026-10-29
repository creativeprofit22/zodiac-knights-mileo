import json

from zk import cli
from zk.stages.code import compare


def _config(tmp_path, dump="tests.fakes.fake_dump_a", extra_type=""):
    lines = ['workspace = "ws"', 'tools = "tools"', 'package = "com.zodiacknights.game"', "[adapters]",
             'device_source = "tests.fakes.fake_device"', f'il2cpp_dump = "{dump}"',
             'il2cpp_crosscheck = "tests.fakes.fake_crosscheck"', 'decompiler = "tests.fakes.fake_decompiler"',
             "[options.il2cpp_crosscheck]", f'extra_type = "{extra_type}"']
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


def _summary(classes):
    return {"assemblies": {a: {"types": len(c), "methods": sum(c.values()), "classes": c}
                           for a, c in classes.items()}}


def test_compare_reports_type_counts_and_method_gaps():
    a = _summary({"G": {"X": 1, "Y": 2}, "Other": {"Z": 1}})
    b = _summary({"G": {"X": 1, "Y": 3, "W": 0}})
    r = compare(a, b, ["G", "Missing"])
    assert r["assemblies"]["G"] == {"types": [2, 3], "methods": [3, 4], "method_gaps": {"W": [None, 0], "Y": [2, 3]}}
    assert r["assemblies"]["Missing"]["types"] == [None, None]
    assert r["type_mismatches"] == ["G"] and r["types_match"] is False
    assert compare(a, a, ["G"])["types_match"] is True


def test_code_stage_records_dump_crosscheck_and_java(tmp_path):
    cfg = _unpacked(tmp_path)
    assert cli.main(["--config", str(cfg), "code"]) == 0
    c = _manifest(tmp_path)["code"]
    assert c["version"] == "0.4.6-17" and c["abi"] == "arm64-v8a"
    assert c["game_assemblies"] == ["Assembly-CSharp", "ZodiacKnights.Game", "ZodiacKnights.Logic"]
    assert c["dump"]["by"] == "a"
    assert c["dump"]["assemblies"]["ZodiacKnights.Game"] == {"types": 2, "methods": 4}
    assert c["crosscheck"]["types_match"] is True and c["crosscheck"]["method_gap_classes"] == 0
    assert c["java"] == {"apk": "base.apk", "exit_code": 1, "errors": ["ERROR - finished with errors, count: 1"]}
    assert set(c["adapters"]) == {"il2cpp_dump", "il2cpp_crosscheck", "decompiler"}
    out = tmp_path / "ws" / "il2cpp" / "0.4.6-17"
    assert (out / "crosscheck.json").is_file() and (out / "DummyDll" / "ZodiacKnights.Logic.dll").is_file()
    assert (tmp_path / "ws" / "code" / "0.4.6-17" / "sources" / "A.java").is_file()


def test_type_mismatch_fails_after_writing_report(tmp_path, capsys):
    cfg = _unpacked(tmp_path, extra_type="ZK.Extra")
    assert cli.main(["--config", str(cfg), "code"]) == 2
    assert "ZodiacKnights.Game [2, 3]" in capsys.readouterr().err
    report = json.loads((tmp_path / "ws" / "il2cpp" / "0.4.6-17" / "crosscheck.json").read_text(encoding="utf-8"))
    assert report["type_mismatches"] == ["ZodiacKnights.Game"]
    assert report["assemblies"]["ZodiacKnights.Game"]["method_gaps"] == {"ZK.Extra": [None, 0]}
    assert "code" not in _manifest(tmp_path)


def test_missing_game_assembly_dll_fails(tmp_path, capsys):
    cfg = _unpacked(tmp_path, dump="tests.fakes.fake_dump_missing")
    assert cli.main(["--config", str(cfg), "code"]) == 2
    assert "DummyDll/ZodiacKnights.Logic.dll is missing" in capsys.readouterr().err


def test_adapters_swap_through_config_only(tmp_path):
    cfg = _unpacked(tmp_path)
    assert cli.main(["--config", str(cfg), "code", "--skip-java"]) == 0
    first = _manifest(tmp_path)["code"]
    _config(tmp_path, dump="tests.fakes.fake_dump_b")
    assert cli.main(["--config", str(cfg), "code", "--skip-java"]) == 0
    second = _manifest(tmp_path)["code"]
    assert first["adapters"]["il2cpp_dump"]["module"] == "tests.fakes.fake_dump_a"
    assert second["adapters"]["il2cpp_dump"]["module"] == "tests.fakes.fake_dump_b"
    assert second["dump"]["by"] == "b" and second["java"] is None
    assert second["crosscheck"]["assemblies"]["ZodiacKnights.Logic"]["method_gaps"] == {"ZK.Rules": [5, 4]}


def test_code_needs_unpack(tmp_path, capsys):
    cfg = _config(tmp_path)
    assert cli.main(["--config", str(cfg), "acquire"]) == 0
    assert cli.main(["--config", str(cfg), "code"]) == 2
    assert "run `zk unpack` first" in capsys.readouterr().err
