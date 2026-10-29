# Port: `device_source` (contract v1)

Module `zk/ports/device_source.py`. Changing this contract needs a new ADR.

Pulls the installed APK for cfg.package into raw/<version>/.

## Protocol
```python
class DeviceSource(Protocol):
    def pull(self, package: str, dest: Path) -> dict: ...
```

## Artifact contract
| path | kind | content |
|---|---|---|
| `base.apk` | file | |

## Adapters
| name (`zk.toml` value) | tool | status |
|---|---|---|
| none yet | | added by its adapter phase |
