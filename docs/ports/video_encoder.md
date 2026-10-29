# Port: `video_encoder` (contract v1)

Module `zk/ports/video_encoder.py`. Changing this contract needs a new ADR ([ADR 0007](../adr/0007-video-encoder.md)).

## Protocol
```python
def encode(self, frames_dir: Path, fps: int, out: Path) -> dict: ...
```
`frames_dir` holds `frame_0000.jpg …` from `zk video`; `fps` is the `.rgbv` header value.

## Artifact contract
| path | kind | content |
|---|---|---|
| `encoded.mp4` | file | H.264 video of the frames, non-empty (`verify_output`) |

## Adapters
| name (`zk.toml` value) | tool | status |
|---|---|---|
| `ffmpeg` | user-installed ffmpeg (`[options.video_encoder] path`, else PATH) | implemented; never downloaded |

## Notes
Command: `ffmpeg -y -framerate <fps> -start_number 0 -i frame_%04d.jpg -c:v libx264 -pix_fmt yuv420p encoded.mp4`. A missing ffmpeg raises "install ffmpeg … or drop --encode". CI has no ffmpeg, so tests check the command line and use a fake encoder.
