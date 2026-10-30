# Stage: `unpack`

`zk unpack [--force]`, module `zk/stages/unpack.py`

## Purpose
Extracts the APKs and lists the engine, code and asset files of the Unity 6 IL2CPP build, so later stages can read these facts from the manifest instead of hard-coding them.

## Inputs
- `raw/<version>/apk/*.apk`, with `version` taken from `manifest["game"]` (written by `acquire`)
- No ports. It uses the parsers in `zk/formats`: [il2cpp_metadata](../formats/il2cpp_metadata.md), [unity_serialized](../formats/unity_serialized.md) and [scripting_assemblies](../formats/scripting_assemblies.md).

## Outputs
- `unpacked/<version>/<apk stem>/` for each APK, e.g. `unpacked/0.4.6-17/base/`. Each APK is extracted into `<stem>.partial/` and renamed when done, so an interrupted run is never mistaken for a finished one.
- Before extracting, it deletes every `unpacked/<version>/<stem>/` folder whose `<stem>.apk` is no longer in `raw/<v>/apk/` (a split that was uninstalled or renamed), so the inventory never reads stale files. This happens with or without `--force`.
- Manifest `unpack` info. Paths are relative to `unpacked/<version>/`:

| key | meaning |
|---|---|
| `version` | build label |
| `extracted` | APKs extracted in this run (`[]` when all were already unpacked) |
| `removed` | sorted folder names deleted because their APK is gone (`[]` when none) |
| `path` | absolute `unpacked/<version>/` |
| `abis` | sorted ABIs that have `lib/<abi>/libil2cpp.so` |
| `il2cpp` | `{abi: path to libil2cpp.so}` |
| `backend` | `il2cpp`, `mono` (`Managed/Assembly-CSharp.dll`) or `unknown` |
| `metadata` | `{path, magic ("0xFAB11BAF"), version, encrypted}` for `global-metadata.dat`, or `null` |
| `unity_version` | engine version from the `globalgamemanagers` SerializedFile header (e.g. `6000.3.2f1`) |
| `serialized_format` | SerializedFile format of `globalgamemanagers` (22 for Unity 6) |
| `assemblies` | `{count, game}` from `ScriptingAssemblies.json`. `game` is the sorted list of type-16 assemblies that are not Unity, System, Mono, mscorlib or netstandard. |
| `serialized_files` | number of SerializedFiles under `assets/bin/Data`. A `.splitN` set counts once, using the header in `.split0`. |
| `resource_streams` | number of `.resource` / `.resS` files under `assets/bin/Data` |
| `videos` | `{files: [{name, bytes}], manifest_json: bool}` for `assets/Video` |
| `warnings` | problems that did not stop the stage (see below) |
| `code_hash`, `adapters` | always recorded by the CLI |

- Game facts: `unity_version`, `metadata_version`, `backend`, `abis`

## Arguments
| flag | default | meaning |
|---|---|---|
| `--force` | off | delete and re-extract APKs that were already unpacked |

## Failure modes
- `RuntimeError` (exit code 2):
  - no version is recorded yet (run `zk acquire` first);
  - there are no APKs in `raw/<v>/apk/`;
  - an APK is not a valid zip.
- Recorded in `warnings` without stopping:
  - `globalgamemanagers` is missing or unreadable;
  - `global-metadata.dat` is missing for an IL2CPP build;
  - the metadata magic is wrong (`encrypted: true`);
  - the metadata version is not in `KNOWN_VERSIONS`;
  - `ScriptingAssemblies.json` is missing or malformed.

## Tests
`tests/test_stages_acquire_unpack.py` uses a synthetic APK that contains:
- 3 ABIs;
- metadata v39;
- `globalgamemanagers` with format 22 and version `6000.3.2f1`;
- a 3-part split file;
- `.resource` pairs;
- `ScriptingAssemblies.json`;
- `assets/Video`.

It checks every manifest field, that reruns skip extraction and `--force` re-extracts, that an orphan folder is removed and not inventoried, that an unknown metadata version only adds a warning, and that an empty tree produces warnings.
