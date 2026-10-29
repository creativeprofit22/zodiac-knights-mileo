# ADR 0007: `video_encoder` contract v1 (frames to MP4)

Status: accepted

## Context

The game ships each clip in `assets/Video/` twice: `<clip>.mp4` and `<clip>.rgbv`, a custom container of whole JPEG frames (see [rgbv](../formats/rgbv.md)). On 0.4.6-17 the two copies differ for four clips: the `.rgbv` is 15 fps at 960x540 while the `.mp4` is 30 fps at 1280x720. The game's `manifest.json` (version 35) matches neither copy for any clip. Reading and checking the files needs no tool, but turning exported frames back into a playable video does, and ffmpeg is a large native binary with no single pinned download for every platform.

## Decision

- New port `video_encoder`, contract v1: `encode(frames_dir, fps, out) -> dict`, `files=("encoded.mp4",)`. `frames_dir` holds `frame_0000.jpg …` as written by `zk video`; `fps` is the `.rgbv` header value.
- The contract also requires `encoded.mp4` to be non-empty (`verify_output`).
- The `ffmpeg` adapter uses a user-installed ffmpeg: `[options.video_encoder] path`, else `ffmpeg` on PATH. Nothing is downloaded and it has no `TOOLS` entry.
- Only `zk video --encode` reaches the port. Parsing `.rgbv`, `.mp4` and `manifest.json` stays in pure `zk.formats` parsers.
- A manifest that disagrees with the shipped files is a finding in `report.json`, never a stage failure.

## Consequences

- `zk video` runs everywhere, including CI, without ffmpeg; `--encode` fails with a clear "install ffmpeg or drop --encode" error.
- Tests cover the adapter by its command line and the stage with a fake encoder.
