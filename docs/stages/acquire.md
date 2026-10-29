# Stage: `acquire`

`zk acquire [--package PKG] [--force]`, module `zk/stages/acquire.py`

## Purpose
Gets the installed game into `raw/<version>/` through the [`device_source`](../ports/device_source.md) port, and records which build it is.

## Inputs
- `package` from `zk.toml` (`com.zodiacknights.game`), or `--package`
- Port `device_source`. The adapter is chosen in `[adapters]` (`adb` or `folder`), with settings in `[options.device_source]`.

## Outputs
- `raw/<version>/apk/base.apk` (plus any splits), and `obb/` and `data/` when available
- Manifest `acquire` info:

| key | meaning |
|---|---|
| `package` | Android package |
| `version` | `versionName-versionCode` label from `identify` |
| `abi` | device primary ABI (`null` for `folder`) |
| `pulled` | adapter's `{"apk": [...], "obb": bool, "data": bool}`, or `false` when the pull was skipped |
| `base_apk` | `{"sha256", "bytes"}` of `apk/base.apk` (streamed hash) |
| `path` | absolute `raw/<version>/` folder |
| `code_hash`, `adapters` | always recorded by the CLI |

- Game facts: `version`, `package`

## Arguments
| flag | default | meaning |
|---|---|---|
| `--package` | `package` in `zk.toml` | package to pull |
| `--force` | off | pull again even if `apk/base.apk` already exists |

## Failure modes
Each of these is a `RuntimeError` and exits with code 2:
- No package is configured.
- `identify` fails: no device, device unauthorized, several devices without `ANDROID_SERIAL`, package not installed, or `folder` options missing.
- The version label contains path separators or other unsafe characters.
- After the pull, the contract check fails because `apk/base.apk` is missing.

Nothing is recorded in the manifest when the stage fails.

## Tests
`tests/test_stages_acquire_unpack.py` runs `cli.main(["acquire"])` with `tests/fakes/fake_device.py`, an adapter that writes a synthetic zip APK. It checks:
- the sha256 and size of `base.apk`;
- the game facts;
- that a rerun skips the pull;
- that labels such as `../evil`, `a/b` and `..` are rejected.
