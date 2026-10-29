import json
from collections import namedtuple
from pathlib import Path

import pytest

from zk.adapters import typetree_cpp2il, typetree_dummydll
from zk.ports.type_info import CONTRACT, TypeInfo

Node = namedtuple("Node", "m_Type m_Name m_Level m_MetaFlag")


class FakeGen:
    def __init__(self, version):
        self.version, self.dlls, self.il2cpp = version, [], None

    def load_dll(self, dll):
        self.dlls.append(dll)

    def load_il2cpp(self, il2cpp, metadata):
        self.il2cpp = (il2cpp, metadata)

    def get_nodes(self, assembly, fullname):
        if fullname == "Bad.Thing":
            raise AssertionError("failed to dump nodes raw")
        if fullname == "Empty.Thing":
            return []
        return [Node("MonoBehaviour", "Base", 0, 0), Node("int", f"{assembly}:{fullname}", 1, 16384)]


class Factory:
    def __init__(self):
        self.made: list[FakeGen] = []

    def __call__(self, version):
        g = FakeGen(version)
        self.made.append(g)
        return g


def _dump(tmp_path: Path) -> Path:
    d = tmp_path / "dump"
    (d / "DummyDll").mkdir(parents=True)
    for f in ("dump.cs", "script.json", "il2cpp.h", "summary.json"):
        (d / f).write_text("{}", encoding="utf-8")
    for n in ("b.dll", "a.dll", "notes.txt"):
        (d / "DummyDll" / n).write_bytes(n.encode())
    return d


def _classes(tmp_path: Path) -> Path:
    p = tmp_path / "classes.json"
    p.write_text(json.dumps([{"assembly": "UnityEngine.UI", "class": "UnityEngine.UI.Image"},
                             {"assembly": "Game", "class": "Bad.Thing"},
                             {"assembly": "Game", "class": "Empty.Thing"},
                             {"assembly": "UnityEngine.UI", "class": "UnityEngine.UI.Image"}]), encoding="utf-8")
    return p


def test_adapters_satisfy_port():
    assert isinstance(typetree_dummydll.create(None), TypeInfo)
    assert isinstance(typetree_cpp2il.create(None), TypeInfo)


def test_dummydll_loads_sorted_dlls_and_writes_nodes(tmp_path):
    f = Factory()
    out = tmp_path / "types"
    info = typetree_dummydll.TypeTreeDummyDll(f).types(
        tmp_path / "lib.so", tmp_path / "m.dat", _dump(tmp_path), "1234.5.6f7", _classes(tmp_path), out)
    gen = f.made[0]
    assert gen.version == "1234.5.6f7"
    assert gen.dlls == [b"a.dll", b"b.dll"]
    CONTRACT.verify(out)
    doc = json.loads((out / "nodes.json").read_text(encoding="utf-8"))
    assert doc["unity_version"] == "1234.5.6f7"
    assert list(doc["classes"]) == ["UnityEngine.UI|UnityEngine.UI.Image"]
    assert doc["classes"]["UnityEngine.UI|UnityEngine.UI.Image"][1] == {
        "m_Type": "int", "m_Name": "UnityEngine.UI.dll:UnityEngine.UI.Image", "m_Level": 1, "m_MetaFlag": 16384}
    assert doc["missing"] == {"Game|Bad.Thing": "AssertionError: failed to dump nodes raw",
                              "Game|Empty.Thing": "no nodes generated"}
    assert (info["classes"], info["missing"], info["dlls"]) == (1, 2, 2)


def test_dummydll_requires_dump_contract(tmp_path):
    d = tmp_path / "dump"
    (d / "DummyDll").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="il2cpp_dump"):
        typetree_dummydll.TypeTreeDummyDll(Factory()).types(d, d, d, "1.0", _classes(tmp_path), tmp_path / "o")


def test_cpp2il_passes_binary_and_metadata(tmp_path):
    (tmp_path / "lib.so").write_bytes(b"ELF")
    (tmp_path / "m.dat").write_bytes(b"META")
    f = Factory()
    out = tmp_path / "types"
    typetree_cpp2il.TypeTreeCpp2Il(f, lambda: True).types(
        tmp_path / "lib.so", tmp_path / "m.dat", tmp_path, "9.9.9f9", _classes(tmp_path), out)
    assert f.made[0].il2cpp == (b"ELF", b"META")
    assert f.made[0].version == "9.9.9f9"
    CONTRACT.verify(out)


def test_cpp2il_refuses_without_native_il2cpp(tmp_path):
    f = Factory()
    with pytest.raises(RuntimeError, match="no IL2CPP support"):
        typetree_cpp2il.TypeTreeCpp2Il(f, lambda: False).types(
            tmp_path, tmp_path, tmp_path, "1.0", _classes(tmp_path), tmp_path / "o")
    assert f.made == []


def test_module_lookup_returns_the_binding_module_not_the_class():
    import inspect

    from zk.adapters import _typetree
    mod = _typetree._module()  # regression: `import pkg.TypeTreeGenerator as m` yielded the re-exported class
    assert inspect.ismodule(mod) and hasattr(mod, "init_dll")


def _n(level, typ, name):
    return {"m_Type": typ, "m_Name": name, "m_Level": level, "m_MetaFlag": 0}


def test_string_array_emitted_as_string_is_retyped_to_vector():
    from zk.adapters._typetree import fix_string_arrays
    nodes = [_n(0, "Base", "Base"),
             _n(1, "string", "m_Name"), _n(2, "Array", "Array"), _n(3, "int", "size"), _n(3, "char", "data"),
             _n(1, "string", "m_Names"), _n(2, "Array", "Array"), _n(3, "int", "size"), _n(3, "string", "data"),
             _n(4, "Array", "Array"), _n(5, "int", "size"), _n(5, "char", "data")]
    assert fix_string_arrays(nodes) == 1
    assert [n["m_Type"] for n in nodes if n["m_Level"] == 1] == ["string", "vector"]
    assert nodes[8]["m_Type"] == "string"  # the element type stays
    assert fix_string_arrays(nodes) == 0


def test_reference_requests_drop_the_monobehaviour_header(tmp_path):
    class RefGen(FakeGen):
        def get_nodes(self, assembly, fullname):
            return [Node("X", "Base", 0, 0), Node("PPtr<GameObject>", "m_GameObject", 1, 0),
                    Node("int", "m_FileID", 2, 0), Node("UInt8", "m_Enabled", 1, 0),
                    Node("PPtr<MonoScript>", "m_Script", 1, 0), Node("string", "m_Name", 1, 0),
                    Node("Array", "Array", 2, 0), Node("int", "size", 3, 0), Node("char", "data", 3, 0),
                    Node("int", "m_Version", 1, 0)]
    classes = tmp_path / "classes.json"
    classes.write_text(json.dumps([{"assembly": "Core", "class": "Ns.Settings", "reference": True},
                                   {"assembly": "Core", "class": "Ns.Comp"}]), encoding="utf-8")
    out = tmp_path / "types"
    info = typetree_dummydll.TypeTreeDummyDll(RefGen).types(tmp_path, tmp_path, _dump(tmp_path), "1.0", classes, out)
    doc = json.loads((out / "nodes.json").read_text(encoding="utf-8"))
    assert [n["m_Name"] for n in doc["references"]["Core|Ns.Settings"]] == ["Base", "m_Version"]
    assert len(doc["classes"]["Core|Ns.Comp"]) == 10 and doc["missing_references"] == {}
    assert (info["classes"], info["references"]) == (1, 1)
