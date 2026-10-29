# Format: `<format>`

Module `zk/formats/<format>.py`. A pure parser: bytes in, data out. It uses no tools and no workspace.

## Where it appears
Path pattern in the APK or workspace, and the game facts it depends on (for example the metadata version).

## Layout
| offset | size | type | field | notes |
|---|---|---|---|---|

## API
```python
def parse(data: bytes) -> ...: ...
```

## Evidence
How the layout was established: dump, Ghidra function or sample file. Keep game files out of git.

## Tests
Synthetic byte fixtures that cover each branch.
