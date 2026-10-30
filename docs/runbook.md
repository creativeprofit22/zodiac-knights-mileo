# Runbook

How to re-decompile a new game build, import an APK without a phone, and keep going when a tool breaks. How `zk update` decides what to rerun is in [Architecture: Update](architecture.md#update).

## A new game version

1. Connect the phone with the new build installed (`adb devices` lists it).
2. Preview: `zk update --dry-run`. Nothing is written and the device isn't asked. `acquire` shows as `check` ("checks the device source"), and later steps are planned as if the source were unchanged, so a dry run before a new version shows only code or config changes.
3. Run: `zk update`. `acquire` asks the device for its version. A new version (or a new `base.apk`) changes its fingerprint, so every step after it reruns.
4. Read the report printed at the end. It's also saved in `workspace/manifest.json` under `update`.

The plan line for each step shows its last duration, or an estimate if it never ran. `ghidra` is the slow one: import plus full analysis takes **about 45 minutes** on this PC's HDD, and **about 3 hours** when every function is decompiled again (any rerun that uses `--force`, which update does whenever ghidra's inputs changed). Everything else takes a few minutes.

### Warnings and checks in the report

| line | meaning | what to do |
|---|---|---|
| `unpack: metadata version N is not one ...` | `global-metadata.dat` has a format version the parsers weren't checked against | check `il2cpp/<v>/` and the dumper cross-check before trusting types; add the version to `formats/il2cpp_metadata.KNOWN_VERSIONS` once verified |
| `unpack: Unity version X is not one ...` | the engine changed | check `assets/<v>/report.json` misses and the MonoBehaviour failures; add it to `formats/unity_serialized.KNOWN_UNITY_VERSIONS` once verified |
| `unpack: ... not found` | the APK layout changed | inspect `unpacked/<v>/`; later steps will likely fail |
| `dumper cross-check types match: False` | the two IL2CPP dumpers disagree on type counts | see `il2cpp/<v>/crosscheck.json` and [il2cpp_crosscheck](ports/il2cpp_crosscheck.md) |
| `MonoBehaviour failed` / `unexplained` > 0 | some MonoBehaviours couldn't be read with the type trees | `assets/<v>/report.json` lists them by reason; `unexplained` ones are new failures |
| `assets cross-check unexplained` > 0 | exported assets disagree with the dump in a way no known reason covers | see `assets/<v>/report.json` |

### When a step fails

`zk update` stops at the first failure, exits 2 and prints:

```
[update] ghidra failed: <error>
  rerun:  zk ghidra
  resume: zk update --from ghidra
```

Fix the cause, then either rerun just that stage with the `rerun` command or resume the whole chain with `--from`. With `--from`, earlier steps aren't run; later steps compare what they use from them (the files and record values on disk now) against their stamps. A step that failed has no stamp, so the next `zk update` reruns it anyway.

Running a stage by hand (`zk ghidra`) records it without an update stamp, so the next `zk update` reruns it and everything after it. That's deliberate: update can't tell what arguments a manual run used.

`zk update --force` reruns every step with `--force` (acquire with `adb` then pulls the APK again, several GB).

### Measured on 0.4.6-17

Real runs with `zk.local.toml` (`folder` source) on this PC:

| run | why | ran | time |
|---|---|---|---|
| first `zk update` | no stamps yet | acquire 28s, unpack 47s, code 3.3 min, csharp 1.2 min, ghidra 44.1 min (exports reused); **assets failed** | 50.6 min, exit 2 with rerun/resume hints |
| second, after a `formats/csharp_dump.py` fix | code changed | code 1.6 min, ghidra 178.1 min (full decompile, upstream code changed), assets 1.2 min, video 3s; acquire, unpack, csharp skipped | 181.3 min, exit 0 |
| third | nothing changed | all 7 skipped | 35 s |

The assets failure was one unexplained dumper cross-check difference (`RenderGraphSettings`, 6 vs 5 methods). The cause was our parser miscounting an accessor with an attribute (`{ get; [Obsolete(...)] set; }`), not a dumper; see [csharp_dump](formats/csharp_dump.md). Final checks: dumper types match, 0 method-gap classes, 0 MonoBehaviour failures, 0 unexplained cross-check differences, no warnings. Video's 40 manifest mismatches are expected ([video](stages/video.md)).

## Importing an APK without a phone

Use the `folder` device source in a local config (for example `zk.local.toml`, which is gitignored):

```toml
[adapters]
device_source = "folder"

[options.device_source]
path = "raw/0.4.7-1"     # a .apk file, or a folder with apk/ (or *.apk), obb/, data/
version = "0.4.7-1"      # the label; the folder has no device to ask
```

Then `zk --config zk.local.toml update`. Give each new build a **new version label**. `acquire` skips the copy when `raw/<version>/apk/base.apk` already exists, so a different APK under the same label isn't picked up. If you must reuse a label, run `zk acquire --force` first.

## Swapping an adapter when a tool breaks

Every tool sits behind a port, and `zk.toml` picks the adapter.

- **The tool needs a new version.** Change its entry in `src/zk/core/pins.py`: the new `version`, `url` and the `sha256` of the download (`fetch` refuses a tool without one). Run `zk tools <name>`. Only the steps whose adapters list that tool in `PINNED` rerun; for example, bumping `jadx` reruns `code` and not `ghidra`.
- **Switch to another adapter.** Change the port's line in `[adapters]`, for example `type_info = "typetree_cpp2il"`. Run `zk update --dry-run` to see what reruns: the step using that port shows `adapter type_info: typetree_dummydll->typetree_cpp2il`, and its dependents show `<step> output … changed` only if that step's outputs they use differ (a dry run shows them as `maybe`, decided after the upstream runs).

A code-only change to a stage reruns that stage, not its dependents: for example, a `zk code` fix reruns ghidra only if `script.json` or `il2cpp.h` change.
- **Change an option.** Edits to `[options.<port>]` rerun only the steps that use that port, for example `option ghidra.decompile_timeout changed`.

A new adapter must declare `PORT`, `create(cfg)` and `PINNED` (the `pins.py` names it downloads; empty if none), plus `PACKAGES` for pip packages whose version matters. See [Architecture: How to add…](architecture.md#how-to-add).
