# Format: `mp4`

Module `zk/formats/mp4.py`. A pure parser: bytes in, data out. It uses no tools and no workspace. It walks ISO-BMFF boxes only and never decodes video.

## Where it appears
`unpacked/<v>/base/assets/Video/<clip>.mp4`.

## Layout
| box path | field | notes |
|---|---|---|
| `moov/mvhd` | timescale, duration | movie duration in seconds (`Mp4Info.duration`) |
| `moov/trak/tkhd` | width, height | 16.16 fixed point |
| `trak/mdia/hdlr` | handler | `vide` picks the video track |
| `trak/mdia/mdhd` | timescale, duration | media duration (`VideoTrack.duration`) |
| `trak/mdia/minf/stbl/stts` | sample counts | frame count; fps = frames / media duration |

Box versions 0 and 1 (32/64-bit times) and 64-bit box sizes are handled.

## API
```python
def parse(data: bytes) -> Mp4Info: ...   # Mp4Info(duration, video: VideoTrack | None)
```
Raises `ValueError` on a truncated or bad-size box, a missing `moov`/`mvhd`, or a video track without `tkhd`, `mdhd` or `stts`.

## Evidence
Checked against the 9 shipped clips of 0.4.6-17. Edit lists and variable frame rates are not interpreted; if `mvhd` and the track disagree, the stage report shows it.

## Tests
`tests/test_formats_video.py`: synthetic boxes built in the test.
