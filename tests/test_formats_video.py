import json
import struct

import pytest

from zk.formats import mp4, rgbv, video_manifest


def jpeg(w=4, h=2):
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    app = b"\xff\xe0" + struct.pack(">H", 4) + b"JF"
    return b"\xff\xd8" + app + sof + b"\xff\xda\x00\x02" + b"\x00" * 3 + b"\xff\xd9"


def rgbv_bytes(fps=15, frames=None, count=None):
    frames = [jpeg(), jpeg(), jpeg()] if frames is None else frames
    body = b"".join(struct.pack("<I", len(f)) + f for f in frames)
    return struct.pack("<II", fps, len(frames) if count is None else count) + body


def test_rgbv_parses_frames():
    r = rgbv.parse(rgbv_bytes())
    assert (r.fps, r.frame_count, len(r.frames), r.duration) == (15, 3, 3, 0.2)
    assert all(f == jpeg() for f in r.frames)
    assert rgbv.jpeg_size(r.frames[0]) == (4, 2)


@pytest.mark.parametrize("data, msg", [
    (b"\x01\x00", "shorter than"),
    (rgbv_bytes()[:-3], "past the end"),
    (rgbv_bytes(fps=0), "fps is 0"),
    (rgbv_bytes(frames=[b"\xff\xd8xx"]), "not a whole JPEG"),
    (rgbv_bytes(count=4), "header says 4 frames, found 3"),
    (rgbv_bytes(count=2), "bytes left after 2 frames"),
    (rgbv_bytes(count=4) + b"\x00\x00", "size field"),
])
def test_rgbv_rejects_bad_bytes(data, msg):
    with pytest.raises(ValueError, match=msg):
        rgbv.parse(data)


def test_jpeg_size_needs_sof():
    with pytest.raises(ValueError, match="no SOF"):
        rgbv.jpeg_size(b"\xff\xd8\xff\xda\x00\x02\xff\xd9")
    with pytest.raises(ValueError, match="no SOI"):
        rgbv.jpeg_size(b"xx")


def box(kind, payload):
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def header(timescale, duration, version=0):
    if version:
        return bytes([1, 0, 0, 0]) + bytes(16) + struct.pack(">IQ", timescale, duration) + bytes(4)
    return bytes(12) + struct.pack(">II", timescale, duration) + bytes(4)


def trak(handler, w=1280, h=720, frames=(90, 30), timescale=15360, duration=61440):
    tkhd = box(b"tkhd", bytes(76) + struct.pack(">II", w << 16, h << 16))
    stts = box(b"stts", bytes(4) + struct.pack(">I", len(frames))
               + b"".join(struct.pack(">II", n, 512) for n in frames))
    mdia = box(b"mdia", box(b"mdhd", header(timescale, duration)) + box(b"hdlr", bytes(8) + handler + bytes(12))
               + box(b"minf", box(b"stbl", stts)))
    return box(b"trak", tkhd + mdia)


def mp4_bytes(version=0, tracks=None):
    tracks = [trak(b"soun", 0, 0), trak(b"vide")] if tracks is None else tracks
    moov = box(b"moov", box(b"mvhd", header(1000, 4020, version)) + b"".join(tracks))
    return box(b"ftyp", b"isom") + moov + box(b"mdat", b"\x00" * 4)


@pytest.mark.parametrize("version", [0, 1])
def test_mp4_reads_duration_size_and_fps(version):
    info = mp4.parse(mp4_bytes(version))
    assert info.duration == 4.02
    assert info.video == mp4.VideoTrack(1280, 720, 120, 4.0)
    assert info.video is not None and info.video.fps == 30.0


def test_mp4_without_video_track():
    assert mp4.parse(mp4_bytes(tracks=[trak(b"soun")])).video is None


@pytest.mark.parametrize("data, msg", [
    (box(b"ftyp", b"isom"), "no moov"),
    (box(b"moov", b""), "no mvhd"),
    (b"\x00\x00\x00\x20moov", "bad size"),
    (b"\x00\x00\x00", "truncated box header"),
])
def test_mp4_rejects_bad_boxes(data, msg):
    with pytest.raises(ValueError, match=msg):
        mp4.parse(data)


CLIP = {"name": "a.mp4", "bytes": 10, "sha256": "ab", "duration": 4.2, "fps": 30.0, "width": 1280,
        "height": 720, "loop": False}


def test_manifest_parses_clips():
    m = video_manifest.parse(json.dumps({"version": 35, "clips": [CLIP]}))
    assert m.version == 35
    assert m.clips == (video_manifest.Clip("a.mp4", 10, "ab", 4.2, 30.0, 1280, 720),)


@pytest.mark.parametrize("doc, msg", [
    ([], "expected an object"),
    ({"clips": []}, "'version' must be an integer"),
    ({"version": 1, "clips": {}}, "'clips' must be a list"),
    ({"version": 1, "clips": [{k: v for k, v in CLIP.items() if k != "sha256"}]}, "clip 0: 'sha256'"),
    ({"version": 1, "clips": [{**CLIP, "width": True}]}, "'width' must be an integer"),
    ({"version": 1, "clips": [{**CLIP, "fps": "30"}]}, "'fps' must be a number"),
    ({"version": 1, "clips": [CLIP, CLIP]}, "duplicate clip 'a.mp4'"),
])
def test_manifest_rejects_bad_docs(doc, msg):
    with pytest.raises(ValueError, match=msg):
        video_manifest.parse(json.dumps(doc))
