import pytest

from zk.adapters import folder
from zk.core.config import Config
from zk.ports.device_source import CONTRACT, DeviceSource

PKG = "com.zodiacknights.game"


def _cfg(tmp_path, **opts):
    return Config(root=tmp_path, workspace=tmp_path / "ws", tools=tmp_path / "tools",
                  adapters={"device_source": "folder"}, options={"device_source": opts})


def test_single_apk_becomes_base(tmp_path):
    (tmp_path / "game.apk").write_bytes(b"PK")
    src = folder.create(_cfg(tmp_path, path="game.apk", version="0.4.6-17"))
    assert isinstance(src, DeviceSource)
    assert src.identify(PKG) == {"package": PKG, "version": "0.4.6-17", "abi": None}
    info = src.pull(PKG, tmp_path / "out")
    CONTRACT.verify(tmp_path / "out")
    assert info["pulled"] == {"apk": ["base.apk"], "obb": False, "data": False}
    assert (tmp_path / "out" / "apk" / "base.apk").read_bytes() == b"PK"


def test_folder_sorts_apk_obb_data(tmp_path):
    s = tmp_path / "src"
    (s / "apk").mkdir(parents=True)
    (s / "apk" / "base.apk").write_bytes(b"A")
    (s / "split_x.apk").write_bytes(b"B")
    (s / "main.17.obb").write_bytes(b"O")
    (s / "data" / "files").mkdir(parents=True)
    (s / "data" / "files" / "save.bin").write_bytes(b"D")
    (s / "notes.txt").write_text("n")
    info = folder.create(_cfg(tmp_path, path=str(s), version="v1")).pull(PKG, tmp_path / "out")
    out = tmp_path / "out"
    assert info["pulled"] == {"apk": ["base.apk", "split_x.apk"], "obb": True, "data": True}
    assert (out / "obb" / "main.17.obb").exists()
    assert (out / "data" / "files" / "save.bin").read_bytes() == b"D"
    assert (out / "data" / "notes.txt").exists()


def test_folder_without_base_apk(tmp_path):
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "split.apk").write_bytes(b"x")
    with pytest.raises(RuntimeError, match="no base.apk"):
        folder.create(_cfg(tmp_path, path="s", version="v")).pull(PKG, tmp_path / "out")
    (tmp_path / "e").mkdir()
    with pytest.raises(RuntimeError, match="no .apk"):
        folder.create(_cfg(tmp_path, path="e", version="v")).pull(PKG, tmp_path / "out")


@pytest.mark.parametrize("opts, match", [
    ({}, "path and version"),
    ({"path": "x.apk"}, "path and version"),
    ({"path": "missing.apk", "version": "v"}, "does not exist"),
])
def test_identify_needs_options(tmp_path, opts, match):
    with pytest.raises(RuntimeError, match=match):
        folder.create(_cfg(tmp_path, **opts)).identify(PKG)


def test_repull_drops_apks_no_longer_in_source(tmp_path):
    s = tmp_path / "src"
    s.mkdir()
    (s / "base.apk").write_bytes(b"A")
    (s / "split_old.apk").write_bytes(b"B")
    src = folder.create(_cfg(tmp_path, path="src", version="v1"))
    src.pull(PKG, tmp_path / "out")
    (s / "split_old.apk").unlink()
    assert src.pull(PKG, tmp_path / "out")["pulled"]["apk"] == ["base.apk"]
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == ["apk"]
    assert sorted(p.name for p in (tmp_path / "out" / "apk").iterdir()) == ["base.apk"]


def test_failed_repull_keeps_previous_apks(tmp_path):
    s = tmp_path / "src"
    s.mkdir()
    (s / "base.apk").write_bytes(b"A")
    folder.create(_cfg(tmp_path, path="src", version="v1")).pull(PKG, tmp_path / "out")
    (s / "split.apk").write_bytes(b"B")
    (tmp_path / "out" / "data").write_bytes(b"not a folder")  # so copying notes.txt into data/ fails
    (s / "notes.txt").write_text("n")
    with pytest.raises(OSError):
        folder.create(_cfg(tmp_path, path="src", version="v1")).pull(PKG, tmp_path / "out")
    assert sorted(p.name for p in (tmp_path / "out" / "apk").iterdir()) == ["base.apk"]
    assert not (tmp_path / "out" / ".apk.partial").exists()
