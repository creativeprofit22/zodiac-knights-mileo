# Port: `device_source` (contract v2)

Module `zk/ports/device_source.py`. Contract v2 comes from [ADR 0002](../adr/0002-device-source-v2.md). Changing it again needs a new ADR.

It gets the installed game for `package` (set in `zk.toml`, or with `zk acquire --package`) into `raw/<version>/`. The `acquire` stage calls it.

## Protocol
```python
class DeviceSource(Protocol):
    def identify(self, package: str) -> dict: ...         # {"package", "version", "abi"?}; RuntimeError if absent
    def pull(self, package: str, dest: Path) -> dict: ...  # returns {"pulled": {"apk": [...], "obb": bool, "data": bool}, ...}
```

`identify` runs first. Its `version` label (`versionName-versionCode`, e.g. `0.4.6-17`) picks `raw/<version>/`. It must contain only letters, digits, `.`, `_`, `+` or `-`, and the stage rejects any other label.

## Artifact contract
| path | kind | content |
|---|---|---|
| `apk/base.apk` | file | base APK (always present) |
| `apk/*.apk` | file | split APKs, if any |
| `obb/` | folder | OBB expansion files, if any |
| `data/` | folder | `/sdcard/Android/data/<pkg>` contents, if readable |

## Adapters
| name (`zk.toml` value) | tool | status |
|---|---|---|
| `adb` | adb (platform-tools, no root) | implemented, `zk/adapters/adb.py` |
| `folder` | local files | implemented, `zk/adapters/folder.py` |

### `adb`
- `identify` checks `adb devices`. It fails with a clear message when:
  - no device is connected;
  - the device is `unauthorized` or `offline`;
  - more than one device is ready and `ANDROID_SERIAL` is unset. The chosen serial is passed to every later adb call as `-s <serial>`.

  It then checks `pm list packages`, reads `versionName` and `versionCode` from `dumpsys package <pkg>`, and gets the ABI from `getprop ro.product.cpu.abi`.
- `pull` copies every split listed by `pm path <pkg>` into `apk/`. It then tries `/sdcard/Android/obb/<pkg>` into `obb/` and `/sdcard/Android/data/<pkg>` into `data/`. If either pull fails, it logs the failure, records `false` and carries on.
- adb is found by `zk.core.toolchain.adb()` (on Windows, `%LOCALAPPDATA%/Android/Sdk/platform-tools`). It is run through Python `subprocess` with native paths, so Git Bash path conversion never applies. To run `adb pull` by hand in Git Bash, set `MSYS_NO_PATHCONV=1` and use Windows-style destination paths.

### `folder`
Use it when the files are already on disk and no device is attached:
```toml
[adapters]
device_source = "folder"

[options.device_source]
path = "raw/0.4.6-17"   # a .apk file or a folder; relative to zk.toml
version = "0.4.6-17"    # required: there is no device to ask
```
- A single `.apk` is stored as `apk/base.apk`.
- A folder is copied file by file, in sorted order:
  - `*.apk` goes to `apk/`;
  - `*.obb` goes to `obb/`;
  - everything else goes to `data/<relative path>`. A leading `apk/`, `obb/` or `data/` folder is dropped, so a folder already in `raw/<v>/` layout keeps its shape.
- It raises `RuntimeError` when:
  - `path` or `version` is missing;
  - the path does not exist;
  - there is no `.apk`, or no `base.apk`;
  - two files map to the same destination.

## Notes
- `[options.<port>]` tables accept string values only, and naming an unknown port is an error.
- Tests: `tests/test_adb_adapter.py` uses a fake adb runner. `tests/test_folder_adapter.py` uses temporary files.
