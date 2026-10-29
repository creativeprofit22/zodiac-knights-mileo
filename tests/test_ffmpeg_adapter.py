import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from zk.adapters import ffmpeg
from zk.ports.video_encoder import OUTPUT, VideoEncoder

EXE = Path("bin/ffmpeg")


def test_command_line():
    assert ffmpeg.command(EXE, Path("f"), 15, Path("o/encoded.mp4")) == [
        str(EXE), "-hide_banner", "-loglevel", "error", "-y", "-framerate", "15", "-start_number", "0",
        "-i", str(Path("f") / "frame_%04d.jpg"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(Path("o/encoded.mp4"))]


def test_satisfies_port():
    assert isinstance(ffmpeg.Ffmpeg(), VideoEncoder)


def test_missing_ffmpeg_is_clear_and_never_runs(tmp_path):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    enc = ffmpeg.Ffmpeg(run=run, which=lambda name: None)
    with pytest.raises(RuntimeError, match="install ffmpeg .* or drop --encode"):
        enc.encode(tmp_path, 30, tmp_path / OUTPUT)
    with pytest.raises(RuntimeError, match="is not a file"):
        ffmpeg.Ffmpeg(tmp_path / "nope").encode(tmp_path, 30, tmp_path / OUTPUT)
    assert calls == []


def test_encode_runs_found_exe_and_checks_output(tmp_path):
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw))
        Path(cmd[-1]).write_bytes(b"mp4")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    out = tmp_path / "v" / OUTPUT
    info = ffmpeg.Ffmpeg(run=run, which=lambda name: "/usr/bin/ffmpeg").encode(tmp_path, 15, out)
    assert info == {"tool": "ffmpeg", "exe": str(Path("/usr/bin/ffmpeg")), "fps": 15, "bytes": 3}
    assert calls[0][0][0] == str(Path("/usr/bin/ffmpeg")) and calls[0][1]["stdin"] == subprocess.DEVNULL


def test_encode_failure_and_empty_output(tmp_path):
    def fail(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, "", "boom")

    def empty(cmd, **kw):
        Path(cmd[-1]).write_bytes(b"")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with pytest.raises(RuntimeError, match="ffmpeg exit 1: boom"):
        ffmpeg.Ffmpeg(run=fail, which=lambda n: "ff").encode(tmp_path, 30, tmp_path / OUTPUT)
    with pytest.raises(RuntimeError, match="is empty"):
        ffmpeg.Ffmpeg(run=empty, which=lambda n: "ff").encode(tmp_path, 30, tmp_path / OUTPUT)


def test_create_reads_path_option(tmp_path):
    cfg = SimpleNamespace(root=tmp_path, options={"video_encoder": {"path": "tools/ffmpeg.exe"}})
    assert ffmpeg.create(cfg).path == tmp_path / "tools/ffmpeg.exe"
    assert ffmpeg.create(SimpleNamespace(root=tmp_path, options={})).path is None
