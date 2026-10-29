import json

from zk import cli


def _config(tmp_path):
    lines = ['workspace = "ws"', 'tools = "tools"', 'package = "com.zodiacknights.game"', "[adapters]",
             'device_source = "tests.fakes.fake_device"', 'il2cpp_dump = "tests.fakes.fake_dump_script"',
             'il2cpp_crosscheck = "tests.fakes.fake_crosscheck"',
             'java_decompiler = "tests.fakes.fake_java_decompiler"', 'ghidra = "tests.fakes.fake_ghidra"']
    p = tmp_path / "zk.toml"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _setup(tmp_path, code=True):
    cfg = _config(tmp_path)
    for argv in [["acquire"], ["unpack"]] + ([["code", "--skip-crosscheck", "--skip-java"]] if code else []):
        assert cli.main(["--config", str(cfg), *argv]) == 0
    return cfg


def _manifest(tmp_path):
    return json.loads((tmp_path / "ws" / "manifest.json").read_text(encoding="utf-8"))


def _out(tmp_path):
    return tmp_path / "ws" / "ghidra" / "0.4.6-17"


def test_exports_only_zodiacknights_classes(tmp_path):
    cfg = _setup(tmp_path)
    assert cli.main(["--config", str(cfg), "ghidra"]) == 0
    g = _manifest(tmp_path)["ghidra"]
    assert g["abi"] == "arm64-v8a" and g["skip_analysis"] is False
    assert g["classes_targeted"] == 2 and g["functions_targeted"] == 3
    assert g["roots"] == {"ZodiacKnights": 2}
    assert g["analysis"] == {"tool": "fake", "binary": "libil2cpp.so", "skip_analysis": False}
    out = _out(tmp_path)
    assert (out / "targets.tsv").read_text(encoding="utf-8") == (
        "1000\tZodiacKnights.Game/AdminLiveOps.c\n1010\tZodiacKnights.Game/AdminLiveOps.c\n"
        "2000\tZodiacKnights.Logic/Rules.c\n")
    assert (out / "functions" / "ZodiacKnights.Game" / "AdminLiveOps.c").is_file()


def test_skip_analysis_filter_and_limit_pass_through(tmp_path):
    cfg = _setup(tmp_path)
    assert cli.main(["--config", str(cfg), "ghidra", "--skip-analysis", "--filter", "Logic"]) == 0
    g = _manifest(tmp_path)["ghidra"]
    assert g["skip_analysis"] is True and g["analysis"]["skip_analysis"] is True
    assert g["classes_targeted"] == 1 and g["filter"] == "Logic"
    assert cli.main(["--config", str(cfg), "ghidra", "--limit", "1"]) == 0
    assert (_out(tmp_path) / "targets.tsv").read_text(encoding="utf-8").count("\n") == 2


def test_force_clears_earlier_output(tmp_path):
    cfg = _setup(tmp_path)
    assert cli.main(["--config", str(cfg), "ghidra"]) == 0
    stale = _out(tmp_path) / "functions" / "Old" / "Gone.c"
    stale.parent.mkdir(parents=True)
    stale.write_text("", encoding="utf-8")
    assert cli.main(["--config", str(cfg), "ghidra", "--force"]) == 0
    assert not stale.exists()


def test_without_code_stage_fails(tmp_path, capsys):
    cfg = _setup(tmp_path, code=False)
    assert cli.main(["--config", str(cfg), "ghidra"]) == 2
    assert "run `zk code` first" in capsys.readouterr().err
    assert "ghidra" not in _manifest(tmp_path)


def test_abi_mismatch_fails(tmp_path, capsys):
    cfg = _setup(tmp_path)
    assert cli.main(["--config", str(cfg), "ghidra", "--abi", "x86_64"]) == 2
    assert "rerun `zk code --abi x86_64`" in capsys.readouterr().err
    assert "ghidra" not in _manifest(tmp_path)


def test_empty_selection_fails(tmp_path, capsys):
    cfg = _setup(tmp_path)
    assert cli.main(["--config", str(cfg), "ghidra", "--filter", "NoSuchClass"]) == 2
    assert "no ZodiacKnights classes selected" in capsys.readouterr().err
    assert "ghidra" not in _manifest(tmp_path)


def test_invalid_filter_regex_fails(tmp_path, capsys):
    cfg = _setup(tmp_path)
    assert cli.main(["--config", str(cfg), "ghidra", "--filter", "("]) == 2
    assert "not a valid regex" in capsys.readouterr().err
    assert "ghidra" not in _manifest(tmp_path)
