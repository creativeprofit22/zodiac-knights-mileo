import hashlib
import json
import struct

from tests.test_formats_video import box, header, jpeg, rgbv_bytes, trak
from zk import cli

VERSION = "0.4.6-17"


def _config(tmp_path, encoder="tests.fakes.fake_video_encoder"):
    lines = ['workspace = "ws"', 'tools = "tools"', 'package = "com.zodiacknights.game"', "[adapters]",
             'device_source = "tests.fakes.fake_device"', f'video_encoder = "{encoder}"']
    p = tmp_path / "zk.toml"
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _mp4(w=4, h=2):
    moov = box(b"moov", box(b"mvhd", header(1000, 200)) + trak(b"vide", w, h, frames=(3,), duration=3072))
    return box(b"ftyp", b"isom") + moov


def _clip(name, data, **kw):
    return {"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "duration": 0.2,
            "fps": 15.0, "width": 4, "height": 2, "loop": False, **kw}


def _setup(tmp_path, **cfg):
    """acquire + unpack with the fake device, then swap in a synthetic Video folder: a ok, b fps wrong, c missing."""
    config = _config(tmp_path, **cfg)
    for argv in (["acquire"], ["unpack"]):
        assert cli.main(["--config", str(config), *argv]) == 0
    vdir = tmp_path / "ws" / "unpacked" / VERSION / "base" / "assets" / "Video"
    for f in vdir.iterdir():
        f.unlink()
    mp4 = _mp4()
    for name in ("a", "b"):
        (vdir / f"{name}.mp4").write_bytes(mp4)
        (vdir / f"{name}.rgbv").write_bytes(rgbv_bytes())
    clips = [_clip("a.mp4", mp4), _clip("b.mp4", mp4, fps=30.0), _clip("c.mp4", mp4)]
    (vdir / "manifest.json").write_text(json.dumps({"version": 35, "clips": clips}), encoding="utf-8")
    return config, vdir


def _out(tmp_path):
    return tmp_path / "ws" / "assets" / VERSION / "video"


def _run(config, *argv):
    return cli.main(["--config", str(config), "video", *argv])


def _record(tmp_path):
    return json.loads((tmp_path / "ws" / "manifest.json").read_text(encoding="utf-8"))["video"]


def test_exports_frames_and_reports_mismatches(tmp_path):
    config, _ = _setup(tmp_path)
    assert _run(config) == 0
    rec = _record(tmp_path)
    assert (rec["clips"], rec["exported"], rec["frames"], rec["manifest_version"]) == (3, 2, 6, 35)
    assert rec["mismatched_clips"] == ["b", "c"] and rec["encoded"] == {}
    out = _out(tmp_path)
    assert (out / "a" / "frame_0002.jpg").read_bytes() == jpeg()
    assert json.loads((out / "a" / "index.json").read_text(encoding="utf-8")) == {
        "source": "a.rgbv", "fps": 15, "frames": 3, "width": 4, "height": 2, "uniform_size": True}
    report = {c["clip"]: c for c in json.loads((out / "report.json").read_text(encoding="utf-8"))["clips"]}
    assert report["a"]["ok"] and all(c["ok"] for c in report["a"]["checks"])
    bad_b = {c["field"]: (c["expected"], c["actual"]) for c in report["b"]["checks"] if not c["ok"]}
    assert bad_b == {"mp4.fps": (30.0, 15.0), "rgbv.fps": (30.0, 15)}
    bad_c = [c["field"] for c in report["c"]["checks"] if not c["ok"]]
    assert bad_c == ["mp4.present", "rgbv.present"] and report["c"]["rgbv"] is None
    assert rec["mismatches"] == 4


def test_size_and_hash_mismatch_is_reported(tmp_path):
    config, vdir = _setup(tmp_path)
    (vdir / "a.mp4").write_bytes(_mp4() + b"\x00\x00\x00\x08free")
    assert _run(config) == 0
    report = json.loads((_out(tmp_path) / "report.json").read_text(encoding="utf-8"))
    a = next(c for c in report["clips"] if c["clip"] == "a")
    assert [c["field"] for c in a["checks"] if not c["ok"]] == ["mp4.bytes", "mp4.sha256"]


def test_resume_skips_exported_clips_and_force_redoes_them(tmp_path):
    config, _ = _setup(tmp_path)
    assert _run(config) == 0
    stale = _out(tmp_path) / "a" / "stale.txt"
    stale.write_text("x", encoding="utf-8")
    assert _run(config) == 0 and _record(tmp_path)["exported"] == 0
    assert _record(tmp_path)["frames"] == 6 and stale.exists()
    assert _run(config, "--force") == 0 and _record(tmp_path)["exported"] == 2
    assert not stale.exists()


def test_bad_rgbv_fails_the_stage(tmp_path, capsys):
    config, vdir = _setup(tmp_path)
    (vdir / "b.rgbv").write_bytes(struct.pack("<II", 15, 9) + b"\x00")
    assert _run(config) == 2
    assert "b.rgbv" in capsys.readouterr().err
    (vdir / "b.rgbv").write_bytes(struct.pack("<II", 0, 0))
    assert _run(config) == 2
    err = capsys.readouterr().err
    assert "b.rgbv" in err and "fps is 0" in err


def test_missing_video_folder_or_manifest_fails(tmp_path, capsys):
    config, vdir = _setup(tmp_path)
    (vdir / "manifest.json").unlink()
    assert _run(config) == 2 and "manifest.json is missing" in capsys.readouterr().err
    for f in vdir.iterdir():
        f.unlink()
    vdir.rmdir()
    assert _run(config) == 2 and "no assets/Video folder" in capsys.readouterr().err


def test_encode_goes_through_the_port(tmp_path):
    config, _ = _setup(tmp_path)
    assert _run(config, "--encode") == 0
    rec = _record(tmp_path)
    assert rec["encoded"] == {n: {"tool": "fake", "frames": 3, "fps": 15} for n in ("a", "b")}
    assert (_out(tmp_path) / "a" / "encoded.mp4").read_bytes() == b"fake 3 frames @ 15"
    assert _run(config, "--encode") == 0 and _record(tmp_path)["encoded"] == {}


def test_encode_without_ffmpeg_fails_clearly(tmp_path, capsys, monkeypatch):
    config, _ = _setup(tmp_path, encoder="ffmpeg")
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert _run(config) == 0
    assert _run(config, "--encode") == 2
    assert "install ffmpeg" in capsys.readouterr().err


def test_encoder_that_writes_an_empty_file_fails_the_stage(tmp_path, capsys):
    config, _ = _setup(tmp_path, encoder="tests.fakes.fake_empty_video_encoder")
    assert _run(config, "--encode") == 2
    assert "is empty" in capsys.readouterr().err


def test_empty_encoded_file_is_reencoded_without_force(tmp_path):
    config, _ = _setup(tmp_path)
    assert _run(config) == 0
    target = _out(tmp_path) / "a" / "encoded.mp4"
    target.write_bytes(b"")
    assert _run(config, "--encode") == 0
    assert set(_record(tmp_path)["encoded"]) == {"a", "b"}
    assert target.read_bytes() == b"fake 3 frames @ 15"
