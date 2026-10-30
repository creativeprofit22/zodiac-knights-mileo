"""video: export the frames of each .rgbv clip and check every clip against assets/Video/manifest.json.

Input: the unpacked assets/Video/ folder (<clip>.mp4, <clip>.rgbv, manifest.json) recorded by `zk unpack`.
Output: video/<version>/<clip>/frame_NNNN.jpg + index.json, and video/<version>/report.json.
A manifest that disagrees with the shipped files is a finding in the report, never a stage failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from zk.formats import mp4, rgbv, video_manifest
from zk.ports.video_encoder import OUTPUT, verify_output

NAME = "video"
HELP = "export .rgbv frames as JPEGs and check every clip against the game's video manifest.json"

VIDEO = "assets/Video"
MANIFEST = "manifest.json"
INDEX = "index.json"
REPORT = "report.json"
DURATION_TOLERANCE = 0.05  # seconds; container rounding, not a real disagreement
FPS_TOLERANCE = 0.01


def add_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--encode", action="store_true",
                   help="also encode each clip's frames to encoded.mp4 through the video_encoder port (needs ffmpeg)")
    p.add_argument("--force", action="store_true", help="export (and encode) every clip again")


def find_video_dir(ctx, version: str) -> Path:
    unpack = ctx.ws.manifest().get("unpack")
    if not unpack or unpack.get("version") != version:
        raise RuntimeError(f"no unpack record for {version}: run `zk unpack` first")
    if not (unpack.get("videos") or {}).get("files"):
        raise RuntimeError(f"unpack found no files in {VIDEO}: nothing to export")
    root = ctx.ws.dir("unpacked", version)
    found = sorted(r / VIDEO for r in root.iterdir() if (r / VIDEO).is_dir())
    if not found:
        raise RuntimeError(f"no {VIDEO} folder under {root}: run `zk unpack --force`")
    return found[0]


def check(field: str, expected: object, actual: object, ok: bool | None = None) -> dict:
    return {"field": field, "expected": expected, "actual": actual, "ok": expected == actual if ok is None else ok}


def _close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol


def mp4_checks(clip: video_manifest.Clip, data: bytes) -> list[dict]:
    out = [check("mp4.bytes", clip.bytes, len(data)),
           check("mp4.sha256", clip.sha256.lower(), hashlib.sha256(data).hexdigest())]
    try:
        info = mp4.parse(data)
    except ValueError as e:
        return out + [check("mp4.parse", "ok", str(e), False)]
    out.append(check("mp4.duration", clip.duration, round(info.duration, 3),
                     _close(clip.duration, info.duration, DURATION_TOLERANCE)))
    if info.video is None:
        return out + [check("mp4.video_track", "present", "missing", False)]
    fps = round(info.video.fps, 3)
    return out + [check("mp4.fps", clip.fps, fps, _close(clip.fps, fps, FPS_TOLERANCE)),
                  check("mp4.width", clip.width, info.video.width),
                  check("mp4.height", clip.height, info.video.height)]


def rgbv_checks(clip: video_manifest.Clip, idx: dict) -> list[dict]:
    duration = round(idx["frames"] / idx["fps"], 3)
    return [check("rgbv.fps", clip.fps, idx["fps"], _close(clip.fps, idx["fps"], FPS_TOLERANCE)),
            check("rgbv.duration", clip.duration, duration, _close(clip.duration, duration, DURATION_TOLERANCE)),
            check("rgbv.width", clip.width, idx["width"]),
            check("rgbv.height", clip.height, idx["height"])]


def export_rgbv(src: Path, dst: Path, force: bool) -> tuple[dict, bool]:
    """Write every frame's JPEG bytes unchanged; index.json is written last, so its presence means complete."""
    index = dst / INDEX
    if index.is_file() and not force:
        return json.loads(index.read_text(encoding="utf-8")), False
    if dst.exists():
        shutil.rmtree(dst)
    try:
        clip = rgbv.parse(src.read_bytes())
        sizes = sorted({rgbv.jpeg_size(f) for f in clip.frames})
    except ValueError as e:
        raise RuntimeError(f"{src}: {e}") from e
    if not sizes:
        raise RuntimeError(f"{src}: no frames")
    dst.mkdir(parents=True)
    for i, frame in enumerate(clip.frames):
        (dst / f"frame_{i:04d}.jpg").write_bytes(frame)
    (width, height) = sizes[0]
    idx = {"source": src.name, "fps": clip.fps, "frames": clip.frame_count, "width": width, "height": height,
           "uniform_size": len(sizes) == 1}
    index.write_text(json.dumps(idx, indent=2), encoding="utf-8")
    return idx, True


def execute(ctx, args: argparse.Namespace) -> dict:
    version = ctx.ws.current_version()
    vdir = find_video_dir(ctx, version)
    mpath = vdir / MANIFEST
    if not mpath.is_file():
        raise RuntimeError(f"{mpath} is missing: run `zk unpack --force`")
    try:
        manifest = video_manifest.parse(mpath.read_text(encoding="utf-8"))
    except ValueError as e:
        raise RuntimeError(f"{mpath}: {e}") from e

    expected = {Path(c.name).stem: c for c in manifest.clips}
    mp4s = {p.stem: p for p in vdir.glob("*.mp4")}
    rgbvs = {p.stem: p for p in vdir.glob("*.rgbv")}
    out = ctx.ws.dir("video", version)
    encoder = ctx.adapter("video_encoder") if args.encode else None

    clips: list[dict] = []
    exported = frames = mismatches = 0
    encoded: dict[str, dict] = {}
    for name in sorted(set(expected) | set(mp4s) | set(rgbvs)):
        clip, mp4_path, rgbv_path = expected.get(name), mp4s.get(name), rgbvs.get(name)
        checks = [check(f"{kind}.present", True, have) for kind, have in
                  (("manifest", clip is not None), ("mp4", mp4_path is not None), ("rgbv", rgbv_path is not None))]
        idx = None
        if rgbv_path is not None:
            print(f"[video] {name}")
            idx, wrote = export_rgbv(rgbv_path, out / name, args.force)
            exported += wrote
            frames += idx["frames"]
            checks.append(check("rgbv.uniform_size", True, idx["uniform_size"]))
        if clip is not None and mp4_path is not None:
            checks += mp4_checks(clip, mp4_path.read_bytes())
        if clip is not None and idx is not None:
            checks += rgbv_checks(clip, idx)
        bad = sum(not c["ok"] for c in checks)
        mismatches += bad
        clips.append({"clip": name, "ok": bad == 0, "rgbv": idx, "checks": checks})

        if encoder is not None and idx is not None:
            target = out / name / OUTPUT
            # a zero-byte file is what a killed encoder leaves behind, so it is not a finished encode
            if target.is_file() and target.stat().st_size > 0 and not args.force:
                encoded[name] = {"skipped": True, "output": str(target), "bytes": target.stat().st_size}
                continue
            encoded[name] = encoder.encode(out / name, idx["fps"], target)
            verify_output(target)

    report = {"version": version, "manifest_version": manifest.version, "source": str(vdir),
              "mismatches": mismatches, "clips": clips, "encoded": encoded}
    (out / REPORT).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if mismatches:
        print(f"[video] {mismatches} manifest mismatch(es); see {out / REPORT}")
    return {"version": version, "path": str(out), "report": str(out / REPORT), "manifest_version": manifest.version,
            "clips": len(clips), "exported": exported, "frames": frames, "mismatches": mismatches,
            "mismatched_clips": [c["clip"] for c in clips if not c["ok"]], "encoded": encoded}
