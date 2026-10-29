import pytest

from zk.core.config import Config
from zk.core.context import Context
from zk.core.workspace import Workspace
from zk.ports import PORTS


def _ctx(tmp_path, **adapters):
    cfg = Config(root=tmp_path, workspace=tmp_path / "ws", tools=tmp_path / "tools", adapters=adapters)
    return Context(cfg, Workspace(cfg.workspace))


def _run(ctx, out):
    info = ctx.adapter("il2cpp_dump").dump(out / "lib.so", out / "global-metadata.dat", out)
    PORTS["il2cpp_dump"].contract.verify(out)
    return info


def test_adapters_swap_through_config_only(tmp_path):
    a = _ctx(tmp_path, il2cpp_dump="tests.fakes.fake_dump_a")
    b = _ctx(tmp_path, il2cpp_dump="tests.fakes.fake_dump_b")
    assert _run(a, tmp_path / "a") == {"by": "a"}
    assert _run(b, tmp_path / "b") == {"by": "b"}
    assert (tmp_path / "b" / "dump.cs").read_text() == "// b\n"
    assert a.used["il2cpp_dump"]["module"] == "tests.fakes.fake_dump_a"
    assert b.used["il2cpp_dump"]["module"] == "tests.fakes.fake_dump_b"


def test_unconfigured_port(tmp_path):
    with pytest.raises(RuntimeError, match="no adapter configured for port 'il2cpp_dump'"):
        _ctx(tmp_path).adapter("il2cpp_dump")


def test_unknown_port(tmp_path):
    with pytest.raises(RuntimeError, match="unknown port"):
        _ctx(tmp_path).adapter("nope")


def test_missing_adapter_module(tmp_path):
    with pytest.raises(RuntimeError, match="not found"):
        _ctx(tmp_path, il2cpp_dump="does_not_exist").adapter("il2cpp_dump")


def test_adapter_for_wrong_port(tmp_path):
    with pytest.raises(RuntimeError, match="implements port 'il2cpp_dump', not 'java_decompiler'"):
        _ctx(tmp_path, java_decompiler="tests.fakes.fake_dump_a").adapter("java_decompiler")


def test_protocol_mismatch(tmp_path):
    with pytest.raises(RuntimeError, match="does not satisfy the il2cpp_dump port"):
        _ctx(tmp_path, il2cpp_dump="tests.fakes.bad_port").adapter("il2cpp_dump")
