import json
import shutil

import pytest

from tests.fakes import fake_unity as fu
from zk import cli
from zk.stages.assets import _known, _unity

GOOD = ("UnityEngine.UI", "UnityEngine.UI.Image")


def _config(tmp_path):
    lines = ['workspace = "ws"', 'tools = "tools"', 'package = "com.zodiacknights.game"', "[adapters]",
             'device_source = "tests.fakes.fake_device"', 'il2cpp_dump = "tests.fakes.fake_dump_a"',
             'il2cpp_crosscheck = "tests.fakes.fake_crosscheck"',
             'java_decompiler = "tests.fakes.fake_java_decompiler"', 'type_info = "tests.fakes.fake_type_info"']
    p = tmp_path / "zk.toml"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _manifest(tmp_path):
    return json.loads((tmp_path / "ws" / "manifest.json").read_text(encoding="utf-8"))


def _coded(tmp_path, unity="7777.1.2f3"):
    cfg = _config(tmp_path)
    for stage in ("acquire", "unpack", "code"):
        assert cli.main(["--config", str(cfg), stage]) == 0
    m = _manifest(tmp_path)
    m["game"]["unity_version"] = unity  # a different synthetic fact must flow through to type_info
    (tmp_path / "ws" / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    return cfg


def _objects(extra=()):
    return [fu.texture(1), fu.texture(2, "empty", width=0), fu.sprite(3), fu.audio(4), fu.font(5), fu.text(6),
            fu.shader(7), *fu.scene_objects(), fu.mono(40, GOOD, file="sharedassets0.assets"), *extra]


@pytest.fixture
def load(monkeypatch):
    holder = {"objects": _objects(), "calls": 0}

    def fake_load(data_dir):
        holder["calls"] += 1
        assert data_dir.name == "Data" and (data_dir / "Managed").is_dir()
        return fu.loaded(holder["objects"])
    monkeypatch.setattr(_unity, "load", fake_load)
    return holder


def _report(tmp_path):
    return json.loads(next((tmp_path / "ws" / "assets").glob("*/report.json")).read_text(encoding="utf-8"))


def test_assets_exports_reports_and_records(tmp_path, load):
    cfg = _coded(tmp_path)
    assert cli.main(["--config", str(cfg), "assets"]) == 0
    rec = _manifest(tmp_path)["assets"]
    assert rec["unity_version"] == "7777.1.2f3" and rec["type_info"]["unity_version"] == "7777.1.2f3"
    nodes = json.loads(next((tmp_path / "ws" / "types").glob("*/nodes.json")).read_text(encoding="utf-8"))
    assert nodes["unity_version"] == "7777.1.2f3"
    r = _report(tmp_path)
    assert r["inventory"] == {"AudioClip": 1, "Font": 1, "MonoBehaviour": 3, "Shader": 1, "Sprite": 1,
                              "TextAsset": 1, "Texture2D": 2}
    assert r["exported"]["Texture2D"] == 1 and r["exported"]["Shader"] == 1
    assert r["misses"] == [{"object": "sharedassets0.assets:2", "type": "Texture2D", "name": "empty",
                            "error": "empty texture (m_Width 0)"}]
    assert r["monobehaviours"] == {"total": 3, "json": 3, "failed": 0, "by_reason": {}, "failures": [],
                                   "unexplained": []}
    assert set(r["crosscheck"]["assemblies"]) == {"UnityEngine.UI"} and r["crosscheck"]["unexplained"] == 0
    scene = json.loads((tmp_path / "ws" / "assets" / rec["version"] / "scenes" / "Main.json").read_text("utf-8"))
    assert scene["file"] == "level0" and [g["name"] for g in scene["roots"]] == ["Root", "Lone"]
    assert r["scenes"]["Assets/_Project/Scenes/Main.unity"]["game_objects"] == 3
    assert {"type": "MonoBehaviour", "path_id": 22} in scene["objects"] and len(scene["objects"]) == 8


def test_assets_resumes_from_index(tmp_path, load):
    cfg = _coded(tmp_path)
    assert cli.main(["--config", str(cfg), "assets", "--limit", "2"]) == 0
    assert _manifest(tmp_path)["assets"]["exported_this_run"] == 2
    assert cli.main(["--config", str(cfg), "assets"]) == 0
    first_tex = load["objects"][0]
    assert first_tex.reads == 1  # done in run 1, skipped in run 2
    assert _manifest(tmp_path)["assets"]["exported_this_run"] == 8  # 7 untouched + the missed empty texture, retried
    out = tmp_path / "ws" / "assets" / _manifest(tmp_path)["assets"]["version"]
    (out / "textures" / "tex_1.png").unlink()
    assert cli.main(["--config", str(cfg), "assets"]) == 0
    assert first_tex.reads == 2 and (out / "textures" / "tex_1.png").is_file()


def test_unexplained_monobehaviour_failure_fails_the_stage(tmp_path, load, monkeypatch):
    load["objects"] = _objects([fu.mono(50, ("UnityEngine.UI", "UnityEngine.UI.Missing")),
                                fu.mono(51, GOOD, read_fails="read_str out of bounds")])
    cfg = _coded(tmp_path)
    assert cli.main(["--config", str(cfg), "assets"]) == 2
    assert "assets" not in _manifest(tmp_path)
    mb = _report(tmp_path)["monobehaviours"]
    assert mb["by_reason"] == {"class_missing_in_type_info": 1, "read_error": 1}
    assert [(f["script_class"], f["error"]) for f in mb["failures"]] == [
        ("UnityEngine.UI.Missing", "AssertionError: failed to dump nodes raw"),
        ("UnityEngine.UI.Image", "EOFError: read_str out of bounds")]
    monkeypatch.setitem(_known.MONOBEHAVIOURS, "UnityEngine.UI|UnityEngine.UI.Missing", "engine class")
    monkeypatch.setitem(_known.MONOBEHAVIOURS, "UnityEngine.UI|UnityEngine.UI.Image", "explained")
    assert cli.main(["--config", str(cfg), "assets"]) == 0
    assert _manifest(tmp_path)["assets"]["monobehaviours"]["failed"] == 2


def test_assets_needs_crosscheck(tmp_path, load):
    cfg = _coded(tmp_path)
    v = _manifest(tmp_path)["game"]["version"]
    shutil.rmtree(tmp_path / "ws" / "il2cpp" / v / "crosscheck")
    assert cli.main(["--config", str(cfg), "assets"]) == 2
    assert "assets" not in _manifest(tmp_path) and load["calls"] == 0


def test_assets_needs_code_record(tmp_path, load):
    cfg = _config(tmp_path)
    for stage in ("acquire", "unpack"):
        assert cli.main(["--config", str(cfg), stage]) == 0
    assert cli.main(["--config", str(cfg), "assets"]) == 2


def test_managed_references_are_requested_and_passed_to_the_reader(tmp_path, load):
    import struct

    def s(text):
        b = text.encode()
        return struct.pack("<i", len(b)) + b + bytes(-len(b) % 4)
    holder = fu.mono(60, GOOD)
    holder.raw_bytes = struct.pack("<q", 1) + s("Battle") + s("ZK") + s("ZodiacKnights.Game") + s("Nope") + s("") + s("X")
    load["objects"] = _objects([holder])
    cfg = _coded(tmp_path)
    assert cli.main(["--config", str(cfg), "assets"]) == 0
    v = _manifest(tmp_path)["assets"]["version"]
    req = json.loads((tmp_path / "ws" / "types" / v / "classes.json").read_text(encoding="utf-8"))
    assert {"assembly": "ZodiacKnights.Game", "class": "ZK.Battle", "reference": True} in req
    assert not any(r["class"] == "Nope" for r in req)
    assert holder.refs == {("Battle", "ZK", "ZodiacKnights.Game"): [
        {"m_Type": "ZK.Battle", "m_Name": "Base", "m_Level": 0, "m_MetaFlag": 0}]}
    assert _manifest(tmp_path)["assets"]["type_info"]["unity_version"] == "7777.1.2f3"
