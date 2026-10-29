# Stage: `video`

`zk video [--encode] [--force]`, module `zk/stages/video.py`

## Purpose
Export every `.rgbv` clip's frames as JPEGs and check each clip against the game's `assets/Video/manifest.json`.

## Inputs
- `unpacked/<v>/<stem>/assets/Video/`: `<clip>.mp4`, `<clip>.rgbv`, `manifest.json` (the `unpack` record must list video files)
- Game fact `version`
- Port `video_encoder`, only with `--encode`

## Outputs
- `assets/<v>/video/<clip>/frame_NNNN.jpg`: the `.rgbv` JPEG bytes, unchanged
- `assets/<v>/video/<clip>/index.json`: `source`, `fps`, `frames`, `width`, `height`, `uniform_size`; written last, so its presence means the clip is complete
- `assets/<v>/video/<clip>/encoded.mp4` with `--encode`
- `assets/<v>/video/report.json`: per clip, a list of checks `{field, expected, actual, ok}`:
  - `manifest.present`, `mp4.present`, `rgbv.present` (clips on only one side)
  - `mp4.bytes`, `mp4.sha256`, `mp4.duration`, `mp4.fps`, `mp4.width`, `mp4.height`
  - `rgbv.uniform_size`, `rgbv.fps`, `rgbv.duration` (frames / fps), `rgbv.width`, `rgbv.height`
  - durations match within 0.05 s, fps within 0.01
- Manifest info: `version`, `path`, `report`, `manifest_version`, `clips`, `exported`, `frames`, `mismatches`, `mismatched_clips`, `encoded`

Mismatches are findings: they are counted and listed but never fail the stage.

## Arguments
| flag | default | meaning |
|---|---|---|
| `--encode` | off | encode each clip's frames to `encoded.mp4` through `video_encoder` (needs ffmpeg) |
| `--force` | off | export (and encode) clips that are already done |

## Failure modes
- No `unpack` record for the version, or no video files in it: run `zk unpack`.
- No `assets/Video` folder or no `manifest.json`: run `zk unpack --force`.
- A malformed `.rgbv` or `manifest.json`: the parser error, with the file path.
- `--encode` without ffmpeg: install ffmpeg (PATH or `[options.video_encoder] path`) or drop `--encode`.

## Tests
`tests/test_stage_video.py`: synthetic mp4/rgbv clips with one manifest mismatch, a clip missing from the manifest, resume and `--force`, a bad `.rgbv`, and `--encode` with `tests/fakes/fake_video_encoder.py`.

## Real run (0.4.6-17)
`zk video`: 9 clips, 1,189 frames exported, exit 0. The game's `manifest.json` (version 35) is out of date compared with the shipped files. The report has 40 mismatches, and every clip has at least one:

| clip | rgbv | manifest says | mismatches besides `mp4.bytes`/`mp4.sha256` |
|---|---|---|---|
| battle_intro | 15 fps, 53 frames, 960x540 | 30 fps, 1280x720 | rgbv fps, width, height |
| fortune_cat_spin | 15 fps, 68 frames, 960x540 | 30 fps, 1280x720 | rgbv fps, width, height |
| gianca_ultimate | 15 fps, 48 frames, 960x540 | 30 fps, 1280x720 | rgbv fps, width, height |
| lobby_ambient_loop | 15 fps, 120 frames, 960x540 | 30 fps, 1280x720 | rgbv fps, width, height |
| summon_bronze | 30 fps, 180 frames (6.0 s) | 4.2 s | mp4 and rgbv duration |
| summon_demigod | 30 fps, 180 frames (6.0 s) | 5.4 s | mp4 and rgbv duration |
| summon_divine | 30 fps, 180 frames (6.0 s) | 5.5 s | mp4 and rgbv duration |
| summon_gold | 30 fps, 180 frames (6.0 s) | 4.5 s | mp4 and rgbv duration |
| summon_silver | 30 fps, 180 frames (6.0 s) | 4.5 s | mp4 and rgbv duration |

No `.mp4` matches its manifest `bytes` or `sha256` (e.g. summon_bronze is 7,376,088 bytes; the manifest says 2,294,417). The four 15 fps clips keep the manifest's duration, so their `.rgbv` is a half-rate, lower-resolution copy of the `.mp4`.
