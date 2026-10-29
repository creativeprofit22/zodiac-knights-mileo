import hashlib
import json
import types

import pytest

from zk import cli, stages
from zk.core import toolchain
from zk.core.codehash import code_hash
from zk.ports import PORTS


@pytest.fixture
def config(tmp_path):
    def write(adapter="tests.fakes.fake_dump_a"):
        p = tmp_path / "zk.toml"
        p.write_text(f'workspace = "ws"\ntools = "tools"\n[adapters]\nil2cpp_dump = "{adapter}"\n', encoding="utf-8")
        return p
    return write


def _stage(tmp_path, fail=False):
    src = tmp_path / "fake_stage.py"
    src.write_text("# fake stage\n", encoding="utf-8")
    mod = types.ModuleType("fake_stage")
    mod.__file__ = str(src)
    setattr(mod, "NAME", "dumpit")
    setattr(mod, "HELP", "fake stage")

    def execute(ctx, args):
        out = ctx.ws.dir("il2cpp", "1.0")
        info = ctx.adapter("il2cpp_dump").dump(out / "lib.so", out / "m.dat", out)
        PORTS["il2cpp_dump"].contract.verify(out)
        if fail:
            raise RuntimeError("boom")
        return info
    setattr(mod, "execute", execute)
    return mod


def _manifest(tmp_path):
    return json.loads((tmp_path / "ws" / "manifest.json").read_text(encoding="utf-8"))


def test_status_prints_adapters_and_manifest(config, capsys):
    assert cli.main(["--config", str(config()), "status"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"adapters": {"il2cpp_dump": "tests.fakes.fake_dump_a"}, "manifest": {}}


def test_tools_fetches_pinned_tool(tmp_path, config, monkeypatch):
    src = tmp_path / "x.jar"
    src.write_bytes(b"x")
    tool = toolchain.Tool("x", "9", src.as_uri(), "x.jar", kind="file", sha256=hashlib.sha256(b"x").hexdigest())
    monkeypatch.setattr(toolchain, "TOOLS", {"x": tool})
    assert cli.main(["--config", str(config()), "tools"]) == 0
    assert (tmp_path / "tools" / "x-9" / "x.jar").read_bytes() == b"x"
    assert cli.main(["--config", str(config()), "tools", "nope"]) == 2



def test_tools_refuses_unpinned_tool(tmp_path, config, monkeypatch, capsys):
    src = tmp_path / "x.jar"
    src.write_bytes(b"x")
    monkeypatch.setattr(toolchain, "TOOLS", {"x": toolchain.Tool("x", "9", src.as_uri(), "x.jar", kind="file")})
    assert cli.main(["--config", str(config()), "tools"]) == 2
    assert "no sha256" in capsys.readouterr().err
    assert not (tmp_path / "tools" / "x-9" / "x.jar").exists()

def test_stage_records_info_code_hash_and_adapters(tmp_path, config, monkeypatch):
    monkeypatch.setattr(stages, "load_all", lambda: [_stage(tmp_path)])
    assert cli.main(["--config", str(config()), "dumpit"]) == 0
    rec = _manifest(tmp_path)["dumpit"]
    assert rec["by"] == "a" and len(rec["code_hash"]) == 64
    assert rec["adapters"] == {"il2cpp_dump": {"adapter": "tests.fakes.fake_dump_a",
                                                "module": "tests.fakes.fake_dump_a"}}
    first = rec["code_hash"]
    # swapping the adapter in config changes what ran and the code hash, with no stage edit
    assert cli.main(["--config", str(config("tests.fakes.fake_dump_b")), "dumpit"]) == 0
    rec = _manifest(tmp_path)["dumpit"]
    assert rec["by"] == "b" and rec["code_hash"] != first


def test_failing_stage_records_nothing(tmp_path, config, monkeypatch, capsys):
    monkeypatch.setattr(stages, "load_all", lambda: [_stage(tmp_path, fail=True)])
    assert cli.main(["--config", str(config()), "dumpit"]) == 2
    assert "boom" in capsys.readouterr().err
    assert not (tmp_path / "ws" / "manifest.json").exists()


def test_code_hash_ignores_crlf():
    assert code_hash({"a.py": b"x\r\ny\n"}) == code_hash({"a.py": b"x\ny\n"})
    assert code_hash({"a.py": b"x"}) != code_hash({"b.py": b"x"})


def test_missing_explicit_config_is_error(tmp_path, capsys):
    assert cli.main(["--config", str(tmp_path / "nope.toml"), "status"]) == 2
    assert "config file not found" in capsys.readouterr().err


def test_invalid_toml_config_is_error(tmp_path, capsys):
    bad = tmp_path / "bad.toml"
    bad.write_text("x = [\n", encoding="utf-8")
    assert cli.main(["--config", str(bad), "status"]) == 2
    assert "config error" in capsys.readouterr().err


@pytest.mark.parametrize("name", ["game", "status", "tools", "dumpit"])
def test_reserved_or_duplicate_stage_name_is_rejected(tmp_path, config, monkeypatch, capsys, name):
    cfg = config()
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "manifest.json").write_text(json.dumps({"game": {"version": "1.0"}}), encoding="utf-8")
    bad = _stage(tmp_path)
    setattr(bad, "NAME", name)
    monkeypatch.setattr(stages, "load_all", lambda: [_stage(tmp_path), bad])
    assert cli.main(["--config", str(cfg), "status"]) == 2
    assert repr(name) in capsys.readouterr().err
    assert _manifest(tmp_path) == {"game": {"version": "1.0"}}
