import shutil
from pathlib import Path

from zk.core.codehash import code_hash, stage_sources

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


def test_shared_stage_helpers_are_hashed():
    import zk.cli
    assert "zk/stages/_unpack.py" in stage_sources(("zk.cli", zk.cli.__file__))


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
