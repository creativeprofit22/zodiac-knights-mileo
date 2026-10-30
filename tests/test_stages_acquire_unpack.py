import hashlib
import json

import pytest

from zk import cli

PKG = "com.zodiacknights.game"


def _config(tmp_path, **opts):
    lines = ['workspace = "ws"', 'tools = "tools"', f'package = "{PKG}"',
             "[adapters]", 'device_source = "tests.fakes.fake_device"', "[options.device_source]"]
    lines += [f'{k} = "{v}"' for k, v in opts.items()]
    p = tmp_path / "zk.toml"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _manifest(tmp_path):
    return json.loads((tmp_path / "ws" / "manifest.json").read_text(encoding="utf-8"))


def test_acquire_then_unpack(tmp_path):
    cfg = _config(tmp_path)
    assert cli.main(["--config", str(cfg), "acquire"]) == 0
    m = _manifest(tmp_path)
    base = tmp_path / "ws" / "raw" / "0.4.6-17" / "apk" / "base.apk"
    acq = m["acquire"]
    assert acq["version"] == "0.4.6-17" and acq["package"] == PKG and acq["abi"] == "arm64-v8a"
    assert acq["base_apk"] == {"sha256": hashlib.sha256(base.read_bytes()).hexdigest(),
                               "bytes": base.stat().st_size}
    assert acq["pulled"]["apk"] == ["base.apk"]
    assert acq["adapters"]["device_source"]["module"] == "tests.fakes.fake_device"
    assert m["game"] == {"version": "0.4.6-17", "package": PKG}

    assert cli.main(["--config", str(cfg), "unpack"]) == 0
    u = _manifest(tmp_path)["unpack"]
    assert u["version"] == "0.4.6-17" and u["extracted"] == ["base.apk"]
    assert u["unity_version"] == "6000.3.2f1" and u["serialized_format"] == 22
    assert u["backend"] == "il2cpp"
    assert u["abis"] == ["arm64-v8a", "armeabi-v7a", "x86_64"]
    assert u["il2cpp"]["arm64-v8a"] == "base/lib/arm64-v8a/libil2cpp.so"
    assert u["metadata"] == {"path": "base/assets/bin/Data/Managed/Metadata/global-metadata.dat",
                             "magic": "0xFAB11BAF", "version": 39, "encrypted": False}
    assert u["assemblies"] == {"count": 7, "game": ["Assembly-CSharp", "ZodiacKnights.Game", "ZodiacKnights.Logic"]}
    # ggm, ggm.assets (3 splits = 1), level0, sharedassets0, 2 hashed files
    assert u["serialized_files"] == 6 and u["resource_streams"] == 2
    assert u["videos"] == {"files": [{"name": "intro.mp4", "bytes": 10}, {"name": "intro.rgbv", "bytes": 5}],
                           "manifest_json": True}
    assert u["warnings"] == []
    game = _manifest(tmp_path)["game"]
    assert game["unity_version"] == "6000.3.2f1" and game["metadata_version"] == 39
    assert game["backend"] == "il2cpp" and game["abis"] == ["arm64-v8a", "armeabi-v7a", "x86_64"]
    assert game["version"] == "0.4.6-17"

    # Reruns skip the pull and the extraction.
    assert cli.main(["--config", str(cfg), "acquire"]) == 0
    assert _manifest(tmp_path)["acquire"]["pulled"] is False
    assert cli.main(["--config", str(cfg), "unpack"]) == 0
    assert _manifest(tmp_path)["unpack"]["extracted"] == []
    assert cli.main(["--config", str(cfg), "unpack", "--force"]) == 0
    assert _manifest(tmp_path)["unpack"]["extracted"] == ["base.apk"]


def test_unknown_metadata_version_is_a_warning(tmp_path):
    cfg = _config(tmp_path, metadata_version="31")
    assert cli.main(["--config", str(cfg), "acquire"]) == 0
    assert cli.main(["--config", str(cfg), "unpack"]) == 0
    u = _manifest(tmp_path)["unpack"]
    assert u["metadata"]["version"] == 31 and u["metadata"]["encrypted"] is False
    assert len(u["warnings"]) == 1 and "metadata version 31" in u["warnings"][0]


@pytest.mark.parametrize("label", ["../evil", "a/b", "..", "", "a b"])
def test_bad_version_label_is_rejected(tmp_path, label, capsys):
    cfg = _config(tmp_path, version=label)
    assert cli.main(["--config", str(cfg), "acquire"]) == 2
    assert "unusable version label" in capsys.readouterr().err
    assert not (tmp_path / "ws" / "raw").exists() or not any((tmp_path / "ws" / "raw").iterdir())


def test_unpack_before_acquire(tmp_path, capsys):
    assert cli.main(["--config", str(_config(tmp_path)), "unpack"]) == 2
    assert "zk acquire" in capsys.readouterr().err


def test_inventory_of_empty_tree_warns(tmp_path):
    from zk.stages.unpack import inventory

    (tmp_path / "base").mkdir()
    inv = inventory(tmp_path)
    assert inv["backend"] == "unknown" and inv["unity_version"] is None and inv["abis"] == []
    assert any("globalgamemanagers" in w for w in inv["warnings"])
    assert any("ScriptingAssemblies.json" in w for w in inv["warnings"])


def test_unknown_unity_version_is_a_warning(tmp_path):
    cfg = _config(tmp_path, unity_version="6000.4.0f1")
    assert cli.main(["--config", str(cfg), "acquire"]) == 0
    assert cli.main(["--config", str(cfg), "unpack"]) == 0
    u = _manifest(tmp_path)["unpack"]
    assert u["unity_version"] == "6000.4.0f1"
    assert len(u["warnings"]) == 1 and "Unity version 6000.4.0f1" in u["warnings"][0]
