# Port: `<port>` (contract v1)

Module `zk/ports/<port>.py`. Changing this contract needs a new ADR.

## Protocol
```python
def method(self, ...) -> dict: ...
```

## Artifact contract
Files and folders the adapter must leave in its output folder.

| path | kind | content |
|---|---|---|

## Adapters
| name (`zk.toml` value) | tool | status |
|---|---|---|

## Options
`[options.<port>]` keys each adapter reads. Keys that don't change the output (e.g. a memory limit) go in the adapter's `UNFINGERPRINTED_OPTIONS: tuple[str, ...]`, so changing them doesn't make `zk update` rerun the step; every other key is part of the update fingerprint.

| adapter | key | default | in fingerprint |
|---|---|---|---|

## Notes
Known tool limits, for example which game or metadata versions break it.
