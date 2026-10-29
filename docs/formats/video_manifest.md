# Format: `video_manifest`

Module `zk/formats/video_manifest.py`. A pure parser: text in, frozen dataclasses out.

## Where it appears
`unpacked/<v>/base/assets/Video/manifest.json` (version 35 on 0.4.6-17).

## Layout
Top level: `version` (int), `generated`, `clips` (list). Each clip: `name` (`<clip>.mp4`), `bytes`, `sha256`, `duration`, `loop`, `fps`, `width`, `height`, `codec`, `audio`, `source`, `generator`.

The parser keeps the fields the stage checks: `name`, `bytes`, `sha256`, `duration`, `fps`, `width`, `height`. Each is required with the right JSON type.

## API
```python
def parse(text: str) -> VideoManifest: ...   # VideoManifest(version, clips: tuple[Clip, ...])
```
Raises `ValueError` naming the clip and key on a missing or mistyped field, and on a duplicate clip name.

## Evidence
The shipped file on 0.4.6-17. It is out of date against the shipped videos; see [stage video](../stages/video.md).

## Tests
`tests/test_formats_video.py`: a valid manifest and one with a missing key.
