""".rgbv: the game's frame-stream video. u32 LE fps, u32 LE frame count, then per frame u32 LE size + one JPEG."""
from __future__ import annotations

import struct
from dataclasses import dataclass

HEADER = struct.Struct("<II")
SIZE = struct.Struct("<I")
SOI, EOI = b"\xff\xd8", b"\xff\xd9"
# baseline, extended, progressive and lossless SOF markers carry the frame size
SOF_MARKERS = frozenset({0xC0, 0xC1, 0xC2, 0xC3})
STANDALONE = frozenset({0x01, *range(0xD0, 0xD8)})


@dataclass(frozen=True)
class Rgbv:
    fps: int
    frame_count: int
    frames: tuple[bytes, ...]

    @property
    def duration(self) -> float:
        return self.frame_count / self.fps if self.fps else 0.0


def parse(data: bytes) -> Rgbv:
    if len(data) < HEADER.size:
        raise ValueError(f"rgbv: {len(data)} bytes is shorter than the {HEADER.size}-byte header")
    fps, count = HEADER.unpack_from(data, 0)
    if fps == 0:
        raise ValueError("rgbv: fps is 0")
    frames: list[bytes] = []
    pos = HEADER.size
    while pos < len(data):
        if pos + SIZE.size > len(data):
            raise ValueError(f"rgbv: frame {len(frames)} size field at {pos} runs past the end")
        (size,) = SIZE.unpack_from(data, pos)
        start = pos + SIZE.size
        end = start + size
        if end > len(data):
            raise ValueError(f"rgbv: frame {len(frames)} at {pos} has size {size}, past the end ({len(data)})")
        frame = data[start:end]
        if not (frame.startswith(SOI) and frame.endswith(EOI)):
            raise ValueError(f"rgbv: frame {len(frames)} at {pos} is not a whole JPEG (no SOI/EOI)")
        frames.append(frame)
        pos = end
        if len(frames) == count:
            break
    if len(frames) != count:
        raise ValueError(f"rgbv: header says {count} frames, found {len(frames)}")
    if pos != len(data):
        raise ValueError(f"rgbv: {len(data) - pos} bytes left after {count} frames")
    return Rgbv(fps, count, tuple(frames))


def jpeg_size(frame: bytes) -> tuple[int, int]:
    """(width, height) from the JPEG's SOF header."""
    if not frame.startswith(SOI):
        raise ValueError("jpeg: no SOI marker")
    pos = 2
    while pos + 4 <= len(frame):
        if frame[pos] != 0xFF:
            raise ValueError(f"jpeg: expected a marker at {pos}")
        marker = frame[pos + 1]
        if marker == 0xFF:
            pos += 1  # fill byte
            continue
        if marker in STANDALONE:
            pos += 2
            continue
        if marker in (0xD9, 0xDA):
            break
        (length,) = struct.unpack_from(">H", frame, pos + 2)
        if marker in SOF_MARKERS:
            if pos + 9 > len(frame):
                break
            height, width = struct.unpack_from(">HH", frame, pos + 5)
            return width, height
        pos += 2 + length
    raise ValueError("jpeg: no SOF header before the image data")
