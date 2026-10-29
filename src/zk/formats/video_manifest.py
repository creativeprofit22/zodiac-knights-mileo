"""assets/Video/manifest.json: the game's list of shipped clips with size, hash and timing."""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Clip:
    name: str
    bytes: int
    sha256: str
    duration: float
    fps: float
    width: int
    height: int


@dataclass(frozen=True)
class VideoManifest:
    version: int
    clips: tuple[Clip, ...]


def _int(clip: dict, key: str, where: str) -> int:
    v = clip.get(key)
    if isinstance(v, bool) or not isinstance(v, int):
        raise ValueError(f"{where}: {key!r} must be an integer")
    return v


def _num(clip: dict, key: str, where: str) -> float:
    v = clip.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError(f"{where}: {key!r} must be a number")
    return float(v)


def _str(clip: dict, key: str, where: str) -> str:
    v = clip.get(key)
    if not isinstance(v, str) or not v:
        raise ValueError(f"{where}: {key!r} must be a non-empty string")
    return v


def parse(text: str) -> VideoManifest:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("video manifest: expected an object")
    version = _int(data, "version", "video manifest")
    clips = data.get("clips")
    if not isinstance(clips, list):
        raise ValueError("video manifest: 'clips' must be a list")
    out: list[Clip] = []
    for i, c in enumerate(clips):
        where = f"video manifest clip {i}"
        if not isinstance(c, dict):
            raise ValueError(f"{where}: expected an object")
        out.append(Clip(_str(c, "name", where), _int(c, "bytes", where), _str(c, "sha256", where),
                        _num(c, "duration", where), _num(c, "fps", where), _int(c, "width", where),
                        _int(c, "height", where)))
    names = [c.name for c in out]
    if dupes := sorted({n for n in names if names.count(n) > 1}):
        raise ValueError(f"video manifest: duplicate clip {dupes[0]!r}")
    return VideoManifest(version, tuple(out))
