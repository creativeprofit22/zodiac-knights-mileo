# Format: `rgbv`

Module `zk/formats/rgbv.py`. A pure parser: bytes in, data out. It uses no tools and no workspace.

## Where it appears
`unpacked/<v>/base/assets/Video/<clip>.rgbv`, next to `<clip>.mp4` and `manifest.json`. 9 clips on 0.4.6-17.

## Layout
All integers little-endian. Every field is verified on all 9 files of 0.4.6-17, with no bytes left over.

| offset | size | type | field | notes |
|---|---|---|---|---|
| 0 | 4 | u32 | fps | 15 or 30 |
| 4 | 4 | u32 | frame_count | 48–180; equals the number of frames that follow |
| 8 | 4 | u32 | size | per frame: byte size of the JPEG |
| 12 | size | bytes | jpeg | whole baseline JPEG, `FFD8` … `FFD9`; repeat size + jpeg `frame_count` times |

Width and height are not in the header; they come from each JPEG's SOF0/SOF2 marker (`jpeg_size`).

## API
```python
def parse(data: bytes) -> Rgbv: ...           # Rgbv(fps, frame_count, frames: tuple[bytes, ...])
def jpeg_size(frame: bytes) -> tuple[int, int]: ...  # (width, height)
```
`parse` raises `ValueError` on a short header, an fps of 0, a size running past the end, a frame without SOI/EOI, a count mismatch or leftover bytes.

## Evidence
Read directly from the 9 shipped files: header values, frame sizes and SOI/EOI markers line up exactly. The JPEG comment says `Lavc62.28.100`, so the frames were written by ffmpeg. The generator script named in the manifest (`Tools/v20_video/render_procedural.py`) is not in the APK and not available; the decoded files are the only source.

## Tests
`tests/test_formats_video.py`: a 3-frame file of tiny synthetic JPEGs, plus each error case.
