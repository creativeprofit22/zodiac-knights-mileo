import pytest

from zk.core.contracts import ArtifactContract
from zk.ports import PORTS


def test_missing_and_verify(tmp_path):
    c = ArtifactContract("p", files=("a.txt",), dirs=("d",))
    assert c.missing(tmp_path) == ["a.txt", "d/"]
    with pytest.raises(RuntimeError, match="p: .*missing a.txt, d/"):
        c.verify(tmp_path)
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "d").mkdir()
    c.verify(tmp_path)


def test_every_port_has_protocol_and_contract():
    assert set(PORTS) == {"device_source", "il2cpp_dump", "il2cpp_crosscheck", "java_decompiler",
                          "il2cpp_assemblies", "decompiler", "type_info", "ghidra"}
    for name, port in PORTS.items():
        assert port.contract.port == name and (port.contract.files or port.contract.dirs)
        assert getattr(port.protocol, "_is_runtime_protocol", False)
