"""MP4 (ISO BMFF) box walk: movie duration and the first video track's size and frame rate. Never decodes video."""
from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass

@dataclass(frozen=True)
class VideoTrack:
    width: int
    height: int
    frames: int
    duration: float  # media duration from mdhd, seconds

    @property
    def fps(self) -> float:
        return self.frames / self.duration if self.duration else 0.0


@dataclass(frozen=True)
class Mp4Info:
    duration: float  # movie duration from mvhd, seconds
    video: VideoTrack | None


def boxes(data: bytes, start: int = 0, end: int | None = None) -> Iterator[tuple[bytes, bytes]]:
    """(type, payload) of each box in data[start:end]."""
    end = len(data) if end is None else end
    pos = start
    while pos < end:
        if pos + 8 > end:
            raise ValueError(f"mp4: truncated box header at {pos}")
        size, kind = struct.unpack_from(">I4s", data, pos)
        head = 8
        if size == 1:
            if pos + 16 > end:
                raise ValueError(f"mp4: truncated 64-bit box size at {pos}")
            (size,) = struct.unpack_from(">Q", data, pos + 8)
            head = 16
        elif size == 0:
            size = end - pos
        if size < head or pos + size > end:
            raise ValueError(f"mp4: box {kind!r} at {pos} has bad size {size}")
        yield kind, data[pos + head:pos + size]
        pos += size


def _child(payload: bytes, kind: bytes) -> bytes | None:
    return next((p for k, p in boxes(payload) if k == kind), None)


def _path(payload: bytes, *kinds: bytes) -> bytes | None:
    cur: bytes | None = payload
    for k in kinds:
        if cur is None:
            return None
        cur = _child(cur, k)
    return cur


def _timing(payload: bytes) -> tuple[int, int]:
    """(timescale, duration) of an mvhd or mdhd payload."""
    if not payload:
        raise ValueError("mp4: empty header box")
    if payload[0] == 1:
        if len(payload) < 32:
            raise ValueError("mp4: truncated v1 header box")
        timescale, duration = struct.unpack_from(">IQ", payload, 20)
    else:
        if len(payload) < 20:
            raise ValueError("mp4: truncated v0 header box")
        timescale, duration = struct.unpack_from(">II", payload, 12)
    return timescale, duration


def _seconds(payload: bytes) -> float:
    timescale, duration = _timing(payload)
    return duration / timescale if timescale else 0.0


def _video(trak: bytes) -> VideoTrack | None:
    hdlr = _path(trak, b"mdia", b"hdlr")
    if hdlr is None or len(hdlr) < 12 or hdlr[8:12] != b"vide":
        return None
    tkhd, mdhd = _child(trak, b"tkhd"), _path(trak, b"mdia", b"mdhd")
    stts = _path(trak, b"mdia", b"minf", b"stbl", b"stts")
    if tkhd is None or mdhd is None or stts is None:
        raise ValueError("mp4: video track lacks tkhd, mdhd or stts")
    if len(tkhd) < 8:
        raise ValueError("mp4: truncated tkhd")
    width, height = struct.unpack_from(">II", tkhd, len(tkhd) - 8)  # 16.16 fixed point, last two fields
    if len(stts) < 8:
        raise ValueError("mp4: truncated stts")
    (entries,) = struct.unpack_from(">I", stts, 4)
    if len(stts) < 8 + 8 * entries:
        raise ValueError("mp4: stts entries run past the box")
    frames = sum(struct.unpack_from(">I", stts, 8 + 8 * i)[0] for i in range(entries))
    return VideoTrack(width >> 16, height >> 16, frames, _seconds(mdhd))


def parse(data: bytes) -> Mp4Info:
    moov = _child(data, b"moov")
    if moov is None:
        raise ValueError("mp4: no moov box")
    mvhd = _child(moov, b"mvhd")
    if mvhd is None:
        raise ValueError("mp4: no mvhd box")
    video = next((v for k, p in boxes(moov) if k == b"trak" and (v := _video(p)) is not None), None)
    return Mp4Info(_seconds(mvhd), video)
