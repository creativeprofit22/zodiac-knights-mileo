import shutil
import types
from pathlib import Path

from zk.core.codehash import code_hash, fingerprint_parts, stage_sources
from zk.core.config import Config

FAKES = Path(__file__).parent / "fakes"


def _copy(dst: Path) -> tuple[Path, Path]:
    mod = dst / "fake_dump_a.py"
    shutil.copy(FAKES / "fake_dump_a.py", mod)
    pkg = dst / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("X = 1\n", encoding="utf-8")
    (pkg / "impl.py").write_text("Y = 2\n", encoding="utf-8")
    return mod, pkg / "__init__.py"


def test_out_of_tree_sources_keyed_by_module_name(tmp_path):
    hashes = []
    for name in ("one", "two"):
        (tmp_path / name).mkdir()
        mod, pkg = _copy(tmp_path / name)
        src = stage_sources(("ext.stage", mod), [("ext.adapter", mod), ("ext.pkg", pkg)])
        assert not any(Path(k).is_absolute() or ":" in k for k in src)
        assert {"ext/stage.py", "ext/adapter.py", "ext/pkg/__init__.py", "ext/pkg/impl.py"} <= src.keys()
        hashes.append(code_hash(src))
    assert hashes[0] == hashes[1]


def test_in_tree_keys_relative_to_src():
    import zk.cli
    src = stage_sources(("zk.cli", zk.cli.__file__))
    assert "zk/cli.py" in src and "zk/core/codehash.py" in src


def test_closure_follows_cross_stage_imports():
    import zk.stages.code
    src = stage_sources(("zk.stages.code", zk.stages.code.__file__))
    assert {"zk/stages/code.py", "zk/stages/_unpack.py", "zk/stages/assets/_compare.py",
            "zk/ports/__init__.py", "zk/ports/il2cpp_dump.py", "zk/core/contracts.py"} <= src.keys()
    # only what it imports: no other stage, no unrelated format, no stages/__init__.py
    assert not {"zk/stages/ghidra.py", "zk/formats/rgbv.py", "zk/stages/__init__.py"} & src.keys()


def test_closure_excludes_pins_but_keeps_toolchain():
    import zk.adapters.jadx
    import zk.stages.code
    src = stage_sources(("zk.stages.code", zk.stages.code.__file__),
                        [("zk.adapters.jadx", zk.adapters.jadx.__file__)])
    assert "zk/core/toolchain.py" in src and "zk/core/pins.py" not in src


def test_out_of_tree_imports_of_zk_are_followed(tmp_path):
    mod = tmp_path / "s.py"
    mod.write_text("from zk.formats import rgbv\n", encoding="utf-8")
    assert "zk/formats/rgbv.py" in stage_sources(("ext.s", mod))


def test_import_inside_function_is_followed(tmp_path):
    mod = tmp_path / "s.py"
    mod.write_text("def f():\n    from zk.formats import mp4\n", encoding="utf-8")
    assert "zk/formats/mp4.py" in stage_sources(("ext.s", mod))


def test_crlf_does_not_change_the_hash(tmp_path):
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_bytes(b"X = 1\nY = 2\n")
    b.write_bytes(b"X = 1\r\nY = 2\r\n")
    assert code_hash(stage_sources(("ext.s", a))) == code_hash(stage_sources(("ext.s", b)))


def test_java_scripts_in_package_change_the_hash(tmp_path):
    mod, pkg = _copy(tmp_path)
    (pkg.parent / "scripts").mkdir()
    script = pkg.parent / "scripts" / "Export.java"
    script.write_text("class Export {}\n", encoding="utf-8")
    src = stage_sources(("ext.stage", mod), [("ext.pkg", pkg)])
    assert "ext/pkg/scripts/Export.java" in src
    before = code_hash(src)
    script.write_text("class Export { int x; }\n", encoding="utf-8")
    assert code_hash(stage_sources(("ext.stage", mod), [("ext.pkg", pkg)])) != before


def test_ghidra_adapter_hashes_its_java_scripts():
    import zk.adapters.ghidra
    src = stage_sources(("zk.adapters.ghidra", zk.adapters.ghidra.__file__))
    assert "zk/adapters/ghidra/scripts/Il2CppExport.java" in src


def _cfg(**adapters: str) -> Config:
    return Config(adapters=adapters, options={"ghidra": {"maxmem": "4G"}})


def test_fingerprint_parts_lists_adapter_pins_and_options():
    import zk.stages.ghidra
    parts = fingerprint_parts(zk.stages.ghidra, ["ghidra"], _cfg(ghidra="ghidra"))
    assert parts["adapters"] == {"ghidra": "ghidra"}
    assert set(parts["tools"]) == {"ghidra", "jdk25"}
    assert parts["tools"]["ghidra"].startswith("12.2 ")
    assert parts["options"] == {"ghidra": {"maxmem": "4G"}}
    assert parts["packages"] == {}


def test_fingerprint_parts_packages_and_missing():
    mod = types.ModuleType("ext.stage")
    mod.__file__ = str(FAKES / "fake_dump_a.py")
    setattr(mod, "PACKAGES", ("pytest", "no-such-dist-zk"))
    parts = fingerprint_parts(mod, [], _cfg())
    assert parts["packages"]["no-such-dist-zk"] == "missing"
    assert parts["packages"]["pytest"] != "missing"


def test_pin_bump_changes_only_adapters_that_declare_it(monkeypatch):
    import dataclasses

    import zk.stages.code
    import zk.stages.ghidra
    from zk.core import pins
    cfg = _cfg(ghidra="ghidra", java_decompiler="jadx")
    g0 = fingerprint_parts(zk.stages.ghidra, ["ghidra"], cfg)
    c0 = fingerprint_parts(zk.stages.code, ["java_decompiler"], cfg)
    bumped = {**pins.TOOLS, "jadx": dataclasses.replace(pins.TOOLS["jadx"], version="9.9.9")}
    monkeypatch.setattr(pins, "TOOLS", bumped)
    assert fingerprint_parts(zk.stages.ghidra, ["ghidra"], cfg) == g0
    assert fingerprint_parts(zk.stages.code, ["java_decompiler"], cfg)["tools"] != c0["tools"]
